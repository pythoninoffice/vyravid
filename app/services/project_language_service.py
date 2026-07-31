"""
Service for managing video project language data
After migration, this is the single source of truth for all project content
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
import logging
from datetime import datetime, timezone

from db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)


class ProjectLanguageService:
    """Service for accessing project language data"""

    def __init__(self, supabase_client: SupabaseClient = None):
        self.supabase_client = supabase_client or SupabaseClient()
        self.supabase = self.supabase_client.supabase

    async def get_primary_language(self, project_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get the primary language entry for a project

        Args:
            project_id: Project UUID

        Returns:
            Primary language data or None
        """
        try:
            result = self.supabase.table("video_project_languages")\
                .select("*")\
                .eq("project_id", str(project_id))\
                .eq("is_primary", True)\
                .execute()

            if result.data:
                return result.data[0]

            logger.warning(f"No primary language found for project {project_id}")
            return None

        except Exception as e:
            logger.error(f"Error getting primary language for project {project_id}: {str(e)}")
            return None

    async def get_language_by_code(
        self,
        project_id: UUID,
        language_code: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific language entry for a project

        Args:
            project_id: Project UUID
            language_code: Language code (e.g., 'en', 'zh')

        Returns:
            Language data or None
        """
        try:
            result = self.supabase.table("video_project_languages")\
                .select("*")\
                .eq("project_id", str(project_id))\
                .eq("language_code", language_code)\
                .execute()

            if result.data:
                return result.data[0]

            return None

        except Exception as e:
            logger.error(f"Error getting language {language_code} for project {project_id}: {str(e)}")
            return None

    async def get_all_languages(self, project_id: UUID) -> List[Dict[str, Any]]:
        """
        Get all language entries for a project

        Args:
            project_id: Project UUID

        Returns:
            List of language data, primary language first
        """
        try:
            result = self.supabase.table("video_project_languages")\
                .select("*")\
                .eq("project_id", str(project_id))\
                .order("is_primary", desc=True)\
                .order("created_at")\
                .execute()

            return result.data or []

        except Exception as e:
            logger.error(f"Error getting languages for project {project_id}: {str(e)}")
            return []

    async def get_story_content(
        self,
        project_id: UUID,
        language_code: Optional[str] = None
    ) -> Optional[str]:
        """
        Get story content for a project in a specific language

        Args:
            project_id: Project UUID
            language_code: Language code, or None for primary language

        Returns:
            Story content string or None
        """
        if language_code:
            lang_data = await self.get_language_by_code(project_id, language_code)
        else:
            lang_data = await self.get_primary_language(project_id)

        return lang_data.get("story_content") if lang_data else None

    async def get_audio_file_id(
        self,
        project_id: UUID,
        language_code: Optional[str] = None
    ) -> Optional[str]:
        """
        Get audio file ID for a project in a specific language

        Args:
            project_id: Project UUID
            language_code: Language code, or None for primary language

        Returns:
            Audio file ID or None
        """
        if language_code:
            lang_data = await self.get_language_by_code(project_id, language_code)
        else:
            lang_data = await self.get_primary_language(project_id)

        return lang_data.get("audio_file_id") if lang_data else None

    async def update_story_content(
        self,
        project_id: UUID,
        story_content: str,
        language_code: Optional[str] = None
    ) -> bool:
        """
        Update story content for a specific language

        Args:
            project_id: Project UUID
            story_content: New story content
            language_code: Language code, or None for primary language

        Returns:
            True if successful
        """
        try:
            if language_code:
                # Update specific language
                result = self.supabase.table("video_project_languages")\
                    .update({
                        "story_content": story_content,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    })\
                    .eq("project_id", str(project_id))\
                    .eq("language_code", language_code)\
                    .execute()
            else:
                # Update primary language
                result = self.supabase.table("video_project_languages")\
                    .update({
                        "story_content": story_content,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    })\
                    .eq("project_id", str(project_id))\
                    .eq("is_primary", True)\
                    .execute()

            return bool(result.data)

        except Exception as e:
            logger.error(f"Error updating story content for project {project_id}: {str(e)}")
            return False

    async def update_audio_file_id(
        self,
        project_id: UUID,
        audio_file_id: str,
        language_code: Optional[str] = None
    ) -> bool:
        """
        Update audio file ID for a specific language

        Args:
            project_id: Project UUID
            audio_file_id: New audio file ID
            language_code: Language code, or None for primary language

        Returns:
            True if successful
        """
        try:
            if language_code:
                # Update specific language
                result = self.supabase.table("video_project_languages")\
                    .update({
                        "audio_file_id": audio_file_id,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    })\
                    .eq("project_id", str(project_id))\
                    .eq("language_code", language_code)\
                    .execute()
            else:
                # Update primary language
                result = self.supabase.table("video_project_languages")\
                    .update({
                        "audio_file_id": audio_file_id,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    })\
                    .eq("project_id", str(project_id))\
                    .eq("is_primary", True)\
                    .execute()

            return bool(result.data)

        except Exception as e:
            logger.error(f"Error updating audio file ID for project {project_id}: {str(e)}")
            return False

    async def ensure_primary_language_exists(
        self,
        project_id: UUID,
        language_code: str = "en",
        language_name: str = "English",
        story_content: str = "",
        audio_file_id: Optional[str] = None
    ) -> bool:
        """
        Ensure a project has a primary language entry, create if missing

        Args:
            project_id: Project UUID
            language_code: Default language code
            language_name: Default language name
            story_content: Initial story content
            audio_file_id: Initial audio file ID

        Returns:
            True if primary language exists or was created
        """
        try:
            # Check if primary language exists
            existing = await self.get_primary_language(project_id)
            if existing:
                return True

            # Create primary language entry
            current_time = datetime.now(timezone.utc).isoformat()
            result = self.supabase.table("video_project_languages").insert({
                "project_id": str(project_id),
                "language_code": language_code,
                "language_name": language_name,
                "is_primary": True,
                "story_content": story_content,
                "audio_file_id": audio_file_id,
                "translation_status": "original",
                "created_at": current_time,
                "updated_at": current_time
            }).execute()

            if result.data:
                logger.info(f"Created primary language {language_code} for project {project_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error ensuring primary language for project {project_id}: {str(e)}")
            return False

    async def delete_language(
        self,
        project_id: UUID,
        language_code: str
    ) -> bool:
        """
        Delete a language entry (cannot delete primary language)

        Args:
            project_id: Project UUID
            language_code: Language code to delete

        Returns:
            True if successful
        """
        try:
            # Check if it's the primary language
            lang_data = await self.get_language_by_code(project_id, language_code)
            if not lang_data:
                return False

            if lang_data.get("is_primary"):
                logger.error(f"Cannot delete primary language {language_code} for project {project_id}")
                return False

            # Delete the language entry
            self.supabase.table("video_project_languages")\
                .delete()\
                .eq("project_id", str(project_id))\
                .eq("language_code", language_code)\
                .execute()

            logger.info(f"Deleted language {language_code} for project {project_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting language {language_code} for project {project_id}: {str(e)}")
            return False


# Singleton instance
_project_language_service: Optional[ProjectLanguageService] = None


def get_project_language_service(supabase_client: SupabaseClient = None) -> ProjectLanguageService:
    """Get singleton instance of ProjectLanguageService"""
    global _project_language_service
    if _project_language_service is None or supabase_client is not None:
        _project_language_service = ProjectLanguageService(supabase_client)
    return _project_language_service
