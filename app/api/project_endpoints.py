"""
API endpoints for project management, drafts, and persistence
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, timezone
import logging
import json

from models.auth_models import UserProfile
from middleware.auth_middleware import get_current_user
from repositories.video_project_repository import VideoProjectRepository
from db.supabase_client import SupabaseClient

router = APIRouter(prefix="/api/projects", tags=["projects"])
logger = logging.getLogger(__name__)

# Pydantic models
class ProjectDraftData(BaseModel):
    """Project draft data model"""
    editableContent: str
    generatedScenes: List[Dict[str, Any]] = []
    audioSettings: Dict[str, Any] = {}
    videoSettings: Dict[str, Any] = {}
    captionSettings: Dict[str, Any] = {}
    musicSettings: Dict[str, Any] = {}
    imageStyles: Dict[str, Any] = {}
    timelineData: Optional[Dict[str, Any]] = None
    generatedAudioId: Optional[str] = None
    generatedAudioUrl: Optional[str] = None
    generatedAudioDuration: Optional[float] = None
    lastSavedAt: str
    creationStep: str = 'content'
    currentLanguage: Optional[str] = None  # Current language being edited

class SaveProjectDraftRequest(BaseModel):
    """Request model for saving project draft"""
    projectId: Optional[str] = None
    title: str
    draftData: ProjectDraftData

class SaveProjectDraftResponse(BaseModel):
    """Response model for saving project draft"""
    projectId: str
    message: str
    lastSavedAt: str

class LoadProjectResponse(BaseModel):
    """Response model for loading project"""
    project: Dict[str, Any]

@router.post("/draft", response_model=SaveProjectDraftResponse)
async def save_project_draft(
    request: SaveProjectDraftRequest,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Save or create a project draft

    Args:
        request: Project draft data
        current_user: Current authenticated user

    Returns:
        Project ID and save confirmation
    """
    try:
        logger.info(f"Saving project draft: {request.title}")

        supabase_client = SupabaseClient()
        supabase = supabase_client.supabase

        # Convert draft data to JSON
        draft_data_json = request.draftData.dict()

        current_time = datetime.now(timezone.utc).isoformat()

        if request.projectId:
            # Update existing project
            logger.info(f"Updating existing project: {request.projectId}")

            # Verify user owns this project
            project_result = supabase.table("video_projects").select("*").eq("id", request.projectId).eq("user_id", str(current_user.id)).execute()

            if not project_result.data:
                raise HTTPException(status_code=404, detail="Project not found or access denied")

            # Update the project
            update_data = {
                "title": request.title,
                "draft_data": draft_data_json,
                "updated_at": current_time,
                "status": "draft"
            }

            supabase.table("video_projects").update(update_data).eq("id", request.projectId).execute()
            project_id = request.projectId

            # Also update the current language's script content if language is specified
            logger.info(f'11111111111111111111111111111111... {request.draftData.currentLanguage}')
            if request.draftData.currentLanguage:
                try:
                    # Check if language entry exists
                    lang_result = supabase.table("video_project_languages").select("*").eq("project_id", request.projectId).eq("language_code", request.draftData.currentLanguage).execute()

                    if lang_result.data:
                        # Update existing language entry
                        supabase.table("video_project_languages").update({
                            "script_content": request.draftData.editableContent,
                            "translation_status": "manual" if lang_result.data[0].get("translation_status") == "auto" else lang_result.data[0].get("translation_status"),
                            "updated_at": current_time
                        }).eq("project_id", request.projectId).eq("language_code", request.draftData.currentLanguage).execute()

                        logger.info(f"Updated language {request.draftData.currentLanguage} content for project {request.projectId}")
                except Exception as e:
                    logger.error(f"Error updating language content: {str(e)}")
                    # Don't fail the whole save if language update fails

        else:
            # Create new project
            logger.info(f"Creating new project: {request.title}")

            project_data = {
                "title": request.title,
                "user_id": str(current_user.id),
                "status": "draft",
                "draft_data": draft_data_json,
                "created_at": current_time,
                "updated_at": current_time,
                "duration": 0,
                "primary_language": "en"  # Default to English
            }

            result = supabase.table("video_projects").insert(project_data).execute()

            if not result.data:
                raise HTTPException(status_code=500, detail="Failed to create project")

            project_id = result.data[0]["id"]

            # Create initial primary language entry if there's content
            logger.info(f'22222222222222222222222222222222... {request}')
            if request.draftData.editableContent:
                try:
                    initial_language_data = {
                        "project_id": project_id,
                        "language_code": "en",
                        "language_name": "English",
                        "is_primary": True,
                        "script_content": request.draftData.editableContent,
                        "translation_status": "original",
                        "created_at": current_time,
                        "updated_at": current_time
                    }

                    supabase.table("video_project_languages").insert(initial_language_data).execute()
                    logger.info(f"Created initial English language entry for new project {project_id}")
                except Exception as e:
                    logger.error(f"Error creating initial language entry: {str(e)}")
                    # Don't fail project creation if language entry fails

        logger.info(f"Successfully saved project draft: {project_id}")

        return SaveProjectDraftResponse(
            projectId=project_id,
            message="Project draft saved successfully",
            lastSavedAt=current_time
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving project draft: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error saving project draft: {str(e)}")

@router.get("/{project_id}", response_model=LoadProjectResponse)
async def load_project(
    project_id: str,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Load a project by ID

    Args:
        project_id: The project ID
        current_user: Current authenticated user

    Returns:
        Complete project data
    """
    try:
        logger.info(f"Loading project: {project_id}")

        supabase_client = SupabaseClient()
        supabase = supabase_client.supabase

        # Get project data
        project_result = supabase.table("video_projects").select("*").eq("id", project_id).eq("user_id", str(current_user.id)).execute()

        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found or access denied")

        project = project_result.data[0]

        # Debug: Log project structure
        logger.info(f"Project {project_id} - Keys: {list(project.keys())}")

        # Generate audio URL if audio_file_id exists
        # Note: audio_file_id typically equals project_id, and audio is stored directly in GCS
        if project.get('audio_file_id'):
            try:
                logger.info(f"Project {project_id} has audio_file_id: {project['audio_file_id']}, generating audio URL...")

                # Audio files are stored in GCS with path: audio/{user_id}/{audio_file_id}.wav
                user_id = project.get('user_id')
                audio_gcs_path = f"audio/{user_id}/{project['audio_file_id']}.wav"

                from services.gcs_service import GCSService
                gcs_service = GCSService()

                if gcs_service.is_available():
                    audio_signed_url = await gcs_service.generate_signed_url(audio_gcs_path, expiration_hours=24)

                    if audio_signed_url:
                        # Add audio URL to project data
                        project['audio_url'] = audio_signed_url
                        logger.info(f"✅ Audio URL generated for project {project_id}")
                    else:
                        logger.warning(f"Failed to generate signed URL for audio GCS path: {audio_gcs_path}")
                else:
                    logger.warning(f"GCS service not available")

            except Exception as e:
                logger.error(f"Error generating audio URL for project {project_id}: {str(e)}")
                # Don't fail the entire request if audio generation fails
                pass

        # Check if main video signed URL needs refreshing before returning
        logger.info(f"Project {project_id} - gcs_path: {project.get('gcs_path')}, gcs_signed_url exists: {bool(project.get('gcs_signed_url'))}")
        if project.get('gcs_path') and project.get('gcs_signed_url'):
            logger.info(f"Project {project_id} - Checking URL expiration...")
            try:
                from services.gcs_service import GCSService
                from repositories.video_project_repository import VideoProjectRepository
                from datetime import datetime

                gcs_service = GCSService()
                if gcs_service.is_available():
                    # Parse the expiration date from the project data
                    expires_at_str = project.get('gcs_signed_url_expires_at')
                    logger.info(f"Project {project_id} - expires_at_str: {expires_at_str}")
                    expires_at = None
                    if expires_at_str:
                        try:
                            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                            logger.info(f"Project {project_id} - parsed expires_at: {expires_at}")
                        except Exception as parse_error:
                            logger.warning(f"Project {project_id} - Failed to parse expiration date: {parse_error}")

                    # Check if the video URL is expired or expiring soon
                    is_expired = gcs_service.is_url_expired_or_expiring_soon(expires_at, buffer_hours=1)
                    logger.info(f"Project {project_id} - URL expired/expiring? {is_expired}")
                    if is_expired:
                        logger.info(f"Video URL expired for project {project_id}, refreshing...")

                        # Generate new signed URL
                        new_signed_url = await gcs_service.generate_signed_url(project['gcs_path'], 24)
                        if new_signed_url:
                            expires_at = gcs_service.get_url_expiry_time(24)

                            # Update the database
                            project_repo = VideoProjectRepository(supabase_client)
                            from uuid import UUID
                            await project_repo.refresh_signed_url(UUID(project_id), new_signed_url, expires_at)

                            # Update the response data
                            project['gcs_signed_url'] = new_signed_url
                            project['gcs_signed_url_expires_at'] = expires_at.isoformat()

                            logger.info(f"Successfully refreshed video URL for project {project_id}")
                        else:
                            logger.error(f"Failed to generate new signed URL for project {project_id}")
            except Exception as e:
                logger.warning(f"Error refreshing video URL for project {project_id}: {str(e)}")

        logger.info(f"Successfully loaded project: {project_id}")

        return LoadProjectResponse(project=project)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading project: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error loading project: {str(e)}")

# @router.get("/{project_id}/timeline")
# async def get_project_timeline(
#     project_id: str,
#     current_user: UserProfile = Depends(get_current_user)
# ) -> Dict[str, Any]:
#     """
#     Get timeline data for a project

#     Args:
#         project_id: The video project ID
#         current_user: Current authenticated user

#     Returns:
#         Timeline segments with image data and timing information
#     """
#     try:
#         logger.info(f"Getting timeline for project: {project_id}")

#         # Verify user owns this project
#         supabase_client = SupabaseClient()
#         supabase = supabase_client.supabase

#         project_result = supabase.table("video_projects").select("*").eq("id", project_id).eq("user_id", str(current_user.id)).execute()

#         if not project_result.data:
#             raise HTTPException(status_code=404, detail="Project not found or access denied")

#         logger.info('kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk')
#         # Get timeline segments directly from video_project_backgrounds
#         timeline_result = supabase.table("video_project_backgrounds").select("""
#             segment_id,
#             project_id,
#             image_id,
#             sort_order,
#             start_time,
#             end_time,
#             duration,
#             effects,
#             transition_settings,
#             image_url,
#             image_width,
#             image_height,
#             file_size,
#             is_user_uploaded,
#             created_at,
#             last_updated_at,
#             camera_movement
#         """).eq("project_id", project_id).eq("background_type", "image_timeline").order("sort_order").execute()

#         logger.info(f"📊 Timeline query result for project {project_id}: {len(timeline_result.data) if timeline_result.data else 0} segments found")
#         if timeline_result.data:
#             for i, segment in enumerate(timeline_result.data):
#                 logger.info(f"🎬 Segment {i}: image_id={segment.get('image_id')}, start={segment.get('start_time')}, end={segment.get('end_time')}")
#         else:
#             logger.warning(f"⚠️  No timeline segments found in database for project {project_id}")

#         segments = []
#         total_duration = 0

#         if timeline_result.data:
#             for segment_data in timeline_result.data:
#                 # Get image info if image_id exists
#                 image_info = {}
#                 if segment_data.get('image_id'):
#                     # Try to get image data from user_images table
#                     image_result = supabase.table("user_images").select("""
#                         id,
#                         filename,
#                         original_name,
#                         signed_url,
#                         thumbnail_signed_url,
#                         gcs_path,
#                         thumbnail_gcs_path,
#                         width,
#                         height,
#                         file_size
#                     """).eq("id", segment_data['image_id']).execute()

#                     if image_result.data:
#                         img = image_result.data[0]

#                         # Refresh signed URLs if they exist
#                         signed_url = img.get('signed_url')
#                         thumbnail_signed_url = img.get('thumbnail_signed_url')

#                         # Check if we need to refresh URLs (if gcs_path exists)
#                         if img.get('gcs_path'):
#                             try:
#                                 from services.gcs_service import GCSService
#                                 gcs_service = GCSService()

#                                 # Refresh main signed URL
#                                 signed_url = await gcs_service.generate_signed_url(img.get('gcs_path'))

#                                 # Refresh thumbnail URL if thumbnail_gcs_path exists
#                                 if img.get('thumbnail_gcs_path'):
#                                     thumbnail_signed_url = await gcs_service.generate_signed_url(img.get('thumbnail_gcs_path'))

#                                 logger.info(f"Refreshed URLs for image {img.get('id')}")
#                             except Exception as e:
#                                 logger.warning(f"Failed to refresh URLs for image {img.get('id')}: {str(e)}")
#                                 # Fall back to existing URLs

#                         image_info = {
#                             "filename": img.get('filename'),
#                             "original_name": img.get('original_name'),
#                             "signed_url": signed_url,
#                             "thumbnail_signed_url": thumbnail_signed_url,
#                             "width": img.get('width'),
#                             "height": img.get('height')
#                         }

#                 # Extract transition settings from JSONB
#                 transition_settings = segment_data.get('transition_settings', {})
#                 if isinstance(transition_settings, dict):
#                     transition_type = transition_settings.get('type', 'crossfade')
#                     transition_duration = transition_settings.get('duration', 0.5)
#                 else:
#                     transition_type = 'crossfade'
#                     transition_duration = 0.5

#                 # Build segment object
#                 segment = {
#                     "id": segment_data.get('segment_id'),
#                     "image_id": segment_data.get('image_id'),
#                     "start_time": segment_data.get('start_time', 0),
#                     "end_time": segment_data.get('end_time', 0),
#                     "transition_type": transition_type,
#                     "transition_duration": transition_duration,
#                     "sort_order": segment_data.get('sort_order', 0),
#                     "camera_movement": segment_data.get('camera_movement', 'static'),
#                     "image_info": image_info
#                 }

#                 segments.append(segment)
#                 total_duration = max(total_duration, segment_data.get('end_time', 0))

#         logger.info(f"Found {len(segments)} timeline segments for project {project_id}")

#         return {
#             "video_project_id": project_id,
#             "segments": segments,
#             "segments_count": len(segments),
#             "total_duration": total_duration
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error getting project timeline: {str(e)}")
#         import traceback
#         logger.error(f"Full traceback: {traceback.format_exc()}")
#         raise HTTPException(status_code=500, detail=f"Error retrieving timeline: {str(e)}")

class SaveTimelineRequest(BaseModel):
    """Request model for saving timeline segments"""
    segments: List[Dict[str, Any]]

@router.post("/{project_id}/timeline")
async def save_project_timeline(
    project_id: str,
    request: SaveTimelineRequest,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Save timeline segments for a project with proper image ID associations

    Args:
        project_id: The video project ID
        request: Timeline segments data
        current_user: Current authenticated user

    Returns:
        Save confirmation with segment count
    """
    try:
        logger.info(f"Saving timeline for project: {project_id}")
        logger.info(f"Segments to save: {len(request.segments)}")

        supabase_client = SupabaseClient()
        supabase = supabase_client.supabase

        # Verify user owns this project
        project_result = supabase.table("video_projects").select("*").eq("id", project_id).eq("user_id", str(current_user.id)).execute()

        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found or access denied")

        # Clear existing timeline segments for this project
        logger.info(f"Clearing existing timeline segments for project {project_id}")
        supabase.table("video_project_backgrounds").delete().eq("project_id", project_id).eq("background_type", "image_timeline").execute()

        # Insert new timeline segments
        segments_inserted = 0
        total_duration = 0

        for segment_data in request.segments:
            try:
                # Extract segment data with proper image_id
                segment_record = {
                    "project_id": project_id,
                    "background_type": "image_timeline",
                    "image_id": segment_data.get("image_id"),
                    "sort_order": segment_data.get("sort_order", 0),
                    "start_time": segment_data.get("start_time", 0),
                    "end_time": segment_data.get("end_time", 0),
                    "transition_settings": {
                        "type": segment_data.get("transition_type", "fade"),
                        "duration": segment_data.get("transition_duration", 0.5),
                        "easing": "ease_in_out"
                    },
                    "effects": {
                        "zoom": {"enabled": False, "start_scale": 1.0, "end_scale": 1.0},
                        "pan": {"enabled": False, "start_position": {"x": 0, "y": 0}, "end_position": {"x": 0, "y": 0}},
                        "fade": {"fade_in_duration": 0, "fade_out_duration": 0},
                        "filters": {"brightness": 0, "contrast": 0, "saturation": 0, "blur": 0}
                    }
                }

                logger.info(f"Inserting segment {segments_inserted}: image_id={segment_record['image_id']}, start={segment_record['start_time']}, end={segment_record['end_time']}")

                # Insert the segment
                result = supabase.table("video_project_backgrounds").insert(segment_record).execute()

                if result.data:
                    segments_inserted += 1
                    total_duration = max(total_duration, segment_record["end_time"])
                    logger.info(f"✅ Successfully inserted segment {segments_inserted}")
                else:
                    logger.warning(f"⚠️  Failed to insert segment {segments_inserted}")

            except Exception as segment_error:
                logger.error(f"Error inserting segment {segments_inserted}: {str(segment_error)}")
                continue

        logger.info(f"Successfully saved {segments_inserted} timeline segments for project {project_id}")

        return {
            "message": f"Timeline saved successfully with {segments_inserted} segments",
            "project_id": project_id,
            "segments_count": segments_inserted,
            "total_duration": total_duration
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving project timeline: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error saving timeline: {str(e)}")