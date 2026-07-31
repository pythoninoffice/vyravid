"""
API endpoints for Cloud Video Processor
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from typing import List, Dict, Any, Optional
import structlog
import os
import asyncio
import aiohttp
import json
import subprocess
import time
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from google import genai
from google.genai import types

from video_processor.models.requests import (
    MediaProcessingRequest,
    TranscriptionRequest,
    VideoCombineRequest,
    AudioVideoSyncRequest,
    VideoSplitRequest,
    SubtitleBurnRequest,
    TimelineRenderRequest,
    WhiteboardDoodleRequest,
    ManimGenerateRequest,
    VyraManimRequest
)
from video_processor.models.responses import (
    MediaProcessingResponse,
    JobStatusResponse,
    HealthResponse,
    TimelineRenderResponse,
    ManimGenerateResponse
)
from video_processor.services.auth_service import validate_service_account
from video_processor.services.media_processor import MediaProcessorService
# from services.cost_calculator import cost_calculator, TranscriptionService  # Removed
from video_processor.services.performance_tracker import performance_tracker, OperationType
from video_processor.services.usage_logger import usage_logger, UsageEventType
from video_processor.services.analytics_service import analytics_service, ReportType
from video_processor.services.ffmpeg_processor import FFmpegProcessor
from video_processor.services.timeline_renderer import get_timeline_renderer
from video_processor.services.gcs_service import get_gcs_service

from dotenv import load_dotenv
load_dotenv()
# Configuration
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
LOCAL_DEBUG_VIDEO_URL = "http://localhost:8000/media/greenscreen/stars_h.mp4"
LOCAL_DEBUG_AUDIO_URL = "http://localhost:8000/media/music/a-stroll.mp3"
LOCAL_DEBUG_SUBTITLE_URL = "http://localhost:8000/media/debug/transcript_0.ass"

# Initialize router and logger
router = APIRouter()
security = HTTPBearer()
logger = structlog.get_logger()

# Initialize services
media_processor = MediaProcessorService()
ffmpeg_processor = FFmpegProcessor()


class MotionGeminiGenerateRequest(BaseModel):
    prompt: str
    user_id: Optional[str] = None
    system_instruction: Optional[str] = None
    max_attempts: int = 5
    timeout_seconds: float = 45.0


class MotionGeminiGenerateResponse(BaseModel):
    text: str
    model_used: str


class AskVyraSceneAssetItem(BaseModel):
    svg_code: str
    audio_url: str


class AskVyraComposeSceneVideoRequest(BaseModel):
    scene_assets: List[AskVyraSceneAssetItem]
    session_id: Optional[str] = None
    fps: int = 30
    user_id: Optional[str] = None


class AskVyraComposeSceneVideoResponse(BaseModel):
    video_url: str
    session_id: str

# Helper functions for error handling and validation
def create_error_response(status_code: int, error_code: str, message: str, details: Dict[str, Any] = None):
    """Create standardized error response"""
    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": error_code,
            "error_message": message,
            "details": details or {},
            "support_reference": f"cloud-video-{status_code}-{error_code}"
        }
    )

def validate_job_id(job_id: str) -> None:
    """Validate job ID format"""
    if not job_id or len(job_id) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job ID must be at least 3 characters long"
        )
    if len(job_id) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job ID must be less than 100 characters"
        )


def _motion_gemini_model_chain() -> List[str]:
    primary = (os.getenv("GEMINI_PRIMARY_MODEL") or "gemini-3.1-pro-preview").strip()
    fallback = (os.getenv("GEMINI_FALLBACK_MODEL") or "gemini-3-pro-preview").strip()
    return list(dict.fromkeys([m for m in [primary, fallback] if m]))


def _is_gemini_overload_error(error: Exception) -> bool:
    msg = str(error).lower()
    tokens = [
        "503",
        "service unavailable",
        "unavailable",
        "high demand",
        "resource_exhausted",
        "rate limit",
        "quota",
    ]
    return any(token in msg for token in tokens)


def _gemini_retry_delay(attempt: int) -> float:
    return min(6.0, 0.8 * (2 ** (attempt - 1)))


def _gemini_generate_text_with_fallback(
    client: genai.Client,
    *,
    contents: str,
    config: Optional[types.GenerateContentConfig] = None,
) -> tuple[str, str]:
    models = _motion_gemini_model_chain()
    last_error: Optional[Exception] = None
    used_model = models[0] if models else "unknown"

    for idx, model_name in enumerate(models):
        try:
            used_model = model_name
            kwargs: Dict[str, Any] = {"model": model_name, "contents": contents}
            if config is not None:
                kwargs["config"] = config
            response = client.models.generate_content(**kwargs)
            return (response.text or "").strip(), used_model
        except Exception as e:
            last_error = e
            has_next_model = idx < len(models) - 1
            if _is_gemini_overload_error(e) and has_next_model:
                logger.warning(
                    "motion_gemini_model_fallback",
                    current_model=model_name,
                    next_model=models[idx + 1],
                    error=str(e),
                )
                continue
            raise

    if last_error:
        raise last_error
    return "", used_model


def _normalize_svg_xml(svg_code: str) -> Optional[str]:
    if not svg_code:
        return None

    candidate = svg_code.strip()
    try:
        ET.fromstring(candidate)
        return candidate
    except Exception:
        pass

    repaired = re.sub(
        r"&(?!#\d+;|#x[0-9a-fA-F]+;|[A-Za-z_][\w.:-]*;)",
        "&amp;",
        candidate,
    )
    try:
        ET.fromstring(repaired)
        return repaired
    except Exception:
        return None


def _find_chromium_executable() -> Optional[str]:
    candidates = [
        os.getenv("CHROMIUM_PATH"),
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) if "/" not in candidate else candidate
        if resolved and os.path.exists(resolved):
            return resolved
    return None


async def _download_to_file(url: str, output_path: str) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to download media from URL (status={resp.status})")
            with open(output_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 256):
                    f.write(chunk)


async def _probe_media_duration_seconds(path: str) -> float:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {stderr.decode('utf-8', errors='ignore')[:500]}")
    try:
        return max(0.1, float(stdout.decode("utf-8").strip()))
    except Exception:
        return 3.0


async def _run_ffmpeg_with_progress(
    cmd: List[str],
    *,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    stage: str = "ffmpeg",
    duration_seconds: Optional[float] = None,
    scene_index: Optional[int] = None,
    scenes_total: Optional[int] = None,
) -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    last_logged_bucket = -1
    last_speed = None

    while True:
        line = await proc.stderr.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="ignore").strip()
        if "=" not in text:
            continue

        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip()

        if key == "speed":
            last_speed = value
            continue

        if key in ("out_time_ms", "out_time_us"):
            try:
                elapsed_sec = float(value) / 1_000_000.0
            except Exception:
                continue

            if duration_seconds and duration_seconds > 0:
                pct = int(max(0, min(100, (elapsed_sec / duration_seconds) * 100)))
                bucket = pct // 10
                if bucket > last_logged_bucket:
                    last_logged_bucket = bucket
                    logger.info(
                        "ask_vyra_ffmpeg_progress",
                        session_id=session_id,
                        user_id=user_id,
                        stage=stage,
                        scene_index=scene_index,
                        scenes_total=scenes_total,
                        elapsed_seconds=round(elapsed_sec, 2),
                        duration_seconds=round(duration_seconds, 2),
                        ffmpeg_progress_percent=pct,
                        speed=last_speed,
                    )
            else:
                # Unknown total duration: log every ~3 seconds of output time.
                bucket = int(elapsed_sec // 3)
                if bucket > last_logged_bucket:
                    last_logged_bucket = bucket
                    logger.info(
                        "ask_vyra_ffmpeg_progress",
                        session_id=session_id,
                        user_id=user_id,
                        stage=stage,
                        scene_index=scene_index,
                        scenes_total=scenes_total,
                        elapsed_seconds=round(elapsed_sec, 2),
                        duration_seconds=None,
                        ffmpeg_progress_percent=None,
                        speed=last_speed,
                    )

    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="ignore")[:1500])


async def _render_svg_to_video_file(
    svg_code: str,
    output_path: str,
    output_format: str,
    duration_seconds: float,
    fps: int,
    *,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    scene_index: Optional[int] = None,
    scenes_total: Optional[int] = None,
) -> None:
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        raise RuntimeError(
            "SVG video export requires Playwright. Install with: pip install playwright && playwright install chromium"
        ) from e

    frame_dir = tempfile.mkdtemp(prefix="ask_vyra_svg_frames_")
    html = f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      html, body {{
        margin: 0;
        padding: 0;
        background: #000;
        overflow: hidden;
      }}
      body {{
        display: flex;
        align-items: center;
        justify-content: center;
      }}
      svg {{
        display: block;
      }}
    </style>
  </head>
  <body>
    {svg_code}
  </body>
</html>
"""

    browser = None
    try:
        chromium_path = _find_chromium_executable()
        total_frames = max(1, int(duration_seconds * fps))

        async with async_playwright() as p:
            launch_kwargs = {"headless": True}
            if chromium_path:
                launch_kwargs["executable_path"] = chromium_path

            browser = await p.chromium.launch(**launch_kwargs)
            page = await browser.new_page(viewport={"width": 1080, "height": 1080})
            await page.set_content(html, wait_until="domcontentloaded")

            size = await page.evaluate(
                """() => {
                    const svg = document.querySelector('svg');
                    if (!svg) return null;
                    const rect = svg.getBoundingClientRect();
                    const viewBox = svg.getAttribute('viewBox');
                    let width = Math.round(rect.width);
                    let height = Math.round(rect.height);
                    if ((!width || !height) && viewBox) {
                      const parts = viewBox.trim().split(/\\s+/).map(Number);
                      if (parts.length === 4 && parts[2] > 0 && parts[3] > 0) {
                        width = Math.round(parts[2]);
                        height = Math.round(parts[3]);
                      }
                    }
                    return {
                      width: Math.max(128, width || 1080),
                      height: Math.max(128, height || 1080),
                    };
                }"""
            )
            if not size:
                raise RuntimeError("No <svg> element found in export payload.")

            width = int(size["width"])
            height = int(size["height"])
            await page.set_viewport_size({"width": width, "height": height})

            await page.evaluate(
                """({w, h}) => {
                    const svg = document.querySelector('svg');
                    if (!svg) return;
                    svg.setAttribute('width', String(w));
                    svg.setAttribute('height', String(h));
                    document.body.style.width = `${w}px`;
                    document.body.style.height = `${h}px`;
                    if (typeof svg.pauseAnimations === 'function') {
                      svg.pauseAnimations();
                    }
                    document.querySelectorAll('*').forEach((el) => {
                      if (typeof el.getAnimations === 'function') {
                        el.getAnimations().forEach((anim) => anim.pause());
                      }
                    });
                }""",
                {"w": width, "h": height},
            )

            for i in range(total_frames):
                t = i / fps
                await page.evaluate(
                    """(timeSec) => {
                        const svg = document.querySelector('svg');
                        if (!svg) return;
                        if (typeof svg.setCurrentTime === 'function') {
                          svg.setCurrentTime(timeSec);
                        }
                        document.querySelectorAll('*').forEach((el) => {
                          if (typeof el.getAnimations === 'function') {
                            el.getAnimations().forEach((anim) => {
                              anim.currentTime = timeSec * 1000;
                            });
                          }
                        });
                    }""",
                    t,
                )
                await page.screenshot(path=os.path.join(frame_dir, f"frame_{i:05d}.png"))

            await browser.close()
            browser = None

        if output_format == "mp4":
            cmd = [
                "ffmpeg",
                "-y",
                "-framerate",
                str(fps),
                "-i",
                os.path.join(frame_dir, "frame_%05d.png"),
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                output_path,
            ]
        else:
            cmd = [
                "ffmpeg",
                "-y",
                "-framerate",
                str(fps),
                "-i",
                os.path.join(frame_dir, "frame_%05d.png"),
                "-c:v",
                "libvpx-vp9",
                "-pix_fmt",
                "yuv420p",
                "-b:v",
                "2M",
                output_path,
            ]

        ffmpeg_cmd = cmd[:-1] + ["-progress", "pipe:2", "-nostats"] + [cmd[-1]]
        try:
            await _run_ffmpeg_with_progress(
                ffmpeg_cmd,
                session_id=session_id,
                user_id=user_id,
                stage="scene_frame_encode",
                duration_seconds=duration_seconds,
                scene_index=scene_index,
                scenes_total=scenes_total,
            )
        except Exception as e:
            raise RuntimeError(f"ffmpeg failed: {str(e)[:1200]}")
    finally:
        if browser is not None:
            await browser.close()
        shutil.rmtree(frame_dir, ignore_errors=True)


