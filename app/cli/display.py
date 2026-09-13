"""
display.py

Reusable Rich-based display helpers shared by menu.py and handlers.py:
headers/section titles, status/priority "badges" with consistent colors,
success/error/warning/info message helpers, a loading-spinner wrapper,
and table builders for the application list/detail/dashboard/follow-up
views.

This module is purely presentational - it renders `JobApplication`
objects and plain data it is handed, and never calls a service or the
database itself. Centralizing this here (rather than duplicating table
and message styling across every handler) is what keeps handlers.py
short and keeps the "look" of the CLI consistent everywhere.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app import __app_name__, __version__
from app.models.application import JobApplication, Priority, Status

# A single shared Console instance, imported by menu.py and handlers.py,
# so every part of the CLI renders through the same configured console.
console = Console()

# --- Status / priority indicators -----------------------------------------
#
# A compact glyph + a Rich color per value, used everywhere a status or
# priority is shown (tables, detail views, dashboard). Plain single-width
# glyphs (not emoji) keep table column widths predictable across terminals.

_STATUS_STYLE: dict[str, tuple[str, str]] = {
    Status.SAVED.value: ("o", "grey58"),
    Status.APPLIED.value: (">", "cyan"),
    Status.ASSESSMENT.value: ("#", "yellow"),
    Status.INTERVIEW.value: ("~", "blue"),
    Status.OFFER.value: ("*", "green"),
    Status.REJECTED.value: ("x", "red"),
    Status.WITHDRAWN.value: ("<", "grey50"),
    Status.ACCEPTED.value: ("v", "bold green"),
}

_PRIORITY_STYLE: dict[str, str] = {
    Priority.LOW.value: "grey58",
    Priority.MEDIUM.value: "yellow",
    Priority.HIGH.value: "bold red",
}


def status_text(status_value: str) -> Text:
    """Return a colored, glyph-prefixed `Text` for a status value, e.g.
    "~ Interview" in blue."""
    glyph, style = _STATUS_STYLE.get(status_value, ("?", "white"))
    return Text(f"{glyph} {status_value}", style=style)


def priority_text(priority_value: str) -> Text:
    """Return a colored `Text` for a priority value, e.g. "High" in bold red."""
    style = _PRIORITY_STYLE.get(priority_value, "white")
    return Text(priority_value, style=style)


# --- Headers / sections / messages -----------------------------------------

def print_header() -> None:
    """Print the application's main banner (shown once, on startup)."""
    content = Text(justify="center")
    content.append(__app_name__.upper(), style="bold white")
    content.append("\n")
    content.append(
        f"v{__version__}  \u2022  Track and manage your job applications", style="dim"
    )
    console.print(Panel(content, box=box.DOUBLE, border_style="cyan", padding=(1, 2)))


def print_section(title: str) -> None:
    """Print a styled section header before a multi-step flow (Add,
    Update, Search, Filter, ...)."""
    console.print()
    console.rule(f"[bold cyan]{title}[/bold cyan]", style="cyan")


def print_success(message: str) -> None:
    """Print a green, checkmark-prefixed success message."""
    console.print(f"[bold green]\u2713 {message}[/bold green]")


def print_error(message: str) -> None:
    """Print a red, cross-prefixed error message."""
    console.print(f"[bold red]\u2717 {message}[/bold red]")


def print_warning(message: str) -> None:
    """Print a yellow, warning-prefixed message."""
    console.print(f"[bold yellow]! {message}[/bold yellow]")


def print_info(message: str) -> None:
    """Print a dim, informational message."""
    console.print(f"[dim]{message}[/dim]")


@contextmanager
def loading(message: str) -> Iterator[None]:
    """Show a brief Rich spinner while a block of code runs, e.g.:

        with loading("Fetching applications..."):
            applications = service.list_applications()

    Even though local SQLite reads are near-instant, this gives the CLI a
    consistent "working..." affordance for every data-fetching action
    instead of the screen appearing to hang.
    """
    with console.status(f"[cyan]{message}[/cyan]", spinner="dots"):
        yield


# --- Tables -----------------------------------------------------------------

def build_summary_table(applications: list[JobApplication], title: str = "Job Applications") -> Table:
    """Build a Rich table summarizing multiple applications, one row each."""
    table = Table(title=title, box=box.SIMPLE_HEAVY, header_style="bold cyan", title_style="bold white")
    table.add_column("ID", justify="right", style="bold")
    table.add_column("Company")
    table.add_column("Job Title")
    table.add_column("Status")
    table.add_column("Priority")
    table.add_column("Applied On")
    table.add_column("Work Mode")

    for application in applications:
        table.add_row(
            str(application.id),
            application.company,
            application.job_title,
            status_text(application.status.value),
            priority_text(application.priority.value),
            application.application_date,
            application.work_mode.value,
        )
    return table


