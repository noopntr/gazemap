# Attention fix: <url>

**Suggestion applied:** <the suggestion from review.md, quoted or paraphrased>, from `<path to review.md>`.
**Target:** `<selector>`. **Branch:** `gaze-fix/<name>` in `<repo>`, uncommitted.

## Result

| Viewport | Target | Before | After | Change |
|---|---|---|---|---|
| Desktop | `button:has-text("Search")` | 0.6% | 4.8% | +4.2 points |
| Mobile | `button:has-text("Search")` | 0.0% | 6.1% | +6.1 points |

One paragraph: improved, unchanged, or worse, on which viewport, and whether the top hotspots moved.

## Change

Files changed: `<file>` (<n> lines).

```diff
<the diff>
```

## Before and after

Side-by-side overlays: `compare/<slug>/desktop.png`, `compare/<slug>/mobile.png`. What the eye lands on before, what it lands on after, in two or three sentences.

## Top hotspots

Before: <#1 share element, #2 ..., #3 ...>
After: <#1 share element, #2 ..., #3 ...>

## Next

Keep: commit the branch yourself. Revert: `git checkout -- <files>`, switch back, delete the branch. Or run `/gaze-fix` again for the next suggestion.