async def _mux_scene_svg_audio_to_segment(
    svg_code: str,
    audio_url: str,
    segment_path: str,
    fps: int,
    *,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    scene_index: Optional[int] = None,
    scenes_total: Optional[int] = None,
) -> None:
    temp_dir = tempfile.mkdtemp(prefix="ask_vyra_scene_compose_")
    try:
        audio_path = os.path.join(temp_dir, "audio_input")
        svg_video_path = os.path.join(temp_dir, "svg_video.mp4")
        await _download_to_file(audio_url, audio_path)
        duration_seconds = await _probe_media_duration_seconds(audio_path)

        await _render_svg_to_video_file(
            svg_code=svg_code,
            output_path=svg_video_path,
            output_format="mp4",
            duration_seconds=duration_seconds,
            fps=fps,
            session_id=session_id,
            user_id=user_id,
            scene_index=scene_index,
            scenes_total=scenes_total,
        )

        mux_cmd = [
            "ffmpeg", "-y",
            "-i", svg_video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-shortest",
            "-movflags", "+faststart",
            "-progress", "pipe:2",
            "-nostats",
            segment_path,
        ]
        try:
            await _run_ffmpeg_with_progress(
                mux_cmd,
                session_id=session_id,
                user_id=user_id,
                stage="scene_mux",
                duration_seconds=duration_seconds,
                scene_index=scene_index,
                scenes_total=scenes_total,
            )
        except Exception:
            mux_fallback_cmd = [
                "ffmpeg", "-y",
                "-i", svg_video_path,
                "-i", audio_path,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                "-r", str(fps),
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "48000",
                "-shortest",
                "-movflags", "+faststart",
                "-progress", "pipe:2",
                "-nostats",
                segment_path,
            ]
            await _run_ffmpeg_with_progress(
                mux_fallback_cmd,
                session_id=session_id,
                user_id=user_id,
                stage="scene_mux_fallback",
                duration_seconds=duration_seconds,
                scene_index=scene_index,
                scenes_total=scenes_total,
            )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

async def send_webhook_notification(
    webhook_url: str, 
    job_id: str, 
    job_status: str, 
    payload: Dict[str, Any],
    cost_breakdown: Optional[Dict[str, Any]] = None,
    performance_metrics: Optional[Dict[str, Any]] = None,
    usage_summary: Optional[Dict[str, Any]] = None
):
    """Send enhanced webhook notification with cost and usage information"""
    if not webhook_url:
        return
        
    try:
        # Build comprehensive notification payload - convert datetime objects
        def serialize_datetime(obj):
            """Convert datetime objects to ISO format strings"""
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: serialize_datetime(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [serialize_datetime(item) for item in obj]
            return obj
        
        serialized_payload = serialize_datetime(payload)
        
        notification_payload = {
            "job_id": job_id,
            "status": job_status,
            "timestamp": serialized_payload.get("updated_at") or datetime.now(timezone.utc).isoformat(),
            "data": serialized_payload
        }
        
        # Add cost information if available
        if cost_breakdown:
            notification_payload["cost_breakdown"] = {
                "transcription_cost": cost_breakdown.get("transcription_cost", 0.0),
                "video_processing_cost": cost_breakdown.get("video_processing_cost", 0.0),
                "storage_cost": cost_breakdown.get("storage_cost", 0.0),
                "total_cost": cost_breakdown.get("total_cost", 0.0),
                "currency": cost_breakdown.get("currency", "USD")
            }
        
        # Add performance metrics if available
        if performance_metrics:
            notification_payload["performance"] = {
                "processing_time_seconds": performance_metrics.get("duration_seconds"),
                "audio_duration_minutes": performance_metrics.get("audio_duration_minutes"),
                "video_duration_minutes": performance_metrics.get("video_duration_minutes"),
                "throughput_ratio": performance_metrics.get("throughput_ratio"),
                "cpu_usage_percent": performance_metrics.get("avg_cpu_percent"),
                "memory_usage_mb": performance_metrics.get("avg_memory_mb"),
                "files_processed": performance_metrics.get("files_processed", 1)
            }
        
        # Add usage summary if available
        if usage_summary:
            notification_payload["usage"] = usage_summary
        
        # Add billing and rate limit information
        notification_payload["billing"] = {
            "processing_mode": "cloud",
            "service_region": os.getenv("GOOGLE_CLOUD_REGION", "us-central1"),
            "usage_tier": "standard"  # Could be based on user subscription
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=notification_payload,
                timeout=aiohttp.ClientTimeout(total=15),  # Increased timeout for larger payload
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "CloudVideoProcessor/1.0"
                }
            ) as response:
                response_text = await response.text()
                
                if response.status >= 400:
                    logger.warning(
                        "webhook_notification_failed",
                        job_id=job_id,
                        webhook_url=webhook_url,
                        status_code=response.status,
                        response_text=response_text[:500]  # Limit log size
                    )
                else:
                    logger.info(
                        "webhook_notification_sent",
                        job_id=job_id,
                        webhook_url=webhook_url,
                        status_code=response.status,
                        payload_size_bytes=len(json.dumps(notification_payload))
                    )
                    
                    # Log webhook delivery for usage tracking
                    from video_processor.services.usage_logger import UsageEvent, UsageEventType
                    webhook_event = UsageEvent(
                        event_id=f"{job_id}_webhook_delivered",
                        event_type=UsageEventType.API_REQUEST,
                        timestamp=datetime.now(timezone.utc),
                        job_id=job_id,
                        metadata={
                            "webhook_url": webhook_url,
                            "response_status": response.status,
                            "payload_size_bytes": len(json.dumps(notification_payload))
                        }
                    )
                    usage_logger.log_usage_event(webhook_event)
                    
    except Exception as e:
        logger.error(
            "webhook_notification_error",
            job_id=job_id,
            webhook_url=webhook_url,
            error=str(e),
            error_type=type(e).__name__
        )

