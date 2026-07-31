"""
Pydantic models for custom voice cloning feature.
Handles validation and serialization for voice cloning API endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class CustomVoiceCreate(BaseModel):
    """Request to clone a new voice"""
    voice_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class CustomVoiceResponse(BaseModel):
    """API response for custom voice"""
    id: str
    voice_name: str
    description: Optional[str]
    provider: str = "elevenlabs"
    voice_id: Optional[str] = None
    elevenlabs_voice_id: str
    status: str
    preview_url: Optional[str]
    created_at: str
    error_message: Optional[str] = None


class CustomVoiceListResponse(BaseModel):
    """List of custom voices"""
    voices: list[CustomVoiceResponse]
    total_count: int
    max_voices: int = 5
