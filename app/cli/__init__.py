"""
CLI package.

Contains the presentation layer of the application: everything responsible
for displaying menus, collecting user input, and rendering output to the
terminal (via Rich). This layer talks only to the services layer and must
never access the database or repository directly.

    menu.py     - banner + numbered menu loop, dispatches to handlers.py.
    handlers.py - one function per menu action: collects input, calls a
                  service, renders the result.
    display.py  - reusable Rich display helpers (headers, status/priority
                  badges, message styles, table builders) shared by
                  menu.py and handlers.py, so styling stays consistent
                  and handlers stay focused on flow rather than formatting.
"""
