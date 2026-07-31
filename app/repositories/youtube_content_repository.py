"""
Repository for YouTube Shorts content operations with Supabase
"""

import logging
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from services.supabase import get_supabase_client
from models.youtube_content_models import (
    YouTubeShortsContent,
    YouTubeShortsContentCreate,
    YouTubeShortsContentUpdate,
    YouTubeShortsContentResponse
)

logger = logging.getLogger(__name__)

class YouTubeContentRepository:
    """Repository for YouTube Shorts content CRUD operations"""

    def __init__(self, supabase_client: get_supabase_client):
        self.supabase = get_supabase_client()
        self.table_name = "youtube_shorts_content"

    async def create(self, youtube_content: YouTubeShortsContentCreate) -> YouTubeShortsContent:
        """
        Create new YouTube Shorts content for a project

        Args:
            youtube_content: YouTube content data to create

        Returns:
            Created YouTube content

        Raises:
            Exception: If creation fails
        """
        try:
            # Prepare data for insertion
            insert_data = {
                "project_id": str(youtube_content.project_id),
                "title": youtube_content.title,
                "description": youtube_content.description,
                "tags": youtube_content.tags,
                "tags_text": youtube_content.tags_text,
            }

            logger.info(f"Creating YouTube content for project {youtube_content.project_id}")
            logger.debug(f"Insert data: {insert_data}")

            # Insert into Supabase
            result = self.supabase.table(self.table_name).insert(insert_data).execute()

            if not result.data:
                raise Exception("Failed to create YouTube content: No data returned")

            created_content = result.data[0]
            logger.info(f"✅ YouTube content created with ID: {created_content['id']}")

            return YouTubeShortsContent(**created_content)

        except Exception as e:
            logger.error(f"❌ Error creating YouTube content: {str(e)}")
            raise Exception(f"Failed to create YouTube content: {str(e)}")

    async def get_by_project_id(self, project_id: UUID) -> Optional[YouTubeShortsContent]:
        """
        Get YouTube Shorts content by project ID

        Args:
            project_id: Project UUID

        Returns:
            YouTube content if found, None otherwise
        """
        try:
            logger.info(f"Fetching YouTube content for project {project_id}")

            result = self.supabase.table(self.table_name)\
                .select("*")\
                .eq("project_id", str(project_id))\
                .execute()

            if not result.data:
                logger.info(f"No YouTube content found for project {project_id}")
                return None

            content_data = result.data[0]
            logger.info(f"✅ Found YouTube content: {content_data['id']}")

            return YouTubeShortsContent(**content_data)

        except Exception as e:
            logger.error(f"❌ Error fetching YouTube content for project {project_id}: {str(e)}")
            return None

    async def update(self, project_id: UUID, update_data: YouTubeShortsContentUpdate) -> Optional[YouTubeShortsContent]:
        """
        Update YouTube Shorts content for a project

        Args:
            project_id: Project UUID
            update_data: Data to update

        Returns:
            Updated YouTube content if found, None otherwise
        """
        try:
            # Prepare update data (exclude None values)
            update_dict = {}
            for field, value in update_data.dict(exclude_unset=True).items():
                if value is not None:
                    update_dict[field] = value

            if not update_dict:
                logger.warning(f"No data to update for project {project_id}")
                return await self.get_by_project_id(project_id)

            # Sync tags and tags_text if one is provided
            if 'tags' in update_dict and 'tags_text' not in update_dict:
                update_dict['tags_text'] = ', '.join(update_dict['tags'])
            elif 'tags_text' in update_dict and 'tags' not in update_dict:
                tags = [tag.strip() for tag in update_dict['tags_text'].split(',') if tag.strip()]
                update_dict['tags'] = tags[:30]  # Limit to 30 tags

            logger.info(f"Updating YouTube content for project {project_id}")
            logger.debug(f"Update data: {update_dict}")

            result = self.supabase.table(self.table_name)\
                .update(update_dict)\
                .eq("project_id", str(project_id))\
                .execute()

            if not result.data:
                logger.warning(f"No YouTube content found to update for project {project_id}")
                return None

            updated_content = result.data[0]
            logger.info(f"✅ YouTube content updated for project {project_id}")

            return YouTubeShortsContent(**updated_content)

        except Exception as e:
            logger.error(f"❌ Error updating YouTube content for project {project_id}: {str(e)}")
            raise Exception(f"Failed to update YouTube content: {str(e)}")

    async def upsert(self, youtube_content: YouTubeShortsContentCreate) -> YouTubeShortsContent:
        """
        Create or update YouTube Shorts content for a project

        Args:
            youtube_content: YouTube content data

        Returns:
            Created or updated YouTube content
        """
        try:
            # Check if content already exists
            existing = await self.get_by_project_id(youtube_content.project_id)

            if existing:
                # Update existing content
                update_data = YouTubeShortsContentUpdate(
                    title=youtube_content.title,
                    description=youtube_content.description,
                    tags=youtube_content.tags,
                    tags_text=youtube_content.tags_text
                )
                result = await self.update(youtube_content.project_id, update_data)
                if result:
                    return result
                else:
                    raise Exception("Failed to update existing YouTube content")
            else:
                # Create new content
                return await self.create(youtube_content)

        except Exception as e:
            logger.error(f"❌ Error upserting YouTube content: {str(e)}")
            raise

    async def delete_by_project_id(self, project_id: UUID) -> bool:
        """
        Delete YouTube Shorts content by project ID

        Args:
            project_id: Project UUID

        Returns:
            True if deleted, False if not found
        """
        try:
            logger.info(f"Deleting YouTube content for project {project_id}")

            result = self.supabase.table(self.table_name)\
                .delete()\
                .eq("project_id", str(project_id))\
                .execute()

            if result.data:
                logger.info(f"✅ YouTube content deleted for project {project_id}")
                return True
            else:
                logger.info(f"No YouTube content found to delete for project {project_id}")
                return False

        except Exception as e:
            logger.error(f"❌ Error deleting YouTube content for project {project_id}: {str(e)}")
            return False

    async def get_by_user_id(self, user_id: UUID, limit: int = 50) -> List[YouTubeShortsContentResponse]:
        """
        Get all YouTube Shorts content for a user (with project info)

        Args:
            user_id: User UUID
            limit: Maximum number of records to return

        Returns:
            List of YouTube content with project info
        """
        try:
            logger.info(f"Fetching YouTube content for user {user_id}")

            # Join with video_projects table to get project info
            result = self.supabase.table(self.table_name)\
                .select("""
                    *,
                    video_projects!inner(title)
                """)\
                .eq("video_projects.user_id", str(user_id))\
                .order("created_at", desc=True)\
                .limit(limit)\
                .execute()

            if not result.data:
                logger.info(f"No YouTube content found for user {user_id}")
                return []

            content_list = []
            for item in result.data:
                # Extract project title from join
                project_title = item.get('video_projects', {}).get('title') if item.get('video_projects') else None

                # Remove the join data from the main object
                clean_item = {k: v for k, v in item.items() if k != 'video_projects'}
                clean_item['project_title'] = project_title

                content_list.append(YouTubeShortsContentResponse(**clean_item))

            logger.info(f"✅ Found {len(content_list)} YouTube content records for user {user_id}")
            return content_list

        except Exception as e:
            logger.error(f"❌ Error fetching YouTube content for user {user_id}: {str(e)}")
            return []