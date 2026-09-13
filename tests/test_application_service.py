"""
test_application_service.py

Tests for `ApplicationService`, the business-logic layer between the CLI
and the repository. These confirm that: validation is actually enforced
before data reaches the database, duplicates are rejected, partial
updates only touch the fields supplied, and repository-level failures
(missing records) surface as the service's own exception types.
"""

from __future__ import annotations

import pytest

from app.models.application import JobType, Priority, Status, WorkMode
from app.services.exceptions import ApplicationNotFoundError, DuplicateApplicationError
from app.validators.validators import ValidationError


class TestCreate:
    def test_add_application_succeeds_with_valid_data(self, app_service, sample_application_kwargs) -> None:
        application = app_service.add_application(**sample_application_kwargs)
        assert application.id is not None
        assert application.company == sample_application_kwargs["company"]
        assert application.status == Status.APPLIED
        assert application.tags == ["referral", "dream-job"]
        assert application.interview_rounds == 1

    def test_add_application_validates_required_fields(self, app_service, sample_application_kwargs) -> None:
        sample_application_kwargs["company"] = "   "
        with pytest.raises(ValidationError, match="Company is required"):
            app_service.add_application(**sample_application_kwargs)

    def test_add_application_validates_date(self, app_service, sample_application_kwargs) -> None:
        sample_application_kwargs["application_date"] = "not-a-date"
        with pytest.raises(ValidationError):
            app_service.add_application(**sample_application_kwargs)

    def test_add_application_validates_salary(self, app_service, sample_application_kwargs) -> None:
        sample_application_kwargs["salary"] = "twenty thousand"
        with pytest.raises(ValidationError, match="non-negative number"):
            app_service.add_application(**sample_application_kwargs)

    def test_add_application_validates_status(self, app_service, sample_application_kwargs) -> None:
        sample_application_kwargs["status"] = "Ghosted"
        with pytest.raises(ValidationError):
            app_service.add_application(**sample_application_kwargs)

    def test_add_application_validates_job_type(self, app_service, sample_application_kwargs) -> None:
        sample_application_kwargs["job_type"] = "Freelance"
        with pytest.raises(ValidationError):
            app_service.add_application(**sample_application_kwargs)

    def test_add_application_validates_work_mode(self, app_service, sample_application_kwargs) -> None:
        sample_application_kwargs["work_mode"] = "From Home"
        with pytest.raises(ValidationError):
            app_service.add_application(**sample_application_kwargs)

    def test_add_application_validates_priority(self, app_service, sample_application_kwargs) -> None:
        sample_application_kwargs["priority"] = "Urgent"
        with pytest.raises(ValidationError):
            app_service.add_application(**sample_application_kwargs)

    def test_add_application_validates_url(self, app_service, sample_application_kwargs) -> None:
        sample_application_kwargs["job_url"] = "not-a-url"
        with pytest.raises(ValidationError, match="must start with http"):
            app_service.add_application(**sample_application_kwargs)

    def test_add_application_rejects_duplicate(self, app_service, sample_application_kwargs) -> None:
        app_service.add_application(**sample_application_kwargs)
        with pytest.raises(DuplicateApplicationError):
            app_service.add_application(**sample_application_kwargs)

    def test_add_application_no_data_left_after_validation_failure(
        self, app_service, sample_application_kwargs
    ) -> None:
        sample_application_kwargs["status"] = "Ghosted"
        with pytest.raises(ValidationError):
            app_service.add_application(**sample_application_kwargs)
        assert app_service.list_applications() == []


class TestRead:
    def test_get_application_returns_record(self, app_service, sample_application_kwargs) -> None:
        created = app_service.add_application(**sample_application_kwargs)
        fetched = app_service.get_application(created.id)
        assert fetched.id == created.id
        assert fetched.company == created.company

    def test_get_nonexistent_application_raises(self, app_service) -> None:
        with pytest.raises(ApplicationNotFoundError, match="No application found"):
            app_service.get_application(9999)

    def test_get_application_invalid_id_raises_validation_error(self, app_service) -> None:
        with pytest.raises(ValidationError):
            app_service.get_application("not-an-id")

    def test_list_applications_empty(self, app_service) -> None:
        assert app_service.list_applications() == []


