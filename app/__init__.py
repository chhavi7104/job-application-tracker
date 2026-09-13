"""
Job Application Tracker
========================

A professional, menu-driven command-line application for tracking job
applications, built with a clean layered architecture:

    CLI / UI  ->  Services (business logic)  ->  Repository (data access)  ->  SQLite

Package layout:
    app.cli         - Terminal user interface (menus, input/output handlers)
    app.models      - Data classes / domain entities
    app.services    - Business logic and orchestration
    app.database    - Database connection management and repository (data access) layer
    app.validators  - Input validation utilities
    app.utils       - Cross-cutting utilities (logging, helpers)

This package intentionally contains no business logic itself; it only
exposes the sub-packages above.
"""

__app_name__ = "Job Application Tracker"
__version__ = "0.1.0"
