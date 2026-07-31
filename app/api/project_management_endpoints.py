"""
API endpoints for video project management and editing
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
import logging
import os

from models.auth_models import UserProfile
from middleware.auth_middleware import get_current_user
from services.project_assets_service import get_project_assets_service
from services.project_language_service import get_project_language_service
from repositories.video_project_repository import VideoProjectRepository
from db.supabase_client import SupabaseClient
from services.gcs_service import GCSService
from config import get_settings
from dotenv import load_dotenv

router = APIRouter(prefix="/api/video/projects", tags=["project-management"])
logger = logging.getLogger(__name__)

load_dotenv()
# Configuration
settings = get_settings()
GCS_BUCKET_NAME = settings.gcs_bucket_name
GCS_BASE_URL = settings.gcs_base_url



# Test endpoint to verify router is working
@router.get("/test")
async def test_endpoint():
    """Test endpoint to verify router is working"""
    return {"message": "Project management router is working", "timestamp": datetime.now().isoformat()}

# Test endpoint with project ID but no auth
@router.get("/test/{project_id}")
async def test_project_endpoint(project_id: str):
    """Test endpoint to verify project routing works"""
    return {"message": f"Project routing works for {project_id}", "timestamp": datetime.now().isoformat()}

# Test project details without auth to debug
@router.get("/debug/{project_id}/details")
async def debug_project_details(project_id: str):
    """Debug endpoint to test project details without auth"""
    try:
        logger.info(f"Debug: Getting project details for project_id: {project_id}")

        # Get project details without auth check
        assets_service = get_project_assets_service()
        project_details = await assets_service.get_project_details(UUID(project_id))

        if not project_details:
            logger.info(f"Debug: No assets found for project {project_id}")
            # Try to get basic project info from video_projects table
            supabase_client = SupabaseClient()
            project_result = supabase_client.supabase.table("video_projects").select("*").eq("id", project_id).execute()

            if not project_result.data:
                return {"error": "Project not found"}

            project = project_result.data[0]
            return {
                "message": "Basic project found (no assets)",
                "project": project,
                "assets": {},
                "backgrounds": [],
                "processing_settings": {},
                "edit_history": []
            }

        logger.info(f"Debug: Successfully retrieved project details for {project_id}")
        return {
            "message": "Full project details found",
            "data": project_details
        }

    except Exception as e:
        logger.error(f"Debug: Error getting project details: {str(e)}")
        import traceback
        logger.error(f"Debug: Full traceback: {traceback.format_exc()}")
        return {"error": str(e), "traceback": traceback.format_exc()}

# Pydantic models for request/response
class ProjectDetailsResponse(BaseModel):
    """Complete project details response"""
    project: Dict[str, Any]
    assets: Dict[str, Any]
    backgrounds: List[Dict[str, Any]]
    processing_settings: Dict[str, Any]
    edit_history: List[Dict[str, Any]]

class TextUpdateRequest(BaseModel):
    """Request model for updating text content"""
    text: str

class SettingsUpdateRequest(BaseModel):
    """Request model for updating processing settings"""
    settings_type: str  # 'caption' or 'video'
    settings: Dict[str, Any]

class BackgroundsUpdateRequest(BaseModel):
    """Request model for updating backgrounds"""
    backgrounds: List[Dict[str, Any]]

class TitleUpdateRequest(BaseModel):
    """Request model for updating project title"""
    title: str

class RegenerateResponse(BaseModel):
    """Response model for video regeneration"""
    success: bool
    job_id: Optional[str] = None
    message: str
    estimated_duration: Optional[int] = None

@router.get("/{project_id}/details-full")
async def get_project_details(
    project_id: str,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Get complete project details including all assets and settings

    Args:
        project_id: The video project ID
        current_user: Current authenticated user

    Returns:
        Complete project data with assets, backgrounds, settings, and history
    """
    try:
        logger.info(f"Getting project details for project_id: {project_id}")

        # Get user_id from UserProfile object
        user_id = str(current_user.id)
        logger.info(f"Current user_id: {user_id}")

        # Verify user owns this project
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)

        project = await project_repo.get_by_id(UUID(project_id))
        logger.info(f"Found project: {project.title if project else 'None'}")

        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if str(project.user_id) != str(user_id):
            logger.error(f"Access denied: project user_id={project.user_id}, current user_id={user_id}")
            raise HTTPException(status_code=403, detail="Access denied")

        # Get project details - but handle case where assets don't exist yet
        assets_service = get_project_assets_service()
        project_details = await assets_service.get_project_details(UUID(project_id))

        if not project_details:
            # If no assets exist yet, create a basic response with just the project info
            logger.info(f"No assets found for project {project_id}, returning basic project info")
            basic_response = {
                "project": project.dict() if hasattr(project, 'dict') else project.__dict__,
                "assets": {},
                "backgrounds": [],
                "processing_settings": {},
                "edit_history": []
            }

            # Try to generate audio URL if audio_file_id exists
            if project.audio_file_id:
                try:
                    gcs_service = GCSService()
                    audio_prefix = f"audio/{user_id}/"

                    # Find audio file in local storage
                    audio_blobs = list(gcs_service.bucket.list_blobs(prefix=audio_prefix))

                    for blob in audio_blobs:
                        # New format: audio/{user_id}/{audio_file_id}.{ext}
                        if (blob.name.endswith(f"{project.audio_file_id}.mp3") or
                            blob.name.endswith(f"{project.audio_file_id}.wav") or
                            blob.name.endswith(f"/{project.audio_file_id}")):
                            audio_signed_url = await gcs_service.generate_signed_url(blob.name)
                            basic_response["assets"]["audio_url"] = audio_signed_url
                            basic_response["assets"]["audio_signed_url"] = audio_signed_url
                            basic_response["assets"]["audio_gcs_path"] = blob.name
                            logger.info(f"Generated audio URL for basic project response: {blob.name}")
                            logger.info(f"Audio signed URL for basic project response: {audio_signed_url}")
                            break

                except Exception as e:
                    logger.warning(f"Failed to generate audio URL for basic response: {str(e)}")

            # Add story content if available
            if project.story_content:
                basic_response["assets"]["original_text_content"] = project.story_content
                basic_response["assets"]["text_content"] = project.story_content

            # Check if main video signed URL needs refreshing for basic response
            if project.gcs_path:
                try:
                    gcs_service = GCSService()
                    if gcs_service.is_available():
                        # Check if the video URL is expired or expiring soon
                        current_expires_at = project.gcs_signed_url_expires_at
                        if gcs_service.is_url_expired_or_expiring_soon(current_expires_at, buffer_hours=1):
                            logger.info(f"Video URL expired for project {project_id} (basic response), refreshing...")

                            # Generate new signed URL
                            new_signed_url = await gcs_service.generate_signed_url(project.gcs_path, 24)
                            if new_signed_url:
                                expires_at = gcs_service.get_url_expiry_time(24)

                                # Update the database
                                await project_repo.refresh_signed_url(project.id, new_signed_url, expires_at)

                                # Update the response data
                                basic_response["project"]["gcs_signed_url"] = new_signed_url
                                basic_response["project"]["gcs_signed_url_expires_at"] = expires_at.isoformat()

                                logger.info(f"Successfully refreshed video URL for project {project_id} (basic response)")
                            else:
                                logger.error(f"Failed to generate new signed URL for project {project_id} (basic response)")
                except Exception as e:
                    logger.warning(f"Error refreshing video URL for project {project_id} (basic response): {str(e)}")

            return basic_response

        # Even if we have project details, ensure audio URL is populated if audio_file_id exists
        if project.audio_file_id and not project_details.get("assets", {}).get("audio_url"):
            try:
                gcs_service = GCSService()
                audio_prefix = f"audio/{user_id}/"

                # Find audio file in local storage
                audio_blobs = list(gcs_service.bucket.list_blobs(prefix=audio_prefix))

                for blob in audio_blobs:
                    # New format: audio/{user_id}/{audio_file_id}.{ext}
                    if (blob.name.endswith(f"{project.audio_file_id}.mp3") or
                        blob.name.endswith(f"{project.audio_file_id}.wav") or
                        blob.name.endswith(f"/{project.audio_file_id}")):
                        audio_signed_url = await gcs_service.generate_signed_url(blob.name)
                        if "assets" not in project_details:
                            project_details["assets"] = {}
                        project_details["assets"]["audio_url"] = audio_signed_url
                        project_details["assets"]["audio_signed_url"] = audio_signed_url
                        project_details["assets"]["audio_gcs_path"] = blob.name
                        logger.info(f"Generated audio URL for existing project details: {blob.name}")
                        logger.info(f"Audio signed URL for existing project details: {audio_signed_url}")
                        break

            except Exception as e:
                logger.warning(f"Failed to generate audio URL for existing project details: {str(e)}")

        # Ensure story_content is included in project_details even when assets exist
        if project.story_content:
            if "assets" not in project_details:
                project_details["assets"] = {}
            project_details["assets"]["original_text_content"] = project.story_content
            project_details["assets"]["text_content"] = project.story_content
            logger.info(f"Added story_content to existing project details for project {project_id}")

        # Check if main video signed URL needs refreshing before returning
        logger.info(f"Project {project_id} - gcs_path: {project.gcs_path}, project_details has project: {bool(project_details.get('project'))}")
        if project.gcs_path and project_details.get("project"):
            logger.info(f"Project {project_id} - Checking URL expiration (details-full)...")
            try:
                gcs_service = GCSService()
                if gcs_service.is_available():
                    # Check if the video URL is expired or expiring soon
                    current_expires_at = project.gcs_signed_url_expires_at
                    logger.info(f"Project {project_id} - current_expires_at: {current_expires_at}")
                    is_expired = gcs_service.is_url_expired_or_expiring_soon(current_expires_at, buffer_hours=1)
                    logger.info(f"Project {project_id} - URL expired/expiring (details-full)? {is_expired}")
                    if is_expired:
                        logger.info(f"Video URL expired for project {project_id}, refreshing...")

                        # Generate new signed URL
                        new_signed_url = await gcs_service.generate_signed_url(project.gcs_path, 24)
                        if new_signed_url:
                            expires_at = gcs_service.get_url_expiry_time(24)

                            # Update the database
                            await project_repo.refresh_signed_url(project.id, new_signed_url, expires_at)

                            # Update the response data
                            project_details["project"]["gcs_signed_url"] = new_signed_url
                            project_details["project"]["gcs_signed_url_expires_at"] = expires_at.isoformat()

                            logger.info(f"Successfully refreshed video URL for project {project_id}")
                        else:
                            logger.error(f"Failed to generate new signed URL for project {project_id}")
            except Exception as e:
                logger.warning(f"Error refreshing video URL for project {project_id}: {str(e)}")

        logger.info(f"Successfully retrieved project details for {project_id}")
        return project_details

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project details: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error retrieving project details: {str(e)}")

