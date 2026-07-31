"""Local greenscreen effect asset resolution."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

VYRAVID_ROOT = Path(os.getenv("VYRAVID_ROOT", Path(__file__).resolve().parents[3]))
STORAGE_ROOT = Path(os.getenv("VYRAVID_STORAGE", VYRAVID_ROOT / "data" / "storage"))
GREENSCREEN_DIR = STORAGE_ROOT / "greenscreen"
MEDIA_PREFIX = "/media"
PUBLIC_BASE = os.getenv("VYRAVID_PUBLIC_BASE", "http://localhost:8000").rstrip("/")


def normalize_greenscreen_effect_name(effect_name_or_path: str) -> str:
    """Return a storage-safe effect filename from an effect ID, URL, or path."""
    value = (effect_name_or_path or "").strip()
    if not value:
        raise FileNotFoundError("No greenscreen effect was provided")

    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        value = unquote(parsed.path)

    if value.startswith(MEDIA_PREFIX + "/"):
        value = value[len(MEDIA_PREFIX) + 1 :]

    name = Path(value).name
    if not name.endswith(".mp4"):
        name = f"{name}.mp4"
    return name.replace("..", "")


def resolve_greenscreen_effect_path(effect_name_or_path: str) -> str:
    """Resolve an effect ID like fire1_v to data/storage/greenscreen/fire1_v.mp4."""
    value = (effect_name_or_path or "").strip()
    if os.path.isabs(value) and Path(value).exists():
        return value

    name = normalize_greenscreen_effect_name(value)
    path = GREENSCREEN_DIR / name
    if path.exists():
        return str(path)

    raise FileNotFoundError(
        f"Greenscreen effect '{name}' is missing. Place it at {GREENSCREEN_DIR / name}"
    )


def greenscreen_effect_media_url(effect_name_or_path: str) -> str:
    """Return the local /media URL for an existing greenscreen effect."""
    path = Path(resolve_greenscreen_effect_path(effect_name_or_path))
    rel = path.relative_to(STORAGE_ROOT).as_posix()
    return f"{PUBLIC_BASE}{MEDIA_PREFIX}/{rel}"
