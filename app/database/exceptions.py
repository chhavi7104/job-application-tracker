"""
exceptions.py

Custom exception types for the database layer. Repository and connection
code catches low-level `sqlite3.Error` subclasses and re-raises them as
one of these, so that callers outside app.database never need to know
SQLite is involved - they only need to catch `DatabaseError`.
"""


class DatabaseError(Exception):
    """Base exception for all database-layer failures."""


class ConnectionError(DatabaseError):
    """Raised when a database connection cannot be established."""


class RecordNotFoundError(DatabaseError):
    """Raised when an operation targets a record that does not exist."""


class IntegrityConstraintError(DatabaseError):
    """Raised when an operation violates a table constraint (e.g. CHECK, NOT NULL)."""
