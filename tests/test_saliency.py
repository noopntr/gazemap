import numpy as np
import pytest

from gazemap.saliency import load_model
from gazemap.saliency.deepgaze import DeepGazeIIE, WEIGHT_FILES, default_model_dir

pytestmark = pytest.mark.smoke


def weights_present():
    return all((default_model_dir() / name).exists() for name in WEIGHT_FILES)


needs_weights = pytest.mark.skipif(not weights_present(), reason="DeepGaze IIE weights not downloaded")


def red_square_image(width=480, height=300, cx=120, cy=80, size=40):
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    image[cy - size // 2 : cy + size // 2, cx - size // 2 : cx + size // 2] = (220, 20, 40)
    return image


@needs_weights
def test_checkpoint_loads_strictly_into_rebuilt_architecture():
    model = DeepGazeIIE(device="cpu")
    assert model.name == "deepgaze2e"
    assert sum(1 for p in model.module.parameters()) > 0


@needs_weights
def test_predict_returns_probability_map_at_image_size_with_peak_on_salient_object():
    model = DeepGazeIIE(device="cpu")
    image = red_square_image()
    prob = model.predict(image, centerbias="uniform")
    assert prob.shape == (300, 480)
    assert prob.sum() == pytest.approx(1.0, abs=1e-4)
    peak_y, peak_x = np.unravel_index(int(np.argmax(prob)), prob.shape)
    assert abs(peak_x - 120) < 30
    assert abs(peak_y - 80) < 30


@needs_weights
@pytest.mark.skipif(not __import__("torch").backends.mps.is_available(), reason="MPS not available")
def test_predict_on_mps_matches_cpu():
    image = red_square_image()
    cpu = DeepGazeIIE(device="cpu").predict(image, centerbias="mit1003")
    mps_model = DeepGazeIIE(device="mps")
    mps = mps_model.predict(image, centerbias="mit1003")
    assert mps_model.device == "mps"
    np.testing.assert_allclose(mps, cpu, atol=1e-4)


def test_load_model_rejects_unknown_name():
    with pytest.raises(ValueError, match="unknown saliency model"):
        load_model("nope", device="cpu")
