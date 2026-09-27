---
name: gaze-review
description: Review where a web page draws the eye. Runs gazemap, asks what the page is for, measures whether that element gets attention, and writes review.md with what steals attention, why, and prioritized concrete fixes tied to hotspot data. Use when asked to review, critique, or improve a page's visual hierarchy or attention.
user-invokable: true
args:
  - name: url
    description: The page to review (public URL or localhost), optionally followed by gazemap flags such as --full-page or --hide "<selector>"
    required: true
---

You are running a first-impression review with gazemap's numbers, not with your own guess about where eyes go. The heatmap comes from a saliency model; your job is to interpret it, name causes you can point to, and propose fixes that the numbers can verify later.

## Where gazemap is

Run every command from the gazemap checkout: `$GAZEMAP_HOME` if set, else the current directory if it contains `src/gazemap`, else `~/Documents/projects/gazemap` if it exists, else ask. Outputs land in `runs/<page-slug>/<viewport>/` there. If `uv run gazemap` fails because the environment is missing, run `uv sync` and `uv run playwright install chromium` first.

## Steps, in order

1. **Run.** `uv run gazemap analyze <url> --viewport both --top 8`, plus any flags the user passed. Above the fold is the default because first impressions are what the model is good at; add `--full-page` only if the user asked for the whole page. If a cookie banner or chat widget takes a hotspot, re-run with `--hide "<selector>"` from the output and say so in the review. If the run warns about a 404 or a bot challenge, stop and report it; do not review a placeholder page.
2. **Look.** Read both `overlay.png` files and both `hotspots.json` files. For each viewport note the top hotspots with element, text, share, and box size, and note what drew nothing that a visitor would need: the call to action, the product, a form, a price.
3. **Ask the goal, once, before writing anything.** Use the AskUserQuestion tool when it exists, otherwise ask in chat: "What should a first-time visitor look at first on this page?" Offer up to three concrete candidates you can see, named by their visible text (for example the primary button, the headline, the hero product), plus an open option. The answer is the target. Do not assume it, even when it looks obvious.
4. **Measure the target.** Find a selector for it: an id or the selector printed in `hotspots.json` when the target already is a hotspot, otherwise a Playwright selector such as `button:has-text("Search")`, `text="Get started"`, `img[alt*="warehouse"]`, or `role=button[name="Search"]`. Bare tags like `form` or `img` match the first element in document order, which is often a footer form or the logo, so always qualify them. Re-run the same command with `--target "<selector>"` so both viewports carry the target's share and box in `hotspots.json` under `targets`, and check the `bbox` it reports is the element you meant. If it reports `not found`, fix the selector and re-run; never estimate the number from the picture. Measuring the target's container as a second `--target` (the whole search bar, not only its button) often makes the verdict clearer; when the box is below the viewport height in an above-the-fold run, say that the target is below the fold, which is a finding in itself.
5. **Write `review.md`.** Use the structure in `review-template.md` next to this file. Save it as `runs/<page-slug>/review.md` in the gazemap checkout and copy it to `~/Desktop/gazemap-reports/<page-slug>-review.md`.
6. **Report in chat.** One verdict line per viewport with the target's share and rank, the single highest-priority suggestion, and the path of the review. Do not paste the whole review.

## Naming the cause

For every hotspot that competes with the target, name the cause from this list and point to the evidence in the overlay or the JSON. Several causes can apply.

- **Contrast**: a strong color or brightness difference against its surroundings: a saturated button, a gradient headline, dark type on a light field, a bright image on a dark page.
- **Size**: a large box or large type. Compare the hotspot's `bbox` and the element's rendered size with the target's box.
- **Faces and objects**: photographs with faces, people, or recognizable objects pull fixations.
- **Position**: people scan interfaces from the top left, and gazemap's default prior (fitted on UI eye tracking) gives elements there a head start. Say so when a hotspot sits in the top-left region, and when the call is close, re-run with `--centerbias uniform` and report both numbers.
- **Clutter**: dense text or many similar elements spread attention thin. The symptom is many small hotspots with low shares.
- **Isolation**: an element alone in white space draws the eye even when it is small.

Never state a cause you cannot point to. If you are unsure, say what the numbers show and stop there.

## Writing suggestions

Order them by expected effect on the target's share. Each suggestion names the change concretely (a CSS-level or layout-level edit a developer can make in minutes), the hotspot it addresses by rank, element, and share, and the expected effect on the target. Prefer, in this order: raising the target (contrast, size, position, isolation), then lowering the strongest competitor, then reducing clutter. Three to six suggestions. No generic advice such as "improve the visual hierarchy".

## Rules

- Do not write the review before the goal is known.
- Every number in the review comes from `hotspots.json`. Do not invent or round beyond one decimal.
- State the model caveat once: a saliency model trained on photographs, combined with a location prior fitted on UI eye tracking; a first-glance signal, not a user test.
- Plain Markdown, no em dashes, no dates in the file, no marketing language.
- Do not change the site. Every fix is a proposal for the user, or for the `/gaze-fix` step if it exists.
