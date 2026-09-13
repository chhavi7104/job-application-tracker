"""
application_service.py

`ApplicationService` is the business-logic layer for job applications. It
is the only layer the CLI is allowed to call into for CRUD/search
operations, and the only layer that talks directly to
`ApplicationRepository`.

Responsibilities:
    - Validate and normalize all input (via `app.validators.validators`)
      before it becomes/updates a `JobApplication`.
    - Enforce business rules that don't belong in the database or the
      CLI - e.g. rejecting duplicate applications (same company + job
      title + application date).
    - Translate low-level `app.database.exceptions` into the service's
      own exception types (`app.services.exceptions`), so the CLI never
      needs to import anything from `app.database`.
    - Support partial updates: `update_application` only touches fields
      the caller actually supplies, leaving everything else unchanged.

The CLI layer must not construct `JobApplication` objects, call the
repository, or contain any of the logic below directly.
"""

from __future__ import annotations

from typing import Any, Optional

from app.database.exceptions import DatabaseError, IntegrityConstraintError, RecordNotFoundError
from app.database.repository import ApplicationRepository
from app.models.application import JobApplication, JobType, Priority, Status, WorkMode
from app.services.exceptions import ApplicationNotFoundError, DuplicateApplicationError, ServiceError
from app.utils.logger import get_logger
from app.validators.validators import (
    ValidationError,
    validate_application_date,
    validate_date_range,
    validate_follow_up_date,
    validate_id,
    validate_interview_rounds,
    validate_job_type,
    validate_job_url,
    validate_optional_text,
    validate_priority,
    validate_required_text,
    validate_salary,
    validate_status,
    validate_tags,
    validate_work_mode,
)

logger = get_logger(__name__)

# Sentinel used to distinguish "field not supplied" (leave unchanged) from
# an explicit value (including an explicit empty string, which clears an
# optional field) in `update_application`.
_UNSET: Any = object()


