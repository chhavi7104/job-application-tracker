"""
repository.py

Implements the repository pattern for the `applications` table:
`ApplicationRepository` is the single place in the codebase that contains
raw SQL. It exposes a small, well-typed interface (create/get/get_all/
update/delete/search/filter_applications/exists, plus analytics-support
reads like count_by_status/count_by_company/get_recent/get_with_follow_up)
that the services layer calls.

Design notes:
    - Every query is parameterized (no string-formatted SQL) to prevent
      SQL injection and correctly handle user-supplied values.
    - `sqlite3.Error` subclasses are always caught here and re-raised as
      the application's own `app.database.exceptions` types, so callers
      outside this module never need to import `sqlite3` themselves.
    - This module has no CLI or business-logic concerns: it only moves
      `JobApplication` objects in and out of SQLite.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from app.database.connection import get_connection
from app.database.exceptions import (
    DatabaseError,
    IntegrityConstraintError,
    RecordNotFoundError,
)
from app.models.application import JobApplication
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ApplicationRepository:
    """Data-access layer for `JobApplication` records.

    Each method opens its own connection (via `get_connection()`), so a
    repository instance is stateless and safe to reuse or recreate freely.
    """

    # --- Create ----------------------------------------------------------

    def create(self, application: JobApplication) -> int:
        """Insert a new job application record.

        Args:
            application: The `JobApplication` to persist. Its `id`,
                `created_at`, and `updated_at` fields are ignored on input
                and assigned by the database.

        Returns:
            The auto-generated `id` of the newly created record.

        Raises:
            IntegrityConstraintError: If the data violates a table
                constraint (e.g. an invalid `status` value, or an empty
                `company`/`job_title`).
            DatabaseError: For any other database failure.
        """
        data = application.to_dict()
        query = """
            INSERT INTO applications (
                company, job_title, location, job_type, work_mode,
                application_date, status, salary, job_url, recruiter,
                notes, priority, follow_up_date, tags, interview_rounds
            ) VALUES (
                :company, :job_title, :location, :job_type, :work_mode,
                :application_date, :status, :salary, :job_url, :recruiter,
                :notes, :priority, :follow_up_date, :tags, :interview_rounds
            );
        """
        try:
            with get_connection() as conn:
                cursor = conn.execute(query, data)
                new_id = cursor.lastrowid
            logger.info("Created application id=%s (%s @ %s)", new_id, data["job_title"], data["company"])
            return new_id
        except sqlite3.IntegrityError as exc:
            logger.warning("Integrity error creating application: %s", exc)
            raise IntegrityConstraintError(str(exc)) from exc
        except sqlite3.Error as exc:
            logger.error("Database error creating application: %s", exc)
            raise DatabaseError(str(exc)) from exc

    # --- Read --------------------------------------------------------------

    def get_by_id(self, application_id: int) -> Optional[JobApplication]:
        """Fetch a single application by its primary key.

        Args:
            application_id: The `id` of the record to fetch.

        Returns:
            The matching `JobApplication`, or `None` if no record with
            that id exists.

        Raises:
            DatabaseError: If the query fails.
        """
        query = "SELECT * FROM applications WHERE id = ?;"
        try:
            with get_connection() as conn:
                row = conn.execute(query, (application_id,)).fetchone()
            return JobApplication.from_row(row) if row else None
        except sqlite3.Error as exc:
            logger.error("Database error fetching application id=%s: %s", application_id, exc)
            raise DatabaseError(str(exc)) from exc

    def get_all(self) -> list[JobApplication]:
        """Fetch all application records, most recently applied first.

        Returns:
            A list of every `JobApplication` in the database (empty list
            if there are none).

        Raises:
            DatabaseError: If the query fails.
        """
        query = "SELECT * FROM applications ORDER BY application_date DESC, id DESC;"
        try:
            with get_connection() as conn:
                rows = conn.execute(query).fetchall()
            return [JobApplication.from_row(row) for row in rows]
        except sqlite3.Error as exc:
            logger.error("Database error fetching all applications: %s", exc)
            raise DatabaseError(str(exc)) from exc

    def exists(
        self,
        company: str,
        job_title: str,
        application_date: str,
        exclude_id: Optional[int] = None,
    ) -> bool:
        """Check whether an application with the same company, job title,
        and application date already exists (used to prevent duplicates).

        Matching is case-insensitive on `company` and `job_title`.

        Args:
            company: Company name to match.
            job_title: Job title to match.
            application_date: Application date to match (YYYY-MM-DD).
            exclude_id: If given, a record with this id is ignored (used
                when checking for duplicates during an update, so a
                record doesn't collide with itself).

        Returns:
            `True` if a matching record exists, `False` otherwise.

        Raises:
            DatabaseError: If the query fails.
        """
        query = """
            SELECT 1 FROM applications
            WHERE company COLLATE NOCASE = :company
              AND job_title COLLATE NOCASE = :job_title
              AND application_date = :application_date
              AND (:exclude_id IS NULL OR id != :exclude_id)
            LIMIT 1;
        """
        params = {
            "company": company,
            "job_title": job_title,
            "application_date": application_date,
            "exclude_id": exclude_id,
        }
        try:
            with get_connection() as conn:
                row = conn.execute(query, params).fetchone()
            return row is not None
        except sqlite3.Error as exc:
            logger.error("Database error checking duplicate application: %s", exc)
            raise DatabaseError(str(exc)) from exc

    def search(self, keyword: str) -> list[JobApplication]:
        """Search applications by company, job title, location, status,
        recruiter, or tags.

        Performs a case-insensitive substring match against all six
        fields; a record matches if *any* of them contain the keyword.

        Args:
            keyword: The text to search for.

        Returns:
            A list of matching `JobApplication` records (empty list if
            none match).

        Raises:
            DatabaseError: If the query fails.
        """
        query = """
            SELECT * FROM applications
            WHERE company   COLLATE NOCASE LIKE :pattern
               OR job_title COLLATE NOCASE LIKE :pattern
               OR location  COLLATE NOCASE LIKE :pattern
               OR status    COLLATE NOCASE LIKE :pattern
               OR recruiter COLLATE NOCASE LIKE :pattern
               OR tags      COLLATE NOCASE LIKE :pattern
            ORDER BY application_date DESC, id DESC;
        """
        pattern = f"%{keyword}%"
        try:
            with get_connection() as conn:
                rows = conn.execute(query, {"pattern": pattern}).fetchall()
            return [JobApplication.from_row(row) for row in rows]
        except sqlite3.Error as exc:
            logger.error("Database error searching applications for %r: %s", keyword, exc)
            raise DatabaseError(str(exc)) from exc

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

        Every argument is optional and independent: only the filters that
        are given (not `None`) are applied, combined with `AND`, so
        callers can mix and match freely (e.g. status + date range, or
        job_type alone). `status`/`job_type`/`work_mode`/`priority` are
        matched exactly (they're constrained enum columns); `company` and
        `location` are case-insensitive substring matches; the date range
        is inclusive on both ends.

        Only a fixed, hardcoded set of column clauses is ever assembled
        here - every value is still passed as a bound parameter - so this
        stays just as injection-safe as the fully static queries above.

        Args:
            status: Exact `status` value to match.
            job_type: Exact `job_type` value to match.
            work_mode: Exact `work_mode` value to match.
            priority: Exact `priority` value to match.
            company: Substring to match against `company`.
            location: Substring to match against `location`.
            date_from: Inclusive lower bound on `application_date`.
            date_to: Inclusive upper bound on `application_date`.

        Returns:
            A list of matching `JobApplication` records (empty list if
            none match, or if no filters were given, all records).

        Raises:
            DatabaseError: If the query fails.
        """
        clauses: list[str] = []
        params: dict[str, str] = {}

        if status is not None:
            clauses.append("status = :status")
            params["status"] = status
        if job_type is not None:
            clauses.append("job_type = :job_type")
            params["job_type"] = job_type
        if work_mode is not None:
            clauses.append("work_mode = :work_mode")
            params["work_mode"] = work_mode
        if priority is not None:
            clauses.append("priority = :priority")
            params["priority"] = priority
        if company:
            clauses.append("company COLLATE NOCASE LIKE :company")
            params["company"] = f"%{company}%"
        if location:
            clauses.append("location COLLATE NOCASE LIKE :location")
            params["location"] = f"%{location}%"
        if date_from is not None:
            clauses.append("application_date >= :date_from")
            params["date_from"] = date_from
        if date_to is not None:
            clauses.append("application_date <= :date_to")
            params["date_to"] = date_to

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM applications {where_sql} ORDER BY application_date DESC, id DESC;"

        try:
            with get_connection() as conn:
                rows = conn.execute(query, params).fetchall()
            return [JobApplication.from_row(row) for row in rows]
        except sqlite3.Error as exc:
            logger.error("Database error filtering applications (%s): %s", params, exc)
            raise DatabaseError(str(exc)) from exc

    # --- Analytics support ---------------------------------------------------

    def count_all(self) -> int:
        """Return the total number of application records.

        Raises:
            DatabaseError: If the query fails.
        """
        query = "SELECT COUNT(*) AS total FROM applications;"
        try:
            with get_connection() as conn:
                row = conn.execute(query).fetchone()
            return int(row["total"])
        except sqlite3.Error as exc:
            logger.error("Database error counting applications: %s", exc)
            raise DatabaseError(str(exc)) from exc

    def count_by_status(self) -> dict[str, int]:
        """Return the number of applications for each status value that has
        at least one record (statuses with zero applications are omitted).

        Raises:
            DatabaseError: If the query fails.
        """
        query = "SELECT status, COUNT(*) AS total FROM applications GROUP BY status;"
        return self._count_by_column(query)

    def count_by_priority(self) -> dict[str, int]:
        """Return the number of applications for each priority value that
        has at least one record.

        Raises:
            DatabaseError: If the query fails.
        """
        query = "SELECT priority, COUNT(*) AS total FROM applications GROUP BY priority;"
        return self._count_by_column(query)

    def count_by_job_type(self) -> dict[str, int]:
        """Return the number of applications for each job type value that
        has at least one record.

        Raises:
            DatabaseError: If the query fails.
        """
        query = "SELECT job_type, COUNT(*) AS total FROM applications GROUP BY job_type;"
        return self._count_by_column(query)

    def count_by_work_mode(self) -> dict[str, int]:
        """Return the number of applications for each work mode value that
        has at least one record.

        Raises:
            DatabaseError: If the query fails.
        """
        query = "SELECT work_mode, COUNT(*) AS total FROM applications GROUP BY work_mode;"
        return self._count_by_column(query)

    def count_by_company(self, limit: int = 5) -> list[tuple[str, int]]:
        """Return the top `limit` companies by number of applications,
        most applications first.

        Args:
            limit: Maximum number of companies to return.

        Returns:
            A list of `(company, count)` pairs, ordered descending by count.

        Raises:
            DatabaseError: If the query fails.
        """
        query = """
            SELECT company, COUNT(*) AS total FROM applications
            GROUP BY company
            ORDER BY total DESC, company ASC
            LIMIT :limit;
        """
        try:
            with get_connection() as conn:
                rows = conn.execute(query, {"limit": limit}).fetchall()
            return [(row["company"], int(row["total"])) for row in rows]
        except sqlite3.Error as exc:
            logger.error("Database error computing top companies: %s", exc)
            raise DatabaseError(str(exc)) from exc

    def get_recent(self, limit: int = 5) -> list[JobApplication]:
        """Fetch the most recently *created* applications (i.e. most
        recently added to the tracker, not most recently applied to).

        Args:
            limit: Maximum number of records to return.

        Returns:
            A list of `JobApplication` records, most recently created first.

        Raises:
            DatabaseError: If the query fails.
        """
        query = "SELECT * FROM applications ORDER BY created_at DESC, id DESC LIMIT :limit;"
        try:
            with get_connection() as conn:
                rows = conn.execute(query, {"limit": limit}).fetchall()
            return [JobApplication.from_row(row) for row in rows]
        except sqlite3.Error as exc:
            logger.error("Database error fetching recent applications: %s", exc)
            raise DatabaseError(str(exc)) from exc

    def _count_by_column(self, query: str) -> dict[str, int]:
        """Run a fixed `GROUP BY` count query (no user input involved) and
        return it as a `{value: count}` dict."""
        try:
            with get_connection() as conn:
                rows = conn.execute(query).fetchall()
            return {row[0]: int(row["total"]) for row in rows}
        except sqlite3.Error as exc:
            logger.error("Database error computing grouped counts: %s", exc)
            raise DatabaseError(str(exc)) from exc

    def get_with_follow_up(self) -> list[JobApplication]:
        """Fetch every application that has a `follow_up_date` set, soonest
        first.

        Returns:
            A list of `JobApplication` records with a non-null
            `follow_up_date`, ordered ascending by that date.

        Raises:
            DatabaseError: If the query fails.
        """
        query = """
            SELECT * FROM applications
            WHERE follow_up_date IS NOT NULL AND TRIM(follow_up_date) != ''
            ORDER BY follow_up_date ASC, id ASC;
        """
        try:
            with get_connection() as conn:
                rows = conn.execute(query).fetchall()
            return [JobApplication.from_row(row) for row in rows]
        except sqlite3.Error as exc:
            logger.error("Database error fetching follow-ups: %s", exc)
            raise DatabaseError(str(exc)) from exc

    # --- Update ------------------------------------------------------------

    def update(self, application: JobApplication) -> None:
        """Update an existing application record in place.

        `updated_at` is always refreshed to the current time; all other
        fields are overwritten with the values on `application`.

        Args:
            application: A `JobApplication` with a valid, existing `id`.

        Raises:
            ValueError: If `application.id` is `None`.
            RecordNotFoundError: If no record with that id exists.
            IntegrityConstraintError: If the update violates a table
                constraint.
            DatabaseError: For any other database failure.
        """
        if application.id is None:
            raise ValueError("Cannot update an application without an id.")

        data = application.to_dict()
        query = """
            UPDATE applications SET
                company = :company,
                job_title = :job_title,
                location = :location,
                job_type = :job_type,
                work_mode = :work_mode,
                application_date = :application_date,
                status = :status,
                salary = :salary,
                job_url = :job_url,
                recruiter = :recruiter,
                notes = :notes,
                priority = :priority,
                follow_up_date = :follow_up_date,
                tags = :tags,
                interview_rounds = :interview_rounds,
                updated_at = datetime('now')
            WHERE id = :id;
        """
        try:
            with get_connection() as conn:
                cursor = conn.execute(query, data)
                if cursor.rowcount == 0:
                    raise RecordNotFoundError(f"No application found with id={application.id}")
            logger.info("Updated application id=%s", application.id)
        except sqlite3.IntegrityError as exc:
            logger.warning("Integrity error updating application id=%s: %s", application.id, exc)
            raise IntegrityConstraintError(str(exc)) from exc
        except sqlite3.Error as exc:
            logger.error("Database error updating application id=%s: %s", application.id, exc)
            raise DatabaseError(str(exc)) from exc

    # --- Delete ------------------------------------------------------------

    def delete(self, application_id: int) -> None:
        """Delete an application record by id.

        Args:
            application_id: The `id` of the record to delete.

        Raises:
            RecordNotFoundError: If no record with that id exists.
            DatabaseError: For any other database failure.
        """
        query = "DELETE FROM applications WHERE id = ?;"
        try:
            with get_connection() as conn:
                cursor = conn.execute(query, (application_id,))
                if cursor.rowcount == 0:
                    raise RecordNotFoundError(f"No application found with id={application_id}")
            logger.info("Deleted application id=%s", application_id)
        except sqlite3.Error as exc:
            logger.error("Database error deleting application id=%s: %s", application_id, exc)
            raise DatabaseError(str(exc)) from exc
