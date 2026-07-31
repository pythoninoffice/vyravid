from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from uuid import UUID
import logging

from auth import get_current_user
from repositories.video_project_repository import VideoProjectRepository
from db.supabase_client import SupabaseClient

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)

@router.get("/stats")
async def get_user_stats(current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Get dashboard statistics for the current user
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User statistics including videos created, processing time, storage used, and success rate
    """
    try:
        # Get user ID from authenticated user
        user_id_str = current_user.get('sub', current_user.get('id', 'unknown-user'))
        user_id = UUID(user_id_str)
        logger.info(f"Getting stats for user: {user_id}")
        
        # Get Supabase client
        supabase_client = SupabaseClient()
        if not supabase_client:
            raise HTTPException(status_code=500, detail="Database connection not available")
        
        # Get video project repository
        project_repo = VideoProjectRepository(supabase_client)
        
        # Get all projects for the user
        projects = await project_repo.get_by_user_id(user_id)
        
        # Calculate statistics
        total_videos = len(projects)
        completed_videos = len([p for p in projects if p.status == "completed"])
        failed_videos = len([p for p in projects if p.status == "failed"])
        processing_videos = len([p for p in projects if p.status == "processing"])
        
        # Calculate total processing time (sum of all video durations)
        total_processing_time = sum(p.duration or 0 for p in projects if p.status == "completed")
        
        # Calculate storage used (sum of all file sizes)
        storage_used = sum(p.file_size or 0 for p in projects)
        
        # Calculate success rate
        success_rate = 100.0
        if total_videos > 0:
            success_rate = (completed_videos / total_videos) * 100
        
        stats = {
            "videosCreated": total_videos,
            "totalProcessingTime": int(total_processing_time),  # in seconds
            "storageUsed": storage_used,  # in bytes
            "successRate": round(success_rate, 1)  # percentage
        }
        
        logger.info(f"Returning stats for user {user_id}: {stats}")
        return stats
        
    except Exception as e:
        logger.error(f"Error getting user stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting user stats: {str(e)}")