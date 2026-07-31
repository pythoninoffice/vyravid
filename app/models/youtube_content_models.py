"""
Pydantic models for YouTube Shorts content stored in Supabase
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class YouTubeShortsContent(BaseModel):
    """YouTube Shorts content model for Supabase storage"""
    id: UUID
    project_id: UUID
    title: str = Field(default="", max_length=100, description="YouTube Shorts title")
    description: str = Field(default="", max_length=5000, description="YouTube Shorts description")
    tags: List[str] = Field(default=[], description="List of YouTube tags")
    tags_text: str = Field(default="", description="Comma-separated tags for editing")
    created_at: datetime
    updated_at: datetime

    @validator('tags_text', always=True)
    def sync_tags_text(cls, v, values):
        """Automatically sync tags_text with tags array"""
        if 'tags' in values and values['tags']:
            return ', '.join(values['tags'])
        return v or ""

    @validator('tags', always=True)
    def sync_tags_from_text(cls, v, values):
        """Sync tags array from tags_text if provided"""
        tags_text = values.get('tags_text', '')
        if tags_text and not v:
            return [tag.strip() for tag in tags_text.split(',') if tag.strip()]
        return v or []

    class Config:
        from_attributes = True

class YouTubeShortsContentCreate(BaseModel):
    """Model for creating YouTube Shorts content"""
    project_id: UUID
    title: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=5000)
    tags: List[str] = Field(default=[])
    tags_text: Optional[str] = Field(default=None)

    @validator('tags_text', always=True)
    def set_tags_text(cls, v, values):
        """Set tags_text from tags if not provided"""
        if v is None and 'tags' in values:
            return ', '.join(values['tags'])
        return v or ""

    @validator('tags', always=True)
    def validate_tags(cls, v, values):
        """Validate and sync tags with tags_text"""
        tags_text = values.get('tags_text', '')

        # If tags_text is provided, parse it
        if tags_text and not v:
            parsed_tags = [tag.strip() for tag in tags_text.split(',') if tag.strip()]
            return parsed_tags[:30]  # Limit to 30 tags

        # Limit to 30 tags
        return (v or [])[:30]

class YouTubeShortsContentUpdate(BaseModel):
    """Model for updating YouTube Shorts content"""
    title: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=5000)
    tags: Optional[List[str]] = None
    tags_text: Optional[str] = None

    @validator('tags', always=True)
    def validate_tags_update(cls, v, values):
        """Validate tags on update"""
        if v is not None:
            return v[:30]  # Limit to 30 tags
        return v

class YouTubeShortsContentResponse(BaseModel):
    """Response model for YouTube Shorts content with project info"""
    id: UUID
    project_id: UUID
    project_title: Optional[str] = None
    title: str
    description: str
    tags: List[str]
    tags_text: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True