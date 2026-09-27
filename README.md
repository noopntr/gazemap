# gazemap

Local attention heatmaps for web pages. Give it a URL, it captures the page above the
fold, runs the DeepGaze IIE saliency model on the screenshot, and tells you where a
first-time viewer is most likely to look and which DOM elements sit there.

Everything runs on your machine. No API keys, no cloud services, no language or vision
model in the loop. The heatmap comes from a dedicated fixation-prediction model.

```
$ uv run gazemap analyze https://www.wikipedia.org --viewport both
loaded deepgaze2e on mps in 2.5s
https://www.wikipedia.org [desktop 1440x900] deepgaze2e on mps: capture 1.27s, inference 1.4s
   1    5.6%  nav #www-wikipedia-org > main > nav.central-featured "English 7,237,000+ articles ..."
   2    7.7%  span #js-lang-list-button > span.lang-list-button-text.jsl10n "Read Wikipedia in your language"
   3    3.1%  strong div.central-textlogo > h1.central-textlogo-wrapper > strong.jsl10n.localized-slogan "The Free Encyclopedia"
   4    3.6%  small #js-link-box-pl > small "1 707 000+ haseł"
   5    4.5%  small #js-link-box-pt > small "1.181.000+ artigos"
  -> runs/wikipedia.org/desktop/overlay.png
```

## Setup

Requires macOS on Apple Silicon (PyTorch uses the MPS device, with CPU fallback) and
[uv](https://docs.astral.sh/uv/). Python 3.12 is pinned in `.python-version`; uv will
fetch it if needed.

```bash
uv sync
uv run playwright install chromium
```

The first `analyze` run downloads the DeepGaze IIE checkpoint (420 MB) and the MIT1003
centerbias (8 MB) into `models/`, which is gitignored. Set `GAZEMAP_MODEL_DIR` to keep
them elsewhere. If the download fails, the error prints the URL and target path so you
can fetch the file by hand.

## Usage

```bash
uv run gazemap analyze <url> [options]
```

| Option | Default | Meaning |
|---|---|---|
| `--viewport desktop\|mobile\|both` | `desktop` | Desktop is 1440x900, mobile is 390x844 with a phone user agent and touch. Both use device pixel ratio 1. |
| `--wait MS` | `0` | Extra wait after the load event, for pages that render late. |
| `--hide SELECTOR` | | CSS selector to hide before capture. Repeatable. Use it for cookie banners and chat widgets. |
| `--centerbias mit1003\|uniform` | `mit1003` for pages, `uniform` for files | Prior over fixation locations. `uniform` removes the center preference. |
| `--top N` | `5` | Number of hotspots to extract. |
| `--device auto\|mps\|cpu` | `auto` | `auto` picks MPS when available. |
| `--out DIR` | `runs` | Output root. |
| `--timeout MS` | `30000` | Navigation timeout. |

Local dev servers work the same way: `uv run gazemap analyze http://localhost:3000`.

### Full page

```bash
uv run gazemap analyze https://example.com --viewport both --full-page
```

| Option | Default | Meaning |
|---|---|---|
| `--full-page` | off | Analyze the whole page screen by screen instead of the first viewport only. |
| `--max-screens N` | `20` | Cap on screens per viewport in full-page mode. Longer pages are truncated with a warning. |

The model needs a single view at roughly the scale it was trained on, so a tall page
cannot go in as one image: a 4000 px page shrunk to 1024 px would turn every headline
into a few pixels. Instead the page is scrolled once so lazy content loads, captured in
full, and cut into viewport-height screens. Each screen is predicted on its own, with
its own center bias, and the maps are stitched with equal weight per screen. Fixed
elements such as cookie banners appear once, in the first screen. Each hotspot records
the `screen` it sits on, and `share` becomes a fraction of the whole page with screens
weighted equally, so shares are smaller than in above-the-fold runs.

### PDFs and images

```bash
uv run gazemap analyze ~/Documents/resume.pdf
uv run gazemap analyze screenshot.png
```

A `.pdf`, `.png`, `.jpg` or `.webp` path works in place of a URL. Each PDF page is rendered
at 150 dpi and analyzed as one view; outputs go to `runs/<file-name>/page-1/` and so on,
images to `runs/<file-name>/image/`. In place of a DOM element, each hotspot reports the
text lines under it from the PDF's text layer (`tag` is `text`, `selector` gives the page
and pixel rows). Images have no text layer, so `element` is `null`. Documents default to
`--centerbias uniform`, because nobody reads a page from its middle; the viewport,
full-page, wait, and hide options do not apply.

Two-column layouts list both columns' lines under a hotspot. And keep in mind what the
model is: a free-viewing first-glance predictor, not a reader. On a resume it can tell
you whether the name and headings dominate or a photo, icon column, or colored sidebar
steals the first look. It cannot tell you what a recruiter, who scans top-left down for a
title, company, and dates, will actually read.

