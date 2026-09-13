"""
menu.py

Defines the main menu structure and navigation loop for the Job
Application Tracker CLI. Displays the banner and numbered menu via the
shared `app.cli.display` helpers and delegates every selected action to a
handler function in handlers.py.

This module intentionally contains no business logic and never imports
`app.services` or `app.database` directly - it only knows how to render a
menu and call the matching handler.
"""

from __future__ import annotations

from typing import Callable, Optional

from rich.prompt import Prompt

from app.cli import display, handlers
from app.cli.display import console

# Menu option -> (display label, handler to call). `None` marks the exit
# option, which the loop handles directly rather than calling a handler.
_MENU_OPTIONS: dict[str, tuple[str, Optional[Callable[[], None]]]] = {
    "1": ("Add Application", handlers.handle_add_application),
    "2": ("View Applications", handlers.handle_view_all_applications),
    "3": ("Search Applications", handlers.handle_search_applications),
    "4": ("Filter Applications", handlers.handle_filter_applications),
    "5": ("View Application Details", handlers.handle_view_application_by_id),
    "6": ("Update Application", handlers.handle_update_application),
    "7": ("Delete Application", handlers.handle_delete_application),
    "8": ("Dashboard", handlers.handle_dashboard),
    "9": ("Follow-ups", handlers.handle_follow_ups),
    "10": ("Exit", None),
}

_EXIT_CHOICE = "10"


def show_welcome_screen() -> None:
    """Display the application's banner when the program starts."""
    display.print_header()


def _show_menu() -> None:
    """Print the numbered list of available menu options."""
    console.print()
    console.rule(style="cyan")
    for key, (label, _) in _MENU_OPTIONS.items():
        console.print(f"  [bold cyan]{key:>2}.[/bold cyan] {label}")
    console.rule(style="cyan")


def run() -> None:
    """Run the main menu loop until the user chooses to exit.

    Repeatedly displays the menu, reads a valid choice, and calls the
    corresponding handler. An invalid choice (anything outside 1-10) is
    never accepted in the first place - Rich re-prompts automatically -
    so the loop can never dispatch to a nonexistent action. Loops
    indefinitely until "Exit" is selected.
    """
    show_welcome_screen()

    while True:
        _show_menu()
        choice = Prompt.ask(
            "Select an option",
            choices=list(_MENU_OPTIONS.keys()),
            default=_EXIT_CHOICE,
            show_choices=False,
        )
        label, action = _MENU_OPTIONS[choice]

        if action is None:
            console.print("\n[cyan]Goodbye! Good luck with your applications.[/cyan]\n")
            break

        action()
