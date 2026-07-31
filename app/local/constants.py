"""Paths and constants for local Vyravid mode."""

from pathlib import Path
import os

# Repo root: Vyravid checkout
REPO_ROOT = Path(os.getenv("VYRAVID_ROOT", Path(__file__).resolve().parents[2]))
DATA_ROOT = Path(os.getenv("VYRAVID_DATA", REPO_ROOT / "data"))
STORAGE_ROOT = DATA_ROOT / "storage"
DB_PATH = Path(os.getenv("VYRAVID_DB", DATA_ROOT / "db" / "openvid.sqlite3"))
MEDIA_URL_PREFIX = "/media"

# Fixed local user (no auth)
LOCAL_USER_ID = "00000000-0000-0000-0000-000000000001"
LOCAL_USER_EMAIL = "local@openvid.local"
LOCAL_USER_NAME = "Local User"

for p in (DATA_ROOT, STORAGE_ROOT, DB_PATH.parent, DATA_ROOT / "videos", DATA_ROOT / "audio", DATA_ROOT / "images", DATA_ROOT / "thumbnails", DATA_ROOT / "temp"):
    p.mkdir(parents=True, exist_ok=True)
