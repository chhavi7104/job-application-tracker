"""
Database package.

Contains the data-access layer of the application:
    connection.py  - manages the SQLite connection lifecycle and creates
                      the schema (applications table + indexes) if it
                      does not already exist.
    repository.py  - implements the repository pattern (`ApplicationRepository`)
                      for CRUD and search operations, isolating all SQL
                      from the rest of the application.
    exceptions.py  - database-layer exception types (`DatabaseError` and
                      subclasses) that callers outside this package use to
                      handle failures without depending on `sqlite3`.

Only the services layer is permitted to interact with this package; the
CLI layer must never import from app.database directly.
"""
