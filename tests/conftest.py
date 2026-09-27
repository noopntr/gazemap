import functools
import http.server
import pathlib
import threading

import pytest
from playwright.sync_api import sync_playwright

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def fixture_server():
    """Serve tests/fixtures over HTTP on a random local port."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(FIXTURES))
    handler.log_message = lambda *args, **kwargs: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="session")
def resume_pdf(fixture_server, tmp_path_factory):
    path = tmp_path_factory.mktemp("docs") / "resume.pdf"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{fixture_server}/resume.html")
        page.pdf(path=str(path), format="A4", print_background=True)
        browser.close()
    return path
