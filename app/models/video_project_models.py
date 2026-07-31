"""
Pydantic models for video projects stored in Supabase
"""

from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID

class VideoProject(BaseModel):
    """Video project model for Supabase storage"""
    id: UUID
    user_id: UUID
    title: str
    status: str = "completed"
    created_at: datetime
    completed_at: Optional[datetime] = None
    duration: float = 0.0
    file_size: int = 0
    gcs_path: Optional[str] = None
    gcs_signed_url: Optional[str] = None
    gcs_signed_url_expires_at: Optional[datetime] = None
    thumbnail_url: Optional[str] = None
    processing_options: Optional[Dict[str, Any]] = None
    story_content: Optional[str] = None
    
    # Cloud processing tracking fields
    processing_method: Optional[str] = "local"  # 'cloud' or 'local'
    webhook_received_at: Optional[datetime] = None  # When webhook was received
    
    # Audio generation fields
    audio_file_id: Optional[str] = None  # Reference to generated audio file

    # Draft data for work-in-progress projects
    draft_data: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

class VideoProjectCreate(BaseModel):
    """Model for creating a new video project"""
    id: Optional[UUID] = None  # Optional - if provided, use this ID; otherwise auto-generate
    user_id: UUID
    title: str
    status: str = "completed"
    duration: float = 0.0
    file_size: int = 0
    gcs_path: Optional[str] = None
    gcs_signed_url: Optional[str] = None
    gcs_signed_url_expires_at: Optional[datetime] = None
    thumbnail_url: Optional[str] = None
    processing_options: Optional[Dict[str, Any]] = None
    story_content: Optional[str] = None

    # Cloud processing tracking fields
    processing_method: Optional[str] = "local"  # 'cloud' or 'local'
    webhook_received_at: Optional[datetime] = None  # When webhook was received

    # Audio generation fields
    audio_file_id: Optional[str] = None  # Reference to generated audio file

    # Draft data for work-in-progress projects
    draft_data: Optional[Dict[str, Any]] = None

class VideoProjectUpdate(BaseModel):
    """Model for updating a video project"""
    title: Optional[str] = None
    status: Optional[str] = None
    completed_at: Optional[datetime] = None
    duration: Optional[float] = None
    file_size: Optional[int] = None
    gcs_path: Optional[str] = None
    gcs_signed_url: Optional[str] = None
    gcs_signed_url_expires_at: Optional[datetime] = None
    thumbnail_url: Optional[str] = None
    processing_options: Optional[Dict[str, Any]] = None
    story_content: Optional[str] = None

    # Cloud processing tracking fields
    processing_method: Optional[str] = None
    webhook_received_at: Optional[datetime] = None

    # Audio generation fields
    audio_file_id: Optional[str] = None  # Reference to generated audio file

    # Draft data for work-in-progress projects
    draft_data: Optional[Dict[str, Any]] = None

# Scene Models
class ProjectSceneBase(BaseModel):
    """Base model for project scenes"""
    id: Optional[str] = None  # Scene UUID - preserved across save/load for stable references
    scene_index: int
    description: str
    prompt: str
    scene_type: Optional[str] = None
    scene_script: Optional[str] = None
    layout_type: Optional[str] = None
    target_duration: Optional[float] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    character_ids: Optional[list[str]] = None
    dialogue_turns: Optional[list[Dict[str, Any]]] = None
    character_layout: Optional[list[Dict[str, Any]]] = None
    generated_image: Optional[Dict[str, Any]] = None
    animation_prompt: Optional[str] = None
    animated_video: Optional[Dict[str, Any]] = None
    camera_movement: Optional[str] = None
    transition_type: Optional[str] = None
    transition_duration: Optional[float] = None
    greenscreen_effect: Optional[str] = None
    scene_audio: Optional[Dict[str, Any]] = None

class ProjectScene(ProjectSceneBase):
    """Full project scene model with metadata"""
    id: UUID
    project_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class SaveProjectScenesRequest(BaseModel):
    """Request to save multiple scenes for a project"""
    project_id: str
    scenes: list[ProjectSceneBase]

class SaveProjectScenesResponse(BaseModel):
    """Response after saving scenes"""
    project_id: str
    scenes_count: int
    message: str

class LoadProjectScenesResponse(BaseModel):
    """Response when loading scenes"""
    project_id: str
    scenes: list[Dict[str, Any]]
    scenes_count: int


class GenerateSceneAudioRequest(BaseModel):
    """Request to generate per-scene audio for a project"""
    tts_provider: str = "deepgram"
    default_voice_id: str
    audio_speed: Optional[float] = 1.0
    language_code: Optional[str] = "en"
    character_voice_map: Optional[Dict[str, Dict[str, Any]]] = None


class GenerateSceneAudioResponse(BaseModel):
    """Response after generating scene audio"""
    project_id: str
    scenes: list[Dict[str, Any]]
    combined_audio: Optional[Dict[str, Any]] = None
    generated_count: int
    message: str


# Text Layer Models
class TextLayerBase(BaseModel):
    """A text overlay on the video timeline"""
    id: Optional[str] = None
    text: str
    startTime: float
    endTime: float
    x: float = 50
    y: float = 50
    fontSize: int = 48
    fontColor: str = "#ffffff"
    fontWeight: str = "bold"
    fontFamily: str = "Arial"
    backgroundColor: str = "transparent"
    animation: str = "none"

class SaveTextLayersRequest(BaseModel):
    """Request to save text layers for a project"""
    project_id: str
    text_layers: list[TextLayerBase]

class SaveTextLayersResponse(BaseModel):
    """Response after saving text layers"""
    project_id: str
    text_layers_count: int
    message: str

class LoadTextLayersResponse(BaseModel):
    """Response when loading text layers"""
    project_id: str
    text_layers: list[Dict[str, Any]]
    text_layers_count: int
