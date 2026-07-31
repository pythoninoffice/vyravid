"""
Pydantic models for character design API endpoints
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID

# =============================================
# Character Collection Models
# =============================================

class CharacterCollectionBase(BaseModel):
    """Base model for character collections"""
    name: str = Field(..., min_length=1, max_length=255, description="Collection name")
    description: Optional[str] = Field(None, description="Optional collection description")

class CharacterCollectionCreate(CharacterCollectionBase):
    """Request model for creating a character collection"""
    pass

class CharacterCollectionUpdate(BaseModel):
    """Request model for updating a character collection"""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Collection name")
    description: Optional[str] = Field(None, description="Collection description")

class CharacterCollection(CharacterCollectionBase):
    """Response model for a character collection"""
    id: UUID = Field(..., description="Unique collection ID")
    user_id: UUID = Field(..., description="Owner user ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    character_count: Optional[int] = Field(0, description="Number of characters in collection")

    class Config:
        from_attributes = True

# =============================================
# Character Reference Image Models
# =============================================

class CharacterReferenceImageBase(BaseModel):
    """Base model for character reference images"""
    angle_description: Optional[str] = Field(None, max_length=255, description="Description of angle/view (e.g., front, side, back)")
    is_primary: bool = Field(False, description="Whether this is the primary thumbnail image")
    display_order: int = Field(0, ge=0, description="Display order for sorting")

class CharacterReferenceImageCreate(CharacterReferenceImageBase):
    """Request model for adding a reference image to a character"""
    generated_image_id: UUID = Field(..., description="ID of the generated image to use as reference")

class CharacterReferenceImageUpdate(BaseModel):
    """Request model for updating a reference image"""
    angle_description: Optional[str] = Field(None, max_length=255, description="Angle description")
    is_primary: Optional[bool] = Field(None, description="Whether this is primary")
    display_order: Optional[int] = Field(None, ge=0, description="Display order")

class CharacterReferenceImage(CharacterReferenceImageBase):
    """Response model for a character reference image"""
    id: UUID = Field(..., description="Unique reference image link ID")
    character_id: UUID = Field(..., description="Character ID")
    generated_image_id: UUID = Field(..., description="Generated image ID")
    created_at: datetime = Field(..., description="Creation timestamp")

    # Nested image data (joined from generated_images)
    image_url: Optional[str] = Field(None, description="Signed URL for the image")
    thumbnail_url: Optional[str] = Field(None, description="Signed URL for thumbnail")
    width: Optional[int] = Field(None, description="Image width")
    height: Optional[int] = Field(None, description="Image height")

    class Config:
        from_attributes = True

class ReorderReferenceImagesRequest(BaseModel):
    """Request model for reordering reference images"""
    image_orders: List[Dict[str, int]] = Field(..., description="List of {id: UUID, display_order: int}")

    @validator('image_orders')
    def validate_image_orders(cls, v):
        """Validate image_orders structure"""
        for item in v:
            if 'id' not in item or 'display_order' not in item:
                raise ValueError("Each item must have 'id' and 'display_order' fields")
        return v

# =============================================
# Character Design Models
# =============================================

class CharacterDesignBase(BaseModel):
    """Base model for character designs"""
    name: str = Field(..., min_length=1, max_length=255, description="Character name")
    description: Optional[str] = Field(None, description="Text description/prompt for the character")
    tags: List[str] = Field(default_factory=list, description="Tags (e.g., novel/game/anime names)")
    visual_style_notes: Optional[str] = Field(None, description="Visual style notes for consistency")
    collection_id: Optional[UUID] = Field(None, description="Optional collection ID")

class CharacterDesignCreate(CharacterDesignBase):
    """Request model for creating a character"""

    @validator('name')
    def validate_name(cls, v):
        """Validate character name is not empty after stripping"""
        if not v.strip():
            raise ValueError("Character name cannot be empty")
        return v.strip()

class CharacterDesignUpdate(BaseModel):
    """Request model for updating a character"""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Character name")
    description: Optional[str] = Field(None, description="Character description/prompt")
    tags: Optional[List[str]] = Field(None, description="Character tags")
    visual_style_notes: Optional[str] = Field(None, description="Visual style notes")
    collection_id: Optional[UUID] = Field(None, description="Collection ID (null to remove from collection)")
    thumbnail_image_id: Optional[UUID] = Field(None, description="Primary thumbnail image ID")

    @validator('name')
    def validate_name(cls, v):
        """Validate character name if provided"""
        if v is not None and not v.strip():
            raise ValueError("Character name cannot be empty")
        return v.strip() if v else v

class CharacterDesign(CharacterDesignBase):
    """Response model for a character design"""
    id: UUID = Field(..., description="Unique character ID")
    user_id: UUID = Field(..., description="Owner user ID")
    thumbnail_image_id: Optional[UUID] = Field(None, description="Primary thumbnail image ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    # Optional nested data
    reference_images: Optional[List[CharacterReferenceImage]] = Field(None, description="Reference images")
    thumbnail_url: Optional[str] = Field(None, description="Thumbnail signed URL")
    collection_name: Optional[str] = Field(None, description="Collection name if in a collection")

    class Config:
        from_attributes = True

class CharacterDesignDetailed(CharacterDesign):
    """Detailed character design with all reference images"""
    reference_images: List[CharacterReferenceImage] = Field(default_factory=list, description="All reference images")

# =============================================
# Character List Response Models
# =============================================

class CharacterListResponse(BaseModel):
    """Response model for listing characters"""
    characters: List[CharacterDesign] = Field(..., description="List of characters")
    total: int = Field(..., description="Total number of characters")
    page: int = Field(..., description="Current page number")
    limit: int = Field(..., description="Items per page")
    has_more: bool = Field(..., description="Whether there are more results")

class CollectionListResponse(BaseModel):
    """Response model for listing collections"""
    collections: List[CharacterCollection] = Field(..., description="List of collections")
    total: int = Field(..., description="Total number of collections")

# =============================================
# Scene Character Models
# =============================================

class SceneCharacterBase(BaseModel):
    """Base model for scene-character relationships"""
    scene_id: str = Field(..., min_length=1, description="Scene ID within the video project")
    character_id: UUID = Field(..., description="Character ID")
    prompt_override: Optional[str] = Field(None, description="Optional scene-specific prompt modifications")

class SceneCharacterCreate(SceneCharacterBase):
    """Request model for adding a character to a scene"""
    video_project_id: UUID = Field(..., description="Video project ID")

class SceneCharacterUpdate(BaseModel):
    """Request model for updating a scene-character relationship"""
    prompt_override: Optional[str] = Field(None, description="Scene-specific prompt modifications")

class SceneCharacter(SceneCharacterBase):
    """Response model for a scene-character relationship"""
    id: UUID = Field(..., description="Unique scene-character link ID")
    video_project_id: UUID = Field(..., description="Video project ID")
    created_at: datetime = Field(..., description="Creation timestamp")

    # Nested character data
    character_name: Optional[str] = Field(None, description="Character name")
    character_description: Optional[str] = Field(None, description="Character description")
    character_thumbnail_url: Optional[str] = Field(None, description="Character thumbnail URL")

    class Config:
        from_attributes = True

class SceneCharactersResponse(BaseModel):
    """Response model for scene characters list"""
    scene_characters: List[SceneCharacter] = Field(..., description="List of characters in the scene")
    total: int = Field(..., description="Total number of characters in scene")

# =============================================
# Combined Prompt Generation Models
# =============================================

class GenerateScenePromptRequest(BaseModel):
    """Request model for generating a combined scene prompt"""
    scene_prompt: str = Field(..., min_length=1, description="Base scene description")
    character_ids: List[UUID] = Field(..., description="List of character IDs to include")
    include_visual_notes: bool = Field(True, description="Whether to include visual style notes")

class GenerateScenePromptResponse(BaseModel):
    """Response model for generated scene prompt"""
    combined_prompt: str = Field(..., description="Combined prompt with character descriptions")
    character_names: List[str] = Field(..., description="List of character names included")
    reference_image_urls: List[str] = Field(..., description="List of reference image URLs")

# =============================================
# Error Response Models
# =============================================

class CharacterErrorResponse(BaseModel):
    """Standard error response for character operations"""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")

# =============================================
# Success Response Models
# =============================================

class DeleteCharacterResponse(BaseModel):
    """Response model for character deletion"""
    success: bool = Field(..., description="Whether deletion was successful")
    message: str = Field(..., description="Status message")

class SetPrimaryImageResponse(BaseModel):
    """Response model for setting primary thumbnail"""
    success: bool = Field(..., description="Whether operation was successful")
    message: str = Field(..., description="Status message")
    thumbnail_image_id: UUID = Field(..., description="New primary thumbnail image ID")
