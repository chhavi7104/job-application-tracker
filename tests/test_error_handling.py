"""
test_error_handling.py

Tests focused specifically on error handling across layers:
    - Non-existent records (repository returns None / raises
      RecordNotFoundError; service raises ApplicationNotFoundError).
    - Simulated database errors (a failing `sqlite3.connect` is wrapped
      into the application's own `DatabaseError`/`ConnectionError`
      hierarchy, never a raw `sqlite3.Error` escaping to a caller).
    - Invalid user input (non-numeric IDs, garbage enum values) raising
      the same `ValidationError` type regardless of which layer first
      encounters it.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.database import connection
from app.database.exceptions import ConnectionError as DBConnectionError
from app.database.exceptions import DatabaseError
from app.database.repository import ApplicationRepository
from app.services.exceptions import ApplicationNotFoundError, ServiceError
from app.validators.validators import ValidationError


class TestNonExistentApplication:
    def test_repository_get_by_id_returns_none(self, repository) -> None:
        assert repository.get_by_id(12345) is None

    def test_repository_delete_raises_record_not_found(self, repository) -> None:
        from app.database.exceptions import RecordNotFoundError

        with pytest.raises(RecordNotFoundError):
            repository.delete(12345)

    def test_service_get_raises_application_not_found(self, app_service) -> None:
        with pytest.raises(ApplicationNotFoundError, match="No application found with ID 12345"):
            app_service.get_application(12345)

    def test_service_update_raises_application_not_found(self, app_service) -> None:
        with pytest.raises(ApplicationNotFoundError):
            app_service.update_application(12345, status="Interview")

    def test_service_delete_raises_application_not_found(self, app_service) -> None:
        with pytest.raises(ApplicationNotFoundError):
            app_service.delete_application(12345)


class TestInvalidUserInput:
    def test_non_numeric_id_raises_validation_error(self, app_service) -> None:
        with pytest.raises(ValidationError, match="whole number"):
            app_service.get_application("banana")

    def test_negative_id_raises_validation_error(self, app_service) -> None:
        with pytest.raises(ValidationError, match="positive"):
            app_service.get_application(-1)

    def test_garbage_status_raises_validation_error_not_crash(
        self, app_service, sample_application_kwargs
    ) -> None:
        sample_application_kwargs["status"] = "totally-not-a-status"
        with pytest.raises(ValidationError):
            app_service.add_application(**sample_application_kwargs)

    def test_garbage_enum_values_never_reach_the_database(
        self, app_service, repository, sample_application_kwargs
    ) -> None:
        sample_application_kwargs["work_mode"] = "Underwater"
        with pytest.raises(ValidationError):
            app_service.add_application(**sample_application_kwargs)
        # Confirm nothing was partially written.
        assert repository.get_all() == []


class TestDatabaseErrorHandling:
    def test_connection_failure_wrapped_as_connection_error(self, temp_db, monkeypatch) -> None:
        def _boom(*_args, **_kwargs):
            raise sqlite3.OperationalError("unable to open database file")

        monkeypatch.setattr(sqlite3, "connect", _boom)

        with pytest.raises(DBConnectionError):
            with connection.get_connection():
                pass  # pragma: no cover - never reached

    def test_repository_wraps_sqlite_error_as_database_error(self, repository, monkeypatch) -> None:
        def _boom(*_args, **_kwargs):
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(sqlite3, "connect", _boom)

        with pytest.raises(DatabaseError):
            repository.get_all()

    def test_service_wraps_database_error_as_service_error(self, app_service, monkeypatch) -> None:
        def _boom(*_args, **_kwargs):
            raise sqlite3.OperationalError("disk I/O error")

        monkeypatch.setattr(sqlite3, "connect", _boom)

        with pytest.raises(ServiceError):
            app_service.list_applications()

    def test_no_raw_sqlite_error_ever_escapes_the_repository(self, repository, monkeypatch) -> None:
        """Whatever goes wrong inside SQLite, callers should only ever see
        our own exception types - never a bare `sqlite3.Error`."""

        def _boom(*_args, **_kwargs):
            raise sqlite3.OperationalError("simulated failure")

        monkeypatch.setattr(sqlite3, "connect", _boom)

        for operation in (
            lambda: repository.get_all(),
            lambda: repository.count_all(),
            lambda: repository.search("x"),
        ):
            with pytest.raises(DatabaseError):
                try:
                    operation()
                except sqlite3.Error:
                    pytest.fail("A raw sqlite3.Error escaped the repository layer.")


class TestDatabaseInitializationIsolation:
    def test_initialize_database_is_idempotent(self, temp_db) -> None:
        """Calling initialize_database() again must not fail or duplicate
        the schema (it's called on every app startup)."""
        connection.initialize_database()
        connection.initialize_database()
        # A working repository call proves the schema is still intact.
        repo = ApplicationRepository()
        assert repo.get_all() == []

    def test_migration_adds_missing_columns_without_data_loss(self, tmp_path, monkeypatch) -> None:
        """Simulate a pre-Phase-6 database (no tags/interview_rounds
        columns) and confirm initialize_database() migrates it in place
        without losing the existing row."""
        db_path = tmp_path / "legacy.db"
        raw_conn = sqlite3.connect(db_path)
        raw_conn.execute(
            """
            CREATE TABLE applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                job_title TEXT NOT NULL,
                location TEXT,
                job_type TEXT NOT NULL DEFAULT 'Full-time',
                work_mode TEXT NOT NULL DEFAULT 'On-site',
                application_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Applied',
                salary TEXT, job_url TEXT, recruiter TEXT, notes TEXT,
                priority TEXT NOT NULL DEFAULT 'Medium',
                follow_up_date TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        raw_conn.execute(
            "INSERT INTO applications (company, job_title, application_date, salary) "
            "VALUES ('LegacyCo', 'Old Role', '2026-01-01', '20 LPA')"
        )
        raw_conn.commit()
        raw_conn.close()

        monkeypatch.setattr(connection, "DATA_DIR", tmp_path)
        monkeypatch.setattr(connection, "DB_PATH", db_path)
        connection.initialize_database()

        repo = ApplicationRepository()
        records = repo.get_all()
        assert len(records) == 1
        assert records[0].company == "LegacyCo"
        assert records[0].salary == "20 LPA"
        assert records[0].tags is None
        assert records[0].interview_rounds == 0
