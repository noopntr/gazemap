import numpy as np
import pytest

from gazemap.hotspots import find_hotspots


def gaussian(shape, cx, cy, sigma, amplitude=1.0):
    ys, xs = np.mgrid[0 : shape[0], 0 : shape[1]]
    return amplitude * np.exp(-((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * sigma**2))


def as_probability(arr):
    return arr / arr.sum()


def test_finds_separated_peaks_ranked_by_height():
    prob = as_probability(gaussian((60, 100), 30, 20, 4) + gaussian((60, 100), 80, 40, 4, amplitude=0.6))
    spots = find_hotspots(prob, top=2)
    assert [s.rank for s in spots] == [1, 2]
    assert (spots[0].x, spots[0].y) == (30, 20)
    assert (spots[1].x, spots[1].y) == (80, 40)
    assert spots[0].share > spots[1].share > 0
    assert sum(s.share for s in spots) <= 1.0


def test_nms_merges_peaks_closer_than_min_distance():
    # two bumps 12 px apart with sigma 3: the saddle between them is below half maximum
    prob = as_probability(gaussian((60, 100), 50, 30, 3) + gaussian((60, 100), 62, 30, 3, amplitude=0.9))
    assert len(find_hotspots(prob, top=3, min_distance=2)) == 2
    assert len(find_hotspots(prob, top=3, min_distance=20)) == 1


def test_ignores_peaks_below_min_peak_fraction():
    prob = as_probability(gaussian((60, 100), 30, 30, 3) + gaussian((60, 100), 80, 30, 3, amplitude=0.02))
    assert len(find_hotspots(prob, top=3, min_peak=0.05, min_share=0.0)) == 1
    assert len(find_hotspots(prob, top=3, min_peak=0.01, min_share=0.0)) == 2


def test_bbox_covers_half_maximum_region_around_peak():
    prob = as_probability(gaussian((60, 100), 50, 30, 4))
    (spot,) = find_hotspots(prob, top=1)
    x, y, w, h = spot.bbox
    assert x <= spot.x < x + w
    assert y <= spot.y < y + h
    # full width at half maximum of a gaussian is about 2.355 * sigma
    assert 8 <= w <= 12
    assert 8 <= h <= 12


def test_share_is_attention_mass_inside_region():
    prob = as_probability(gaussian((80, 120), 60, 40, 5))
    (spot,) = find_hotspots(prob, top=1)
    # a 2D gaussian holds exactly half its mass inside the half-maximum contour
    assert spot.share == pytest.approx(0.5, abs=0.05)
    assert spot.peak == pytest.approx(1.0)


def test_returns_fewer_hotspots_when_map_has_no_more_peaks():
    prob = np.zeros((40, 40))
    prob[10, 10] = 1.0
    spots = find_hotspots(prob, top=5, min_distance=5)
    assert len(spots) == 1
    assert (spots[0].x, spots[0].y) == (10, 10)


def test_shoulder_peak_does_not_wrap_around_the_dominant_hotspot():
    # a small bump on the slope of a big blob: its half-maximum threshold is low in
    # absolute terms, so a naive region would ring the dominant peak and enclose it
    prob = as_probability(gaussian((60, 100), 50, 30, 10) + gaussian((60, 100), 68, 30, 2, amplitude=0.3))
    first, second = find_hotspots(prob, top=2, min_distance=5)
    assert (first.x, first.y) == (50, 30)
    assert 66 <= second.x <= 70
    x, y, w, h = second.bbox
    assert not (x <= first.x < x + w and y <= first.y < y + h), "second bbox encloses the first peak"
    assert w <= 12
    assert second.share < first.share


def test_peaks_with_negligible_share_give_way_to_the_next_peak():
    # a sharp needle on the slope of a big blob outranks a distant soft blob by height,
    # but its region holds almost no attention, so the soft blob should take the slot
    prob = as_probability(
        gaussian((60, 100), 30, 30, 10)
        + gaussian((60, 100), 50, 30, 1, amplitude=0.35)
        + gaussian((60, 100), 85, 30, 4, amplitude=0.4)
    )
    spots = find_hotspots(prob, top=2, min_distance=5, min_share=0.01)
    assert [(s.rank, s.x, s.y) for s in spots] == [(1, 30, 30), (2, 85, 30)]
    assert all(s.share >= 0.01 for s in spots)
    # without the floor the needle takes second place
    assert find_hotspots(prob, top=2, min_distance=5, min_share=0.0)[1].x == 50
