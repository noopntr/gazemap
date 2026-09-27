"""Before/after comparison of two gazemap runs: target share deltas and side-by-side overlays."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

VIEW_ORDER = {"desktop": 0, "mobile": 1}
GUTTER = 24
HEADER = 44
TARGET_COLOR = (255, 200, 0)


def load_run(run_dir: str | Path) -> dict[str, dict]:
    """Map viewport name -> record for a run directory (a slug dir with viewport subdirs, or one viewport dir)."""
    run_dir = Path(run_dir)
    records = {}
    candidates = [run_dir] if (run_dir / "hotspots.json").exists() else sorted(p for p in run_dir.iterdir() if p.is_dir())
    for view_dir in candidates:
        path = view_dir / "hotspots.json"
        if path.exists():
            record = json.loads(path.read_text())
            record["_dir"] = str(view_dir)
            records[record["viewport"]["name"]] = record
    if not records:
        raise ValueError(f"no gazemap run found under {run_dir}")
    return records


def compare_runs(before: str | Path, after: str | Path, out: str | Path) -> dict:
    """Compare matching viewports of two runs, write side-by-side images and compare.json."""
    before_runs, after_runs = load_run(before), load_run(after)
    common = sorted(set(before_runs) & set(after_runs), key=lambda n: (VIEW_ORDER.get(n, 9), n))
    warnings = [f"{name} exists only in one run and was skipped" for name in sorted(set(before_runs) ^ set(after_runs))]
    if not common:
        raise ValueError("no viewport is present in both runs")

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    views = []
    for name in common:
        b, a = before_runs[name], after_runs[name]
        targets = _target_deltas(b, a)
        image_path = out / f"{name}.png"
        render_side_by_side(b, a, targets).save(image_path)
        views.append(
            {
                "viewport": name,
                "targets": targets,
                "hotspots_before": _top(b),
                "hotspots_after": _top(a),
                "page_height_before": b["capture"]["page_height"],
                "page_height_after": a["capture"]["page_height"],
                "image": str(image_path),
            }
        )
    result = {"before": str(before), "after": str(after), "warnings": warnings, "views": views}
    (out / "compare.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def _target_deltas(before: dict, after: dict) -> list[dict]:
    by_selector_after = {t["selector"]: t for t in after.get("targets", [])}
    selectors = [t["selector"] for t in before.get("targets", [])]
    selectors += [s for s in by_selector_after if s not in selectors]
    by_selector_before = {t["selector"]: t for t in before.get("targets", [])}
    rows = []
    for selector in selectors:
        b, a = by_selector_before.get(selector), by_selector_after.get(selector)
        share_b = b["share"] if b and b["found"] else None
        share_a = a["share"] if a and a["found"] else None
        rows.append(
            {
                "selector": selector,
                "before": share_b,
                "after": share_a,
                "delta": round(share_a - share_b, 4) if share_b is not None and share_a is not None else None,
                "bbox_before": b["bbox"] if b else None,
                "bbox_after": a["bbox"] if a else None,
            }
        )
    return rows


def _top(record: dict, limit: int = 5) -> list[dict]:
    rows = []
    for spot in record.get("hotspots", [])[:limit]:
        element = spot.get("element") or {}
        rows.append(
            {
                "rank": spot["rank"],
                "share": spot["share"],
                "selector": element.get("selector"),
                "text": element.get("text"),
            }
        )
    return rows


def render_side_by_side(before: dict, after: dict, targets: list[dict]) -> Image.Image:
    """Before and after overlays next to each other, target boxes marked, shares in the header."""
    left = Image.open(Path(before["_dir"]) / "overlay.png").convert("RGB")
    right = Image.open(Path(after["_dir"]) / "overlay.png").convert("RGB")
    _mark_targets(left, [t["bbox_before"] for t in targets])
    _mark_targets(right, [t["bbox_after"] for t in targets])

    width = left.width + GUTTER + right.width
    height = HEADER + max(left.height, right.height)
    canvas = Image.new("RGB", (width, height), (245, 245, 245))
    canvas.paste(left, (0, HEADER))
    canvas.paste(right, (left.width + GUTTER, HEADER))

    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=18)
    draw.text((12, 12), _caption("before", targets, "before"), fill=(20, 20, 20), font=font)
    draw.text((left.width + GUTTER + 12, 12), _caption("after", targets, "after"), fill=(20, 20, 20), font=font)
    return canvas


def _mark_targets(image: Image.Image, boxes: list[dict | None]) -> None:
    draw = ImageDraw.Draw(image)
    for box in boxes:
        if box:
            x, y, w, h = box["x"], box["y"], box["width"], box["height"]
            draw.rectangle([x - 2, y - 2, x + w + 1, y + h + 1], outline=TARGET_COLOR, width=3)


def _caption(label: str, targets: list[dict], key: str) -> str:
    parts = []
    for t in targets:
        share = t[key]
        parts.append(f"{t['selector']}: " + ("not found" if share is None else f"{share * 100:.1f}%"))
    return f"{label}" + (": " + " | ".join(parts) if parts else "")


def print_comparison(result: dict) -> None:
    for warning in result["warnings"]:
        print(f"  warning: {warning}")
    for view in result["views"]:
        print(f"{view['viewport']}: page height {view['page_height_before']} -> {view['page_height_after']} px")
        for t in view["targets"]:
            fmt = lambda v: "not found" if v is None else f"{v * 100:.1f}%"
            delta = "" if t["delta"] is None else f"  ({t['delta'] * 100:+.1f} points)"
            print(f"  target {t['selector']}: before {fmt(t['before'])}, after {fmt(t['after'])}{delta}")
        for label, rows in (("before", view["hotspots_before"]), ("after", view["hotspots_after"])):
            top = ", ".join(f"#{r['rank']} {r['share'] * 100:.1f}% {r['text'] or r['selector'] or ''}".strip() for r in rows[:3])
            print(f"  top hotspots {label}: {top or 'none'}")
        print(f"  -> {view['image']}")
