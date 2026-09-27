"""Command line entry point: ``gazemap analyze <url or file>``."""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# Must be set before torch is imported anywhere in the process.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

from PIL import Image  # noqa: E402

from gazemap.capture import VIEWPORTS, CaptureError, PageSession, Viewport  # noqa: E402
from gazemap.document import is_document_path, load_document  # noqa: E402
from gazemap.hotspots import Hotspot, find_hotspots  # noqa: E402
from gazemap.maps import normalize_unit, stitch_windows  # noqa: E402
from gazemap.render import render_heatmap, render_overlay  # noqa: E402
from gazemap.report import write_report  # noqa: E402
from gazemap.saliency import (  # noqa: E402
    CENTERBIAS_KINDS,
    MODEL_NAMES,
    ModelDownloadError,
    SaliencyModel,
    load_model,
)

DEFAULT_REPORT_DIR = "~/Desktop/gazemap-reports"
TEXT_LIMIT = 80


def slugify_url(url: str) -> str:
    """Filesystem-friendly name for a URL: host, port, and path, without query."""
    parts = urlparse(url if "://" in url else f"http://{url}")
    pieces = [(parts.hostname or "page").lower().removeprefix("www.")]
    if parts.port:
        pieces.append(str(parts.port))
    pieces += [segment for segment in parts.path.lower().split("/") if segment]
    return _clean_slug("-".join(pieces))


def slugify_path(path: str | Path) -> str:
    """Filesystem-friendly name for a document: its file name without the extension."""
    return _clean_slug(Path(path).stem.lower())


def _clean_slug(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9.-]+", "-", raw)
    return re.sub(r"-{2,}", "-", slug).strip("-.") or "page"


def analyze_page(
    url: str,
    viewport: Viewport,
    model: SaliencyModel,
    *,
    out_dir: str | Path = "runs",
    centerbias: str = "mit1003",
    top: int = 5,
    wait_ms: int = 0,
    hide: list[str] | tuple[str, ...] = (),
    timeout_ms: int = 30000,
    full_page: bool = False,
    max_screens: int = 20,
) -> dict:
    """Capture a web page, predict, extract hotspots, map them to DOM elements, write outputs.

    In full-page mode every viewport-sized screen is predicted on its own and the
    maps are stitched, so each screen carries equal weight.
    """
    started = time.perf_counter()
    session_args = dict(wait_ms=wait_ms, hide=hide, timeout_ms=timeout_ms, full_page=full_page, max_screens=max_screens)
    with PageSession(url, viewport, **session_args) as session:
        capture = session.capture
        captured = time.perf_counter()
        window_maps = [(w.scroll_y, model.predict(w.image, centerbias=centerbias)) for w in capture.windows]
        prob = stitch_windows(window_maps, height=capture.image.shape[0], width=capture.image.shape[1])
        inferred = time.perf_counter()
        spots = find_hotspots(prob, top=top, min_distance=_min_distance(viewport.width, viewport.height))

        def lookup(spot: Hotspot) -> dict | None:
            element = session.element_at(spot.x, spot.y)
            if element is None:
                return None
            return {"tag": element.tag, "selector": element.selector, "text": element.text}

        hotspots = [_hotspot_record(spot, lookup(spot), viewport.height) for spot in spots]

    meta = {
        "url": url,
        "final_url": capture.final_url,
        "http_status": capture.status,
        "warnings": capture.warnings,
        "viewport": {"name": viewport.name, "width": viewport.width, "height": viewport.height, "mobile": viewport.is_mobile},
        "model": model.name,
        "centerbias": centerbias,
        "device": model.device,
        "capture": {
            "mode": "full_page" if full_page else "above_the_fold",
            "page_height": capture.page_height,
            "screens": len(capture.windows),
            "screen_height": viewport.height,
        },
    }
    timings = {"capture": round(captured - started, 2), "inference": round(inferred - captured, 2)}
    out = Path(out_dir) / slugify_url(url) / viewport.name
    return _write_outputs(out, capture.image, prob, spots, hotspots, meta, timings, started)


def analyze_document(
    path: str | Path,
    model: SaliencyModel,
    *,
    out_dir: str | Path = "runs",
    centerbias: str = "uniform",
    top: int = 5,
) -> list[dict]:
    """Analyze each page of a PDF, or a single image, as one view. Returns one record per page."""
    path = Path(path).expanduser()
    started = time.perf_counter()
    with load_document(path) as document:
        loaded = time.perf_counter()
        records = [
            _analyze_document_page(path, page, index, model, out_dir, centerbias, top, started, loaded)
            for index, page in enumerate(document.pages)
        ]
    return records


def _analyze_document_page(path, page, index, model, out_dir, centerbias, top, started, loaded) -> dict:
    """Predict one document page, map hotspots to its text lines, and write outputs."""
    page_started = time.perf_counter()
    prob = model.predict(page.image, centerbias=centerbias)
    inferred = time.perf_counter()
    height, width = page.image.shape[:2]
    spots = find_hotspots(prob, top=top, min_distance=_min_distance(width, height))

    def lookup(spot: Hotspot, page=page, width=width) -> dict | None:
        x, y, w, h = spot.bbox
        text = page.text_in(0, y, width, h)  # the text lines under the hotspot
        if text is None:
            return None
        return {"tag": "text", "selector": f"{page.name} y {y}-{y + h}", "text": text[:TEXT_LIMIT]}

    hotspots = [_hotspot_record(spot, lookup(spot), height) for spot in spots]
    meta = {
        "url": str(path),
        "final_url": str(path.resolve()),
        "http_status": None,
        "warnings": [],
        "viewport": {"name": page.name, "width": width, "height": height, "mobile": False},
        "model": model.name,
        "centerbias": centerbias,
        "device": model.device,
        "capture": {"mode": "document", "page_height": height, "screens": 1, "screen_height": height},
    }
    timings = {
        "capture": round(loaded - started, 2) if index == 0 else 0.0,
        "inference": round(inferred - page_started, 2),
    }
    out = Path(out_dir) / slugify_path(path) / page.name
    return _write_outputs(out, page.image, prob, spots, hotspots, meta, timings, page_started)


