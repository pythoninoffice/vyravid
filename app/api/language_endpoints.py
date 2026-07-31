"""
API endpoints for multi-language support in video projects
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, timezone
import logging

from models.auth_models import UserProfile
from middleware.auth_middleware import get_current_user
from services.translation_service import TranslationService
from services.tts_service import TTSService
from services.project_language_service import get_project_language_service
from db.supabase_client import SupabaseClient

router = APIRouter(prefix="/api/video/projects", tags=["languages"])
logger = logging.getLogger(__name__)

# Pydantic models
class AddLanguageRequest(BaseModel):
    """Request model for adding a language to a project"""
    language_code: str
    language_name: str
    auto_translate: bool = True
    source_language: Optional[str] = None
    source_content: Optional[str] = None  # Editor content to translate from

class UpdateLanguageRequest(BaseModel):
    """Request model for updating language content"""
    story_content: Optional[str] = None
    translation_status: Optional[str] = None
    audio_file_id: Optional[str] = None
    video_file_id: Optional[str] = None
    is_primary: Optional[bool] = None

class LanguageResponse(BaseModel):
    """Response model for language data"""
    id: str
    project_id: str
    language_code: str
    language_name: str
    is_primary: bool
    story_content: Optional[str] = None
    audio_file_id: Optional[str] = None
    video_file_id: Optional[str] = None
    translation_status: str
    created_at: str
    updated_at: str

class TranslationResponse(BaseModel):
    """Response model for translation result"""
    translated_text: str
    original_length: int
    translated_length: int
    original_word_count: int
    translated_word_count: int
    estimated_duration_ratio: float

class AudioFileResponse(BaseModel):
    """Response model for audio file details"""
    id: str
    url: str
    duration: float
    projectId: str

# Helper function to get language mapping
LANGUAGE_MAP = {
    'en': 'English',
    'zh': 'Chinese',
    'zh-CN': 'Simplified Chinese',
    'zh-TW': 'Traditional Chinese',
    'es': 'Spanish',
    'fr': 'French',
    'de': 'German',
    'ja': 'Japanese',
    'ko': 'Korean',
    'pt': 'Portuguese',
    'ru': 'Russian',
    'ar': 'Arabic',
    'hi': 'Hindi',
    'it': 'Italian',
    'nl': 'Dutch',
    'pl': 'Polish',
    'tr': 'Turkish',
    'vi': 'Vietnamese',
    'th': 'Thai',
    'id': 'Indonesian'
}

def get_language_name(code: str) -> str:
    """Get full language name from code"""
    return LANGUAGE_MAP.get(code, code)

@router.post("/{project_id}/languages", response_model=LanguageResponse)
async def add_language_to_project(
    project_id: str,
    request: AddLanguageRequest,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Add a new language to a video project

    Args:
        project_id: The video project ID
        request: Language addition request
        current_user: Current authenticated user

    Returns:
        Created language data
    """
    try:
        logger.info(f"Adding language {request.language_code} to project {project_id}")

        supabase_client = SupabaseClient()
        supabase = supabase_client.supabase
        lang_service = get_project_language_service(supabase_client)

        # Verify user owns this project
        project_result = supabase.table("video_projects").select("*").eq("id", project_id).eq("user_id", str(current_user.id)).execute()

        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found or access denied")

        project = project_result.data[0]

        # Ensure project has a primary language entry
        # After migration, all projects should have this, but this ensures it
        await lang_service.ensure_primary_language_exists(
            project_id=UUID(project_id),
            language_code=project.get("primary_language", "en"),
            language_name=get_language_name(project.get("primary_language", "en"))
        )

        # Check if language already exists for this project
        existing_lang = supabase.table("video_project_languages").select("*").eq("project_id", project_id).eq("language_code", request.language_code).execute()

        if existing_lang.data:
            raise HTTPException(status_code=400, detail=f"Language {request.language_code} already exists for this project")

        # Get the source story content for translation
        story_content = None
        translation_status = "original"

        if request.auto_translate and request.source_language:
            logger.info(f"Auto-translate requested from {request.source_language} to {request.language_code}")

            # Prefer source_content from request (current editor content) over database
            # This allows translation of unsaved content
            source_script = None
            if request.source_content:
                source_script = request.source_content
                logger.info(f"Using source script from request (editor content), length: {len(source_script)} chars")
            else:
                # Fall back to database content if no editor content provided
                source_script = await lang_service.get_story_content(
                    project_id=UUID(project_id),
                    language_code=request.source_language
                )
                if source_script:
                    logger.info(f"Using source script from database, length: {len(source_script)} chars")

            if source_script:
                pass  # Continue with translation

                # Translate using the translation service
                translation_service = TranslationService()
                translation_result = await translation_service.translate_video_script(
                    text=source_script,
                    source_language=get_language_name(request.source_language),
                    target_language=get_language_name(request.language_code)
                )

                story_content = translation_result["translated_text"]
                translation_status = "auto"

                logger.info(f"Translation completed. Original: {len(source_script)} chars, Translated: {len(story_content)} chars, Duration ratio: {translation_result['estimated_duration_ratio']:.2f}")
            else:
                logger.warning(f"No source content found for language {request.source_language} in project {project_id}")

        # Create language entry
        current_time = datetime.now(timezone.utc).isoformat()

        language_data = {
            "project_id": project_id,
            "language_code": request.language_code,
            "language_name": request.language_name,
            "is_primary": False,
            "story_content": story_content,
            "translation_status": translation_status,
            "created_at": current_time,
            "updated_at": current_time
        }

        logger.info(f"Inserting language entry for {request.language_code}: story_content length = {len(story_content) if story_content else 0}, translation_status = {translation_status}")

        result = supabase.table("video_project_languages").insert(language_data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create language entry")

        logger.info(f"Successfully added language {request.language_code} to project {project_id}")
        logger.info(f"Returned data: story_content length = {len(result.data[0].get('story_content', '')) if result.data[0].get('story_content') else 0}")

        return LanguageResponse(**result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding language: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to add language: {str(e)}")

@router.get("/{project_id}/languages", response_model=List[LanguageResponse])
async def get_project_languages(
    project_id: str,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Get all languages for a video project

    Args:
        project_id: The video project ID
        current_user: Current authenticated user

    Returns:
        List of languages for the project
    """
    try:
        logger.info(f"Fetching languages for project {project_id}")

        supabase_client = SupabaseClient()
        supabase = supabase_client.supabase

        # Verify user owns this project
        project_result = supabase.table("video_projects").select("*").eq("id", project_id).eq("user_id", str(current_user.id)).execute()

        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found or access denied")

        # Get all languages for this project
        languages_result = supabase.table("video_project_languages").select("*").eq("project_id", project_id).order("created_at").execute()

        return [LanguageResponse(**lang) for lang in languages_result.data]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching languages: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch languages: {str(e)}")

@router.put("/{project_id}/languages/{language_code}", response_model=LanguageResponse)
async def update_language_content(
    project_id: str,
    language_code: str,
    request: UpdateLanguageRequest,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Update language content for a video project

    Args:
        project_id: The video project ID
        language_code: The language code to update
        request: Update request data
        current_user: Current authenticated user

    Returns:
        Updated language data
    """
    try:
        logger.info(f"Updating language {language_code} for project {project_id}")

        supabase_client = SupabaseClient()
        supabase = supabase_client.supabase

        # Verify user owns this project
        project_result = supabase.table("video_projects").select("*").eq("id", project_id).eq("user_id", str(current_user.id)).execute()

        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found or access denied")

        # Get the language entry
        lang_result = supabase.table("video_project_languages").select("*").eq("project_id", project_id).eq("language_code", language_code).execute()

        if not lang_result.data:
            raise HTTPException(status_code=404, detail="Language not found for this project")

        # Build update data
        update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}

        if request.story_content is not None:
            update_data["story_content"] = request.story_content

        if request.translation_status is not None:
            update_data["translation_status"] = request.translation_status

        if request.audio_file_id is not None:
            update_data["audio_file_id"] = request.audio_file_id

        if request.video_file_id is not None:
            update_data["video_file_id"] = request.video_file_id

        if request.is_primary is not None:
            # If setting as primary, unset all other languages
            if request.is_primary:
                supabase.table("video_project_languages").update({"is_primary": False}).eq("project_id", project_id).execute()
            update_data["is_primary"] = request.is_primary

        # Update the language entry
        result = supabase.table("video_project_languages").update(update_data).eq("project_id", project_id).eq("language_code", language_code).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update language")

        logger.info(f"Successfully updated language {language_code} for project {project_id}")

        return LanguageResponse(**result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating language: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update language: {str(e)}")

@router.delete("/{project_id}/languages/{language_code}")
async def delete_language(
    project_id: str,
    language_code: str,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Delete a language from a video project

    Args:
        project_id: The video project ID
        language_code: The language code to delete
        current_user: Current authenticated user

    Returns:
        Success message
    """
    try:
        logger.info(f"Deleting language {language_code} from project {project_id}")

        supabase_client = SupabaseClient()
        supabase = supabase_client.supabase

        # Verify user owns this project
        project_result = supabase.table("video_projects").select("*").eq("id", project_id).eq("user_id", str(current_user.id)).execute()

        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found or access denied")

        # Check if this is the primary language
        lang_result = supabase.table("video_project_languages").select("*").eq("project_id", project_id).eq("language_code", language_code).execute()

        if not lang_result.data:
            raise HTTPException(status_code=404, detail="Language not found for this project")

        if lang_result.data[0].get("is_primary"):
            raise HTTPException(status_code=400, detail="Cannot delete the primary language")

        # Delete the language entry
        supabase.table("video_project_languages").delete().eq("project_id", project_id).eq("language_code", language_code).execute()

        logger.info(f"Successfully deleted language {language_code} from project {project_id}")

        return {"message": f"Language {language_code} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting language: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete language: {str(e)}")

@router.get("/audio/{audio_file_id}", response_model=AudioFileResponse)
async def get_audio_file_details(
    audio_file_id: str,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Get audio file details by ID

    This endpoint fetches audio file details from the video_projects table or GCS.
    The audio_file_id is typically the project_id for project-level audio.

    Args:
        audio_file_id: The audio file ID (usually the project ID)
        current_user: Current authenticated user

    Returns:
        Audio file details including URL and duration
    """
    try:
        logger.info(f"Fetching audio file details for ID: {audio_file_id}")

        supabase_client = SupabaseClient()
        supabase = supabase_client.supabase

        # Check if this audio_file_id is actually a project_id
        project_result = supabase.table("video_projects").select("*").eq("id", audio_file_id).eq("user_id", str(current_user.id)).execute()

        if project_result.data:
            # This is a project - get the audio details from the project
            project = project_result.data[0]

            # Get audio URL from GCS
            from services.gcs_service import GCSService
            gcs_service = GCSService()

            # Try to find the audio file in GCS
            audio_prefix = f"audio/{current_user.id}/"

            try:
                # Try direct file paths first (most common case)
                possible_filenames = [
                    f"audio/{current_user.id}/{audio_file_id}.mp3",
                    f"audio/{current_user.id}/{audio_file_id}.wav",
                    f"audio/{current_user.id}/{audio_file_id}.flac"
                ]

                audio_blob = None
                for filename in possible_filenames:
                    blob = gcs_service.bucket.blob(filename)
                    if blob.exists():
                        audio_blob = blob
                        logger.info(f"Found audio file at: {filename}")
                        break

                # If not found, search through all files with STRICT matching
                if not audio_blob:
                    logger.warning(f"⚠️ Direct lookup failed for audio_file_id: {audio_file_id}")
                    logger.info(f"🔍 Searching all files with prefix: {audio_prefix}")
                    blobs = list(gcs_service.bucket.list_blobs(prefix=audio_prefix))

                    for blob in blobs:
                        # STRICT MATCH: Only match if the blob name is exactly "audio/{user_id}/{audio_file_id}.{ext}"
                        # This prevents accidentally matching the wrong audio file
                        expected_mp3 = f"audio/{current_user.id}/{audio_file_id}.mp3"
                        expected_wav = f"audio/{current_user.id}/{audio_file_id}.wav"

                        if blob.name == expected_mp3 or blob.name == expected_wav:
                            audio_blob = blob
                            logger.info(f"✅ Found audio file via strict search: {blob.name}")
                            break
                        else:
                            logger.debug(f"⏭️ Skipping non-matching blob: {blob.name}")

                if not audio_blob:
                    logger.error(f"Audio file not found for ID: {audio_file_id}, searched prefix: {audio_prefix}")
                    raise HTTPException(status_code=404, detail="Audio file not found in storage")

                # Generate signed URL
                audio_url = await gcs_service.generate_signed_url(audio_blob.name)

                # Get duration from project or default to 0
                duration = float(project.get('duration', 0))

                return AudioFileResponse(
                    id=audio_file_id,
                    url=audio_url,
                    duration=duration,
                    projectId=audio_file_id
                )

            except Exception as e:
                logger.error(f"Error fetching audio from GCS: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to fetch audio from storage: {str(e)}")

        else:
            # Not a project - maybe it's a standalone audio file
            # Try to load from TTS service metadata
            tts_service = TTSService()
            audio_file = await tts_service.load_audio_metadata(audio_file_id)

            if audio_file:
                # Verify user has access
                if hasattr(audio_file, '__dict__') and 'user_id' in audio_file.__dict__:
                    if audio_file.__dict__['user_id'] != str(current_user.id):
                        raise HTTPException(status_code=403, detail="Access denied to this audio file")

                return AudioFileResponse(
                    id=str(audio_file.id),
                    url=audio_file.url,
                    duration=audio_file.duration,
                    projectId=str(audio_file.id)
                )

            # Fallback: Try direct GCS lookup for orphaned audio files
            logger.info(f"🔍 Attempting direct GCS lookup for audio file: {audio_file_id}")
            try:
                from services.gcs_service import GCSService
                gcs_service = GCSService()

                if not gcs_service.is_available():
                    logger.error("GCS service not available for direct audio lookup")
                    raise HTTPException(status_code=404, detail="Audio file not found")

                # Try common audio file paths
                possible_paths = [
                    f"audio/{current_user.id}/{audio_file_id}.mp3",
                    f"audio/{current_user.id}/{audio_file_id}.wav"
                ]

                audio_blob = None
                found_path = None
                for path in possible_paths:
                    blob = gcs_service.bucket.blob(path)
                    if blob.exists():
                        audio_blob = blob
                        found_path = path
                        logger.info(f"✅ Found audio file via direct GCS lookup: {path}")
                        break

                if not audio_blob:
                    logger.error(f"❌ Audio file not found in GCS at paths: {possible_paths}")
                    raise HTTPException(status_code=404, detail="Audio file not found in storage")

                # Generate signed URL (no local file fallback)
                signed_url = await gcs_service.generate_signed_url(found_path)

                if not signed_url:
                    logger.error(f"❌ Failed to generate signed URL for: {found_path}")
                    raise HTTPException(status_code=500, detail="Failed to generate audio URL")

                logger.info(f"✅ Generated signed URL for audio file: {audio_file_id}")

                return AudioFileResponse(
                    id=audio_file_id,
                    url=signed_url,
                    duration=0.0,  # Unknown duration for orphaned files
                    projectId=audio_file_id
                )

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"❌ Error during direct GCS audio lookup: {str(e)}")
                raise HTTPException(status_code=404, detail="Audio file not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching audio file details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch audio file details: {str(e)}")
