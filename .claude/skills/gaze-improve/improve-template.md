# Attention redesign: <url>

**Main target:** `<selector>` (<what it is>). **Secondary:** `<selector>`, ... **Hidden during capture:** `<selector>` or none.
**Success criterion:** <the criterion>. **Result:** met / not met.

## Main target share

| Viewport | Baseline | Final | Change | Top-3 hotspot |
|---|---|---|---|---|
| Desktop | 0.6% | 9.8% | +9.2 points | yes, rank 2 |
| Mobile | 0.0% | 14.1% | +14.1 points | yes, rank 1 |

Secondary targets: <selector> <baseline> to <final> per viewport.

## Attempts

| # | Idea | Aimed at | Main target desktop | Main target mobile | Kept |
|---|---|---|---|---|---|
| 1 | Move the search bar under the headline on mobile | fold, mobile | 0.6% | 12.3% | yes |
| 2 | ... | ... | ... | ... | no: <reason> |

## Kept changes

One short paragraph per kept idea: what it changes, which hotspot it addressed, what the numbers did.

```css
<contents of best.css>
```

## Before and after

`compare/improve/<slug>/<final>/compare/desktop.png` and `mobile.png`. Two or three sentences on where the first look lands before and after.

## Next

Port `best.css` into the codebase with `/gaze-fix <dev url> <repo>`, which will re-measure on the dev server, or apply it by hand. The CSS uses the live page's class names; the real change belongs in the components that render them.

## Caveats

The heatmap is a prediction of where a first glance lands, from DeepGaze IIE and a location prior fitted on UI eye tracking. It reacts to contrast, size, faces, text, and position and knows nothing about intent. On held-out UI screenshots its top hotspot lands where people looked about two times in three. Treat the gain as a strong hint to confirm with real users, not as a measurement of them.
