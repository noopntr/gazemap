"""Peak extraction from an attention probability map."""

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from gazemap.maps import normalize_unit


@dataclass
class Hotspot:
    rank: int
    x: int
    y: int
    bbox: tuple[int, int, int, int]  # x, y, width, height in map pixels
    share: float  # fraction of total attention inside the region
    peak: float  # peak value relative to the global maximum (1.0 for rank 1)


def find_hotspots(
    prob: np.ndarray,
    top: int = 5,
    min_distance: int | None = None,
    region_fraction: float = 0.5,
    min_peak: float = 0.05,
    min_share: float = 0.01,
    max_candidates: int = 200,
) -> list[Hotspot]:
    """Greedy non-maximum suppression over ``prob``.

    Only local maxima are candidates. Peaks closer than ``min_distance`` to an
    earlier peak, or below ``min_peak`` of the global maximum, are dropped. Every
    pixel is then assigned to the local maximum it climbs to, maxima suppressed by a
    candidate count as part of that candidate, and a candidate's region is the
    connected part of its own basin that stays above ``region_fraction`` of its peak.
    Candidates whose region holds less than ``min_share`` of the attention are
    skipped, and the first ``top`` survivors are returned in order of peak height.
    Regions never overlap or enclose another hotspot.
    """
    height, width = prob.shape
    if min_distance is None:
        min_distance = max(1, round(0.05 * max(height, width)))

    unit = normalize_unit(prob)
    local_max = ndimage.maximum_filter(unit, size=3, mode="nearest") == unit
    candidates = np.where(local_max, unit, -1.0)
    ys, xs = np.mgrid[0:height, 0:width]
    owner = np.zeros(prob.shape, dtype=np.int32)  # which candidate each local maximum belongs to

    peaks: list[tuple[int, int, float]] = []
    while len(peaks) < max_candidates:
        peak_value = float(candidates.max())
        if peak_value < min_peak:
            break
        py, px = np.unravel_index(int(np.argmax(candidates)), prob.shape)
        peaks.append((int(py), int(px), peak_value))
        nearby = (xs - px) ** 2 + (ys - py) ** 2 <= min_distance**2
        owner[nearby & local_max & (owner == 0)] = len(peaks)
        candidates[nearby] = -1.0
    if not peaks:
        return []

    basin = owner.ravel()[_climb_to_maximum(unit)]

    spots: list[Hotspot] = []
    for index, (py, px, peak_value) in enumerate(peaks, start=1):
        if len(spots) == top:
            break
        above = (basin == index) & (unit >= region_fraction * peak_value)
        labels, _ = ndimage.label(above)
        region = labels == labels[py, px]
        share = float(prob[region].sum())
        if share < min_share:
            continue
        region_ys, region_xs = np.nonzero(region)
        bbox = (
            int(region_xs.min()),
            int(region_ys.min()),
            int(region_xs.max() - region_xs.min() + 1),
            int(region_ys.max() - region_ys.min() + 1),
        )
        spots.append(Hotspot(rank=len(spots) + 1, x=px, y=py, bbox=bbox, share=share, peak=peak_value))
    return spots


def _climb_to_maximum(unit: np.ndarray) -> np.ndarray:
    """For every pixel, the flat index of the local maximum reached by steepest ascent."""
    height, width = unit.shape
    padded = np.pad(unit, 1, mode="constant", constant_values=-np.inf)
    index = np.arange(height * width).reshape(height, width)
    padded_index = np.pad(index, 1, mode="constant", constant_values=0)
    best_value = unit.copy()
    parent = index.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            neighbour = padded[1 + dy : 1 + dy + height, 1 + dx : 1 + dx + width]
            better = neighbour > best_value
            best_value = np.where(better, neighbour, best_value)
            parent = np.where(better, padded_index[1 + dy : 1 + dy + height, 1 + dx : 1 + dx + width], parent)
    root = parent.ravel()
    while True:  # pointer jumping: converges in O(log path length) passes
        jumped = root[root]
        if np.array_equal(jumped, root):
            return root.reshape(height, width)
        root = jumped
