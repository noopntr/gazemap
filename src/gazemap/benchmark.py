"""Score saliency models against human eye tracking on UI screenshots."""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from gazemap.datasets import CATEGORIES, Sample
from gazemap.maps import fit_long_side
from gazemap.metrics import auc_judd, cc, hotspot_hit, kld, nss, sim

METRICS = ("auc_judd", "nss", "cc", "kld", "sim", "hotspot_hit")


class CenterBaseline:
    """Predicts only a prior, ignoring the image.

    ``mit1003`` uses DeepGaze's photograph prior if downloaded, else a centered Gaussian;
    ``ueyes`` uses the packaged UI prior.
    """

    device = "cpu"

    def __init__(self, prior: str = "mit1003"):
        template = None
        if prior == "ueyes":
            from gazemap.priors import load_prior

            template = load_prior("ueyes")
        else:
            from gazemap.saliency.deepgaze import default_model_dir

            path = default_model_dir() / "centerbias_mit1003.npy"
            template = np.load(path) if path.exists() else None
        self.template = template
        self.name = "UI prior only" if prior == "ueyes" else "center prior only"

    def predict(self, image: np.ndarray, centerbias: str = "mit1003") -> np.ndarray:
        height, width = image.shape[:2]
        if self.template is not None:
            log = np.asarray(Image.fromarray(self.template.astype(np.float32), mode="F").resize((width, height), Image.BILINEAR))
            prob = np.exp(log - log.max())
        else:
            ys, xs = np.mgrid[0:height, 0:width]
            prob = np.exp(-(((xs - width / 2) / (0.3 * width)) ** 2 + ((ys - height / 2) / (0.3 * height)) ** 2) / 2)
        return prob / prob.sum()


def score_sample(prediction: np.ndarray, fix: np.ndarray, human: np.ndarray) -> dict:
    return {
        "auc_judd": auc_judd(prediction, fix),
        "nss": nss(prediction, fix),
        "cc": cc(prediction, human),
        "kld": kld(prediction, human),
        "sim": sim(prediction, human),
        "hotspot_hit": float(hotspot_hit(prediction, human)),
    }


def _load_gray(path: Path, size: tuple[int, int] | None = None) -> np.ndarray:
    image = Image.open(path).convert("L")
    if size is not None and image.size != size:
        image = image.resize(size, Image.BILINEAR)
    return np.asarray(image, dtype=np.float64)


def load_fixations(path: Path, size: tuple[int, int]) -> np.ndarray:
    """Boolean fixation map at ``size`` (width, height) from a UEyes fixation map.

    Fixations are single bright pixels, but a third of UEyes maps are JPEGs whose
    compression smears each one into a blotch. Taking local maxima above a floor
    recovers one point per fixation; the points are then rescaled, never the map.
    """
    from scipy import ndimage

    raw = np.asarray(Image.open(path).convert("L"), dtype=np.float64)
    peaks = (raw == ndimage.maximum_filter(raw, size=5)) & (raw >= 64)
    ys, xs = np.nonzero(peaks)
    width, height = size
    fix = np.zeros((height, width), dtype=bool)
    fix[
        np.clip((ys * height / raw.shape[0]).astype(int), 0, height - 1),
        np.clip((xs * width / raw.shape[1]).astype(int), 0, width - 1),
    ] = True
    return fix


def run_benchmark(
    samples: list[Sample],
    models: dict[str, tuple[object, str]],
    out: str | Path,
    max_side: int = 1024,
) -> dict:
    """Score each ``label -> (model, centerbias)`` on every sample, grouped by UI category.

    Ground truth and predictions are compared at the ground truth's own resolution,
    capped at ``max_side`` on the long side to keep the metrics fast on tall pages.
    """
    per_image = []
    for index, sample in enumerate(samples, start=1):
        image = np.asarray(Image.open(sample.image).convert("RGB"))
        human_full = Image.open(sample.heatmap)
        width, height, _ = fit_long_side(*human_full.size, target=min(max_side, max(human_full.size)))
        human = _load_gray(sample.heatmap, (width, height))
        fix = load_fixations(sample.fixmap, (width, height))
        for label, (model, centerbias) in models.items():
            prediction = model.predict(image, centerbias=centerbias)
            if prediction.shape != (height, width):
                prediction = np.asarray(Image.fromarray(prediction.astype(np.float32), mode="F").resize((width, height), Image.BILINEAR))
            per_image.append({"image": sample.name, "category": sample.category, "model": label, **score_sample(prediction, fix, human)})
        print(f"\r  scored {index}/{len(samples)}", end="", file=sys.stderr)
    print(file=sys.stderr)

    summary: dict[str, dict] = {}
    for label in models:
        rows = [r for r in per_image if r["model"] == label]
        groups = {"all": rows} | {c: [r for r in rows if r["category"] == c] for c in CATEGORIES}
        summary[label] = {
            group: {"n": len(items), **{m: round(float(np.mean([r[m] for r in items])), 4) for m in METRICS}}
            for group, items in groups.items()
            if items
        }

    result = {"models": summary, "per_image": per_image}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def print_table(result: dict) -> None:
    header = f"{'model':<24} {'set':<8} {'n':>4} {'AUC':>6} {'NSS':>6} {'CC':>6} {'KLD':>6} {'SIM':>6} {'top-1 hit':>10}"
    print(header)
    print("-" * len(header))
    for label, groups in result["models"].items():
        for group, s in groups.items():
            print(
                f"{label:<24} {group:<8} {s['n']:>4} {s['auc_judd']:>6.3f} {s['nss']:>6.2f} {s['cc']:>6.3f} "
                f"{s['kld']:>6.2f} {s['sim']:>6.3f} {s['hotspot_hit'] * 100:>9.0f}%"
            )
        print()
