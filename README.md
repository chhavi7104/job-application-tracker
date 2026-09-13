# Job Application Tracker

A professional, menu-driven command-line application for tracking job
applications — companies, roles, statuses, and progress — built with a
clean, layered architecture and persistent SQLite storage.

> **Status:** 🚧 Under active development. This README reflects the
> current phase of the project (see [Development Status](#development-status)).

## Overview

Job hunting means juggling dozens of applications across companies,
stages, and deadlines. **Job Application Tracker** is a terminal-based
tool for logging, searching, updating, and analyzing job applications
without needing a spreadsheet or web app.

The project is intentionally built the way a real production CLI tool
would be, rather than a single-file script:

- Clear separation of concerns (CLI → Services → Repository → Database)
- Persistent storage via SQLite (no data loss between runs)
- Input validation and robust exception handling
- Structured application logging for debugging and auditing
- Automated tests with `pytest`
- A polished terminal UI powered by [Rich](https://github.com/Textualize/rich)

## Architecture

The application follows a strict layered architecture:

```
CLI / UI  --->  Services (business logic)  --->  Repository  --->  SQLite
(app/cli)        (app/services)                  (app/database)
```

- **`app/cli`** — Menus and handlers. Renders output and collects input;
  never talks to the database directly.
- **`app/models`** — Plain data classes representing domain entities
  (e.g. a job application record).
- **`app/services`** — Business logic and orchestration. The only layer
  the CLI is allowed to call.
- **`app/database`** — Connection management and the repository
  (data-access) layer. Isolates all SQL from the rest of the app.
- **`app/validators`** — Reusable input validation functions.
- **`app/utils`** — Cross-cutting utilities, such as logging setup.

This separation keeps each layer independently testable and makes it
straightforward to, for example, swap SQLite for another backend later
without touching the CLI or business logic.

## Project Structure

```
job-application-tracker/
├── app/
│   ├── main.py                    # Application entry point
│   ├── cli/                       # Presentation layer (Rich-based menus)
│   │   ├── menu.py                #   Banner + 10-option navigation loop
│   │   ├── handlers.py            #   One function per menu action
│   │   └── display.py             #   Reusable Rich helpers (tables, badges, messages)
│   ├── models/                    # Domain entities
│   ├── services/                  # Business logic
│   │   ├── application_service.py #   Validated CRUD + search
│   │   ├── analytics_service.py   #   Dashboard stats + follow-up reminders
│   │   └── exceptions.py          #   Service-layer exception types
│   ├── database/                  # Connection + repository (data access)
│   ├── validators/                # Input validation
│   └── utils/                     # Logging and shared helpers
├── tests/                         # pytest test suite
├── data/                          # SQLite database file lives here (gitignored)
├── logs/                          # Application log files (gitignored)
├── requirements.txt
├── .gitignore
├── LICENSE
└── README.md
```

## Tech Stack

| Concern             | Choice                     |
|---------------------|-----------------------------|
| Language             | Python 3.11+                |
| Storage              | SQLite                      |
| Terminal UI          | [Rich](https://github.com/Textualize/rich) |
| Testing              | pytest                      |
| Logging              | Python standard `logging`   |
| Version control      | Git / GitHub                |

## Getting Started

### Prerequisites

- Python 3.11 or newer
- Git

### Setup

```bash
# Clone the repository
git clone https://github.com/chhavi7104/job-application-tracker.git
cd job-application-tracker

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application

```bash
python -m app.main
```

### Running Tests

```bash
pytest
```

Every test runs against an isolated, throwaway SQLite database created
under pytest's own `tmp_path` (see `tests/conftest.py`) - the suite never
reads or writes the real `data/job_applications.db`.

## Planned Features

- [x] **Add** a new job application (company, role, status, date applied, notes)
- [x] **View** all applications in a formatted, sortable table
- [x] **View** a single application by ID
- [x] **Update** an existing application's details or status (partial-field updates)
- [x] **Delete** an application record (with confirmation)
- [x] **Search / filter** applications by company, job title, location, status, recruiter, tags, job type, work mode, priority, and date range (combinable)
- [x] **Input validation** for all user-entered data
- [x] **Persistent storage** in SQLite (survives restarts, with in-place schema migrations)
- [x] **Application logs** written to `logs/app.log` for debugging/auditing
- [x] **Analytics dashboard** (totals, breakdown by status/job type/work mode/priority, top companies, recent applications, response/interview/offer/acceptance rates)
- [x] **Follow-up tracking** (overdue / due today / upcoming, on the dashboard and a dedicated view)
- [x] **Tags** (simple comma-separated tags, searchable)
- [x] **Interview-round tracking** (count of rounds completed per application)
- [x] **Automated tests** covering validators, services, and the repository layer (154 tests, isolated temp database)
- [x] Packaged **GitHub Release** with versioned tag

## Development Status

This project is being built in phases:

- **Phase 1 — Project Scaffold (complete):** Directory structure, module
  stubs, logging infrastructure, dependency setup, and a runnable
  entry point.
- **Phase 2 — Database & Data Model (complete):** `JobApplication` domain
  model, SQLite schema with constraints, connection management, and a
  repository (data access) layer with full CRUD + search.
- **Phase 3 — Complete CRUD (complete):** Full menu-driven Create, Read
  (all + by ID), Update (partial-field, pre-filled prompts), and Delete
  (with confirmation) wired through `ApplicationService`. Input
  validation, duplicate-application prevention, and translated,
  CLI-friendly error messages for every failure mode.
- **Phase 4 — Search, Filtering & Validation (complete):** Keyword search
  across company/job title/location/status/recruiter; combinable filters
  by status, job type, work mode, priority, company, location, and
  application-date range; centralized, named validators (salary, email,
  date range, and per-field enum wrappers); every CLI entry point can
  recover from invalid input (retry loop) instead of crashing or bouncing
  back to the main menu.
- **Phase 5 — Professional CLI Interface (complete):** Centered banner and
  a 10-option menu (Add, View, Search, Filter, View Details, Update,
  Delete, Dashboard, Follow-ups, Exit); a reusable `app/cli/display.py`
  helper module (headers, section rules, colored status/priority
  indicators, success/error/warning messages, loading spinners, table
  builders) shared by every handler so styling is consistent everywhere;
  invalid menu choices are rejected and re-prompted automatically, never
  dispatched.
- **Phase 6 — Dashboard, Analytics & Productivity (complete):** Full
  analytics dashboard - all 8 statuses (zero-filled), breakdowns by job
  type/work mode/priority, top 5 companies, 5 most recent applications,
  and 4 hiring-funnel rates (response/interview/offer/acceptance) with
  their raw counts, all computed in `AnalyticsService`. Follow-up
  tracking (overdue/due today/upcoming) shown on both the Dashboard and a
  dedicated Follow-ups view. A simple comma-separated **tags** system and
  **interview-round** tracking added via an in-place schema migration
  (`ALTER TABLE ... ADD COLUMN`, safe on databases from any earlier
  phase); tags are also searchable alongside company/job title/location/
  status/recruiter.
- **Phase 7 — Testing, Error Handling & Code Quality (current):** 154
  `pytest` tests across validators, the repository, `ApplicationService`,
  `AnalyticsService`, and dedicated error-handling scenarios (missing
  records, simulated `sqlite3` failures, invalid input, schema
  migration) - every test runs against an isolated temporary SQLite
  database (see `tests/conftest.py`) and never touches the real
  `data/job_applications.db`. Reduced duplication between the Add/Update
  CLI flows via a shared field-prompting helper (which also fixed a real
  bug: retrying after a validation error used to discard everything
  already typed). Zero `pyflakes` warnings; all lines under 110 chars.
- **Phase 8 (planned):** Final documentation pass and first GitHub Release.

## License

This project is licensed under the [MIT License](LICENSE).
