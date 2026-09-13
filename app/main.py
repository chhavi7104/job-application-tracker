"""
main.py

Application entry point. Configures logging, initializes the CLI, and
handles top-level exceptions so the application always exits cleanly with
a helpful message rather than an unhandled traceback.

Run with:
    python -m app.main
"""

import sys

from app import __app_name__, __version__
from app.cli import menu
from app.database.connection import initialize_database
from app.database.exceptions import DatabaseError
from app.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> int:
    """Run the application.

    Returns:
        Process exit code (0 on success, 1 on unhandled/startup error).
    """
    logger.info("Starting %s v%s", __app_name__, __version__)

    try:
        initialize_database()
    except DatabaseError:
        logger.exception("Failed to initialize the database.")
        print("Could not initialize the database. Check logs/app.log for details.")
        return 1

    try:
        menu.run()
    except KeyboardInterrupt:
        logger.warning("Application interrupted by user (KeyboardInterrupt).")
        print("\nExiting. Goodbye!")
        return 0
    except Exception:
        # Catch-all so the user never sees a raw traceback; the full
        # details are always available in logs/app.log for debugging.
        logger.exception("Unhandled exception occurred.")
        print("An unexpected error occurred. Check logs/app.log for details.")
        return 1

    logger.info("Application exited normally.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