### Report

Every run also writes a self-contained HTML report to `~/Desktop/gazemap-reports/`,
one file per page slug, overwritten on re-run. It embeds the overlays and lists the
hotspots, the total attention per DOM element, and the elements that draw attention in
every viewport. It states what the model predicted and how to read it; it does not
critique the design, which is the job of the later review step.

| Option | Default | Meaning |
|---|---|---|
| `--report-dir DIR` | `~/Desktop/gazemap-reports` | Where the report is written. |
| `--no-report` | off | Skip the report. |

### Outputs

Each run writes to `runs/<page-slug>/<viewport>/` and overwrites what was there. The
slug is the host, port, and path of the URL, so `http://localhost:3000/pricing` becomes
`runs/localhost-3000-pricing/desktop/`.

| File | Content |
|---|---|
| `screenshot.png` | The captured viewport. |
| `heatmap.png` | Grayscale attention map, 255 at the strongest point. |
| `overlay.png` | Heatmap blended over the screenshot. Blend strength follows attention, so quiet areas show the page as is. Hotspots are boxed and numbered by rank. |
| `hotspots.json` | Everything below. |

`hotspots.json` records the URL, final URL after redirects, HTTP status, capture
warnings, viewport, model, centerbias, device actually used, capture mode with page
height and screen count, and runtime in seconds for capture, inference, and total. Each
hotspot has:

- `rank`: 1 is the highest peak.
- `center`: peak pixel in screenshot coordinates.
- `bbox`: extent of the region around the peak that stays above half the peak value.
- `share`: fraction of the page's total predicted attention inside that region.
- `peak`: peak height relative to the strongest hotspot.
- `screen`: which viewport-height screen the peak is on, counted from 1.
- `element`: `tag`, a short CSS `selector`, and trimmed visible `text` of the topmost DOM element at the center, from `document.elementFromPoint` in the same browser session. `null` if the point is outside the document.

Hotspots are ranked by peak height, which is the model's best guess at where the eye
lands first. A broad, softer region can hold a larger `share` than a sharper peak ranked
above it. Both numbers are reported so you can use whichever fits the question.

### Exit codes

`0` success, `2` the page could not be captured (unreachable host, connection refused,
timeout, TLS problem), `3` a model file could not be downloaded. HTTP errors and bot
challenges do not abort the run. The page is captured anyway and a warning is printed and
saved, because a 403 page can still be worth looking at.

## How it works

1. **Capture.** Playwright drives headless Chromium at the requested viewport. It waits
   for the load event, then for network idle up to 10 s, then `--wait`. Hidden selectors
   are removed with an injected stylesheet. Animations are frozen for the screenshot.
2. **Saliency.** The screenshot is resized so its long side is 1024 px, the scale
   DeepGaze was trained at (MIT1003 images at about 35 px per degree of visual angle).
   The centerbias log density is rescaled to the same size and renormalized. The model
   returns a log density, which is turned into a probability map and resized back to
   screenshot size, renormalized to sum to 1.
3. **Hotspots.** Greedy non-maximum suppression over local maxima. Peaks within 5% of
   the long side of an earlier peak, or below 5% of the global maximum, are dropped.
   Every pixel is then assigned to the local maximum it reaches by steepest ascent, and
   maxima that were suppressed count as part of the hotspot that suppressed them. A
   hotspot's region is the connected part of its own basin that stays above half its
   peak, so regions never overlap or enclose another hotspot. Candidates whose region
   holds under 1% of the attention are skipped in favour of the next peak.
4. **DOM mapping.** For each hotspot center the still-open page is asked for the element
   at that point.
5. **Render and write.** Images and JSON are written, then the summary is printed.

The model sits behind a small `SaliencyModel` protocol in `src/gazemap/saliency/`, so
another model can be added without touching the pipeline. UMSI is the planned fallback.

### About the DeepGaze loader

DeepGaze IIE is an ensemble of four ImageNet backbones with 30 small readout heads each.
The published checkpoint contains all backbone weights, but the upstream constructors
still download each backbone's original ImageNet weights first, from Bitbucket, a GitHub
release, and `torch.hub`, which stops at an interactive trust prompt. gazemap builds the
same architectures empty in `saliency/backbones.py` and loads the checkpoint with strict
key checking, so the only downloads are the checkpoint and the centerbias. DeepGaze is
pinned to tag v1.1.0, whose IIE code is identical to the current main branch but does not
require OpenAI CLIP.

## Runtime

Measured on a MacBook Pro M4 Pro (24 GB) with the Wikipedia home page.

