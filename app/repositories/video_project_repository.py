"""
Repository for video projects in Supabase
"""

from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta, timezone
import logging

from models.video_project_models import VideoProject, VideoProjectCreate, VideoProjectUpdate
from services.supabase import get_supabase_client

logger = logging.getLogger(__name__)

class VideoProjectRepository:
    """Repository for managing video projects in Supabase"""
    
    def __init__(self, supabase_client):
        self.supabase = supabase_client.supabase
        self.table_name = "video_projects"
    
    async def create(self, project_data: VideoProjectCreate) -> VideoProject:
        """Create a new video project"""
        try:
            # Convert to dict and handle serialization
            data = project_data.model_dump()

            # Convert UUID objects to strings, or remove if None
            if data.get('id'):
                data['id'] = str(data['id'])
            elif 'id' in data:
                # Remove id field if it's None to let Supabase auto-generate
                del data['id']

            if data.get('user_id'):
                data['user_id'] = str(data['user_id'])

            # Convert audio_file_id to string if it exists
            if data.get('audio_file_id'):
                data['audio_file_id'] = str(data['audio_file_id'])
            
            # Convert datetime objects to ISO strings
            if data.get('gcs_signed_url_expires_at'):
                data['gcs_signed_url_expires_at'] = data['gcs_signed_url_expires_at'].isoformat()
            
            logger.info(f"🗃️ Inserting video project data into Supabase: {data}")
            result = self.supabase.table(self.table_name).insert(data).execute()
            logger.info(f"🗃️ Supabase insert result: {result.data}")
            
            if result.data:
                return VideoProject(**result.data[0])
            else:
                raise Exception("Failed to create video project")
                
        except Exception as e:
            logger.error(f"Error creating video project: {str(e)}")
            raise
    
    async def get_by_id(self, project_id: UUID) -> Optional[VideoProject]:
        """Get a video project by ID"""
        try:
            result = self.supabase.table(self.table_name).select("*").eq("id", str(project_id)).execute()
            
            if result.data:
                return VideoProject(**result.data[0])
            return None
            
        except Exception as e:
            logger.error(f"Error getting video project {project_id}: {str(e)}")
            return None
    
    async def get_by_audio_file_id(self, audio_file_id: str) -> Optional[VideoProject]:
        """Get video project by audio file ID"""
        try:
            logger.info(f"🗃️ Fetching video project by audio_file_id: {audio_file_id}")
            result = self.supabase.table(self.table_name).select("*").eq("audio_file_id", audio_file_id).execute()
            
            if result.data and len(result.data) > 0:
                logger.info(f"🗃️ Found existing project for audio file: {result.data[0]['id']}")
                return VideoProject(**result.data[0])
            else:
                logger.info(f"🗃️ No existing project found for audio file: {audio_file_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting video project by audio_file_id: {str(e)}")
            return None
    
    async def get_by_user_id(self, user_id: UUID, limit: Optional[int] = None, status_filter: Optional[str] = None) -> List[VideoProject]:
        """Get all video projects for a user"""
        try:
            query = self.supabase.table(self.table_name).select("*").eq("user_id", str(user_id))
            
            # Apply status filter if provided
            if status_filter:
                query = query.eq("status", status_filter)
            
            # Apply limit if provided
            if limit:
                query = query.limit(limit)
            
            # Order by created_at descending (newest first)
            query = query.order("created_at", desc=True)
            
            result = query.execute()
            
            if result.data:
                return [VideoProject(**project) for project in result.data]
            return []
            
        except Exception as e:
            logger.error(f"Error getting video projects for user {user_id}: {str(e)}")
            return []
    
    async def update(self, project_id: UUID, update_data: VideoProjectUpdate) -> Optional[VideoProject]:
        """Update a video project"""
        try:
            # Convert to dict and remove None values
            data = {k: v for k, v in update_data.model_dump().items() if v is not None}
            
            # Convert datetime objects to ISO strings
            if data.get('completed_at'):
                data['completed_at'] = data['completed_at'].isoformat()
            if data.get('gcs_signed_url_expires_at'):
                data['gcs_signed_url_expires_at'] = data['gcs_signed_url_expires_at'].isoformat()
            
            result = self.supabase.table(self.table_name).update(data).eq("id", str(project_id)).execute()

            if result.data:
                return VideoProject(**result.data[0])
            else:
                logger.warning(f"⚠️ Update returned no data for project {project_id}. Project may not exist or RLS policy blocked the update.")
                return None
            
        except Exception as e:
            logger.error(f"Error updating video project {project_id}: {str(e)}")
            return None
    
    async def delete(self, project_id: UUID) -> bool:
        """Delete a video project"""
        try:
            result = self.supabase.table(self.table_name).delete().eq("id", str(project_id)).execute()
            return True
            
        except Exception as e:
            logger.error(f"Error deleting video project {project_id}: {str(e)}")
            return False
    
    async def refresh_signed_url(self, project_id: UUID, new_signed_url: str, expires_at: datetime) -> bool:
        """Update the signed URL for a project"""
        try:
            data = {
                'gcs_signed_url': new_signed_url,
                'gcs_signed_url_expires_at': expires_at.isoformat()
            }
            
            result = self.supabase.table(self.table_name).update(data).eq("id", str(project_id)).execute()
            return bool(result.data)
            
        except Exception as e:
            logger.error(f"Error refreshing signed URL for project {project_id}: {str(e)}")
            return False
    
    async def get_projects_with_expired_urls(self) -> List[VideoProject]:
        """Get projects with expired signed URLs that need refreshing"""
        try:
            now = datetime.now(timezone.utc).isoformat()
            
            result = self.supabase.table(self.table_name).select("*").lt("gcs_signed_url_expires_at", now).execute()
            
            if result.data:
                return [VideoProject(**project) for project in result.data]
            return []
            
        except Exception as e:
            logger.error(f"Error getting projects with expired URLs: {str(e)}")
            return []