def build_detail_table(application: JobApplication) -> Table:
    """Build a Rich key/value table showing every field of one application."""
    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
    table.add_column("Field", style="bold cyan", no_wrap=True)
    table.add_column("Value")

    rows: list[tuple[str, object]] = [
        ("ID", str(application.id)),
        ("Company", application.company),
        ("Job Title", application.job_title),
        ("Location", application.location or "-"),
        ("Job Type", application.job_type.value),
        ("Work Mode", application.work_mode.value),
        ("Application Date", application.application_date),
        ("Status", status_text(application.status.value)),
        ("Priority", priority_text(application.priority.value)),
        ("Salary", application.salary or "-"),
        ("Job URL", application.job_url or "-"),
        ("Recruiter", application.recruiter or "-"),
        ("Notes", application.notes or "-"),
        ("Follow-up Date", application.follow_up_date or "-"),
        ("Tags", ", ".join(application.tags) if application.tags else "-"),
        ("Interview Rounds", str(application.interview_rounds)),
        ("Created At", application.created_at or "-"),
        ("Updated At", application.updated_at or "-"),
    ]
    for field_name, value in rows:
        table.add_row(field_name, value)
    return table


def build_counts_table(title: str, counts: dict[str, int], kind: str = "plain") -> Table:
    """Build a small two-column table of value -> count (used for the
    Dashboard's status/job type/work mode/priority breakdowns).

    Args:
        title: Table title.
        counts: `{value: count}`, in the order it should be displayed
            (callers pass an already zero-filled, pipeline-ordered dict
            from `AnalyticsService`, so this never re-sorts it).
        kind: `"status"` or `"priority"` renders the value as its colored
            badge; anything else renders it as plain text.
    """
    table = Table(title=title, box=box.SIMPLE, header_style="bold cyan", title_style="bold white")
    table.add_column("Value")
    table.add_column("Count", justify="right")

    for value, count in counts.items():
        if kind == "status":
            label = status_text(value)
        elif kind == "priority":
            label = priority_text(value)
        else:
            label = value
        table.add_row(label, str(count))
    if not counts:
        table.add_row("[dim]No data yet[/dim]", "0")
    return table


def build_company_table(by_company: list[tuple[str, int]]) -> Table:
    """Build a table of the top companies by application count."""
    table = Table(
        title="Top Companies", box=box.SIMPLE, header_style="bold cyan", title_style="bold white"
    )
    table.add_column("Company")
    table.add_column("Applications", justify="right")

    for company, count in by_company:
        table.add_row(company, str(count))
    if not by_company:
        table.add_row("[dim]No data yet[/dim]", "0")
    return table


def build_metrics_panel(
    response_rate: float,
    interview_rate: float,
    offer_rate: float,
    acceptance_rate: float,
    responded_count: int,
    interviewed_count: int,
    offer_count: int,
    accepted_count: int,
    applied_total: int,
) -> Panel:
    """Build a Panel showing the four hiring-funnel conversion rates,
    each paired with its raw counts and color-coded (green/yellow/red) so
    the dashboard is scannable at a glance."""
    lines = [
        _metric_line("Response rate", response_rate, responded_count, applied_total, "applied"),
        _metric_line("Interview rate", interview_rate, interviewed_count, applied_total, "applied"),
        _metric_line("Offer rate", offer_rate, offer_count, applied_total, "applied"),
        _metric_line("Acceptance rate", acceptance_rate, accepted_count, offer_count, "offers"),
    ]
    return Panel("\n".join(lines), title="Funnel Metrics", border_style="cyan", title_align="left")


def _metric_line(label: str, rate: float, numerator: int, denominator: int, unit: str) -> str:
    """Format one color-coded "Label: NN.N%  (n / d unit)" line for the
    metrics panel. Thresholds (>=50 green, >=20 yellow, else red) are an
    arbitrary but reasonable "traffic light" cue, not an industry
    standard - they only affect color, never the underlying number."""
    color = "green" if rate >= 50 else "yellow" if rate >= 20 else "red"
    return f"[bold]{label}:[/bold] [{color}]{rate:.1f}%[/{color}]  ({numerator}/{denominator} {unit})"


def build_follow_up_table(rows: list[tuple[JobApplication, int]]) -> Table:
    """Build a table of applications with an upcoming/overdue follow-up
    date. `rows` is a list of (application, days_until) pairs, where a
    negative `days_until` means overdue."""
    table = Table(
        title="Follow-ups", box=box.SIMPLE_HEAVY, header_style="bold cyan", title_style="bold white"
    )
    table.add_column("ID", justify="right", style="bold")
    table.add_column("Company")
    table.add_column("Job Title")
    table.add_column("Follow-up Date")
    table.add_column("When")
    table.add_column("Status")

    for application, days_until in rows:
        when = _follow_up_when_text(days_until)
        table.add_row(
            str(application.id),
            application.company,
            application.job_title,
            application.follow_up_date or "-",
            when,
            status_text(application.status.value),
        )
    return table


def _follow_up_when_text(days_until: int) -> Text:
    """Render a `days_until` value as a colored human-readable label."""
    if days_until < 0:
        n = abs(days_until)
        return Text(f"Overdue by {n} day{'s' if n != 1 else ''}", style="bold red")
    if days_until == 0:
        return Text("Due today", style="bold yellow")
    return Text(f"In {days_until} day{'s' if days_until != 1 else ''}", style="green")
