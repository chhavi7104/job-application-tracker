"""
exceptions.py

Service-layer exception types. The CLI catches these (plus
`app.validators.validators.ValidationError`) and never needs to know
about `app.database.exceptions` or `sqlite3` directly - the service layer
translates lower-level database errors into these before they surface.
"""


class ServiceError(Exception):
    """Base exception for all service-layer failures."""


class ApplicationNotFoundError(ServiceError):
    """Raised when an operation targets an application id that doesn't exist."""


class DuplicateApplicationError(ServiceError):
    """Raised when creating/updating an application would duplicate an
    existing one (same company, job title, and application date)."""
