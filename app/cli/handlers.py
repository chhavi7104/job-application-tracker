"""
handlers.py

Handler functions invoked by menu.py for each menu option. Each handler:
    1. Collects raw input from the user via Rich prompts (pre-filling
       current values on update, so the user can just press Enter to keep
       them unchanged).
    2. Calls the corresponding service method (`ApplicationService` or
       `AnalyticsService`), passing the raw input straight through - all
       validation and business rules live in the service layer, not here.
    3. Renders the result (or a clear error message) via the shared
       helpers in `app.cli.display`.

Handlers never construct SQL, talk to the repository, or build Rich
tables/panels inline - table/message styling lives in `display.py` so it
stays consistent everywhere and handlers stay focused on the flow of each
action. This keeps the CLI strictly a presentation layer.
"""

from __future__ import annotations

from typing import Iterable

from rich.prompt import Confirm, Prompt

from app.cli import display
from app.cli.display import console
from app.models.application import JobType, Priority, Status, WorkMode
from app.services.analytics_service import AnalyticsService
from app.services.application_service import ApplicationService
from app.services.exceptions import ApplicationNotFoundError, DuplicateApplicationError, ServiceError
from app.utils.logger import get_logger
from app.validators.validators import ValidationError, today_str

logger = get_logger(__name__)

# Single shared service instances, reused across handlers for the life of
# the CLI session. Both services are stateless (each method opens its own
# repository/connection), so sharing them is safe.
_service = ApplicationService()
_analytics = AnalyticsService()


# --- Shared field prompting (used by both Add and Update) ------------------

# (field key, prompt label). A single source of truth for every
# application field prompt, so Add and Update can't drift out of sync.
_APPLICATION_FIELD_SPECS: list[tuple[str, str]] = [
    ("company", "Company"),
    ("job_title", "Job title"),
    ("application_date", "Application date (YYYY-MM-DD)"),
    ("job_type", "Job type"),
    ("work_mode", "Work mode"),
    ("status", "Status"),
    ("priority", "Priority"),
    ("location", "Location"),
    ("salary", "Salary (numeric)"),
    ("job_url", "Job URL"),
    ("recruiter", "Recruiter"),
    ("notes", "Notes"),
    ("follow_up_date", "Follow-up date (YYYY-MM-DD)"),
    ("tags", "Tags (comma-separated)"),
    ("interview_rounds", "Interview rounds completed so far"),
]
# Enum-backed fields get their allowed choices looked up here rather than
# recomputing `_enum_values(...)` on every prompt call.
_FIELD_CHOICES: dict[str, list[str]] = {
    "job_type": [member.value for member in JobType],
    "work_mode": [member.value for member in WorkMode],
    "status": [member.value for member in Status],
    "priority": [member.value for member in Priority],
}


def _collect_application_fields(defaults: dict[str, str]) -> dict[str, str]:
    """Prompt for every application field (in `_APPLICATION_FIELD_SPECS`
    order), pre-filled from `defaults`, and return the raw strings typed.

    Used by both Add (defaults are today's date / enum defaults / blanks)
    and Update (defaults are the record's current values), so the two
    flows can never have their prompts drift out of sync.
    """
    values: dict[str, str] = {}
    for key, label in _APPLICATION_FIELD_SPECS:
        default = defaults.get(key, "")
        choices = _FIELD_CHOICES.get(key)
        values[key] = Prompt.ask(label, choices=choices, default=default) if choices else Prompt.ask(
            label, default=default
        )
    return values


# --- Add ---------------------------------------------------------------------

_ADD_DEFAULTS: dict[str, str] = {
    "application_date": "",  # filled in per-call with today's date
    "job_type": JobType.FULL_TIME.value,
    "work_mode": WorkMode.ON_SITE.value,
    "status": Status.APPLIED.value,
    "priority": Priority.MEDIUM.value,
    "interview_rounds": "0",
}


def handle_add_application() -> None:
    """Prompt for a new application's details and create it. On invalid
    input, lets the user correct and resubmit - without returning to the
    main menu, and without losing whatever they'd already typed."""
    display.print_section("Add New Application")

    defaults = {**_ADD_DEFAULTS, "application_date": today_str()}
    while True:
        values = _collect_application_fields(defaults)

        try:
            with display.loading("Saving application..."):
                application = _service.add_application(**values)
        except (ValidationError, DuplicateApplicationError, ServiceError) as exc:
            display.print_error(f"Could not add application: {exc}")
            if Confirm.ask("Correct the details and try again?", default=True):
                defaults = values  # keep whatever was already entered
                continue
            return
        break

    display.print_success(f"Application added successfully (ID {application.id}).")
    console.print(display.build_detail_table(application))


# --- View --------------------------------------------------------------------

def handle_view_all_applications() -> None:
    """Fetch and display every application in a summary table."""
    try:
        with display.loading("Fetching applications..."):
            applications = _service.list_applications()
    except ServiceError as exc:
        display.print_error(str(exc))
        return

    if not applications:
        display.print_warning("No applications found. Add one first!")
        return

    console.print(display.build_summary_table(applications))


