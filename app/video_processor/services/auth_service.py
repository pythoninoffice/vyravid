"""Local processor auth — accept any token."""

from typing import Any, Dict, Optional


class AuthenticationError(Exception):
    pass


async def validate_service_account(token: str = None) -> Dict[str, Any]:
    """Always accept tokens in local mode."""
    return {
        "sub": "local",
        "email": "local@openvid.local",
        "valid": True,
    }


def get_service_account_credentials():
    return None


def validate_api_key(api_key: Optional[str] = None) -> bool:
    return True


def verify_token(token: Optional[str] = None) -> dict:
    return {"sub": "local", "valid": True}