def _min_distance(width: int, height: int) -> int:
    """Suppression radius: 5% of the view's long side, never of the page height."""
    return max(1, round(0.05 * max(width, height)))


def _hotspot_record(spot: Hotspot, element: dict | None, screen_height: int) -> dict:
    x, y, w, h = spot.bbox
    return {
        "rank": spot.rank,
        "center": {"x": spot.x, "y": spot.y},
        "bbox": {"x": x, "y": y, "width": w, "height": h},
        "share": round(spot.share, 4),
        "peak": round(spot.peak, 4),
        "screen": spot.y // screen_height + 1,
        "element": element,
    }


def _write_outputs(out: Path, image, prob, spots, hotspots, meta: dict, timings: dict, started: float) -> dict:
    unit = normalize_unit(prob)
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image).save(out / "screenshot.png")
    render_heatmap(unit).save(out / "heatmap.png")
    render_overlay(image, unit, spots).save(out / "overlay.png")
    record = {
        **meta,
        "runtime_seconds": {**timings, "total": round(time.perf_counter() - started, 2)},
        "output_dir": str(out),
        "hotspots": hotspots,
    }
    (out / "hotspots.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def print_summary(record: dict, limit: int = 5) -> None:
    vp = record["viewport"]
    cap = record["capture"]
    runtime = record["runtime_seconds"]
    mode = {"full_page": f"{cap['screens']} screens", "above_the_fold": "above the fold", "document": "document"}[cap["mode"]]
    print(
        f"{record['url']} [{vp['name']} {vp['width']}x{vp['height']}, {mode}] "
        f"{record['model']} on {record['device']}, centerbias {record['centerbias']}: "
        f"capture {runtime['capture']}s, inference {runtime['inference']}s"
    )
    for warning in record["warnings"]:
        print(f"  warning: {warning}")
    if not record["hotspots"]:
        print("  no hotspots found")
    for spot in record["hotspots"][:limit]:
        element = spot["element"]
        where = "no element" if element is None else f"{element['tag']} {element['selector']}"
        text = f' "{element["text"]}"' if element and element["text"] else ""
        screen = f"  (screen {spot['screen']})" if cap["mode"] == "full_page" else ""
        print(f"  {spot['rank']:>2}  {spot['share'] * 100:5.1f}%  {where}{text}{screen}")
    print(f"  -> {record['output_dir']}/overlay.png")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gazemap", description="Predict where people look first on a web page or document.")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="capture a page or load a file and produce an attention heatmap")
    analyze.add_argument("url", metavar="URL_OR_FILE", help="a web page URL, or a .pdf, .png, .jpg or .webp file")
    analyze.add_argument("--viewport", choices=["desktop", "mobile", "both"], default="desktop", help="web pages only")
    analyze.add_argument("--wait", type=int, default=0, metavar="MS", help="extra wait after load (web pages)")
    analyze.add_argument(
        "--hide", action="append", default=[], metavar="SELECTOR", help="CSS selector to hide before capture (repeatable)"
    )
    analyze.add_argument(
        "--centerbias", choices=CENTERBIAS_KINDS, default=None, help="default: mit1003 for web pages, uniform for files"
    )
    analyze.add_argument("--top", type=int, default=5, metavar="N", help="number of hotspots")
    analyze.add_argument("--device", choices=["auto", "mps", "cpu"], default="auto")
    analyze.add_argument("--model", choices=MODEL_NAMES, default="deepgaze2e")
    analyze.add_argument("--out", default="runs", metavar="DIR", help="output root directory")
    analyze.add_argument("--timeout", type=int, default=30000, metavar="MS", help="navigation timeout (web pages)")
    analyze.add_argument("--full-page", action="store_true", help="analyze a web page screen by screen")
    analyze.add_argument("--max-screens", type=int, default=20, metavar="N", help="cap for --full-page")
    analyze.add_argument(
        "--report-dir", default=DEFAULT_REPORT_DIR, metavar="DIR", help="where the HTML report is written"
    )
    analyze.add_argument("--no-report", action="store_true", help="skip the HTML report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target = args.url
    document = is_document_path(target)
    if document and not Path(target).expanduser().is_file():
        print(f"error: file not found: {target}", file=sys.stderr)
        return 2

    loading = time.perf_counter()
    try:
        model = load_model(args.model, device=args.device)
    except ModelDownloadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    print(f"loaded {model.name} on {model.device} in {time.perf_counter() - loading:.1f}s", file=sys.stderr)

    if document:
        try:
            records = analyze_document(
                target, model, out_dir=args.out, centerbias=args.centerbias or "uniform", top=args.top
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        for record in records:
            print_summary(record)
        slug = slugify_path(target)
    else:
        viewports = ["desktop", "mobile"] if args.viewport == "both" else [args.viewport]
        records = []
        for name in viewports:
            try:
                record = analyze_page(
                    target,
                    VIEWPORTS[name],
                    model,
                    out_dir=args.out,
                    centerbias=args.centerbias or "mit1003",
                    top=args.top,
                    wait_ms=args.wait,
                    hide=args.hide,
                    timeout_ms=args.timeout,
                    full_page=args.full_page,
                    max_screens=args.max_screens,
                )
            except CaptureError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print_summary(record)
            records.append(record)
        slug = slugify_url(target)

    if not args.no_report:
        path = write_report(records, args.report_dir, slug=slug)
        print(f"  report: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
