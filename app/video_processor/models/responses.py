"""
Response models for Cloud Video Processor API
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime

class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class MediaProcessingResponse(BaseModel):
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Current job status (processing, completed, failed)")  # Use string for compatibility
    message: Optional[str] = Field(default=None, description="Status message")
    transcript: Optional[str] = Field(default=None, description="Transcribed text")
    subtitle_files: List[str] = Field(default=[], description="Generated SRT files (GCS URLs)")
    output_files: List[str] = Field(default=[], description="Processed video files (GCS URLs)")
    transcription_cost: Optional[float] = Field(default=None, description="Transcription API cost")
    processing_time: Optional[float] = Field(default=None, description="Processing time in seconds")
    error_message: Optional[str] = Field(default=None, description="Error details if failed")
    created_at: Optional[datetime] = Field(default=None, description="Job creation timestamp")
    completed_at: Optional[datetime] = Field(default=None, description="Job completion timestamp")
    
    # Additional fields for local processing compatibility
    operation: Optional[str] = Field(default=None, description="Operation type performed")
    audio_sources_count: Optional[int] = Field(default=None, description="Number of audio sources processed")
    video_files_count: Optional[int] = Field(default=None, description="Number of video files processed")
    webhook_url: Optional[str] = Field(default=None, description="Webhook callback URL")
    processing_mode: str = Field(default="cloud", description="Processing mode (cloud/local for compatibility)")
    
    # Processing steps tracking for transparency
    processing_steps: Optional[Dict[str, bool]] = Field(default=None, description="Completed processing steps")
    partial_success: Optional[bool] = Field(default=None, description="Whether processing had partial failures")
    processing_errors: Optional[List[str]] = Field(default=None, description="List of non-fatal processing errors")
    
    # Simplified processing result (for new synchronous approach)
    result: Optional[Dict[str, Any]] = Field(default=None, description="Detailed processing results and timing")

class JobStatusResponse(BaseModel):
    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(..., description="Current job status")
    progress: Optional[float] = Field(default=None, description="Progress percentage (0-100)")
    current_step: Optional[str] = Field(default=None, description="Current processing step")
    transcript: Optional[str] = Field(default=None, description="Transcribed text (if available)")
    output_files: List[str] = Field(default=[], description="Completed output files")
    error_message: Optional[str] = Field(default=None, description="Error details if failed")
    created_at: Optional[datetime] = Field(default=None, description="Job creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Last update timestamp")

class HealthResponse(BaseModel):
    status: str = Field(..., description="Service health status")
    version: str = Field(..., description="Service version")
    checks: Dict[str, bool] = Field(default={}, description="Individual health check results")
    timestamp: Optional[str] = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="Health check timestamp")

class ErrorResponse(BaseModel):
    error_code: str = Field(..., description="Error code")
    error_message: str = Field(..., description="Human-readable error message")
    details: Dict[str, Any] = Field(default={}, description="Additional error details")
    retry_after: Optional[int] = Field(default=None, description="Retry delay in seconds")
    support_reference: str = Field(..., description="Support reference ID")

class TimelineRenderResponse(BaseModel):
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Current job status (completed, failed, processing)")
    message: Optional[str] = Field(default=None, description="Status message")
    video_url: Optional[str] = Field(default=None, description="GCS URL of rendered video")
    duration: Optional[float] = Field(default=None, description="Video duration in seconds")
    processing_time: Optional[float] = Field(default=None, description="Processing time in seconds")
    error_message: Optional[str] = Field(default=None, description="Error details if failed")
    created_at: Optional[datetime] = Field(default=None, description="Job creation timestamp")
    completed_at: Optional[datetime] = Field(default=None, description="Job completion timestamp")


class ManimGenerateResponse(BaseModel):
    """Response model for Manim animation generation"""
    success: bool = Field(..., description="Whether the generation was successful")
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Current job status (processing, completed, failed)")
    video_url: Optional[str] = Field(default=None, description="Signed GCS URL of the generated video")
    gcs_path: Optional[str] = Field(default=None, description="GCS path to the video file")
    code: Optional[str] = Field(default=None, description="Generated Manim Python code")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    message: Optional[str] = Field(default=None, description="Status message")
    processing_time: Optional[float] = Field(default=None, description="Processing time in seconds")
    file_size: Optional[int] = Field(default=None, description="Video file size in bytes")
    generated_id: Optional[str] = Field(default=None, description="ID of the record in generated_images table")
    created_at: Optional[datetime] = Field(default=None, description="Job creation timestamp")
    completed_at: Optional[datetime] = Field(default=None, description="Job completion timestamp")