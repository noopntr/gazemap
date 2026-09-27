from PIL import Image

from gazemap.report import attention_by_element, build_report, write_report


def make_record(tmp_path, viewport, hotspots, mode="above_the_fold", screens=1):
    out = tmp_path / "runs" / "example.com" / viewport
    out.mkdir(parents=True)
    Image.new("RGB", (8, 4), (200, 30, 30)).save(out / "overlay.png")
    return {
        "url": "https://example.com/",
        "final_url": "https://example.com/",
        "http_status": 200,
        "warnings": ["server returned HTTP 200 test warning"] if viewport == "mobile" else [],
        "viewport": {"name": viewport, "width": 100, "height": 50, "mobile": viewport == "mobile"},
        "model": "deepgaze2e",
        "centerbias": "mit1003",
        "device": "mps",
        "capture": {"mode": mode, "page_height": 50 * screens, "screens": screens, "screen_height": 50},
        "runtime_seconds": {"capture": 1.0, "inference": 0.5, "total": 2.0},
        "output_dir": str(out),
        "hotspots": hotspots,
    }


def hotspot(rank, share, selector, text, tag="span", screen=1):
    return {
        "rank": rank,
        "center": {"x": 10 * rank, "y": 5 * rank},
        "bbox": {"x": 0, "y": 0, "width": 4, "height": 4},
        "share": share,
        "peak": 1.0 / rank,
        "screen": screen,
        "element": {"tag": tag, "selector": selector, "text": text},
    }


def test_attention_by_element_sums_shares_of_the_same_selector(tmp_path):
    record = make_record(
        tmp_path,
        "desktop",
        [
            hotspot(1, 0.12, "h1 > span.hero", "for rent in Georgia."),
            hotspot(2, 0.05, "h1 > span.hero", "for rent in Georgia."),
            hotspot(3, 0.08, "#cta", "Get started", tag="button"),
        ],
    )
    rows = attention_by_element(record)
    assert rows[0]["selector"] == "h1 > span.hero"
    assert rows[0]["share"] == 0.17
    assert rows[0]["hotspots"] == [1, 2]
    assert rows[1] == {"selector": "#cta", "tag": "button", "text": "Get started", "share": 0.08, "hotspots": [3]}


def test_build_report_contains_facts_images_and_cross_viewport_overlap(tmp_path):
    desktop = make_record(tmp_path, "desktop", [hotspot(1, 0.3, "#cta", "Get started", tag="button")])
    mobile = make_record(
        tmp_path,
        "mobile",
        [hotspot(1, 0.2, "#cta", "Get started", tag="button", screen=2), hotspot(2, 0.1, "p.lead", "Lead text")],
        mode="full_page",
        screens=3,
    )
    html = build_report([desktop, mobile])
    assert "https://example.com/" in html
    assert "Get started" in html and "Lead text" in html
    assert "30.0%" in html and "20.0%" in html
    assert html.count("data:image/png;base64,") == 2
    assert "full page" in html and "3 screens" in html
    assert "test warning" in html
    # an element that draws attention in both viewports is called out
    assert "Both viewports" in html
    assert "<script" not in html
    assert "&lt;" not in html or "<" in html


def test_write_report_saves_one_file_per_page_slug(tmp_path):
    record = make_record(tmp_path, "desktop", [hotspot(1, 0.3, "#cta", "Get started", tag="button")])
    path = write_report([record], tmp_path / "reports")
    assert path == tmp_path / "reports" / "example.com.html"
    assert path.read_text().startswith("<!doctype html>")


def test_report_lists_targets_when_present(tmp_path):
    record = make_record(tmp_path, "desktop", [hotspot(1, 0.3, "#cta", "Get started", tag="button")])
    record["targets"] = [
        {"selector": "#cta", "found": True, "bbox": {"x": 1, "y": 2, "width": 3, "height": 4}, "share": 0.42, "hotspots": [1]},
        {"selector": "#missing", "found": False, "bbox": None, "share": None, "hotspots": []},
    ]
    html = build_report([record])
    assert "Targets" in html
    assert "42.0%" in html
    assert "not found" in html
