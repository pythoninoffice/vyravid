"""
Public Images Models
Pydantic models for public image sharing functionality
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Literal
from datetime import datetime


class PublicImageMetadata(BaseModel):
    """Metadata for making an image public"""
    title: Optional[str] = Field(None, max_length=200, description="Public title for the image")
    description: Optional[str] = Field(None, max_length=1000, description="Public description for the image")
    tags: List[str] = Field(default_factory=list, max_items=10, description="Tags for categorization")

    @validator('tags')
    def validate_tags(cls, v):
        if v:
            # Clean and validate tags
            cleaned_tags = []
            for tag in v:
                if isinstance(tag, str) and tag.strip():
                    cleaned_tag = tag.strip().lower()
                    if len(cleaned_tag) <= 50 and cleaned_tag not in cleaned_tags:
                        cleaned_tags.append(cleaned_tag)
            return cleaned_tags[:10]  # Limit to 10 tags
        return []


class MakeImagePublicRequest(BaseModel):
    """Request to make an image public"""
    image_id: str = Field(..., description="ID of the user image to make public")
    title: Optional[str] = Field(None, max_length=200, description="Public title for the image")
    description: Optional[str] = Field(None, max_length=1000, description="Public description for the image")
    tags: List[str] = Field(default_factory=list, max_items=10, description="Tags for categorization")

    @validator('tags')
    def validate_tags(cls, v):
        if v:
            # Clean and validate tags
            cleaned_tags = []
            for tag in v:
                if isinstance(tag, str) and tag.strip():
                    cleaned_tag = tag.strip().lower()
                    if len(cleaned_tag) <= 50 and cleaned_tag not in cleaned_tags:
                        cleaned_tags.append(cleaned_tag)
            return cleaned_tags[:10]  # Limit to 10 tags
        return []


class PublicImage(BaseModel):
    """Public image with metadata"""
    id: str = Field(..., description="Public image ID")
    user_image_id: str = Field(..., description="Original generated image ID")  # Keep frontend field name for compatibility
    original_user_id: str = Field(..., description="ID of user who made it public")
    title: Optional[str] = Field(None, description="Public title")
    description: Optional[str] = Field(None, description="Public description")
    tags: List[str] = Field(default_factory=list, description="Tags")
    is_public: bool = Field(True, description="Whether image is public")
    view_count: int = Field(0, description="Number of views")
    copy_count: int = Field(0, description="Number of copies")
    created_at: datetime = Field(..., description="When made public")
    updated_at: datetime = Field(..., description="Last updated")

    # Extended data from user_images/generated_images join
    filename: Optional[str] = Field(None, description="Original filename")
    original_name: Optional[str] = Field(None, description="Original name")
    signed_url: Optional[str] = Field(None, description="Signed URL to image")
    thumbnail_signed_url: Optional[str] = Field(None, description="Signed URL to thumbnail")
    width: Optional[int] = Field(None, description="Image width")
    height: Optional[int] = Field(None, description="Image height")
    file_size: Optional[int] = Field(None, description="File size in bytes")
    original_creator_name: Optional[str] = Field(None, description="Name of original creator")
    
    # Generated image specific fields
    prompt: Optional[str] = Field(None, description="Generation prompt (for AI-generated images)")
    model_name: Optional[str] = Field(None, description="AI model used (for AI-generated images)")


class PublicImagesResponse(BaseModel):
    """Response for paginated public images"""
    images: List[PublicImage] = Field(..., description="List of public images")
    total: int = Field(..., description="Total number of public images")
    page: int = Field(..., description="Current page number")
    limit: int = Field(..., description="Items per page")
    has_more: bool = Field(..., description="Whether there are more pages")


class PublicImageFilters(BaseModel):
    """Filters for public images query"""
    tags: Optional[List[str]] = Field(None, description="Filter by tags")
    search: Optional[str] = Field(None, max_length=200, description="Search in title, description, filename")
    min_copy_count: Optional[int] = Field(None, ge=0, description="Minimum copy count")
    sort_by: Optional[Literal['created_at', 'view_count', 'copy_count']] = Field('created_at', description="Sort field")
    sort_order: Optional[Literal['asc', 'desc']] = Field('desc', description="Sort order")


class CopiedImage(BaseModel):
    """Response for copied image"""
    id: str = Field(..., description="New image ID")
    user_id: str = Field(..., description="User who copied the image")
    filename: str = Field(..., description="Filename")
    original_name: str = Field(..., description="Original name")
    gcs_signed_url: Optional[str] = Field(None, description="Signed URL to image")
    thumbnail_signed_url: Optional[str] = Field(None, description="Signed URL to thumbnail")
    width: Optional[int] = Field(None, description="Image width")
    height: Optional[int] = Field(None, description="Image height")
    file_size: Optional[int] = Field(None, description="File size in bytes")
    copied_from_public_id: str = Field(..., description="ID of public image copied from")
    created_at: datetime = Field(..., description="When copied")


class TagsResponse(BaseModel):
    """Response for available tags"""
    tags: List[str] = Field(..., description="List of available tags")


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: Optional[dict] = Field(None, description="Additional error details")