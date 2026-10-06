"""The alternate design must preserve the default site and research endpoints."""

import json
from http.server import ThreadingHTTPServer
from importlib.resources import files
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest
from test_research_app import A, build, fixture

from upset import research_app as app


def test_design_selection_and_static_files_leave_the_api_unchanged(tmp_path):
    database = tmp_path / "research"
    build(fixture(tmp_path), database)
    path = database / "upset.sqlite"
    servers = [ThreadingHTTPServer(("127.0.0.1", 0), app.handler(path, design))
               for design in ("broadcast", "editorial")]
    threads = [Thread(target=server.serve_forever, daemon=True) for server in servers]
    for thread in threads:
        thread.start()
    bases = [f"http://127.0.0.1:{server.server_address[1]}" for server in servers]
    try:
        with urlopen(bases[0]) as response:
            assert response.read() == files("upset").joinpath("web/research.html").read_bytes()
        with urlopen(bases[1]) as response:
            body = response.read().decode()
            assert '/web/research_editorial.css' in body
            assert '/web/research_editorial.js' in body
        for name, mime in app.WEB_FILES.items():
            with urlopen(bases[1] + "/web/" + name) as response:
                assert response.headers["Content-Type"] == mime
                assert response.read() == files("upset").joinpath("web/" + name).read_bytes()
        for target in ("/web/research_app.py", "/web/../research_app.py",
                       "/web/%2e%2e/research_app.py", "/web/unknown.js"):
            with pytest.raises(HTTPError) as error:
                urlopen(bases[1] + target)
            assert error.value.code == 404
        for endpoint in ("/api/meta", "/api/fighters?q=Alpha",
                         f"/api/fighter?id={A}&before=2020-06-01&window=0"):
            responses = []
            for base in bases:
                with urlopen(base + endpoint) as response:
                    responses.append(json.loads(response.read()))
            assert responses[0] == responses[1]
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)
