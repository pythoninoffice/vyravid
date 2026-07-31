"""
Pydantic models for image generation API endpoints
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from uuid import UUID

class ImageGenerationRequest(BaseModel):
    """Request model for image generation"""
    prompt: str = Field(..., min_length=1, description="Text prompt for image generation")
    model: str = Field(default="prunaai/z-image-turbo:7ea16386290ff5977c7812e66e462d7ec3954d8e007a8cd18ded3e7d41f5d7cf", description="Model to use for generation")
    width: int = Field(default=1024, ge=512, le=2048, description="Image width in pixels")
    height: int = Field(default=1024, ge=512, le=2048, description="Image height in pixels")
    num_outputs: int = Field(default=1, ge=1, le=4, description="Number of images to generate")
    aspect_ratio: Optional[str] = Field(default=None, description="Aspect ratio (e.g., '1:1', '16:9', '9:16', '4:3', '3:4')")
    reference_images: Optional[List[str]] = Field(default=None, alias="referenceImages", description="Optional list of reference images as base64 strings")
    tags: Optional[List[str]] = Field(default=None, description="Optional tags for organizing images (e.g., character names, anime/novel names)")
    input: Optional[Dict[str, Any]] = Field(default=None, description="Custom input parameters for specific models (e.g., openai/gpt-image-2)")
    
    @validator('prompt')
    def validate_prompt(cls, v):
        """Validate prompt is not empty after stripping whitespace"""
        if not v.strip():
            raise ValueError("Prompt cannot be empty")
        return v.strip()
    
    class Config:
        populate_by_name = True  # Allow both camelCase and snake_case
        schema_extra = {
            "example": {
                "prompt": "A beautiful sunset over mountains",
                "model": "prunaai/z-image-turbo:7ea16386290ff5977c7812e66e462d7ec3954d8e007a8cd18ded3e7d41f5d7cf",
                "width": 1024,
                "height": 1024,
                "num_outputs": 1
            }
        }

class ImageGenerationStatus(str, Enum):
    """Status of image generation"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ImageGenerationResponse(BaseModel):
    """Response model for image generation initiation"""
    id: str = Field(..., description="Unique generation ID")
    prompt: str = Field(..., description="Text prompt used for generation")
    model_name: str = Field(..., description="Model used for generation")
    status: ImageGenerationStatus = Field(..., description="Current generation status")
    prediction_id: Optional[str] = Field(None, description="Provider prediction ID")
    estimated_time: Optional[int] = Field(None, description="Estimated completion time in seconds")
    created_at: datetime = Field(..., description="Generation creation timestamp")
    
    class Config:
        schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "prompt": "A beautiful sunset over mountains",
                "model_name": "prunaai/z-image-turbo:7ea16386290ff5977c7812e66e462d7ec3954d8e007a8cd18ded3e7d41f5d7cf",
                "status": "processing",
                "prediction_id": "pred_abc123",
                "estimated_time": 30,
                "created_at": "2024-01-01T12:00:00Z"
            }
        }

class GeneratedImage(BaseModel):
    """Model for a generated image record"""
    id: str = Field(..., description="Unique generation ID")
    prompt: str = Field(..., description="Text prompt used for generation")
    model_name: str = Field(..., description="Model used for generation")
    provider: str = Field(default="replicate", description="Provider used for generation")
    status: ImageGenerationStatus = Field(..., description="Generation status")
    signed_url: Optional[str] = Field(None, description="Signed URL for accessing the image")
    thumbnail_signed_url: Optional[str] = Field(None, description="Signed URL for thumbnail")
    width: Optional[int] = Field(None, description="Image width in pixels")
    height: Optional[int] = Field(None, description="Image height in pixels")
    file_size: Optional[int] = Field(None, description="File size in bytes")
    generation_time_ms: Optional[int] = Field(None, description="Generation time in milliseconds")
    error_message: Optional[str] = Field(None, description="Error message if generation failed")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    media_type: Optional[str] = Field(default="image", description="Media type: 'image' or 'video'")
    tags: Optional[List[str]] = Field(default=None, description="Tags for organizing and searching images")
    folder_id: Optional[str] = Field(default=None, description="ID of the folder this image belongs to")

    class Config:
        schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "prompt": "A beautiful sunset over mountains",
                "model_name": "prunaai/z-image-turbo:7ea16386290ff5977c7812e66e462d7ec3954d8e007a8cd18ded3e7d41f5d7cf",
                "provider": "replicate",
                "status": "completed",
                "signed_url": "https://storage.googleapis.com/...",
                "thumbnail_signed_url": "https://storage.googleapis.com/...",
                "width": 1024,
                "height": 1024,
                "file_size": 1048576,
                "generation_time_ms": 15000,
                "error_message": None,
                "created_at": "2024-01-01T12:00:00Z",
                "updated_at": "2024-01-01T12:00:30Z"
            }
        }

class ImageModel(BaseModel):
    """Model information for available image generation models"""
    id: str = Field(..., description="Model identifier")
    name: str = Field(..., description="Human-readable model name")
    description: str = Field(..., description="Model description")
    max_width: int = Field(default=2048, description="Maximum supported width")
    max_height: int = Field(default=2048, description="Maximum supported height")
    supports_batch: bool = Field(default=True, description="Whether model supports batch generation")
    
    class Config:
        schema_extra = {
            "example": {
                "id": "prunaai/z-image-turbo:7ea16386290ff5977c7812e66e462d7ec3954d8e007a8cd18ded3e7d41f5d7cf",
                "name": "Standard",
                "description": "High-quality image generation model",
                "max_width": 2048,
                "max_height": 2048,
                "supports_batch": True
            }
        }

class UserGenerationsResponse(BaseModel):
    """Response model for user's generated images"""
    images: List[GeneratedImage] = Field(..., description="List of generated images")
    total_count: int = Field(..., description="Total number of generations for the user")
    has_more: bool = Field(..., description="Whether there are more results available")
    
    class Config:
        schema_extra = {
            "example": {
                "images": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "prompt": "A beautiful sunset over mountains",
                        "model_name": "prunaai/z-image-turbo:7ea16386290ff5977c7812e66e462d7ec3954d8e007a8cd18ded3e7d41f5d7cf",
                        "provider": "replicate",
                        "status": "completed",
                        "signed_url": "https://storage.googleapis.com/...",
                        "thumbnail_signed_url": "https://storage.googleapis.com/...",
                        "width": 1024,
                        "height": 1024,
                        "file_size": 1048576,
                        "generation_time_ms": 15000,
                        "error_message": None,
                        "created_at": "2024-01-01T12:00:00Z",
                        "updated_at": "2024-01-01T12:00:30Z"
                    }
                ],
                "total_count": 1,
                "has_more": False
            }
        }

class ErrorResponse(BaseModel):
    """Standard error response model"""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    
    class Config:
        schema_extra = {
            "example": {
                "error": "generation_failed",
                "message": "Image generation failed.",
                "details": {}
            }
        }

class DeleteImageResponse(BaseModel):
    """Response model for image deletion"""
    success: bool = Field(..., description="Whether deletion was successful")
    message: str = Field(..., description="Status message")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "Image deleted successfully"
            }
        }
