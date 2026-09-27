"""DeepGaze IIE (Linardos et al. 2021) as a gazemap saliency model."""

import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Let PyTorch route individual unsupported ops to the CPU instead of failing.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import numpy as np  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402
from scipy.special import logsumexp  # noqa: E402

from gazemap.maps import fit_long_side, log_density_to_probability, resize_probability  # noqa: E402
from gazemap.saliency import CENTERBIAS_KINDS, ModelDownloadError  # noqa: E402

RELEASE = "https://github.com/matthias-k/DeepGaze/releases/download/v1.0.0"
WEIGHT_FILES = {
    "deepgaze2e.pth": f"{RELEASE}/deepgaze2e.pth",
    "centerbias_mit1003.npy": f"{RELEASE}/centerbias_mit1003.npy",
}
MIXTURE_COMPONENTS = 30  # 3 instances x 10 cross-validation folds per backbone


def default_model_dir() -> Path:
    env = os.environ.get("GAZEMAP_MODEL_DIR")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[3] / "models"


def ensure_file(model_dir: Path, name: str) -> Path:
    """Return the path of a model file, downloading it first if missing."""
    path = model_dir / name
    if path.exists():
        return path
    url = WEIGHT_FILES[name]
    model_dir.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    print(f"downloading {name} from {url}", file=sys.stderr)
    try:
        urllib.request.urlretrieve(url, partial, reporthook=_progress(name))
        partial.replace(path)
    except (urllib.error.URLError, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise ModelDownloadError(
            f"could not download {name}: {exc}\n"
            f"download it manually from {url} and save it as {path}"
        ) from exc
    finally:
        print(file=sys.stderr)
    return path


def _progress(name):
    def hook(blocks, block_size, total):
        if total > 0:
            done = min(100, blocks * block_size * 100 // total)
            print(f"\r  {name}: {done}%", end="", file=sys.stderr)

    return hook


def pick_device(requested: str) -> str:
    if requested == "auto":
        return "mps" if torch.backends.mps.is_available() else "cpu"
    if requested == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("MPS was requested but is not available on this machine")
    if requested not in ("cpu", "mps"):
        raise ValueError(f"unknown device {requested!r} (use auto, mps or cpu)")
    return requested


def build_deepgaze2e(weights_path: Path) -> torch.nn.Module:
    """Rebuild the DeepGaze IIE ensemble and load the checkpoint strictly."""
    from deepgaze_pytorch.deepgaze2e import BACKBONES, build_deepgaze_mixture
    from deepgaze_pytorch.modules import MixtureModel

    from gazemap.saliency.backbones import REPLACEMENTS

    configs = [{**cfg, "type": REPLACEMENTS[cfg["type"]]} for cfg in BACKBONES]
    module = MixtureModel([build_deepgaze_mixture(cfg, components=MIXTURE_COMPONENTS) for cfg in configs])
    state = torch.load(weights_path, map_location="cpu")
    module.load_state_dict(state, strict=True)
    return module.float().eval()


class DeepGazeIIE:
    name = "deepgaze2e"

    def __init__(self, device: str = "auto", model_dir: Path | None = None, long_side: int = 1024):
        self.model_dir = Path(model_dir) if model_dir else default_model_dir()
        self.long_side = long_side
        weights = ensure_file(self.model_dir, "deepgaze2e.pth")
        self._centerbias_path = ensure_file(self.model_dir, "centerbias_mit1003.npy")
        self.module = build_deepgaze2e(weights)
        self.device = "cpu"
        self._move_to(pick_device(device))

    def _move_to(self, device: str) -> None:
        self.module.to(device)
        self.device = device

    def predict(self, image: np.ndarray, centerbias: str = "mit1003") -> np.ndarray:
        height, width = image.shape[:2]
        in_w, in_h, _ = fit_long_side(width, height, self.long_side)
        resized = np.asarray(Image.fromarray(image).convert("RGB").resize((in_w, in_h), Image.BILINEAR))
        image_tensor = torch.from_numpy(resized.transpose(2, 0, 1).copy()).float()[None]
        centerbias_tensor = torch.from_numpy(self._centerbias(centerbias, in_w, in_h))[None]

        try:
            log_density = self._forward(image_tensor, centerbias_tensor)
        except (RuntimeError, NotImplementedError) as exc:
            if self.device != "mps":
                raise
            print(f"MPS inference failed ({str(exc).splitlines()[0]}); retrying on CPU", file=sys.stderr)
            self._move_to("cpu")
            log_density = self._forward(image_tensor, centerbias_tensor)

        return resize_probability(log_density_to_probability(log_density), width, height)

    def _forward(self, image_tensor: torch.Tensor, centerbias_tensor: torch.Tensor) -> np.ndarray:
        with torch.no_grad():
            out = self.module(image_tensor.to(self.device), centerbias_tensor.to(self.device))
        return out[0, 0].float().cpu().numpy().astype(np.float64)

    def _centerbias(self, kind: str, width: int, height: int) -> np.ndarray:
        if kind == "uniform":
            return np.zeros((height, width), dtype=np.float32)
        if kind != "mit1003":
            raise ValueError(f"unknown centerbias {kind!r} (use {' or '.join(CENTERBIAS_KINDS)})")
        template = np.load(self._centerbias_path).astype(np.float32)
        # nearest-neighbour rescale of the log density, then renormalize
        scaled = np.asarray(Image.fromarray(template, mode="F").resize((width, height), Image.NEAREST))
        return (scaled - logsumexp(scaled)).astype(np.float32)
