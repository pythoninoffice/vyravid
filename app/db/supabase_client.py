"""
Local Supabase-compatible client for database operations.
"""

from typing import List, Dict, Any, Optional
import logging

from local.db import get_local_db

logger = logging.getLogger(__name__)


class SupabaseClient:
    def __init__(self):
        """Initialize local database client"""
        self.supabase = get_local_db()

    async def insert_reddit_post(self, post_data: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.supabase.table("reddit_posts").select("*").eq("reddit_id", post_data["reddit_id"]).execute()
        if existing.data:
            return existing.data[0]
        result = self.supabase.table("reddit_posts").insert(post_data).execute()
        return result.data[0] if result.data else post_data

    async def insert_comments(self, comments_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not comments_data:
            return []
        result = self.supabase.table("comments").insert(comments_data).execute()
        return result.data or []

    async def get_reddit_post_by_reddit_id(self, reddit_id: str) -> Optional[Dict[str, Any]]:
        result = self.supabase.table("reddit_posts").select("*").eq("reddit_id", reddit_id).execute()
        return result.data[0] if result.data else None


# Module-level singleton expected by various endpoints
supabase_client = SupabaseClient()
