from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from uuid import UUID

class Story(BaseModel):
    id: UUID
    reddit_id: str
    title: str
    content: str
    author: str
    subreddit: str
    upvotes: int
    comment_count: int
    created_at: datetime
    url: Optional[str] = None
    
    class Config:
        from_attributes = True

class Comment(BaseModel):
    id: UUID
    story_id: UUID
    reddit_id: str
    content: str
    author: str
    upvotes: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ProcessedStory(BaseModel):
    id: UUID
    original_story_id: UUID
    processed_content: str
    user_edits: Optional[str] = None
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    user_id: Optional[UUID] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class VoiceSettings(BaseModel):
    voice_id: str = "English_magnetic_voiced_man"
    speed: float = 1.0
    volume: float = 1.0
    pitch: float = 0.0
    emotion: Optional[str] = None
    english_normalization: bool = True
    
    class Config:
        from_attributes = True

class AudioSettings(BaseModel):
    sample_rate: int = 16000 #32000
    bitrate: int = 128000
    format: str = "mp3"  # Changed from "wav" to "mp3" - Minimax API only supports mp3, pcm, flac
    channel: int = 1
    
    class Config:
        from_attributes = True

class GenerationStatus(str, Enum):
    QUEUED = "queued"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"

class AudioFile(BaseModel):
    id: UUID
    processed_story_id: Optional[UUID] = None
    file_path: str
    duration: Optional[float] = None
    format: str = "mp3"
    voice_settings: VoiceSettings
    audio_settings: AudioSettings
    status: GenerationStatus = GenerationStatus.QUEUED
    task_id: Optional[str] = None  # For async processing
    created_at: datetime
    # GCS fields
    url: Optional[str] = None  # Signed URL for accessing the audio
    gcs_path: Optional[str] = None  # GCS object path
    public_url: Optional[str] = None  # Public GCS URL
    
    class Config:
        from_attributes = True

class WordSegment(BaseModel):
    word: str
    start: float
    end: float
    confidence: Optional[float] = None
    
    class Config:
        from_attributes = True

class Caption(BaseModel):
    id: UUID
    audio_file_id: Optional[UUID] = None
    text: str
    start_time: float
    end_time: float
    confidence: Optional[float] = None
    
    class Config:
        from_attributes = True

class SubtitleStyle(str, Enum):
    KARAOKE = "karaoke"  # Full sentence shown, current word highlighted
    WORD_BY_WORD = "word_by_word"  # Only current word displayed
    SENTENCE = "sentence"  # Full sentences shown for their duration
    
    @classmethod
    def _missing_(cls, value):
        """Handle invalid enum values with a clear error message"""
        valid_values = [e.value for e in cls]
        raise ValueError(
            f"Invalid subtitle style '{value}'. Valid options are: {', '.join(valid_values)}"
        )

class CaptionSettings(BaseModel):
    position: str = "middle"  # "top", "middle", "bottom"
    font_size: int = 32
    font_family: str = "Luckiest Guy"
    font_file_path: Optional[str] = None  # Path to TTF font file
    highlight_color: str = "&H00FFFF&"
    default_color: str = "&HFFFFFF&"
    alignment: Optional[int] = None
    margin_v: int = 0
    subtitle_style: SubtitleStyle = SubtitleStyle.KARAOKE
    
    @validator('subtitle_style', pre=True)
    def validate_subtitle_style(cls, v):
        """Validate subtitle_style with clear error messages"""
        if isinstance(v, str):
            try:
                return SubtitleStyle(v)
            except ValueError:
                valid_values = [e.value for e in SubtitleStyle]
                raise ValueError(
                    f"Invalid subtitle_style '{v}'. Valid options are: {', '.join(valid_values)}"
                )
        return v
    
    @validator('position')
    def validate_position(cls, v):
        """Validate position field"""
        valid_positions = ["top", "middle", "bottom"]
        if v not in valid_positions:
            raise ValueError(
                f"Invalid position '{v}'. Valid options are: {', '.join(valid_positions)}"
            )
        return v
    
    class Config:
        from_attributes = True

class TranscriptionResult(BaseModel):
    language: str
    segments: List[Caption]
    word_segments: List[WordSegment]
    duration: float
    confidence: Optional[float] = None
    
    class Config:
        from_attributes = True

class VideoFile(BaseModel):
    id: UUID
    file_path: str
    duration: Optional[float] = None
    resolution: Optional[str] = None  # e.g., "1920x1080"
    format: str = "mp4"
    created_at: datetime
    
    class Config:
        from_attributes = True

class VideoProcessingJob(BaseModel):
    id: UUID
    audio_file_id: Optional[UUID] = None
    audio_file_path: Optional[str] = None  # Direct path/URL to audio file (supports GCS URLs)
    background_video_ids: Optional[List[UUID]] = None
    background_video_paths: Optional[List[str]] = None  # For direct file path processing
    caption_file_path: Optional[str] = None
    output_file_path: str
    status: GenerationStatus = GenerationStatus.QUEUED
    progress: float = 0.0
    error_message: Optional[str] = None
    processing_options: Optional[Dict[str, Any]] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    # Google Cloud Storage fields
    gcs_path: Optional[str] = None
    public_url: Optional[str] = None
    signed_url: Optional[str] = None
    user_id: Optional[str] = None
    # Database integration fields
    project_id: Optional[UUID] = None  # Link to database project
    story_content: Optional[str] = None  # For better title generation
    project_title: Optional[str] = None  # User-provided project title
    
    class Config:
        from_attributes = True

class VideoProcessingOptions(BaseModel):
    resolution: str = "1080x1080" #"1280x720"
    fps: int = 30
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    quality: str = "medium"  # low, medium, high
    add_captions: bool = True
    caption_position: str = "middle"
    
    class Config:
        from_attributes = True