def handle_view_application_by_id() -> None:
    """Prompt for an ID and display that application's full details."""
    display.print_section("View Application Details")
    raw_id = Prompt.ask("Application ID")

    try:
        application = _service.get_application(raw_id)
    except (ValidationError, ApplicationNotFoundError, ServiceError) as exc:
        display.print_error(str(exc))
        return

    console.print(display.build_detail_table(application))


# --- Update ------------------------------------------------------------------

def handle_update_application() -> None:
    """Prompt for an ID, then walk through each field (pre-filled with the
    current value) so the user can update only what's changed."""
    display.print_section("Update Application")
    raw_id = Prompt.ask("ID of application to update")

    try:
        existing = _service.get_application(raw_id)
    except (ValidationError, ApplicationNotFoundError, ServiceError) as exc:
        display.print_error(str(exc))
        return

    console.print("\n[bold cyan]Current details:[/bold cyan]")
    console.print(display.build_detail_table(existing))
    display.print_info("Press Enter to keep the current value for any field.")
    console.print()

    defaults = _application_to_field_defaults(existing)
    while True:
        values = _collect_application_fields(defaults)
        changes = _diff_fields(existing, **values)

        try:
            with display.loading("Updating application..."):
                updated = _service.update_application(existing.id, **changes)
        except (ValidationError, ApplicationNotFoundError, DuplicateApplicationError, ServiceError) as exc:
            display.print_error(f"Could not update application: {exc}")
            if Confirm.ask("Correct the details and try again?", default=True):
                defaults = values  # keep whatever was already entered
                continue
            return
        break

    display.print_success(f"Application {updated.id} updated successfully.")
    console.print(display.build_detail_table(updated))


# --- Delete ------------------------------------------------------------------

def handle_delete_application() -> None:
    """Prompt for an ID, show the record, and confirm before deleting it."""
    display.print_section("Delete Application")
    raw_id = Prompt.ask("ID of application to delete")

    try:
        existing = _service.get_application(raw_id)
    except (ValidationError, ApplicationNotFoundError, ServiceError) as exc:
        display.print_error(str(exc))
        return

    console.print(display.build_detail_table(existing))
    confirmed = Confirm.ask(
        f"[bold red]Delete application {existing.id} ({existing.job_title} @ {existing.company})? "
        "This cannot be undone.[/bold red]",
        default=False,
    )
    if not confirmed:
        display.print_warning("Deletion cancelled.")
        return

    try:
        with display.loading("Deleting application..."):
            deleted = _service.delete_application(existing.id)
    except (ValidationError, ApplicationNotFoundError, ServiceError) as exc:
        display.print_error(f"Could not delete application: {exc}")
        return

    display.print_success(f"Deleted application {deleted.id} ({deleted.job_title} @ {deleted.company}).")


# --- Search ------------------------------------------------------------------

def handle_search_applications() -> None:
    """Prompt for a keyword and search across company, job title,
    location, status, and recruiter (case-insensitive). Lets the user
    correct an invalid (empty) keyword without crashing or losing the
    menu loop."""
    display.print_section("Search Applications")
    display.print_info("Matches company, job title, location, status, recruiter, or tags (case-insensitive).")

    while True:
        keyword = Prompt.ask("Search keyword")
        try:
            with display.loading("Searching..."):
                results = _service.search_applications(keyword)
        except (ValidationError, ServiceError) as exc:
            display.print_error(str(exc))
            if Confirm.ask("Try again?", default=True):
                continue
            return
        break

    if not results:
        display.print_warning(f"No applications matched '{keyword}'.")
        return

    display.print_success(f"Found {len(results)} matching application(s).")
    console.print(display.build_summary_table(results, title=f"Search results for '{keyword}'"))


# --- Filter --------------------------------------------------------------

def handle_filter_applications() -> None:
    """Prompt for any combination of filters (all optional - blank skips
    a filter) and display matching applications. Lets the user correct
    invalid values (e.g. a malformed date) without crashing."""
    display.print_section("Filter Applications")
    display.print_info("Leave any field blank to skip that filter. Filters combine with AND.")

    while True:
        status = Prompt.ask("Status", choices=_enum_values(Status), default="")
        job_type = Prompt.ask("Job type", choices=_enum_values(JobType), default="")
        work_mode = Prompt.ask("Work mode", choices=_enum_values(WorkMode), default="")
        priority = Prompt.ask("Priority", choices=_enum_values(Priority), default="")
        company = Prompt.ask("Company contains", default="")
        location = Prompt.ask("Location contains", default="")
        date_from = Prompt.ask("Applied on/after (YYYY-MM-DD)", default="")
        date_to = Prompt.ask("Applied on/before (YYYY-MM-DD)", default="")

        try:
            with display.loading("Applying filters..."):
                results = _service.filter_applications(
                    status=status or None,
                    job_type=job_type or None,
                    work_mode=work_mode or None,
                    priority=priority or None,
                    company=company or None,
                    location=location or None,
                    date_from=date_from or None,
                    date_to=date_to or None,
                )
        except (ValidationError, ServiceError) as exc:
            display.print_error(str(exc))
            if Confirm.ask("Correct the filters and try again?", default=True):
                continue
            return
        break

    if not results:
        display.print_warning("No applications matched those filters.")
        return

    display.print_success(f"Found {len(results)} matching application(s).")
    console.print(display.build_summary_table(results, title="Filtered Applications"))


