import numpy as np
import pytest

from gazemap.metrics import auc_judd, cc, hotspot_hit, kld, nss, sim


def gaussian(shape, cx, cy, sigma):
    ys, xs = np.mgrid[0 : shape[0], 0 : shape[1]]
    return np.exp(-((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * sigma**2))


def fixations(shape, points):
    fix = np.zeros(shape, dtype=bool)
    for x, y in points:
        fix[y, x] = True
    return fix


def test_nss_is_high_when_prediction_peaks_on_fixations_and_zero_for_flat_maps():
    pred = gaussian((50, 80), 20, 25, 3)
    fix = fixations(pred.shape, [(20, 25), (21, 25)])
    assert nss(pred, fix) > 5
    assert nss(np.ones((50, 80)), fix) == 0.0
    assert nss(pred, fixations(pred.shape, [(75, 45)])) < 0


def test_cc_is_pearson_correlation():
    a = gaussian((40, 40), 10, 10, 5)
    assert cc(a, a) == pytest.approx(1.0)
    assert cc(a, -a) == pytest.approx(-1.0)
    assert cc(a, np.ones_like(a)) == 0.0


def test_sim_is_histogram_intersection_of_normalized_maps():
    a = gaussian((40, 40), 10, 10, 3)
    assert sim(a, a) == pytest.approx(1.0)
    b = np.zeros((40, 40))
    b[0:5, 30:40] = 1
    assert sim(a, b) == pytest.approx(0.0, abs=1e-6)


def test_kld_is_zero_for_identical_maps_and_positive_otherwise():
    a = gaussian((40, 40), 10, 10, 3)
    b = gaussian((40, 40), 30, 30, 3)
    assert kld(a, a) == pytest.approx(0.0, abs=1e-9)
    assert kld(b, a) > 1


def test_auc_judd_ranks_fixated_pixels_against_the_rest():
    pred = gaussian((50, 80), 20, 25, 4)
    near = fixations(pred.shape, [(20, 25), (22, 26), (19, 23)])
    far = fixations(pred.shape, [(78, 2), (1, 48)])
    assert auc_judd(pred, near) > 0.99
    # Judd's curve is interpolated from the origin, so the worst placement scores just under chance, not 0
    assert auc_judd(pred, far) < 0.5
    rng = np.random.default_rng(0)
    random_fix = fixations(pred.shape, [(int(x), int(y)) for x, y in zip(rng.integers(0, 80, 400), rng.integers(0, 50, 400))])
    assert auc_judd(rng.random((50, 80)), random_fix) == pytest.approx(0.5, abs=0.05)


def test_hotspot_hit_checks_the_top_peak_against_the_humans_top_region():
    human = gaussian((50, 80), 60, 20, 5)
    assert hotspot_hit(gaussian((50, 80), 61, 21, 5), human) is True
    assert hotspot_hit(gaussian((50, 80), 10, 40, 5), human) is False
