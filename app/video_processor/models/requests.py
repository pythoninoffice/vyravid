"""
Request models for Cloud Video Processor API
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum

class SourceType(str, Enum):
    URL = "url"
    GCS = "gcs"

class AudioSource(BaseModel):
    url: str = Field(..., description="URL or GCS path to audio file")
    type: SourceType = Field(..., description="Source type: url or gcs")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")
    duration: Optional[float] = Field(default=None, description="Audio duration in seconds (if provided, skips ffprobe)")

class VideoFile(BaseModel):
    url: str = Field(..., description="GCS URL or HTTP URL to video file")
    duration: Optional[float] = Field(default=None, description="Video duration in seconds (if provided, skips ffprobe)")

class ImageFile(BaseModel):
    url: str = Field(..., description="GCS URL or HTTP URL to image file")
    duration: Optional[float] = Field(default=None, description="Duration to display image in seconds")

class TextOverlay(BaseModel):
    text: str = Field(..., description="Text content to display")
    startTime: float = Field(default=0, description="Start time in seconds")
    endTime: float = Field(default=5, description="End time in seconds")
    x: float = Field(default=50, description="X position as percentage of video width (0-100)")
    y: float = Field(default=50, description="Y position as percentage of video height (0-100)")
    fontSize: int = Field(default=48, description="Font size in pixels")
    fontColor: str = Field(default="#ffffff", description="Font color as hex (e.g. #ffffff)")
    fontWeight: str = Field(default="bold", description="Font weight: normal or bold")
    fontFamily: str = Field(default="Arial", description="Font family name")
    backgroundColor: str = Field(default="transparent", description="Background color (transparent or hex)")
    animation: str = Field(default="none", description="Animation: none, fade-in, slide-up, slide-down")


class ImageTimelineSegment(BaseModel):
    image_url: str = Field(..., description="URL to image file")
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    transition_type: Optional[str] = Field(default="cut", description="Transition type: cut, crossfade, slide")
    transition_duration: Optional[float] = Field(default=0, description="Transition duration in seconds")
    camera_movement: Optional[str] = Field(default="static", description="Camera movement: static, pan_right, pan_left, pan_up, pan_down, zoom_in, zoom_out, doodle_slow, doodle_fast")
    greenscreen_effect: Optional[str] = Field(default=None, description="Greenscreen effect URL: fire1, fire2, or custom URL")

class VideoSegment(BaseModel):
    start_time: str = Field(..., description="Start timestamp (HH:MM:SS)")
    end_time: str = Field(..., description="End timestamp (HH:MM:SS)")
    output_name: Optional[str] = Field(default=None, description="Output filename")

class MediaProcessingRequest(BaseModel):
    job_id: str = Field(..., description="Unique job identifier")
    operation: str = Field(..., description="Operation type: full_pipeline, transcribe_only, video_only")
    audio_sources: List[AudioSource] = Field(default=[], description="Audio files for transcription")
    video_files: List[VideoFile] = Field(default=[], description="Video files with optional duration")

    # Background configuration
    background_type: Optional[str] = Field(default="video", description="Background type: video, image, image_timeline")
    background_image_url: Optional[str] = Field(default=None, description="Single image URL for static background")
    image_timeline: Optional[List[ImageTimelineSegment]] = Field(default=None, description="Image timeline segments for dynamic backgrounds")

    # Camera movements configuration
    camera_movements: Optional[List[str]] = Field(
        default=None,
        description="Camera movements per image/video ('pan_right', 'pan_left', 'pan_up', 'pan_down', 'zoom_in', 'zoom_out', 'doodle_slow', 'doodle_fast', 'static')"
    )

    transcription_config: Dict[str, Any] = Field(default={}, description="Transcription service configuration")
    video_parameters: Dict[str, Any] = Field(default={}, description="FFmpeg processing parameters")
    
    # Background music configuration
    background_music_id: Optional[str] = Field(default=None, description="ID of preset music track to use")
    music_volume: Optional[float] = Field(default=0.25, description="Music volume level (0.0-1.0)")
    music_fade_in: Optional[float] = Field(default=2.0, description="Music fade in duration in seconds")
    music_fade_out: Optional[float] = Field(default=3.0, description="Music fade out duration in seconds")

    text_overlays: Optional[List[TextOverlay]] = Field(default=None, description="Text overlays to burn into the final video")
    watermark_logo_url: Optional[str] = Field(default=None, description="Signed/public URL to transparent watermark or logo image")
    watermark_logo_gcs_path: Optional[str] = Field(default=None, description="GCS path for the user's watermark or logo image")
    watermark_logo_position: Optional[str] = Field(default="bottom_right", description="Watermark/logo position: top_left, top_right, bottom_left, or bottom_right")

    webhook_url: str = Field(..., description="Callback URL for completion notification")
    user_id: Optional[str] = Field(default=None, description="User ID for tracking")
    language_code: Optional[str] = Field(default=None, description="Language code for multi-language support (e.g., 'en', 'es', 'fr')")

class TranscriptionRequest(BaseModel):
    job_id: str = Field(..., description="Unique job identifier")
    audio_sources: List[AudioSource] = Field(..., description="Audio files for transcription")
    transcription_config: Dict[str, Any] = Field(default={}, description="Transcription service configuration")
    webhook_url: str = Field(..., description="Callback URL for completion notification")
    user_id: Optional[str] = Field(default=None, description="User ID for tracking")

class VideoCombineRequest(BaseModel):
    job_id: str = Field(..., description="Unique job identifier")
    video_files: List[str] = Field(..., description="GCS URLs for video files to combine")
    output_filename: Optional[str] = Field(default=None, description="Output filename")
    video_parameters: Dict[str, Any] = Field(default={}, description="FFmpeg parameters")
    webhook_url: str = Field(..., description="Callback URL for completion notification")
    user_id: Optional[str] = Field(default=None, description="User ID for tracking")

class AudioVideoSyncRequest(BaseModel):
    job_id: str = Field(..., description="Unique job identifier")
    video_file: str = Field(..., description="GCS URL for video file")
    audio_file: str = Field(..., description="GCS URL for audio file")
    sync_parameters: Dict[str, Any] = Field(default={}, description="Audio/video sync parameters")
    webhook_url: str = Field(..., description="Callback URL for completion notification")
    user_id: Optional[str] = Field(default=None, description="User ID for tracking")

class VideoSplitRequest(BaseModel):
    job_id: str = Field(..., description="Unique job identifier")
    video_file: str = Field(..., description="GCS URL for video file")
    segments: List[VideoSegment] = Field(..., description="Video segments to extract")
    webhook_url: str = Field(..., description="Callback URL for completion notification")
    user_id: Optional[str] = Field(default=None, description="User ID for tracking")

class SubtitleBurnRequest(BaseModel):
    job_id: str = Field(..., description="Unique job identifier")
    video_file: str = Field(..., description="GCS URL for video file")
    subtitle_file: str = Field(..., description="GCS URL for subtitle file (SRT format)")
    style_config: Dict[str, Any] = Field(default={}, description="Subtitle styling configuration")
    webhook_url: str = Field(..., description="Callback URL for completion notification")
    user_id: Optional[str] = Field(default=None, description="User ID for tracking")

# Timeline Rendering Models
class ClipTransform(BaseModel):
    x: float = Field(default=0, description="X position in pixels")
    y: float = Field(default=0, description="Y position in pixels")
    scaleX: float = Field(default=1, description="Horizontal scale factor")
    scaleY: float = Field(default=1, description="Vertical scale factor")
    rotation: float = Field(default=0, description="Rotation in degrees")
    opacity: float = Field(default=1, description="Opacity (0-1)")

class TextProperties(BaseModel):
    content: str = Field(..., description="Text content to display")
    fontSize: int = Field(default=32, description="Font size in pixels")
    fill: str = Field(default="#ffffff", description="Text color (hex)")
    fontFamily: str = Field(default="Arial", description="Font family")
    x: float = Field(default=100, description="X position in pixels")
    y: float = Field(default=100, description="Y position in pixels")

class TimelineClip(BaseModel):
    """
    Timeline clip with support for effects from ffmpeg_processor.

    Effects supported:
    - Camera movements: pan_right, pan_left, pan_up, pan_down, zoom_in, zoom_out, doodle_slow, doodle_fast
    - Greenscreen overlays: fire, electric, rain, stars, thunder, etc.
    - Transitions: Currently reserved for future sequential timeline mode

    Note on transitions:
    The timeline renderer supports non-linear editing with overlapping clips.
    Transitions (xfade) work best for sequential clips without overlap.
    For now, transition properties are defined but not yet implemented in rendering.
    Future enhancement could add a "sequential mode" that applies transitions between
    clips on the same track when they're arranged end-to-end.
    """
    id: float = Field(..., description="Unique clip identifier")
    type: str = Field(..., description="Clip type: video, image, audio, text")
    name: str = Field(..., description="Clip name")
    startTime: float = Field(..., description="Start time in seconds")
    duration: float = Field(..., description="Duration in seconds")
    src: Optional[str] = Field(default=None, description="GCS URL or HTTP URL to media file")
    transform: Optional[ClipTransform] = Field(default=None, description="Transformation properties for image/video")
    text: Optional[TextProperties] = Field(default=None, description="Text properties for text clips")

    # New effect properties from ffmpeg_processor
    cameraMovement: Optional[str] = Field(
        default=None,
        description="Camera movement: pan_right, pan_left, pan_up, pan_down, zoom_in, zoom_out, doodle_slow, doodle_fast, static"
    )
    greenscreenEffect: Optional[str] = Field(
        default=None,
        description="Greenscreen effect overlay URL or effect name (e.g., 'fire1_v', 'electric_h')"
    )
    transitionType: Optional[str] = Field(
        default=None,
        description="[Reserved] Transition to next clip: fade, slidedown, smoothleft, pixelize, circleopen, etc. Not yet implemented in timeline renderer."
    )
    transitionDuration: Optional[float] = Field(
        default=0.5,
        description="[Reserved] Duration of transition effect in seconds. Not yet implemented in timeline renderer."
    )

class TimelineTrack(BaseModel):
    id: int = Field(..., description="Track ID")
    name: str = Field(..., description="Track name")
    zIndex: int = Field(..., description="Layer order (higher = on top)")
    clips: List[TimelineClip] = Field(default=[], description="Clips in this track")

class CanvasSettings(BaseModel):
    width: int = Field(..., description="Canvas width in pixels")
    height: int = Field(..., description="Canvas height in pixels")
    background: str = Field(default="#000000", description="Background color (hex)")

class TimelineData(BaseModel):
    version: str = Field(..., description="Timeline format version")
    duration: float = Field(..., description="Total timeline duration in seconds")
    canvas: CanvasSettings = Field(..., description="Canvas configuration")
    tracks: List[TimelineTrack] = Field(..., description="Timeline tracks")

class TimelineRenderRequest(BaseModel):
    job_id: Optional[str] = Field(default=None, description="Unique job identifier (generated if not provided)")
    timeline: TimelineData = Field(..., description="Timeline data to render")
    output_format: Optional[str] = Field(default="mp4", description="Output format: mp4, webm")
    quality: Optional[str] = Field(default="high", description="Quality preset: low, medium, high")
    upscale_mode: Optional[str] = Field(default="none", description="Image upscaling: none or 2k_option_1 (ffmpeg)")
    webhook_url: Optional[str] = Field(default=None, description="Callback URL for completion notification")
    user_id: Optional[str] = Field(default=None, description="User ID for tracking")

    # Watermark / logo overlay support (profile-driven from frontend)
    include_watermark_logo: Optional[bool] = Field(
        default=None,
        description="Whether to include/apply watermark/logo overlay (if None, apply when url or gcs_path present)"
    )
    watermark_logo_url: Optional[str] = Field(
        default=None,
        description="Signed/public URL to transparent watermark or logo image"
    )
    watermark_logo_gcs_path: Optional[str] = Field(
        default=None,
        description="GCS path for the user's watermark or logo image"
    )
    watermark_logo_position: Optional[str] = Field(
        default="bottom_right",
        description="Watermark/logo position: top_left, top_right, bottom_left, or bottom_right"
    )


class WhiteboardDoodleRequest(BaseModel):
    """Request model for whiteboard doodle generation"""
    image_url: str = Field(..., description="URL to source image")
    duration: float = Field(default=5.0, description="Duration of animation in seconds")
    speed: str = Field(default="fast", description="Animation speed: 'fast' or 'slow'")
    width: int = Field(default=1080, description="Output video width in pixels")
    height: int = Field(default=1920, description="Output video height in pixels")
    job_id: Optional[str] = Field(default=None, description="Unique job identifier")


class ManimGenerateRequest(BaseModel):
    """Request model for Manim animation generation"""
    prompt: str = Field(..., description="Text prompt describing the animation to generate")
    mode: str = Field(default="creative", description="Generation mode: 'creative' (AI enhanced) or 'strict' (exact prompt)")
    quality: str = Field(default="m", description="Video quality: 'l' (480p), 'm' (720p), 'h' (1080p), 'k' (4k)")
    aspect_ratio: str = Field(default="16:9", description="Video aspect ratio: '16:9' (landscape), '9:16' (portrait), '1:1' (square)")
    model: str = Field(default="gemini-2.5-flash", description="Gemini model to use for code generation")
    webhook_url: Optional[str] = Field(default=None, description="Callback URL for completion notification")
    project_id: Optional[str] = Field(default=None, description="Project ID for tracking")
    scene_id: Optional[str] = Field(default=None, description="Scene ID for tracking")
    user_id: Optional[str] = Field(default=None, description="User ID for GCS path organization")
    job_id: Optional[str] = Field(default=None, description="Unique job identifier (generated if not provided)")


class VyraManimRequest(BaseModel):
    """Request model for Vyra Manim animation generation via Claude"""
    description: str = Field(..., description="Text description of the animation to generate")
    user_id: str = Field(..., description="User ID for GCS path organization")
    session_id: str = Field(..., description="Session ID for tracking")
    previous_code: Optional[str] = Field(default=None, description="Previous code for iterative refinement")
    quality: str = Field(default="h", description="Video quality: 'l' (480p), 'm' (720p), 'h' (1080p), 'k' (4k)")
    aspect_ratio: str = Field(default="16:9", description="Video aspect ratio: '16:9', '9:16', '1:1'")
