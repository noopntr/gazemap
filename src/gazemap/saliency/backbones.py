"""DeepGaze IIE backbones rebuilt without their ImageNet weight downloads.

The DeepGaze IIE checkpoint already contains every backbone's weights, so the
architectures are built empty here and filled by a strict state-dict load.
Module nesting mirrors deepgaze_pytorch.features so the checkpoint keys match.
"""

from collections import OrderedDict

import torch
import torch.nn as nn
import torchvision
from deepgaze_pytorch.features.efficientnet_pytorch import EfficientNet


class Normalizer(nn.Module):
    """ImageNet normalization of a 0..255 RGB tensor, in float32."""

    def __init__(self):
        super().__init__()
        mean = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32).view(3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32).view(3, 1, 1)
        self.register_buffer("mean", mean, persistent=False)
        self.register_buffer("std", std, persistent=False)

    def forward(self, tensor):
        return (tensor / 255.0 - self.mean) / self.std


class ShapeNetC(nn.Sequential):
    def __init__(self):
        resnet = torchvision.models.resnet50(weights=None)
        super().__init__(Normalizer(), nn.Sequential(OrderedDict([("module", resnet)])))


class EfficientNetB5(nn.Sequential):
    def __init__(self):
        super().__init__(Normalizer(), EfficientNet.from_name("efficientnet-b5"))


class DenseNet201(nn.Sequential):
    def __init__(self):
        super().__init__(Normalizer(), torchvision.models.densenet201(weights=None))


class ResNeXt50(nn.Sequential):
    def __init__(self):
        super().__init__(Normalizer(), torchvision.models.resnext50_32x4d(weights=None))


# DeepGaze IIE backbone class -> local replacement
REPLACEMENTS = {
    "deepgaze_pytorch.features.shapenet.RGBShapeNetC": f"{__name__}.ShapeNetC",
    "deepgaze_pytorch.features.efficientnet.RGBEfficientNetB5": f"{__name__}.EfficientNetB5",
    "deepgaze_pytorch.features.densenet.RGBDenseNet201": f"{__name__}.DenseNet201",
    "deepgaze_pytorch.features.resnext.RGBResNext50": f"{__name__}.ResNeXt50",
}
