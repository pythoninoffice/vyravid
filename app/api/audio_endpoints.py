"""
Audio file upload API endpoints
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, status
from typing import Optional
from pydantic import BaseModel
import uuid
import logging
from datetime import datetime, timezone, timedelta
import mimetypes
import os

from services.gcs_service import get_gcs_service
from auth import get_current_user
from models.story_models import AudioFile, VoiceSettings, AudioSettings, GenerationStatus
from models.video_project_models import VideoProjectCreate
from repositories.video_project_repository import VideoProjectRepository
from services.tts_service import TTSService

router = APIRouter(prefix="/api/audio", tags=["audio-upload"])
logger = logging.getLogger(__name__)

class AudioUploadResponse(BaseModel):
    id: str
    filename: str
    original_name: str
    file_size: int
    duration: Optional[float] = None
    mime_type: str
    gcs_path: str
    signed_url: str
    upload_date: str
    project_id: Optional[str] = None

@router.post("/upload", response_model=AudioUploadResponse)
async def upload_audio(
    file: UploadFile = File(..., description="Audio file to upload"),
    project_id: Optional[str] = Form(None, description="Optional project ID to associate audio with existing draft"),
    language_code: Optional[str] = Form("en", description="Language code for the audio (default: en)"),
    current_user: dict = Depends(get_current_user)
) -> AudioUploadResponse:
    """
    Upload audio file to Google Cloud Storage for video generation

    Supports MP3, WAV, M4A, OGG formats
    Maximum file size: 50MB

    Smart project linking:
    - If project_id is provided, updates that specific draft project
    - If not provided, automatically links to the most recent draft/audio_ready project within 2 hours
    - Creates new project only if no recent projects exist

    Language support:
    - language_code parameter determines the language of the uploaded audio (default: 'en')
    - This creates language-specific transcript files for multi-language support
    """
    
    # Validate file type
    if not file.content_type or not file.content_type.startswith('audio/'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an audio file"
        )
    
    # Validate file size (50MB limit)
    max_size = 200 * 1024 * 1024  # 50MB
    file_content = await file.read()
    file_size = len(file_content)
    
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {max_size // (1024*1024)}MB"
        )
    
    # Reset file position for further reading
    await file.seek(0)

    user_id = current_user.get('id') or current_user.get('user_id')
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token"
        )

    logger.info(f"🎤 Uploading audio file for language: {language_code}, project_id: {project_id}")

    try:
        # Get GCS service
        gcs_service = get_gcs_service()
        
        # Determine project_id first to use as audio_id (for consistent naming)
        temp_project_id = project_id
        if not temp_project_id:
            # Check for recent draft project
            try:
                from db.supabase_client import supabase_client
                video_project_repo = VideoProjectRepository(supabase_client)

                if isinstance(user_id, str):
                    user_uuid = uuid.UUID(user_id)
                else:
                    user_uuid = user_id

                user_projects = await video_project_repo.get_by_user_id(user_uuid, limit=5)
                for project in user_projects:
                    if (project.status in ["draft", "audio_ready"] and
                        project.created_at and
                        (datetime.now(timezone.utc) - project.created_at).total_seconds() < 7200):
                        temp_project_id = str(project.id)
                        break
            except:
                pass

        # Use project_id as audio_id if available, otherwise generate new UUID
        # This ensures audio file is overwritten for the same project
        file_id = temp_project_id if temp_project_id else str(uuid.uuid4())
        file_extension = os.path.splitext(file.filename or "audio.mp3")[1].lstrip('.')

        logger.info(f"📁 Using audio_id: {file_id} (project_id: {temp_project_id})")

        # Upload to GCS using the existing audio upload method
        upload_result = await gcs_service.upload_audio_bytes(
            audio_bytes=file_content,
            user_id=str(user_id),
            file_extension=file_extension,
            audio_id=file_id,  # Using project_id ensures overwrite
            metadata={
                'original_filename': file.filename or "audio.mp3",
                'file_size': file_size,
                'content_type': file.content_type,
                'upload_source': 'user_upload'
            }
        )
        
        if not upload_result:
            raise Exception("Failed to upload audio to GCS")
        
        # Extract filename from gcs_path
        gcs_filename = upload_result['gcs_path'].split('/')[-1]
        
        # Create AudioFile record in the database (similar to generated audio)
        try:
            # Create voice and audio settings for the uploaded file
            voice_settings = VoiceSettings(
                voice_id="uploaded_audio",  # Special identifier for uploaded audio
                speed=1.0,
                volume=1.0,
                pitch=0.0
            )
            
            audio_settings = AudioSettings(
                sample_rate=16000,
                bitrate=128000,
                format=file_extension,
                channel=1
            )
            
            # Create AudioFile record
            audio_file = AudioFile(
                id=uuid.UUID(file_id),
                file_path=upload_result['gcs_path'],
                duration=None,  # Will be set client-side
                format=file_extension,
                voice_settings=voice_settings,
                audio_settings=audio_settings,
                status=GenerationStatus.COMPLETED,  # Uploaded files are immediately ready
                created_at=datetime.now(),
                url=upload_result['signed_url'],
                gcs_path=upload_result['gcs_path']
            )
            
            # Save AudioFile using TTS service (to maintain consistency)
            tts_service = TTSService()
            await tts_service._save_audio_metadata(audio_file)
            
            logger.info(f"✅ Created AudioFile record: {file_id}")
            
        except Exception as audio_record_error:
            logger.warning(f"⚠️ Failed to create AudioFile record: {str(audio_record_error)}")
            # Continue anyway - the upload succeeded, just the record creation failed
        
        # Handle VideoProject - update existing draft or create new project
        final_project_id = None
        try:
            from db.supabase_client import supabase_client
            video_project_repo = VideoProjectRepository(supabase_client)

            # Handle user_id conversion
            if isinstance(user_id, str):
                user_uuid = uuid.UUID(user_id)
            else:
                user_uuid = user_id

            if project_id:
                # Try to update existing project with audio file
                try:
                    existing_project = await video_project_repo.get_by_id(uuid.UUID(project_id))
                    if existing_project and existing_project.user_id == user_uuid:
                        # Update existing project with audio file
                        from models.video_project_models import VideoProjectUpdate
                        update_data = VideoProjectUpdate(
                            status="audio_ready",
                            audio_file_id=file_id,
                            file_size=file_size,
                            processing_options={
                                **existing_project.processing_options,
                                "audio_uploaded": True,
                                "mode": "uploaded_audio"
                            }
                        )
                        updated_project = await video_project_repo.update(uuid.UUID(project_id), update_data)
                        final_project_id = project_id
                        logger.info(f"✅ Updated existing project {project_id} with uploaded audio {file_id}")
                    else:
                        logger.warning(f"⚠️ Project {project_id} not found or access denied, creating new project")
                        project_id = None  # Fall back to creating new project
                except Exception as e:
                    logger.warning(f"⚠️ Failed to update existing project {project_id}: {str(e)}, creating new project")
                    project_id = None  # Fall back to creating new project

            if not project_id:
                # Auto-link to the most recent draft project for this user
                try:
                    # Get the most recent project for this user
                    user_projects = await video_project_repo.get_by_user_id(user_uuid, limit=5)
                    most_recent_draft = None

                    # Find the most recent draft or audio_ready project (within reasonable time)
                    for project in user_projects:
                        if (project.status in ["draft", "audio_ready"] and
                            project.created_at and
                            (datetime.now(timezone.utc) - project.created_at).total_seconds() < 7200):  # Within last 2 hours
                            most_recent_draft = project
                            break  # Projects are ordered by creation time, so first match is most recent

                    if most_recent_draft:
                        # Update the most recent draft with audio file
                        from models.video_project_models import VideoProjectUpdate

                        # Preserve existing processing options and add audio info
                        updated_options = most_recent_draft.processing_options.copy() if most_recent_draft.processing_options else {}
                        updated_options.update({
                            "audio_uploaded": True,
                            "mode": "uploaded_audio"
                        })

                        update_data = VideoProjectUpdate(
                            status="audio_ready",
                            audio_file_id=file_id,
                            file_size=file_size,
                            processing_options=updated_options
                        )
                        await video_project_repo.update(most_recent_draft.id, update_data)
                        final_project_id = str(most_recent_draft.id)
                        logger.info(f"✅ Auto-linked audio {file_id} to most recent project: {final_project_id} (was: {most_recent_draft.status})")

                        # Delete old transcript files when new audio is uploaded to existing project
                        try:
                            import asyncio
                            # Delete language-specific transcript files for the current language
                            transcript_path = f"output/{user_id}/{final_project_id}/raw_transcript_data_{language_code}.txt"
                            sentences_path = f"output/{user_id}/{final_project_id}/transcript_sentences.json"
                            # Also delete non-language-specific files for backward compatibility
                            transcript_path_legacy = f"output/{user_id}/{final_project_id}/raw_transcript_data.txt"

                            logger.info(f"🗑️ Cleaning up old transcript files for project {final_project_id} (language: {language_code})")
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(None, gcs_service._delete_file_sync, transcript_path)
                            await loop.run_in_executor(None, gcs_service._delete_file_sync, transcript_path_legacy)
                            await loop.run_in_executor(None, gcs_service._delete_file_sync, sentences_path)
                            logger.info(f"✅ Deleted old transcript files for language {language_code}")
                        except Exception as cleanup_error:
                            logger.warning(f"⚠️ Failed to cleanup old transcript files: {str(cleanup_error)}")
                    else:
                        # No recent project found, create new project
                        project_data = VideoProjectCreate(
                            user_id=user_uuid,
                            title=f"Uploaded Audio Video {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                            status="audio_ready",
                            duration=0.0,  # Will be updated when duration is known
                            file_size=file_size,
                            processing_options={"mode": "uploaded_audio", "audio_uploaded": True},
                            audio_file_id=file_id
                        )

                        project = await video_project_repo.create(project_data)
                        final_project_id = str(project.id)
                        logger.info(f"✅ No recent drafts found, created new VideoProject: {final_project_id}")

                except Exception as e:
                    logger.warning(f"⚠️ Failed to auto-link to recent project: {str(e)}, creating new project")
                    # Fallback to creating new project
                    project_data = VideoProjectCreate(
                        user_id=user_uuid,
                        title=f"Uploaded Audio Video {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                        status="audio_ready",
                        duration=0.0,
                        file_size=file_size,
                        processing_options={"mode": "uploaded_audio", "audio_uploaded": True},
                        audio_file_id=file_id
                    )

                    project = await video_project_repo.create(project_data)
                    final_project_id = str(project.id)
                    logger.info(f"✅ Created fallback VideoProject: {final_project_id}")

            # Note: AudioFile model doesn't have project_id field
            # The project association is managed through the VideoProject model

        except Exception as project_error:
            logger.error(f"⚠️ Failed to handle VideoProject: {str(project_error)}", exc_info=True)
            # Use audio file ID as fallback project ID
            final_project_id = file_id
            logger.warning(f"⚠️ Using audio file ID as fallback project ID: {final_project_id}")

        logger.info(f"📋 Final project ID for transcription: {final_project_id}")

        # Automatically transcribe the uploaded audio
        try:
            logger.info(f"🎤 Starting automatic transcription for uploaded audio file {file_id}")
            from services.transcription_service import TranscriptionServiceSelector

            transcription_selector = TranscriptionServiceSelector()

            # Local Vyravid: faster-whisper (no cloud; works with /media localhost paths)
            transcription_config = {
                "service": "faster-whisper",
                "caption_style": "karaoke",
                "font_size": 52,
                "font_family": "Arial",
                "position": "bottom",
                "default_color": "&HFFFFFF",
                "highlight_color": "&H00FFFF"
            }

            # Prefer local path over URL so whisper never needs a public host
            audio_ref = upload_result.get("gcs_path") or upload_result.get("signed_url")
            await transcription_selector.transcribe_with_service(
                audio_url=audio_ref,
                service_name="faster-whisper",
                config=transcription_config,
                user_id=str(user_id),
                job_id=final_project_id,
                user_input_text=None,
                language_code=language_code,
            )
            logger.info(f"✅ Transcription completed (faster-whisper) for uploaded audio file {file_id}")

        except Exception as transcription_error:
            # Log the error but don't fail the audio upload
            logger.error(f"⚠️ Failed to start transcription for uploaded audio file {file_id}: {str(transcription_error)}")
            logger.warning("⚠️ Audio upload succeeded but transcription failed - continuing")

        # Update language-specific audio_file_id if language_code is provided and it's not the primary language
        if language_code and final_project_id:
            try:
                logger.info(f"🌐 Updating language record for {language_code} with audio_file_id: {file_id}")
                from db.supabase_client import supabase_client as sb_client
                supabase = sb_client.supabase

                # First check if this language exists and is not primary
                lang_check = supabase.table("video_project_languages")\
                    .select("is_primary, audio_file_id")\
                    .eq("project_id", final_project_id)\
                    .eq("language_code", language_code)\
                    .execute()

                if lang_check.data and len(lang_check.data) > 0:
                    lang_record = lang_check.data[0]
                    is_primary = lang_record.get("is_primary", False)

                    if not is_primary:
                        # Update the video_project_languages table with the audio_file_id
                        result = supabase.table("video_project_languages")\
                            .update({"audio_file_id": str(file_id)})\
                            .eq("project_id", final_project_id)\
                            .eq("language_code", language_code)\
                            .execute()

                        if result.data:
                            logger.info(f"✅ Updated language {language_code} with audio_file_id: {file_id}")
                        else:
                            logger.warning(f"⚠️ Failed to update language record for {language_code}")
                    else:
                        logger.info(f"ℹ️ Skipping language table update for primary language {language_code} (stored in video_projects table)")
                else:
                    logger.warning(f"⚠️ No language record found for {language_code} in project {final_project_id}")

            except Exception as lang_update_error:
                logger.error(f"❌ Failed to update language record: {str(lang_update_error)}")
                # Don't fail the whole request, just log the error

        logger.info(f"Audio uploaded successfully: {upload_result['gcs_path']}")

        response = AudioUploadResponse(
            id=file_id,
            filename=gcs_filename,
            original_name=file.filename or "audio.mp3",
            file_size=file_size,
            duration=None,  # Will be set client-side
            mime_type=file.content_type,
            gcs_path=upload_result['gcs_path'],
            signed_url=upload_result['signed_url'],
            upload_date=upload_result['uploaded_at'],
            project_id=final_project_id
        )

        logger.info(f"🎯 Returning upload response with project_id={final_project_id}, audio_id={file_id}")
        return response
        
    except Exception as e:
        logger.error(f"Error uploading audio: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload audio file: {str(e)}"
        )

@router.get("/{audio_id}")
async def get_audio_file(
    audio_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get audio file details by ID
    """
    try:
        # Get the audio file from database
        tts_service = TTSService()
        audio_file = await tts_service.load_audio_metadata(audio_id)

        if not audio_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Audio file not found: {audio_id}"
            )

        logger.info(f"📂 Retrieved audio file {audio_id}: {audio_file.file_path}")

        return {
            "id": audio_file.id,
            "file_url": audio_file.url,
            "url": audio_file.url,
            "duration": audio_file.duration,
            "file_path": audio_file.file_path,
            "status": audio_file.status
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving audio file {audio_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audio file: {str(e)}"
        )

@router.post("/refresh-url/{audio_id}")
async def refresh_audio_url(
    audio_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Refresh the signed URL for an audio file
    """
    user_id = current_user.get('id') or current_user.get('user_id')
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token"
        )

    try:
        # Get the audio file from database to get the GCS path
        tts_service = TTSService()
        audio_file = await tts_service.load_audio_metadata(audio_id)

        if not audio_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Audio file not found: {audio_id}"
            )

        # Generate new signed URL with 24 hour expiration
        gcs_service = get_gcs_service()
        new_signed_url = await gcs_service.generate_signed_url(
            audio_file.gcs_path,
            expiration_hours=24
        )

        if not new_signed_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate signed URL"
            )

        # Calculate expiry time (24 hours from now)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        logger.info(f"✅ Refreshed audio URL for {audio_id}, expires at {expires_at.isoformat()}")

        return {
            "signed_url": new_signed_url,
            "expires_at": expires_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing audio URL: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh audio URL: {str(e)}"
        )
