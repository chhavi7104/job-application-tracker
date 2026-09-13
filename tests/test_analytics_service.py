"""
test_analytics_service.py

Tests for `AnalyticsService`: the dashboard's zero-filled breakdowns, the
hiring-funnel rate calculations, and follow-up date classification
(overdue / due today / upcoming) relative to the real current date.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.models.application import JobApplication, JobType, Priority, Status, WorkMode


class TestDashboardSummaryEmpty:
    def test_empty_database_summary(self, analytics_service) -> None:
        summary = analytics_service.get_dashboard_summary()
        assert summary.total_applications == 0
        assert summary.applied_total == 0
        assert summary.response_rate == 0.0
        assert summary.interview_rate == 0.0
        assert summary.offer_rate == 0.0
        assert summary.acceptance_rate == 0.0
        # All 8 statuses should still be present, zero-filled.
        assert set(summary.by_status.keys()) == {s.value for s in Status}
        assert all(count == 0 for count in summary.by_status.values())


class TestDashboardBreakdownsAndRates:
    @staticmethod
    def _seed(repository) -> None:
        seed = [
            dict(company="A", job_title="Role1", application_date="2026-08-01",
                 job_type=JobType.FULL_TIME, work_mode=WorkMode.REMOTE,
                 status=Status.SAVED, priority=Priority.LOW),
            dict(company="B", job_title="Role2", application_date="2026-08-02",
                 job_type=JobType.FULL_TIME, work_mode=WorkMode.REMOTE,
                 status=Status.APPLIED, priority=Priority.MEDIUM),
            dict(company="C", job_title="Role3", application_date="2026-08-03",
                 job_type=JobType.INTERNSHIP, work_mode=WorkMode.HYBRID,
                 status=Status.ASSESSMENT, priority=Priority.MEDIUM),
            dict(company="D", job_title="Role4", application_date="2026-08-04",
                 job_type=JobType.FULL_TIME, work_mode=WorkMode.ON_SITE,
                 status=Status.INTERVIEW, priority=Priority.HIGH),
            dict(company="A", job_title="Role5", application_date="2026-08-05",
                 job_type=JobType.CONTRACT, work_mode=WorkMode.REMOTE,
                 status=Status.OFFER, priority=Priority.HIGH),
            dict(company="E", job_title="Role6", application_date="2026-08-06",
                 job_type=JobType.FULL_TIME, work_mode=WorkMode.ON_SITE,
                 status=Status.REJECTED, priority=Priority.LOW),
            dict(company="F", job_title="Role7", application_date="2026-08-07",
                 job_type=JobType.PART_TIME, work_mode=WorkMode.HYBRID,
                 status=Status.WITHDRAWN, priority=Priority.LOW),
            dict(company="A", job_title="Role8", application_date="2026-08-08",
                 job_type=JobType.FULL_TIME, work_mode=WorkMode.REMOTE,
                 status=Status.ACCEPTED, priority=Priority.HIGH),
        ]
        for kwargs in seed:
            repository.create(JobApplication(**kwargs))

    def test_total_and_status_breakdown(self, repository, analytics_service) -> None:
        self._seed(repository)
        summary = analytics_service.get_dashboard_summary()
        assert summary.total_applications == 8
        assert summary.by_status[Status.SAVED.value] == 1
        assert summary.by_status[Status.APPLIED.value] == 1
        assert summary.by_status[Status.ACCEPTED.value] == 1

    def test_job_type_and_work_mode_breakdown(self, repository, analytics_service) -> None:
        self._seed(repository)
        summary = analytics_service.get_dashboard_summary()
        assert summary.by_job_type[JobType.FULL_TIME.value] == 5
        assert summary.by_work_mode[WorkMode.REMOTE.value] == 4

    def test_top_companies(self, repository, analytics_service) -> None:
        self._seed(repository)
        summary = analytics_service.get_dashboard_summary()
        assert summary.by_company[0] == ("A", 3)

    def test_funnel_rates(self, repository, analytics_service) -> None:
        self._seed(repository)
        summary = analytics_service.get_dashboard_summary()

        # applied_total = 8 total - 1 Saved = 7
        assert summary.applied_total == 7
        # responded = Assessment + Interview + Offer + Rejected + Accepted = 5
        assert summary.responded_count == 5
        assert round(summary.response_rate, 1) == round(5 / 7 * 100, 1)
        # interviewed = Interview + Offer + Accepted = 3
        assert summary.interviewed_count == 3
        assert round(summary.interview_rate, 1) == round(3 / 7 * 100, 1)
        # offered = Offer + Accepted = 2
        assert summary.offer_count == 2
        assert round(summary.offer_rate, 1) == round(2 / 7 * 100, 1)
        # accepted = 1, out of 2 offers = 50%
        assert summary.accepted_count == 1
        assert summary.acceptance_rate == 50.0

    def test_recent_applications_most_recent_first(self, repository, analytics_service) -> None:
        self._seed(repository)
        summary = analytics_service.get_dashboard_summary()
        assert summary.recent_applications[0].job_title == "Role8"


class TestFollowUpClassification:
    @staticmethod
    def _iso(offset_days: int) -> str:
        return (date.today() + timedelta(days=offset_days)).strftime("%Y-%m-%d")

    def test_overdue_due_today_upcoming_counts(self, repository, analytics_service) -> None:
        repository.create(
            JobApplication(company="A", job_title="Overdue Role", application_date="2026-01-01",
                            follow_up_date=self._iso(-5))
        )
        repository.create(
            JobApplication(company="B", job_title="Today Role", application_date="2026-01-01",
                            follow_up_date=self._iso(0))
        )
        repository.create(
            JobApplication(company="C", job_title="Future Role", application_date="2026-01-01",
                            follow_up_date=self._iso(7))
        )
        repository.create(
            JobApplication(company="D", job_title="No Follow-up", application_date="2026-01-01")
        )

        summary = analytics_service.get_dashboard_summary()
        assert summary.overdue_follow_ups == 1
        assert summary.due_today_follow_ups == 1
        assert summary.upcoming_follow_ups == 1

    def test_get_follow_ups_sorted_and_labeled(self, repository, analytics_service) -> None:
        repository.create(
            JobApplication(company="A", job_title="Overdue Role", application_date="2026-01-01",
                            follow_up_date=self._iso(-3))
        )
        repository.create(
            JobApplication(company="B", job_title="Soon Role", application_date="2026-01-01",
                            follow_up_date=self._iso(2))
        )

        items = analytics_service.get_follow_ups()
        assert len(items) == 2
        assert items[0].application.job_title == "Overdue Role"
        assert items[0].days_until == -3
        assert items[1].days_until == 2

    def test_no_follow_ups_returns_empty(self, repository, analytics_service) -> None:
        repository.create(JobApplication(company="A", job_title="Role", application_date="2026-01-01"))
        assert analytics_service.get_follow_ups() == []

    def test_malformed_follow_up_date_is_skipped_not_raised(self, repository, analytics_service) -> None:
        # Bypass validation to simulate a corrupted/malformed date already
        # in the database - the analytics layer should skip it, not crash.
        application = JobApplication(
            company="A", job_title="Role", application_date="2026-01-01", follow_up_date="2026-13-40"
        )
        repository.create(application)
        # get_with_follow_up() will return it (it's non-null), but
        # AnalyticsService must not blow up trying to parse it.
        items = analytics_service.get_follow_ups()
        assert items == []
        summary = analytics_service.get_dashboard_summary()
        assert summary.overdue_follow_ups == 0
        assert summary.due_today_follow_ups == 0
        assert summary.upcoming_follow_ups == 0
