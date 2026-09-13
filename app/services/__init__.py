"""
Services package.

Contains the business logic layer of the application. Services orchestrate
operations between the CLI layer and the repository/database layer,
enforce business rules, and are the only layer the CLI is allowed to call
into directly.

    application_service.py  - ApplicationService: validated CRUD + search
                               for job applications.
    analytics_service.py    - AnalyticsService: dashboard summary
                               statistics and follow-up reminders.
    exceptions.py            - Service-layer exception types
                               (ApplicationNotFoundError, DuplicateApplicationError,
                               ServiceError) used to translate database
                               failures into CLI-friendly errors.
"""
