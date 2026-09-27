import socket

import pytest

from gazemap.capture import VIEWPORTS, CaptureError, PageSession


def test_desktop_capture_matches_viewport_and_finds_element_at_point(fixture_server):
    with PageSession(f"{fixture_server}/button.html", VIEWPORTS["desktop"]) as session:
        capture = session.capture
        assert capture.image.shape == (900, 1440, 3)
        assert capture.status == 200
        # button spans x 360..600, y 315..395 in a 1440x900 viewport
        element = session.element_at(480, 355)
        assert element.tag == "button"
        assert element.selector == "#cta"
        assert element.text == "Get started"
        # plain background maps to the document itself, not the button
        assert session.element_at(1300, 850).tag in ("html", "body")


def test_mobile_capture_uses_mobile_viewport(fixture_server):
    with PageSession(f"{fixture_server}/button.html", VIEWPORTS["mobile"]) as session:
        assert session.capture.image.shape == (844, 390, 3)


def test_hide_removes_matching_elements_before_screenshot(fixture_server):
    url = f"{fixture_server}/button.html"
    with PageSession(url, VIEWPORTS["desktop"], hide=["#cta"]) as session:
        assert session.element_at(480, 355).tag in ("html", "body")
        assert session.capture.image[355, 480].tolist() == [255, 255, 255]


def test_unreachable_host_raises_clear_error():
    with pytest.raises(CaptureError, match="resolve"):
        with PageSession("http://nonexistent.invalid/", VIEWPORTS["desktop"], timeout_ms=10000):
            pass


def test_connection_refused_raises_clear_error():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
    with pytest.raises(CaptureError, match="refused"):
        with PageSession(f"http://127.0.0.1:{closed_port}/", VIEWPORTS["desktop"], timeout_ms=10000):
            pass


def test_http_error_is_captured_with_status(fixture_server):
    with PageSession(f"{fixture_server}/missing.html", VIEWPORTS["desktop"]) as session:
        assert session.capture.status == 404
        assert session.capture.image.shape == (900, 1440, 3)


def test_full_page_capture_covers_the_document_in_viewport_windows(fixture_server):
    with PageSession(f"{fixture_server}/long.html", VIEWPORTS["desktop"], full_page=True) as session:
        capture = session.capture
        assert capture.image.shape == (3000, 1440, 3)
        assert capture.page_height == 3000
        # windows are one viewport tall, the last one aligned to the page bottom
        assert [w.scroll_y for w in capture.windows] == [0, 900, 1800, 2100]
        assert all(w.image.shape == (900, 1440, 3) for w in capture.windows)
        # the deep button spans x 360..600, y 2300..2380 in page coordinates (sample off its label)
        assert capture.image[2310, 380].tolist() == [225, 29, 72]
        element = session.element_at(480, 2340)
        assert element.tag == "button"
        assert element.selector == "#deep"
        # a point in the first screen is looked up without scrolling
        assert session.element_at(700, 100).tag in ("html", "body", "section")


def test_full_page_capture_is_capped_by_max_screens(fixture_server):
    with PageSession(f"{fixture_server}/long.html", VIEWPORTS["desktop"], full_page=True, max_screens=2) as session:
        capture = session.capture
        assert capture.image.shape == (1800, 1440, 3)
        assert [w.scroll_y for w in capture.windows] == [0, 900]
        assert any("2 screens" in w for w in capture.warnings)


def test_above_the_fold_capture_reports_a_single_window(fixture_server):
    with PageSession(f"{fixture_server}/long.html", VIEWPORTS["desktop"]) as session:
        capture = session.capture
        assert capture.image.shape == (900, 1440, 3)
        assert capture.page_height == 3000
        assert [w.scroll_y for w in capture.windows] == [0]
