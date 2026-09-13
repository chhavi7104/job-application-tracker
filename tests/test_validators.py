"""
test_validators.py

Unit tests for `app.validators.validators`. These tests need no database
at all - every validator here is a pure function - so none of them use
the `temp_db` fixture.
"""

from __future__ import annotations

import pytest

from app.validators.validators import (
    ValidationError,
    validate_date_range,
    validate_email,
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


class TestRequiredFields:
    def test_valid_text_is_trimmed(self) -> None:
        assert validate_required_text("  Acme Corp  ", "Company") == "Acme Corp"

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_empty_required_field_raises(self, value) -> None:
        with pytest.raises(ValidationError, match="Company is required"):
            validate_required_text(value, "Company")

    def test_too_long_required_field_raises(self) -> None:
        with pytest.raises(ValidationError, match="200 characters or fewer"):
            validate_required_text("x" * 201, "Company", max_length=200)

    def test_optional_text_blank_becomes_none(self) -> None:
        assert validate_optional_text("", "Location") is None
        assert validate_optional_text("   ", "Location") is None

    def test_optional_text_trims_value(self) -> None:
        assert validate_optional_text("  Remote  ", "Location") == "Remote"


class TestDates:
    def test_valid_application_date(self) -> None:
        from app.validators.validators import validate_application_date

        assert validate_application_date("2026-01-15") == "2026-01-15"

    @pytest.mark.parametrize(
        "bad_date",
        ["not-a-date", "2026-13-01", "2026-02-30", "01-15-2026", "2026/01/15", ""],
    )
    def test_invalid_dates_raise(self, bad_date) -> None:
        from app.validators.validators import validate_application_date

        with pytest.raises(ValidationError):
            validate_application_date(bad_date)

    def test_optional_follow_up_date_blank_is_none(self) -> None:
        from app.validators.validators import validate_follow_up_date

        assert validate_follow_up_date("") is None
        assert validate_follow_up_date(None) is None

    def test_date_range_valid(self) -> None:
        assert validate_date_range("2026-01-01", "2026-02-01") == ("2026-01-01", "2026-02-01")

    def test_date_range_both_blank(self) -> None:
        assert validate_date_range("", "") == (None, None)

    def test_date_range_reversed_raises(self) -> None:
        with pytest.raises(ValidationError, match="must not be after"):
            validate_date_range("2026-03-01", "2026-01-01")

    def test_date_range_malformed_bound_raises(self) -> None:
        with pytest.raises(ValidationError):
            validate_date_range("not-a-date", "")


class TestSalary:
    @pytest.mark.parametrize(
        "raw, expected",
        [("60000", "60000"), ("60,000", "60000"), ("60000.5", "60000.50"), ("0", "0")],
    )
    def test_valid_salary(self, raw, expected) -> None:
        assert validate_salary(raw) == expected

    def test_blank_salary_is_none(self) -> None:
        assert validate_salary("") is None
        assert validate_salary(None) is None

    def test_negative_salary_raises(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            validate_salary("-100")

    @pytest.mark.parametrize("bad_salary", ["20 LPA", "abc", "60k", "$60000"])
    def test_non_numeric_salary_raises(self, bad_salary) -> None:
        with pytest.raises(ValidationError, match="valid non-negative number"):
            validate_salary(bad_salary)


class TestEnumFields:
    def test_valid_status_case_insensitive(self) -> None:
        assert validate_status("applied").value == "Applied"
        assert validate_status("APPLIED").value == "Applied"

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(ValidationError, match="Status must be one of"):
            validate_status("Ghosted")

    def test_valid_job_type(self) -> None:
        assert validate_job_type("Full-time").value == "Full-time"

    def test_invalid_job_type_raises(self) -> None:
        with pytest.raises(ValidationError, match="Job type must be one of"):
            validate_job_type("Freelance")

    def test_valid_work_mode(self) -> None:
        assert validate_work_mode("remote").value == "Remote"

    def test_invalid_work_mode_raises(self) -> None:
        with pytest.raises(ValidationError, match="Work mode must be one of"):
            validate_work_mode("From the beach")

    def test_valid_priority(self) -> None:
        assert validate_priority("high").value == "High"

    def test_invalid_priority_raises(self) -> None:
        with pytest.raises(ValidationError, match="Priority must be one of"):
            validate_priority("Urgent")


class TestUrl:
    def test_valid_urls(self) -> None:
        assert validate_job_url("https://example.com/job/1") == "https://example.com/job/1"
        assert validate_job_url("http://example.com") == "http://example.com"

    def test_blank_url_is_none(self) -> None:
        assert validate_job_url("") is None

    @pytest.mark.parametrize("bad_url", ["example.com", "ftp://example.com", "www.example.com"])
    def test_invalid_url_raises(self, bad_url) -> None:
        with pytest.raises(ValidationError, match="must start with http"):
            validate_job_url(bad_url)


class TestEmail:
    def test_valid_email_lowercased(self) -> None:
        assert validate_email("Jane.Doe@Example.com") == "jane.doe@example.com"

    def test_blank_email_is_none_when_not_required(self) -> None:
        assert validate_email("") is None

    def test_blank_email_raises_when_required(self) -> None:
        with pytest.raises(ValidationError, match="required"):
            validate_email("", required=True)

    def test_invalid_email_raises(self) -> None:
        with pytest.raises(ValidationError, match="valid email"):
            validate_email("not-an-email")


class TestTags:
    def test_blank_tags_is_none(self) -> None:
        assert validate_tags("") is None

    def test_tags_normalized_deduped(self) -> None:
        assert validate_tags("Referral, Dream Job, referral") == ["referral", "dream job"]

    def test_empty_entries_dropped(self) -> None:
        assert validate_tags("a,,b, ,c") == ["a", "b", "c"]

    def test_too_long_tag_raises(self) -> None:
        with pytest.raises(ValidationError, match="30 characters or fewer"):
            validate_tags("x" * 31)

    def test_too_many_tags_raises(self) -> None:
        with pytest.raises(ValidationError, match="at most 10 tags"):
            validate_tags(",".join(str(i) for i in range(11)))


class TestInterviewRounds:
    def test_blank_defaults_to_zero(self) -> None:
        assert validate_interview_rounds("") == 0
        assert validate_interview_rounds(None) == 0

    def test_valid_count(self) -> None:
        assert validate_interview_rounds("3") == 3

    def test_negative_raises(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            validate_interview_rounds("-1")

    def test_non_numeric_raises(self) -> None:
        with pytest.raises(ValidationError, match="whole number"):
            validate_interview_rounds("abc")

    def test_too_large_raises(self) -> None:
        with pytest.raises(ValidationError, match="20 or fewer"):
            validate_interview_rounds("99")


class TestValidateId:
    def test_valid_id(self) -> None:
        assert validate_id("5") == 5
        assert validate_id(5) == 5

    def test_non_numeric_id_raises(self) -> None:
        with pytest.raises(ValidationError, match="whole number"):
            validate_id("abc")

    @pytest.mark.parametrize("bad_id", ["0", "-1"])
    def test_non_positive_id_raises(self, bad_id) -> None:
        with pytest.raises(ValidationError, match="positive"):
            validate_id(bad_id)
