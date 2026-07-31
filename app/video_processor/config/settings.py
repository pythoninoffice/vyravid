"""
Configuration settings for Cloud Video Processor
"""

import os
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # Service configuration
    service_name: str = "cloud-video-processor"
    environment: str = "production"
    env: str = "production"  # Alternative name for environment
    debug: bool = False
    
    # Database (Supabase)
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_jwt_secret: str = ""
    
    # Google Cloud Storage
    gcs_project_id: str = ""
    gcs_bucket_name: str = ""
    gcs_service_account_key: str = ""  # JSON key file (for local development)
    gcs_signing_service_account_email: str = ""  # Service account email for signed URL impersonation (recommended)
    gcs_make_public: bool = False
    
    # Template video system
    template_videos_bucket: str = "cloud-video-templates"
    template_videos_prefix: str = "background_videos/"
    
    # Transcription APIs
    deepgram_api_key: str = ""
    assemblyai_api_key: str = Field(default="", alias="ASSEMBLYAI_API_KEY")
    gemini_api_key: str = Field(default="", alias="GOOGLE_GEMINI_API_KEY")
    
    # Processing limits
    max_file_size_mb: int = 1000  # 1GB default
    max_processing_time_minutes: int = 55  # Cloud Run timeout
    
    # Temporary storage
    temp_dir: str = "/tmp/video_processing"
    
    # Cloud Run specific
    port: int = 8080
    
    # Security
    cloud_video_processor_api_key: str = ""
    
    model_config = {
        "env_file": ".env",
        "env_prefix": "",
        "case_sensitive": False,
        "extra": "ignore"  # Ignore extra fields
    }


@lru_cache()
def get_settings() -> Settings:
    """Get application settings as a singleton"""
    return Settings()