"""
application.py

Defines the `JobApplication` domain model - a plain data class
representing a single job application record - along with the enums that
constrain its `job_type`, `work_mode`, `status`, and `priority` fields.

This module has no database or business logic: it only describes the
shape of a job application and provides small conversion helpers
(`to_dict` / `from_row`) used by the repository layer to move data
between SQLite rows and Python objects.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class JobType(str, Enum):
    """Allowed values for `JobApplication.job_type`."""

    FULL_TIME = "Full-time"
    INTERNSHIP = "Internship"
    PART_TIME = "Part-time"
    CONTRACT = "Contract"


class WorkMode(str, Enum):
    """Allowed values for `JobApplication.work_mode`."""

    REMOTE = "Remote"
    HYBRID = "Hybrid"
    ON_SITE = "On-site"


class Status(str, Enum):
    """Allowed values for `JobApplication.status`, representing the
    application's stage in the hiring pipeline."""

    SAVED = "Saved"
    APPLIED = "Applied"
    ASSESSMENT = "Assessment"
    INTERVIEW = "Interview"
    OFFER = "Offer"
    REJECTED = "Rejected"
    WITHDRAWN = "Withdrawn"
    ACCEPTED = "Accepted"


class Priority(str, Enum):
    """Allowed values for `JobApplication.priority`."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


@dataclass
class JobApplication:
    """A single job application record.

    Attributes:
        id: Primary key. `None` for a record that has not yet been
            persisted to the database.
        company: Name of the hiring company. Required.
        job_title: Title of the role applied for. Required.
        location: Free-text location (e.g. "Bengaluru, India"). Optional.
        job_type: One of `JobType` (e.g. Full-time, Internship).
        work_mode: One of `WorkMode` (e.g. Remote, Hybrid, On-site).
        application_date: ISO date (YYYY-MM-DD) the application was submitted.
        status: One of `Status`, defaulting to `Status.APPLIED`.
        salary: Free-text salary/compensation info (e.g. "12 LPA"). Optional.
        job_url: Link to the job posting. Optional.
        recruiter: Name/contact of the recruiter or hiring manager. Optional.
        notes: Free-text notes. Optional.
        priority: One of `Priority`, defaulting to `Priority.MEDIUM`.
        follow_up_date: ISO date (YYYY-MM-DD) to follow up by. Optional.
        tags: A short list of free-text labels (e.g. ["referral", "dream-job"]),
            stored in SQLite as a comma-separated string. Optional.
        interview_rounds: Number of interview rounds completed so far.
            Defaults to 0 (no interviews yet).
        created_at: Timestamp set by the database on insert (read-only).
        updated_at: Timestamp set by the database on insert/update (read-only).
    """

    company: str
    job_title: str
    application_date: str
    job_type: JobType = JobType.FULL_TIME
    work_mode: WorkMode = WorkMode.ON_SITE
    status: Status = Status.APPLIED
    priority: Priority = Priority.MEDIUM
    location: Optional[str] = None
    salary: Optional[str] = None
    job_url: Optional[str] = None
    recruiter: Optional[str] = None
    notes: Optional[str] = None
    follow_up_date: Optional[str] = None
    tags: Optional[list[str]] = None
    interview_rounds: int = 0
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert this record into a plain dict suitable for parameterized
        SQL statements (enum fields are converted to their string value;
        `tags` is joined into a comma-separated string).
        """
        return {
            "id": self.id,
            "company": self.company,
            "job_title": self.job_title,
            "location": self.location,
            "job_type": self._enum_value(self.job_type),
            "work_mode": self._enum_value(self.work_mode),
            "application_date": self.application_date,
            "status": self._enum_value(self.status),
            "salary": self.salary,
            "job_url": self.job_url,
            "recruiter": self.recruiter,
            "notes": self.notes,
            "priority": self._enum_value(self.priority),
            "follow_up_date": self.follow_up_date,
            "tags": ",".join(self.tags) if self.tags else None,
            "interview_rounds": self.interview_rounds,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "JobApplication":
        """Build a `JobApplication` from a `sqlite3.Row` returned by the
        repository layer.

        Args:
            row: A row from the `applications` table, accessed by column
                name (requires `conn.row_factory = sqlite3.Row`).

        Returns:
            A populated `JobApplication` instance.
        """
        raw_tags = row["tags"] if "tags" in row.keys() else None
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()] if raw_tags else None
        interview_rounds = row["interview_rounds"] if "interview_rounds" in row.keys() else 0

        return cls(
            id=row["id"],
            company=row["company"],
            job_title=row["job_title"],
            location=row["location"],
            job_type=JobType(row["job_type"]),
            work_mode=WorkMode(row["work_mode"]),
            application_date=row["application_date"],
            status=Status(row["status"]),
            salary=row["salary"],
            job_url=row["job_url"],
            recruiter=row["recruiter"],
            notes=row["notes"],
            priority=Priority(row["priority"]),
            follow_up_date=row["follow_up_date"],
            tags=tags,
            interview_rounds=interview_rounds or 0,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _enum_value(value: Any) -> Optional[str]:
        """Return the plain string value of an Enum member, or pass through
        a plain string (or None) unchanged."""
        return value.value if isinstance(value, Enum) else value
