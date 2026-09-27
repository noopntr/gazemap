"""Self-contained HTML report for one page across viewports."""

import base64
import html
from pathlib import Path

STYLE = """
body { font: 15px/1.5 -apple-system, system-ui, sans-serif; color: #1a1a1a; background: #fff;
       max-width: 1100px; margin: 0 auto; padding: 32px 24px; }
h1 { font-size: 24px; margin: 0 0 4px; } h2 { font-size: 20px; margin: 40px 0 8px; }
h3 { font-size: 16px; margin: 24px 0 8px; }
.muted { color: #666; } .warn { background: #fff4e5; border-left: 4px solid #f0a020; padding: 8px 12px; margin: 12px 0; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 16px; font-size: 14px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #e5e5e5; vertical-align: top; }
th { font-weight: 600; color: #444; } td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
code { font: 12px/1.4 ui-monospace, Menlo, monospace; color: #444; word-break: break-all; }
img.overlay { max-width: 100%; height: auto; border: 1px solid #ddd; display: block; margin: 8px 0 16px; }
.notes { background: #f6f7f9; padding: 12px 16px; border-radius: 6px; font-size: 14px; }
.notes p { margin: 6px 0; }
"""


def attention_by_element(record: dict) -> list[dict]:
    """Total attention share per DOM element, most attention first."""
    totals: dict[str, dict] = {}
    for spot in record["hotspots"]:
        element = spot["element"]
        if element is None:
            continue
        row = totals.setdefault(
            element["selector"],
            {"selector": element["selector"], "tag": element["tag"], "text": element["text"], "share": 0.0, "hotspots": []},
        )
        row["share"] = round(row["share"] + spot["share"], 4)
        row["hotspots"].append(spot["rank"])
    return sorted(totals.values(), key=lambda row: row["share"], reverse=True)


def build_report(records: list[dict]) -> str:
    first = records[0]
    e = html.escape
    parts = [
        "<!doctype html>",
        f"<html lang='en'><head><meta charset='utf-8'><title>gazemap: {e(first['url'])}</title>",
        f"<style>{STYLE}</style></head><body>",
        f"<h1>Attention report</h1><p class='muted'>{_source_line(first)}"
        + f"<br>{e(first['model'])} on {e(first['device'])}, centerbias {e(first['centerbias'])}"
        + (f", HTTP {first['http_status']}" if first["http_status"] is not None else "")
        + "</p>",
    ]
    for record in records:
        parts.append(_viewport_section(record))
    if len(records) > 1:
        parts.append(_overlap_section(records))
    parts.append(_notes())
    parts.append("</body></html>")
    return "\n".join(parts)


def _viewport_section(record: dict) -> str:
    e = html.escape
    vp = record["viewport"]
    cap = record["capture"]
    mode = {
        "full_page": f"full page, {cap['screens']} screens of {cap['screen_height']} px; page height {cap['page_height']} px",
        "above_the_fold": f"above the fold; page height {cap['page_height']} px",
        "document": "document page",
    }[cap["mode"]]
    runtime = record["runtime_seconds"]
    out = [
        f"<h2>{e(vp['name'].replace('-', ' ').capitalize())} {vp['width']}&times;{vp['height']}</h2>",
        f"<p class='muted'>{e(mode)}; capture {runtime['capture']} s, inference {runtime['inference']} s</p>",
    ]
    for warning in record["warnings"]:
        out.append(f"<div class='warn'>{e(warning)}</div>")
    out.append(f"<img class='overlay' alt='attention overlay, {e(vp['name'])}' src='{_data_uri(record)}'>")

    out.append("<h3>Hotspots by peak</h3><table><tr><th class='num'>#</th><th class='num'>Share</th>"
               "<th>Element</th><th>Text</th><th>Position</th></tr>")
    for spot in record["hotspots"]:
        element = spot["element"]
        where = f"x {spot['center']['x']}, y {spot['center']['y']}"
        if cap["mode"] == "full_page":
            where += f", screen {spot.get('screen', 1)}"
        out.append(
            f"<tr><td class='num'>{spot['rank']}</td><td class='num'>{spot['share'] * 100:.1f}%</td>"
            + (
                f"<td>{e(element['tag'])} <code>{e(element['selector'])}</code></td><td>{e(element['text'])}</td>"
                if element
                else "<td colspan='2' class='muted'>no element</td>"
            )
            + f"<td class='muted'>{e(where)}</td></tr>"
        )
    out.append("</table>")

    targets = record.get("targets") or []
    if targets:
        out.append("<h3>Targets</h3><table><tr><th>Selector</th><th class='num'>Share</th><th>Hotspots inside</th></tr>")
        for target in targets:
            if target["found"]:
                inside = ", ".join(str(r) for r in target["hotspots"]) or "none"
                out.append(
                    f"<tr><td><code>{e(target['selector'])}</code></td>"
                    f"<td class='num'>{target['share'] * 100:.1f}%</td><td class='muted'>{e(inside)}</td></tr>"
                )
            else:
                out.append(f"<tr><td><code>{e(target['selector'])}</code></td><td colspan='2' class='muted'>not found</td></tr>")
        out.append("</table>")

    rows = attention_by_element(record)
    if rows:
        out.append("<h3>Attention by element</h3><table><tr><th class='num'>Share</th><th>Element</th>"
                   "<th>Text</th><th>Hotspots</th></tr>")
        for row in rows:
            out.append(
                f"<tr><td class='num'>{row['share'] * 100:.1f}%</td>"
                f"<td>{e(row['tag'])} <code>{e(row['selector'])}</code></td><td>{e(row['text'])}</td>"
                f"<td class='muted'>{', '.join(str(r) for r in row['hotspots'])}</td></tr>"
            )
        out.append("</table>")
    return "\n".join(out)


