"""
logger.py

Centralized logging configuration for the application.

Provides `get_logger(name)`, which returns a module-level logger writing
to a rotating log file under logs/app.log as well as (at WARNING+) to the
console. All other modules should obtain their logger via this function
rather than configuring `logging` themselves, so the whole application
shares one consistent logging setup.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Directory that holds log files, relative to the project root.
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure_root_logger() -> None:
    """Configure the root 'job_application_tracker' logger exactly once.

    Sets up:
        - A rotating file handler (DEBUG and above) writing to logs/app.log.
        - A console (stream) handler (WARNING and above) so the CLI
          output isn't cluttered with routine log messages.
    """
    global _configured
    if _configured:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("job_application_tracker")
    root_logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.propagate = False

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger configured for this application.

    Args:
        name: Typically `__name__` of the calling module, e.g.
            'app.cli.menu'. Used to namespace log messages so their
            origin is clear in logs/app.log.

    Returns:
        A `logging.Logger` instance that writes to logs/app.log (and to
        the console for warnings/errors), sharing a single shared
        configuration across the whole application.
    """
    _configure_root_logger()
    return logging.getLogger(f"job_application_tracker.{name}")
