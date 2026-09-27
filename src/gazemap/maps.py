"""Conversions between the model's log density and screenshot-space attention maps."""

import numpy as np
from PIL import Image
from scipy.special import logsumexp


def fit_long_side(width: int, height: int, target: int = 1024) -> tuple[int, int, float]:
    """Size that puts the longer side at ``target`` pixels, keeping aspect ratio.

    Returns ``(width, height, scale)`` where ``scale`` maps screenshot pixels
    to model-input pixels.
    """
    scale = target / max(width, height)
    return max(1, round(width * scale)), max(1, round(height * scale)), scale


def log_density_to_probability(log_density: np.ndarray) -> np.ndarray:
    """Turn a (possibly unnormalized) log density into a map that sums to 1."""
    return np.exp(log_density - logsumexp(log_density))


def resize_probability(prob: np.ndarray, width: int, height: int) -> np.ndarray:
    """Bilinearly resize a probability map to ``(height, width)`` and renormalize."""
    image = Image.fromarray(prob.astype(np.float32), mode="F")
    resized = np.asarray(image.resize((width, height), Image.BILINEAR), dtype=np.float64)
    resized = np.clip(resized, 0, None)
    return resized / resized.sum()


def normalize_unit(prob: np.ndarray) -> np.ndarray:
    """Scale a non-negative map so its maximum is 1."""
    peak = prob.max()
    return prob / peak if peak > 0 else prob


def stitch_windows(windows: list[tuple[int, np.ndarray]], height: int, width: int) -> np.ndarray:
    """Combine per-screen probability maps into one page map that sums to 1.

    ``windows`` holds ``(top_offset, map)`` pairs. Rows covered by more than one
    window are averaged, so every screen carries equal weight.
    """
    total = np.zeros((height, width), dtype=np.float64)
    count = np.zeros((height, width), dtype=np.float64)
    for top, window in windows:
        rows = min(window.shape[0], height - top)
        total[top : top + rows] += window[:rows]
        count[top : top + rows] += 1
    stitched = np.divide(total, count, out=np.zeros_like(total), where=count > 0)
    return stitched / stitched.sum()