def _overlap_section(records: list[dict]) -> str:
    e = html.escape
    shares = [{row["selector"]: row for row in attention_by_element(r)} for r in records]
    common = set(shares[0]).intersection(*shares[1:])
    names = [r["viewport"]["name"].replace("-", " ") for r in records]
    documents = records[0]["capture"]["mode"] == "document"
    out = ["<h2>Across pages</h2>" if documents else "<h2>Both viewports</h2>"]
    if not common:
        out.append(f"<p class='muted'>No text or element is among the hotspots on every {'page' if documents else 'viewport'}.</p>")
        return "\n".join(out)
    out.append("<table><tr><th>Element</th><th>Text</th>"
               + "".join(f"<th class='num'>{e(n)}</th>" for n in names) + "</tr>")
    for selector in sorted(common, key=lambda s: -sum(v[s]["share"] for v in shares)):
        row = shares[0][selector]
        out.append(
            f"<tr><td>{e(row['tag'])} <code>{e(selector)}</code></td><td>{e(row['text'])}</td>"
            + "".join(f"<td class='num'>{v[selector]['share'] * 100:.1f}%</td>" for v in shares)
            + "</tr>"
        )
    out.append("</table>")
    return "\n".join(out)


def _notes() -> str:
    return (
        "<h2>How to read this</h2><div class='notes'>"
        "<p>The heatmap is a prediction from DeepGaze IIE, a model of where people fixate first when "
        "free-viewing an image. It was trained on photographs, not web pages, so treat it as a rough "
        "signal about contrast, size, faces, text, and position rather than a measurement of real users.</p>"
        "<p>Hotspots are ranked by peak height, the model's best guess at where the eye lands first. "
        "Share is the fraction of predicted attention inside the boxed region around each peak. "
        "A broad soft region can hold more share than a sharper peak ranked above it.</p>"
        "<p>In full-page mode each screen is analyzed as its own view and every screen carries equal "
        "weight, so a share is a fraction of the whole page with screens weighted equally. Fixed "
        "elements such as cookie banners are captured once, in the first screen.</p>"
        "<p>The MIT1003 center bias pulls attention toward the middle of each screen. Re-run with "
        "<code>--centerbias uniform</code> to see the page without that prior.</p></div>"
    )


def _source_line(record: dict) -> str:
    e = html.escape
    url = record["url"]
    shown = f"<a href='{e(url)}'>{e(url)}</a>" if url.startswith(("http://", "https://")) else f"<code>{e(url)}</code>"
    if record["final_url"] != url and url.startswith(("http://", "https://")):
        shown += f" &rarr; {e(record['final_url'])}"
    return shown


def _data_uri(record: dict) -> str:
    data = (Path(record["output_dir"]) / "overlay.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def write_report(records: list[dict], report_dir: str | Path, slug: str | None = None) -> Path:
    if slug is None:
        from gazemap.cli import slugify_url

        slug = slugify_url(records[0]["url"])
    report_dir = Path(report_dir).expanduser()
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{slug}.html"
    path.write_text(build_report(records))
    return path
