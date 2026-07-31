"""Application settings for local Vyravid mode."""

import os
from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings

# Ensure Vyravid root is known
_REPO = Path(__file__).resolve().parents[1]
if not os.getenv("VYRAVID_ROOT"):
    os.environ["VYRAVID_ROOT"] = str(_REPO)


class Settings(BaseSettings):
    """Application settings — all cloud secrets optional for local use."""

    # Database (SQLite)
    database_url: str = Field(
        default=f"sqlite:///{_REPO / 'data' / 'db' / 'openvid.sqlite3'}",
        env="DATABASE_URL",
    )

    # JWT (unused locally)
    jwt_secret_key: str = Field(default="local-dev-secret", env="JWT_SECRET_KEY")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = Field(default=10080, env="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    jwt_refresh_token_expire_days: int = Field(default=30, env="JWT_REFRESH_TOKEN_EXPIRE_DAYS")

    # File Storage
    upload_dir: str = Field(default="uploads")
    max_file_size_mb: int = Field(default=500)

    # Supabase stubs (unused — local DB is used)
    supabase_url: str = Field(default="http://localhost/local", env="SUPABASE_URL")
    supabase_key: str = Field(default="local-key", env="SUPABASE_KEY")
    supabase_jwt_secret: str = Field(default="local-jwt-secret", env="SUPABASE_JWT_SECRET")
    supabase_jwt_expiry: int = Field(default=604800, env="SUPABASE_JWT_EXPIRY")

    # LLM / AI APIs (set in .env as needed)
    deepseek_api_key: str = Field(default="", env="DEEPSEEK_API_KEY")
    minimax_api_key: str = Field(default="", env="MINIMAX_API_KEY")
    minimax_group_id: str = Field(default="", env="MINIMAX_GROUP_ID")
    deepgram_api_key: str = Field(default="", env="DEEPGRAM_API_KEY")
    elevenlabs_api_key: str = Field(default="", env="ELEVENLABS_API_KEY")

    # Reddit (optional)
    reddit_client_id: str = Field(default="", env="REDDIT_CLIENT_ID")
    reddit_client_secret: str = Field(default="", env="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = Field(default="vyravid-local", env="REDDIT_USER_AGENT")

    # Local storage (GCS fields kept for compatibility)
    gcs_project_id: str = Field(default="local", env="GCS_PROJECT_ID")
    gcs_bucket_name: str = Field(default="local", env="GCS_BUCKET_NAME")
    gcs_service_account_key: str = Field(default="", env="GCS_SERVICE_ACCOUNT_KEY")
    gcs_make_public: bool = Field(default=True, env="GCS_MAKE_PUBLIC")
    gcs_base_url: str = Field(default="http://localhost:8000/media/", env="GCS_BASE_URL")

    # Stripe stubs (disabled)
    stripe_secret_key: str = Field(default="", env="STRIPE_SECRET_KEY")
    stripe_publishable_key: str = Field(default="", env="STRIPE_PUBLISHABLE_KEY")
    stripe_webhook_secret: str = Field(default="", env="STRIPE_WEBHOOK_SECRET")
    stripe_success_url: str = Field(default="http://localhost:5173/", env="STRIPE_SUCCESS_URL")
    stripe_cancel_url: str = Field(default="http://localhost:5173/", env="STRIPE_CANCEL_URL")

    # Video processor — embedded in this app at /vp (same process)
    cloud_video_processor_url: str = Field(
        default="http://localhost:8000/vp",
        env="CLOUD_VIDEO_PROCESSOR_URL",
    )
    use_cloud_processing: bool = Field(default=True, env="USE_CLOUD_PROCESSING")
    webhook_base_url: str = Field(default="http://localhost:8000", env="WEBHOOK_BASE_URL")
    google_application_credentials: str = Field(default="", env="GOOGLE_APPLICATION_CREDENTIALS")

    # Replicate / Google / Anthropic
    replicate_api_key: str = Field(default="", env="REPLICATE_API_KEY")
    replicate_poll_interval_seconds: float = Field(default=2.0, env="REPLICATE_POLL_INTERVAL")
    google_api_key: str = Field(default="", env="GOOGLE_API_KEY")
    GOOGLE_API_KEY: str = Field(default="", env="GOOGLE_API_KEY")
    google_vertex_api_key: str = Field(default="", env="GOOGLE_VERTEX_API_KEY")
    google_genai_use_vertexai: bool = Field(default=False, env="GOOGLE_GENAI_USE_VERTEXAI")
    anthropic_api_key: str = Field(default="", env="ANTHROPIC_API_KEY")

    # YouTube / TikTok optional
    youtube_client_id: str = Field(default="", env="YOUTUBE_CLIENT_ID")
    youtube_client_secret: str = Field(default="", env="YOUTUBE_CLIENT_SECRET")
    youtube_redirect_uri: str = Field(default="http://localhost:8000/api/youtube/auth/callback", env="YOUTUBE_REDIRECT_URI")
    youtube_api_service_name: str = Field(default="youtube", env="YOUTUBE_API_SERVICE_NAME")
    youtube_api_version: str = Field(default="v3", env="YOUTUBE_API_VERSION")
    youtube_scopes: str = Field(default="", env="YOUTUBE_SCOPES")
    tiktok_client_key: str = Field(default="", env="TIKTOK_CLIENT_KEY")
    tiktok_client_secret: str = Field(default="", env="TIKTOK_CLIENT_SECRET")
    tiktok_redirect_uri: str = Field(default="", env="TIKTOK_REDIRECT_URI")
    assemblyai_api_key: str = Field(default="", env="ASSEMBLYAI_API_KEY")

    frontend_url: str = Field(default="http://localhost:5173", env="FRONTEND_URL")
    ask_vyra_api_keys: str = Field(default="", env="ASK_VYRA_API_KEYS")

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
