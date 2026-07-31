"""Local-mode Supabase client (SQLite-backed)."""

from typing import Optional, Union
import os

_supabase_client = None


def get_supabase_client(force_recreate: bool = False):
    """
    Return the local SQLite database client (Supabase-compatible API).
    """
    global _supabase_client

    if force_recreate:
        _supabase_client = None

    if _supabase_client is None:
        from local.db import get_local_db
        _supabase_client = get_local_db()
        print("Local SQLite database client ready")

    return _supabase_client


async def get_usage(user_id: str):
    """Local mode: no usage tracking."""
    return {"user_id": user_id, "usage": {}}
