"""Local-mode auth: always authenticated as the fixed local user."""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from models.auth_models import UserProfile
from local.constants import LOCAL_USER_ID, LOCAL_USER_EMAIL, LOCAL_USER_NAME

security = HTTPBearer(auto_error=False)


class LocalUserProfile(UserProfile):
    """UserProfile that also supports dict-style .get() used by some endpoints."""

    def get(self, key: str, default=None):
        return getattr(self, key, default)

    def __getitem__(self, key: str):
        return getattr(self, key)


def _local_profile() -> LocalUserProfile:
    return LocalUserProfile(
        id=LOCAL_USER_ID,
        email=LOCAL_USER_EMAIL,
        first_name=LOCAL_USER_NAME,
        last_name=None,
        type="local",
        has_watched_tutorial=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        email_confirmed_at=datetime.now(timezone.utc),
    )


def create_access_token(data: dict, expires_delta=None) -> str:
    return "local-token"


def decode_access_token(token: str) -> dict:
    return {"id": LOCAL_USER_ID, "email": LOCAL_USER_EMAIL}


async def fetch_supabase_jwk() -> Dict[str, Any]:
    return {}


async def validate_supabase_token(token: str) -> Dict[str, Any]:
    return {"id": LOCAL_USER_ID, "email": LOCAL_USER_EMAIL}


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> UserProfile:
    return _local_profile()


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[UserProfile]:
    return _local_profile()