| | Model load | First inference | Warm inference per page |
|---|---|---|---|
| MPS, desktop 1440x900 | 2.9 s | 2.6 s | 0.56 s |
| MPS, mobile 390x844 | | 1.2 s | 0.49 s |
| CPU, desktop 1440x900 | 1.2 s | 1.4 s | 1.33 s |
| CPU, mobile 390x844 | | 1.3 s | 1.27 s |

The first MPS call per input shape pays for kernel compilation. Capture adds about 1.2 s
per viewport, including the browser launch. A single-page run therefore takes a few
seconds end to end on either device; MPS wins once more than one page is analyzed in the
same process. If an MPS op fails, the run retries on CPU and says so.

Full page on a 4200 px desktop page (5 screens) and a 7700 px mobile page (10 screens),
both viewports in one run, including the report: 23 s wall clock on MPS. Inference was
4.0 s and 5.7 s, capture 2.7 s and 3.0 s.

## Models and licenses

| Component | Source | License |
|---|---|---|
| DeepGaze IIE code and checkpoint | [matthias-k/DeepGaze](https://github.com/matthias-k/DeepGaze), tag v1.1.0 | No license file in the repository and the MIT classifier in its `setup.py` is commented out. Research code published with the paper: Linardos, Kümmerer, Press, Bethge, *Calibrated prediction in and out-of-domain for state-of-the-art saliency modeling*, ICCV 2021. Used here for personal, non-commercial purposes. |
| MIT1003 centerbias | Same release | Derived from the MIT1003 eye-tracking dataset (Judd et al. 2009). No explicit license. |
| ShapeNet-C backbone weights | [rgeirhos/texture-vs-shape](https://github.com/rgeirhos/texture-vs-shape), redistributed inside the checkpoint | No license for code or weights in that repository; it only ships a `DATASET_LICENSE` for its stimuli. Research weights from Geirhos et al., ICLR 2019. |
| EfficientNet-B5 backbone code and weights | [lukemelas/EfficientNet-PyTorch](https://github.com/lukemelas/EfficientNet-PyTorch), vendored in DeepGaze | Apache-2.0 |
| DenseNet201 and ResNeXt50 backbone weights | torchvision | BSD-3-Clause |
| PyTorch, torchvision | | BSD-3-Clause |
| NumPy, SciPy, boltons | | BSD-3-Clause |
| Pillow | | MIT-CMU |
| pypdfium2 (PDFium) | | BSD-3-Clause and Apache-2.0 |
| Playwright, Chromium | | Apache-2.0, BSD-3-Clause |

Model weights are never committed. They live in the gitignored `models/` directory.

## Known limitations

- **DeepGaze is trained on natural images, not web pages.** MIT1003 is photographs.
  The heatmap is a rough signal about contrast, faces, text, and position, not a
  measurement of real users. Treat it as one input to your own judgment.
- **One view at a time.** The model predicts first fixations on a single view. Full-page
  mode analyzes each screen as if the viewer had just scrolled there, which ignores
  everything they saw on the way.
- **Center bias.** The MIT1003 prior pulls attention toward the center of the viewport.
  Compare with `--centerbias uniform` when an off-center element seems under-rated.
- **Mobile scaling.** Mobile screenshots are upscaled to 1024 px on the long side, the
  same rule as desktop. At a phone's viewing distance the native width is already close
  to the training scale, so this is a judgment call. The constant lives in
  `DeepGazeIIE(long_side=...)`.
- **Headless detection.** Some sites serve a challenge page or a 403 to headless
  browsers. The run continues with a warning; check `http_status` and `warnings` in the
  JSON before trusting the result.
- **DOM mapping picks the topmost element.** Overlays, transparent wrappers, and text
  spans inside buttons are reported as they are.

## Development

```bash
uv run pytest            # 55 tests, about 40 s with weights and Chromium present
uv run pytest -m "not smoke"   # unit and capture tests only
```

Unit tests cover normalization, coordinate mapping, map stitching, peak extraction with
suppression, rendering, full-page capture and DOM lookup against fixture pages served
locally, PDF and image loading with text lookup, report generation, and CLI output.
Tests never write to the real Desktop. The smoke
test runs the real model on a plain page with one red button and asserts the top hotspot
lands on it in both viewports. Model tests skip when the weights are not downloaded.

```
src/gazemap/
  cli.py                  argument parsing, pipeline, terminal summary
  capture.py              Playwright session, screenshots, screens, elementFromPoint
  document.py             PDF pages and images as views, text under a rectangle
  maps.py                 log density -> probability, resizing, stitching
  hotspots.py             peaks, suppression, regions, attention share
  render.py               heatmap and overlay images
  report.py               self-contained HTML report
  saliency/__init__.py    SaliencyModel protocol and load_model()
  saliency/deepgaze.py    DeepGaze IIE: downloads, device, prediction
  saliency/backbones.py   backbone architectures rebuilt without downloads
```