# --- Dashboard -----------------------------------------------------------

def handle_dashboard() -> None:
    """Fetch and display the full analytics dashboard: totals, breakdowns
    by status/job type/work mode/priority, top companies, recent
    applications, funnel conversion rates, and a follow-up summary."""
    display.print_section("Dashboard")

    try:
        with display.loading("Crunching numbers..."):
            summary = _analytics.get_dashboard_summary()
    except ServiceError as exc:
        display.print_error(str(exc))
        return

    console.print(f"[bold]Total applications:[/bold] {summary.total_applications}")
    if summary.total_applications == 0:
        display.print_warning("No applications yet - add one to see stats here.")
        return

    console.print(display.build_counts_table("By Status", summary.by_status, kind="status"))
    console.print(display.build_counts_table("By Job Type", summary.by_job_type, kind="plain"))
    console.print(display.build_counts_table("By Work Mode", summary.by_work_mode, kind="plain"))
    console.print(display.build_counts_table("By Priority", summary.by_priority, kind="priority"))
    console.print(display.build_company_table(summary.by_company))

    console.print(
        display.build_metrics_panel(
            response_rate=summary.response_rate,
            interview_rate=summary.interview_rate,
            offer_rate=summary.offer_rate,
            acceptance_rate=summary.acceptance_rate,
            responded_count=summary.responded_count,
            interviewed_count=summary.interviewed_count,
            offer_count=summary.offer_count,
            accepted_count=summary.accepted_count,
            applied_total=summary.applied_total,
        )
    )

    if summary.recent_applications:
        console.print(display.build_summary_table(summary.recent_applications, title="Recent Applications"))

    console.print(
        f"[bold]Follow-ups:[/bold] "
        f"[bold red]{summary.overdue_follow_ups} overdue[/bold red], "
        f"[bold yellow]{summary.due_today_follow_ups} due today[/bold yellow], "
        f"[green]{summary.upcoming_follow_ups} upcoming[/green]"
    )


# --- Follow-ups ------------------------------------------------------------

def handle_follow_ups() -> None:
    """Fetch and display every application with a follow-up date, soonest
    or most overdue first."""
    display.print_section("Follow-ups")

    try:
        with display.loading("Fetching follow-ups..."):
            items = _analytics.get_follow_ups()
    except ServiceError as exc:
        display.print_error(str(exc))
        return

    if not items:
        display.print_info("No applications have a follow-up date set.")
        return

    rows = [(item.application, item.days_until) for item in items]
    console.print(display.build_follow_up_table(rows))


# --- Internal helpers ------------------------------------------------------

def _enum_values(enum_cls: Iterable) -> list[str]:
    """Return the list of allowed string values for an Enum class, used
    to constrain Rich `Prompt.ask(..., choices=...)`."""
    return [member.value for member in enum_cls]


def _application_to_field_defaults(existing: object) -> dict[str, str]:
    """Convert an existing `JobApplication` into the `{field: default_str}`
    shape `_collect_application_fields` expects, so Update can pre-fill
    every prompt with the record's current values."""
    return {
        "company": existing.company,
        "job_title": existing.job_title,
        "application_date": existing.application_date,
        "job_type": existing.job_type.value,
        "work_mode": existing.work_mode.value,
        "status": existing.status.value,
        "priority": existing.priority.value,
        "location": existing.location or "",
        "salary": existing.salary or "",
        "job_url": existing.job_url or "",
        "recruiter": existing.recruiter or "",
        "notes": existing.notes or "",
        "follow_up_date": existing.follow_up_date or "",
        "tags": ", ".join(existing.tags) if existing.tags else "",
        "interview_rounds": str(existing.interview_rounds),
    }


def _diff_fields(existing, **new_values) -> dict:
    """Compare freshly-entered field values against `existing` and return
    only the ones that actually changed, as kwargs ready for
    `ApplicationService.update_application(**changes)`.

    This keeps updates truly partial: a field the user left untouched
    (identical to its current value) is never re-validated or re-sent,
    which also protects older records whose stored value might not pass
    a validation rule added after they were created (e.g. a legacy
    free-text salary).
    """
    enum_fields = {"job_type", "work_mode", "status", "priority"}
    changes: dict = {}
    for field_name, new_value in new_values.items():
        current = getattr(existing, field_name)
        if field_name in enum_fields:
            current_value = current.value
        elif field_name == "tags":
            current_value = ", ".join(current) if current else ""
        elif isinstance(current, int):
            current_value = str(current)
        else:
            current_value = current or ""
        if new_value != current_value:
            changes[field_name] = new_value
    return changes
