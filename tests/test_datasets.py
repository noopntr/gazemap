import functools
import http.server
import io
import os
import threading
import zipfile

import pytest
from PIL import Image

from gazemap.datasets import download_ueyes, load_ueyes


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    """Static handler with just enough Range support for zipfile seeking."""

    def log_message(self, *args):
        pass

    def send_head(self):
        path = self.translate_path(self.path)
        if not os.path.isfile(path) or "Range" not in self.headers:
            return super().send_head()
        size = os.path.getsize(path)
        start, end = self.headers["Range"].removeprefix("bytes=").split("-")
        start, end = int(start), min(int(end or size - 1), size - 1)
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        return io.BytesIO(f.read(end - start + 1))


def png_bytes(color, size=(20, 10)):
    buf = io.BytesIO()
    Image.new("L" if isinstance(color, int) else "RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def fake_ueyes(tmp_path):
    root = tmp_path / "srv"
    root.mkdir()
    with zipfile.ZipFile(root / "ueyes.zip", "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("UEyes_dataset/image_types.csv", "Image Name;Category;Block;Train/Test\na1.png;web;0;Test\nb2.jpg;mobile;0;Train\nc3.png;poster;1;Test\nd4.png;desktop;1;Test\n")
        for name in ("a1.png", "b2.jpg", "c3.png", "d4.png"):
            z.writestr(f"UEyes_dataset/images/{name}", png_bytes((200, 30, 30)))
            if name == "d4.png":
                continue  # like two real UEyes images, this one has no maps
            for kind in ("fixmaps", "heatmaps"):
                for duration in (1, 3):
                    # maps keep the image's own extension
                    z.writestr(f"UEyes_dataset/saliency_maps/{kind}_{duration}s/{name}", png_bytes(255 if kind == "fixmaps" else 128))
        z.writestr("UEyes_dataset/scanpaths/paths_3s/a1/1.png", b"not needed" * 1000)
    handler = functools.partial(RangeHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/ueyes.zip"
    server.shutdown()


def test_download_fetches_only_the_requested_split_and_duration(fake_ueyes, tmp_path):
    dest = tmp_path / "ueyes"
    fetched = download_ueyes(dest, split="test", duration=3, url=fake_ueyes)
    assert fetched == 7  # index + 2 complete test images x (image, fixmap, heatmap); d4 has no maps
    assert (dest / "image_types.csv").exists()
    assert (dest / "unscored.txt").read_text().split() == ["d4.png"]
    assert sorted(p.name for p in (dest / "images").iterdir()) == ["a1.png", "c3.png"]
    assert sorted(p.name for p in (dest / "heatmaps_3s").iterdir()) == ["a1.png", "c3.png"]
    assert sorted(p.name for p in (dest / "fixmaps_3s").iterdir()) == ["a1.png", "c3.png"]
    assert not (dest / "fixmaps_1s").exists()
    assert not (dest / "scanpaths").exists()
    # a second call finds everything on disk and fetches nothing
    assert download_ueyes(dest, split="test", duration=3, url=fake_ueyes) == 0


def test_load_lists_samples_with_category_and_paths(fake_ueyes, tmp_path):
    dest = tmp_path / "ueyes"
    download_ueyes(dest, split="all", duration=3, url=fake_ueyes)
    samples = load_ueyes(dest, split="all", duration=3)
    # d4 has no human maps and is skipped, not reported as incomplete
    assert [(s.name, s.category) for s in samples] == [("a1.png", "web"), ("b2.jpg", "mobile"), ("c3.png", "poster")]
    assert samples[1].fixmap.name == "b2.jpg"
    assert all(s.image.exists() and s.fixmap.exists() and s.heatmap.exists() for s in samples)
    assert [s.name for s in load_ueyes(dest, split="test", duration=3)] == ["a1.png", "c3.png"]


def test_load_reports_missing_data_clearly(tmp_path):
    with pytest.raises(FileNotFoundError, match="--download"):
        load_ueyes(tmp_path / "nothing", split="test", duration=3)


def test_range_reads_retry_after_a_dropped_response(fake_ueyes, tmp_path, monkeypatch):
    import http.client
    import urllib.request

    from gazemap import datasets

    real_urlopen = urllib.request.urlopen
    failures = {"left": 2}

    def flaky(req, *args, **kwargs):
        if isinstance(req, urllib.request.Request) and req.get_header("Range") and failures["left"]:
            failures["left"] -= 1
            raise http.client.IncompleteRead(b"partial", 10)
        return real_urlopen(req, *args, **kwargs)

    monkeypatch.setattr(datasets.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(datasets, "RETRY_DELAY", 0)
    assert download_ueyes(tmp_path / "ueyes", split="test", duration=3, url=fake_ueyes) == 7
    assert failures["left"] == 0


def test_download_can_skip_images_when_only_fixations_are_needed(fake_ueyes, tmp_path):
    dest = tmp_path / "ueyes"
    fetched = download_ueyes(dest, split="train", duration=3, url=fake_ueyes, kinds=("fixmaps",))
    assert fetched == 2  # index + one train fixation map
    assert not (dest / "images").exists()
    assert [p.name for p in (dest / "fixmaps_3s").iterdir()] == ["b2.jpg"]


def test_downloaded_files_match_the_archive_byte_for_byte(fake_ueyes, tmp_path):
    dest = tmp_path / "ueyes"
    download_ueyes(dest, split="all", duration=3, url=fake_ueyes, workers=4)
    archive = zipfile.ZipFile(tmp_path / "srv" / "ueyes.zip")
    for name in ("a1.png", "b2.jpg", "c3.png"):
        assert (dest / "images" / name).read_bytes() == archive.read(f"UEyes_dataset/images/{name}")
        assert (dest / "heatmaps_3s" / name).read_bytes() == archive.read(f"UEyes_dataset/saliency_maps/heatmaps_3s/{name}")


def test_rate_limited_requests_wait_and_retry(fake_ueyes, tmp_path, monkeypatch):
    import email.message
    import urllib.error
    import urllib.request

    from gazemap import datasets

    real_urlopen = urllib.request.urlopen
    state = {"limited": 1, "slept": []}

    def limited(req, *args, **kwargs):
        if isinstance(req, urllib.request.Request) and req.get_header("Range") and state["limited"]:
            state["limited"] -= 1
            headers = email.message.Message()
            headers["Retry-After"] = "3"
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", headers, None)
        return real_urlopen(req, *args, **kwargs)

    monkeypatch.setattr(datasets.urllib.request, "urlopen", limited)
    monkeypatch.setattr(datasets.time, "sleep", lambda s: state["slept"].append(s))
    assert download_ueyes(tmp_path / "ueyes", split="test", duration=3, url=fake_ueyes) == 7
    assert state["slept"] == [3.0]


def test_other_http_errors_are_not_retried(fake_ueyes, tmp_path, monkeypatch):
    import urllib.error
    import urllib.request

    from gazemap import datasets

    real_urlopen = urllib.request.urlopen

    def forbidden(req, *args, **kwargs):
        if isinstance(req, urllib.request.Request) and req.get_header("Range"):
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
        return real_urlopen(req, *args, **kwargs)

    monkeypatch.setattr(datasets.urllib.request, "urlopen", forbidden)
    with pytest.raises(urllib.error.HTTPError):
        download_ueyes(tmp_path / "ueyes", split="test", duration=3, url=fake_ueyes)


def test_requests_are_spaced_to_stay_under_the_rate_limit(monkeypatch):
    from gazemap import datasets

    clock = {"now": 100.0}
    slept = []
    monkeypatch.setattr(datasets.time, "monotonic", lambda: clock["now"])

    def fake_sleep(seconds):
        slept.append(round(seconds, 3))
        clock["now"] += seconds

    monkeypatch.setattr(datasets.time, "sleep", fake_sleep)
    monkeypatch.setattr(datasets, "MIN_INTERVAL", 0.5)
    monkeypatch.setattr(datasets, "_last_request", [0.0])
    for _ in range(3):
        datasets._throttle()
    assert slept == [0.5, 0.5]  # the first request goes at once, later ones wait their turn