# Local project update helper functions
async def update_local_project_completion(request: MediaProcessingRequest, result: Dict[str, Any]):
    """Update local database with video processing completion data."""
    try:
        from video_processor.services.supabase_service import get_supabase_service
        from video_processor.services.gcs_service import get_gcs_service
        import os
        
        project_store = get_supabase_service()
        gcs_service = get_gcs_service()
        
        logger.info("🔧 Service availability check",
                   project_store_available=project_store.is_available() if project_store else False,
                   gcs_available=gcs_service.is_available() if gcs_service else False,
                   gcs_service_type=type(gcs_service).__name__ if gcs_service else "None")
        
        if not project_store.is_available():
            logger.warning("Local project store not available, skipping project update", job_id=request.job_id)
            return
        
        # Extract video URL from result
        video_url = None
        signed_url = None
        file_size = 0
        duration = 0.0
        
        # Look for the main video file in output_files
        output_files = result.get('output_files', [])
        logger.info("Processing output files", output_files=output_files, count=len(output_files))
        
        for file_url in output_files:
            logger.info("Checking output file", file_url=file_url, is_video=any(ext in file_url.lower() for ext in ['.mp4', '.mov', '.avi', '.mkv']))
            if any(ext in file_url.lower() for ext in ['.mp4', '.mov', '.avi', '.mkv']):
                video_url = file_url
                break
        
        if not video_url and output_files:
            video_url = output_files[-1]  # Fallback to last file
            logger.info("Using fallback video URL", video_url=video_url)
        
        if video_url:
            # Generate signed URL for the video
            try:
                bucket_name = None
                blob_path = None
                
                if video_url.startswith('gs://'):
                    # Extract bucket and path from gs:// URL
                    parts = video_url.replace('gs://', '').split('/', 1)
                    if len(parts) == 2:
                        bucket_name, blob_path = parts
                elif 'storage.googleapis.com' in video_url:
                    # Extract bucket and path from HTTPS URL
                    # Format: https://storage.googleapis.com/bucket/path/file.mp4
                    parts = video_url.split('/')
                    if len(parts) >= 5:  # https, '', storage.googleapis.com, bucket, path...
                        bucket_name = parts[3]
                        blob_path = '/'.join(parts[4:])
                
                if bucket_name and blob_path:
                    logger.info("Generating signed URL", bucket=bucket_name, blob_path=blob_path)
                    
                    # Try generating signed URL with retry logic
                    signed_url = None
                    max_retries = 3
                    
                    # Try to generate signed URL (with automatic fallback to public URL)
                    for attempt in range(max_retries):
                        try:
                            logger.info(f"🚀 CLOUD-VIDEO-PROCESSOR v4.1 (Smart Service Account Detection) - Attempting URL generation (attempt {attempt + 1})",
                                       bucket_name=bucket_name,
                                       blob_path=blob_path,
                                       gcs_service_available=gcs_service.is_available(),
                                       can_generate_signed=gcs_service.can_generate_signed_urls())
                            
                            signed_url = await gcs_service.generate_signed_url(
                                bucket_name, 
                                blob_path, 
                                24 * 60  # 24 hours in minutes
                            )
                                
                            logger.info("🔍 Signed URL generation result",
                                        attempt=attempt + 1,
                                        signed_url=signed_url,
                                        signed_url_type=type(signed_url).__name__,
                                        signed_url_length=len(signed_url) if signed_url else 0,
                                        is_none=signed_url is None,
                                        is_empty=signed_url == "" if signed_url is not None else False)
                            
                            if signed_url:
                                logger.info("✅ Signed URL generated successfully", 
                                            attempt=attempt + 1,
                                            signed_url_preview=signed_url[:80] + "..." if len(signed_url) > 80 else signed_url)
                                break
                            else:
                                logger.warning("⚠️ Signed URL generation returned None/empty", 
                                                attempt=attempt + 1)
                        except Exception as retry_e:
                            logger.error("❌ Signed URL generation attempt failed with exception", 
                                        attempt=attempt + 1,
                                        error=str(retry_e),
                                        error_type=type(retry_e).__name__,
                                        bucket_name=bucket_name,
                                        blob_path=blob_path)
                            import traceback
                            logger.error("📊 Full exception traceback:", traceback=traceback.format_exc())
                            
                            if attempt < max_retries - 1:
                                await asyncio.sleep(1)  # Wait 1 second before retry
                            else:
                                # Use original URL as fallback instead of failing
                                logger.error("💥 ALL signed URL attempts failed, falling back to gs:// URL",
                                            total_attempts=max_retries,
                                            final_fallback=video_url)
                                signed_url = video_url
                                break
                    
                    # Get file info for size
                    file_info = await gcs_service.get_file_info(video_url)
                    if file_info and file_info.get('size'):
                        file_size = file_info['size']
                else:
                    logger.warning("Could not extract bucket and path from video URL", video_url=video_url)
                    signed_url = video_url  # Use original URL as fallback
                
            except Exception as e:
                logger.error("Failed to generate signed URL", 
                           error=str(e), 
                           error_type=type(e).__name__,
                           video_url=video_url,
                           bucket_name=bucket_name,
                           blob_path=blob_path)
                import traceback
                logger.error("Signed URL generation traceback", traceback=traceback.format_exc())
                signed_url = video_url  # Use original URL as fallback
        
        # Extract processing time
        processing_time_seconds = result.get('total_time_seconds', 0.0)
        
        # Extract duration from video processing results
        if 'step2_video_processing' in result:
            # Could extract duration from video processing metadata if available
            pass
        
        # Update the local project row
        if video_url:
            logger.info("Preparing local project update",
                       video_url=video_url, 
                       signed_url_available=bool(signed_url),
                       signed_url_length=len(signed_url) if signed_url else 0)
            
            final_signed_url = signed_url or video_url
            logger.info("Final signed URL for local project",
                       final_signed_url_length=len(final_signed_url),
                       is_gs_url=final_signed_url.startswith('gs://'),
                       contains_signature=('Signature=' in final_signed_url))
            
            if final_signed_url.startswith(('gs://', 'https://storage.googleapis.com/')):
                logger.error("Storage URL generation failed in local mode; refusing to store external storage URL",
                           video_url=video_url,
                           final_signed_url=final_signed_url,
                           gcs_service_available=gcs_service.is_available() if gcs_service else False)
                return
            else:
                logger.info("✅ SUCCESS: Generated proper signed URL for database storage",
                           signed_url_preview=final_signed_url[:60] + "..." if len(final_signed_url) > 60 else final_signed_url)
            
            success = await project_store.update_project_with_completion(
                project_id=request.job_id,
                video_url=video_url,
                signed_url=final_signed_url,
                file_size=file_size,
                duration=duration,
                processing_time_seconds=processing_time_seconds
            )
            
            if success:
                logger.info(
                    "Successfully updated local project with completion data",
                    job_id=request.job_id,
                    video_url=video_url,
                    file_size=file_size
                )
            else:
                logger.warning(
                    "Failed to update local project with completion data",
                    job_id=request.job_id
                )
        else:
            logger.warning(
                "No video URL found in result, cannot update local project",
                job_id=request.job_id,
                output_files=output_files
            )
            
    except Exception as e:
        logger.error(
            "Error updating local project completion",
            job_id=request.job_id,
            error=str(e),
            error_type=type(e).__name__
        )

