"""
test_repository.py

Tests for `ApplicationRepository` against an isolated temporary SQLite
database (via the `temp_db`/`repository` fixtures in conftest.py). These
exercise the data-access layer directly: raw CRUD, search, filtering, and
the `exists()` duplicate check - all against real SQLite, just not the
real production file.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.database.exceptions import DatabaseError, RecordNotFoundError
from app.models.application import JobApplication, JobType, Priority, Status, WorkMode


class TestCreate:
    def test_create_returns_new_id(self, repository, sample_application) -> None:
        new_id = repository.create(sample_application)
        assert isinstance(new_id, int)
        assert new_id > 0

    def test_created_record_is_persisted(self, repository, sample_application) -> None:
        new_id = repository.create(sample_application)
        fetched = repository.get_by_id(new_id)
        assert fetched is not None
        assert fetched.company == sample_application.company
        assert fetched.job_title == sample_application.job_title
        assert fetched.created_at is not None
        assert fetched.updated_at is not None

    def test_create_rejects_blank_company(self, repository, sample_application) -> None:
        bad = replace(sample_application, company="   ")
        with pytest.raises(DatabaseError):
            repository.create(bad)


class TestRead:
    def test_get_by_id_returns_none_for_missing(self, repository) -> None:
        assert repository.get_by_id(9999) is None

    def test_get_all_empty_database(self, repository) -> None:
        assert repository.get_all() == []

    def test_get_all_returns_every_record(self, repository, sample_application) -> None:
        repository.create(sample_application)
        repository.create(replace(sample_application, company="Other Co", job_title="Other Role"))
        assert len(repository.get_all()) == 2


class TestUpdate:
    def test_update_changes_fields(self, repository, sample_application) -> None:
        new_id = repository.create(sample_application)
        record = repository.get_by_id(new_id)
        record.status = Status.INTERVIEW
        record.notes = "Phone screen scheduled"
        repository.update(record)

        updated = repository.get_by_id(new_id)
        assert updated.status == Status.INTERVIEW
        assert updated.notes == "Phone screen scheduled"

    def test_update_refreshes_updated_at_only(self, repository, sample_application) -> None:
        new_id = repository.create(sample_application)
        original = repository.get_by_id(new_id)

        original.status = Status.OFFER
        repository.update(original)
        updated = repository.get_by_id(new_id)

        assert updated.created_at == original.created_at
        assert updated.status == Status.OFFER

    def test_update_missing_record_raises(self, repository, sample_application) -> None:
        ghost = replace(sample_application, id=9999)
        with pytest.raises(RecordNotFoundError):
            repository.update(ghost)


class TestDelete:
    def test_delete_removes_record(self, repository, sample_application) -> None:
        new_id = repository.create(sample_application)
        repository.delete(new_id)
        assert repository.get_by_id(new_id) is None

    def test_delete_missing_record_raises(self, repository) -> None:
        with pytest.raises(RecordNotFoundError):
            repository.delete(9999)


class TestExists:
    def test_exists_true_for_duplicate(self, repository, sample_application) -> None:
        repository.create(sample_application)
        assert repository.exists(
            sample_application.company, sample_application.job_title, sample_application.application_date
        )

    def test_exists_false_for_new_combo(self, repository, sample_application) -> None:
        repository.create(sample_application)
        assert not repository.exists("Somewhere Else", "Some Role", "2026-01-01")

    def test_exists_excludes_given_id(self, repository, sample_application) -> None:
        new_id = repository.create(sample_application)
        assert not repository.exists(
            sample_application.company,
            sample_application.job_title,
            sample_application.application_date,
            exclude_id=new_id,
        )

    def test_exists_is_case_insensitive(self, repository, sample_application) -> None:
        repository.create(sample_application)
        assert repository.exists(
            sample_application.company.upper(),
            sample_application.job_title.upper(),
            sample_application.application_date,
        )


class TestSearch:
    @pytest.fixture(autouse=True)
    def _seed(self, repository) -> None:
        repository.create(
            JobApplication(
                company="TechNova Inc",
                job_title="Backend Engineer",
                application_date="2026-08-01",
                location="Bengaluru",
                status=Status.APPLIED,
                recruiter="Priya Sharma",
            )
        )
        repository.create(
            JobApplication(
                company="Globex",
                job_title="Data Analyst",
                application_date="2026-08-05",
                location="Pune",
                status=Status.INTERVIEW,
                recruiter="Raj Mehta",
                tags=["referral"],
            )
        )

    def test_search_by_company(self, repository) -> None:
        results = repository.search("TechNova")
        assert len(results) == 1
        assert results[0].company == "TechNova Inc"

    def test_search_by_job_title(self, repository) -> None:
        results = repository.search("Analyst")
        assert len(results) == 1
        assert results[0].job_title == "Data Analyst"

    def test_search_is_case_insensitive(self, repository) -> None:
        assert len(repository.search("technova")) == 1
        assert len(repository.search("TECHNOVA")) == 1

    def test_search_by_location(self, repository) -> None:
        assert len(repository.search("Bengaluru")) == 1

    def test_search_by_status(self, repository) -> None:
        assert len(repository.search("Interview")) == 1

    def test_search_by_recruiter(self, repository) -> None:
        assert len(repository.search("Priya")) == 1

    def test_search_by_tag(self, repository) -> None:
        assert len(repository.search("referral")) == 1

    def test_search_no_match_returns_empty(self, repository) -> None:
        assert repository.search("nonexistent-xyz") == []


class TestFilter:
    @pytest.fixture(autouse=True)
    def _seed(self, repository) -> None:
        repository.create(
            JobApplication(
                company="TechNova Inc",
                job_title="Backend Engineer",
                application_date="2026-08-01",
                job_type=JobType.FULL_TIME,
                work_mode=WorkMode.REMOTE,
                status=Status.APPLIED,
                priority=Priority.HIGH,
            )
        )
        repository.create(
            JobApplication(
                company="Globex",
                job_title="Data Analyst Intern",
                application_date="2026-08-15",
                job_type=JobType.INTERNSHIP,
                work_mode=WorkMode.HYBRID,
                status=Status.INTERVIEW,
                priority=Priority.MEDIUM,
            )
        )
        repository.create(
            JobApplication(
                company="TechNova Inc",
                job_title="DevOps Engineer",
                application_date="2026-08-20",
                job_type=JobType.CONTRACT,
                work_mode=WorkMode.REMOTE,
                status=Status.REJECTED,
                priority=Priority.MEDIUM,
            )
        )

    def test_filter_by_status(self, repository) -> None:
        results = repository.filter_applications(status="Interview")
        assert len(results) == 1
        assert results[0].company == "Globex"

    def test_filter_by_job_type(self, repository) -> None:
        results = repository.filter_applications(job_type="Full-time")
        assert len(results) == 1
        assert results[0].job_title == "Backend Engineer"

    def test_filter_by_work_mode(self, repository) -> None:
        results = repository.filter_applications(work_mode="Remote")
        assert len(results) == 2

    def test_filter_by_priority(self, repository) -> None:
        results = repository.filter_applications(priority="Medium")
        assert len(results) == 2

    def test_filter_combined_company_and_work_mode(self, repository) -> None:
        results = repository.filter_applications(company="TechNova", work_mode="Remote")
        assert len(results) == 2
        assert all(a.company == "TechNova Inc" for a in results)

    def test_filter_combined_three_criteria(self, repository) -> None:
        results = repository.filter_applications(company="TechNova", work_mode="Remote", status="Rejected")
        assert len(results) == 1
        assert results[0].job_title == "DevOps Engineer"

    def test_filter_date_range(self, repository) -> None:
        results = repository.filter_applications(date_from="2026-08-10", date_to="2026-08-31")
        assert len(results) == 2

    def test_filter_no_criteria_returns_all(self, repository) -> None:
        assert len(repository.filter_applications()) == 3

    def test_filter_no_match_returns_empty(self, repository) -> None:
        assert repository.filter_applications(company="Nonexistent") == []


class TestAnalyticsSupportQueries:
    def test_count_all_empty(self, repository) -> None:
        assert repository.count_all() == 0

    def test_count_by_status(self, repository, sample_application) -> None:
        repository.create(sample_application)
        repository.create(replace(sample_application, job_title="Other Role", status=Status.INTERVIEW))
        counts = repository.count_by_status()
        assert counts.get("Applied") == 1
        assert counts.get("Interview") == 1

    def test_count_by_company_top_n(self, repository, sample_application) -> None:
        repository.create(sample_application)
        repository.create(replace(sample_application, job_title="Role 2"))
        repository.create(replace(sample_application, company="Other Co", job_title="Role 3"))
        top = repository.count_by_company(limit=5)
        assert top[0] == (sample_application.company, 2)

    def test_get_recent_orders_by_created_at_desc(self, repository, sample_application) -> None:
        first_id = repository.create(sample_application)
        second_id = repository.create(replace(sample_application, job_title="Second Role"))
        recent = repository.get_recent(limit=5)
        assert recent[0].id == second_id
        assert recent[1].id == first_id

    def test_get_with_follow_up_only_returns_dated(self, repository, sample_application) -> None:
        repository.create(sample_application)  # has follow_up_date set
        repository.create(replace(sample_application, job_title="No Follow-up", follow_up_date=None))
        results = repository.get_with_follow_up()
        assert len(results) == 1
        assert results[0].follow_up_date == sample_application.follow_up_date
