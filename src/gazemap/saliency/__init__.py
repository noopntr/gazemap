"""Saliency model interface. Models take an RGB screenshot and return a probability map."""

from typing import Protocol

import numpy as np


class SaliencyModel(Protocol):
    name: str
    device: str

    def predict(self, image: np.ndarray, centerbias: str = "ueyes") -> np.ndarray:
        """Return a (height, width) map that sums to 1, at the image's own size."""
        ...


MODEL_NAMES = ("deepgaze2e",)
CENTERBIAS_KINDS = ("mit1003", "ueyes", "uniform")


class ModelDownloadError(Exception):
    """A model file is missing and could not be fetched."""


def load_model(name: str = "deepgaze2e", device: str = "auto", model_dir=None) -> SaliencyModel:
    if name == "deepgaze2e":
        from gazemap.saliency.deepgaze import DeepGazeIIE

        return DeepGazeIIE(device=device, model_dir=model_dir)
    raise ValueError(f"unknown saliency model: {name!r} (available: {', '.join(MODEL_NAMES)})")
