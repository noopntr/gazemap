"""Standard saliency metrics (MIT/Tuebingen benchmark definitions) plus a gazemap-specific hit rate.

``pred`` is a non-negative saliency map, ``fix`` a boolean fixation map and ``human`` a
continuous human attention map, all the same shape.
"""

import numpy as np

EPS = np.finfo(np.float64).eps


def nss(pred: np.ndarray, fix: np.ndarray) -> float:
    """Normalized scanpath saliency: mean z-scored prediction at fixated pixels."""
    std = pred.std()
    if std == 0 or not fix.any():
        return 0.0
    return float(((pred - pred.mean()) / std)[fix].mean())


def cc(pred: np.ndarray, human: np.ndarray) -> float:
    """Pearson correlation between prediction and human map."""
    a, b = pred - pred.mean(), human - human.mean()
    denom = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / denom) if denom > 0 else 0.0


def sim(pred: np.ndarray, human: np.ndarray) -> float:
    """Similarity: histogram intersection of both maps normalized to sum 1."""
    p, q = _dist(pred), _dist(human)
    return float(np.minimum(p, q).sum())


def kld(pred: np.ndarray, human: np.ndarray) -> float:
    """KL divergence of the human distribution from the predicted one (lower is better)."""
    p, q = _dist(human), _dist(pred)
    return float((p * np.log(EPS + p / (q + EPS))).sum())


def auc_judd(pred: np.ndarray, fix: np.ndarray) -> float:
    """AUC with thresholds at the predicted values of fixated pixels (Judd et al.)."""
    values = pred.ravel()
    fixated = np.sort(values[fix.ravel()])[::-1]
    n_fix, n_pix = fixated.size, values.size
    if n_fix == 0 or n_fix == n_pix:
        return 0.5
    ordered = np.sort(values)
    # pixels at or above each threshold, via binary search on the sorted map
    above = n_pix - np.searchsorted(ordered, fixated, side="left")
    tp = np.concatenate([[0.0], np.arange(1, n_fix + 1) / n_fix, [1.0]])
    fp = np.concatenate([[0.0], (above - np.arange(1, n_fix + 1)) / (n_pix - n_fix), [1.0]])
    return float(np.trapezoid(tp, fp))


def hotspot_hit(pred: np.ndarray, human: np.ndarray, top_fraction: float = 0.1) -> bool:
    """Whether the predicted global peak lies in the top ``top_fraction`` of human attention pixels."""
    y, x = np.unravel_index(int(np.argmax(pred)), pred.shape)
    threshold = np.quantile(human, 1 - top_fraction)
    return bool(human[y, x] >= threshold and human[y, x] > human.min())


def _dist(m: np.ndarray) -> np.ndarray:
    m = np.clip(m.astype(np.float64), 0, None)
    total = m.sum()
    return m / total if total > 0 else np.full(m.shape, 1.0 / m.size)
