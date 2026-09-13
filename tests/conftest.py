"""
conftest.py

Shared pytest fixtures for the test suite.

The most important fixture here is `temp_db`: it redirects the database
layer's module-level `DATA_DIR`/`DB_PATH` to a pytest-managed temporary
directory for the duration of a single test, then pytest deletes that
directory automatically afterwards. Every other fixture in this file
builds on top of it, so no test in this suite - CRUD, search, filters,
validation, or error handling - ever reads or writes the real
`data/job_applications.db` used by the actual application.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from app.database import connection
from app.database.repository import ApplicationRepository
from app.models.application import JobApplication, JobType, Priority, Status, WorkMode
from app.services.analytics_service import AnalyticsService
from app.services.application_service import ApplicationService


@pytest.fixture
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the database layer at a throwaway SQLite file for one test.

    Monkeypatch automatically restores `connection.DATA_DIR`/`DB_PATH` to
    their real values when the test ends, and `tmp_path` is a fresh,
    pytest-managed directory unique to this test - so there is no way for
    a test to accidentally read or write the developer's real database.
    """
    db_path = tmp_path / "test_applications.db"
    monkeypatch.setattr(connection, "DATA_DIR", tmp_path)
    monkeypatch.setattr(connection, "DB_PATH", db_path)
    connection.initialize_database()
    yield db_path


@pytest.fixture
def repository(temp_db: Path) -> ApplicationRepository:
    """A repository backed by the isolated temporary database."""
    return ApplicationRepository()


@pytest.fixture
def app_service(repository: ApplicationRepository) -> ApplicationService:
    """An `ApplicationService` backed by the isolated temporary database."""
    return ApplicationService(repository=repository)


@pytest.fixture
def analytics_service(repository: ApplicationRepository) -> AnalyticsService:
    """An `AnalyticsService` backed by the isolated temporary database."""
    return AnalyticsService(repository=repository)


@pytest.fixture
def sample_application_kwargs() -> dict:
    """A complete, valid set of kwargs for `ApplicationService.add_application`."""
    return {
        "company": "TechNova Inc",
        "job_title": "Backend Engineer",
        "application_date": "2026-08-01",
        "job_type": JobType.FULL_TIME.value,
        "work_mode": WorkMode.REMOTE.value,
        "status": Status.APPLIED.value,
        "priority": Priority.HIGH.value,
        "location": "Bengaluru",
        "salary": "200000",
        "job_url": "https://technova.example/careers/42",
        "recruiter": "Priya Sharma",
        "notes": "Referred by a friend",
        "follow_up_date": "2026-09-01",
        "tags": "referral, dream-job",
        "interview_rounds": 1,
    }


@pytest.fixture
def sample_application(sample_application_kwargs: dict) -> JobApplication:
    """A `JobApplication` model instance built directly (not persisted),
    useful for repository-level tests that don't need service validation."""
    return JobApplication(
        company=sample_application_kwargs["company"],
        job_title=sample_application_kwargs["job_title"],
        application_date=sample_application_kwargs["application_date"],
        job_type=JobType(sample_application_kwargs["job_type"]),
        work_mode=WorkMode(sample_application_kwargs["work_mode"]),
        status=Status(sample_application_kwargs["status"]),
        priority=Priority(sample_application_kwargs["priority"]),
        location=sample_application_kwargs["location"],
        salary=sample_application_kwargs["salary"],
        job_url=sample_application_kwargs["job_url"],
        recruiter=sample_application_kwargs["recruiter"],
        notes=sample_application_kwargs["notes"],
        follow_up_date=sample_application_kwargs["follow_up_date"],
    )
