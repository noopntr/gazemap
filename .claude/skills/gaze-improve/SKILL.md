---
name: gaze-improve
description: Rework a page's design until its main elements win the first look. Iterates on CSS injected at capture time, measures each attempt with gazemap, keeps what raises the target's attention share, and stops when the goal is met. No code or site is changed; the winning CSS is the spec for /gaze-fix. Use when asked to redesign, improve, or make a page's main elements more visible or user friendly.
user-invokable: true
args:
  - name: url
    description: The page to improve (live URL or localhost), optionally followed by gazemap flags such as --hide "<selector>"
    required: true
---

You are redesigning with a measurement loop. Opus proposes design changes as CSS, gazemap measures them with the saliency model, and only changes that move the numbers are kept. Nothing is edited in any repository; every attempt is a stylesheet injected into the page before capture.

## Where gazemap is

Run every command from the gazemap checkout: `$GAZEMAP_HOME` if set, else the current directory if it contains `src/gazemap`, else `~/Documents/projects/gazemap` if it exists, else ask. Work in `compare/improve/<page-slug>/` there.

## Steps, in order

1. **Goal.** If `runs/<page-slug>/review.md` exists, take the target selectors and hidden selectors from it and confirm them in one line. Otherwise ask, once, what a first-time visitor should look at first, offering up to three visible candidates, and find selectors for them the way `/gaze-review` does (qualified, checked by the `bbox` in `hotspots.json`). Up to three targets; the first is the main one.
2. **Success criterion.** Default: on every viewport, the main target holds one of the top three hotspots and its share at least doubles from the baseline. Tell the user the default and accept a different one if they give it. Also note each secondary target's baseline share; none may fall by more than a third.
3. **Baseline.** `uv run gazemap analyze <url> --viewport both --top 8 [--hide ...] --target <main> [--target ...] --no-report --out compare/improve/<slug>/iter-0`. Read both overlays and `hotspots.json`. If the page shows a 404, a bot challenge, or the targets are not found, stop and say so.
4. **Iterate, at most six times.** For attempt k:
   - Choose one design idea that addresses the strongest competitor or the target's weakest property (the cause taxonomy of `/gaze-review`: contrast, size, faces and objects, position, clutter, isolation). Say which hotspot it targets and why.
   - Write `compare/improve/<slug>/iter-k.css` containing every kept change so far plus the new one, each rule under a comment naming the idea. Scope rules to viewports with media queries when an idea is for one viewport only (`@media (max-width: 767px)` for mobile).
   - Check the stylesheet against the rules below before running it.
   - Run the baseline command with `--css compare/improve/<slug>/iter-k.css --out compare/improve/<slug>/iter-k`.
   - Compare with the best attempt so far: `uv run gazemap compare compare/improve/<slug>/<best>/<dev-or-live-slug> compare/improve/<slug>/iter-k/<slug> --out compare/improve/<slug>/iter-k/compare`. Keep the new idea only if the main target's share rose on the viewport it was aimed at, no viewport lost more than a point on the main target, and no secondary target fell by more than a third of its baseline. Otherwise drop it and note why.
   - Look at the side-by-side image. If the change breaks the layout (overlapping text, cut-off content, unreadable contrast), drop it even if the number rose.
   - Stop early when the success criterion is met, or after two attempts in a row that were dropped.
5. **Write `improve.md`** in `compare/improve/<slug>/` from `improve-template.md` next to this file, save the winning stylesheet as `best.css`, and copy both to `~/Desktop/gazemap-reports/<slug>-improve.md` and `<slug>-improve.css`.
6. **Report in chat.** Baseline and final share of the main target per viewport, whether the criterion was met, the kept ideas in one line each, the side-by-side image path, and the next step: `/gaze-fix <dev url> <repo>` ports `best.css` into real code, or the user applies it by hand.

## Rules for the stylesheet

The number is only worth something if the page stays the page. Never:

- hide, remove, or empty content: no `display: none`, `visibility: hidden`, `opacity` below 0.6, `content: ""` over text, `font-size` below 12px, `color` equal to its background, `clip`, `clip-path`, or zero width or height on anything that holds text, images, or controls;
- cover content with overlays, or push content off screen with negative margins or transforms;
- change text, images, or links; restyle and reorder only;
- use colors outside the page's own palette except for pure black, white, and grays, unless the user asked for a new palette.

Allowed moves are size, weight, color from the palette, contrast, spacing, alignment, order (`order`, grid placement, `flex-direction`), position within the normal flow, borders, shadows, and backgrounds. Prefer the smallest change that works; a real designer should be willing to ship every kept rule.

## Rules for reporting

- Every number comes from `hotspots.json` or `compare.json`, one decimal.
- An attempt that did not help is reported as such; the table shows all attempts.
- The model caveat applies once: a saliency model trained on photographs predicts the first glance; the result is a strong hint, not a user test.
- Plain Markdown, no em dashes, no dates.
