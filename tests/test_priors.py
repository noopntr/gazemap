import numpy as np
import pytest
from PIL import Image

from gazemap.priors import fit_prior, load_prior


def write_fixmap(path, size, points):
    fix = np.zeros((size[1], size[0]), dtype=np.uint8)
    for x, y in points:
        fix[y, x] = 255
    Image.fromarray(fix).save(path)


def test_prior_is_a_normalized_log_density_that_follows_the_fixations(tmp_path):
    # fixations cluster in the top-left of screens of different sizes
    paths = []
    for i, size in enumerate([(200, 100), (100, 200), (300, 300)]):
        path = tmp_path / f"f{i}.png"
        w, h = size
        write_fixmap(path, size, [(int(0.2 * w), int(0.15 * h)), (int(0.25 * w), int(0.2 * h)), (int(0.7 * w), int(0.8 * h))])
        paths.append(path)
    log_density = fit_prior(paths, grid=64, sigma=0.05)
    assert log_density.shape == (64, 64)
    assert np.exp(log_density).sum() == pytest.approx(1.0)
    peak_y, peak_x = np.unravel_index(int(np.argmax(log_density)), log_density.shape)
    assert peak_x < 32 and peak_y < 32  # top-left, where two of three fixations per screen fell
    assert log_density[48, 45] > log_density[5, 60]  # the bottom-right fixation leaves a trace


def test_packaged_ueyes_prior_loads_with_top_left_peak():
    log_density = load_prior("ueyes")
    assert log_density.ndim == 2
    assert np.exp(log_density.astype(np.float64)).sum() == pytest.approx(1.0, abs=1e-3)
    peak_y, peak_x = np.unravel_index(int(np.argmax(log_density)), log_density.shape)
    h, w = log_density.shape
    assert peak_x < w / 2 and peak_y < h / 2
