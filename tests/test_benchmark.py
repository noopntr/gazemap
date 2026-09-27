import json

import numpy as np
import pytest
from PIL import Image

from gazemap import cli
from gazemap.benchmark import CenterBaseline, run_benchmark
from gazemap.datasets import Sample


def gaussian(shape, cx, cy, sigma):
    ys, xs = np.mgrid[0 : shape[0], 0 : shape[1]]
    return np.exp(-((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * sigma**2))


@pytest.fixture
def tiny_dataset(tmp_path):
    """Four screenshots whose human attention sits on one red square each, off center."""
    samples = []
    for i, (category, cx, cy) in enumerate([("web", 30, 20), ("web", 90, 50), ("mobile", 25, 60), ("poster", 100, 15)]):
        image = np.full((80, 120, 3), 255, dtype=np.uint8)
        image[cy - 5 : cy + 5, cx - 5 : cx + 5] = (220, 20, 40)
        heat = gaussian((80, 120), cx, cy, 6)
        fix = np.zeros((80, 120), dtype=np.uint8)
        fix[cy, cx] = fix[cy + 1, cx] = fix[cy, cx + 2] = 255
        paths = [tmp_path / f"{kind}{i}.png" for kind in ("img", "fix", "heat")]
        Image.fromarray(image).save(paths[0])
        Image.fromarray(fix).save(paths[1])
        Image.fromarray(np.round(heat * 255).astype(np.uint8)).save(paths[2])
        samples.append(Sample(f"s{i}.png", category, *paths))
    return samples


class RedModel:
    """Finds the red square, like a perfect saliency model would on these images."""

    name = "red"
    device = "cpu"

    def predict(self, image, centerbias="mit1003"):
        red = (image[..., 0] > 200) & (image[..., 1] < 60)
        ys, xs = np.nonzero(red)
        prob = gaussian(image.shape[:2], xs.mean(), ys.mean(), 6)
        return prob / prob.sum()


def test_benchmark_scores_models_per_category_and_overall(tiny_dataset, tmp_path):
    results = run_benchmark(
        tiny_dataset,
        {"red": (RedModel(), "uniform"), "center": (CenterBaseline(), "mit1003")},
        out=tmp_path / "bench",
    )
    red, center = results["models"]["red"], results["models"]["center"]
    assert set(red) == {"all", "web", "mobile", "poster"}
    assert red["all"]["n"] == 4 and red["web"]["n"] == 2
    for metric in ("auc_judd", "nss", "cc", "kld", "sim", "hotspot_hit"):
        assert metric in red["all"]
    # the model that finds the object must beat the center prior on every metric
    assert red["all"]["nss"] > center["all"]["nss"]
    assert red["all"]["cc"] > center["all"]["cc"]
    assert red["all"]["auc_judd"] > center["all"]["auc_judd"]
    assert red["all"]["kld"] < center["all"]["kld"]
    assert red["all"]["hotspot_hit"] == 1.0
    saved = json.loads((tmp_path / "bench" / "results.json").read_text())
    assert saved["models"]["red"]["all"]["n"] == 4
    assert len(saved["per_image"]) == 8


def test_benchmark_cli_prints_a_table(tiny_dataset, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_model", lambda name, device: RedModel())
    monkeypatch.setattr(cli, "load_ueyes", lambda root, split, duration: tiny_dataset)
    code = cli.main(["benchmark", "--data", str(tmp_path), "--out", str(tmp_path / "bench")])
    assert code == 0
    out = capsys.readouterr().out
    for label in ("deepgaze2e (mit1003)", "deepgaze2e (uniform)", "center prior only", "AUC", "NSS", "CC", "KLD", "SIM", "top-1 hit"):
        assert label in out
    assert "web" in out and "mobile" in out and "poster" in out


def test_fixations_from_a_jpeg_map_ignore_compression_noise(tmp_path):
    from gazemap.benchmark import load_fixations

    fix = np.zeros((60, 60), dtype=np.uint8)
    fix[20, 20] = fix[40, 45] = 255
    Image.fromarray(fix).save(tmp_path / "fix.jpg", quality=75)
    noisy = np.asarray(Image.open(tmp_path / "fix.jpg"))
    assert (noisy > 0).sum() > 2  # the JPEG smears each fixation into a blotch
    points = load_fixations(tmp_path / "fix.jpg", (60, 60))
    assert points.sum() == 2
    assert points[20, 20] and points[40, 45]


def test_center_baseline_can_use_the_ui_prior(tmp_path):
    image = np.zeros((400, 300, 3), dtype=np.uint8)
    prob = CenterBaseline(prior="ueyes").predict(image)
    assert prob.shape == (400, 300)
    assert prob.sum() == pytest.approx(1.0)
    y, x = np.unravel_index(int(np.argmax(prob)), prob.shape)
    assert x < 150 and y < 200
    assert CenterBaseline(prior="ueyes").name == "UI prior only"


def test_benchmark_cli_compares_all_priors(tiny_dataset, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_model", lambda name, device: RedModel())
    monkeypatch.setattr(cli, "load_ueyes", lambda root, split, duration: tiny_dataset)
    assert cli.main(["benchmark", "--data", str(tmp_path), "--out", str(tmp_path / "bench")]) == 0
    out = capsys.readouterr().out
    assert "deepgaze2e (ueyes)" in out and "UI prior only" in out
