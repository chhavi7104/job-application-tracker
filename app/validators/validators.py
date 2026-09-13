"""
validators.py

Standalone validation functions used by the services layer to check and
sanitize user input before it is turned into a `JobApplication` or passed
to the repository. Each validator raises `ValidationError` with a clear,
user-facing message on invalid input rather than returning a boolean, so
callers can catch one exception type and display it directly.

This module has no knowledge of the CLI or the database - it only knows
how to validate plain Python values (mostly strings). Generic helpers
(validate_required_text, validate_optional_text, validate_date,
validate_enum, ...) are backed by named, field-specific wrappers
(validate_status, validate_job_type, validate_salary, validate_email,
validate_date_range, ...) so both the service layer and any future
caller can validate a specific field without needing to know which
generic helper backs it.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import Enum
from typing import Optional, Type, TypeVar

from app.models.application import JobType, Priority, Status, WorkMode

E = TypeVar("E", bound=Enum)


class ValidationError(Exception):
    """Raised when user-supplied input fails validation."""


# --- Text fields -----------------------------------------------------------

def validate_required_text(value: Optional[str], field_name: str, max_length: int = 200) -> str:
    """Validate a required, free-text field.

    Args:
        value: The raw input.
        field_name: Human-readable field name, used in error messages.
        max_length: Maximum allowed length after stripping whitespace.

    Returns:
        The trimmed, validated string.

    Raises:
        ValidationError: If the value is missing, blank, or too long.
    """
    if value is None or not value.strip():
        raise ValidationError(f"{field_name} is required and cannot be empty.")
    cleaned = value.strip()
    if len(cleaned) > max_length:
        raise ValidationError(f"{field_name} must be {max_length} characters or fewer.")
    return cleaned


def validate_optional_text(value: Optional[str], field_name: str, max_length: int = 1000) -> Optional[str]:
    """Validate an optional, free-text field.

    An empty/whitespace-only value is treated as "no value" and returned
    as `None` (this is how a user clears an optional field on update).

    Args:
        value: The raw input.
        field_name: Human-readable field name, used in error messages.
        max_length: Maximum allowed length after stripping whitespace.

    Returns:
        The trimmed string, or `None` if the value was empty.

    Raises:
        ValidationError: If the value is too long.
    """
    if value is None or not value.strip():
        return None
    cleaned = value.strip()
    if len(cleaned) > max_length:
        raise ValidationError(f"{field_name} must be {max_length} characters or fewer.")
    return cleaned


# --- Dates -------------------------------------------------------------------

DATE_FORMAT = "%Y-%m-%d"


def validate_date(value: Optional[str], field_name: str) -> str:
    """Validate a required date string in `YYYY-MM-DD` format.

    Args:
        value: The raw input.
        field_name: Human-readable field name, used in error messages.

    Returns:
        The validated date string, unchanged.

    Raises:
        ValidationError: If the value is missing or not a real calendar
            date in `YYYY-MM-DD` format.
    """
    text = validate_required_text(value, field_name, max_length=10)
    try:
        datetime.strptime(text, DATE_FORMAT)
    except ValueError as exc:
        raise ValidationError(f"{field_name} must be a valid date in YYYY-MM-DD format.") from exc
    return text


def validate_optional_date(value: Optional[str], field_name: str) -> Optional[str]:
    """Validate an optional date string in `YYYY-MM-DD` format.

    Args:
        value: The raw input.
        field_name: Human-readable field name, used in error messages.

    Returns:
        The validated date string, or `None` if no value was given.

    Raises:
        ValidationError: If a value was given but isn't a real calendar
            date in `YYYY-MM-DD` format.
    """
    if value is None or not value.strip():
        return None
    return validate_date(value, field_name)


def today_str() -> str:
    """Return today's date as a `YYYY-MM-DD` string (convenience helper
    for defaulting `application_date`)."""
    return date.today().strftime(DATE_FORMAT)


# --- Enums ---------------------------------------------------------------

def validate_enum(value: Optional[str], field_name: str, enum_cls: Type[E]) -> E:
    """Validate that `value` matches one of `enum_cls`'s allowed values.

    Matching is case-insensitive on the enum's string value (e.g. "remote"
    matches `WorkMode.REMOTE`).

    Args:
        value: The raw input.
        field_name: Human-readable field name, used in error messages.
        enum_cls: The `Enum` subclass to validate against.

    Returns:
        The matching enum member.

    Raises:
        ValidationError: If the value is missing or doesn't match any
            allowed value.
    """
    text = validate_required_text(value, field_name, max_length=50)
    for member in enum_cls:
        if member.value.lower() == text.lower():
            return member
    allowed = ", ".join(m.value for m in enum_cls)
    raise ValidationError(f"{field_name} must be one of: {allowed}.")


# --- Misc --------------------------------------------------------------------

def validate_salary(value: Optional[str], field_name: str = "Salary") -> Optional[str]:
    """Validate an optional salary/compensation field.

    Accepts a plain non-negative number, with or without a decimal
    component and optional thousands separators (commas). This keeps the
    stored value unambiguous and sortable/comparable in the future, while
    still being easy to type (e.g. "60000", "60,000", "60000.50").

    Args:
        value: The raw input.
        field_name: Human-readable field name, used in error messages.

    Returns:
        A normalized numeric string (commas stripped), or `None` if no
        value was given.

    Raises:
        ValidationError: If a value was given but isn't a valid
            non-negative number.
    """
    if value is None or not str(value).strip():
        return None
    cleaned = str(value).strip().replace(",", "")
    try:
        amount = float(cleaned)
    except ValueError as exc:
        raise ValidationError(
            f"{field_name} must be a valid non-negative number (e.g. 60000 or 60000.50)."
        ) from exc
    if amount < 0:
        raise ValidationError(f"{field_name} cannot be negative.")
    # Render whole numbers without a trailing ".0" but keep real decimals.
    return str(int(amount)) if amount == int(amount) else f"{amount:.2f}"


_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def validate_email(value: Optional[str], field_name: str = "Email", required: bool = False) -> Optional[str]:
    """Validate an optional email address field.

    Not currently wired to any `JobApplication` field (the schema only has
    a free-text `recruiter` name, not a dedicated email column), but
    provided centrally so a recruiter-email field can validate through it
    if one is added later.

    Args:
        value: The raw input.
        field_name: Human-readable field name, used in error messages.
        required: If `True`, a missing value raises instead of returning
            `None`.

    Returns:
        The trimmed, lowercased email address, or `None` if no value was
        given and `required` is `False`.

    Raises:
        ValidationError: If the value is required but missing, or doesn't
            look like a valid email address.
    """
    if value is None or not str(value).strip():
        if required:
            raise ValidationError(f"{field_name} is required and cannot be empty.")
        return None
    cleaned = str(value).strip()
    if not _EMAIL_PATTERN.match(cleaned):
        raise ValidationError(f"{field_name} must be a valid email address (e.g. name@example.com).")
    return cleaned.lower()


def validate_url(value: Optional[str], field_name: str = "Job URL") -> Optional[str]:
    """Validate an optional URL field.

    Only performs a lightweight sanity check (must start with http:// or
    https://) rather than full URL parsing, since job posting links can
    have all kinds of query-string shapes.

    Args:
        value: The raw input.
        field_name: Human-readable field name, used in error messages.

    Returns:
        The trimmed URL, or `None` if no value was given.

    Raises:
        ValidationError: If a value was given but doesn't look like a URL.
    """
    cleaned = validate_optional_text(value, field_name, max_length=500)
    if cleaned is None:
        return None
    if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
        raise ValidationError(f"{field_name} must start with http:// or https://.")
    return cleaned


def validate_id(value: object, field_name: str = "ID") -> int:
    """Validate that `value` is a positive integer ID.

    Accepts an `int` or a numeric `str` (as CLI input often arrives as a
    string before this validator normalizes it).

    Args:
        value: The raw input.
        field_name: Human-readable field name, used in error messages.

    Returns:
        The validated ID as an `int`.

    Raises:
        ValidationError: If the value isn't a positive integer.
    """
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be a whole number.") from exc
    if parsed <= 0:
        raise ValidationError(f"{field_name} must be a positive number.")
    return parsed


def validate_date_range(
    date_from: Optional[str], date_to: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """Validate an optional `(date_from, date_to)` filter range.

    Each bound is validated individually via `validate_optional_date`, and
    if both are given, `date_from` must not be after `date_to`.

    Args:
        date_from: Start of the range (inclusive), or `None`/empty.
        date_to: End of the range (inclusive), or `None`/empty.

    Returns:
        The validated `(date_from, date_to)` tuple.

    Raises:
        ValidationError: If either bound is malformed, or `date_from` is
            after `date_to`.
    """
    start = validate_optional_date(date_from, "Applied-from date")
    end = validate_optional_date(date_to, "Applied-to date")
    if start is not None and end is not None and start > end:
        raise ValidationError("The 'applied from' date must not be after the 'applied to' date.")
    return start, end


# --- Named field wrappers ---------------------------------------------------
#
# Thin, discoverable wrappers around validate_enum/validate_date/validate_url
# for the specific fields that need them, so calling code can validate e.g.
# a status value without having to know which generic helper backs it.

def validate_status(value: Optional[str]) -> Status:
    """Validate a `status` value against the allowed `Status` values."""
    return validate_enum(value, "Status", Status)


def validate_job_type(value: Optional[str]) -> JobType:
    """Validate a `job_type` value against the allowed `JobType` values."""
    return validate_enum(value, "Job type", JobType)


def validate_work_mode(value: Optional[str]) -> WorkMode:
    """Validate a `work_mode` value against the allowed `WorkMode` values."""
    return validate_enum(value, "Work mode", WorkMode)


def validate_priority(value: Optional[str]) -> Priority:
    """Validate a `priority` value against the allowed `Priority` values."""
    return validate_enum(value, "Priority", Priority)


def validate_application_date(value: Optional[str]) -> str:
    """Validate a required `application_date` value."""
    return validate_date(value, "Application date")


def validate_follow_up_date(value: Optional[str]) -> Optional[str]:
    """Validate an optional `follow_up_date` value."""
    return validate_optional_date(value, "Follow-up date")


def validate_job_url(value: Optional[str]) -> Optional[str]:
    """Validate an optional `job_url` value."""
    return validate_url(value, "Job URL")


# --- Tags & interview tracking (Phase 6) ------------------------------------

MAX_TAGS = 10
MAX_TAG_LENGTH = 30


def validate_tags(value: Optional[str], field_name: str = "Tags") -> Optional[list[str]]:
    """Validate and normalize a comma-separated tags string into a clean
    list of tags.

    Each tag is trimmed and lowercased; empty entries (e.g. from a
    trailing comma) are dropped; duplicates are removed while preserving
    first-seen order.

    Args:
        value: Raw comma-separated input, e.g. "Referral, Dream Job, referral".
        field_name: Human-readable field name, used in error messages.

    Returns:
        A deduplicated list of lowercase tags (e.g. ["referral", "dream job"]),
        or `None` if no value was given.

    Raises:
        ValidationError: If any single tag exceeds `MAX_TAG_LENGTH`
            characters, or more than `MAX_TAGS` distinct tags are given.
    """
    if value is None or not str(value).strip():
        return None

    seen: set[str] = set()
    cleaned: list[str] = []
    for raw_tag in str(value).split(","):
        tag = raw_tag.strip().lower()
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            raise ValidationError(
                f"{field_name}: each tag must be {MAX_TAG_LENGTH} characters or fewer (got '{tag}')."
            )
        if tag not in seen:
            seen.add(tag)
            cleaned.append(tag)

    if len(cleaned) > MAX_TAGS:
        raise ValidationError(f"{field_name}: you can add at most {MAX_TAGS} tags.")

    return cleaned or None


def validate_interview_rounds(value: object, field_name: str = "Interview rounds") -> int:
    """Validate a count of interview rounds completed so far.

    An empty value defaults to 0 (no interviews yet) rather than raising,
    since this field is optional on both add and update.

    Args:
        value: Raw input (int, numeric string, or empty).
        field_name: Human-readable field name, used in error messages.

    Returns:
        The validated round count as a non-negative `int`.

    Raises:
        ValidationError: If the value isn't a whole number, is negative,
            or is unrealistically large (> 20).
    """
    if value is None or str(value).strip() == "":
        return 0
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be a whole number.") from exc
    if parsed < 0:
        raise ValidationError(f"{field_name} cannot be negative.")
    if parsed > 20:
        raise ValidationError(f"{field_name} must be 20 or fewer.")
    return parsed
