# Files for an interface collaborator

For design, layout, wording and client-side interface changes, send
`src/upset/web/research.html` and screenshots of the running viewer. The HTML,
CSS and browser JavaScript are together in that file. Send a short description
of desired changes and request that API paths/response fields remain compatible.
Opening the HTML alone does not supply its search or fighter API responses.

For API/calculation review, include `src/upset/research_app.py` and relevant
tests. The database builder is useful for ingestion/schema review, but is not
required to redesign the page.

To run a complete working copy on another computer, supply the repository's
Python source package and `pyproject.toml`, plus the chosen built database folder
containing `upset.sqlite` and `manifest.json`. Three individual source files
alone are insufficient because the server imports other package modules. With
the project installed, run `python -m upset.research_app --database PATH/upset.sqlite`.
The server verifies the manifest hash and serves the page and API on that
computer at `http://127.0.0.1:8765`. No provider key or API requests are needed.

The loopback URL is local to each computer. Screen sharing or screenshots let
a collaborator review the existing running copy. Reload after saving HTML;
restart the server after Python changes. Design changes do not rebuild the DB.
