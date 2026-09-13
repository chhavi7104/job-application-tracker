"""
analytics_service.py

`AnalyticsService` derives summary statistics and follow-up reminders from
stored job application data. Like `ApplicationService`, it is the only
layer allowed to call `ApplicationRepository` for this purpose, and the
CLI must go through it rather than querying the repository or database
directly - every calculation below (funnel rates, follow-up
classification, zero-filled breakdowns) is business logic and lives here,
never in a CLI handler.

Responsibilities:
    - Aggregate counts (total applications, breakdown by status/job type/
      work mode/priority/company, most recent applications) for the
      Dashboard view.
    - Compute hiring-funnel conversion rates (response/interview/offer/
      acceptance) from those counts.
    - Classify each application's `follow_up_date` as overdue, due today,
      or upcoming, relative to the current date - this "what counts as
      overdue" business rule belongs here, not in the repository (which
      only knows how to fetch rows) or the CLI (which only renders them).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from app.database.exceptions import DatabaseError
from app.database.repository import ApplicationRepository
from app.models.application import JobApplication, JobType, Priority, Status, WorkMode
from app.services.exceptions import ServiceError
from app.utils.logger import get_logger

logger = get_logger(__name__)

# How many companies/recent applications to show on the Dashboard.
_TOP_COMPANIES_LIMIT = 5
_RECENT_APPLICATIONS_LIMIT = 5

# Statuses that count as "the company responded" (positive or negative),
# i.e. anything past the passive "Applied"/"Saved" stages. Used for the
# funnel rate calculations below.
_RESPONDED_STATUSES = {
    Status.ASSESSMENT.value,
    Status.INTERVIEW.value,
    Status.OFFER.value,
    Status.REJECTED.value,
    Status.ACCEPTED.value,
}
_INTERVIEWED_STATUSES = {Status.INTERVIEW.value, Status.OFFER.value, Status.ACCEPTED.value}
_OFFERED_STATUSES = {Status.OFFER.value, Status.ACCEPTED.value}
_ACCEPTED_STATUSES = {Status.ACCEPTED.value}


@dataclass
class DashboardSummary:
    """Aggregate statistics rendered on the Dashboard screen.

    Attributes:
        total_applications: Total number of application records.
        by_status: Application count for every `Status` value (0 for
            statuses with no applications yet), in enum-definition order.
        by_job_type: Application count for every `JobType` value.
        by_work_mode: Application count for every `WorkMode` value.
        by_priority: Application count for every `Priority` value.
        by_company: Top companies by application count, most first, as
            `(company, count)` pairs.
        recent_applications: The most recently *added* applications
            (by `created_at`), most recent first.
        applied_total: Applications actually submitted (status != Saved) -
            the denominator for the funnel rates below.
        responded_count / interviewed_count / offer_count / accepted_count:
            Raw counts backing the four rates, shown alongside them so the
            percentages are never presented without their basis.
        response_rate: `responded_count / applied_total * 100`.
        interview_rate: `interviewed_count / applied_total * 100`.
        offer_rate: `offer_count / applied_total * 100`.
        acceptance_rate: `accepted_count / offer_count * 100` (offers that
            were actually accepted - 0 if there were no offers).
        overdue_follow_ups: Applications whose follow-up date has passed.
        due_today_follow_ups: Applications whose follow-up date is today.
        upcoming_follow_ups: Applications whose follow-up date is in the future.
    """

    total_applications: int
    by_status: dict[str, int]
    by_job_type: dict[str, int]
    by_work_mode: dict[str, int]
    by_priority: dict[str, int]
    by_company: list[tuple[str, int]]
    recent_applications: list[JobApplication]

    applied_total: int
    responded_count: int
    interviewed_count: int
    offer_count: int
    accepted_count: int
    response_rate: float
    interview_rate: float
    offer_rate: float
    acceptance_rate: float

    overdue_follow_ups: int
    due_today_follow_ups: int
    upcoming_follow_ups: int


@dataclass
class FollowUpItem:
    """A single application paired with how many days remain until its
    follow-up date (negative = overdue, 0 = due today, positive = upcoming)."""

    application: JobApplication
    days_until: int


class AnalyticsService:
    """Business-logic layer for dashboard statistics and follow-up reminders."""

    def __init__(self, repository: Optional[ApplicationRepository] = None) -> None:
        self._repository = repository or ApplicationRepository()

    def get_dashboard_summary(self) -> DashboardSummary:
        """Compute every statistic shown on the Dashboard screen: totals,
        breakdowns, funnel rates, and a follow-up summary.

        Raises:
            ServiceError: If any underlying database read fails.
        """
        try:
            total = self._repository.count_all()
            raw_by_status = self._repository.count_by_status()
            raw_by_job_type = self._repository.count_by_job_type()
            raw_by_work_mode = self._repository.count_by_work_mode()
            raw_by_priority = self._repository.count_by_priority()
            by_company = self._repository.count_by_company(limit=_TOP_COMPANIES_LIMIT)
            recent_applications = self._repository.get_recent(limit=_RECENT_APPLICATIONS_LIMIT)
            follow_up_applications = self._repository.get_with_follow_up()
        except DatabaseError as exc:
            raise ServiceError("Could not compute the dashboard summary due to a database error.") from exc

        by_status = self._zero_fill(raw_by_status, Status)
        by_job_type = self._zero_fill(raw_by_job_type, JobType)
        by_work_mode = self._zero_fill(raw_by_work_mode, WorkMode)
        by_priority = self._zero_fill(raw_by_priority, Priority)

        applied_total = total - by_status.get(Status.SAVED.value, 0)
        responded_count = self._sum_statuses(by_status, _RESPONDED_STATUSES)
        interviewed_count = self._sum_statuses(by_status, _INTERVIEWED_STATUSES)
        offer_count = self._sum_statuses(by_status, _OFFERED_STATUSES)
        accepted_count = self._sum_statuses(by_status, _ACCEPTED_STATUSES)

        overdue, due_today, upcoming = self._classify_follow_ups(follow_up_applications)

        return DashboardSummary(
            total_applications=total,
            by_status=by_status,
            by_job_type=by_job_type,
            by_work_mode=by_work_mode,
            by_priority=by_priority,
            by_company=by_company,
            recent_applications=recent_applications,
            applied_total=applied_total,
            responded_count=responded_count,
            interviewed_count=interviewed_count,
            offer_count=offer_count,
            accepted_count=accepted_count,
            response_rate=self._percentage(responded_count, applied_total),
            interview_rate=self._percentage(interviewed_count, applied_total),
            offer_rate=self._percentage(offer_count, applied_total),
            acceptance_rate=self._percentage(accepted_count, offer_count),
            overdue_follow_ups=overdue,
            due_today_follow_ups=due_today,
            upcoming_follow_ups=upcoming,
        )

    def get_follow_ups(self) -> list[FollowUpItem]:
        """Fetch every application with a follow-up date, paired with how
        many days remain (soonest/most-overdue first).

        Raises:
            ServiceError: If the underlying database read fails.
        """
        try:
            applications = self._repository.get_with_follow_up()
        except DatabaseError as exc:
            raise ServiceError("Could not fetch follow-ups due to a database error.") from exc

        today = date.today()
        items: list[FollowUpItem] = []
        for application in applications:
            days = self._days_until(application.follow_up_date, today)
            if days is None:
                continue
            items.append(FollowUpItem(application=application, days_until=days))
        return items  # already ordered by follow_up_date via the repository query

    # --- Internal helpers ------------------------------------------------------

    def _classify_follow_ups(self, applications: list[JobApplication]) -> tuple[int, int, int]:
        """Classify a list of applications' follow-up dates into
        (overdue, due_today, upcoming) counts relative to today."""
        today = date.today()
        overdue = due_today = upcoming = 0
        for application in applications:
            days = self._days_until(application.follow_up_date, today)
            if days is None:
                continue
            if days < 0:
                overdue += 1
            elif days == 0:
                due_today += 1
            else:
                upcoming += 1
        return overdue, due_today, upcoming

    @staticmethod
    def _zero_fill(counts: dict[str, int], enum_cls) -> dict[str, int]:
        """Return `counts` with every member of `enum_cls` present (as 0
        if it had no applications), in enum-definition order, so the
        Dashboard always shows the full set of statuses/types/modes/
        priorities rather than only the ones with data."""
        return {member.value: counts.get(member.value, 0) for member in enum_cls}

    @staticmethod
    def _sum_statuses(by_status: dict[str, int], statuses: set[str]) -> int:
        """Sum the counts for a subset of status values (used to build the
        funnel counts from the zero-filled status breakdown)."""
        return sum(count for status, count in by_status.items() if status in statuses)

    @staticmethod
    def _percentage(numerator: int, denominator: int) -> float:
        """Return `numerator / denominator * 100`, or 0.0 if the
        denominator is 0 (avoids a `ZeroDivisionError` when there's no
        data yet)."""
        if denominator <= 0:
            return 0.0
        return (numerator / denominator) * 100

    @staticmethod
    def _days_until(follow_up_date: Optional[str], today: date) -> Optional[int]:
        """Return the number of days between `today` and `follow_up_date`,
        or `None` if the date is missing or malformed.

        A malformed date shouldn't normally reach the database (input is
        validated on create/update), but this stays defensive rather than
        raising, so one bad row can't take down the whole dashboard.
        """
        if not follow_up_date:
            return None
        try:
            target = datetime.strptime(follow_up_date, "%Y-%m-%d").date()
        except ValueError:
            logger.warning("Skipping malformed follow_up_date %r in analytics.", follow_up_date)
            return None
        return (target - today).days
