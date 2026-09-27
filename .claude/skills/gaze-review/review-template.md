# Attention review: <url>

**Goal:** <what the user said a first-time visitor should look at first>, measured as `<selector>`.
Captured <above the fold | full page, N screens> on desktop 1440x900 and mobile 390x844<, with `<hidden selector>` hidden>.

## Verdict

| Viewport | Target share | Target rank | Strongest competitor | Its share |
|---|---|---|---|---|
| Desktop | 4.2% | hotspot 3 | span.hero "for rent in Georgia." | 12.2% |
| Mobile | 1.1% | none | span.hero "for rent in Georgia." | 28.3% |

One paragraph: does the target win, lose, or split the first look, by how much, and whether desktop and mobile agree.

## What draws the first look

Per viewport, the top hotspots as a short list: rank, element with its text, share, and the cause in a few words. Then one sentence on what drew nothing that a visitor would need.

## What steals attention from the target, and why

Ranked list of competitors. For each: element and text, share per viewport, the cause from the taxonomy, and the evidence (box size, color, position, content).

## Suggestions, in priority order

1. **<Concrete change>.** Addresses hotspot N (<element>, <share>). Expected effect: <what should happen to the target's share and why>.
2. ...

## Verify

After changing the page, re-run:

```bash
uv run gazemap analyze <url> --viewport both --target "<selector>"
```

Compare the target's share with the verdict table above. A change that does not move it is not a fix.

## Caveats

The heatmap is a prediction from DeepGaze IIE, a model trained on photographs, of where a first glance lands. It reacts to contrast, size, faces, text, and position, it knows nothing about intent or reading order, and its MIT1003 prior pulls attention toward the middle of each viewport. Treat the numbers as a first-impression signal to check against your own judgment, not as a measurement of users.
