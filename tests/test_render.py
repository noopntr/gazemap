import numpy as np

from gazemap.hotspots import Hotspot
from gazemap.render import render_heatmap, render_overlay


def unit_map():
    ys, xs = np.mgrid[0:60, 0:100]
    return np.exp(-((xs - 70) ** 2 + (ys - 20) ** 2) / (2 * 5.0**2))


def test_heatmap_is_grayscale_with_peak_at_255():
    image = render_heatmap(unit_map())
    assert image.mode == "L"
    assert image.size == (100, 60)
    assert image.getpixel((70, 20)) == 255
    assert image.getpixel((5, 55)) == 0


def test_overlay_keeps_screenshot_where_attention_is_zero():
    screenshot = np.full((60, 100, 3), 40, dtype=np.uint8)
    image = render_overlay(screenshot, unit_map(), [])
    assert image.mode == "RGB"
    assert image.size == (100, 60)
    assert image.getpixel((5, 55)) == (40, 40, 40)
    assert image.getpixel((70, 20)) != (40, 40, 40)


def test_overlay_draws_hotspot_markers():
    screenshot = np.full((60, 100, 3), 40, dtype=np.uint8)
    spot = Hotspot(rank=1, x=70, y=20, bbox=(60, 12, 20, 16), share=0.4, peak=1.0)
    plain = np.asarray(render_overlay(screenshot, np.zeros((60, 100)), []))
    marked = np.asarray(render_overlay(screenshot, np.zeros((60, 100)), [spot]))
    assert not np.array_equal(plain, marked)
    # the bbox outline touches its top-left corner, the rest of the page is untouched
    assert not np.array_equal(plain[12, 60], marked[12, 60])
    assert np.array_equal(plain[55, 5], marked[55, 5])


def test_marker_size_follows_width_not_page_height():
    spot = Hotspot(rank=1, x=200, y=150, bbox=(196, 146, 8, 8), share=0.4, peak=1.0)
    short = np.asarray(render_overlay(np.full((300, 400, 3), 40, dtype=np.uint8), np.zeros((300, 400)), [spot]))
    tall = np.asarray(render_overlay(np.full((3000, 400, 3), 40, dtype=np.uint8), np.zeros((3000, 400)), [spot]))
    # the marker is the same size in both, so a pixel 30 px right of the centre is untouched in each
    assert short[150, 230].tolist() == [40, 40, 40]
    assert tall[150, 230].tolist() == [40, 40, 40]
    # and the marker itself is drawn in both
    assert short[150, 200].tolist() != [40, 40, 40]
    assert tall[150, 200].tolist() != [40, 40, 40]
