import json

import pytest
from PIL import Image

from gazemap import cli
from gazemap.compare import compare_runs


def make_run(root, viewport, width, height, targets, hotspots, color=(200, 200, 200)):
    out = root / viewport
    out.mkdir(parents=True)
    Image.new("RGB", (width, height), color).save(out / "overlay.png")
    record = {
        "url": "http://localhost:3000/",
        "viewport": {"name": viewport, "width": width, "height": height, "mobile": viewport == "mobile"},
        "capture": {"mode": "above_the_fold", "page_height": height, "screens": 1, "screen_height": height},
        "targets": targets,
        "hotspots": hotspots,
    }
    (out / "hotspots.json").write_text(json.dumps(record))
    return out


def target(selector, share, x=10, y=10, w=40, h=20, found=True):
    if not found:
        return {"selector": selector, "found": False, "bbox": None, "share": None, "hotspots": []}
    return {"selector": selector, "found": True, "bbox": {"x": x, "y": y, "width": w, "height": h}, "share": share, "hotspots": []}


def hotspot(rank, share, text):
    return {
        "rank": rank,
        "center": {"x": 5 * rank, "y": 5 * rank},
        "bbox": {"x": 0, "y": 0, "width": 4, "height": 4},
        "share": share,
        "peak": 1 / rank,
        "screen": 1,
        "element": {"tag": "span", "selector": f"span.n{rank}", "text": text},
    }


def test_compare_reports_target_deltas_and_writes_side_by_side(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    make_run(before, "desktop", 100, 60, [target("#cta", 0.05)], [hotspot(1, 0.3, "Headline"), hotspot(2, 0.05, "CTA")])
    make_run(after, "desktop", 100, 60, [target("#cta", 0.12)], [hotspot(1, 0.2, "Headline"), hotspot(2, 0.12, "CTA")])
    result = compare_runs(before, after, tmp_path / "out")

    (view,) = result["views"]
    assert view["viewport"] == "desktop"
    (delta,) = view["targets"]
    assert delta["selector"] == "#cta"
    assert delta["before"] == 0.05 and delta["after"] == 0.12
    assert delta["delta"] == pytest.approx(0.07)
    assert [h["text"] for h in view["hotspots_before"]] == ["Headline", "CTA"]
    assert [h["text"] for h in view["hotspots_after"]] == ["Headline", "CTA"]

    image = Image.open(tmp_path / "out" / "desktop.png")
    assert image.size[0] >= 200  # both overlays side by side
    assert image.size[1] >= 60
    saved = json.loads((tmp_path / "out" / "compare.json").read_text())
    assert saved == result


def test_compare_skips_viewports_and_targets_missing_on_one_side(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    make_run(before, "desktop", 100, 60, [target("#cta", 0.05)], [])
    make_run(before, "mobile", 50, 80, [target("#cta", 0.02)], [])
    make_run(after, "desktop", 100, 60, [target("#cta", 0.0, found=False)], [])
    result = compare_runs(before, after, tmp_path / "out")
    assert [v["viewport"] for v in result["views"]] == ["desktop"]
    assert any("mobile" in w for w in result["warnings"])
    (delta,) = result["views"][0]["targets"]
    assert delta["after"] is None and delta["delta"] is None


def test_compare_with_no_common_viewport_raises(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    make_run(before, "desktop", 100, 60, [], [])
    make_run(after, "mobile", 50, 80, [], [])
    with pytest.raises(ValueError, match="no viewport"):
        compare_runs(before, after, tmp_path / "out")


def test_compare_cli_prints_a_table_with_deltas(tmp_path, capsys):
    before = tmp_path / "before"
    after = tmp_path / "after"
    make_run(before, "desktop", 100, 60, [target("#cta", 0.05)], [hotspot(1, 0.3, "Headline")])
    make_run(after, "desktop", 100, 60, [target("#cta", 0.12)], [hotspot(1, 0.2, "Headline")])
    code = cli.main(["compare", str(before), str(after), "--out", str(tmp_path / "out")])
    assert code == 0
    out = capsys.readouterr().out
    assert "desktop" in out
    assert "#cta" in out and "5.0%" in out and "12.0%" in out and "+7.0" in out
    assert str(tmp_path / "out" / "desktop.png") in out
