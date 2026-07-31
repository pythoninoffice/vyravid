"""Image upscaling helpers for storyboard/video rendering.

Supports two 2K-oriented modes:
- ``2k_option_1`` / ``ffmpeg``: fast FFmpeg bicubic + unsharp resize.
- ``2k_option_2``: hidden/disabled legacy value; treated as FFmpeg 2K.
"""

from __future__ import annotations

# import os  # Real-ESRGAN disabled
import subprocess
import time
# import urllib.request  # Real-ESRGAN disabled
# import importlib.util  # Real-ESRGAN disabled
from pathlib import Path
from typing import Any, Dict, Optional

import structlog
try:
    import cv2
except ImportError:
    cv2 = None

logger = structlog.get_logger(__name__)

UPSCALE_MODE_NONE = "none"
UPSCALE_MODE_FFMPEG_2K = "2k_option_1"
UPSCALE_MODE_REALESRGAN_2K = "2k_option_2"

_UPSCALE_ALIASES = {
    "": UPSCALE_MODE_NONE,
    "none": UPSCALE_MODE_NONE,
    "off": UPSCALE_MODE_NONE,
    "false": UPSCALE_MODE_NONE,
    "0": UPSCALE_MODE_NONE,
    "no_upscale": UPSCALE_MODE_NONE,
    "no-upscale": UPSCALE_MODE_NONE,
    "2k option 1": UPSCALE_MODE_FFMPEG_2K,
    "2k_option_1": UPSCALE_MODE_FFMPEG_2K,
    "2k-option-1": UPSCALE_MODE_FFMPEG_2K,
    "2k ffmpeg": UPSCALE_MODE_FFMPEG_2K,
    "2k_ffmpeg": UPSCALE_MODE_FFMPEG_2K,
    "ffmpeg": UPSCALE_MODE_FFMPEG_2K,
    "fast": UPSCALE_MODE_FFMPEG_2K,
    # Real-ESRGAN is hidden/disabled; treat stale values as FFmpeg 2K.
    "2k option 2": UPSCALE_MODE_FFMPEG_2K,
    "2k_option_2": UPSCALE_MODE_FFMPEG_2K,
    "2k-option-2": UPSCALE_MODE_FFMPEG_2K,
    "2k realesrgan": UPSCALE_MODE_FFMPEG_2K,
    "2k_realesrgan": UPSCALE_MODE_FFMPEG_2K,
    "realesrgan": UPSCALE_MODE_FFMPEG_2K,
    "real-esrgan": UPSCALE_MODE_FFMPEG_2K,
    "ai": UPSCALE_MODE_FFMPEG_2K,
}

_REAL_ESRGAN_MODELS: Dict[str, Dict[str, Any]] = {
    "RealESRGAN_x2plus": {
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
        "scale": 2,
    },
}

_upsampler_cache: Dict[str, Any] = {}


class RealESRGANUnavailableError(RuntimeError):
    """Raised when the optional Real-ESRGAN runtime is not installed/usable."""


def normalize_upscale_mode(value: Optional[Any]) -> str:
    """Normalize user/API upscale option names to canonical internal modes."""
    if value is None:
        return UPSCALE_MODE_NONE
    key = str(value).strip().lower().replace("_", " ").replace("-", " ")
    compact_key = str(value).strip().lower()
    if key.startswith("2k option 1"):
        return UPSCALE_MODE_FFMPEG_2K
    if key.startswith("2k option 2"):
        return UPSCALE_MODE_FFMPEG_2K
    return _UPSCALE_ALIASES.get(key) or _UPSCALE_ALIASES.get(compact_key, UPSCALE_MODE_NONE)


def upscale_mode_from_resolution_label(resolution: Optional[Any]) -> str:
    """Infer upscale mode from storyboard resolution labels such as '2K Option 1'."""
    return normalize_upscale_mode(resolution)


def is_upscale_enabled(value: Optional[Any]) -> bool:
    return normalize_upscale_mode(value) != UPSCALE_MODE_NONE


def _missing_realesrgan_dependencies() -> list[str]:
    """Return optional packages missing from the Real-ESRGAN path."""
    # Real-ESRGAN is hidden/disabled.
    # required_modules = ("torch", "basicsr", "realesrgan")
    # return [name for name in required_modules if importlib.util.find_spec(name) is None]
    return ["torch", "basicsr", "realesrgan"]


def _probe_image_size(path: str) -> tuple[int, int]:
    if cv2 is not None:
        img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if img is not None and img.shape[0] > 0 and img.shape[1] > 0:
            h, w = img.shape[:2]
            return int(w), int(h)

    # Fallback to ffprobe for formats cv2 cannot decode.
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and "x" in result.stdout:
        w_s, h_s = result.stdout.strip().split("x", 1)
        return int(w_s), int(h_s)

    raise ValueError(f"Could not determine image dimensions for {path}")


def upscale_ffmpeg(input_path: str, output_path: str, scale: int = 2) -> None:
    """Upscale an image by integer scale using FFmpeg bicubic + unsharp."""
    w, h = _probe_image_size(input_path)
    new_w, new_h = w * scale, h * scale
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        f"scale={new_w}:{new_h}:flags=bicubic,unsharp=5:5:1.0:5:5:0.0",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg upscaling failed: {result.stderr[-1200:]}")


