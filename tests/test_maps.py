import numpy as np
import pytest

from gazemap.maps import (
    fit_long_side,
    log_density_to_probability,
    normalize_unit,
    resize_probability,
)


def test_log_density_to_probability_sums_to_one():
    rng = np.random.default_rng(0)
    log_density = rng.normal(size=(40, 60))
    prob = log_density_to_probability(log_density)
    assert prob.shape == (40, 60)
    assert prob.min() >= 0
    assert prob.sum() == pytest.approx(1.0)


def test_log_density_to_probability_ignores_constant_offset():
    rng = np.random.default_rng(1)
    log_density = rng.normal(size=(20, 30))
    a = log_density_to_probability(log_density)
    b = log_density_to_probability(log_density + 123.0)
    np.testing.assert_allclose(a, b, rtol=1e-6)


def test_fit_long_side_downscales_desktop_viewport():
    width, height, scale = fit_long_side(1440, 900, target=1024)
    assert (width, height) == (1024, 640)
    assert scale == pytest.approx(1024 / 1440)


def test_fit_long_side_upscales_mobile_viewport():
    width, height, scale = fit_long_side(390, 844, target=1024)
    assert (width, height) == (473, 1024)
    assert scale == pytest.approx(1024 / 844)


def test_resize_probability_keeps_mass_and_moves_peak_with_scale():
    prob = np.zeros((50, 100))
    ys, xs = np.mgrid[0:50, 0:100]
    prob = np.exp(-((xs - 70) ** 2 + (ys - 20) ** 2) / (2 * 3.0**2))
    prob /= prob.sum()
    resized = resize_probability(prob, width=200, height=100)
    assert resized.shape == (100, 200)
    assert resized.sum() == pytest.approx(1.0)
    peak_y, peak_x = np.unravel_index(np.argmax(resized), resized.shape)
    assert abs(peak_x - 140) <= 1
    assert abs(peak_y - 40) <= 1


def test_normalize_unit_scales_max_to_one():
    prob = np.array([[0.1, 0.4], [0.2, 0.3]])
    unit = normalize_unit(prob)
    assert unit.max() == pytest.approx(1.0)
    assert unit.min() == pytest.approx(0.25)


def test_stitch_windows_places_each_screen_at_its_offset_with_equal_weight():
    from gazemap.maps import stitch_windows

    a = np.zeros((10, 20))
    a[2, 5] = 1.0
    b = np.zeros((10, 20))
    b[7, 15] = 1.0
    stitched = stitch_windows([(0, a), (10, b)], height=20, width=20)
    assert stitched.shape == (20, 20)
    assert stitched.sum() == pytest.approx(1.0)
    assert stitched[2, 5] == pytest.approx(0.5)
    assert stitched[17, 15] == pytest.approx(0.5)


def test_stitch_windows_averages_overlapping_rows():
    from gazemap.maps import stitch_windows

    a = np.full((10, 4), 1 / 40)
    b = np.full((10, 4), 1 / 40)
    stitched = stitch_windows([(0, a), (5, b)], height=15, width=4)
    assert stitched.sum() == pytest.approx(1.0)
    # rows 5..9 are covered twice and must not be counted twice
    np.testing.assert_allclose(stitched[5:10], stitched[0:5])
    np.testing.assert_allclose(stitched[10:15], stitched[0:5])
