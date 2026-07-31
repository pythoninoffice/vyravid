"""
Pydantic models for image folder API endpoints
"""

from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
from uuid import UUID


class ImageFolder(BaseModel):
    """Model for an image folder"""
    id: str = Field(..., description="Unique folder ID")
    user_id: str = Field(..., description="ID of the user who owns this folder")
    name: str = Field(..., description="Display name of the folder")
    color: Optional[str] = Field(default="#6366f1", description="Hex color code for folder display")
    sort_order: int = Field(default=0, description="Custom sort order")
    image_count: Optional[int] = Field(default=0, description="Number of images in this folder")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "user-123",
                "name": "Portraits",
                "color": "#6366f1",
                "sort_order": 0,
                "image_count": 15,
                "created_at": "2024-01-01T12:00:00Z",
                "updated_at": "2024-01-01T12:00:00Z"
            }
        }


class CreateFolderRequest(BaseModel):
    """Request model for creating a folder"""
    name: str = Field(..., min_length=1, max_length=100, description="Folder name (1-100 characters)")
    color: Optional[str] = Field(default="#6366f1", description="Hex color code (e.g., #6366f1)")

    @validator('name')
    def validate_name(cls, v):
        """Validate folder name"""
        v = v.strip()

        if not v:
            raise ValueError("Folder name cannot be empty")

        if len(v) > 100:
            raise ValueError("Folder name cannot exceed 100 characters")

        # Check for reserved names (case-insensitive)
        reserved_names = ['all images', 'uncategorized']
        if v.lower() in reserved_names:
            raise ValueError(f"'{v}' is a reserved name and cannot be used")

        # Validate characters (alphanumeric, spaces, hyphens, underscores)
        import re
        if not re.match(r'^[a-zA-Z0-9\s\-_]+$', v):
            raise ValueError("Folder name can only contain letters, numbers, spaces, hyphens, and underscores")

        return v

    @validator('color')
    def validate_color(cls, v):
        """Validate color is a valid hex code"""
        if v is None:
            return "#6366f1"

        v = v.strip()
        if not v.startswith('#'):
            v = '#' + v

        # Validate hex color format
        import re
        if not re.match(r'^#[0-9A-Fa-f]{6}$', v):
            raise ValueError("Color must be a valid 6-digit hex code (e.g., #6366f1)")

        return v

    class Config:
        schema_extra = {
            "example": {
                "name": "Portraits",
                "color": "#6366f1"
            }
        }


class UpdateFolderRequest(BaseModel):
    """Request model for updating a folder"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="New folder name")
    color: Optional[str] = Field(None, description="New hex color code")
    sort_order: Optional[int] = Field(None, description="New sort order")

    @validator('name')
    def validate_name(cls, v):
        """Validate folder name if provided"""
        if v is None:
            return v

        v = v.strip()

        if not v:
            raise ValueError("Folder name cannot be empty")

        if len(v) > 100:
            raise ValueError("Folder name cannot exceed 100 characters")

        # Check for reserved names
        reserved_names = ['all images', 'uncategorized']
        if v.lower() in reserved_names:
            raise ValueError(f"'{v}' is a reserved name and cannot be used")

        # Validate characters
        import re
        if not re.match(r'^[a-zA-Z0-9\s\-_]+$', v):
            raise ValueError("Folder name can only contain letters, numbers, spaces, hyphens, and underscores")

        return v

    @validator('color')
    def validate_color(cls, v):
        """Validate color if provided"""
        if v is None:
            return v

        v = v.strip()
        if not v.startswith('#'):
            v = '#' + v

        import re
        if not re.match(r'^#[0-9A-Fa-f]{6}$', v):
            raise ValueError("Color must be a valid 6-digit hex code (e.g., #6366f1)")

        return v

    class Config:
        schema_extra = {
            "example": {
                "name": "Updated Portraits",
                "color": "#8b5cf6"
            }
        }


class MoveImageToFolderRequest(BaseModel):
    """Request model for moving an image to a folder"""
    folder_id: Optional[str] = Field(None, description="Folder ID to move image to (null to remove from folder)")

    class Config:
        schema_extra = {
            "example": {
                "folder_id": "123e4567-e89b-12d3-a456-426614174000"
            }
        }


class BulkMoveImagesRequest(BaseModel):
    """Request model for moving multiple images to a folder"""
    image_ids: list[str] = Field(..., min_length=1, description="List of image IDs to move")
    folder_id: Optional[str] = Field(None, description="Folder ID to move images to (null to remove from folder)")

    @validator('image_ids')
    def validate_image_ids(cls, v):
        """Validate image IDs list"""
        if not v:
            raise ValueError("image_ids cannot be empty")

        if len(v) > 100:
            raise ValueError("Cannot move more than 100 images at once")

        # Remove duplicates
        return list(set(v))

    class Config:
        schema_extra = {
            "example": {
                "image_ids": ["img-1", "img-2", "img-3"],
                "folder_id": "123e4567-e89b-12d3-a456-426614174000"
            }
        }


class FolderResponse(BaseModel):
    """Response model for folder operations"""
    folder: ImageFolder = Field(..., description="The folder data")

    class Config:
        schema_extra = {
            "example": {
                "folder": {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "user_id": "user-123",
                    "name": "Portraits",
                    "color": "#6366f1",
                    "sort_order": 0,
                    "image_count": 15,
                    "created_at": "2024-01-01T12:00:00Z",
                    "updated_at": "2024-01-01T12:00:00Z"
                }
            }
        }


class FoldersListResponse(BaseModel):
    """Response model for listing folders"""
    folders: list[ImageFolder] = Field(..., description="List of folders")
    total: int = Field(..., description="Total number of folders")

    class Config:
        schema_extra = {
            "example": {
                "folders": [
                    {
                        "id": "folder-1",
                        "user_id": "user-123",
                        "name": "Portraits",
                        "color": "#6366f1",
                        "sort_order": 0,
                        "image_count": 15,
                        "created_at": "2024-01-01T12:00:00Z",
                        "updated_at": "2024-01-01T12:00:00Z"
                    }
                ],
                "total": 1
            }
        }


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")

    class Config:
        schema_extra = {
            "example": {
                "error": "folder_not_found",
                "message": "Folder not found or access denied"
            }
        }
