import json

import numpy as np
import pytest
from PIL import Image

from gazemap import cli
from gazemap.capture import VIEWPORTS


class FakeModel:
    """Puts attention on the red fixture button if visible, else weakly on the centre."""

    name = "fake"
    device = "cpu"

    def predict(self, image, centerbias="mit1003"):
        height, width = image.shape[:2]
        ys, xs = np.mgrid[0:height, 0:width]
        red = (image[..., 0] > 200) & (image[..., 1] < 60) & (image[..., 2] < 100)
        if red.any():
            cy, cx = np.nonzero(red)[0].mean(), np.nonzero(red)[1].mean()
            sigma = 40.0
        else:
            cy, cx, sigma = height / 2, width / 2, 120.0
        prob = np.exp(-((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * sigma**2))
        return prob / prob.sum()


@pytest.mark.parametrize(
    "url, slug",
    [
        ("https://www.example.com/", "example.com"),
        ("https://example.com/pricing/", "example.com-pricing"),
        ("http://localhost:3000", "localhost-3000"),
        ("http://localhost:3000/app/Settings?tab=1", "localhost-3000-app-settings"),
    ],
)
def test_slugify_url(url, slug):
    assert cli.slugify_url(url) == slug


def test_analyze_page_writes_outputs_and_maps_top_hotspot_to_element(fixture_server, tmp_path):
    url = f"{fixture_server}/button.html"
    record = cli.analyze_page(url, VIEWPORTS["desktop"], FakeModel(), out_dir=tmp_path, top=3)

    out = tmp_path / cli.slugify_url(url) / "desktop"
    assert Image.open(out / "screenshot.png").size == (1440, 900)
    assert Image.open(out / "heatmap.png").size == (1440, 900)
    assert Image.open(out / "overlay.png").size == (1440, 900)
    saved = json.loads((out / "hotspots.json").read_text())
    assert saved == record

    assert record["viewport"] == {"name": "desktop", "width": 1440, "height": 900, "mobile": False}
    assert record["model"] == "fake"
    assert record["centerbias"] == "ueyes"
    assert record["device"] == "cpu"
    assert record["capture"] == {"mode": "above_the_fold", "page_height": 900, "screens": 1, "screen_height": 900}
    assert set(record["runtime_seconds"]) == {"capture", "inference", "total"}
    top = record["hotspots"][0]
    assert top["rank"] == 1
    assert top["element"] == {"tag": "button", "selector": "#cta", "text": "Get started"}
    assert 0 < top["share"] <= 1
    assert set(top["bbox"]) == {"x", "y", "width", "height"}


def test_main_runs_analyze_and_prints_summary(fixture_server, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_model", lambda name, device: FakeModel())
    url = f"{fixture_server}/button.html"
    code = cli.main(
        ["analyze", url, "--viewport", "desktop", "--top", "2", "--out", str(tmp_path), "--report-dir", str(tmp_path / "reports")]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "#cta" in out
    assert "Get started" in out
    assert (tmp_path / cli.slugify_url(url) / "desktop" / "hotspots.json").exists()
    report = tmp_path / "reports" / f"{cli.slugify_url(url)}.html"
    assert report.exists()
    assert "Get started" in report.read_text()
    assert str(report) in out


def test_no_report_flag_skips_the_report(fixture_server, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_model", lambda name, device: FakeModel())
    url = f"{fixture_server}/button.html"
    code = cli.main(["analyze", url, "--out", str(tmp_path), "--report-dir", str(tmp_path / "reports"), "--no-report"])
    assert code == 0
    assert not (tmp_path / "reports").exists()


def test_full_page_analysis_finds_deep_element_and_records_its_screen(fixture_server, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_model", lambda name, device: FakeModel())
    url = f"{fixture_server}/long.html"
    code = cli.main(
        ["analyze", url, "--viewport", "both", "--full-page", "--out", str(tmp_path), "--report-dir", str(tmp_path / "reports")]
    )
    assert code == 0
    record = json.loads((tmp_path / cli.slugify_url(url) / "desktop" / "hotspots.json").read_text())
    assert record["capture"] == {"mode": "full_page", "page_height": 3000, "screens": 4, "screen_height": 900}
    assert Image.open(tmp_path / cli.slugify_url(url) / "desktop" / "overlay.png").size == (1440, 3000)
    top = record["hotspots"][0]
    assert top["element"]["selector"] == "#deep"
    assert top["screen"] == 3
    assert 2300 <= top["center"]["y"] <= 2380
    html = (tmp_path / "reports" / f"{cli.slugify_url(url)}.html").read_text()
    assert "Deep button" in html and "4 screens" in html


def test_main_reports_capture_errors_without_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_model", lambda name, device: FakeModel())
    code = cli.main(["analyze", "http://nonexistent.invalid/", "--out", str(tmp_path), "--timeout", "10000", "--no-report"])
    assert code == 2
    assert "resolve" in capsys.readouterr().err


def test_analyze_accepts_a_pdf_and_reports_the_text_under_each_hotspot(resume_pdf, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_model", lambda name, device: FakeModel())
    code = cli.main(["analyze", str(resume_pdf), "--out", str(tmp_path), "--report-dir", str(tmp_path / "reports")])
    assert code == 0
    out_dir = tmp_path / "resume" / "page-1"
    record = json.loads((out_dir / "hotspots.json").read_text())
    assert record["capture"] == {"mode": "document", "page_height": record["viewport"]["height"], "screens": 1, "screen_height": record["viewport"]["height"]}
    assert record["viewport"]["name"] == "page-1"
    assert record["centerbias"] == "ueyes"
    assert record["http_status"] is None
    assert abs(Image.open(out_dir / "overlay.png").size[0] - 1240) <= 3
    top = record["hotspots"][0]
    assert top["element"]["tag"] == "text"
    assert "JANE EXAMPLE" in top["element"]["text"]
    assert (tmp_path / "reports" / "resume.html").exists()
    assert "JANE EXAMPLE" in capsys.readouterr().out


def test_analyze_accepts_an_image_without_text_layer(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_model", lambda name, device: FakeModel())
    shot = tmp_path / "Landing Page v2.png"
    Image.new("RGB", (800, 500), (255, 255, 255)).save(shot)
    code = cli.main(["analyze", str(shot), "--out", str(tmp_path), "--no-report"])
    assert code == 0
    record = json.loads((tmp_path / "landing-page-v2" / "image" / "hotspots.json").read_text())
    assert record["hotspots"][0]["element"] is None


def test_missing_file_is_a_clear_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_model", lambda name, device: FakeModel())
    code = cli.main(["analyze", str(tmp_path / "nope.pdf"), "--out", str(tmp_path), "--no-report"])
    assert code == 2
    assert "nope.pdf" in capsys.readouterr().err


def test_targets_measure_attention_share_inside_the_element(fixture_server, tmp_path, capsys):
    url = f"{fixture_server}/button.html"
    record = cli.analyze_page(
        url, VIEWPORTS["desktop"], FakeModel(), out_dir=tmp_path, targets=["#cta", "#missing"]
    )
    found, missing = record["targets"]
    assert found["selector"] == "#cta"
    assert found["found"] is True
    assert found["bbox"] == {"x": 360, "y": 315, "width": 240, "height": 80}
    # a gaussian with sigma 40 centred on the button keeps roughly two thirds of its mass inside
    assert 0.55 < found["share"] < 0.8
    assert found["hotspots"] == [1]
    assert missing == {"selector": "#missing", "found": False, "bbox": None, "share": None, "hotspots": []}
    assert any("#missing" in w for w in record["warnings"])
    cli.print_summary(record)
    out = capsys.readouterr().out
    assert "target #cta:" in out and "% of attention" in out and "hotspot 1 inside" in out
    assert "target #missing: not found" in out


def test_main_passes_repeated_target_flags(fixture_server, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_model", lambda name, device: FakeModel())
    url = f"{fixture_server}/button.html"
    code = cli.main(["analyze", url, "--target", "#cta", "--target", "body", "--out", str(tmp_path), "--no-report"])
    assert code == 0
    record = json.loads((tmp_path / cli.slugify_url(url) / "desktop" / "hotspots.json").read_text())
    assert [t["selector"] for t in record["targets"]] == ["#cta", "body"]


def test_ueyes_is_a_valid_centerbias_choice():
    args = cli.build_parser().parse_args(["analyze", "https://example.com", "--centerbias", "ueyes"])
    assert args.centerbias == "ueyes"


def test_css_flag_reads_files_and_records_them(fixture_server, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_model", lambda name, device: FakeModel())
    tweak = tmp_path / "tweak.css"
    tweak.write_text("#cta { background: #00aa00 !important; }")
    url = f"{fixture_server}/button.html"
    code = cli.main(["analyze", url, "--css", str(tweak), "--out", str(tmp_path), "--no-report"])
    assert code == 0
    record = json.loads((tmp_path / cli.slugify_url(url) / "desktop" / "hotspots.json").read_text())
    assert record["css"] == [str(tweak)]
    shot = np.asarray(Image.open(tmp_path / cli.slugify_url(url) / "desktop" / "screenshot.png"))
    assert shot[320, 380].tolist() == [0, 170, 0]


def test_missing_css_file_is_a_clear_error(tmp_path, capsys):
    code = cli.main(["analyze", "https://example.com", "--css", str(tmp_path / "nope.css"), "--no-report"])
    assert code == 2
    assert "nope.css" in capsys.readouterr().err


def test_ui_prior_is_the_default_for_pages_and_files(fixture_server, resume_pdf, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_model", lambda name, device: FakeModel())
    url = f"{fixture_server}/button.html"
    assert cli.main(["analyze", url, "--out", str(tmp_path), "--no-report"]) == 0
    assert cli.main(["analyze", str(resume_pdf), "--out", str(tmp_path), "--no-report"]) == 0
    page = json.loads((tmp_path / cli.slugify_url(url) / "desktop" / "hotspots.json").read_text())
    doc = json.loads((tmp_path / "resume" / "page-1" / "hotspots.json").read_text())
    assert page["centerbias"] == "ueyes"
    assert doc["centerbias"] == "ueyes"
