from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks, Depends, status
from fastapi.responses import FileResponse
from typing import List, Optional, Any, Dict, Tuple
from pydantic import BaseModel
import tempfile
import shutil
import uuid
import asyncio
import json
import requests
from pathlib import Path
import logging
from datetime import datetime
from uuid import UUID
from pprint import pprint

from services.video_processing_service import VideoProcessingService
from services.tts_service import TTSService
from services.transcription_service import TranscriptionServiceSelector
from models.story_models import (
    VideoProcessingJob, VideoProcessingOptions, VideoFile, 
    AudioFile, GenerationStatus
)
from models.video_project_models import VideoProjectCreate, VideoProjectUpdate
from models.youtube_content_models import (
    YouTubeShortsContentCreate, YouTubeShortsContentUpdate,
    YouTubeShortsContentResponse
)
from auth import get_current_user

from services.video_resolution import get_pixel_dimensions, get_upscale_mode



router = APIRouter(prefix="/api/video", tags=["video-processing"])

# Dashboard router for stats endpoint
dashboard_router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Helper function to get video duration
async def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds"""
    try:
        if not video_path or not Path(video_path).exists():
            return 0.0
        
        import ffmpeg
        probe = ffmpeg.probe(video_path)
        duration = float(probe['format']['duration'])
        return duration
    except Exception as e:
        logger.warning(f"Could not get duration for video {video_path}: {str(e)}")
        return 0.0

# Helper function to generate video thumbnail
async def generate_video_thumbnail(video_path: str, job_id: str) -> Optional[str]:
    """Generate a thumbnail for a video file"""
    try:
        if not video_path or not Path(video_path).exists():
            return None
        
        # Create thumbnails directory
        thumbnails_dir = Path("data/thumbnails")
        thumbnails_dir.mkdir(exist_ok=True)
        
        thumbnail_path = thumbnails_dir / f"{job_id}_thumb.jpg"
        
        # Skip if thumbnail already exists
        if thumbnail_path.exists():
            return f"/thumbnails/{thumbnail_path.name}"
        
        import ffmpeg
        
        # Extract frame at 1 second (or 10% of video duration)
        duration = await get_video_duration(video_path)
        timestamp = min(1.0, duration * 0.1) if duration > 0 else 1.0
        
        # Generate thumbnail
        (
            ffmpeg
            .input(video_path, ss=timestamp)
            .output(str(thumbnail_path), vframes=1, format='image2', vcodec='mjpeg', s='320x180')
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        
        if thumbnail_path.exists():
            return f"/thumbnails/{thumbnail_path.name}"
        else:
            return None
            
    except Exception as e:
        logger.warning(f"Could not generate thumbnail for video {video_path}: {str(e)}")
        return None
video_service = VideoProcessingService()
tts_service = TTSService()
logger = logging.getLogger(__name__)

class VideoProcessingRequest(BaseModel):
    audio_file_id: str
    background_video_paths: List[str]
    caption_file_path: Optional[str] = None
    processing_options: Optional[VideoProcessingOptions] = None
    project_title: Optional[str] = None
    # Music options
    background_music_id: Optional[str] = None  # ID from preset music library
    music_volume: Optional[float] = 0.25  # Volume level (0.0-1.0)
    music_fade_in: Optional[float] = 2.0  # Fade in duration in seconds
    music_fade_out: Optional[float] = 3.0  # Fade out duration in seconds

class VideoJobResponse(BaseModel):
    job: VideoProcessingJob
    message: str

@router.post("/process", response_model=VideoJobResponse)
async def create_video_processing_job(request: VideoProcessingRequest) -> VideoJobResponse:
    """
    Create a new video processing job
    
    Args:
        request: Video processing request with audio and video files
    
    Returns:
        Video processing job information
    """
    try:
        # Load audio file metadata
        audio_file = await tts_service.load_audio_metadata(request.audio_file_id)
        
        if not audio_file:
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        # Validate audio file exists
        if not Path(audio_file.file_path).exists():
            raise HTTPException(status_code=404, detail="Audio file not found on disk")
        
        # Validate background videos
        valid_videos = []
        for video_path in request.background_video_paths:
            if Path(video_path).exists():
                valid_videos.append(video_path)
            else:
                raise HTTPException(status_code=404, detail=f"Background video not found: {video_path}")
        
        if not valid_videos:
            raise HTTPException(status_code=400, detail="No valid background videos provided")
        
        # Validate caption file if provided
        if request.caption_file_path and not Path(request.caption_file_path).exists():
            raise HTTPException(status_code=404, detail="Caption file not found")
        
        # Create video processing job
        job = await video_service.create_video_processing_job(
            audio_file=audio_file,
            background_video_paths=valid_videos,
            caption_file_path=request.caption_file_path,
            processing_options=request.processing_options,
            project_title=request.project_title
        )
        
        return VideoJobResponse(
            job=job,
            message=f"Video processing job created: {job.id}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating video processing job: {str(e)}")

@router.get("/job/{job_id}/status", response_model=VideoProcessingJob)
async def get_video_job_status(job_id: str) -> VideoProcessingJob:
    """
    Get the status of a video processing job
    
    Args:
        job_id: ID of the video processing job
    
    Returns:
        Video processing job with current status
    """
    try:
        job = await video_service.get_job_status(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="Video processing job not found")
        
        return job
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting job status: {str(e)}")

@router.post("/job/{job_id}/cancel")
async def cancel_video_job(job_id: str) -> dict:
    """
    Cancel a video processing job
    
    Args:
        job_id: ID of the video processing job to cancel
    
    Returns:
        Cancellation status
    """
    try:
        success = await video_service.cancel_job(job_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Job not found or cannot be cancelled")
        
        return {
            "job_id": job_id,
            "message": "Video processing job cancelled successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cancelling job: {str(e)}")

@router.get("/job/{job_id}/download")
async def download_processed_video(job_id: str):
    """
    Download the processed video file
    
    Args:
        job_id: ID of the video processing job
    
    Returns:
        Video file for download
    """
    try:
        job = await video_service.get_job_status(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="Video processing job not found")
        
        if job.status != GenerationStatus.COMPLETED:
            raise HTTPException(
                status_code=400, 
                detail=f"Video not ready. Status: {job.status}"
            )
        
        # Check if output file exists
        output_path = Path(job.output_file_path)
        if not output_path.exists():
            raise HTTPException(status_code=404, detail="Processed video file not found")
        
        return FileResponse(
            path=str(output_path),
            filename=f"story_video_{job_id}.mp4",
            media_type="video/mp4"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading video: {str(e)}")

@router.get("/queue/status")
async def get_queue_status() -> dict:
    """
    Get current video processing queue status
    
    Returns:
        Queue status and statistics
    """
    try:
        status = await video_service.get_queue_status()
        return status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting queue status: {str(e)}")

@router.get("/background-videos", response_model=List[VideoFile])
async def list_background_videos() -> List[VideoFile]:
    """
    List available background videos
    
    Returns:
        List of available background video files
    """
    try:
        videos = await video_service.list_background_videos()
        return videos
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing background videos: {str(e)}")

@router.post("/background-videos/upload")
async def upload_background_video(
    video_file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
) -> dict:
    """
    Upload a new background video
    
    Args:
        video_file: Video file to upload
        background_tasks: FastAPI background tasks
    
    Returns:
        Upload status and file information
    """
    try:
        # Validate file type
        if not video_file.content_type.startswith('video/'):
            raise HTTPException(status_code=400, detail="File must be a video file")
        
        # Generate unique filename
        file_extension = Path(video_file.filename).suffix
        if file_extension.lower() not in ['.mp4', '.avi', '.mov', '.mkv']:
            raise HTTPException(status_code=400, detail="Unsupported video format")
        
        unique_filename = f"bg_video_{uuid.uuid4().hex}{file_extension}"
        output_path = video_service.background_videos_dir / unique_filename
        
        # Save uploaded file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            content = await video_file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        # Move to background videos directory
        shutil.move(temp_file_path, str(output_path))
        
        # Get video information
        duration = video_service._get_duration(str(output_path))
        
        return {
            "filename": unique_filename,
            "file_path": str(output_path),
            "duration": duration,
            "size": len(content),
            "message": "Background video uploaded successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading background video: {str(e)}")

@router.get("/processing-options")
async def get_processing_options() -> dict:
    """
    Get available video processing options
    
    Returns:
        Available processing options and their descriptions
    """
    return {
        "resolutions": [
            {"value": "1920x1080", "label": "Full HD (1080p)"},
            {"value": "1280x720", "label": "HD (720p)", "default": True},
            {"value": "854x480", "label": "SD (480p)"},
            {"value": "640x360", "label": "Low (360p)"}
        ],
        "fps_options": [24, 30, 60],
        "video_codecs": [
            {"value": "libx264", "label": "H.264 (recommended)", "default": True},
            {"value": "libx265", "label": "H.265 (smaller files)"},
            {"value": "libvpx-vp9", "label": "VP9 (web optimized)"}
        ],
        "audio_codecs": [
            {"value": "aac", "label": "AAC (recommended)", "default": True},
            {"value": "mp3", "label": "MP3"},
            {"value": "opus", "label": "Opus (high quality)"}
        ],
        "quality_levels": [
            {"value": "low", "label": "Low (fast processing)"},
            {"value": "medium", "label": "Medium (balanced)", "default": True},
            {"value": "high", "label": "High (best quality)"}
        ],
        "caption_positions": ["top", "middle", "bottom"],
        "subtitle_styles": [
            {"value": "karaoke", "label": "Karaoke (sentence with highlighted word)", "default": True},
            {"value": "word_by_word", "label": "Word by Word (only current word shown)"},
            {"value": "sentence", "label": "Sentence (full sentences shown)"}
        ],
        "font_families": [
            {"value": "Luckiest Guy", "label": "Luckiest Guy (playful)", "default": True},
            {"value": "Arial", "label": "Arial (clean)"},
            {"value": "Impact", "label": "Impact (bold)"},
            {"value": "app/fonts/LuckiestGuy-Regular.ttf", "label": "Custom Luckiest Guy Font"}
        ]
    }

@router.post("/cleanup")
async def cleanup_temp_files() -> dict:
    """
    Clean up temporary video processing files
    
    Returns:
        Cleanup status
    """
    try:
        await video_service.cleanup_temp_files()
        return {"message": "Temporary video files cleaned up successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cleaning up files: {str(e)}")

@router.post("/generate-complete")
async def generate_complete_video(
    request: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Complete video generation pipeline: Text → TTS → Captions → Video
    
    Enhanced to support both cloud and local processing:
    - Cloud processing (default): Offloads transcription and video processing to cloud-video-processor
    - Local processing (fallback): Uses local services for processing
    
    Args:
        request: Dictionary with text, background_video_url, project_title, and caption_settings
    
    Returns:
        Generated video information
    """
    user_id = None
    try:
        logger.info("🚀 Starting generate_complete_video endpoint")
        logger.info(f"📝 Request received: {pprint(request)}")
        logger.info(f"👤 Current user: {current_user}")
        
        from services.tts_service import TTSService
        from services.whisper_service import WhisperService
        from services.cloud_video_service import cloud_video_service
        from models.story_models import VoiceSettings, AudioSettings, CaptionSettings, VideoProcessingOptions
        from repositories.video_project_repository import VideoProjectRepository
        from db.supabase_client import supabase_client
        import asyncio
        from pathlib import Path
        import uuid
        import tempfile
        from datetime import datetime, timezone
        
        text = request.get('text', '')
        
        # Support for different background types
        background_type = request.get('background_type', 'video')  # 'video', 'image', 'image_timeline'
        background_video_url = request.get('background_video_url', '')
        background_image_url = request.get('background_image_url', '')
        background_image_timeline = request.get('image_timeline', [])
        use_xfade_transitions = request.get('use_xfade_transitions', True)

        logger.info(f"🎬 XFADE DEBUG: Extracted use_xfade_transitions={use_xfade_transitions} from request")

        voice_id = request.get('voice_id','')
        project_title = request.get('project_title', '')
        caption_settings_req = request.get('caption_settings', {})
        video_settings_req = request.get('video_settings', {})

        # Optional profile branding. If the frontend omits it, fall back to the user's saved profile fields.
        include_watermark_logo = request.get('include_watermark_logo')
        watermark_logo_url = request.get('watermark_logo_url')
        watermark_logo_gcs_path = request.get('watermark_logo_gcs_path')
        watermark_logo_position = str(request.get('watermark_logo_position') or 'bottom_right').lower().replace('-', '_')
        if watermark_logo_position not in {'top_left', 'top_right', 'bottom_left', 'bottom_right'}:
            watermark_logo_position = 'bottom_right'
        
        # Check for existing audio to reuse
        existing_audio_id = request.get('existing_audio_id', '')
        project_id = request.get('project_id', '')
        
        # Extract music parameters
        background_music_id = request.get('background_music_id')
        music_volume = request.get('music_volume', 0.25)
        music_fade_in = request.get('music_fade_in', 2.0)
        music_fade_out = request.get('music_fade_out', 3.0)

        # Extract language code for multi-language support
        language_code = request.get('language_code')
        
        # Resolution labels are normalized by services.video_resolution so cloud output matches frontend render settings.
        # Debug logging
        logger.info(f"🎬 Video generation request received:")
        logger.info(f"  - Request: {request}")
        logger.info(f"  - Text length: {len(text)}")
        logger.info(f"  - Background type: {background_type}")
        logger.info(f"  - Background video URL: {background_video_url}")
        logger.info(f"  - Background image URL: {background_image_url}")
        logger.info(f"  - Image timeline segments: {len(background_image_timeline) if background_image_timeline else 0}")
        logger.info(f"  - Voice ID: {voice_id}")
        logger.info(f"  - Project title: '{project_title}'")
        logger.info(f"  - Caption settings: {caption_settings_req}")
        logger.info(f"  - Video settings: {video_settings_req}")
        logger.info(f"  - Existing audio ID: '{existing_audio_id}'")
        logger.info(f"  - Project ID: '{project_id}'")
        logger.info(f"  - Include watermark logo: {include_watermark_logo}")
        logger.info(f"  - Watermark logo position: {watermark_logo_position}")
        logger.info(f"  - Watermark logo URL present: {bool(watermark_logo_url)}")
        logger.info(f"  - Watermark logo GCS path: {watermark_logo_gcs_path}")
        
        # Validate that we have either text content, existing audio, OR image_timeline (which can work without audio)
        if not text.strip() and not existing_audio_id and background_type != 'image_timeline':
            raise HTTPException(status_code=400, detail="Either text content or existing audio file is required")
        
        # Validate background configuration
        if background_type == 'video' and not background_video_url:
            raise HTTPException(status_code=400, detail="Background video URL required for video background")
        elif background_type == 'image' and not background_image_url:
            raise HTTPException(status_code=400, detail="Background image URL required for image background")  
        elif background_type == 'image_timeline' and not background_image_timeline:
            raise HTTPException(status_code=400, detail="Image timeline required for timeline background")
        
        # Get user ID from authenticated user
        user_id = current_user.get('sub', current_user.get('id', 'unknown-user'))
        logger.info(f"🆔 Extracted user_id: {user_id}")
        
        if include_watermark_logo is False:
            watermark_logo_url = None
            watermark_logo_gcs_path = None

        # Resolve saved watermark/logo from public.users if it was not included in the request.
        if include_watermark_logo is not False and not watermark_logo_url and not watermark_logo_gcs_path and user_id != 'unknown-user':
            try:
                user_profile_response = supabase_client.supabase.table('users').select(
                    'watermark_logo_url, watermark_logo_gcs_path'
                ).eq('id', user_id).single().execute()
                user_profile_data = user_profile_response.data or {}
                watermark_logo_url = user_profile_data.get('watermark_logo_url')
                watermark_logo_gcs_path = user_profile_data.get('watermark_logo_gcs_path')
                logger.info(f"🏷️ Loaded profile watermark for user {user_id}: {bool(watermark_logo_url or watermark_logo_gcs_path)}")
            except Exception as watermark_profile_error:
                logger.warning(f"⚠️ Failed to load profile watermark: {watermark_profile_error}")

        # Prefer a fresh signed URL when we have the GCS path, because saved signed URLs can expire.
        if include_watermark_logo is not False and watermark_logo_gcs_path:
            try:
                from services.gcs_service import GCSService
                gcs_service = GCSService()
                refreshed_watermark_url = await gcs_service.generate_signed_url(watermark_logo_gcs_path, expiration_hours=24)
                if refreshed_watermark_url:
                    watermark_logo_url = refreshed_watermark_url
                    logger.info("🏷️ Refreshed watermark logo signed URL from GCS path")
            except Exception as watermark_url_error:
                logger.warning(f"⚠️ Failed to refresh watermark logo signed URL: {watermark_url_error}")

        # Initialize services
        tts_service = TTSService()
        whisper_service = WhisperService(model_size="small")
        
        # Step 1: Check for existing audio or generate new audio
        audio_file = None
        generated_new_audio = False  # Track whether we generated new audio

        if existing_audio_id:
            #logger.info(f"🎵 Checking for existing audio file: {existing_audio_id}")
            try:
                audio_file = await tts_service.load_audio_metadata(existing_audio_id)
                #logger.info(f"🎵 Audio file loaded: {audio_file is not None}")
                if audio_file:
                    logger.info(f"🎵 Audio file status: {audio_file.status}")
                    logger.info(f"🎵 Audio file path: {audio_file.file_path}")
                    logger.info(f"🎵 Audio file GCS path: {getattr(audio_file, 'gcs_path', 'N/A')}")
                if audio_file and audio_file.status == GenerationStatus.COMPLETED:
                    logger.info(f"✅ Using existing audio file: {audio_file.id}")
                else:
                    # If local metadata not found, try GCS direct lookup
                    if not audio_file:
                        logger.info(f"🔍 Local metadata not found, trying GCS direct lookup for: {existing_audio_id}")
                        try:
                            from services.gcs_service import GCSService
                            from datetime import datetime, timezone

                            gcs_service = GCSService()

                            # Try to find audio file in GCS
                            possible_paths = [
                                f"audio/{user_id}/{existing_audio_id}.mp3",
                                f"audio/{user_id}/{existing_audio_id}.wav",
                                f"audio/{user_id}/{existing_audio_id}.m4a",
                                f"audio/{user_id}/{existing_audio_id}.ogg",
                                f"audio/{user_id}/{existing_audio_id}.flac",
                            ]

                            found_path = None
                            for path in possible_paths:
                                blob = gcs_service.bucket.blob(path)
                                if blob.exists():
                                    found_path = path
                                    logger.info(f"✅ Found audio file in GCS: {path}")
                                    break

                            if found_path:
                                # Generate signed URL
                                signed_url = await gcs_service.generate_signed_url(found_path)

                                if signed_url:
                                    # Create AudioFile object from GCS file with default settings
                                    audio_file = AudioFile(
                                        id=UUID(existing_audio_id),
                                        file_path=found_path,
                                        duration=0.0,  # Duration unknown for GCS-only files
                                        format=(
                                            "mp3" if found_path.endswith(".mp3")
                                            else "wav" if found_path.endswith(".wav")
                                            else "m4a" if found_path.endswith(".m4a")
                                            else "ogg" if found_path.endswith(".ogg")
                                            else "flac" if found_path.endswith(".flac")
                                            else "mp3"
                                        ),
                                        status=GenerationStatus.COMPLETED,
                                        created_at=datetime.now(timezone.utc),
                                        url=signed_url,
                                        voice_settings=VoiceSettings(
                                            voice_id="unknown",
                                            speed=1.0,
                                            volume=1.0,
                                            pitch=0.0
                                        ),
                                        audio_settings=AudioSettings(
                                            sample_rate=32000,
                                            bitrate=128000,
                                            format=(
                                                "mp3" if found_path.endswith(".mp3")
                                                else "wav" if found_path.endswith(".wav")
                                                else "m4a" if found_path.endswith(".m4a")
                                                else "ogg" if found_path.endswith(".ogg")
                                                else "flac" if found_path.endswith(".flac")
                                                else "mp3"
                                            ),
                                            channel=1
                                        )
                                    )
                                    # Add GCS path as custom attribute
                                    audio_file.__dict__['gcs_path'] = found_path
                                    logger.info(f"✅ Created AudioFile object from GCS for: {existing_audio_id}")
                                else:
                                    logger.warning(f"⚠️ Failed to generate signed URL for GCS audio")
                                    existing_audio_id = ''
                            else:
                                logger.warning(f"⚠️ Audio file not found in GCS either")
                                existing_audio_id = ''
                        except Exception as gcs_error:
                            logger.warning(f"⚠️ GCS lookup failed: {str(gcs_error)}")
                            existing_audio_id = ''
                    else:
                        #logger.warning(f"⚠️ Existing audio file not found or not completed, generating new audio")
                        #logger.warning(f"⚠️ Audio file: {audio_file}")
                        #logger.warning(f"⚠️ Expected status: {GenerationStatus.COMPLETED}")
                        existing_audio_id = ''
            except Exception as e:
                #logger.warning(f"⚠️ Failed to load existing audio: {str(e)}, generating new audio")
                import traceback
                #logger.warning(f"⚠️ Full traceback: {traceback.format_exc()}")
                existing_audio_id = ''

        # Skip TTS if no text is provided (for video-only generation)
        if not text.strip():
            logger.info("🎵 No text provided - skipping TTS generation (video-only mode)")
            audio_file = None
            generated_new_audio = False
        elif not existing_audio_id or not audio_file:
            #logger.info("🎵 Generating new audio...")
            generated_new_audio = True

            voice_settings = VoiceSettings(
                voice_id=voice_id,
                speed=1.0,
                volume=1.0,
                pitch=0.0
            )

            audio_settings = AudioSettings(
                sample_rate=32000,
                bitrate=128000,
                format="mp3",
                channel=1
            )

            audio_file = await tts_service.text_to_speech_auto_and_wait(
                text=text,
                voice_settings=voice_settings,
                audio_settings=audio_settings,
                processed_story_id=None,  # No processed story for direct text processing
                max_wait_time=900,  # 15 minutes timeout for TTS completion
                user_id=user_id
            )
        else:
            logger.info(f"🎵 Reusing existing audio file: {audio_file.id}, duration: {audio_file.duration}s")
        
        # Step 2: Check processing method and route accordingly
        use_cloud = cloud_video_service.is_cloud_processing_enabled()
        logger.info(f"🔄 Processing method: {'Cloud' if use_cloud else 'Local'}")
        
        if use_cloud:
            # CLOUD PROCESSING PATH
            #logger.info("☁️ Using cloud processing for transcription and video generation")

            # Handle video-only mode (no audio)
            if audio_file is None:
                logger.info("🎵 Video-only mode - no audio file to process")
                audio_url = None
            else:
                # Always try to refresh signed URL from gcs_path first.
                # Uploaded audio often stores a previously signed URL that may expire before regeneration.
                audio_url = None
                gcs_path = getattr(audio_file, 'gcs_path', None)
                if gcs_path:
                    try:
                        from services.gcs_service import GCSService
                        gcs_service = GCSService()
                        refreshed_url = await gcs_service.generate_signed_url(gcs_path, expiration_hours=24)
                        if refreshed_url:
                            audio_url = refreshed_url
                            audio_file.url = refreshed_url
                            logger.info(f"✅ Refreshed audio signed URL from gcs_path: {gcs_path}")
                            try:
                                await tts_service._save_audio_metadata(audio_file)
                            except Exception as metadata_error:
                                logger.warning(f"⚠️ Failed to persist refreshed audio URL metadata: {metadata_error}")
                    except Exception as refresh_error:
                        logger.warning(f"⚠️ Failed to refresh signed URL from gcs_path {gcs_path}: {refresh_error}")

                # Fallback chain if refresh is unavailable
                if not audio_url and getattr(audio_file, 'url', None):
                    audio_url = audio_file.url
                if not audio_url and getattr(audio_file, 'public_url', None):
                    audio_url = audio_file.public_url

                if not audio_url:
                    logger.error("❌ Audio file URL not available for cloud processing")
                    logger.error(f"❌ audio_file.file_path: {getattr(audio_file, 'file_path', None)}")
                    logger.error(f"❌ audio_file.gcs_path: {getattr(audio_file, 'gcs_path', None)}")
                    logger.error(f"❌ audio_file.url: {getattr(audio_file, 'url', None)}")
                    logger.error(f"❌ audio_file.public_url: {getattr(audio_file, 'public_url', None)}")
                    raise HTTPException(
                        status_code=500,
                        detail="Audio file URL not available for cloud processing"
                    )

                logger.info(f"🎵 Using audio URL for cloud processing: {audio_url}")
            logger.info(f"🎵 Audio URL for cloud processing: {audio_url}")
            
            # Prepare processing options with video settings
            processing_options = {
                "fps": 30,
                "video_codec": "libx264", 
                "audio_codec": "aac",
                "quality": "medium"
            }
            
            # Only apply aspect ratio settings for image backgrounds, not video backgrounds
            if background_type in ['image', 'image_timeline']:
                aspect_ratio = video_settings_req.get('aspect_ratio', '9:16')
                resolution_level = video_settings_req.get('resolution', '1080p')
                pixel_resolution = get_pixel_dimensions(aspect_ratio, resolution_level)
                upscale_mode = get_upscale_mode(resolution_level)
                
                processing_options.update({
                    "resolution": pixel_resolution,
                    "aspect_ratio": aspect_ratio,
                    "resolution_label": resolution_level,
                    "upscale_mode": upscale_mode
                })
                
                logger.info(f"📐 Image background - Video dimensions calculated: {aspect_ratio} @ {resolution_level} = {pixel_resolution}, upscale_mode={upscale_mode}")
            else:
                logger.info(f"📐 Video background - Using original video dimensions (aspect ratio will be preserved from source)")
            
            # Check if there's already a project for this request, otherwise create one
            try:
                video_project_repo = VideoProjectRepository(supabase_client)

                # First, try to find existing project by provided project_id
                existing_project = None
                if project_id:
                    try:
                        # Handle prefixed project IDs (e.g. "upload_project_uuid")
                        clean_project_id = project_id
                        if '_' in project_id and len(project_id) > 36:
                            # Extract UUID from prefixed string (UUID is always 36 chars)
                            parts = project_id.split('_')
                            if len(parts) > 1:
                                potential_uuid = parts[-1]  # Get the last part
                                if len(potential_uuid) == 36:
                                    clean_project_id = potential_uuid
                                    logger.info(f"📝 Extracted UUID from prefixed project_id: {project_id} -> {clean_project_id}")

                        existing_project = await video_project_repo.get_by_id(UUID(clean_project_id))
                        if existing_project:
                            logger.info(f"📝 Found existing project by project_id: {clean_project_id}")
                        else:
                            logger.warning(f"⚠️ No project found with project_id: {clean_project_id}")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to find project by project_id {project_id}: {str(e)}")

                # Fall back to finding by audio file ID only if no project_id provided or project not found
                if not existing_project and audio_file and hasattr(audio_file, 'id'):
                    existing_project = await video_project_repo.get_by_audio_file_id(str(audio_file.id))
                    if existing_project:
                        logger.info(f"📝 Found existing project by audio_file_id: {audio_file.id}")

                if existing_project:
                    audio_id_str = audio_file.id if audio_file else "N/A (video-only)"
                    logger.info(f"📝 Found existing project {existing_project.id} for audio file {audio_id_str}")
                    
                    # Update the existing project with video processing details
                    project_update_data = VideoProjectUpdate(
                        title=project_title or existing_project.title,
                        status="processing",
                        processing_method="cloud",
                        processing_options={
                            "cloud_processing": True,
                            "caption_settings": caption_settings_req,
                            "language_code": language_code,  # Store language code for webhook
                            "watermark_logo_gcs_path": watermark_logo_gcs_path,
                            "watermark_logo_position": watermark_logo_position,
                            **processing_options
                        },
                        story_content=text if text else existing_project.story_content
                    )
                    
                    project = await video_project_repo.update(existing_project.id, project_update_data)
                    if project:
                        logger.info(f"📝 Updated existing project {project.id} for video generation")
                    else:
                        logger.error(f"❌ Failed to update project {existing_project.id} - update returned None")
                        # Use the existing project if update failed
                        project = existing_project
                else:
                    logger.info(f"📝 No existing project found, creating new project")
                    logger.info(f"   - project_id provided: {project_id}")
                    logger.info(f"   - audio_file_id: {audio_file.id if audio_file else 'N/A'}")

                    # Create new project record with explicit ID if provided
                    project_data = VideoProjectCreate(
                        id=UUID(project_id) if project_id else None,  # Use provided project_id as the record ID
                        user_id=uuid.UUID(user_id) if isinstance(user_id, str) else user_id,
                        title=project_title or f"Cloud Video {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
                        status="processing",
                        duration=audio_file.duration if audio_file else 0.0,
                        file_size=0,
                        processing_method="cloud",
                        processing_options={
                            "cloud_processing": True,
                            "caption_settings": caption_settings_req,
                            "language_code": language_code,  # Store language code for webhook
                            "watermark_logo_gcs_path": watermark_logo_gcs_path,
                            "watermark_logo_position": watermark_logo_position,
                            **processing_options
                        },
                        story_content=text,  # Store first 1000 chars
                        audio_file_id=audio_file.id if audio_file else None
                    )

                    project = await video_project_repo.create(project_data)
                    logger.info(f"📝 Created new project record {project.id} for cloud processing")
                    logger.info(f"⏱️ Initial project duration set to: {audio_file.duration if audio_file else 0.0}s (from audio file)")
                
            except Exception as db_error:
                logger.error(f"❌ Failed to create project record: {str(db_error)}")
                # Don't fail the request, but log for monitoring
                project = None

            # Store project assets for future editing EARLY (before cloud submission)
            # This ensures assets are saved even if video processing fails
            try:
                from services.project_assets_service import get_project_assets_service

                if project:
                    assets_service = get_project_assets_service()

                    # Prepare audio file data
                    audio_file_data = {
                        'id': str(audio_file.id),
                        'gcs_path': getattr(audio_file, 'gcs_path', None),
                        'url': audio_url,
                        'duration': audio_file.duration
                    } if audio_file else None

                    # Store all assets used in this generation
                    asset_storage_success = await assets_service.store_project_assets(
                        project_id=project.id,
                        generation_request=request,  # Original request data
                        audio_file_data=audio_file_data
                    )

                    if asset_storage_success:
                        logger.info(f"📦 Successfully stored project assets for project {project.id}")
                    else:
                        logger.warning(f"⚠️ Failed to store project assets for project {project.id}")
                else:
                    logger.warning("⚠️ No project created, skipping asset storage")

            except Exception as asset_error:
                logger.error(f"❌ Error storing project assets: {str(asset_error)}")
                # Don't fail the request, just log the error

            # Submit to cloud processing
            try:
                logger.info(f"🚀 Submitting to cloud with project_id: {str(project.id) if project else 'fallback-uuid'}")
                logger.info(f"🎵 Audio URL: {audio_url}")
                logger.info(f"🎬 Background video URL: {background_video_url}")
                logger.info(f"📝 Caption settings: {caption_settings_req}")
                logger.info(f"⚙️ Processing options: {processing_options}")
                
                # Convert image timeline to dict format if needed
                image_timeline_dict = None
                if background_type == 'image_timeline' and background_image_timeline:
                    logger.info(f"🎬 Converting {len(background_image_timeline)} timeline segments to cloud format")
                    image_timeline_dict = []
                    for i, segment in enumerate(background_image_timeline):
                        logger.info(f"🎬 Segment {i}: camera_movement='{segment.get('camera_movement', 'static')}', transition='{segment.get('transition_type', 'cut')}')")

                        # Ensure image_url is not None/empty before adding segment
                        image_url = segment.get('image_url')
                        if image_url:
                            image_timeline_dict.append({
                                'image_url': image_url,
                                'start_time': segment.get('start_time', 0),
                                'end_time': segment.get('end_time', 30),
                                'transition_type': segment.get('transition_type', 'cut'),
                                'transition_duration': segment.get('transition_duration', 0),
                                'camera_movement': segment.get('camera_movement', 'static'),
                                'greenscreen_effect': segment.get('greenscreen_effect')
                            })
                            logger.info(f"🎬 Added segment {i} with image_url: {image_url[:50]}...")
                        else:
                            logger.warning(f"⚠️  Skipping segment {i} - missing or null image_url")
                
                # Load text overlays from database if project exists
                text_overlays_for_render = None
                if project:
                    try:
                        from repositories.project_scenes_repository import get_project_scenes_repository
                        scenes_repo = get_project_scenes_repository()
                        text_layers = await scenes_repo.get_text_layers_by_project(project.id)
                        if text_layers:
                            text_overlays_for_render = text_layers
                            logger.info(f"📝 Loaded {len(text_layers)} text overlays for rendering")
                    except Exception as tl_err:
                        logger.warning(f"Could not load text overlays: {tl_err}")

                cloud_job_id = str(project.id) if project else str(uuid.uuid4())

                async def submit_cloud_video_job_in_background() -> None:
                    """Submit the long-running Cloud Run job after the HTTP response is sent."""
                    try:
                        cloud_result = await cloud_video_service.submit_video_processing_job(
                            audio_url=audio_url,
                            background_video_url=background_video_url if background_type == 'video' else None,
                            background_image_url=background_image_url if background_type == 'image' else None,
                            background_type=background_type,
                            image_timeline=image_timeline_dict if background_type == 'image_timeline' else None,
                            use_xfade_transitions=use_xfade_transitions,
                            caption_settings=caption_settings_req,
                            processing_options=processing_options,
                            user_id=user_id,
                            project_id=cloud_job_id,
                            project_title=project_title,
                            # Music parameters
                            background_music_id=background_music_id,
                            music_volume=music_volume,
                            music_fade_in=music_fade_in,
                            music_fade_out=music_fade_out,
                            # Language code for multi-language support
                            language_code=language_code,
                            # Text overlays
                            text_overlays=text_overlays_for_render,
                            # Profile branding
                            watermark_logo_url=watermark_logo_url,
                            watermark_logo_gcs_path=watermark_logo_gcs_path,
                            watermark_logo_position=watermark_logo_position
                        )
                        logger.info(f"✅ Background cloud job completed/submitted: {cloud_result}")
                    except Exception as cloud_submit_error:
                        logger.error(
                            "❌ Background cloud submission failed",
                            extra={
                                "project_id": cloud_job_id,
                                "error": str(cloud_submit_error),
                            },
                        )
                        if project:
                            try:
                                failure_options = {
                                    "cloud_processing": True,
                                    "cloud_submission_failed": True,
                                    "cloud_submission_error": str(cloud_submit_error),
                                    "caption_settings": caption_settings_req,
                                    "language_code": language_code,
                                    "watermark_logo_gcs_path": watermark_logo_gcs_path,
                                    "watermark_logo_position": watermark_logo_position,
                                    **processing_options,
                                }
                                await video_project_repo.update(
                                    project.id,
                                    VideoProjectUpdate(
                                        status="failed",
                                        processing_method="cloud",
                                        processing_options=failure_options,
                                        webhook_received_at=datetime.now(timezone.utc),
                                    ),
                                )
                            except Exception as project_update_error:
                                logger.error(
                                    f"❌ Failed to mark project {project.id} failed after cloud submission error: {project_update_error}"
                                )

                background_tasks.add_task(submit_cloud_video_job_in_background)
                logger.info(f"✅ Cloud job queued in background: {cloud_job_id}")

                # Save predictable video_file_id immediately to video_project_languages table
                if project and language_code:
                    try:
                        # Construct the predictable video file path
                        # Format: videos/{user_id}/{project_id}_{language_code}.mp4
                        predictable_video_path = f"videos/{user_id}/{str(project.id)}_{language_code}.mp4"

                        logger.info(f"💾 Saving predictable video_file_id: {predictable_video_path}")

                        # Update the language record with the predictable path
                        lang_update = supabase_client.supabase.table("video_project_languages")\
                            .update({"video_file_id": predictable_video_path})\
                            .eq("project_id", str(project.id))\
                            .eq("language_code", language_code)\
                            .execute()

                        if lang_update.data:
                            logger.info(f"✅ Saved predictable video_file_id for {language_code}: {predictable_video_path}")
                        else:
                            logger.warning(f"⚠️ Could not save video_file_id - language record may not exist yet")

                    except Exception as video_id_error:
                        logger.error(f"❌ Failed to save video_file_id: {str(video_id_error)}")
                        # Don't fail the request, just log the error

                # Return immediate response for cloud processing
                return {
                    "job_id": cloud_job_id,
                    "audio_file_id": str(audio_file.id) if audio_file else None,
                    "duration": audio_file.duration if audio_file else 0.0,
                    "status": "processing",
                    "message": "Video processing submitted to cloud. You will be notified when complete.",
                    "cloud_hosted": True,
                    "processing_method": "cloud",
                    "project_id": str(project.id) if project else cloud_job_id,
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                    "estimated_completion": "2-5 minutes"
                }
                
            except Exception as cloud_error:
                logger.error(f"❌ Cloud processing failed: {type(cloud_error).__name__}: {str(cloud_error)}")
                logger.error(f"❌ Cloud error details: {repr(cloud_error)}")
                import traceback
                logger.error(f"❌ Cloud error traceback: {traceback.format_exc()}")
                # Fall back to local processing
                logger.info("🔄 Falling back to local processing due to cloud failure")
                use_cloud = False
        
        if not use_cloud:
            # LOCAL PROCESSING PATH (FALLBACK)
            logger.info("🖥️ Using local processing for transcription and video generation")

            # Local processing requires audio - video-only mode only works with cloud processing
            if audio_file is None:
                raise HTTPException(
                    status_code=400,
                    detail="Video-only mode (no audio/text) requires cloud processing to be enabled. Local processing requires audio for transcription."
                )

            # Step 2: Generate captions (LOCAL)
            logger.info('generating captions...')
            transcription_result = await whisper_service.transcribe_from_audio_file(audio_file)
            
            from models.story_models import SubtitleStyle
            
            caption_settings = CaptionSettings(
                position=caption_settings_req.get('position', 'middle'),
                font_size=caption_settings_req.get('font_size', 32),
                font_family=caption_settings_req.get('font_family', "Luckiest Guy"),
                font_file_path=caption_settings_req.get('font_file_path'),  # Support custom font files
                highlight_color=caption_settings_req.get('highlight_color', "&H00FFFF&"),
                default_color=caption_settings_req.get('default_color', "&HFFFFFF&"),
                subtitle_style=SubtitleStyle(caption_settings_req.get('subtitle_style', 'karaoke'))
            )
            
            animated_caption_file = await whisper_service.generate_animated_captions(
                word_segments=transcription_result.word_segments,
                language=transcription_result.language,
                settings=caption_settings
            )
            
            # Step 3: Generate video (LOCAL)
            logger.info('creating video...')
            
            # Calculate resolution for local processing - only for image backgrounds
            processing_options_dict = {
                "fps": 30,
                "video_codec": "libx264",
                "audio_codec": "aac",
                "quality": "medium",
                "add_captions": True,
                "caption_position": caption_settings_req.get('position', 'middle')
            }
            
            # Only apply aspect ratio settings for image backgrounds, not video backgrounds
            if background_type in ['image', 'image_timeline']:
                aspect_ratio = video_settings_req.get('aspect_ratio', '9:16')
                resolution_level = video_settings_req.get('resolution', '1080p')
                pixel_resolution = get_pixel_dimensions(aspect_ratio, resolution_level)
                upscale_mode = get_upscale_mode(resolution_level)
                
                processing_options_dict["resolution"] = pixel_resolution
                processing_options_dict["resolution_label"] = resolution_level
                processing_options_dict["upscale_mode"] = upscale_mode
                logger.info(f"📐 Local processing - Image background - Video dimensions: {aspect_ratio} @ {resolution_level} = {pixel_resolution}, upscale_mode={upscale_mode}")
            else:
                logger.info(f"📐 Local processing - Video background - Using original video dimensions")
            
            processing_options = VideoProcessingOptions(**processing_options_dict)
        
        # Handle different types of backgrounds (video and image)
        background_videos = []
        temp_files_to_cleanup = []
        
        if background_type == 'video':
            # Handle video backgrounds (existing logic)
            if background_video_url.startswith('http://localhost:8000/'):
                # Convert local URL to local file path
                filename = background_video_url.split('/')[-1]
                local_path = Path(__file__).parent.parent / filename
                if local_path.exists():
                    background_videos = [str(local_path)]
            elif background_video_url.startswith('https://') and ('supabase.co' in background_video_url or 'commondatastorage.googleapis.com' in background_video_url):
                # Handle Supabase and other remote URLs by downloading temporarily
                import requests
                import tempfile
                
                try:
                    print(f"📥 Downloading video from: {background_video_url}")
                    response = requests.get(background_video_url, stream=True, timeout=300)
                    response.raise_for_status()
                    
                    # Create temporary file
                    temp_dir = Path(tempfile.gettempdir())
                    temp_filename = f"temp_bg_video_{uuid.uuid4().hex}.mp4"
                    temp_path = temp_dir / temp_filename
                    
                    # Download video to temp file
                    with open(temp_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    if temp_path.exists() and temp_path.stat().st_size > 0:
                        background_videos = [str(temp_path)]
                        temp_files_to_cleanup.append(str(temp_path))
                        print(f"✅ Video downloaded successfully: {temp_path}")
                    else:
                        raise Exception("Downloaded file is empty or doesn't exist")
                        
                except Exception as e:
                    print(f"❌ Failed to download video: {e}")
                    raise HTTPException(status_code=400, detail=f"Failed to download background video: {str(e)}")
            else:
                # Try to use the URL directly (for other cases)
                background_videos = [background_video_url]
            
            if not background_videos:
                raise HTTPException(status_code=400, detail="Background video not found")
                
        elif background_type in ['image', 'image_timeline']:
            # Handle image backgrounds using video processing service
            try:
                # Estimate audio duration from text (rough calculation)
                # This will be more accurate when we have the actual audio file
                estimated_duration = len(text.strip()) / 150 * 60  # Assume 150 chars per minute
                estimated_duration = max(5, min(300, estimated_duration))  # Between 5s and 5 minutes
                
                logger.info(f"🖼️ Processing image background, estimated duration: {estimated_duration}s")
                
                # Create background configuration
                if background_type == 'image':
                    background_config = {
                        'type': 'single_image',
                        'image_url': background_image_url
                    }
                else:  # image_timeline
                    background_config = {
                        'type': 'image_timeline',
                        'timeline_segments': background_image_timeline,
                        'video_project_id': str(project.id) if project else None,
                        'use_xfade_transitions': use_xfade_transitions
                    }
                
                # Generate temporary background video from images
                temp_dir = Path(tempfile.gettempdir())
                temp_bg_filename = f"temp_img_bg_{uuid.uuid4().hex}.mp4"
                temp_bg_path = temp_dir / temp_bg_filename
                
                # Use video processing service to create background video
                success = await video_service.process_image_background(
                    background_config=background_config,
                    audio_duration=estimated_duration,
                    temp_background_path=str(temp_bg_path),
                    processing_options=processing_options
                )
                
                if success and temp_bg_path.exists():
                    background_videos = [str(temp_bg_path)]
                    temp_files_to_cleanup.append(str(temp_bg_path))
                    logger.info(f"✅ Generated background video from images: {temp_bg_path}")
                else:
                    raise HTTPException(status_code=500, detail="Failed to generate background video from images")
                    
            except Exception as e:
                logger.error(f"❌ Error processing image background: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to process image background: {str(e)}")
        
        try:
            # Get user ID from authenticated user
            user_id = current_user.get('sub', current_user.get('id', 'unknown-user'))
            
            video_job = await video_service.create_video_processing_job(
                audio_file=audio_file,
                background_video_paths=background_videos,
                caption_file_path=animated_caption_file,
                processing_options=processing_options,
                user_id=user_id,
                project_title=project_title
            )
            
            # Wait for completion (with timeout)
            max_wait_time = 300  # 5 minutes
            wait_interval = 2
            elapsed_time = 0
            
            while elapsed_time < max_wait_time:
                current_job = await video_service.get_job_status(video_job.id)
                
                if current_job and current_job.status == "completed":
                    output_path = Path(current_job.output_file_path)
                    if output_path.exists():
                        file_size = output_path.stat().st_size
                        
                        # Return the video file URL from the videos directory
                        video_url = f"/videos/{output_path.name}"
                        
                        # Prepare response with local URL
                        response = {
                            "video_url": video_url,
                            "audio_file_id": audio_file.id,
                            "duration": audio_file.duration,
                            "file_size": file_size,
                            "job_id": str(current_job.id),
                            "message": "Video generated successfully"
                        }
                        
                        # Add GCS information if available
                        if hasattr(current_job, 'gcs_path') and current_job.gcs_path:
                            response["gcs_info"] = {
                                "gcs_path": current_job.gcs_path,
                                "public_url": current_job.public_url,
                                "signed_url": current_job.signed_url,
                                "cloud_storage": True
                            }
                            # Use GCS signed URL as primary video URL if available
                            if current_job.signed_url:
                                response["video_url"] = current_job.signed_url
                                response["cloud_hosted"] = True
                        else:
                            response["cloud_hosted"] = False
                        
                        return response
                        
                elif current_job and current_job.status == "failed":
                    raise HTTPException(status_code=500, detail=f"Video generation failed: {current_job.error_message}")
                    
                await asyncio.sleep(wait_interval)
                elapsed_time += wait_interval
            
            raise HTTPException(status_code=408, detail="Video generation timeout")
            
        finally:
            # Clean up temporary downloaded files
            for temp_file in temp_files_to_cleanup:
                try:
                    if Path(temp_file).exists():
                        Path(temp_file).unlink()
                        print(f"🗑️ Cleaned up temporary file: {temp_file}")
                except Exception as e:
                    print(f"⚠️ Failed to cleanup temp file {temp_file}: {e}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Fatal error in generate_complete_video for user {user_id}: {type(e).__name__}: {str(e)}")
        logger.error(f"❌ Error details: {repr(e)}")
        import traceback
        logger.error(f"❌ Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error generating video: {str(e)}")

@router.post("/test-processing")
async def test_video_processing(test_data: dict) -> dict:
    """
    Test video processing with existing files
    
    Args:
        test_data: Dictionary with test configuration
    
    Returns:
        Test processing result
    """
    try:
        # This would be used for testing with existing audio and video files
        # Implementation would depend on available test files
        
        return {
            "message": "Test video processing endpoint",
            "available_audio_files": len(list(Path("data/audio").glob("*.mp3"))),
            "available_background_videos": len(list(Path("data/background_videos").glob("*.mp4"))),
            "note": "Use the main /process endpoint with actual file IDs for processing"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in test processing: {str(e)}")

@router.get("/user/projects")
async def get_user_projects(
    limit: Optional[int] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Get all video projects for the current user from Supabase database
    
    Args:
        limit: Maximum number of projects to return
        status: Filter by status (completed, processing, failed)
        current_user: Current authenticated user
        
    Returns:
        List of user's video projects with metadata
    """
    try:
        from repositories.video_project_repository import VideoProjectRepository
        from db.supabase_client import supabase_client
        from services.gcs_service import get_gcs_service
        from datetime import datetime, timedelta, timezone
        
        # Get user ID from authenticated user
        user_id_str = current_user.get('sub', current_user.get('id', 'unknown-user'))
        user_id = UUID(user_id_str)
        logger.info(f"Getting projects for user: {user_id}")
        
        # Get Supabase client
        supabase_client = supabase_client
        if not supabase_client:
            raise HTTPException(status_code=500, detail="Database connection not available")
        
        # Get video project repository
        project_repo = VideoProjectRepository(supabase_client)
        
        # Get projects from database
        projects_db = await project_repo.get_by_user_id(user_id, limit=limit, status_filter=status)
        logger.info(f"Found {len(projects_db)} projects in database for user {user_id}")

        # Reconstruction logic disabled - projects should only be created via normal API flow
        # If no projects are showing up, it's likely a database query issue, not missing records
        
        # Convert database projects to API format
        projects = []
        gcs_service = get_gcs_service()
        
        for project_db in projects_db:
            try:
                # Check if signed URL needs refreshing
                video_url = project_db.gcs_signed_url
                if project_db.gcs_path and gcs_service.is_available():
                    # Check if URL is expired or will expire soon
                    if gcs_service.is_url_expired_or_expiring_soon(project_db.gcs_signed_url_expires_at, buffer_hours=1):
                        
                        try:
                            # Generate new signed URL
                            new_signed_url = await gcs_service.generate_signed_url(project_db.gcs_path, 24)
                            if new_signed_url:
                                expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
                                await project_repo.refresh_signed_url(project_db.id, new_signed_url, expires_at)
                                video_url = new_signed_url
                                logger.info(f"Refreshed signed URL for project {project_db.id}")
                        except Exception as e:
                            logger.warning(f"Error refreshing signed URL for project {project_db.id}: {e}")
                
                draft_data = project_db.draft_data or {}
                timeline_data = draft_data.get("timelineData") or draft_data.get("timeline_data") or {}

                # Create project response
                project = {
                    "id": str(project_db.id),
                    "title": project_db.title,
                    "status": project_db.status,
                    "createdAt": project_db.created_at.isoformat(),
                    "completedAt": project_db.completed_at.isoformat() if project_db.completed_at else None,
                    "duration": project_db.duration,
                    "thumbnail": project_db.thumbnail_url or None,
                    "videoUrl": video_url,
                    "size": project_db.file_size,
                    "creationStep": draft_data.get("creationStep") or draft_data.get("creation_step"),
                    "projectType": timeline_data.get("type"),
                    "progress": 100 if project_db.status == "completed" else 0,
                    "errorMessage": None,
                    "gcsInfo": {
                        "gcsPath": project_db.gcs_path,
                        "publicUrl": None,
                        "signedUrl": video_url,
                        "cloudHosted": bool(project_db.gcs_path)
                    } if project_db.gcs_path else None
                }
                
                projects.append(project)
                
            except Exception as e:
                logger.warning(f"Error processing project {project_db.id}: {str(e)}")
                continue
        
        logger.info(f"Returning {len(projects)} projects for user {user_id}")
        
        return {
            "projects": projects,
            "total": len(projects),
            "userId": user_id_str
        }
        
    except Exception as e:
        logger.error(f"Error getting user projects: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting user projects: {str(e)}")

@router.delete("/user/projects/{project_id}")
async def delete_user_project(
    project_id: str,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Delete a user's video project from Supabase database
    
    Args:
        project_id: ID of the project to delete
        current_user: Current authenticated user
        
    Returns:
        Deletion confirmation
    """
    try:
        from repositories.video_project_repository import VideoProjectRepository
        from db.supabase_client import supabase_client
        from services.gcs_service import get_gcs_service
        from uuid import UUID
        from pathlib import Path
        
        # Get user ID from authenticated user
        user_id_str = current_user.get('sub', current_user.get('id', 'unknown-user'))
        user_id = UUID(user_id_str)
        project_uuid = UUID(project_id)
        
        logger.info(f"Deleting project {project_id} for user {user_id}")
        
        # Get Supabase client
        supabase_client = supabase_client
        if not supabase_client:
            raise HTTPException(status_code=500, detail="Database connection not available")
        
        # Get video project repository
        project_repo = VideoProjectRepository(supabase_client)
        
        # Get the project to verify ownership and get file paths
        projects = await project_repo.get_by_user_id(user_id)
        logger.info(f"Found {len(projects)} projects for user {user_id}")
        logger.info(f"Looking for project_uuid: {project_uuid}")

        project = None
        for p in projects:
            logger.info(f"Checking project: {p.id} (type: {type(p.id)})")
            if p.id == project_uuid:
                project = p
                break

        if not project:
            # Try direct fetch as fallback
            try:
                logger.info(f"Project not found in list, trying direct fetch for {project_uuid}")
                project = await project_repo.get_by_id(project_uuid)

                # Verify ownership
                if project and project.user_id != user_id:
                    logger.warning(f"Project {project_uuid} belongs to different user: {project.user_id} != {user_id}")
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied"
                    )
            except Exception as e:
                logger.error(f"Direct fetch also failed: {str(e)}")

        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        logger.info(f"Found project: {project.title}, GCS path: {project.gcs_path}")
        
        # Delete from GCS if it exists
        if project.gcs_path:
            gcs_service = get_gcs_service()
            if gcs_service.is_available():
                try:
                    await gcs_service.delete_video(project.gcs_path)
                    logger.info(f"Deleted video from GCS: {project.gcs_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete from GCS: {str(e)}")
        
        # Delete local files if they exist
        video_service = VideoProcessingService()
        try:
            # Try to find local files based on project ID
            videos_dir = video_service.videos_dir
            local_files = list(videos_dir.glob(f"*{project_id}*"))
            for local_file in local_files:
                if local_file.exists():
                    local_file.unlink()
                    logger.info(f"Deleted local file: {local_file}")
        except Exception as e:
            logger.warning(f"Failed to delete local files: {str(e)}")
        
        # Delete metadata file
        try:
            metadata_dir = video_service.videos_dir / "metadata"
            metadata_file = metadata_dir / f"{project_id}.json"
            if metadata_file.exists():
                metadata_file.unlink()
                logger.info(f"Deleted metadata file: {metadata_file}")
        except Exception as e:
            logger.warning(f"Failed to delete metadata file: {str(e)}")
        
        # Remove from active jobs if present
        if project_id in video_service.active_jobs:
            del video_service.active_jobs[project_id]
            logger.info(f"Removed project from active jobs: {project_id}")
        
        # Delete from Supabase database
        success = await project_repo.delete(project_uuid)
        if not success:
            logger.warning(f"Failed to delete project from database: {project_id}")
        else:
            logger.info(f"Successfully deleted project from database: {project_id}")
        
        return {
            "message": "Project deleted successfully",
            "projectId": project_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting project: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting project: {str(e)}")

# Debug endpoints removed - using Supabase database for project management

@dashboard_router.get("/stats")
async def get_user_stats(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Get user dashboard statistics
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User statistics including videos created, processing time, storage used, and success rate
    """
    try:
        from repositories.video_project_repository import VideoProjectRepository
        from db.supabase_client import supabase_client
        from uuid import UUID
        from datetime import datetime, timezone
        
        # Get user ID from authenticated user
        user_id_str = current_user.get('sub', current_user.get('id', 'unknown-user'))
        user_id = UUID(user_id_str)
        logger.info(f"Getting stats for user: {user_id}")
        
        # Get Supabase client
        supabase_client = supabase_client
        if not supabase_client:
            # Return default stats if database is unavailable
            return {
                "videosCreated": 0,
                "totalProcessingTime": 0,
                "storageUsed": 0,
                "successRate": 100
            }
        
        # Get video project repository
        project_repo = VideoProjectRepository(supabase_client)
        
        # Get all projects for the user
        all_projects = await project_repo.get_by_user_id(user_id)
        
        # Calculate statistics
        videos_created = len(all_projects)
        completed_projects = [p for p in all_projects if p.status == "completed"]
        
        # Calculate total processing time (sum of all video durations)
        total_processing_time = sum(p.duration or 0 for p in completed_projects)
        
        # Calculate storage used (sum of all file sizes)
        storage_used = sum(p.file_size or 0 for p in completed_projects)
        
        # Calculate success rate
        if videos_created > 0:
            success_rate = round((len(completed_projects) / videos_created) * 100, 1)
        else:
            success_rate = 100.0
        
        stats = {
            "videosCreated": videos_created,
            "totalProcessingTime": int(total_processing_time),
            "storageUsed": int(storage_used),
            "successRate": success_rate
        }
        
        logger.info(f"User {user_id} stats: {stats}")
        return stats
        
    except Exception as e:
        logger.error(f"Error getting user stats: {str(e)}")
        # Return default stats on error
        return {
            "videosCreated": 0,
            "totalProcessingTime": 0,
            "storageUsed": 0,
            "successRate": 100
        }

# YouTube Metadata Management Endpoints

@router.post("/projects/{project_id}/youtube-metadata", response_model=YouTubeShortsContentResponse)
async def create_or_update_youtube_metadata(
    project_id: str,
    youtube_data: YouTubeShortsContentCreate,
    current_user: dict = Depends(get_current_user)
) -> YouTubeShortsContentResponse:
    """
    Create or update YouTube Shorts metadata for a video project

    Args:
        project_id: ID of the video project
        youtube_data: YouTube metadata (title, description, tags)
        current_user: Current authenticated user

    Returns:
        Created or updated YouTube metadata
    """
    try:
        from repositories.youtube_content_repository import YouTubeContentRepository
        from repositories.video_project_repository import VideoProjectRepository
        from db.supabase_client import supabase_client
        from uuid import UUID

        # Get user ID from authenticated user
        user_id = current_user.get('sub', current_user.get('id', 'unknown-user'))
        project_uuid = UUID(project_id)

        logger.info(f"Creating/updating YouTube metadata for project {project_id} by user {user_id}")

        # Verify project ownership
        project_repo = VideoProjectRepository(supabase_client)
        user_projects = await project_repo.get_by_user_id(UUID(user_id))

        project_exists = any(p.id == project_uuid for p in user_projects)
        if not project_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or access denied"
            )

        # Create YouTube content repository
        youtube_repo = YouTubeContentRepository(supabase_client)

        # Override project_id to ensure it matches the URL parameter
        youtube_data.project_id = project_uuid

        # Upsert YouTube metadata
        result = await youtube_repo.upsert(youtube_data)

        # Convert to response format
        response = YouTubeShortsContentResponse(
            id=result.id,
            project_id=result.project_id,
            project_title=None,  # Will be populated by frontend if needed
            title=result.title,
            description=result.description,
            tags=result.tags,
            tags_text=result.tags_text,
            created_at=result.created_at,
            updated_at=result.updated_at
        )

        logger.info(f"✅ YouTube metadata saved for project {project_id}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error saving YouTube metadata for project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save YouTube metadata: {str(e)}")

@router.get("/projects/{project_id}/youtube-metadata", response_model=YouTubeShortsContentResponse)
async def get_youtube_metadata(
    project_id: str,
    current_user: dict = Depends(get_current_user)
) -> YouTubeShortsContentResponse:
    """
    Get YouTube Shorts metadata for a video project

    Args:
        project_id: ID of the video project
        current_user: Current authenticated user

    Returns:
        YouTube metadata for the project
    """
    try:
        from repositories.youtube_content_repository import YouTubeContentRepository
        from repositories.video_project_repository import VideoProjectRepository
        from db.supabase_client import supabase_client
        from uuid import UUID

        # Get user ID from authenticated user
        user_id = current_user.get('sub', current_user.get('id', 'unknown-user'))
        project_uuid = UUID(project_id)

        logger.info(f"Fetching YouTube metadata for project {project_id} by user {user_id}")

        # Verify project ownership
        project_repo = VideoProjectRepository(supabase_client)
        user_projects = await project_repo.get_by_user_id(UUID(user_id))

        project_exists = any(p.id == project_uuid for p in user_projects)
        if not project_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or access denied"
            )

        # Get YouTube metadata
        youtube_repo = YouTubeContentRepository(supabase_client)
        youtube_content = await youtube_repo.get_by_project_id(project_uuid)

        if not youtube_content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="YouTube metadata not found for this project"
            )

        # Convert to response format
        response = YouTubeShortsContentResponse(
            id=youtube_content.id,
            project_id=youtube_content.project_id,
            project_title=None,  # Will be populated by frontend if needed
            title=youtube_content.title,
            description=youtube_content.description,
            tags=youtube_content.tags,
            tags_text=youtube_content.tags_text,
            created_at=youtube_content.created_at,
            updated_at=youtube_content.updated_at
        )

        logger.info(f"✅ Found YouTube metadata for project {project_id}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching YouTube metadata for project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch YouTube metadata: {str(e)}")

@router.put("/projects/{project_id}/youtube-metadata", response_model=YouTubeShortsContentResponse)
async def update_youtube_metadata(
    project_id: str,
    update_data: YouTubeShortsContentUpdate,
    current_user: dict = Depends(get_current_user)
) -> YouTubeShortsContentResponse:
    """
    Update YouTube Shorts metadata for a video project

    Args:
        project_id: ID of the video project
        update_data: YouTube metadata updates
        current_user: Current authenticated user

    Returns:
        Updated YouTube metadata
    """
    try:
        from repositories.youtube_content_repository import YouTubeContentRepository
        from repositories.video_project_repository import VideoProjectRepository
        from db.supabase_client import supabase_client
        from uuid import UUID

        # Get user ID from authenticated user
        user_id = current_user.get('sub', current_user.get('id', 'unknown-user'))
        project_uuid = UUID(project_id)

        logger.info(f"Updating YouTube metadata for project {project_id} by user {user_id}")

        # Verify project ownership
        project_repo = VideoProjectRepository(supabase_client)
        user_projects = await project_repo.get_by_user_id(UUID(user_id))

        project_exists = any(p.id == project_uuid for p in user_projects)
        if not project_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or access denied"
            )

        # Update YouTube metadata
        youtube_repo = YouTubeContentRepository(supabase_client)
        result = await youtube_repo.update(project_uuid, update_data)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="YouTube metadata not found for this project"
            )

        # Convert to response format
        response = YouTubeShortsContentResponse(
            id=result.id,
            project_id=result.project_id,
            project_title=None,  # Will be populated by frontend if needed
            title=result.title,
            description=result.description,
            tags=result.tags,
            tags_text=result.tags_text,
            created_at=result.created_at,
            updated_at=result.updated_at
        )

        logger.info(f"✅ YouTube metadata updated for project {project_id}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error updating YouTube metadata for project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update YouTube metadata: {str(e)}")

@router.delete("/projects/{project_id}/youtube-metadata")
async def delete_youtube_metadata(
    project_id: str,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Delete YouTube Shorts metadata for a video project

    Args:
        project_id: ID of the video project
        current_user: Current authenticated user

    Returns:
        Deletion confirmation
    """
    try:
        from repositories.youtube_content_repository import YouTubeContentRepository
        from repositories.video_project_repository import VideoProjectRepository
        from db.supabase_client import supabase_client
        from uuid import UUID

        # Get user ID from authenticated user
        user_id = current_user.get('sub', current_user.get('id', 'unknown-user'))
        project_uuid = UUID(project_id)

        logger.info(f"Deleting YouTube metadata for project {project_id} by user {user_id}")

        # Verify project ownership
        project_repo = VideoProjectRepository(supabase_client)
        user_projects = await project_repo.get_by_user_id(UUID(user_id))

        project_exists = any(p.id == project_uuid for p in user_projects)
        if not project_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or access denied"
            )

        # Delete YouTube metadata
        youtube_repo = YouTubeContentRepository(supabase_client)
        success = await youtube_repo.delete_by_project_id(project_uuid)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="YouTube metadata not found for this project"
            )

        logger.info(f"✅ YouTube metadata deleted for project {project_id}")
        return {
            "message": "YouTube metadata deleted successfully",
            "project_id": project_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error deleting YouTube metadata for project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete YouTube metadata: {str(e)}")

@router.get("/user/youtube-metadata", response_model=List[YouTubeShortsContentResponse])
async def get_user_youtube_metadata(
    limit: Optional[int] = 50,
    current_user: dict = Depends(get_current_user)
) -> List[YouTubeShortsContentResponse]:
    """
    Get all YouTube Shorts metadata for the current user

    Args:
        limit: Maximum number of records to return
        current_user: Current authenticated user

    Returns:
        List of user's YouTube metadata
    """
    try:
        from repositories.youtube_content_repository import YouTubeContentRepository
        from db.supabase_client import supabase_client
        from uuid import UUID

        # Get user ID from authenticated user
        user_id_str = current_user.get('sub', current_user.get('id', 'unknown-user'))
        user_id = UUID(user_id_str)

        logger.info(f"Fetching YouTube metadata for user {user_id}")

        # Get YouTube metadata for user
        youtube_repo = YouTubeContentRepository(supabase_client)
        youtube_content_list = await youtube_repo.get_by_user_id(user_id, limit=limit or 50)

        logger.info(f"✅ Found {len(youtube_content_list)} YouTube metadata records for user {user_id}")
        return youtube_content_list

    except Exception as e:
        logger.error(f"❌ Error fetching user YouTube metadata: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch YouTube metadata: {str(e)}")

@router.post("/webhook/cloud-processing")
async def handle_cloud_processing_webhook(request: dict) -> dict:
    """
    Webhook endpoint to receive completion notifications from cloud-video-processor
    
    This endpoint is called by the cloud-video-processor when a video processing job
    completes (either successfully or with failure). It updates the VideoProject 
    status in Supabase and prepares the response for frontend consumption.
    
    Args:
        request: Webhook payload from cloud-video-processor
        
    Returns:
        Acknowledgment response
    """
    try:
        from repositories.video_project_repository import VideoProjectRepository
        from db.supabase_client import supabase_client
        from services.cloud_video_service import cloud_video_service
        from models.video_project_models import VideoProjectUpdate
        from datetime import datetime, timedelta, timezone
        from pathlib import Path
        import re
        
        logger.info("🔔 Received webhook from cloud-video-processor")
        logger.info(f"Webhook payload: {request}")
        
        # Extract key information from webhook
        job_id = request.get('job_id')
        status = request.get('status', 'unknown')
        result = request.get('result', {}) or request.get('data', {})  # Handle both formats
        
        if not job_id:
            logger.error("❌ Webhook missing job_id")
            return {"status": "error", "message": "Missing job_id"}
        
        # Find the project in database by project ID (job_id is the project ID)
        try:
            video_project_repo = VideoProjectRepository(supabase_client)
            
            # Search for project with this ID (job_id is project ID)
            response = supabase_client.supabase.table("video_projects").select("*").eq("id", job_id).execute()
            
            if not response.data:
                logger.warning(f"⚠️ No project found for ID: {job_id}")
                return {"status": "error", "message": f"Project not found for job_id: {job_id}"}
            
            project_data = response.data[0]
            project_id = project_data['id']
            
            logger.info(f"📝 Found project {project_id} for cloud job {job_id}")
            
            # Prepare update data based on status
            update_data = {
                "webhook_received_at": datetime.now(timezone.utc).isoformat(),
                "processing_method": "cloud"
            }
            
            if status == "completed":
                # Processing successful
                output_files = result.get('output_files', [])
                processing_time = result.get('total_time_seconds', 0)
                
                # Find main video file - check multiple possible locations
                video_url = None
                
                # Method 1: Check step2_video_processing.result_url (preferred)
                if 'step2_video_processing' in result and 'result_url' in result['step2_video_processing']:
                    video_url = result['step2_video_processing']['result_url']
                    logger.info(f"📹 Found video URL in step2_video_processing: {video_url}")
                
                # Method 2: Look through output_files for video files
                if not video_url:
                    for file_url in output_files:
                        if any(ext in file_url.lower() for ext in ['.mp4', '.mov', '.avi']):
                            video_url = file_url
                            logger.info(f"📹 Found video URL in output_files: {video_url}")
                            break
                
                # Method 3: Fallback to last file in output_files
                if not video_url and output_files:
                    video_url = output_files[-1]
                    logger.info(f"📹 Using last file as video URL: {video_url}")
                
                # Extract file size from webhook and use audio duration from project
                file_size = 0
                video_duration = 0.0

                try:
                    # Get file size from webhook result
                    file_size = result.get('file_size', 0)

                    # Use audio duration from the project (video duration = audio duration)
                    if project_data and project_data.get('duration'):
                        video_duration = float(project_data['duration'])
                        logger.info(f"⏱️ Using audio duration from project: {video_duration}s (video will match audio)")
                    else:
                        logger.warning("⚠️ No audio duration found in project data")

                except Exception as e:
                    logger.warning(f"⚠️ Error extracting data from webhook: {str(e)}")
                    file_size = 0
                    video_duration = 0.0
                
                # Generate proper signed URL instead of using raw gs:// URL
                signed_url = video_url  # Default fallback
                signed_url_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)  # 1 hour from now
                gcs_blob_path = None  # For storing just the blob path in gcs_path
                
                # Try to generate a proper signed URL if we have GCS service available
                try:
                    from services.gcs_service import get_gcs_service
                    gcs_service = get_gcs_service()
                    
                    logger.info(f"Checking output file, file_url: {video_url}, is_video: true")
                    
                    if gcs_service.is_available() and video_url:
                        # Extract GCS blob path from video_url
                        if video_url.startswith('gs://'):
                            # Convert gs://bucket/path to just the blob path (like login flow)
                            gcs_full_path = video_url.replace('gs://', '')
                            if '/' in gcs_full_path:
                                bucket_name, blob_path = gcs_full_path.split('/', 1)
                                gcs_blob_path = blob_path  # Store just the blob path for gcs_path field
                                
                                logger.info(f"Generating signed URL, blob_path: {blob_path}, bucket: {bucket_name}")
                                
                                # Generate signed URL using GCS service (handles both service account keys and Application Default Credentials)
                                logger.info(f"🚀 WEBHOOK FIX v3.0 - Attempting signed URL generation for blob: {blob_path}")
                                
                                generated_signed_url = await gcs_service.generate_signed_url(blob_path, 24)
                                if generated_signed_url:
                                    signed_url = generated_signed_url
                                    signed_url_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
                                    
                                    # Check if it's a proper signed URL or public URL
                                    has_signature = 'Signature=' in signed_url or 'signature=' in signed_url
                                    logger.info(f"✅ Generated URL successfully: {generated_signed_url[:80]}...")
                                    logger.info(f"🔍 URL type: {'signed' if has_signature else 'public'}")
                                    
                                else:
                                    logger.error(f"❌ Failed to generate any accessible URL for blob: {blob_path}")
                                    logger.error(f"❌ SIGNED URL GENERATION FAILED - storing gs:// URL in database!, final_signed_url: {signed_url}, gcs_service_available: true, video_url: {video_url}")
                            else:
                                logger.warning(f"⚠️ Invalid GCS path format: {video_url}")
                        else:
                            logger.info(f"📝 Video URL is not a GCS URL, using as-is: {video_url}")
                    else:
                        logger.error(f"❌ GCS service not available or no video URL")
                        logger.error(f"❌ SIGNED URL GENERATION FAILED - storing gs:// URL in database!, final_signed_url: {signed_url}, gcs_service_available: false, video_url: {video_url}")
                            
                except Exception as e:
                    logger.error(f"❌ Error generating signed URL in webhook: {str(e)}")
                    import traceback
                    logger.error(f"❌ Full traceback: {traceback.format_exc()}")
                    logger.error(f"❌ SIGNED URL GENERATION FAILED - storing gs:// URL in database!, final_signed_url: {signed_url}, gcs_service_available: true, video_url: {video_url}")
                    # Continue with the original URL as fallback
                
                if (signed_url or "").startswith(('gs://', 'https://storage.googleapis.com/')) or (video_url or "").startswith(('gs://', 'https://storage.googleapis.com/')):
                    error_message = "Completed job returned an external Google Cloud Storage URL, which is unsupported in local mode"
                    update_data.update({
                        "status": "failed",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "processing_options": {
                            "cloud_processing": True,
                            "error": error_message,
                            "failed_at": datetime.now(timezone.utc).isoformat(),
                            "output_files": output_files,
                        }
                    })
                    logger.error(f"❌ Job {job_id} cannot complete in local mode: {error_message}")
                else:
                    update_data.update({
                        "status": "completed",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "duration": video_duration,  # Store the actual video duration
                        "gcs_path": gcs_blob_path or video_url,  # Compatibility field; stores local media path/URL in local mode
                        "gcs_signed_url": signed_url,  # Local mode URL served from /media
                        "gcs_signed_url_expires_at": signed_url_expires_at.isoformat(),
                        "file_size": file_size,
                        "processing_options": {
                            "cloud_processing": True,
                            "processing_time_seconds": processing_time,
                            "output_files": output_files,
                            "signed_url_generated": signed_url != video_url,  # Track if we generated a new URL
                            "gcs_blob_path_extracted": gcs_blob_path  # Debug info
                        }
                    })
                    
                    logger.info(f"✅ Job {job_id} completed successfully")
                    logger.info(f"📹 Video URL: {video_url}")
                    logger.info(f"⏱️ Video duration: {video_duration}s")
                    logger.info(f"📦 File size: {file_size} bytes")
                
            elif status == "failed":
                # Processing failed
                error_message = result.get('error', 'Unknown error occurred during cloud processing')
                
                update_data.update({
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "processing_options": {
                        "cloud_processing": True,
                        "error": error_message,
                        "failed_at": datetime.now(timezone.utc).isoformat()
                    }
                })
                
                logger.error(f"❌ Job {job_id} failed: {error_message}")
                
            else:
                logger.warning(f"⚠️ Unknown status received: {status}")
                update_data.update({
                    "status": status,
                    "processing_options": {
                        "cloud_processing": True,
                        "unknown_status": True,
                        "webhook_data": result
                    }
                })
            
            # Add detailed logging for Supabase update
            if update_data.get("status") == "completed" and video_url:
                logger.info(f"Local project update data preparation, project_id: {project_id}, gcs_path: {gcs_blob_path or 'unknown'}, signed_url_length: {len(signed_url) if signed_url else 0}, signed_url_has_signature: {'signature' in (signed_url or '')}, signed_url_is_gs: {(signed_url or '').startswith('gs://')}")
                logger.info(f"Updating video project, project_id: {project_id}, update_fields: {list(update_data.keys())}")

            # Update project in database
            update_response = supabase_client.supabase.table("video_projects").update(update_data).eq("id", project_id).execute()
            
            if update_response.data:
                logger.info(f"Successfully updated video project, project_id: {project_id}, updated_fields: {list(update_data.keys())}")
                
                if update_data.get("status") == "completed" and video_url:
                    logger.info(f"Successfully updated local project with completion data, job_id: {job_id}, video_url: {video_url[:100]}..., file_size: {file_size}")

                    # Update video_project_languages table with video_file_id
                    try:
                        if gcs_blob_path:
                            # Try to get language_code from processing_options
                            language_code = project_data.get('processing_options', {}).get('language_code')

                            if language_code:
                                # Update specific language record
                                logger.info(f"🌐 Updating language {language_code} with video_file_id: {gcs_blob_path}")
                                lang_update_response = supabase_client.supabase.table("video_project_languages")\
                                    .update({"video_file_id": gcs_blob_path})\
                                    .eq("project_id", project_id)\
                                    .eq("language_code", language_code)\
                                    .execute()

                                if lang_update_response.data:
                                    logger.info(f"✅ Updated language {language_code} with video_file_id for project {project_id}")
                                else:
                                    logger.warning(f"⚠️ No language record found for {language_code} in project {project_id}")
                            else:
                                # No language_code specified - update PRIMARY language record
                                logger.info(f"🌐 No language_code in processing_options, updating PRIMARY language with video_file_id: {gcs_blob_path}")
                                lang_update_response = supabase_client.supabase.table("video_project_languages")\
                                    .update({"video_file_id": gcs_blob_path})\
                                    .eq("project_id", project_id)\
                                    .eq("is_primary", True)\
                                    .execute()

                                if lang_update_response.data:
                                    logger.info(f"✅ Updated PRIMARY language with video_file_id for project {project_id}")
                                else:
                                    logger.warning(f"⚠️ No primary language record found for project {project_id}")
                        else:
                            logger.warning(f"⚠️ No gcs_blob_path available, cannot update language table")
                    except Exception as lang_error:
                        logger.error(f"❌ Error updating language table: {str(lang_error)}")
                        # Don't fail the webhook, just log the error

                # Optional: Trigger any additional notifications here
                # (e.g., WebSocket notifications to frontend, email notifications, etc.)

                return {
                    "status": "success",
                    "message": f"Webhook processed for job {job_id}",
                    "project_id": project_id,
                    "updated_status": status
                }
            else:
                logger.error(f"❌ Failed to update project {project_id} in database")
                return {"status": "error", "message": "Database update failed"}
                
        except Exception as db_error:
            logger.error(f"❌ Database error processing webhook: {str(db_error)}")
            return {"status": "error", "message": f"Database error: {str(db_error)}"}
        
    except Exception as e:
        logger.error(f"❌ Error processing cloud webhook: {str(e)}")
        return {"status": "error", "message": f"Webhook processing failed: {str(e)}"}

# Regenerate Audio Endpoint
class RegenerateAudioRequest(BaseModel):
    text: str
    voice_id: str
    tts_provider: Optional[str] = "minimax"
    user_input_text: Optional[str] = None  # User's original input text from editor
    audio_speed: Optional[float] = 1.0  # Audio speed (0.5x to 2.0x)
    language_code: Optional[str] = None  # Language code for multi-language support
    voice_system_prompt: Optional[str] = None  # Custom voice system prompt for TTS


class CaptionTextUpdateRequest(BaseModel):
    caption_text: str
    language_code: Optional[str] = "en"


def _tokenize_caption_text(text: str) -> List[str]:
    """Split edited caption text into words while preserving punctuation in tokens."""
    return [token for token in text.split() if token]


def _build_updated_words(
    existing_words: List[Dict[str, Any]],
    edited_text: str
) -> List[Dict[str, Any]]:
    """
    Build updated words list from edited caption text.
    Reuse original timings when word counts match; otherwise distribute timings evenly.
    """
    tokens = _tokenize_caption_text(edited_text)
    if not tokens:
        return []

    if existing_words and len(existing_words) == len(tokens):
        updated_words: List[Dict[str, Any]] = []
        for existing_word, token in zip(existing_words, tokens):
            updated_word = dict(existing_word)
            updated_word["text"] = token
            updated_words.append(updated_word)
        return updated_words

    # Timing fallback for count mismatch
    if existing_words:
        total_start = float(existing_words[0].get("start", 0) or 0)
        total_end = float(existing_words[-1].get("end", total_start) or total_start)
        if total_end <= total_start:
            total_end = total_start + max(0.5, len(tokens) * 0.2)
    else:
        total_start = 0.0
        total_end = max(0.5, len(tokens) * 0.2)

    total_duration = max(0.01, total_end - total_start)
    step = total_duration / len(tokens)

    updated_words = []
    for index, token in enumerate(tokens):
        start = total_start + (step * index)
        end = total_start + (step * (index + 1))
        updated_words.append({
            "text": token,
            "start": round(start, 3),
            "end": round(end, 3),
            "confidence": 1.0
        })

    return updated_words


def _load_transcript_json_from_gcs(
    bucket,
    user_id: str,
    project_id: str,
    language_code: Optional[str] = "en"
) -> Tuple[Dict[str, Any], str]:
    """
    Load transcript JSON from preferred language-specific path, then fallback path.
    Returns (json_data, filename_used).
    """
    preferred_filenames = []
    if language_code:
        preferred_filenames.append(f"raw_transcript_data_{language_code}.txt")
    preferred_filenames.append("raw_transcript_data.txt")

    for filename in preferred_filenames:
        blob_path = f"output/{user_id}/{project_id}/{filename}"
        blob = bucket.blob(blob_path)
        if blob.exists():
            content = blob.download_as_text(encoding="utf-8")
            return json.loads(content), filename

    raise HTTPException(
        status_code=404,
        detail="Transcript file not found. Generate audio/transcription first."
    )


@router.get("/projects/{project_id}/caption-text")
async def get_project_caption_text(
    project_id: str,
    language_code: Optional[str] = "en",
    current_user: dict = Depends(get_current_user)
):
    """Get editable caption text from project transcript data in GCS."""
    try:
        from db.supabase_client import SupabaseClient
        from services.gcs_service import get_gcs_service

        user_id = current_user.get('sub', current_user.get('id', current_user.get('user_id')))
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")

        supabase = SupabaseClient().supabase
        project_res = supabase.table("video_projects").select("id,user_id").eq("id", project_id).execute()
        if not project_res.data:
            raise HTTPException(status_code=404, detail="Project not found")

        project_owner = str(project_res.data[0].get("user_id"))
        if project_owner != str(user_id):
            raise HTTPException(status_code=403, detail="Access denied")

        gcs_service = get_gcs_service()
        if not gcs_service.bucket:
            raise HTTPException(status_code=500, detail="GCS service unavailable")

        transcript_data, source_filename = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _load_transcript_json_from_gcs(
                gcs_service.bucket,
                str(user_id),
                project_id,
                language_code
            )
        )

        caption_text = transcript_data.get("text") or transcript_data.get("user_input_text") or ""
        words = transcript_data.get("words", []) or []
        word_timestamps = [
            {
                "text": str(word.get("text", "")),
                "start": float(word.get("start", 0) or 0),
                "end": float(word.get("end", 0) or 0)
            }
            for word in words
        ]

        return {
            "project_id": project_id,
            "language_code": language_code,
            "source_file": source_filename,
            "caption_text": caption_text,
            "word_count": len(words),
            "word_timestamps": word_timestamps
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to load caption text for project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to load caption text: {str(e)}")


@router.put("/projects/{project_id}/caption-text")
async def update_project_caption_text(
    project_id: str,
    request: CaptionTextUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Update caption text in transcript JSON stored in GCS.
    This becomes the source for subtitle generation in cloud processing.
    """
    try:
        from db.supabase_client import SupabaseClient
        from services.gcs_service import get_gcs_service

        user_id = current_user.get('sub', current_user.get('id', current_user.get('user_id')))
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")

        if not request.caption_text.strip():
            raise HTTPException(status_code=400, detail="Caption text cannot be empty")

        supabase = SupabaseClient().supabase
        project_res = supabase.table("video_projects").select("id,user_id").eq("id", project_id).execute()
        if not project_res.data:
            raise HTTPException(status_code=404, detail="Project not found")

        project_owner = str(project_res.data[0].get("user_id"))
        if project_owner != str(user_id):
            raise HTTPException(status_code=403, detail="Access denied")

        gcs_service = get_gcs_service()
        if not gcs_service.bucket:
            raise HTTPException(status_code=500, detail="GCS service unavailable")

        # Load transcript JSON from either language-specific or fallback path
        loaded = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _load_transcript_json_from_gcs(
                gcs_service.bucket,
                str(user_id),
                project_id,
                request.language_code
            )
        )
        transcript_data, source_filename = loaded

        existing_words = transcript_data.get("words", []) or []
        normalized_text = " ".join(request.caption_text.strip().split())
        updated_words = _build_updated_words(existing_words, normalized_text)

        transcript_data["text"] = normalized_text
        transcript_data["user_input_text"] = normalized_text
        transcript_data["words"] = updated_words
        transcript_data["caption_edited"] = True
        transcript_data["caption_edited_at"] = datetime.now().isoformat()

        payload = json.dumps(transcript_data, ensure_ascii=False, indent=2)

        filenames_to_update = set([source_filename, "raw_transcript_data.txt"])
        if request.language_code:
            filenames_to_update.add(f"raw_transcript_data_{request.language_code}.txt")

        for filename in filenames_to_update:
            blob_path = f"output/{user_id}/{project_id}/{filename}"
            blob = gcs_service.bucket.blob(blob_path)
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda b=blob: b.upload_from_string(payload.encode("utf-8"), content_type="application/json; charset=utf-8")
            )

        logger.info(
            f"✅ Updated caption text for project {project_id}: "
            f"old_words={len(existing_words)} new_words={len(updated_words)} files={sorted(filenames_to_update)}"
        )

        return {
            "success": True,
            "project_id": project_id,
            "language_code": request.language_code,
            "word_count": len(updated_words),
            "updated_files": sorted(filenames_to_update),
            "word_timestamps": [
                {
                    "text": str(word.get("text", "")),
                    "start": float(word.get("start", 0) or 0),
                    "end": float(word.get("end", 0) or 0)
                }
                for word in updated_words
            ],
            "message": "Caption text updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to update caption text for project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update caption text: {str(e)}")

@router.post("/projects/{project_id}/regenerate-audio")
async def regenerate_audio_for_project(
    project_id: str,
    request: RegenerateAudioRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Regenerate audio for an existing project with optional speed control
    
    This endpoint now returns immediately and processes audio generation in the background
    to prevent 504 timeout errors.

    Args:
        project_id: ID of the video project
        request: Audio regeneration request with text, voice, and optional speed
        current_user: Current authenticated user data

    Returns:
        Job status with job_id for tracking progress
    """
    try:
        logger.info(f"🔄 Starting audio regeneration for project {project_id}")
        logger.info(f"📝 Request: text_length={len(request.text)}, voice_id={request.voice_id}, audio_speed={request.audio_speed}x")

        user_id = current_user.get('id') or current_user.get('user_id')
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")

        # Validate input
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="Text cannot be empty")

        if len(request.text) > 1000000:
            raise HTTPException(status_code=400, detail="Text too long (max 1,000,000 characters)")

        # Update project status to "processing" immediately
        from repositories.video_project_repository import VideoProjectRepository
        from db.supabase_client import supabase_client
        from models.video_project_models import VideoProjectUpdate
        from uuid import UUID
        import asyncio

        video_project_repo = VideoProjectRepository(supabase_client)

        # Set project to processing status
        update_data = VideoProjectUpdate(status="processing")
        await video_project_repo.update(UUID(project_id), update_data)

        # Generate job ID for tracking
        import time
        job_id = f"audio_regen_{project_id}_{int(time.time())}"

        # Start background task for audio generation
        asyncio.create_task(
            _regenerate_audio_background_task(
                project_id=project_id,
                request=request,
                user_id=user_id,
                job_id=job_id
            )
        )

        logger.info(f"✅ Audio regeneration job {job_id} started for project {project_id}")

        # Return immediately with job status
        return {
            "success": True,
            "message": "Audio regeneration started",
            "job_id": job_id,
            "project_id": project_id,
            "status": "processing",
            "estimated_completion": "2-3 minutes"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error starting audio regeneration for project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start audio regeneration: {str(e)}")


async def _regenerate_audio_background_task(
    project_id: str,
    request: RegenerateAudioRequest,
    user_id: str,
    job_id: str
):
    """
    Background task for audio regeneration to prevent timeout issues

    Args:
        project_id: Video project ID
        request: Audio regeneration request
        user_id: User ID
        job_id: Job tracking ID
        job_id: Job tracking ID
    """
    try:
        logger.info(f"🎵 Background audio generation started for project {project_id} (job: {job_id})")

        from uuid import UUID
        from services.tts_service import TTSService
        from services.tts_factory import get_tts_service
        from models.story_models import VoiceSettings
        from repositories.video_project_repository import VideoProjectRepository
        from db.supabase_client import supabase_client

        # Get the appropriate TTS service
        if request.tts_provider not in ("minimax", "google"):
            raise HTTPException(status_code=400, detail="Unsupported TTS provider. Use 'minimax' or 'google'.")

        tts_service = get_tts_service(request.tts_provider)

        # Set up voice settings
        voice_settings = VoiceSettings()
        voice_settings.voice_id = request.voice_id

        # For multi-language support: Check if language already has an audio_file_id
        # If yes, reuse it. If no, generate a new UUID for this language.
        language_audio_id = None
        if request.language_code:
            try:
                from db.supabase_client import SupabaseClient
                supabase_client_instance = SupabaseClient()
                supabase = supabase_client_instance.supabase

                # Check if this language already has an audio_file_id
                lang_result = supabase.table("video_project_languages")\
                    .select("audio_file_id")\
                    .eq("project_id", project_id)\
                    .eq("language_code", request.language_code)\
                    .execute()

                if lang_result.data and lang_result.data[0].get("audio_file_id"):
                    language_audio_id = lang_result.data[0]["audio_file_id"]
                    logger.info(f"🌐 Reusing existing audio ID for language {request.language_code}: {language_audio_id}")
                else:
                    # Generate new UUID for this language
                    from uuid import uuid4
                    language_audio_id = str(uuid4())
                    logger.info(f"🌐 Generated new audio ID for language {request.language_code}: {language_audio_id}")
            except Exception as e:
                logger.error(f"❌ Error checking language audio ID: {e}")
                # Fall back to project_id
                language_audio_id = project_id
        else:
            # No language code provided, use project_id (primary language)
            language_audio_id = project_id

        # Generate new audio with language-specific audio_id
        logger.info(f"🎵 Generating new audio with {request.tts_provider} TTS (audio_id: {language_audio_id})")
        # Track if ElevenLabs provided timestamps (skip AssemblyAI if so)
        elevenlabs_has_timestamps = False

        if request.tts_provider == "elevenlabs":
            # ElevenLabs uses convert_with_timestamps which returns timestamps directly
            # This saves API cost and time by skipping AssemblyAI transcription
            logger.info("🎤 Using ElevenLabs TTS with timestamps...")
            result = await tts_service.text_to_speech_auto_and_wait(
                text=request.text,
                voice_settings=voice_settings,
                audio_settings=None,
                user_id=user_id,
                audio_speed=request.audio_speed,
                audio_id=language_audio_id,
                voice_system_prompt=request.voice_system_prompt,
                project_id=project_id,  # Pass project_id for timestamp storage
                language_code=request.language_code  # Pass language code for filename
            )
            # ElevenLabs returns dict with audio_file, word_segments, has_timestamps
            audio_file = result['audio_file']
            elevenlabs_has_timestamps = result.get('has_timestamps', False)
            if elevenlabs_has_timestamps:
                logger.info(f"✅ ElevenLabs provided {len(result.get('word_segments', []))} word timestamps - skipping AssemblyAI")
            else:
                logger.warning("⚠️ ElevenLabs did not return timestamps - AssemblyAI will be used for transcription")

        elif request.tts_provider == "deepgram":
            audio_file = await tts_service.text_to_speech_auto(
                text=request.text,
                voice_settings=voice_settings,
                audio_settings=None,
                user_id=user_id,
                audio_speed=request.audio_speed,
                audio_id=language_audio_id,  # Use language-specific audio_id
                voice_system_prompt=request.voice_system_prompt  # Pass custom voice prompt
            )

            # For Deepgram, if audio_speed is provided and not 1.0, adjust the audio speed
            # Deepgram API doesn't support speed parameter, so we adjust post-generation
            if request.audio_speed and request.audio_speed != 1.0:
                logger.info(f"🔄 Adjusting Deepgram audio speed to {request.audio_speed}x...")
                try:
                    # Calculate target duration based on speed
                    # If speed is 1.5x, target duration = current_duration / 1.5
                    current_duration = audio_file.duration
                    target_duration = current_duration / request.audio_speed

                    logger.info(f"📊 Current duration: {current_duration:.2f}s, Target duration: {target_duration:.2f}s (speed: {request.audio_speed}x)")

                    # Use the TTS service to adjust the audio duration
                    adjusted_audio_file = await tts_service.adjust_audio_file_duration(
                        audio_file=audio_file,
                        target_duration=target_duration
                    )
                    audio_file = adjusted_audio_file
                    logger.info(f"✅ Deepgram audio speed adjusted successfully to {request.audio_speed}x (duration: {audio_file.duration:.2f}s)")
                except Exception as speed_error:
                    logger.error(f"❌ Failed to adjust Deepgram audio speed: {str(speed_error)}")
                    # Continue with original audio file instead of failing completely
                    logger.warning("⚠️ Continuing with original audio (1.0x speed)")
        else:
            # Minimax uses text_to_speech_auto_and_wait with native speed support
            audio_file = await tts_service.text_to_speech_auto_and_wait(
                text=request.text,
                voice_settings=voice_settings,
                audio_settings=None,
                user_id=user_id,
                audio_speed=request.audio_speed,
                audio_id=language_audio_id,  # Use language-specific audio_id
                voice_system_prompt=request.voice_system_prompt  # Pass custom voice prompt
            )

        # Update the project with new audio
        logger.info(f"🔄 Updating project {project_id} with new audio file")
        video_project_repo = VideoProjectRepository(supabase_client)

        # Get existing project
        existing_project = await video_project_repo.get_by_id(UUID(project_id))
        if not existing_project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Update project with new audio information (but keep status as processing for now)
        from models.video_project_models import VideoProjectUpdate

        update_data = VideoProjectUpdate(
            audio_file_id=str(audio_file.id),
            duration=audio_file.duration or 0.0,
            status="processing"  # Keep as processing until transcription starts
        )

        updated_project = await video_project_repo.update(UUID(project_id), update_data)

        if not updated_project:
            raise HTTPException(status_code=500, detail="Failed to update project with new audio")

        logger.info(f"✅ Audio file generated for project {project_id}")
        logger.info(f"📊 Audio file ID: {updated_project.audio_file_id}")
        logger.info(f"📊 Duration: {updated_project.duration}")

        # Update language-specific audio_file_id
        # If language_code is provided, update that language's record
        # Otherwise, update the primary language record (for backward compatibility)
        try:
            from db.supabase_client import SupabaseClient
            supabase_client_instance = SupabaseClient()
            supabase = supabase_client_instance.supabase

            if request.language_code:
                logger.info(f"🌐 Updating language record for {request.language_code} with audio_file_id: {audio_file.id}")
                # Update the video_project_languages table with the audio_file_id
                result = supabase.table("video_project_languages")\
                    .update({"audio_file_id": str(audio_file.id)})\
                    .eq("project_id", project_id)\
                    .eq("language_code", request.language_code)\
                    .execute()

                if result.data:
                    logger.info(f"✅ Updated language {request.language_code} with audio_file_id: {audio_file.id}")
                else:
                    logger.warning(f"⚠️ No language record found for {request.language_code} in project {project_id}")
            else:
                # No language_code provided - update the primary language
                logger.info(f"🌐 Updating PRIMARY language record with audio_file_id: {audio_file.id}")
                result = supabase.table("video_project_languages")\
                    .update({"audio_file_id": str(audio_file.id)})\
                    .eq("project_id", project_id)\
                    .eq("is_primary", True)\
                    .execute()

                if result.data:
                    logger.info(f"✅ Updated primary language with audio_file_id: {audio_file.id}")
                else:
                    logger.warning(f"⚠️ No primary language record found for project {project_id}")
        except Exception as lang_update_error:
            logger.error(f"❌ Failed to update language record: {str(lang_update_error)}")
            # Don't fail the whole request, just log the error

        # Automatically transcribe the generated audio (skip if ElevenLabs already provided timestamps)
        if elevenlabs_has_timestamps:
            logger.info(f"⏭️ Skipping AssemblyAI transcription - ElevenLabs already provided timestamps for audio file {audio_file.id}")
            logger.info("💰 Saved API cost and time by using ElevenLabs timestamps directly")
        else:
            try:
                logger.info(f"🎤 Starting automatic transcription for audio file {audio_file.id}")
                transcription_selector = TranscriptionServiceSelector()

                # Configure transcription with proper styling options
                transcription_config = {
                    "service": "faster-whisper",
                    "caption_style": "karaoke",
                    "font_size": 52,
                    "font_family": "Arial",
                    "position": "bottom",
                    "default_color": "&HFFFFFF",
                    "highlight_color": "&H00FFFF"
                }

                # Start transcription in background - don't wait for completion
                await transcription_selector.transcribe_with_service(
                    audio_url=audio_file.url,
                    service_name="faster-whisper",  # Use AssemblyAI as default
                    config=transcription_config,
                    user_id=user_id,
                    job_id=project_id,
                    user_input_text=request.user_input_text,
                    language_code=request.language_code  # Pass language code for language-specific file naming
                )
                logger.info(f"✅ Transcription started successfully for audio file {audio_file.id}")

            except Exception as transcription_error:
                # Log the error but don't fail the audio generation
                logger.error(f"⚠️ Failed to start transcription for audio file {audio_file.id}: {str(transcription_error)}")
                logger.warning("⚠️ Audio generation succeeded but transcription failed - continuing")

        # Now that all processing is complete (audio + transcription started), mark as ready
        try:
            final_update = VideoProjectUpdate(status="audio_ready")
            await video_project_repo.update(UUID(project_id), final_update)
            logger.info(f"📊 Final status set to 'audio_ready' for project {project_id}")
        except Exception as status_error:
            logger.error(f"⚠️ Failed to update final status: {str(status_error)}")

        logger.info(f"🎯 Background audio regeneration completed for project {project_id} (job: {job_id})")

    except Exception as e:
        logger.error(f"❌ Background audio regeneration failed for project {project_id}: {str(e)}")

        # Update project status to error
        try:
            from uuid import UUID
            from repositories.video_project_repository import VideoProjectRepository
            from db.supabase_client import supabase_client
            from models.video_project_models import VideoProjectUpdate

            video_project_repo = VideoProjectRepository(supabase_client)
            update_data = VideoProjectUpdate(status="error")
            await video_project_repo.update(UUID(project_id), update_data)
        except:
            pass


@router.get("/projects/video/{gcs_path:path}")
async def get_video_file_details(
    gcs_path: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get video file details from GCS path and generate a fresh signed URL.

    Args:
        gcs_path: GCS path like "videos/user_id/project_id_lang.mp4"

    Returns:
        Video details with fresh signed URL
    """
    from services.gcs_service import get_gcs_service

    try:
        user_id = current_user.get("user_id")

        logger.info(f"🎬 Getting video file details for GCS path: {gcs_path}")

        # Get GCS service
        gcs_service = get_gcs_service()

        if not gcs_service.is_available():
            logger.error("❌ GCS service not available")
            raise HTTPException(status_code=503, detail="Storage service unavailable")

        # Get video info from GCS
        video_info = await gcs_service.get_video_info(gcs_path)

        if not video_info:
            logger.error(f"❌ Video file not found in GCS: {gcs_path}")
            raise HTTPException(status_code=404, detail="Video file not found")

        # Generate fresh signed URL (valid for 24 hours)
        signed_url = await gcs_service.generate_signed_url(gcs_path, expiration_hours=24)

        if not signed_url:
            logger.error(f"❌ Failed to generate signed URL for {gcs_path}")
            raise HTTPException(status_code=500, detail="Failed to generate video URL")

        logger.info(f"✅ Generated signed URL for video: {gcs_path}")

        # Return video details matching the VideoFile interface expected by frontend
        return {
            "id": gcs_path,
            "url": signed_url,
            "size": video_info.get("size", 0),
            "duration": 0,  # Duration not stored in GCS metadata
            "projectId": None  # Can be derived from path if needed
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting video file details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get video details: {str(e)}")