class ApplicationService:
    """Business-logic layer for creating, reading, updating, deleting, and
    searching job applications."""

    def __init__(self, repository: Optional[ApplicationRepository] = None) -> None:
        self._repository = repository or ApplicationRepository()

    # --- Create --------------------------------------------------------------

    def add_application(
        self,
        *,
        company: str,
        job_title: str,
        application_date: str,
        job_type: str = JobType.FULL_TIME.value,
        work_mode: str = WorkMode.ON_SITE.value,
        status: str = Status.APPLIED.value,
        priority: str = Priority.MEDIUM.value,
        location: Optional[str] = None,
        salary: Optional[str] = None,
        job_url: Optional[str] = None,
        recruiter: Optional[str] = None,
        notes: Optional[str] = None,
        follow_up_date: Optional[str] = None,
        tags: Optional[str] = None,
        interview_rounds: Any = 0,
    ) -> JobApplication:
        """Validate input and create a new job application.

        Returns:
            The newly created `JobApplication`, including its assigned
            `id`, `created_at`, and `updated_at`.

        Raises:
            ValidationError: If any field fails validation.
            DuplicateApplicationError: If an application with the same
                company, job title, and application date already exists.
            ServiceError: For any other unexpected database failure.
        """
        application = JobApplication(
            company=validate_required_text(company, "Company", max_length=150),
            job_title=validate_required_text(job_title, "Job title", max_length=150),
            application_date=validate_application_date(application_date),
            job_type=validate_job_type(job_type),
            work_mode=validate_work_mode(work_mode),
            status=validate_status(status),
            priority=validate_priority(priority),
            location=validate_optional_text(location, "Location", max_length=150),
            salary=validate_salary(salary),
            job_url=validate_job_url(job_url),
            recruiter=validate_optional_text(recruiter, "Recruiter", max_length=150),
            notes=validate_optional_text(notes, "Notes", max_length=2000),
            follow_up_date=validate_follow_up_date(follow_up_date),
            tags=validate_tags(tags),
            interview_rounds=validate_interview_rounds(interview_rounds),
        )

        self._reject_if_duplicate(application)

        try:
            new_id = self._repository.create(application)
        except IntegrityConstraintError as exc:
            raise ValidationError(f"Invalid application data: {exc}") from exc
        except DatabaseError as exc:
            raise ServiceError("Could not save the application due to a database error.") from exc

        logger.info("Added application id=%s (%s @ %s)", new_id, application.job_title, application.company)
        return self._repository.get_by_id(new_id)

    # --- Read ----------------------------------------------------------------

    def get_application(self, application_id: Any) -> JobApplication:
        """Fetch a single application by id.

        Raises:
            ValidationError: If `application_id` isn't a positive integer.
            ApplicationNotFoundError: If no application with that id exists.
            ServiceError: For any other unexpected database failure.
        """
        valid_id = validate_id(application_id)
        try:
            record = self._repository.get_by_id(valid_id)
        except DatabaseError as exc:
            raise ServiceError("Could not fetch the application due to a database error.") from exc

        if record is None:
            raise ApplicationNotFoundError(f"No application found with ID {valid_id}.")
        return record

    def list_applications(self) -> list[JobApplication]:
        """Fetch every application, most recently applied first.

        Raises:
            ServiceError: If the database read fails.
        """
        try:
            return self._repository.get_all()
        except DatabaseError as exc:
            raise ServiceError("Could not fetch applications due to a database error.") from exc

    def search_applications(self, keyword: str) -> list[JobApplication]:
        """Search applications by company, job title, location, status,
        recruiter, or tags (case-insensitive substring match on any of them).

        Raises:
            ValidationError: If `keyword` is empty.
            ServiceError: If the database search fails.
        """
        cleaned = validate_required_text(keyword, "Search keyword", max_length=200)
        try:
            return self._repository.search(cleaned)
        except DatabaseError as exc:
            raise ServiceError("Could not search applications due to a database error.") from exc

    def filter_applications(
        self,
        *,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        work_mode: Optional[str] = None,
        priority: Optional[str] = None,
        company: Optional[str] = None,
        location: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list[JobApplication]:
        """Fetch applications matching any combination of filters.

        Every argument is optional; only the ones actually supplied
        (not `None`/empty) are validated and applied, combined with
        `AND`, so callers can freely combine e.g. status + date range, or
        just job_type alone. `status`/`job_type`/`work_mode`/`priority`
        are validated against their allowed enum values; `company` and
        `location` are matched as case-insensitive substrings; the date
        range is inclusive and validated as a coherent range (`date_from`
        not after `date_to`).

        Raises:
            ValidationError: If any supplied filter value is invalid, or
                the date range is incoherent.
            ServiceError: If the database query fails.
        """
        validated_status = validate_status(status).value if status else None
        validated_job_type = validate_job_type(job_type).value if job_type else None
        validated_work_mode = validate_work_mode(work_mode).value if work_mode else None
        validated_priority = validate_priority(priority).value if priority else None
        validated_company = validate_optional_text(company, "Company", max_length=150)
        validated_location = validate_optional_text(location, "Location", max_length=150)
        validated_from, validated_to = validate_date_range(date_from, date_to)

        try:
            return self._repository.filter_applications(
                status=validated_status,
                job_type=validated_job_type,
                work_mode=validated_work_mode,
                priority=validated_priority,
                company=validated_company,
                location=validated_location,
                date_from=validated_from,
                date_to=validated_to,
            )
        except DatabaseError as exc:
            raise ServiceError("Could not filter applications due to a database error.") from exc

    # --- Update ------------------------------------------------------------

    def update_application(
        self,
        application_id: Any,
        *,
        company: Any = _UNSET,
        job_title: Any = _UNSET,
        location: Any = _UNSET,
        job_type: Any = _UNSET,
        work_mode: Any = _UNSET,
        application_date: Any = _UNSET,
        status: Any = _UNSET,
        salary: Any = _UNSET,
        job_url: Any = _UNSET,
        recruiter: Any = _UNSET,
        notes: Any = _UNSET,
        priority: Any = _UNSET,
        follow_up_date: Any = _UNSET,
        tags: Any = _UNSET,
        interview_rounds: Any = _UNSET,
    ) -> JobApplication:
        """Partially update an existing application.

        Only keyword arguments that are actually supplied are validated
        and applied; any left at their default (unset) are left
        untouched. This lets the CLI prompt "press Enter to keep current
        value" for each field without the caller needing to re-fetch and
        re-submit unchanged data.

        Raises:
            ValidationError: If any supplied field fails validation.
            ApplicationNotFoundError: If no application with that id exists.
            DuplicateApplicationError: If the update would collide with
                another existing application's company/title/date.
            ServiceError: For any other unexpected database failure.
        """
        existing = self.get_application(application_id)

        if company is not _UNSET:
            existing.company = validate_required_text(company, "Company", max_length=150)
        if job_title is not _UNSET:
            existing.job_title = validate_required_text(job_title, "Job title", max_length=150)
        if application_date is not _UNSET:
            existing.application_date = validate_application_date(application_date)
        if job_type is not _UNSET:
            existing.job_type = validate_job_type(job_type)
        if work_mode is not _UNSET:
            existing.work_mode = validate_work_mode(work_mode)
        if status is not _UNSET:
            existing.status = validate_status(status)
        if priority is not _UNSET:
            existing.priority = validate_priority(priority)
        if location is not _UNSET:
            existing.location = validate_optional_text(location, "Location", max_length=150)
        if salary is not _UNSET:
            existing.salary = validate_salary(salary)
        if job_url is not _UNSET:
            existing.job_url = validate_job_url(job_url)
        if recruiter is not _UNSET:
            existing.recruiter = validate_optional_text(recruiter, "Recruiter", max_length=150)
        if notes is not _UNSET:
            existing.notes = validate_optional_text(notes, "Notes", max_length=2000)
        if follow_up_date is not _UNSET:
            existing.follow_up_date = validate_follow_up_date(follow_up_date)
        if tags is not _UNSET:
            existing.tags = validate_tags(tags)
        if interview_rounds is not _UNSET:
            existing.interview_rounds = validate_interview_rounds(interview_rounds)

        self._reject_if_duplicate(existing, exclude_id=existing.id)

        try:
            self._repository.update(existing)
        except RecordNotFoundError as exc:
            raise ApplicationNotFoundError(str(exc)) from exc
        except IntegrityConstraintError as exc:
            raise ValidationError(f"Invalid application data: {exc}") from exc
        except DatabaseError as exc:
            raise ServiceError("Could not update the application due to a database error.") from exc

        logger.info("Updated application id=%s", existing.id)
        return self._repository.get_by_id(existing.id)

    # --- Delete ------------------------------------------------------------

    def delete_application(self, application_id: Any) -> JobApplication:
        """Delete an application by id.

        The caller (CLI) is responsible for confirming the deletion with
        the user before calling this method - the service layer performs
        the deletion unconditionally once called.

        Returns:
            The `JobApplication` that was deleted (useful for confirmation
            messages, since the data is no longer retrievable afterwards).

        Raises:
            ValidationError: If `application_id` isn't a positive integer.
            ApplicationNotFoundError: If no application with that id exists.
            ServiceError: For any other unexpected database failure.
        """
        existing = self.get_application(application_id)

        try:
            self._repository.delete(existing.id)
        except RecordNotFoundError as exc:
            raise ApplicationNotFoundError(str(exc)) from exc
        except DatabaseError as exc:
            raise ServiceError("Could not delete the application due to a database error.") from exc

        logger.info("Deleted application id=%s (%s @ %s)", existing.id, existing.job_title, existing.company)
        return existing

    # --- Internal helpers ----------------------------------------------------

    def _reject_if_duplicate(self, application: JobApplication, exclude_id: Optional[int] = None) -> None:
        """Raise `DuplicateApplicationError` if another record already
        shares this application's company, job title, and application
        date."""
        try:
            duplicate = self._repository.exists(
                application.company,
                application.job_title,
                application.application_date,
                exclude_id=exclude_id,
            )
        except DatabaseError as exc:
            raise ServiceError("Could not verify the application due to a database error.") from exc

        if duplicate:
            raise DuplicateApplicationError(
                f"An application for '{application.job_title}' at '{application.company}' "
                f"on {application.application_date} already exists."
            )
