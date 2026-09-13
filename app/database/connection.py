"""
connection.py

Manages the SQLite database connection lifecycle for the application:

    - Resolves the database file location (data/job_applications.db).
    - Provides `get_connection()`, a context manager that yields a
      configured `sqlite3.Connection` and guarantees commit/rollback and
      closing behave correctly.
    - Provides `initialize_database()`, which creates the `applications`
      table (and its indexes) if they do not already exist, so the schema
      is safe to "initialize" on every application startup.

No business logic lives here - this module is purely about getting a
working, correctly configured connection to the SQLite file and ensuring
the schema exists. Query logic belongs in `app.database.repository`.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.database.exceptions import ConnectionError as DBConnectionError
from app.database.exceptions import DatabaseError
from app.utils.logger import get_logger

logger = get_logger(__name__)

# --- Database location -------------------------------------------------

# Project root is three levels up from this file: app/database/connection.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "job_applications.db"


# --- Schema --------------------------------------------------------------

# Allowed values are enforced both here (via CHECK constraints) and in the
# Python-level enums in app.models.application, so invalid data can never
# reach the database even if it bypasses the model/service layer.
_CREATE_APPLICATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS applications (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    company           TEXT NOT NULL CHECK (TRIM(company) != ''),
    job_title         TEXT NOT NULL CHECK (TRIM(job_title) != ''),
    location          TEXT,
    job_type          TEXT NOT NULL DEFAULT 'Full-time'
                          CHECK (job_type IN ('Full-time', 'Internship', 'Part-time', 'Contract')),
    work_mode         TEXT NOT NULL DEFAULT 'On-site'
                          CHECK (work_mode IN ('Remote', 'Hybrid', 'On-site')),
    application_date  TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'Applied'
                          CHECK (status IN ('Saved', 'Applied', 'Assessment', 'Interview',
                                             'Offer', 'Rejected', 'Withdrawn', 'Accepted')),
    salary            TEXT,
    job_url           TEXT,
    recruiter         TEXT,
    notes             TEXT,
    priority          TEXT NOT NULL DEFAULT 'Medium'
                          CHECK (priority IN ('Low', 'Medium', 'High')),
    follow_up_date    TEXT,
    tags              TEXT,
    interview_rounds  INTEGER NOT NULL DEFAULT 0 CHECK (interview_rounds >= 0),
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Columns added after the initial release. Applied via `_apply_migrations`
# with an `ALTER TABLE ... ADD COLUMN` for any database file created by an
# earlier phase that doesn't have them yet - new databases already get
# them from `_CREATE_APPLICATIONS_TABLE` above, so this is a no-op there.
_SCHEMA_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("tags", "ALTER TABLE applications ADD COLUMN tags TEXT;"),
    ("interview_rounds", "ALTER TABLE applications ADD COLUMN interview_rounds INTEGER NOT NULL DEFAULT 0;"),
)

# Indexes on columns that are commonly filtered/searched on (status,
# company, application_date) to keep future search/analytics queries fast.
_CREATE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);",
    "CREATE INDEX IF NOT EXISTS idx_applications_company ON applications(company);",
    "CREATE INDEX IF NOT EXISTS idx_applications_application_date ON applications(application_date);",
)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Yield a configured SQLite connection as a context manager.

    Configures the connection so that:
        - Rows are returned as `sqlite3.Row` (dict-like, column-name access).
        - Foreign key enforcement is turned on (for future related tables).
        - Changes are committed automatically on successful exit, and
          rolled back automatically if an exception occurs.
        - The connection is always closed, even on error.

    Yields:
        A ready-to-use `sqlite3.Connection`.

    Raises:
        app.database.exceptions.ConnectionError: If the connection to the
            SQLite file cannot be established.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        conn = sqlite3.connect(DB_PATH)
    except sqlite3.Error as exc:
        logger.error("Failed to connect to database at %s: %s", DB_PATH, exc)
        raise DBConnectionError(f"Could not connect to database at {DB_PATH}") from exc

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        yield conn
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database() -> None:
    """Create the `applications` table and its indexes if they do not
    already exist, then apply any pending column migrations.

    Safe to call on every application startup: existing data is left
    untouched because all DDL statements use `IF NOT EXISTS` (or check for
    the column's existence first, for migrations).

    Raises:
        app.database.exceptions.ConnectionError: If the database file
            cannot be opened.
        app.database.exceptions.DatabaseError: If schema creation fails
            for any other reason.
    """
    logger.info("Initializing database at %s", DB_PATH)

    with get_connection() as conn:
        try:
            conn.execute(_CREATE_APPLICATIONS_TABLE)
            for statement in _CREATE_INDEXES:
                conn.execute(statement)
            _apply_migrations(conn)
        except sqlite3.Error as exc:
            logger.error("Failed to initialize database schema: %s", exc)
            raise DatabaseError("Failed to initialize database schema") from exc

    logger.info("Database ready at %s", DB_PATH)


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Add any columns from `_SCHEMA_MIGRATIONS` that are missing from an
    existing `applications` table (e.g. a database file created by an
    earlier phase, before `tags`/`interview_rounds` existed).

    Uses `PRAGMA table_info` to check what already exists, so this is safe
    to run on every startup - already-migrated databases are untouched.
    """
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(applications);").fetchall()}
    for column_name, alter_statement in _SCHEMA_MIGRATIONS:
        if column_name not in existing_columns:
            conn.execute(alter_statement)
            logger.info("Migrated schema: added '%s' column to applications.", column_name)
