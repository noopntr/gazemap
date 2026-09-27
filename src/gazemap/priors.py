"""Fixation priors: where people look regardless of content, as a log density over the unit square.

``mit1003`` is DeepGaze's own prior, fitted on photographs; it favours the center.
``ueyes`` is fitted here from the fixations on the UEyes training screenshots (Jiang et
al., CHI 2023, CC BY 4.0); people look at interfaces with a top-left bias instead.
"""

from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.special import logsumexp

PACKAGED = {"ueyes": Path(__file__).parent / "saliency" / "centerbias_ueyes.npy"}


def fit_prior(fixmap_paths: list[Path], grid: int = 256, sigma: float = 0.04) -> np.ndarray:
    """Pool fixations from maps of any size in normalized coordinates, blur, return log density.

    ``sigma`` is the Gaussian blur in units of the square's side. Each map counts once,
    however many fixations it holds, so busy screens do not dominate the prior.
    """
    from gazemap.benchmark import load_fixations

    counts = np.zeros((grid, grid), dtype=np.float64)
    for path in fixmap_paths:
        points = load_fixations(Path(path), (grid, grid))
        total = points.sum()
        if total:
            counts += points / total
    density = ndimage.gaussian_filter(counts, sigma * grid, mode="nearest")
    density += density.max() * 1e-4  # nowhere is impossible
    log_density = np.log(density)
    return log_density - logsumexp(log_density)


def load_prior(name: str) -> np.ndarray:
    path = PACKAGED.get(name)
    if path is None or not path.exists():
        raise ValueError(f"no packaged prior named {name!r}")
    return np.load(path)


def prior_at(log_density: np.ndarray, width: int, height: int) -> np.ndarray:
    """Rescale a log-density template to an image size and renormalize."""
    scaled = np.asarray(Image.fromarray(log_density.astype(np.float32), mode="F").resize((width, height), Image.BILINEAR))
    return (scaled - logsumexp(scaled)).astype(np.float32)
