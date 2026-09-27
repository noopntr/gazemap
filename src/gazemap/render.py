"""Heatmap and overlay images."""

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from gazemap.hotspots import Hotspot

# Blue -> cyan -> green -> yellow -> red, applied to attention in [0, 1].
_STOPS = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
_COLORS = np.array(
    [[0, 0, 140], [0, 160, 255], [0, 220, 90], [255, 230, 0], [230, 20, 20]],
    dtype=np.float64,
)


def colormap(unit: np.ndarray) -> np.ndarray:
    """Map values in [0, 1] to RGB float colors, shape (..., 3)."""
    unit = np.clip(unit, 0.0, 1.0)
    return np.stack([np.interp(unit, _STOPS, _COLORS[:, c]) for c in range(3)], axis=-1)


def render_heatmap(unit: np.ndarray) -> Image.Image:
    """Grayscale image of the attention map, peak at 255."""
    return Image.fromarray(np.round(np.clip(unit, 0, 1) * 255).astype(np.uint8), mode="L")


def render_overlay(
    screenshot: np.ndarray,
    unit: np.ndarray,
    hotspots: list[Hotspot],
    alpha: float = 0.65,
) -> Image.Image:
    """Blend the colored attention map over the screenshot and mark hotspots by rank.

    Blend strength follows attention, so regions with no attention show the page as is.
    """
    base = screenshot.astype(np.float64)
    weight = (alpha * np.clip(unit, 0, 1))[..., None]
    blended = base * (1 - weight) + colormap(unit) * weight
    image = Image.fromarray(np.round(blended).astype(np.uint8), mode="RGB")

    draw = ImageDraw.Draw(image)
    # markers scale with the viewport width, so full-page overlays keep the same size
    radius = max(10, image.size[0] // 80)
    font = ImageFont.load_default(size=max(12, int(radius * 1.3)))
    for spot in hotspots:
        x, y, w, h = spot.bbox
        draw.rectangle([x, y, x + w - 1, y + h - 1], outline=(255, 255, 255), width=2)
        draw.rectangle([x - 1, y - 1, x + w, y + h], outline=(0, 0, 0), width=1)
        draw.ellipse(
            [spot.x - radius, spot.y - radius, spot.x + radius, spot.y + radius],
            fill=(0, 0, 0),
            outline=(255, 255, 255),
            width=2,
        )
        draw.text((spot.x, spot.y), str(spot.rank), fill=(255, 255, 255), font=font, anchor="mm")
    return image
