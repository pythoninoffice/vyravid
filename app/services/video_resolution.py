"""Video resolution helpers shared by generation and regeneration flows."""

from __future__ import annotations

from typing import Any


def normalize_resolution_label(resolution: Any) -> str:
    """Normalize UI resolution labels before pixel conversion."""
    resolution_key = str(resolution or "720p").strip().lower()
    aliases = {
        "4k": "1440p",
        "uhd": "1440p",
        "2k": "1440p",
        "2k option 1": "1440p",
        "2k_option_1": "1440p",
        "2k-option-1": "1440p",
        "2k option 2": "1440p",
        "2k_option_2": "1440p",
        "2k-option-2": "1440p",
    }
    if resolution_key in {"4k", "uhd", "2160p"}:
        # 4K is hidden/disabled; treat stale saved values as FFmpeg 2K.
        return "1440p"
    if resolution_key.startswith("2k option 1") or resolution_key.startswith("2k option 2"):
        return "1440p"
    return aliases.get(resolution_key, resolution_key)


def get_upscale_mode(resolution: Any) -> str:
    """Map storyboard 2K UI choices to cloud upscaling modes."""
    resolution_key = str(resolution or "").strip().lower().replace("_", " ").replace("-", " ")
    if resolution_key in {"4k", "uhd", "2160p"}:
        # 4K is hidden/disabled; treat stale saved values as FFmpeg 2K.
        return "2k_option_1"
    if resolution_key.startswith("2k option 1"):
        return "2k_option_1"
    if resolution_key.startswith("2k option 2"):
        # Real-ESRGAN is hidden/disabled; treat stale saved values as FFmpeg 2K.
        return "2k_option_1"
    return "none"


def get_pixel_dimensions(aspect_ratio: Any, resolution: Any, default_resolution: str = "1280x720") -> str:
    """
    Convert an aspect ratio and UI resolution label to encoded pixel dimensions.

    The frontend treats resolution labels as the short edge of the canvas:
    - 16:9 1080p -> 1920x1080
    - 9:16 1080p -> 1080x1920
    - 9:16 2K -> 1440x2560
    """
    try:
        resolution_str = str(resolution or "").strip().lower()
        if "x" in resolution_str:
            width_str, height_str = resolution_str.split("x", 1)
            width = int(width_str.strip())
            height = int(height_str.strip())
            if width <= 0 or height <= 0:
                return default_resolution
            if width % 2:
                width += 1
            if height % 2:
                height += 1
            return f"{width}x{height}"

        aspect_ratio_str = str(aspect_ratio or "16:9")
        aspect_parts = aspect_ratio_str.split(":")
        if len(aspect_parts) != 2:
            return default_resolution

        width_ratio = int(aspect_parts[0])
        height_ratio = int(aspect_parts[1])
        if width_ratio <= 0 or height_ratio <= 0:
            return default_resolution

        resolution_map = {
            "720p": 720,
            "1080p": 1080,
            "1440p": 1440,
            "2160p": 2160,
        }
        short_edge = resolution_map.get(normalize_resolution_label(resolution), 720)

        if width_ratio == height_ratio:
            width = height = short_edge
        elif width_ratio > height_ratio:
            height = short_edge
            width = round(short_edge * width_ratio / height_ratio)
        else:
            width = short_edge
            height = round(short_edge * height_ratio / width_ratio)

        # H.264/yuv420p requires even dimensions.
        if width % 2:
            width += 1
        if height % 2:
            height += 1

        return f"{width}x{height}"
    except Exception:
        return default_resolution
