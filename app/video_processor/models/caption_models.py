"""
Caption and subtitle models for Cloud Video Processor

This module provides data models for caption generation, subtitle styling,
and word-level timing information.
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from enum import Enum
from uuid import UUID


class WordSegment(BaseModel):
    """Word-level timing information for subtitle generation"""
    word: str = Field(..., description="The word text")
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    confidence: Optional[float] = Field(default=None, description="Confidence score (0-1)")
    
    class Config:
        from_attributes = True


class Caption(BaseModel):
    """Caption segment with timing information"""
    id: Optional[UUID] = Field(default=None, description="Unique caption identifier")
    text: str = Field(..., description="Caption text")
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    confidence: Optional[float] = Field(default=None, description="Confidence score (0-1)")
    
    class Config:
        from_attributes = True


class SubtitleStyle(str, Enum):
    """Subtitle animation styles"""
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
    """Settings for caption generation and styling"""
    position: str = Field(default="middle", description="Caption position: top, middle, bottom")
    font_size: int = Field(default=60, description="Font size in points")
    font_family: str = Field(default="Luckiest Guy", description="Font family name")
    font_file_path: Optional[str] = Field(default=None, description="Path to TTF font file")
    highlight_color: str = Field(default="&H00FFFF&", description="Highlight color in ASS format")
    default_color: str = Field(default="&HFFFFFF&", description="Default text color in ASS format")
    alignment: Optional[int] = Field(default=None, description="Text alignment (ASS format)")
    margin_v: int = Field(default=0, description="Vertical margin in pixels")
    subtitle_style: SubtitleStyle = Field(default=SubtitleStyle.KARAOKE, description="Subtitle animation style")
    background_type: Optional[str] = Field(default="video", description="Background type: video, image, image_timeline")
    video_parameters: Optional[Dict[str, Any]] = Field(default=None, description="Video processing parameters including resolution")
    
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


class CaptionGenerationRequest(BaseModel):
    """Request for caption generation"""
    job_id: str = Field(..., description="Unique job identifier")
    word_segments: List[WordSegment] = Field(..., description="Word-level timing data")
    settings: CaptionSettings = Field(default_factory=CaptionSettings, description="Caption styling settings")
    output_filename: Optional[str] = Field(default=None, description="Output filename (without extension)")
    language: str = Field(default="en", description="Language code")
    user_id: Optional[int] = Field(default=None, description="User ID for file organization")
    
    class Config:
        from_attributes = True


class CaptionGenerationResult(BaseModel):
    """Result of caption generation"""
    job_id: str = Field(..., description="Job identifier")
    srt_content: str = Field(..., description="Generated SRT subtitle content")
    ass_content: str = Field(..., description="Generated ASS subtitle content")
    srt_file_url: Optional[str] = Field(default=None, description="GCS URL for SRT file")
    ass_file_url: Optional[str] = Field(default=None, description="GCS URL for ASS file")
    word_count: int = Field(..., description="Number of words processed")
    duration: float = Field(..., description="Total duration in seconds")
    style_used: SubtitleStyle = Field(..., description="Subtitle style that was applied")
    
    class Config:
        from_attributes = True


class TranscriptionResult(BaseModel):
    """Result of transcription with word-level timing"""
    language: str = Field(..., description="Detected or specified language")
    segments: List[Caption] = Field(default=[], description="Sentence-level captions")
    word_segments: List[WordSegment] = Field(..., description="Word-level timing data")
    duration: float = Field(..., description="Total audio duration in seconds")
    confidence: Optional[float] = Field(default=None, description="Overall confidence score")
    
    class Config:
        from_attributes = True