class TestUpdate:
    def test_partial_update_only_changes_given_fields(self, app_service, sample_application_kwargs) -> None:
        created = app_service.add_application(**sample_application_kwargs)
        updated = app_service.update_application(created.id, status=Status.INTERVIEW.value)

        assert updated.status == Status.INTERVIEW
        assert updated.company == sample_application_kwargs["company"]
        assert updated.job_title == sample_application_kwargs["job_title"]
        assert updated.salary == "200000"

    def test_update_nonexistent_application_raises(self, app_service) -> None:
        with pytest.raises(ApplicationNotFoundError):
            app_service.update_application(9999, status=Status.OFFER.value)

    def test_update_validates_changed_field(self, app_service, sample_application_kwargs) -> None:
        created = app_service.add_application(**sample_application_kwargs)
        with pytest.raises(ValidationError):
            app_service.update_application(created.id, salary="not-a-number")

    def test_update_does_not_revalidate_untouched_field(self, app_service, repository) -> None:
        # Simulate a "legacy" record whose salary predates the numeric
        # salary rule (as if written directly, bypassing validation).
        from app.models.application import JobApplication

        legacy = JobApplication(
            company="LegacyCo", job_title="Old Role", application_date="2026-01-01", salary="20 LPA"
        )
        new_id = repository.create(legacy)

        # Updating only the status must succeed even though `salary`
        # would fail validate_salary if it were re-checked.
        updated = app_service.update_application(new_id, status=Status.INTERVIEW.value)
        assert updated.salary == "20 LPA"
        assert updated.status == Status.INTERVIEW

    def test_update_tags_and_interview_rounds(self, app_service, sample_application_kwargs) -> None:
        created = app_service.add_application(**sample_application_kwargs)
        updated = app_service.update_application(created.id, tags="onsite-done", interview_rounds=3)
        assert updated.tags == ["onsite-done"]
        assert updated.interview_rounds == 3

    def test_update_to_duplicate_combo_raises(self, app_service, sample_application_kwargs) -> None:
        app_service.add_application(**sample_application_kwargs)
        other_kwargs = dict(sample_application_kwargs)
        other_kwargs["job_title"] = "Different Role"
        other = app_service.add_application(**other_kwargs)

        with pytest.raises(DuplicateApplicationError):
            app_service.update_application(other.id, job_title=sample_application_kwargs["job_title"])


class TestDelete:
    def test_delete_removes_application(self, app_service, sample_application_kwargs) -> None:
        created = app_service.add_application(**sample_application_kwargs)
        deleted = app_service.delete_application(created.id)
        assert deleted.id == created.id
        with pytest.raises(ApplicationNotFoundError):
            app_service.get_application(created.id)

    def test_delete_nonexistent_application_raises(self, app_service) -> None:
        with pytest.raises(ApplicationNotFoundError):
            app_service.delete_application(9999)


class TestSearch:
    def test_search_matches_company_case_insensitive(self, app_service, sample_application_kwargs) -> None:
        app_service.add_application(**sample_application_kwargs)
        results = app_service.search_applications("technova")
        assert len(results) == 1

    def test_search_matches_job_title(self, app_service, sample_application_kwargs) -> None:
        app_service.add_application(**sample_application_kwargs)
        results = app_service.search_applications("Backend")
        assert len(results) == 1

    def test_search_blank_keyword_raises(self, app_service) -> None:
        with pytest.raises(ValidationError):
            app_service.search_applications("")

    def test_search_no_match_returns_empty(self, app_service, sample_application_kwargs) -> None:
        app_service.add_application(**sample_application_kwargs)
        assert app_service.search_applications("nonexistent-xyz") == []


class TestFilter:
    def _seed_two(self, app_service, sample_application_kwargs) -> None:
        app_service.add_application(**sample_application_kwargs)
        other = dict(sample_application_kwargs)
        other.update(
            company="Globex",
            job_title="Data Analyst",
            status=Status.INTERVIEW.value,
            job_type=JobType.INTERNSHIP.value,
            work_mode=WorkMode.HYBRID.value,
            priority=Priority.LOW.value,
            application_date="2026-08-20",
        )
        app_service.add_application(**other)

    def test_filter_by_status(self, app_service, sample_application_kwargs) -> None:
        self._seed_two(app_service, sample_application_kwargs)
        results = app_service.filter_applications(status="Interview")
        assert len(results) == 1
        assert results[0].company == "Globex"

    def test_filter_combined_criteria(self, app_service, sample_application_kwargs) -> None:
        self._seed_two(app_service, sample_application_kwargs)
        results = app_service.filter_applications(job_type="Internship", work_mode="Hybrid")
        assert len(results) == 1
        assert results[0].company == "Globex"

    def test_filter_invalid_status_raises(self, app_service) -> None:
        with pytest.raises(ValidationError):
            app_service.filter_applications(status="NotAStatus")

    def test_filter_invalid_date_range_raises(self, app_service) -> None:
        with pytest.raises(ValidationError, match="must not be after"):
            app_service.filter_applications(date_from="2026-09-01", date_to="2026-01-01")

    def test_filter_no_criteria_returns_all(self, app_service, sample_application_kwargs) -> None:
        self._seed_two(app_service, sample_application_kwargs)
        assert len(app_service.filter_applications()) == 2
