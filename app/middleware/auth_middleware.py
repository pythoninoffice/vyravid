"""Local-mode auth middleware — always returns the fixed local user."""

from typing import Optional
from datetime import datetime, timezone
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from models.auth_models import UserProfile
from auth import LocalUserProfile, _local_profile

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> UserProfile:
    return _local_profile()


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[UserProfile]:
    return _local_profile()


def require_auth(user: UserProfile = Depends(get_current_user)) -> UserProfile:
    return user


def optional_auth(user: Optional[UserProfile] = Depends(get_current_user_optional)) -> Optional[UserProfile]:
    return user