@router.put("/{project_id}")
async def update_project_title(
    project_id: str,
    request: TitleUpdateRequest,
    current_user: UserProfile = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Update the title of a project

    Args:
        project_id: The video project ID
        request: New title
        current_user: Current authenticated user

    Returns:
        Success status and updated project info
    """
    try:
        # Verify user owns this project
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)

        project = await project_repo.get_by_id(UUID(project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if str(project.user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")

        if not request.title.strip():
            raise HTTPException(status_code=400, detail="Title cannot be empty")

        # Update the title in the database
        supabase = supabase_client.supabase
        update_data = {
            "title": request.title.strip(),
            "updated_at": datetime.now().isoformat()
        }

        result = supabase.table("video_projects").update(update_data).eq("id", project_id).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update title")

        logger.info(f"Successfully updated title for project {project_id} to: {request.title.strip()}")

        return {
            "success": True,
            "message": "Project title updated successfully",
            "title": request.title.strip(),
            "updated_at": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating project title: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating title: {str(e)}")

@router.put("/{project_id}/text")
async def update_project_text(
    project_id: str,
    request: TextUpdateRequest,
    current_user: UserProfile = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Update the text content of a project

    Args:
        project_id: The video project ID
        request: New text content
        current_user: Current authenticated user

    Returns:
        Success status and updated text info
    """
    try:
        # Verify user owns this project
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)

        project = await project_repo.get_by_id(UUID(project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if str(project.user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")

        if not request.text.strip():
            raise HTTPException(status_code=400, detail="Text content cannot be empty")

        # Update the text
        assets_service = get_project_assets_service()
        success = await assets_service.update_project_text(
            project_id=UUID(project_id),
            user_id=UUID(current_user.id),
            new_text=request.text.strip()
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to update text content")

        return {
            "success": True,
            "message": "Text content updated successfully",
            "character_count": len(request.text),
            "word_count": len(request.text.split()),
            "updated_at": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating project text: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating text: {str(e)}")

@router.put("/{project_id}/settings")
async def update_project_settings(
    project_id: str,
    request: SettingsUpdateRequest,
    current_user: UserProfile = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Update processing settings for a project

    Args:
        project_id: The video project ID
        request: Settings update request with type and new settings
        current_user: Current authenticated user

    Returns:
        Success status and updated settings info
    """
    try:
        # Verify user owns this project
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)

        project = await project_repo.get_by_id(UUID(project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if str(project.user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")

        if request.settings_type not in ['caption', 'video']:
            raise HTTPException(status_code=400, detail="Settings type must be 'caption' or 'video'")

        # Update the settings
        assets_service = get_project_assets_service()
        success = await assets_service.update_project_settings(
            project_id=UUID(project_id),
            user_id=UUID(current_user.id),
            settings_type=request.settings_type,
            new_settings=request.settings
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to update settings")

        return {
            "success": True,
            "message": f"{request.settings_type.title()} settings updated successfully",
            "settings_type": request.settings_type,
            "updated_at": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating project settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating settings: {str(e)}")

@router.put("/{project_id}/backgrounds")
async def update_project_backgrounds(
    project_id: str,
    request: BackgroundsUpdateRequest,
    current_user: UserProfile = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Update background assets for a project

    Args:
        project_id: The video project ID
        request: New background assets
        current_user: Current authenticated user

    Returns:
        Success status and updated backgrounds info
    """
    try:
        # Verify user owns this project
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)

        project = await project_repo.get_by_id(UUID(project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if str(project.user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")

        if not request.backgrounds:
            raise HTTPException(status_code=400, detail="At least one background is required")

        # Validate background data
        for bg in request.backgrounds:
            bg_type = bg.get('background_type')
            if bg_type not in ['video', 'image', 'image_timeline']:
                raise HTTPException(status_code=400, detail="Invalid background type")

            if bg_type == 'video' and not bg.get('video_url'):
                raise HTTPException(status_code=400, detail="Video URL required for video background")
            elif bg_type == 'image' and not bg.get('image_url'):
                raise HTTPException(status_code=400, detail="Image URL required for image background")

        # Update the backgrounds
        assets_service = get_project_assets_service()
        success = await assets_service.update_project_backgrounds(
            project_id=UUID(project_id),
            user_id=UUID(current_user.id),
            backgrounds=request.backgrounds
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to update backgrounds")

        return {
            "success": True,
            "message": f"Updated {len(request.backgrounds)} background assets",
            "background_count": len(request.backgrounds),
            "updated_at": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating project backgrounds: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating backgrounds: {str(e)}")

@router.get("/{project_id}/history")
async def get_project_history(
    project_id: str,
    limit: int = 50,
    current_user: UserProfile = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get edit history for a project

    Args:
        project_id: The video project ID
        limit: Maximum number of history entries to return
        current_user: Current authenticated user

    Returns:
        Project edit history
    """
    try:
        # Verify user owns this project
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)

        project = await project_repo.get_by_id(UUID(project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if str(project.user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Get edit history
        supabase = supabase_client.supabase
        result = supabase.table("video_project_edit_history").select("*").eq("project_id", project_id).order("edited_at", desc=True).limit(limit).execute()

        return {
            "project_id": project_id,
            "history": result.data or [],
            "total_edits": len(result.data) if result.data else 0
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving history: {str(e)}")

def greenscreen_effect_name_to_url(effect_name: str | None) -> str | None:
    """Resolve a greenscreen effect name to a local media URL."""
    if not effect_name:
        return None

    from video_processor.services.greenscreen_effects import greenscreen_effect_media_url

    return greenscreen_effect_media_url(effect_name)

@router.post("/{project_id}/regenerate", response_model=RegenerateResponse)
async def regenerate_project(
    project_id: str,
    request: dict,
    current_user: UserProfile = Depends(get_current_user)
) -> RegenerateResponse:
    """
    Regenerate video with updated project settings

    Args:
        project_id: The video project ID
        request: New settings to apply for regeneration
        current_user: Current authenticated user

    Returns:
        Regeneration job information
    """
    try:
        # Verify user owns this project
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)

        project = await project_repo.get_by_id(UUID(project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if str(project.user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Prepare regeneration request with existing project data
        assets_service = get_project_assets_service()
        base_regeneration_request = await assets_service.prepare_regeneration_request(UUID(project_id))

        if not base_regeneration_request:
            raise HTTPException(status_code=400, detail="Unable to prepare regeneration request - project assets may be incomplete")

        # Merge new settings from request with existing project data
        regeneration_request = await assets_service.merge_regeneration_settings(
            base_request=base_regeneration_request,
            new_settings=request,
            project_id=UUID(project_id),
            user_id=UUID(current_user.id)
        )

        # Call the cloud video processor with the regeneration request
        from services.cloud_video_service import cloud_video_service

        # Check if cloud processing is enabled
        use_cloud = cloud_video_service.is_cloud_processing_enabled()
        if not use_cloud:
            raise HTTPException(status_code=503, detail="Cloud video processing is not available")

        # Extract necessary data from regeneration request
        audio_url = None
        if regeneration_request.get('existing_audio_id'):
            # Get audio URL for existing audio file
            audio_file_id = regeneration_request['existing_audio_id']

            # Load audio metadata to get the URL
            from services.tts_service import TTSService
            tts_service = TTSService()

            try:
                audio_file = await tts_service.load_audio_metadata(audio_file_id)
                if audio_file and hasattr(audio_file, 'url') and audio_file.url:
                    audio_url = audio_file.url
                    logger.info(f"🎵 Using existing audio URL for regeneration: {audio_url}")
                else:
                    logger.error(f"❌ Could not get audio URL for existing audio file: {audio_file_id}")
                    raise HTTPException(status_code=400, detail="Could not access existing audio file")
            except Exception as e:
                logger.error(f"❌ Failed to load existing audio file {audio_file_id}: {str(e)}")
                raise HTTPException(status_code=400, detail=f"Failed to load existing audio file: {str(e)}")
        else:
            logger.error("❌ No existing audio ID found in regeneration request")
            raise HTTPException(status_code=400, detail="No audio available for regeneration")

        background_type = regeneration_request.get('background_type', 'video')
        background_video_url = regeneration_request.get('background_video_url') if background_type == 'video' else None
        background_image_url = regeneration_request.get('background_image_url') if background_type == 'image' else None

        # For image_timeline, fetch current timeline segments from database with proper image URLs
        image_timeline = None
        if background_type == 'image_timeline':
            try:
                # Get timeline segments directly from video_project_backgrounds
                timeline_result = supabase_client.supabase.table("video_project_backgrounds").select("*").eq("project_id", project_id).eq("background_type", "image_timeline").order("sort_order").execute()

                logger.info(f"🎬 Retrieved {len(timeline_result.data) if timeline_result.data else 0} timeline segments for regeneration")

                image_timeline = []
                if timeline_result.data:
                    
                    for segment_data in timeline_result.data:
                        # Get image info from generated_images table
                        image_url = None
                        image_id = segment_data.get('image_id')

                        if image_id:
                            from services.gcs_service import GCSService
                            gcs_service = GCSService()

                            # Fetch from generated_images
                            image_result = supabase_client.supabase.table("generated_images").select(
                                "gcs_signed_url, gcs_path"
                            ).eq("id", image_id).execute()

                            if image_result.data:
                                img = image_result.data[0]
                                image_url = img.get('gcs_signed_url')

                                # Check if URL is expired or missing by parsing the URL
                                needs_refresh = False
                                if not image_url:
                                    needs_refresh = True
                                    logger.info(f"Image {image_id} has no signed URL, generating new one")
                                elif gcs_service.is_signed_url_expired(image_url, buffer_minutes=60):
                                    needs_refresh = True
                                    logger.info(f"Image {image_id} URL expired/expiring, refreshing for regeneration...")

                                # Generate new URL if needed
                                if needs_refresh and img.get('gcs_path'):
                                    try:
                                        image_url = await gcs_service.generate_signed_url(img['gcs_path'], 24)
                                        logger.info(f"🎬 Generated signed URL for image {image_id}")
                                    except Exception as gcs_error:
                                        logger.error(f"❌ Failed to generate signed URL: {gcs_error}")
                            else:
                                logger.warning(f"⚠️ Image {image_id} not found in generated_images")

                        if image_url:
                            # Extract transition settings
                            transition_settings = segment_data.get('transition_settings', {})
                            if isinstance(transition_settings, str):
                                import json
                                try:
                                    transition_settings = json.loads(transition_settings)
                                except:
                                    transition_settings = {}

                            segment = {
                                'image_url': image_url,
                                'start_time': segment_data.get('start_time', 0),
                                'end_time': segment_data.get('end_time', 30),
                                'transition_type': segment_data.get('transition_type') or transition_settings.get('type', 'cut'),
                                'transition_duration': segment_data.get('transition_duration') or transition_settings.get('duration', 0.5),
                                'camera_movement': segment_data.get('camera_movement', 'static'),
                                'greenscreen_effect': greenscreen_effect_name_to_url(segment_data.get('greenscreen_effect'))
                            }
                            image_timeline.append(segment)
                            logger.info(f"🎬 Added segment with image_url: {image_url[:50]}...")
                        else:
                            logger.warning(f"⚠️  Skipping segment with image_id {segment_data.get('image_id')} - no image URL found")

                logger.info(f"🎬 Prepared {len(image_timeline)} timeline segments with valid image URLs for regeneration")
            except Exception as e:
                logger.error(f"❌ Error retrieving timeline segments for regeneration: {str(e)}")
                image_timeline = regeneration_request.get('image_timeline')  # Fallback to request data

        # Load text overlays from database
        text_overlays_for_regen = None
        try:
            from repositories.project_scenes_repository import get_project_scenes_repository
            scenes_repo = get_project_scenes_repository()
            text_layers = await scenes_repo.get_text_layers_by_project(UUID(project_id))
            if text_layers:
                text_overlays_for_regen = text_layers
                logger.info(f"📝 Loaded {len(text_layers)} text overlays for regeneration")
        except Exception as tl_err:
            logger.warning(f"Could not load text overlays for regeneration: {tl_err}")

        # Submit to cloud service for regeneration
        cloud_result = await cloud_video_service.submit_video_processing_job(
            audio_url=audio_url,  # URL from existing audio file
            background_video_url=background_video_url,
            background_image_url=background_image_url,
            background_type=background_type,
            image_timeline=image_timeline,
            caption_settings=regeneration_request.get('caption_settings', {}),
            processing_options=regeneration_request.get('video_settings', {}),  # video_settings goes here
            user_id=str(current_user.id),
            project_id=project_id,
            project_title=regeneration_request.get('project_title', 'Regenerated Video'),
            # Music parameters
            background_music_id=regeneration_request.get('background_music_id'),
            music_volume=regeneration_request.get('music_volume', 0.25),
            music_fade_in=regeneration_request.get('music_fade_in', 2.0),
            music_fade_out=regeneration_request.get('music_fade_out', 3.0),
            text_overlays=text_overlays_for_regen
        )

        # Log the regeneration attempt
        await assets_service.log_project_edit(
            project_id=UUID(project_id),
            user_id=UUID(current_user.id),
            edit_type="regeneration",
            field_changed="video_output",
            description="Initiated video regeneration"
        )

        return RegenerateResponse(
            success=True,
            job_id=cloud_result.get('job_id', f"regen_{project_id}_{int(datetime.now().timestamp())}"),
            message="Video regeneration initiated successfully",
            estimated_duration=cloud_result.get('estimated_duration', 120)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error regenerating project: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error initiating regeneration: {str(e)}")

@router.get("/{project_id}/regeneration-preview")
async def get_regeneration_preview(
    project_id: str,
    current_user: UserProfile = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get a preview of what will be regenerated (without actually triggering regeneration)

    Args:
        project_id: The video project ID
        current_user: Current authenticated user

    Returns:
        Preview of regeneration parameters
    """
    try:
        # Verify user owns this project
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)

        project = await project_repo.get_by_id(UUID(project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if str(project.user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Prepare regeneration request (preview only)
        assets_service = get_project_assets_service()
        regeneration_request = await assets_service.prepare_regeneration_request(UUID(project_id))

        if not regeneration_request:
            raise HTTPException(status_code=400, detail="Unable to preview regeneration - project assets may be incomplete")

        # Calculate estimated costs/duration based on text length
        text_length = len(regeneration_request.get('text', ''))
        estimated_duration = max(60, text_length // 10)  # Rough estimate: 10 chars per second minimum 60s

        return {
            "project_id": project_id,
            "ready_for_regeneration": True,
            "text_length": text_length,
            "estimated_duration_seconds": estimated_duration,
            "parameters": {
                "text_content": regeneration_request.get('text', ''),
                "voice_id": regeneration_request.get('voice_id', ''),
                "background_type": regeneration_request.get('background_type', ''),
                "has_music": bool(regeneration_request.get('background_music_id')),
                "resolution": regeneration_request.get('video_settings', {}).get('resolution', ''),
                "caption_style": regeneration_request.get('caption_settings', {}).get('subtitle_style', '')
            },
            "preview_generated_at": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting regeneration preview: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating preview: {str(e)}")

@router.post("/{project_id}/duplicate")
async def duplicate_project(
    project_id: str,
    new_title: str,
    current_user: UserProfile = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Create a copy of an existing project

    Args:
        project_id: The source project ID
        new_title: Title for the new project
        current_user: Current authenticated user

    Returns:
        New project information
    """
    try:
        # Verify user owns this project
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)

        project = await project_repo.get_by_id(UUID(project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if str(project.user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Get project assets
        assets_service = get_project_assets_service()
        project_details = await assets_service.get_project_details(UUID(project_id))

        if not project_details:
            raise HTTPException(status_code=400, detail="Cannot duplicate project - assets not found")

        # Create new project (this would need to be implemented)
        # For now, return a placeholder response

        return {
            "success": True,
            "message": "Project duplication initiated",
            "original_project_id": project_id,
            "new_project_title": new_title,
            "note": "Project duplication feature requires additional implementation"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error duplicating project: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error duplicating project: {str(e)}")

@router.post("/{project_id}/refresh-urls")
async def refresh_project_urls(
    project_id: str,
    current_user: UserProfile = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Refresh Google Cloud Storage signed URLs for project assets

    Args:
        project_id: The video project ID
        current_user: Current authenticated user

    Returns:
        Updated URLs for project assets
    """
    try:
        logger.info(f"Refreshing URLs for project: {project_id}")

        # Get user_id from UserProfile object
        user_id = str(current_user.id)

        # Verify user owns this project
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)

        project = await project_repo.get_by_id(UUID(project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if str(project.user_id) != str(user_id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Initialize GCS service
        gcs_service = GCSService()
        refreshed_data = {
            "project": {},
            "assets": {},
            "backgrounds": []
        }

        # Refresh main video URL if exists
        if project.gcs_path:
            try:
                video_signed_url = await gcs_service.generate_signed_url(project.gcs_path)
                refreshed_data["project"]["gcs_signed_url"] = video_signed_url

                # Update database with new signed URL
                update_data = {
                    "gcs_signed_url": video_signed_url,
                    "gcs_signed_url_expires_at": gcs_service.get_url_expiry_time()
                }
                supabase_client.supabase.table("video_projects").update(update_data).eq("id", project_id).execute()
                logger.info(f"Updated main video URL for project {project_id}")
            except Exception as e:
                logger.warning(f"Failed to refresh main video URL: {str(e)}")

        # Refresh audio URL if audio_file_id exists
        if project.audio_file_id:
            try:
                # Construct GCS path: audio/<user_id>/<audio_file_id>.{ext}
                # Find the audio file by matching the audio_file_id
                audio_prefix = f"audio/{user_id}/"

                # Find audio files matching the pattern in local storage
                audio_blobs = list(gcs_service.bucket.list_blobs(prefix=audio_prefix))
                matching_audio_blob = None

                for blob in audio_blobs:
                    # New format: audio/{user_id}/{audio_file_id}.{ext}
                    if (blob.name.endswith(f"{project.audio_file_id}.mp3") or
                        blob.name.endswith(f"{project.audio_file_id}.wav") or
                        blob.name.endswith(f"/{project.audio_file_id}")):
                        matching_audio_blob = blob
                        break

                if matching_audio_blob:
                    audio_signed_url = await gcs_service.generate_signed_url(matching_audio_blob.name)
                    refreshed_data["assets"]["audio_url"] = audio_signed_url
                    refreshed_data["assets"]["audio_signed_url"] = audio_signed_url
                    refreshed_data["assets"]["audio_gcs_path"] = matching_audio_blob.name
                    refreshed_data["assets"]["tts_provider"] = "minimax"  # Default, could be stored in DB
                    logger.info(f"Generated audio URL for project {project_id}: {matching_audio_blob.name}")
                else:
                    logger.warning(f"No audio file found for audio_file_id: {project.audio_file_id}")

            except Exception as e:
                logger.warning(f"Failed to refresh audio URL: {str(e)}")

        # Get project text content from story_content field
        if project.story_content:
            refreshed_data["assets"]["original_text_content"] = project.story_content
            refreshed_data["assets"]["text_content"] = project.story_content

        # Get any existing assets from project_assets_service
        try:
            assets_service = get_project_assets_service()
            existing_details = await assets_service.get_project_details(UUID(project_id))
            if existing_details and existing_details.get("assets"):
                # Merge existing assets with refreshed URLs
                existing_assets = existing_details["assets"]
                refreshed_data["assets"].update(existing_assets)

            if existing_details and existing_details.get("backgrounds"):
                refreshed_data["backgrounds"] = existing_details["backgrounds"]

        except Exception as e:
            logger.warning(f"Could not get existing assets: {str(e)}")

        logger.info(f"Successfully refreshed URLs for project {project_id}")
        return refreshed_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing project URLs: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error refreshing URLs: {str(e)}")

# Draft saving models
class CreateEmptyProjectRequest(BaseModel):
    """Request model for creating an empty project"""
    title: Optional[str] = "Untitled Project"

class CreateProjectDraftRequest(BaseModel):
    """Request model for creating a new project draft"""
    title: str
    script_content: str
    ui_preferences: Dict[str, Any]
    youtube_metadata: Optional[Dict[str, Any]] = None
    timeline_segments: Optional[List[Dict[str, Any]]] = None
    audio_file_id: Optional[str] = None  # If provided, check for existing project with this audio file

class SaveProjectDraftRequest(BaseModel):
    """Request model for updating project draft data"""
    script_content: str
    ui_preferences: Dict[str, Any]
    youtube_metadata: Optional[Dict[str, Any]] = None
    timeline_segments: Optional[List[Dict[str, Any]]] = None

class ProjectDraftResponse(BaseModel):
    """Response model for draft operations"""
    project_id: str
    message: str
    last_saved_at: str

def extract_greenscreen_effect_name(greenscreen_effect: str | None) -> str | None:
    """Extract effect name from an old URL or return as-is if already a name."""
    if not greenscreen_effect:
        return None

    # If it's a full URL, extract the filename without extension
    if greenscreen_effect.startswith('http'):
        try:
            # Extract filename from URL: https://storage.googleapis.com/bucket/greenscreen/fire2_v.mp4 -> fire2_v
            url_parts = greenscreen_effect.split('/')
            filename = url_parts[-1]  # Get last part (fire2_v.mp4)
            name_without_ext = filename.rsplit('.', 1)[0]  # Remove extension (fire2_v)
            return name_without_ext
        except Exception as e:
            logger.warning(f"Failed to extract effect name from URL: {greenscreen_effect}, error: {e}")
            return greenscreen_effect

    # Already just a name, return as-is
    return greenscreen_effect

async def save_timeline_segments(project_id: UUID, timeline_segments: List[Dict[str, Any]], supabase_client: SupabaseClient):
    """Helper function to save timeline segments to video_project_backgrounds table"""
    logger.info(f"🎬 save_timeline_segments called with project_id={project_id}, segments count={len(timeline_segments) if timeline_segments else 0}")

    if not timeline_segments:
        logger.info("🎬 No timeline segments provided, skipping save")
        return

    logger.info(f"🎬 Timeline segments data: {timeline_segments}")

    try:
        # Clear existing timeline segments for this project
        logger.info(f"🎬 Clearing existing timeline segments for project {project_id}")
        delete_result = supabase_client.supabase.table("video_project_backgrounds").delete().eq("project_id", str(project_id)).eq("background_type", "image_timeline").execute()
        logger.info(f"🎬 Delete result: {delete_result}")

        segments_inserted = 0
        # Insert new timeline segments
        for i, segment in enumerate(timeline_segments):
            logger.info(f"🎬 Processing segment {i}: {segment}")

            segment_data = {
                "project_id": str(project_id),
                "background_type": "image_timeline",
                "image_id": segment.get("image_id"),
                "sort_order": i,
                "start_time": segment.get("start_time", 0),
                "end_time": segment.get("end_time", 0),
                # Note: image_url removed - fetch from generated_images/user_images via image_id
                "transition_type": segment.get("transition_type", "crossfade"),
                "transition_duration": segment.get("transition_duration", 0.5),
                "camera_movement": segment.get("camera_movement", "static"),
                "greenscreen_effect": extract_greenscreen_effect_name(segment.get("greenscreen_effect"))
            }

            logger.info(f"🎬 Prepared segment_data: {segment_data}")

            # Only insert if we have essential data
            if segment_data["image_id"] and segment_data["end_time"] > segment_data["start_time"]:
                logger.info(f"🎬 Inserting segment {i} with image_id={segment_data['image_id']}")
                insert_result = supabase_client.supabase.table("video_project_backgrounds").insert(segment_data).execute()
                logger.info(f"🎬 Insert result for segment {i}: {insert_result}")
                segments_inserted += 1
            else:
                logger.warning(f"🎬 Skipping segment {i}: missing image_id ({segment_data['image_id']}) or invalid time range ({segment_data['start_time']}-{segment_data['end_time']})")

        logger.info(f"🎬 Successfully saved {segments_inserted}/{len(timeline_segments)} timeline segments for project {project_id}")

    except Exception as e:
        logger.error(f"🎬 Error saving timeline segments for project {project_id}: {str(e)}")
        import traceback
        logger.error(f"🎬 Full traceback: {traceback.format_exc()}")
        raise

@router.post("/create-empty", response_model=ProjectDraftResponse)
async def create_empty_project(
    request: CreateEmptyProjectRequest,
    current_user: UserProfile = Depends(get_current_user)
) -> ProjectDraftResponse:
    """
    Create a new empty project (for "Custom Text" button)

    Args:
        request: Create empty project request with optional title
        current_user: Current authenticated user

    Returns:
        Project ID to navigate to
    """
    try:
        logger.info(f"Creating new empty project for user {current_user.id}")

        # Create new project with draft status and minimal data
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)

        from models.video_project_models import VideoProjectCreate

        project_data = VideoProjectCreate(
            user_id=UUID(current_user.id),
            title=request.title or "Untitled Project",
            status="draft",
            story_content="",  # Empty content
            draft_data={}  # Empty draft data
        )

        project = await project_repo.create(project_data)

        logger.info(f"Successfully created empty project with ID: {project.id}")

        # Create primary language record (English by default) in video_project_languages
        # This ensures audio generation can save to video_project_languages table
        try:
            supabase = supabase_client.supabase
            current_time = datetime.now().isoformat()
            primary_language_data = {
                "project_id": str(project.id),
                "language_code": "en",
                "language_name": "English",
                "is_primary": True,
                "story_content": "",  # Empty content for new project
                "audio_file_id": None,
                "translation_status": "original",
                "created_at": current_time,
                "updated_at": current_time
            }

            supabase.table("video_project_languages").insert(primary_language_data).execute()
            logger.info(f"Created primary language (en) for new project {project.id}")
        except Exception as lang_error:
            logger.warning(f"Failed to create primary language record: {str(lang_error)}")
            # Don't fail the whole request if language record creation fails

        return ProjectDraftResponse(
            project_id=str(project.id),
            message="Empty project created successfully",
            last_saved_at=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error creating empty project: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating project: {str(e)}")

@router.post("/create-draft", response_model=ProjectDraftResponse)
async def create_project_draft(
    request: CreateProjectDraftRequest,
    current_user: UserProfile = Depends(get_current_user)
) -> ProjectDraftResponse:
    """
    Create a new project draft

    Args:
        request: Create draft request with title and initial draft data
        current_user: Current authenticated user

    Returns:
        Project ID and save confirmation
    """
    try:
        logger.info(f"Creating new project draft for user {current_user.id}")
        logger.info(f"🎬 Request timeline_segments: {len(request.timeline_segments) if request.timeline_segments else 0} segments")
        if request.timeline_segments:
            logger.info(f"🎬 Timeline segments sample: {request.timeline_segments[:2] if len(request.timeline_segments) > 0 else []}")

        # Create new project with draft status
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)

        # Check if a project already exists with this audio_file_id
        if request.audio_file_id:
            logger.info(f"🔍 Checking for existing project with audio_file_id: {request.audio_file_id}")
            existing_project = await project_repo.get_by_audio_file_id(request.audio_file_id)
            if existing_project:
                logger.info(f"✅ Found existing project {existing_project.id} with audio_file_id {request.audio_file_id}")
                logger.info(f"📝 Updating existing project instead of creating new one")

                # Update the existing project instead of creating a new one
                from models.video_project_models import VideoProjectUpdate

                draft_data = {
                    "ui_preferences": request.ui_preferences,
                    "youtube_metadata": request.youtube_metadata or {}
                }

                update_data = VideoProjectUpdate(
                    title=request.title,
                    story_content=request.script_content,
                    draft_data=draft_data,
                    last_edited_at=datetime.now()
                )

                project = await project_repo.update(existing_project.id, update_data)

                # DISABLED: Scenes are already saved via ProjectScenesRepository in frontend
                # Calling save_timeline_segments would create duplicate records
                # if request.timeline_segments:
                #     await save_timeline_segments(project.id, request.timeline_segments, supabase_client)

                return ProjectDraftResponse(
                    project_id=str(project.id),
                    message="Draft updated successfully",
                    last_saved_at=datetime.now().isoformat()
                )

        from models.video_project_models import VideoProjectCreate

        # Combine UI preferences and YouTube metadata for draft_data
        draft_data = {
            "ui_preferences": request.ui_preferences,
            "youtube_metadata": request.youtube_metadata or {}
        }

        logger.info(f'44444444444444444444444444444444... {request}')


        project_data = VideoProjectCreate(
            user_id=UUID(current_user.id),
            title=request.title,
            status="draft",
            story_content=request.script_content,  # Store script in normalized column
            draft_data=draft_data  # Store only UI preferences in JSON
        )

        project = await project_repo.create(project_data)

        # Create primary language entry with the script content
        try:
            lang_service = get_project_language_service(supabase_client)
            await lang_service.ensure_primary_language_exists(
                project_id=project.id,
                language_code="en",
                language_name="English",
                story_content=request.script_content,
                audio_file_id=request.audio_file_id
            )
            logger.info(f"Created primary language entry for project {project.id}")
        except Exception as lang_error:
            logger.error(f"Failed to create primary language entry: {str(lang_error)}")
            # Continue - the script is still in video_projects as fallback

        # DISABLED: Scenes are already saved via ProjectScenesRepository in frontend
        # Calling save_timeline_segments would create duplicate records
        # if request.timeline_segments:
        #     await save_timeline_segments(project.id, request.timeline_segments, supabase_client)

        logger.info(f"Successfully created project draft with ID: {project.id}")

        return ProjectDraftResponse(
            project_id=str(project.id),
            message="Draft created successfully",
            last_saved_at=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error creating project draft: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating draft: {str(e)}")

@router.put("/{project_id}/save-draft", response_model=ProjectDraftResponse)
async def save_project_draft(
    project_id: str,
    request: SaveProjectDraftRequest,
    current_user: UserProfile = Depends(get_current_user)
) -> ProjectDraftResponse:
    """
    Save/update project draft data

    Args:
        project_id: The video project ID to update
        request: Save draft request with updated draft data
        current_user: Current authenticated user

    Returns:
        Save confirmation and timestamp
    """
    try:
        logger.info(f"Saving draft for project {project_id}, user {current_user.id}")
        logger.info(f"🎬 Request timeline_segments: {len(request.timeline_segments) if request.timeline_segments else 0} segments")
        if request.timeline_segments:
            logger.info(f"🎬 Timeline segments sample: {request.timeline_segments[:2] if len(request.timeline_segments) > 0 else []}")

        # Verify user owns this project
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)

        project = await project_repo.get_by_id(UUID(project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Debug logging for authorization check
        logger.info(f"Authorization check: project.user_id={project.user_id} (type: {type(project.user_id)}), current_user.id={current_user.id} (type: {type(current_user.id)})")
        logger.info(f"String comparison: '{str(project.user_id)}' != '{str(current_user.id)}' = {str(project.user_id) != str(current_user.id)}")

        if str(project.user_id) != str(current_user.id):
            logger.error(f"Access denied: project user_id={project.user_id}, current user_id={current_user.id}")
            raise HTTPException(status_code=403, detail="Access denied")

        # Update project with new draft data
        from models.video_project_models import VideoProjectUpdate

        # Combine UI preferences and YouTube metadata for draft_data
        draft_data = {
            "ui_preferences": request.ui_preferences,
            "youtube_metadata": request.youtube_metadata or {}
        }

        update_data = VideoProjectUpdate(
            story_content=request.script_content,  # Update script in normalized column
            draft_data=draft_data  # Update only UI preferences in JSON
        )

        updated_project = await project_repo.update(UUID(project_id), update_data)

        if not updated_project:
            raise HTTPException(status_code=500, detail="Failed to save draft")

        # Update primary language entry with the script content
        try:
            lang_service = get_project_language_service(supabase_client)
            await lang_service.update_story_content(
                project_id=UUID(project_id),
                story_content=request.script_content
            )
            logger.info(f"Updated primary language entry for project {project_id}")
        except Exception as lang_error:
            logger.error(f"Failed to update primary language entry: {str(lang_error)}")
            # Continue - the script is still in video_projects as fallback

        # DISABLED: Scenes are already saved via ProjectScenesRepository in frontend
        # Calling save_timeline_segments would create duplicate records
        # if request.timeline_segments:
        #     await save_timeline_segments(UUID(project_id), request.timeline_segments, supabase_client)

        logger.info(f"Successfully saved draft for project {project_id}")

        return ProjectDraftResponse(
            project_id=str(project_id),
            message="Draft saved successfully",
            last_saved_at=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving project draft: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving draft: {str(e)}")
