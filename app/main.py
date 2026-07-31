"""
Vyravid local API server.

Stripped of auth, payments, blog, and cloud-only features.
Uses SQLite + local filesystem storage.
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import uvicorn
import os
import sys
from pathlib import Path

# Ensure app/ and repo root are on path
APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("VYRAVID_ROOT", str(REPO_ROOT))
# Load .env from repo root or app/
try:
    from dotenv import load_dotenv
    for env_path in (REPO_ROOT / ".env", APP_DIR / ".env"):
        if env_path.exists():
            load_dotenv(env_path, override=False)
except Exception:
    pass

os.environ.setdefault("VYRAVID_LOCAL", "true")
# Default public base — single backend process (API + video processor)
_default_port = os.getenv("PORT", "8000")
os.environ.setdefault("VYRAVID_PUBLIC_BASE", os.getenv("VYRAVID_PUBLIC_BASE", f"http://localhost:{_default_port}"))
# Video processor is embedded under /vp on this same app
_public = os.environ["VYRAVID_PUBLIC_BASE"].rstrip("/")
os.environ.setdefault("CLOUD_VIDEO_PROCESSOR_URL", f"{_public}/vp")
os.environ.setdefault("USE_CLOUD_PROCESSING", "true")

from local.constants import STORAGE_ROOT, DATA_ROOT, LOCAL_USER_ID  # noqa: E402
from local.db import get_local_db  # noqa: E402

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("vyravid")

# Initialize local DB early
get_local_db()

app = FastAPI(
    title="vyravid",
    description="Vyravid local video creation tool",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Media mounts ---
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(STORAGE_ROOT)), name="media")

videos_dir = DATA_ROOT / "videos"
videos_dir.mkdir(parents=True, exist_ok=True)
app.mount("/videos", StaticFiles(directory=str(videos_dir)), name="videos")

thumbnails_dir = DATA_ROOT / "thumbnails"
thumbnails_dir.mkdir(parents=True, exist_ok=True)
app.mount("/thumbnails", StaticFiles(directory=str(thumbnails_dir)), name="thumbnails")

# Optional legacy static dir
static_dir = APP_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# --- Core routers for the SimpleProjectCreator workflow ---
from api.tts_endpoints import router as tts_router
from api.whisper_endpoints import router as whisper_router
from api.video_processing_endpoints import router as video_processing_router, dashboard_router
from api.project_management_endpoints import router as project_management_router
from api.dashboard_endpoints import router as dashboard_stats_router
from api.image_endpoints import router as image_router
from api.audio_endpoints import router as audio_router
from api.music_endpoints import router as music_router
from api.scene_generation_endpoints import router as scene_generation_router
from api.project_endpoints import router as project_router
from api.character_endpoints import router as character_router
from api.language_endpoints import router as language_router
from api.cloud_video_proxy import router as cloud_video_proxy_router
from api.scene_storage_endpoints import router as scene_storage_router
from api.folder_endpoints import router as folder_router

app.include_router(tts_router)
app.include_router(whisper_router)
app.include_router(video_processing_router)
app.include_router(project_management_router)
app.include_router(dashboard_router)
app.include_router(dashboard_stats_router)
app.include_router(image_router)
app.include_router(character_router)
app.include_router(audio_router)
app.include_router(music_router)
app.include_router(scene_generation_router)
app.include_router(project_router)
app.include_router(language_router)
app.include_router(cloud_video_proxy_router)
app.include_router(scene_storage_router)
app.include_router(folder_router)

# --- Embedded video processor (ffmpeg / timeline / captions) ---
# Formerly a separate cloud-video-processor service; now app/video_processor
try:
    from video_processor.api.endpoints import router as video_processor_router

    app.include_router(
        video_processor_router,
        prefix="/vp",
        tags=["video-processor"],
    )
    logger.info("Embedded video processor mounted at /vp/*")
except Exception as e:
    logger.exception("Failed to mount embedded video processor: %s", e)
    raise


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "mode": "local",
        "user_id": LOCAL_USER_ID,
        "storage": str(STORAGE_ROOT),
        "video_processor": "/vp",
    }


@app.get("/api/local/info")
async def local_info():
    return {
        "name": "vyravid",
        "mode": "local",
        "user_id": LOCAL_USER_ID,
        "data_root": str(DATA_ROOT),
        "storage_root": str(STORAGE_ROOT),
        "video_processor_url": os.environ.get("CLOUD_VIDEO_PROCESSOR_URL"),
        "services": ["api", "video-processor"],
    }


# Lightweight auth stubs so frontend that still calls /api/auth/* does not 404
from fastapi import APIRouter

auth_stub = APIRouter(prefix="/api/auth", tags=["auth-local"])


@auth_stub.get("/me")
@auth_stub.get("/profile")
@auth_stub.get("/user")
async def auth_me():
    from auth import _local_profile
    return _local_profile()


@auth_stub.post("/refresh")
async def auth_refresh():
    return {
        "access_token": "local-token",
        "refresh_token": "local-refresh",
        "expires_in": 86400 * 365,
    }


@auth_stub.get("/status")
async def auth_status():
    return {"authenticated": True, "mode": "local"}


app.include_router(auth_stub)


@app.get("/")
async def root():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")
    return {
        "message": "vyravid API is running",
        "docs": "/docs",
        "health": "/health",
        "frontend": "Run the Vue dev server (npm run dev in frontend/)",
    }


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if full_path.startswith(("api/", "media/", "videos/", "thumbnails/", "vp/", "docs", "openapi")):
        raise HTTPException(status_code=404, detail="Not found")
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="Frontend not built")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