def _ensure_model(model_name: str, dest_dir: Optional[str] = None) -> str:
    if model_name not in _REAL_ESRGAN_MODELS:
        raise ValueError(f"Unknown Real-ESRGAN model: {model_name}")

    model_dir = Path(dest_dir or os.getenv("REAL_ESRGAN_MODEL_DIR") or "/tmp/realesrgan_models")
    model_dir.mkdir(parents=True, exist_ok=True)
    dest = model_dir / f"{model_name}.pth"
    if not dest.exists() or dest.stat().st_size == 0:
        url = _REAL_ESRGAN_MODELS[model_name]["url"]
        logger.info("Downloading Real-ESRGAN model", model_name=model_name, url=url, dest=str(dest))
        urllib.request.urlretrieve(url, dest)
    return str(dest)


def _get_realesrgan_upsampler(model_name: str, model_path: str, gpu_id: int = 0, tile: int = 512):
    """Lazy-load Real-ESRGAN. Imports stay local so ffmpeg mode has no ML dependency."""
    raise RealESRGANUnavailableError("Real-ESRGAN upscaling is disabled")
    # try:
    #     import torch
    #     from basicsr.archs.rrdbnet_arch import RRDBNet
    #     from realesrgan import RealESRGANer
    # except Exception as e:
    #     raise RealESRGANUnavailableError(
    #         "Real-ESRGAN upscaling requires torch, basicsr, and realesrgan dependencies"
    #     ) from e

    if not torch.cuda.is_available():
        gpu_id = -1

    key = f"{model_name}|{model_path}|gpu={gpu_id}|tile={tile}"
    if key in _upsampler_cache:
        return _upsampler_cache[key]

    if model_name != "RealESRGAN_x2plus":
        raise ValueError(f"Unsupported model configured for 2K AI upscale: {model_name}")

    model = RRDBNet(
        num_in_ch=3,
        num_out_ch=3,
        scale=2,
        num_feat=64,
        num_block=23,
        num_grow_ch=32,
    )
    upsampler = RealESRGANer(
        scale=2,
        model_path=model_path,
        model=model,
        tile=tile,
        tile_pad=10,
        pre_pad=0,
        half=torch.cuda.is_available() and gpu_id >= 0,
        gpu_id=None if gpu_id < 0 else gpu_id,
    )
    _upsampler_cache[key] = upsampler
    return upsampler


def upscale_realesrgan(input_path: str, output_path: str, scale: int = 2) -> None:
    """Upscale an image with Real-ESRGAN x2plus and write a PNG output."""
    raise RealESRGANUnavailableError("Real-ESRGAN upscaling is disabled")
    if scale != 2:
        raise ValueError("Real-ESRGAN storyboard mode currently supports 2x upscaling only")
    if cv2 is None:
        raise RuntimeError("Real-ESRGAN upscaling requires opencv-python-headless")

    # try:
    #     import numpy as np  # noqa: F401 - imported to make dependency error explicit
    #     from PIL import Image
    # except Exception as e:
    #     raise RuntimeError("Real-ESRGAN upscaling requires pillow/numpy dependencies") from e

    missing = _missing_realesrgan_dependencies()
    if missing:
        raise RealESRGANUnavailableError(
            "Real-ESRGAN upscaling requires torch, basicsr, and realesrgan dependencies "
            f"(missing: {', '.join(missing)})"
        )

    # import torch

    model_name = os.getenv("REAL_ESRGAN_MODEL_NAME", "RealESRGAN_x2plus")
    model_path = os.getenv("REAL_ESRGAN_MODEL_PATH") or _ensure_model(model_name)
    tile = int(os.getenv("REAL_ESRGAN_TILE", "512"))
    gpu_id = int(os.getenv("REAL_ESRGAN_GPU_ID", "0")) if torch.cuda.is_available() else -1

    upsampler = _get_realesrgan_upsampler(model_name, model_path, gpu_id=gpu_id, tile=tile)

    img = cv2.imread(str(input_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(input_path)

    # cv2 loads BGR/BGRA; Real-ESRGAN expects RGB/RGBA.
    if img.ndim == 3 and img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    elif img.ndim == 3 and img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)

    output, _ = upsampler.enhance(img, outscale=float(scale))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    if output.ndim == 3 and output.shape[2] == 3:
        output_bgr = cv2.cvtColor(output, cv2.COLOR_RGB2BGR)
        if not cv2.imwrite(str(output_path), output_bgr):
            raise RuntimeError(f"Failed to write Real-ESRGAN output: {output_path}")
    else:
        Image.fromarray(output).save(str(output_path))


def upscale_image(input_path: str, output_path: str, mode: Optional[Any], scale: int = 2) -> str:
    """Upscale input image according to mode and return output_path.

    ``mode`` accepts canonical values and UI labels. Disabled modes return input_path.
    """
    normalized = normalize_upscale_mode(mode)
    if normalized == UPSCALE_MODE_NONE:
        return str(input_path)

    t0 = time.perf_counter()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if normalized == UPSCALE_MODE_FFMPEG_2K:
        upscale_ffmpeg(str(input_path), str(output_path), scale=scale)
    elif normalized == UPSCALE_MODE_REALESRGAN_2K:
        try:
            upscale_realesrgan(str(input_path), str(output_path), scale=scale)
        except RealESRGANUnavailableError as e:
            logger.warning(
                "Real-ESRGAN unavailable; falling back to FFmpeg upscaling",
                error=str(e),
                input_path=str(input_path),
                output_path=str(output_path),
            )
            upscale_ffmpeg(str(input_path), str(output_path), scale=scale)
    else:
        raise ValueError(f"Unsupported upscale mode: {mode}")

    logger.info(
        "Image upscaling completed",
        mode=normalized,
        input_path=str(input_path),
        output_path=str(output_path),
        elapsed_seconds=round(time.perf_counter() - t0, 2),
    )
    return str(output_path)