async def update_local_project_failure(request: MediaProcessingRequest, error_message: str):
    """Update local database with video processing failure data."""
    try:
        from video_processor.services.supabase_service import get_supabase_service
        
        project_store = get_supabase_service()
        
        if not project_store.is_available():
            logger.warning("Local project store not available, skipping failure update", job_id=request.job_id)
            return
        
        # Update the project with failure information
        success = await project_store.update_project_with_failure(
            project_id=request.job_id,
            error_message=error_message,
            processing_time_seconds=0.0  # Could track partial processing time if needed
        )
        
        if success:
            logger.info(
                "Successfully updated local project with failure data",
                job_id=request.job_id,
                error_message=error_message
            )
        else:
            logger.warning(
                "Failed to update local project with failure data",
                job_id=request.job_id
            )
            
    except Exception as e:
        logger.error(
            "Error updating local project failure",
            job_id=request.job_id,
            error=str(e),
            error_type=type(e).__name__
        )

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint for Cloud Run
    """
    try:
        # Basic health checks with timeout
        check_tasks = [
            asyncio.wait_for(media_processor.check_ffmpeg_availability(), timeout=5.0),
            asyncio.wait_for(media_processor.check_gcs_connectivity(), timeout=10.0)
        ]
        
        results = await asyncio.gather(*check_tasks, return_exceptions=True)
        
        ffmpeg_available = results[0] if not isinstance(results[0], Exception) else False
        gcs_accessible = results[1] if not isinstance(results[1], Exception) else False
        
        # Log any exceptions from health checks
        if isinstance(results[0], Exception):
            logger.warning("ffmpeg_health_check_failed", error=str(results[0]))
        if isinstance(results[1], Exception):
            logger.warning("gcs_health_check_failed", error=str(results[1]))
        
        status = "healthy" if ffmpeg_available and gcs_accessible else "degraded"
        
        response = HealthResponse(
            status=status,
            version="1.0.0",
            checks={
                "ffmpeg": ffmpeg_available,
                "gcs": gcs_accessible
            }
        )
        
        # Return appropriate HTTP status based on health
        if status == "degraded":
            return JSONResponse(
                status_code=503,
                content=response.model_dump()
            )
        
        return response
        
    except Exception as e:
        logger.error("health_check_exception", error=str(e))
        return create_error_response(
            503,
            "HEALTH_CHECK_FAILED",
            "Service health check failed",
            {"error": str(e)}
        )


@router.get("/debug/ffprobe")
async def debug_ffprobe_timing():
    """Debug endpoint to test ffprobe timing against local media storage."""
    url = LOCAL_DEBUG_VIDEO_URL
    
    try:
        logger.info("Starting ffprobe debug test", url=url)
        
        # Test curl timing
        logger.info("Testing curl timing")
        curl_start = time.time()
        try:
            curl_result = subprocess.run(
                ['curl', '-I', '-s', url], 
                capture_output=True, text=True, timeout=30
            )
            curl_time = time.time() - curl_start
        except subprocess.TimeoutExpired:
            curl_time = 30.0
            curl_result = type('obj', (object,), {'returncode': -1, 'stdout': '', 'stderr': 'TIMEOUT'})
        except FileNotFoundError:
            curl_time = 0.0
            curl_result = type('obj', (object,), {'returncode': -1, 'stdout': '', 'stderr': 'curl command not found'})
        
        # Test ffprobe timing  
        logger.info("Testing ffprobe timing")
        ffprobe_start = time.time()
        try:
            ffprobe_result = subprocess.run([
                'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', 
                '-of', 'csv=p=0', url
            ], capture_output=True, text=True, timeout=120)
            ffprobe_time = time.time() - ffprobe_start
        except subprocess.TimeoutExpired:
            ffprobe_time = 120.0
            ffprobe_result = type('obj', (object,), {'returncode': -1, 'stdout': '', 'stderr': 'TIMEOUT'})
        except FileNotFoundError:
            ffprobe_time = 0.0
            ffprobe_result = type('obj', (object,), {'returncode': -1, 'stdout': '', 'stderr': 'ffprobe command not found'})
        
        # Test local media host resolution (try multiple methods)
        logger.info("Testing local media host resolution")
        dns_start = time.time()
        dns_result = None
        try:
            # Try nslookup first
            dns_result = subprocess.run(
                ['nslookup', 'localhost'],
                capture_output=True, text=True, timeout=10
            )
            dns_time = time.time() - dns_start
        except (subprocess.TimeoutExpired, FileNotFoundError):
            try:
                # Fallback to host command
                dns_result = subprocess.run(
                    ['host', 'localhost'],
                    capture_output=True, text=True, timeout=10
                )
                dns_time = time.time() - dns_start
            except (subprocess.TimeoutExpired, FileNotFoundError):
                try:
                    # Fallback to dig command
                    dns_result = subprocess.run(
                        ['dig', '+short', 'localhost'],
                        capture_output=True, text=True, timeout=10
                    )
                    dns_time = time.time() - dns_start
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    # Use Python socket as final fallback
                    import socket
                    try:
                        ip = socket.gethostbyname('localhost')
                        dns_time = time.time() - dns_start
                        dns_result = type('obj', (object,), {
                            'returncode': 0, 
                            'stdout': f'localhost resolved to {ip}',
                            'stderr': ''
                        })
                    except Exception:
                        dns_time = time.time() - dns_start
                        dns_result = type('obj', (object,), {
                            'returncode': -1, 
                            'stdout': '', 
                            'stderr': 'All DNS methods failed'
                        })
        
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "test_url": url,
            "curl": {
                "time_seconds": round(curl_time, 2),
                "status": curl_result.returncode if curl_result else -1,
                "headers_preview": curl_result.stdout[:500] if curl_result and hasattr(curl_result, 'stdout') and curl_result.stdout else None,
                "error": curl_result.stderr[:200] if curl_result and hasattr(curl_result, 'stderr') and curl_result.stderr else None
            },
            "ffprobe": {
                "time_seconds": round(ffprobe_time, 2),
                "status": ffprobe_result.returncode,
                "duration_output": ffprobe_result.stdout.strip() if hasattr(ffprobe_result, 'stdout') and ffprobe_result.stdout else None,
                "error": ffprobe_result.stderr[:500] if hasattr(ffprobe_result, 'stderr') and ffprobe_result.stderr else None
            },
            "dns": {
                "time_seconds": round(dns_time, 2),
                "status": dns_result.returncode if dns_result else -1,
                "output_preview": dns_result.stdout[:300] if dns_result and hasattr(dns_result, 'stdout') and dns_result.stdout else None,
                "error": dns_result.stderr[:200] if dns_result and hasattr(dns_result, 'stderr') and dns_result.stderr else None
            }
        }
        
        logger.info("Debug ffprobe test completed", 
                   curl_time=curl_time, 
                   ffprobe_time=ffprobe_time,
                   dns_time=dns_time)
        
        return result
        
    except Exception as e:
        logger.error("Debug ffprobe test failed", error=str(e))
        return {
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@router.get("/debug/ffmpeg-python")
async def debug_ffmpeg_python_timing():
    """Debug endpoint to test ffmpeg-python library timing (same as app uses)"""
    import ffmpeg
    import asyncio
    
    url = LOCAL_DEBUG_VIDEO_URL
    
    try:
        logger.info("Starting ffmpeg-python library test", url=url)
        
        # Test the exact same method your app uses
        logger.info("Testing ffmpeg.probe() via run_in_executor")
        start_time = time.time()
        
        loop = asyncio.get_event_loop()
        probe = await loop.run_in_executor(None, ffmpeg.probe, url)
        
        total_time = time.time() - start_time
        
        # Extract duration like your app does
        duration = None
        if 'format' in probe and 'duration' in probe['format']:
            duration = float(probe['format']['duration'])
        else:
            for stream in probe['streams']:
                if 'duration' in stream:
                    duration = float(stream['duration'])
                    break
        
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "test_url": url,
            "method": "ffmpeg.probe() via run_in_executor",
            "total_time_seconds": round(total_time, 2),
            "duration_found": duration,
            "probe_keys": list(probe.keys()) if probe else None,
            "format_keys": list(probe.get('format', {}).keys()) if probe else None,
            "stream_count": len(probe.get('streams', [])) if probe else 0
        }
        
        logger.info("ffmpeg-python library test completed", total_time=total_time, duration=duration)
        return result
        
    except Exception as e:
        total_time = time.time() - start_time
        logger.error("ffmpeg-python library test failed", error=str(e), total_time=total_time)
        return {
            "error": str(e),
            "total_time_seconds": round(total_time, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

@router.get("/debug/ffmpeg-command")
async def debug_ffmpeg_command():
    """Debug endpoint to test the exact FFmpeg command that's timing out on Cloud Run"""
    import subprocess
    import time
    import asyncio
    from datetime import datetime, timezone
    
    # Test URL
    input_url = LOCAL_DEBUG_AUDIO_URL
    output_path = "/tmp/debug_test_output.mp4"
    
    # Build the exact FFmpeg command that the application would use
    # This mimics a typical video processing command
    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-i', input_url,
        '-vf', 'scale=640:480',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-c:a', 'aac',
        '-t', '10',  # Limit to 10 seconds for testing
        output_path
    ]
    
    total_start = time.time()
    
    try:
        # Test 1: Direct subprocess call with timeout (what should work)
        subprocess_start = time.time()
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=60  # 1 minute timeout for testing
        )
        subprocess_time = time.time() - subprocess_start
        
        # Test 2: Simulate the application's executor pattern
        loop = asyncio.get_event_loop()
        executor_start = time.time()
        
        def run_subprocess():
            return subprocess.run(
                ffmpeg_cmd,
                capture_output=True, 
                text=True,
                timeout=60
            )
        
        executor_result = await loop.run_in_executor(None, run_subprocess)
        executor_time = time.time() - executor_start
        
        total_time = time.time() - total_start
        
        # Clean up test file
        try:
            import os
            if os.path.exists(output_path):
                os.remove(output_path)
        except:
            pass
        
        return {
            "subprocess_direct": {
                "time_seconds": round(subprocess_time, 2),
                "return_code": result.returncode,
                "success": result.returncode == 0,
                "stderr_length": len(result.stderr) if result.stderr else 0
            },
            "executor_pattern": {
                "time_seconds": round(executor_time, 2),
                "return_code": executor_result.returncode,
                "success": executor_result.returncode == 0,
                "stderr_length": len(executor_result.stderr) if executor_result.stderr else 0
            },
            "command_tested": " ".join(ffmpeg_cmd),
            "total_time_seconds": round(total_time, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except subprocess.TimeoutExpired as e:
        return {
            "error": "FFmpeg command timed out",
            "timeout_seconds": 60,
            "command": " ".join(ffmpeg_cmd),
            "total_time_seconds": round(time.time() - total_start, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {
            "error": str(e),
            "command": " ".join(ffmpeg_cmd),
            "total_time_seconds": round(time.time() - total_start, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@router.get("/debug/isolated-video-processing")
async def debug_isolated_video_processing():
    """Debug endpoint to test isolated video processing pipeline without full complexity"""
    import time
    from datetime import datetime, timezone
    from video_processor.services.ffmpeg_processor import get_ffmpeg_processor
    
    # Test parameters - will probe for actual durations
    audio_url = LOCAL_DEBUG_AUDIO_URL
    video_url = LOCAL_DEBUG_VIDEO_URL
    subtitle_url = LOCAL_DEBUG_SUBTITLE_URL
    test_job_id = "debug-test-001"
    test_user_id = 0
    
    # Create VideoFile object for new API
    class TestVideoFile:
        def __init__(self, url: str, duration: Optional[float] = None):
            self.url = url
            self.duration = duration
    
    total_start = time.time()
    results = {}
    
    try:
        logger.info("Starting isolated video processing debug test")
        
        # Initialize ffmpeg processor
        processor_start = time.time()
        ffmpeg_processor = get_ffmpeg_processor()
        processor_init_time = time.time() - processor_start
        results["processor_init_time_seconds"] = round(processor_init_time, 2)
        
        # Step 0: Transcription (to test if this causes resource issues)
        logger.info("Debug Step 0: Starting transcription")
        transcription_start = time.time()
        
        from video_processor.services.transcription_service import TranscriptionServiceSelector
        transcription_service = TranscriptionServiceSelector()
        transcription_config = {
            "service": "whisper",
            "caption_style": "karaoke", 
            "font_size": 52,
            "font_family": "Arial",
            "position": "bottom",
            "default_color": "&HFFFFFF", 
            "highlight_color": "&H00FFFF"
        }
        
        transcription_result = await transcription_service.transcribe_with_service(
            audio_url=audio_url,
            service_name="whisper",
            config=transcription_config
        )
        
        transcription_time = time.time() - transcription_start
        results["step0_transcription"] = {
            "completed": True,
            "time_seconds": round(transcription_time, 2),
            "transcript_length": len(transcription_result.transcript) if transcription_result.transcript else 0,
            "cost": transcription_result.cost if hasattr(transcription_result, 'cost') else 0
        }
        logger.info("Debug Step 0: Transcription completed", time_seconds=transcription_time)
        
        # Step 0.5: GCS Upload (to test if this causes resource exhaustion)
        logger.info("Debug Step 0.5: Starting GCS uploads")
        gcs_upload_start = time.time()
        
        from video_processor.services.gcs_service import get_gcs_service
        gcs_service = get_gcs_service()
        
        # Upload SRT file (like full pipeline does)
        srt_url = await gcs_service.upload_content(
            transcription_result.srt_content,
            test_user_id,
            test_job_id,
            "transcript_0.srt", 
            "output"
        )
        
        # Upload ASS file (like full pipeline does)
        ass_url = await gcs_service.upload_content(
            transcription_result.ass_content,
            test_user_id,
            test_job_id,
            "transcript_0.ass",
            "output"
        )
        
        gcs_upload_time = time.time() - gcs_upload_start
        results["step0_5_gcs_uploads"] = {
            "completed": True,
            "time_seconds": round(gcs_upload_time, 2),
            "srt_url": srt_url,
            "ass_url": ass_url
        }
        logger.info("Debug Step 0.5: GCS uploads completed", time_seconds=gcs_upload_time)
        
        # Step 1: Combine videos with audio (will probe for durations)
        logger.info("Debug Step 1: Starting video combination with duration probing")
        combine_start = time.time()
        
        combined_video_url = await ffmpeg_processor.combine_videos(
            video_files=[TestVideoFile(video_url)],
            audio_url=audio_url,
            user_id=test_user_id,
            job_id=test_job_id,
            processing_options={
                'resolution': '1280x720',  # Lower resolution for faster processing
                'fps': 30,
                'video_codec': 'h264_nvenc' if os.getenv('ENABLE_GPU', 'false').lower() == 'true' else 'libx264',
                'audio_codec': 'aac',
                'preset': 'p4' if os.getenv('ENABLE_GPU', 'false').lower() == 'true' else 'ultrafast',  # NVENC preset
                'threads': 0,  # Use all available CPU cores
                'tune': 'fastdecode' if os.getenv('ENABLE_GPU', 'false').lower() != 'true' else None,
                'gpu_options': {
                    'rc': 'vbr',  # Variable bitrate for NVENC
                    'b:v': '5M',  # Target bitrate
                    'maxrate': '10M',  # Max bitrate
                    'bufsize': '10M'  # Buffer size
                } if os.getenv('ENABLE_GPU', 'false').lower() == 'true' else {}
            },
            upload_result=False  # Don't upload intermediate result
        )
        
        combine_time = time.time() - combine_start
        results["step1_combine_videos"] = {
            "completed": True,
            "time_seconds": round(combine_time, 2),
            "result_url": combined_video_url,
            "probed_durations": True
        }
        logger.info("Debug Step 1: Video combination completed", time_seconds=combine_time)
        
        # Step 2: Burn subtitles  
        logger.info("Debug Step 2: Starting subtitle burning")
        subtitle_start = time.time()
        
        final_video_url = await ffmpeg_processor.burn_subtitles(
            video_url=combined_video_url,
            subtitle_url=ass_url,
            user_id=test_user_id,
            job_id=test_job_id,
            style_options={
                'font_size': 24,
                'font_color': 'white',
                'outline_color': 'black',
                'outline_width': 2
            },
            upload_result=False  # Don't upload, we'll handle this separately
        )
        
        subtitle_time = time.time() - subtitle_start
        results["step2_burn_subtitles"] = {
            "completed": True,
            "time_seconds": round(subtitle_time, 2),
            "result_url": final_video_url
        }
        logger.info("Debug Step 2: Subtitle burning completed", time_seconds=subtitle_time)
        
        # Step 2.5: Upload final video to GCS
        logger.info("Debug Step 2.5: Starting final video upload to GCS")
        upload_start = time.time()
        
        from video_processor.services.gcs_service import get_gcs_service
        gcs_service = get_gcs_service()
        
        final_video_gcs_url = await gcs_service.upload_file(
            final_video_url,  # This is now a local path
            test_user_id,
            test_job_id,
            f"final_video_{test_job_id}.mp4",
            "output"
        )
        
        upload_time = time.time() - upload_start
        results["step2_5_final_upload"] = {
            "completed": True,
            "time_seconds": round(upload_time, 2),
            "gcs_url": final_video_gcs_url,
            "local_path": final_video_url
        }
        logger.info("Debug Step 2.5: Final video upload completed", 
                   time_seconds=upload_time,
                   gcs_url=final_video_gcs_url)
        
        # Step 3: Add usage logging (test resource impact)
        logger.info("Debug Step 3: Starting usage logging")
        usage_start = time.time()
        
        from video_processor.services.usage_logger import usage_logger, UsageEvent, UsageEventType
        from datetime import datetime, timezone
        
        # Log job started event
        usage_logger.log_job_started(
            job_id=test_job_id,
            user_id=test_user_id,
            operation_type="debug_test",
            metadata={
                "video_count": 1,
                "audio_duration_seconds": 10,
                "video_duration_seconds": 10,
                "transcription_service": "whisper"
            }
        )
        
        # Create mock performance metrics for usage logging
        from video_processor.services.performance_tracker import PerformanceMetrics, OperationType
        mock_performance_metrics = PerformanceMetrics(
            job_id=test_job_id,
            operation_type=OperationType.VIDEO_COMBINATION,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            duration_seconds=time.time() - total_start,
            avg_cpu_percent=50.0,
            peak_memory_mb=512.0,
            avg_memory_mb=256.0,
            throughput_ratio=1.0,
            error_occurred=False
        )
        
        # Create mock cost breakdown
        mock_cost_breakdown = {
            "transcription_cost": results["step0_transcription"]["cost"],
            "processing_cost": 0.05,
            "storage_cost": 0.01,
            "total_cost": results["step0_transcription"]["cost"] + 0.06
        }
        
        # Log job completed event  
        usage_logger.log_job_completed(
            job_id=test_job_id,
            performance_metrics=mock_performance_metrics,
            cost_breakdown=mock_cost_breakdown,
            user_id=test_user_id,
            metadata={
                "combined_video_url": combined_video_url,
                "final_video_url": final_video_url,
                "transcription_cost": results["step0_transcription"]["cost"]
            }
        )
        
        usage_time = time.time() - usage_start
        results["step3_usage_logging"] = {
            "completed": True,
            "time_seconds": round(usage_time, 2)
        }
        logger.info("Debug Step 3: Usage logging completed", time_seconds=usage_time)
        
        # Step 4: Send webhook notification (test network impact)
        logger.info("Debug Step 4: Starting webhook notification")
        webhook_start = time.time()
        
        webhook_url = "https://webhook.site/a05e3a04-364a-46a2-a1a9-d3a5ad16e964"  # Test webhook endpoint
        notification_payload = {
            "job_id": test_job_id,
            "status": "completed",
            "result_url": final_video_url,
            "processing_time_seconds": time.time() - total_start,
            "metadata": {
                "steps_completed": 6,
                "transcription_service": "whisper",
                "probed_durations": True
            }
        }
        
        try:
            await send_webhook_notification(
                webhook_url=webhook_url,
                job_id=test_job_id,
                job_status="completed",
                payload=notification_payload
            )
            webhook_success = True
        except Exception as webhook_error:
            logger.error("Webhook notification failed in debug test", error=str(webhook_error))
            webhook_success = False
        
        webhook_time = time.time() - webhook_start
        results["step4_webhook_notification"] = {
            "completed": webhook_success,
            "time_seconds": round(webhook_time, 2),
            "webhook_url": webhook_url
        }
        logger.info("Debug Step 4: Webhook notification completed", 
                   time_seconds=webhook_time, 
                   success=webhook_success)
        
        # Calculate total time
        total_time = time.time() - total_start
        results["total_time_seconds"] = round(total_time, 2)
        results["success"] = True
        
        logger.info("Isolated video processing debug test completed successfully", 
                   total_time=total_time,
                   transcription_time=transcription_time,
                   gcs_upload_time=gcs_upload_time,
                   combine_time=combine_time,
                   subtitle_time=subtitle_time,
                   usage_time=usage_time,
                   webhook_time=webhook_time)
        
        return {
            "status": "success", 
            "test_name": "isolated_video_processing_with_logging_and_webhook",
            "steps_completed": 6,
            "optimization": "Full processing with duration probing",
            "test_files": {
                "video": {"url": video_url},
                "audio": {"url": audio_url}
            },
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        total_time = time.time() - total_start
        logger.error("Isolated video processing debug test failed", 
                    error=str(e), 
                    total_time=total_time)
        
        return {
            "status": "error", 
            "test_name": "isolated_video_processing",
            "error": str(e),
            "error_type": type(e).__name__,
            "partial_results": results,
            "total_time_seconds": round(total_time, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

@router.get("/debug/single-step-video-processing")
async def debug_single_step_video_processing():
    """Debug endpoint to test single-step video+audio+subtitles processing"""
    import time
    from datetime import datetime, timezone
    from video_processor.services.ffmpeg_processor import get_ffmpeg_processor
    from video_processor.services.transcription_service import TranscriptionServiceSelector
    from video_processor.services.gcs_service import get_gcs_service
    from video_processor.services.usage_logger import usage_logger
    
    
    start_time = time.time()
    job_id = f"single_run_debug_{int(time.time())}"
    
    try:
        # Test parameters - use same pattern as isolated debug endpoint
        audio_url = LOCAL_DEBUG_AUDIO_URL
        video_urls = [
            LOCAL_DEBUG_VIDEO_URL,
        ]
        
        # Create VideoFile object for new API (same pattern as isolated debug)
        class TestVideoFile:
            def __init__(self, url: str, duration: Optional[float] = None):
                self.url = url
                self.duration = duration
        
        total_start = time.time()
        results = {}
        
        logger.info("Starting single-step video processing debug test")
        
        # Get processor instances
        ffmpeg_processor = get_ffmpeg_processor()
        transcription_service = TranscriptionServiceSelector()
        gcs_service = get_gcs_service()
        
        # Step 1: Get durations (actual probing, not hardcoded)
        logger.info("Debug Step 1: Starting duration probing")
        step1_start = time.time()
        
        audio_duration = await ffmpeg_processor._get_duration_from_url(audio_url)
        video_durations = {}
        for video_url in video_urls:
            try:
                duration = await ffmpeg_processor._get_duration_from_url(video_url)
                video_durations[video_url] = duration
            except Exception as e:
                logger.warning(f"Failed to probe video duration for {video_url}, using fallback", error=str(e))
                video_durations[video_url] = 10.0  # Use fallback duration
        
        step1_time = time.time() - step1_start
        results["step1_duration_probing"] = {
            "completed": True,
            "time_seconds": round(step1_time, 2),
            "audio_duration": audio_duration,
            "video_durations": video_durations
        }
        logger.info("Debug Step 1: Duration probing completed", time_seconds=step1_time)
        
        # Step 2: Transcription 
        logger.info("Debug Step 2: Starting transcription")
        step2_start = time.time()
        
        transcription_config = {
            "service": "whisper",
            "caption_style": "karaoke", 
            "font_size": 24,
            "font_family": "Arial",
            "position": "bottom",
            "default_color": "&HFFFFFF", 
            "highlight_color": "&H00FFFF"
        }
        
        # Transcribe audio
        result = await transcription_service.transcribe_with_service(
            audio_url=audio_url,
            service_name="whisper",
            config=transcription_config
        )
        
        step2_time = time.time() - step2_start
        results["step2_transcription"] = {
            "completed": True,
            "time_seconds": round(step2_time, 2),
            "transcript_length": len(result.transcript) if result.transcript else 0,
            "cost": result.cost if hasattr(result, 'cost') else 0
        }
        logger.info("Debug Step 2: Transcription completed", time_seconds=step2_time)
        
        # Step 3: Upload SRT file to GCS (simulate subtitle file availability)
        logger.info("Debug Step 3: Starting subtitle upload")
        step3_start = time.time()
        
        subtitle_gcs_url = await gcs_service.upload_content(
            result.srt_content,
            1,  # user_id
            job_id,
            f"debug_subtitles_{job_id}.srt",
            "output"  # file_type
        )
        
        step3_time = time.time() - step3_start
        results["step3_subtitle_upload"] = {
            "completed": True,
            "time_seconds": round(step3_time, 2),
            "subtitle_gcs_url": subtitle_gcs_url
        }
        logger.info("Debug Step 3: Subtitle upload completed", time_seconds=step3_time)
        
        # Step 4: SINGLE-STEP video+audio+subtitles processing
        logger.info("Debug Step 4: Starting single-step video+audio+subtitles processing")
        step4_start = time.time()
        
        processing_options = {
            'resolution': '1280x720',  # Lower resolution for faster processing
            'fps': 30,
            'video_codec': 'h264_nvenc' if os.getenv('ENABLE_GPU', 'false').lower() == 'true' else 'libx264',
            'audio_codec': 'aac',
            'preset': 'p4' if os.getenv('ENABLE_GPU', 'false').lower() == 'true' else 'ultrafast',
            'threads': 0,  # Use all available CPU cores
            'tune': 'fastdecode' if os.getenv('ENABLE_GPU', 'false').lower() != 'true' else None,
            'gpu_options': {
                'rc': 'vbr',  # Variable bitrate for NVENC
                'b:v': '5M',  # Target bitrate
                'maxrate': '10M',  # Max bitrate
                'bufsize': '10M'  # Buffer size
            } if os.getenv('ENABLE_GPU', 'false').lower() == 'true' else {}
        }
        
        style_options = {
            'font_name': 'Arial',
            'font_size': 24,
            'font_color': 'white',
            'outline_color': 'black',
            'outline_width': 2,
            'alignment': 'bottom_center',
            'margin_v': 20
        }
        
        # Create video files using TestVideoFile class (same pattern as isolated debug)
        video_files = [
            TestVideoFile(url, video_durations[url]) 
            for url in video_urls
        ]
        
        # Use NEW single-step method
        final_video_url = await ffmpeg_processor.combine_videos_with_subtitles(
            video_files,
            audio_url,
            subtitle_gcs_url,
            1,  # user_id
            job_id,
            processing_options,
            style_options,
            audio_duration=audio_duration,
            upload_result=False  # Return local path for timing analysis
        )
        
        step4_time = time.time() - step4_start
        results["step4_single_step_processing"] = {
            "completed": True,
            "time_seconds": round(step4_time, 2),
            "result_url": final_video_url
        }
        logger.info("Debug Step 4: Single-step processing completed", time_seconds=step4_time)
        
        # Step 5: Upload final result to GCS
        logger.info("Debug Step 5: Starting final video upload")
        step5_start = time.time()
        
        final_gcs_url = await gcs_service.upload_file(
            final_video_url,
            1,  # user_id
            job_id,
            f"debug_single_step_final_{job_id}.mp4",
            "output"  # file_type
        )
        
        step5_time = time.time() - step5_start
        results["step5_final_upload"] = {
            "completed": True,
            "time_seconds": round(step5_time, 2),
            "gcs_url": final_gcs_url,
            "local_path": final_video_url
        }
        logger.info("Debug Step 5: Final video upload completed", time_seconds=step5_time, gcs_url=final_gcs_url)
        
        # Step 6: Test usage logger
        logger.info("Debug Step 6: Starting usage logging")
        step6_start = time.time()
        
        # Test usage logging
        usage_logger.log_transcription_event(
            job_id=job_id,
            service_name='whisper',
            audio_duration=audio_duration,
            processing_time=step2_time,
            cost=result.cost or 0.0,
            metadata={'debug': True, 'single_step': True}
        )
        
        step6_time = time.time() - step6_start
        results["step6_usage_logging"] = {
            "completed": True,
            "time_seconds": round(step6_time, 2)
        }
        logger.info("Debug Step 6: Usage logging completed", time_seconds=step6_time)
        
        # Calculate total time
        total_time = time.time() - total_start
        results["total_time_seconds"] = round(total_time, 2)
        results["success"] = True
        
        logger.info("Single-step video processing debug test completed successfully", 
                   total_time=total_time,
                   single_step_time=step4_time)
        
        return {
            "status": "success", 
            "test_name": "single_step_video_audio_subtitles_processing",
            "steps_completed": 6,
            "optimization": "Single-step FFmpeg operation for video+audio+subtitles",
            "test_files": {
                "video_urls": video_urls,
                "audio_url": audio_url,
                "subtitle_url": subtitle_gcs_url
            },
            "results": results,
            "gpu_enabled": os.getenv('ENABLE_GPU', 'false').lower() == 'true',
            "comparison_note": "Compare step4_single_step_processing time to (combine_videos + burn_subtitles) from two-step process",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        total_time = time.time() - total_start
        logger.error("Single-step debug test failed", error=str(e), total_time=total_time)
        
        return {
            "status": "error", 
            "test_name": "single_step_video_audio_subtitles_processing",
            "error": str(e),
            "error_type": type(e).__name__,
            "partial_results": results,
            "total_time_seconds": round(total_time, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@router.get("/")
async def service_info():
    """
    Service discovery endpoint
    """
    return {
        "service": "cloud-video-processor",  # Match requirement 11.2 for consistent format
        "version": "1.0.0",
        "description": "Scalable video processing service with multiple transcription options",
        "status": "active",
        "features": [
            "Multi-service transcription (Whisper, Deepgram, AssemblyAI)",
            "FFmpeg video processing and combination", 
            "Subtitle burning and overlay",
            "Background job processing",
            "Webhook notifications",
            "Auto-scaling Cloud Run deployment"
        ],
        "endpoints": {
            "health": "/health",
            "service_info": "/",
            "process_media": "/process-media",
            "transcribe_audio": "/transcribe-audio", 
            "combine_clips": "/combine-clips",
            "add_audio": "/add-audio",
            "split_video": "/split-video",
            "burn_subtitles": "/burn-subtitles",
            "job_status": "/status/{job_id}"
        },
        "authentication": "Bearer token (Google Service Account)",
        "documentation": "See API endpoints for request/response schemas"
    }


@router.post("/ask-vyra/compose-scene-video", response_model=AskVyraComposeSceneVideoResponse)
async def ask_vyra_compose_scene_video(
    request: AskVyraComposeSceneVideoRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Compose Ask-Vyra scene assets (animated SVG + audio URL) into one final video.
    """
    await validate_service_account(credentials.credentials)

    if not request.scene_assets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_scene_assets", "message": "scene_assets cannot be empty."},
        )

    fps = max(12, min(int(request.fps or 30), 60))
    session_id = request.session_id or str(uuid.uuid4())
    user_id = str(request.user_id or "anonymous")
    total_scenes = len(request.scene_assets)

    logger.info(
        "ask_vyra_compose_started",
        session_id=session_id,
        user_id=user_id,
        total_scenes=total_scenes,
        fps=fps,
        progress_percent=0,
        stage="started",
    )

    gcs_service = get_gcs_service()
    if not gcs_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "gcs_unavailable", "message": "GCS service is not available."},
        )

    work_dir = tempfile.mkdtemp(prefix="ask_vyra_scene_video_")
    try:
        logger.info(
            "ask_vyra_compose_stage",
            session_id=session_id,
            user_id=user_id,
            progress_percent=5,
            stage="preparing_segments",
        )
        segment_paths: List[str] = [
            os.path.join(work_dir, f"segment_{idx:04d}.mp4")
            for idx in range(len(request.scene_assets))
        ]

        scene_progress = {"completed": 0}

        async def _build_one_segment(idx: int, item: AskVyraSceneAssetItem) -> None:
            normalized_svg = _normalize_svg_xml(item.svg_code or "")
            if not normalized_svg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"error": "invalid_svg", "message": f"Invalid SVG for scene {idx + 1}."},
                )
            await _mux_scene_svg_audio_to_segment(
                svg_code=normalized_svg,
                audio_url=item.audio_url,
                segment_path=segment_paths[idx],
                fps=fps,
                session_id=session_id,
                user_id=user_id,
                scene_index=idx + 1,
                scenes_total=total_scenes,
            )
            scene_progress["completed"] += 1
            completed = scene_progress["completed"]
            segment_progress = 10 + int((completed / total_scenes) * 55)
            logger.info(
                "ask_vyra_compose_scene_completed",
                session_id=session_id,
                user_id=user_id,
                scene_index=idx + 1,
                scenes_completed=completed,
                scenes_total=total_scenes,
                progress_percent=min(segment_progress, 65),
                stage="rendering_segments",
            )

        max_parallel = min(2, max(1, len(request.scene_assets)))
        semaphore = asyncio.Semaphore(max_parallel)

        async def _guarded_build(idx: int, item: AskVyraSceneAssetItem) -> None:
            async with semaphore:
                await _build_one_segment(idx, item)

        await asyncio.gather(*[
            _guarded_build(idx, item) for idx, item in enumerate(request.scene_assets)
        ])

        logger.info(
            "ask_vyra_compose_stage",
            session_id=session_id,
            user_id=user_id,
            progress_percent=70,
            stage="segments_ready_concat_starting",
        )

        list_path = os.path.join(work_dir, "concat_list.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for seg in segment_paths:
                safe_path = seg.replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")

        output_path = os.path.join(work_dir, f"final_{uuid.uuid4().hex}.mp4")
        concat_duration = 0.0
        for seg in segment_paths:
            try:
                concat_duration += await _probe_media_duration_seconds(seg)
            except Exception:
                pass
        concat_duration = concat_duration if concat_duration > 0 else None

        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            "-progress", "pipe:2",
            "-nostats",
            output_path,
        ]
        try:
            await _run_ffmpeg_with_progress(
                concat_cmd,
                session_id=session_id,
                user_id=user_id,
                stage="concat_segments",
                duration_seconds=concat_duration,
            )
        except Exception:
            logger.info(
                "ask_vyra_compose_concat_fallback",
                session_id=session_id,
                user_id=user_id,
                progress_percent=78,
                stage="concat_reencode_fallback",
            )
            concat_fallback_cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_path,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                "-r", str(fps),
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "48000",
                "-movflags", "+faststart",
                "-progress", "pipe:2",
                "-nostats",
                output_path,
            ]
            await _run_ffmpeg_with_progress(
                concat_fallback_cmd,
                session_id=session_id,
                user_id=user_id,
                stage="concat_segments_fallback",
                duration_seconds=concat_duration,
            )

        logger.info(
            "ask_vyra_compose_stage",
            session_id=session_id,
            user_id=user_id,
            progress_percent=85,
            stage="concat_completed_upload_starting",
        )

        uploaded_url = await gcs_service.upload_file(
            local_path=output_path,
            user_id=user_id,
            job_id=session_id,
            filename=f"ask_vyra_scene_{session_id}.mp4",
            file_type="output",
            make_public=False,
        )

        final_url = uploaded_url
        if uploaded_url.startswith("gs://"):
            path_without_scheme = uploaded_url.replace("gs://", "", 1)
            bucket_name, blob_name = path_without_scheme.split("/", 1)
            try:
                signed_url = await gcs_service.generate_signed_url(
                    bucket_name=bucket_name,
                    blob_name=blob_name,
                    expiration_minutes=60 * 24,
                )
                if signed_url:
                    final_url = signed_url
            except Exception as sign_err:
                logger.warning("ask_vyra_compose_signed_url_failed", error=str(sign_err))

        logger.info(
            "ask_vyra_compose_completed",
            session_id=session_id,
            user_id=user_id,
            total_scenes=total_scenes,
            progress_percent=100,
            stage="completed",
            video_url=final_url,
        )

        return AskVyraComposeSceneVideoResponse(
            video_url=final_url,
            session_id=session_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("ask_vyra_compose_failed", error=str(e), session_id=session_id, user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "scene_compose_failed", "message": str(e)},
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

@router.post("/process-media", response_model=MediaProcessingResponse)
async def process_media(
    request: MediaProcessingRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Complete media pipeline (transcription + video processing)
    
    Supports operation types:
    - "full_pipeline": Transcription + video processing + subtitle burning
    - "transcribe_only": Audio transcription only  
    - "video_only": Video processing only
    
    Now executes synchronously like debug endpoint for better performance.
    Requires Google Service Account authentication.
    """
    try:
        # Validate authentication
        await validate_service_account(credentials.credentials)
        
        # Validate job ID
        validate_job_id(request.job_id)
        logger.info(f"🚀🚀🚀🚀🚀🚀 Request: {request}")
        # Validate operation type
        valid_operations = {"full_pipeline", "transcribe_only", "video_only"}
        if request.operation not in valid_operations:
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_OPERATION",
                f"Operation must be one of: {', '.join(valid_operations)}",
                {"provided_operation": request.operation, "valid_operations": list(valid_operations)}
            )
        
        # Validate request content based on operation
        if request.operation in ["full_pipeline", "transcribe_only"] and not request.audio_sources:
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "MISSING_AUDIO_SOURCES", 
                f"Operation '{request.operation}' requires at least one audio source"
            )
        
        if request.operation in ["full_pipeline", "video_only"] and not (request.video_files or request.background_image_url or request.image_timeline):
            return create_error_response(
                status.HTTP_400_BAD_REQUEST,
                "MISSING_VIDEO_FILES",
                f"Operation '{request.operation}' requires at least one video file"
            )
        
        logger.info(
            "media_processing_started",
            job_id=request.job_id,
            operation=request.operation,
            audio_sources_count=len(request.audio_sources),
            video_files_count=len(request.video_files)
        )
        
        # Process directly in request handler (like debug endpoint)
        result = await media_processor.process_media_pipeline_simplified(request)
        
        # Update local database with completion data
        await update_local_project_completion(request, result)
        
        # Send webhook notification if provided
        if request.webhook_url:
            try:
                await send_webhook_notification(
                    request.webhook_url,
                    request.job_id,
                    "completed",
                    result
                )
            except Exception as webhook_error:
                logger.warning("webhook_notification_failed", 
                              job_id=request.job_id, 
                              error=str(webhook_error))
        
        return MediaProcessingResponse(
            job_id=request.job_id,
            status="completed",
            message=f"Media processing completed for operation: {request.operation}",
            result=result
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions (validation errors)
        raise
    except Exception as e:
        logger.error(
            "media_processing_failed",
            job_id=request.job_id if hasattr(request, 'job_id') else "unknown",
            error=str(e)
        )
        
        # Update local database with failure data
        await update_local_project_failure(request, str(e))
        
        # Send failure webhook
        if hasattr(request, 'webhook_url') and request.webhook_url:
            try:
                await send_webhook_notification(
                    request.webhook_url,
                    request.job_id,
                    "failed",
                    {"error": str(e)}
                )
            except Exception:
                pass  # Don't fail on webhook errors
        
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "PROCESSING_FAILED",
            "Media processing failed",
            {"error": str(e)}
        )

@router.post("/transcribe-audio", response_model=MediaProcessingResponse)
async def transcribe_audio(
    request: TranscriptionRequest,
    background_tasks: BackgroundTasks,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Audio transcription only
    """
    # Validate authentication
    await validate_service_account(credentials.credentials)
    
    logger.info(
        "transcription_started",
        job_id=request.job_id,
        service=request.transcription_config.get("service", "whisper"),
        audio_sources_count=len(request.audio_sources)
    )
    
    try:
        logger.info(
            "adding_background_task",
            job_id=request.job_id,
            audio_sources=len(request.audio_sources),
            transcription_service=request.transcription_config.get("service", "whisper")
        )
        
        # Process transcription in background
        background_tasks.add_task(
            media_processor.transcribe_audio_only,
            request
        )
        
        logger.info("background_task_added_successfully", job_id=request.job_id)
        
        return MediaProcessingResponse(
            job_id=request.job_id,
            status="processing",
            message="Transcription started"
        )
        
    except Exception as e:
        logger.error(
            "transcription_failed",
            job_id=request.job_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

@router.post("/combine-clips", response_model=MediaProcessingResponse)
async def combine_clips(
    request: VideoCombineRequest,
    background_tasks: BackgroundTasks,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Concatenate multiple video files
    """
    # Validate authentication
    await validate_service_account(credentials.credentials)
    
    logger.info(
        "video_combine_started",
        job_id=request.job_id,
        video_files_count=len(request.video_files)
    )
    
    try:
        # Process video combination in background
        background_tasks.add_task(
            media_processor.combine_video_clips,
            request
        )
        
        return MediaProcessingResponse(
            job_id=request.job_id,
            status="processing",
            message="Video combination started"
        )
        
    except Exception as e:
        logger.error(
            "video_combine_failed",
            job_id=request.job_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Video combination failed: {str(e)}")

@router.post("/add-audio", response_model=MediaProcessingResponse)
async def add_audio(
    request: AudioVideoSyncRequest,
    background_tasks: BackgroundTasks,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Synchronize audio with video
    """
    # Validate authentication
    await validate_service_account(credentials.credentials)
    
    logger.info(
        "audio_video_sync_started",
        job_id=request.job_id,
        video_file=request.video_file,
        audio_file=request.audio_file
    )
    
    try:
        # Process audio/video sync in background
        background_tasks.add_task(
            media_processor.sync_audio_video,
            request
        )
        
        return MediaProcessingResponse(
            job_id=request.job_id,
            status="processing",
            message="Audio/video synchronization started"
        )
        
    except Exception as e:
        logger.error(
            "audio_video_sync_failed",
            job_id=request.job_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Audio/video sync failed: {str(e)}")

@router.post("/split-video", response_model=MediaProcessingResponse)
async def split_video(
    request: VideoSplitRequest,
    background_tasks: BackgroundTasks,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Extract video segments at specific timestamps
    """
    # Validate authentication
    await validate_service_account(credentials.credentials)
    
    logger.info(
        "video_split_started",
        job_id=request.job_id,
        video_file=request.video_file,
        segments_count=len(request.segments)
    )
    
    try:
        # Process video splitting in background
        background_tasks.add_task(
            media_processor.split_video_segments,
            request
        )
        
        return MediaProcessingResponse(
            job_id=request.job_id,
            status="processing",
            message="Video splitting started"
        )
        
    except Exception as e:
        logger.error(
            "video_split_failed",
            job_id=request.job_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Video splitting failed: {str(e)}")

@router.post("/burn-subtitles", response_model=MediaProcessingResponse)
async def burn_subtitles(
    request: SubtitleBurnRequest,
    background_tasks: BackgroundTasks,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Overlay subtitles onto video
    """
    # Validate authentication
    await validate_service_account(credentials.credentials)
    
    logger.info(
        "subtitle_burn_started",
        job_id=request.job_id,
        video_file=request.video_file,
        subtitle_file=request.subtitle_file
    )
    
    try:
        # Process subtitle burning in background
        background_tasks.add_task(
            media_processor.burn_subtitles_to_video,
            request
        )
        
        return MediaProcessingResponse(
            job_id=request.job_id,
            status="processing",
            message="Subtitle burning started"
        )
        
    except Exception as e:
        logger.error(
            "subtitle_burn_failed",
            job_id=request.job_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Subtitle burning failed: {str(e)}")

@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Check processing status for a job
    
    Returns detailed job status including:
    - Current processing step
    - Output files generated
    - Transcript (if available)
    - Error messages (if failed)
    - Processing costs (if applicable)
    """
    try:
        # Validate authentication
        await validate_service_account(credentials.credentials)
        
        # Validate job ID
        validate_job_id(job_id)
        
        # Get job status
        job_status = await media_processor.get_job_status(job_id)
        
        # Check if job exists
        if job_status.status == "failed" and job_status.error_message == "Job not found":
            return create_error_response(
                status.HTTP_404_NOT_FOUND,
                "JOB_NOT_FOUND",
                f"Job with ID '{job_id}' was not found",
                {"job_id": job_id}
            )
        
        logger.info(
            "job_status_retrieved",
            job_id=job_id,
            status=job_status.status,
            output_files_count=len(job_status.output_files)
        )
        
        return job_status
        
    except HTTPException:
        # Re-raise HTTP exceptions (validation/auth errors)
        raise
    except Exception as e:
        logger.error(
            "status_check_failed",
            job_id=job_id,
            error=str(e)
        )
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "STATUS_CHECK_FAILED",
            "Failed to retrieve job status",
            {"job_id": job_id, "error": str(e)}
        )

# Analytics and Usage Tracking Endpoints

@router.get("/analytics/usage")
async def get_usage_analytics(
    start_date: str,
    end_date: str,
    user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get usage analytics for a specific period
    
    Query parameters:
    - start_date: ISO format date string (YYYY-MM-DD)
    - end_date: ISO format date string (YYYY-MM-DD)
    - user_id: Optional user filter
    - organization_id: Optional organization filter
    """
    try:
        await validate_service_account(credentials.credentials)
        
        # Parse dates
        start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
        
        # Validate date range
        if start_dt >= end_dt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Start date must be before end date"
            )
        
        if (end_dt - start_dt).days > 90:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Date range cannot exceed 90 days"
            )
        
        # Generate usage report
        report = analytics_service.generate_usage_report(
            start_dt, end_dt, user_id, organization_id
        )
        
        logger.info(
            "usage_analytics_requested",
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            total_jobs=report["usage_metrics"]["total_jobs"]
        )
        
        return report
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {str(e)}"
        )
    except Exception as e:
        logger.error("usage_analytics_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate usage analytics"
        )

@router.get("/analytics/costs")
async def get_cost_analysis(
    start_date: str,
    end_date: str,
    user_id: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get detailed cost analysis for a specific period
    
    Query parameters:
    - start_date: ISO format date string (YYYY-MM-DD)  
    - end_date: ISO format date string (YYYY-MM-DD)
    - user_id: Optional user filter
    """
    try:
        await validate_service_account(credentials.credentials)
        
        start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
        
        if start_dt >= end_dt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Start date must be before end date"
            )
        
        # Generate cost analysis
        report = analytics_service.generate_cost_analysis(start_dt, end_dt, user_id)
        
        logger.info(
            "cost_analysis_requested",
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            total_cost=report["cost_breakdown"]["total_cost"]
        )
        
        return report
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {str(e)}"
        )
    except Exception as e:
        logger.error("cost_analysis_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate cost analysis"
        )

@router.get("/analytics/performance")
async def get_performance_metrics(
    start_date: str,
    end_date: str,
    operation_type: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get performance metrics for a specific period
    
    Query parameters:
    - start_date: ISO format date string (YYYY-MM-DD)
    - end_date: ISO format date string (YYYY-MM-DD)
    - operation_type: Optional operation type filter (transcription, video_combination, etc.)
    """
    try:
        await validate_service_account(credentials.credentials)
        
        start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
        
        if start_dt >= end_dt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Start date must be before end date"
            )
        
        # Validate operation type
        operation_enum = None
        if operation_type:
            try:
                operation_enum = OperationType(operation_type)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid operation type: {operation_type}"
                )
        
        # Generate performance report
        report = analytics_service.generate_performance_report(
            start_dt, end_dt, operation_enum
        )
        
        logger.info(
            "performance_metrics_requested",
            start_date=start_date,
            end_date=end_date,
            operation_type=operation_type
        )
        
        return report
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {str(e)}"
        )
    except Exception as e:
        logger.error("performance_metrics_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate performance metrics"
        )

@router.get("/analytics/billing")
async def get_billing_report(
    start_date: str,
    end_date: str,
    user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Generate billing report for invoicing
    
    Query parameters:
    - start_date: ISO format date string (YYYY-MM-DD)
    - end_date: ISO format date string (YYYY-MM-DD)
    - user_id: Optional user filter
    - organization_id: Optional organization filter
    """
    try:
        await validate_service_account(credentials.credentials)
        
        start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
        
        if start_dt >= end_dt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Start date must be before end date"
            )
        
        # Generate billing report
        report = analytics_service.generate_billing_report(
            start_dt, end_dt, user_id, organization_id
        )
        
        logger.info(
            "billing_report_requested",
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            total_amount=report["cost_summary"]["total_amount"]
        )
        
        return report
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {str(e)}"
        )
    except Exception as e:
        logger.error("billing_report_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate billing report"
        )

@router.get("/analytics/realtime")
async def get_realtime_metrics(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get real-time system and usage metrics
    """
    try:
        await validate_service_account(credentials.credentials)
        
        metrics = analytics_service.get_real_time_metrics()
        
        logger.info("realtime_metrics_requested")
        
        return metrics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("realtime_metrics_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get real-time metrics"
        )

@router.get("/analytics/user/{user_id}/summary")
async def get_user_usage_summary(
    user_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get usage summary for a specific user
    
    Path parameters:
    - user_id: User identifier
    
    Query parameters:
    - start_date: Optional ISO format date string (YYYY-MM-DD)
    - end_date: Optional ISO format date string (YYYY-MM-DD)
    """
    try:
        await validate_service_account(credentials.credentials)
        
        start_dt = None
        end_dt = None
        
        if start_date:
            start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        if end_date:
            end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
        
        if start_dt and end_dt and start_dt >= end_dt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Start date must be before end date"
            )
        
        # Get user usage summary
        summary = usage_logger.get_user_usage_summary(user_id, start_dt, end_dt)
        
        logger.info(
            "user_usage_summary_requested",
            user_id=user_id,
            total_jobs=summary.get("total_jobs", 0)
        )
        
        return summary
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {str(e)}"
        )
    except Exception as e:
        logger.error("user_usage_summary_failed", user_id=user_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user usage summary"
        )

@router.get("/fonts")
async def list_available_fonts():
    """
    Get list of available custom fonts for subtitle styling
    
    Returns:
        Dict with available fonts and their details
    """
    try:
        available_fonts = ffmpeg_processor.list_available_fonts()
        
        return {
            "available_fonts": available_fonts,
            "fonts_directory": str(ffmpeg_processor.fonts_dir),
            "total_fonts": len(available_fonts),
            "usage_examples": {
                "method_1_transcription_config": {
                    "transcription_config": {
                        "service": "whisper",
                        "caption_style": "karaoke",
                        "font_family": available_fonts[0] if available_fonts else "Arial",
                        "font_size": 52,
                        "position": "bottom",
                        "default_color": "&HFFFFFF",
                        "highlight_color": "&H00FFFF"
                    }
                },
                "method_2_video_parameters": {
                    "video_parameters": {
                        "subtitle_style": {
                            "font_name": available_fonts[0] if available_fonts else "Arial",
                            "font_size": 24,
                            "font_color": "white",
                            "outline_color": "black",
                            "outline_width": 2
                        }
                    }
                }
            }
        }
        
    except Exception as e:
        logger.error("Failed to list available fonts", error=str(e))
        return create_error_response(
            500,
            "FONTS_LIST_FAILED",
            "Failed to retrieve available fonts",
            {"error": str(e)}
        )

@router.post("/timeline/render", response_model=TimelineRenderResponse)
async def render_timeline(
    request: TimelineRenderRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Render video from timeline JSON data

    This endpoint accepts a timeline with multiple tracks containing video, image, audio,
    and text clips with transformations, and renders them into a final video using FFmpeg.

    Request body should include:
    - timeline: Complete timeline data with tracks and clips
    - output_format: Output format (mp4, webm)
    - quality: Quality preset (low, medium, high)

    Returns:
        TimelineRenderResponse with job status and video URL
    """
    start_time = time.time()

    try:
        # Validate service account
        await validate_service_account(credentials.credentials)

        # Generate job ID if not provided
        job_id = request.job_id or f"timeline_render_{int(time.time())}"

        logger.info(
            "timeline_render_started",
            job_id=job_id,
            tracks_count=len(request.timeline.tracks),
            total_clips=sum(len(track.clips) for track in request.timeline.tracks),
            duration=request.timeline.duration,
            canvas_size=f"{request.timeline.canvas.width}x{request.timeline.canvas.height}"
        )

        # Get timeline renderer service
        renderer = get_timeline_renderer()

        # Render the timeline
        video_url, metadata = await renderer.render_timeline(
            timeline=request.timeline,
            job_id=job_id,
            output_format=request.output_format or "mp4",
            quality=request.quality or "high",
            upscale_mode=request.upscale_mode or "none",
            user_id=request.user_id
        )

        processing_time = metadata.get('processing_time', time.time() - start_time)

        return TimelineRenderResponse(
            job_id=job_id,
            status="completed",
            message="Timeline rendered successfully",
            video_url=video_url,
            duration=request.timeline.duration,
            processing_time=processing_time,
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "timeline_render_failed",
            job_id=request.job_id,
            error=str(e),
            exc_info=True
        )
        return create_error_response(
            500,
            "TIMELINE_RENDER_FAILED",
            f"Failed to render timeline: {str(e)}",
            {"error": str(e)}
        )


@router.post("/whiteboard-doodle/generate")
async def generate_whiteboard_doodle(
    request: WhiteboardDoodleRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Generate whiteboard doodle animation from image.

    Takes an image URL and creates an animated doodle effect video
    where the image appears to be drawn on a whiteboard.

    Args:
        request: WhiteboardDoodleRequest with image_url, duration, speed, width, height

    Returns:
        Dict with status, video_url, job_id, and dimensions
    """
    import uuid
    from video_processor.services.gcs_service import get_gcs_service

    try:
        # Validate auth
        await validate_service_account(credentials.credentials)

        job_id = request.job_id or str(uuid.uuid4())

        logger.info(
            "whiteboard_doodle_started",
            job_id=job_id,
            image_url=request.image_url[:50] + "..." if len(request.image_url) > 50 else request.image_url,
            duration=request.duration,
            speed=request.speed,
            dimensions=f"{request.width}x{request.height}"
        )

        # Download image to temp file
        image_path = await ffmpeg_processor._download_media_file(
            request.image_url, "image"
        )

        # Generate doodle video using existing function
        output_path = ffmpeg_processor._create_doodle_effect_video(
            image_path=image_path,
            duration=request.duration,
            width=request.width,
            height=request.height,
            fps=24,
            speed=request.speed
        )

        logger.info("whiteboard_doodle_video_generated", output_path=str(output_path))

        # Store whiteboard doodle output in local media storage.
        gcs = get_gcs_service()
        public_url = await gcs.upload_file(
            local_path=str(output_path),
            destination_path=f"whiteboard-doodle/{job_id}.mp4",
        )

        logger.info(
            "whiteboard_doodle_complete",
            job_id=job_id,
            video_url=public_url
        )

        return {
            "status": "success",
            "video_url": public_url,
            "job_id": job_id,
            "dimensions": {
                "width": request.width,
                "height": request.height
            }
        }

    except Exception as e:
        logger.error(
            "whiteboard_doodle_failed",
            job_id=request.job_id,
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(
            status_code=500,
            detail=f"Generation failed: {str(e)}"
        )


@router.post("/manim/generate", response_model=ManimGenerateResponse)
async def generate_manim_video(
    request: ManimGenerateRequest,
    background_tasks: BackgroundTasks,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Generate Manim animation video from a text prompt.

    Uses Gemini AI to generate Manim Python code and renders it to video.
    The generated video is uploaded to GCS and the URL is returned.

    Args:
        request: ManimGenerateRequest with prompt, mode, quality, etc.

    Returns:
        ManimGenerateResponse with video_url, generated code, and status
    """
    import uuid
    from video_processor.services.manim_service import get_manim_service

    try:
        # Validate auth
        await validate_service_account(credentials.credentials)

        job_id = request.job_id or str(uuid.uuid4())
        user_id = request.user_id or "anonymous"
        start_time = time.time()

        logger.info(
            "manim_generation_started",
            job_id=job_id,
            user_id=user_id,
            prompt=request.prompt[:100] + "..." if len(request.prompt) > 100 else request.prompt,
            mode=request.mode,
            quality=request.quality,
            aspect_ratio=request.aspect_ratio,
            model=request.model
        )

        # Get manim service and generate video
        manim_service = get_manim_service()
        result = await manim_service.generate_video(
            prompt=request.prompt,
            user_id=user_id,
            project_id=request.project_id,
            scene_id=request.scene_id,
            job_id=job_id,
            model=request.model,
            mode=request.mode,
            quality=request.quality,
            aspect_ratio=request.aspect_ratio,
            max_retries=3
        )

        processing_time = time.time() - start_time

        if result["success"]:
            logger.info(
                "manim_generation_complete",
                job_id=job_id,
                video_url=result["video_url"],
                gcs_path=result.get("gcs_path"),
                generated_id=result.get("generated_id"),
                file_size=result.get("file_size"),
                processing_time=processing_time
            )

            # Send webhook notification if URL provided
            if request.webhook_url:
                background_tasks.add_task(
                    send_webhook_notification,
                    request.webhook_url,
                    job_id,
                    "completed",
                    {
                        "video_url": result["video_url"],
                        "gcs_path": result.get("gcs_path"),
                        "code": result["code"],
                        "project_id": request.project_id,
                        "scene_id": request.scene_id,
                        "generated_id": result.get("generated_id"),
                        "file_size": result.get("file_size"),
                        "processing_time": processing_time
                    }
                )

            return ManimGenerateResponse(
                success=True,
                job_id=job_id,
                status="completed",
                video_url=result["video_url"],
                gcs_path=result.get("gcs_path"),
                code=result["code"],
                message="Manim animation generated successfully",
                processing_time=processing_time,
                file_size=result.get("file_size"),
                generated_id=result.get("generated_id"),
                completed_at=datetime.now(timezone.utc)
            )
        else:
            logger.error(
                "manim_generation_failed",
                job_id=job_id,
                error=result["error"],
                processing_time=processing_time
            )

            # Send failure webhook if URL provided
            if request.webhook_url:
                background_tasks.add_task(
                    send_webhook_notification,
                    request.webhook_url,
                    job_id,
                    "failed",
                    {
                        "error": result["error"],
                        "code": result["code"],
                        "project_id": request.project_id,
                        "scene_id": request.scene_id
                    }
                )

            return ManimGenerateResponse(
                success=False,
                job_id=job_id,
                status="failed",
                code=result["code"],
                error=result["error"],
                message="Manim animation generation failed",
                processing_time=processing_time
            )

    except Exception as e:
        logger.error(
            "manim_generation_error",
            job_id=request.job_id,
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(
            status_code=500,
            detail=f"Manim generation failed: {str(e)}"
        )


@router.post("/manim/generate-claude", response_model=ManimGenerateResponse)
async def generate_manim_video_claude(
    request: VyraManimRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Generate Manim animation video using Claude AI with code-execution skills.

    Full pipeline: Claude code-gen → Manim render → GCS upload → signed URL.
    """
    import uuid
    from video_processor.services.manim_service import get_manim_service

    try:
        await validate_service_account(credentials.credentials)

        start_time = time.time()
        session_id = request.session_id or str(uuid.uuid4())

        logger.info(
            "vyra_manim_generation_started",
            user_id=request.user_id,
            session_id=session_id,
            description=request.description[:100],
        )

        manim_service = get_manim_service()
        result = await manim_service.generate_video_claude(
            description=request.description,
            user_id=request.user_id,
            session_id=session_id,
            quality=request.quality,
            aspect_ratio=request.aspect_ratio,
            previous_code=request.previous_code,
            max_retries=3,
        )

        processing_time = time.time() - start_time

        if result["success"]:
            return ManimGenerateResponse(
                success=True,
                job_id=session_id,
                status="completed",
                video_url=result["video_url"],
                code=result["code"],
                message="Manim animation generated via Claude",
                processing_time=processing_time,
                completed_at=datetime.now(timezone.utc),
            )
        else:
            return ManimGenerateResponse(
                success=False,
                job_id=session_id,
                status="failed",
                code=result.get("code"),
                error=result["error"],
                message="Manim animation generation failed",
                processing_time=processing_time,
            )

    except Exception as e:
        logger.error("vyra_manim_generation_error", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Claude Manim generation failed: {str(e)}"
        )
