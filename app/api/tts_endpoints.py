from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse
from typing import Optional
from pydantic import BaseModel
import uuid
import os
import tempfile
import subprocess
from datetime import datetime, timezone, timedelta

from services.tts_service import TTSService
from services.tts_factory import get_tts_service, TTSServiceFactory, TTSProvider
from services.transcription_service import TranscriptionServiceSelector
from models.story_models import AudioFile, VoiceSettings, AudioSettings, GenerationStatus
from models.video_project_models import VideoProjectCreate
from models.custom_voice_models import CustomVoiceCreate, CustomVoiceResponse, CustomVoiceListResponse
from repositories.video_project_repository import VideoProjectRepository
from services.supabase import get_supabase_client
from middleware.auth_middleware import get_current_user
import structlog

logger = structlog.get_logger(__name__)


def _is_missing_column_error(error: Exception, column_name: str) -> bool:
    return column_name in str(error) and ("does not exist" in str(error) or "42703" in str(error))


def _can_use_provider_column(supabase_client) -> bool:
    try:
        supabase_client.table('custom_voices').select('provider').limit(1).execute()
        return True
    except Exception as error:
        if _is_missing_column_error(error, 'provider'):
            return False
        raise


router = APIRouter(prefix="/api/generate", tags=["text-to-speech"])
tts_service = TTSService()

# Constants for voice cloning
MAX_CUSTOM_VOICES = 5   # Maximum voices per user
MIN_AUDIO_DURATION = 40  # Seconds
MAX_AUDIO_DURATION = 90  # Seconds (1.5 minutes)
MINIMAX_MIN_AUDIO_DURATION = 10  # Seconds
MINIMAX_MAX_AUDIO_DURATION = 300  # Seconds (5 minutes)
MINIMAX_MAX_AUDIO_SIZE = 20 * 1024 * 1024  # 20MB

class TTSRequest(BaseModel):
    text: str
    processed_story_id: Optional[str] = ""
    voice_settings: Optional[VoiceSettings] = None
    audio_settings: Optional[AudioSettings] = None
    use_async: bool = False
    force_method: Optional[str] = None  # 'sync', 'async', 'long_async', or None for auto
    wait_for_completion: bool = False  # If True, wait for async TTS to complete before returning
    tts_provider: Optional[str] = "minimax"  # 'minimax' or 'google'

class TTSResponse(BaseModel):
    audio_file: AudioFile
    message: str

class TimelineAudioRequest(BaseModel):
    text: str
    voice_id: str
    project_title: Optional[str] = None
    voice_settings: Optional[VoiceSettings] = None
    audio_settings: Optional[AudioSettings] = None
    tts_provider: Optional[str] = "minimax"  # 'minimax' or 'google'
    user_input_text: Optional[str] = None  # User's original input text from editor
    audio_speed: Optional[float] = 1.0  # Audio speed multiplier (0.5x to 2.0x)
    language_code: Optional[str] = None  # Language code for multi-language support
    voice_system_prompt: Optional[str] = None  # Custom voice system prompt for TTS

class TimelineAudioResponse(BaseModel):
    audio_file: AudioFile
    project_id: str
    message: str

@router.post("/audio", response_model=TTSResponse)
async def generate_audio(request: TTSRequest) -> TTSResponse:
    """
    Convert text to speech

    Args:
        request: TTS request with text and settings

    Returns:
        AudioFile information and generation status
    """
    try:
        if len(request.text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text cannot be empty")

        if len(request.text) > 1000000:  # Updated limit for long TTS support
            raise HTTPException(status_code=400, detail="Text too long (max 1,000,000 characters)")

        if request.tts_provider not in ("minimax", "google"):
            raise HTTPException(status_code=400, detail="Unsupported TTS provider. Use 'minimax' or 'google'.")

        # Get the appropriate TTS service based on provider
        tts_service = get_tts_service(request.tts_provider)

        # Google TTS uses the Gemini API and handles the method internally.
        if request.tts_provider == "google":
            audio_file = await tts_service.text_to_speech_auto(
                text=request.text,
                voice_settings=request.voice_settings,
                audio_settings=request.audio_settings,
                processed_story_id=request.processed_story_id
            )
            provider_name = request.tts_provider.capitalize()
            message = f"{provider_name} audio generation completed successfully"
            return TTSResponse(audio_file=audio_file, message=message)

        # Use automatic method selection or forced method for Minimax
        if request.force_method:
            if request.force_method == 'sync':
                audio_file = await tts_service.text_to_speech_sync(
                    text=request.text,
                    voice_settings=request.voice_settings,
                    audio_settings=request.audio_settings,
                    processed_story_id=request.processed_story_id
                )
                message = "Synchronous audio generation completed successfully"
            elif request.force_method == 'async':
                audio_file = await tts_service.text_to_speech_async(
                    text=request.text,
                    voice_settings=request.voice_settings,
                    audio_settings=request.audio_settings,
                    processed_story_id=request.processed_story_id
                )
                message = f"Async TTS generation started. Task ID: {audio_file.task_id}"
            elif request.force_method == 'long_async':
                audio_file = await tts_service.text_to_speech_async_long(
                    text=request.text,
                    voice_settings=request.voice_settings,
                    audio_settings=request.audio_settings,
                    processed_story_id=request.processed_story_id
                )
                message = f"Long async TTS generation started. Task ID: {audio_file.task_id}"
            else:
                raise HTTPException(status_code=400, detail="Invalid force_method. Use 'sync', 'async', or 'long_async'")
        elif request.use_async:
            # Legacy support for use_async parameter
            audio_file = await tts_service.text_to_speech_async(
                text=request.text,
                voice_settings=request.voice_settings,
                audio_settings=request.audio_settings,
                processed_story_id=request.processed_story_id
            )
            message = f"Async TTS generation started. Task ID: {audio_file.task_id}"
        else:
            # Use automatic method selection
            if request.wait_for_completion:
                # Wait for completion regardless of method used
                audio_file = await tts_service.text_to_speech_auto_and_wait(
                    text=request.text,
                    voice_settings=request.voice_settings,
                    audio_settings=request.audio_settings,
                    processed_story_id=request.processed_story_id,
                    max_wait_time=600  # 10 minutes timeout
                )
                message = "Audio generation completed successfully"
            else:
                # Don't wait, return immediately
                audio_file = await tts_service.text_to_speech_auto(
                    text=request.text,
                    voice_settings=request.voice_settings,
                    audio_settings=request.audio_settings,
                    processed_story_id=request.processed_story_id
                )
                
                if audio_file.status == GenerationStatus.COMPLETED:
                    message = "Audio generation completed successfully"
                else:
                    message = f"TTS generation started. Task ID: {audio_file.task_id}"
        
        return TTSResponse(audio_file=audio_file, message=message)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating audio: {str(e)}")

@router.get("/audio/{audio_id}/status", response_model=AudioFile)
async def get_audio_status(audio_id: str, provider: str = "minimax") -> AudioFile:
    """
    Get the status of an audio generation task

    Args:
        audio_id: ID of the audio file
        provider: TTS provider used ('minimax', 'deepgram', or 'google')

    Returns:
        Updated AudioFile object
    """
    try:
        if provider not in ("minimax", "google"):
            raise HTTPException(status_code=400, detail="Unsupported TTS provider. Use 'minimax' or 'google'.")
        tts_service = get_tts_service(provider)
        audio_file = await tts_service.load_audio_metadata(audio_id)

        if not audio_file:
            raise HTTPException(status_code=404, detail="Audio file not found")

        # If it's an async task that's still generating, check status (Minimax only)
        if (provider == "minimax" and
            audio_file.status == GenerationStatus.GENERATING and
            audio_file.task_id):
            audio_file = await tts_service.check_async_status(audio_file)

        return audio_file

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking audio status: {str(e)}")

@router.get("/audio/{audio_id}/preview")
async def get_audio_preview(audio_id: str):
    """
    Get audio file preview information
    
    Args:
        audio_id: ID of the audio file
    
    Returns:
        Audio file preview information
    """
    try:
        audio_file = await tts_service.load_audio_metadata(audio_id)
        
        if not audio_file:
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        preview_info = await tts_service.get_audio_preview_info(audio_file)
        return preview_info
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting audio preview: {str(e)}")

@router.get("/audio/{audio_id}/download")
async def download_audio(audio_id: str):
    """
    Download generated audio file
    
    Args:
        audio_id: ID of the audio file
    
    Returns:
        Audio file for download
    """
    try:
        audio_file = await tts_service.load_audio_metadata(audio_id)
        
        if not audio_file:
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        if audio_file.status != GenerationStatus.COMPLETED:
            raise HTTPException(status_code=400, detail=f"Audio file not ready. Status: {audio_file.status}")
        
        # Check if file exists
        from pathlib import Path
        file_path = Path(audio_file.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Audio file not found on disk")
        
        return FileResponse(
            path=str(file_path),
            filename=f"audio_{audio_id}.{audio_file.format}",
            media_type=f"audio/{audio_file.format}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading audio: {str(e)}")

@router.get("/voices")
async def get_available_voices(provider: str = None):
    """
    Get list of available voice options

    Args:
        provider: Filter by TTS provider ('minimax', 'google', or None for all)

    Returns:
        List of available voices and their settings
    """
    try:
        if provider:
            tts_provider = TTSProvider(provider.lower())
            voices = TTSServiceFactory.get_available_voices(tts_provider)
        else:
            voices = TTSServiceFactory.get_available_voices()

        # Add additional metadata for Minimax voices
        minimax_extras = {
            "emotions": ["neutral", "happy", "sad", "angry", "surprised", "fearful"],
            "speed_range": {"min": 0.5, "max": 2.0, "default": 1.0},
            "volume_range": {"min": 0.1, "max": 2.0, "default": 1.0},
            "pitch_range": {"min": -1.0, "max": 1.0, "default": 0.0}
        }

        return {
            "voices": voices,
            "providers": ["minimax", "google"],
            "minimax_extras": minimax_extras
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting voices: {str(e)}")


@router.get("/elevenlabs/voice-preview/{voice_id}")
async def get_elevenlabs_voice_preview(voice_id: str):
    """
    Get ElevenLabs voice preview.

    First tries to fetch the voice's built-in preview_url.
    If that fails (voice not found, no permissions, etc.), falls back to
    generating a short TTS sample using the voice.

    Args:
        voice_id: The ElevenLabs voice ID

    Returns:
        Preview URL (either ElevenLabs hosted or base64 data URL)
    """
    raise HTTPException(status_code=410, detail="ElevenLabs is disabled in local mode. Use MiniMax voice cloning.")

    try:
        import os
        api_key = os.getenv('ELEVENLABS_API_KEY')
        if not api_key:
            raise HTTPException(status_code=500, detail="ElevenLabs API key not configured")

        client = ElevenLabs(api_key=api_key)

        # First, try to get the voice's built-in preview URL
        try:
            voice = client.voices.get(voice_id=voice_id)
            if voice and voice.preview_url:
                logger.info(f"Found preview URL for voice {voice_id}: {voice.name}")
                return {
                    "voice_id": voice_id,
                    "name": voice.name,
                    "preview_url": voice.preview_url
                }
        except Exception as voice_error:
            logger.warning(f"Could not fetch voice details for {voice_id}: {str(voice_error)}")
            # Fall through to generate a sample

        # Fallback: Generate a short sample using TTS
        logger.info(f"Generating TTS sample for voice {voice_id}")
        sample_text = "Hello! This is a preview of my voice. I hope you like how I sound."

        response = client.text_to_speech.convert_with_timestamps(
            text=sample_text,
            voice_id=voice_id,
            model_id="eleven_turbo_v2_5",
            output_format="mp3_44100_128"
        )

        # Return base64 audio data as a data URL for direct playback
        audio_base64 = response.audio_base_64
        data_url = f"data:audio/mpeg;base64,{audio_base64}"

        return {
            "voice_id": voice_id,
            "preview_url": data_url
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ElevenLabs voice preview: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting voice preview: {str(e)}")


@router.post("/elevenlabs/clone-voice", response_model=CustomVoiceResponse)
async def clone_custom_voice(
    voice_name: str = Form(...),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    supabase_client = Depends(get_supabase_client)
):
    """
    Upload audio sample and clone voice.

    Limit: 5 voices per user
    Audio: 40 seconds to 1.5 minutes, MP3/WAV/M4A/OGG, max 50MB
    """
    raise HTTPException(status_code=410, detail="ElevenLabs is disabled in local mode. Use /api/generate/minimax/clone-voice.")

    user_id = current_user.id

    # 1. Check voice count limit (5 max)
    existing_voices = supabase_client.table('custom_voices')\
        .select('id')\
        .eq('user_id', user_id)\
        .eq('status', 'completed')\
        .execute()

    if len(existing_voices.data) >= MAX_CUSTOM_VOICES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_CUSTOM_VOICES} custom voices reached. Delete a voice to add a new one."
        )

    # 2. Validate file
    if not file.content_type or not file.content_type.startswith('audio/'):
        raise HTTPException(status_code=400, detail="File must be an audio file")

    file_extension = file.filename.split('.')[-1].lower()
    if file_extension not in ['mp3', 'wav', 'm4a', 'ogg']:
        raise HTTPException(status_code=400, detail="Supported formats: MP3, WAV, M4A, OGG")

    # Read audio bytes
    audio_bytes = await file.read()

    if len(audio_bytes) > 50 * 1024 * 1024:  # 50MB
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    # 4. Validate audio duration
    with tempfile.NamedTemporaryFile(suffix=f'.{file_extension}', delete=False) as temp_file:
        temp_file.write(audio_bytes)
        temp_path = temp_file.name

    try:
        # Get duration using ffprobe
        cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', temp_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        duration = float(result.stdout.strip())

        if duration < MIN_AUDIO_DURATION or duration > MAX_AUDIO_DURATION:
            os.unlink(temp_path)
            raise HTTPException(
                status_code=400,
                detail=f"Audio duration must be between 40 seconds and 1.5 minutes. Your audio is {duration:.1f} seconds."
            )
    except (subprocess.CalledProcessError, ValueError) as e:
        os.unlink(temp_path)
        raise HTTPException(status_code=400, detail="Could not validate audio duration")
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    # 5. Upload to GCS
    voice_record_id = str(uuid.uuid4())

    from services.gcs_service import get_gcs_service
    gcs_service = get_gcs_service()

    gcs_result = await gcs_service.upload_audio_bytes(
        audio_bytes=audio_bytes,
        user_id=user_id,
        file_extension=file_extension,
        audio_id=voice_record_id,
        metadata={
            'purpose': 'voice_clone_sample',
            'voice_name': voice_name,
            'duration': duration
        }
    )

    # 6. Clone voice with ElevenLabs
    elevenlabs_service = get_elevenlabs_service()

    clone_result = await elevenlabs_service.clone_voice(
        voice_name=voice_name,
        audio_bytes=audio_bytes,
        description=description
    )

    if not clone_result['success']:
        # Rollback: delete GCS file
        await gcs_service.delete_video(gcs_result['gcs_path'])
        raise HTTPException(status_code=500, detail=f"Voice cloning failed: {clone_result['error']}")

    # 7. Save to database
    voice_data = {
        'id': voice_record_id,
        'user_id': user_id,
        'elevenlabs_voice_id': clone_result['voice_id'],
        'provider': 'elevenlabs',
        'voice_name': voice_name,
        'description': description,
        'sample_audio_gcs_path': gcs_result['gcs_path'],
        'sample_audio_signed_url': gcs_result['signed_url'],
        'sample_audio_signed_url_expires_at': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        'sample_duration_seconds': duration,
        'status': 'completed'
    }

    try:
        logger.info(f"Attempting to insert voice data: {voice_data}")
        result = supabase_client.table('custom_voices').insert(voice_data).execute()

        logger.info(f"Database insert result: {result}")

        if not result.data:
            raise Exception("Database insert failed - no data returned")

        logger.info(f"✅ Custom voice created: {voice_name} (ID: {clone_result['voice_id']})")

        return CustomVoiceResponse(
            id=voice_record_id,
            voice_name=voice_name,
            description=description,
            provider='elevenlabs',
            voice_id=clone_result['voice_id'],
            elevenlabs_voice_id=clone_result['voice_id'],
            status='completed',
            preview_url=gcs_result['signed_url'],
            created_at=datetime.now(timezone.utc).isoformat()
        )

    except Exception as db_error:
        logger.error(f"❌ Database error: {type(db_error).__name__}: {str(db_error)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Rollback: delete ElevenLabs voice and GCS file
        await elevenlabs_service.delete_cloned_voice(clone_result['voice_id'])
        await gcs_service.delete_video(gcs_result['gcs_path'])
        raise HTTPException(status_code=500, detail=f"Failed to save voice: {str(db_error)}")


@router.get("/elevenlabs/custom-voices", response_model=CustomVoiceListResponse)
async def list_custom_voices(
    current_user: dict = Depends(get_current_user),
    supabase_client = Depends(get_supabase_client)
):
    """List user's custom voices with auto-refresh of expired URLs"""
    raise HTTPException(status_code=410, detail="ElevenLabs is disabled in local mode. Use /api/generate/minimax/custom-voices.")

    user_id = current_user.id

    result = supabase_client.table('custom_voices')\
        .select('*')\
        .eq('user_id', user_id)\
        .eq('status', 'completed')\
        .order('created_at', desc=True)\
        .execute()

    voices = []
    from services.gcs_service import get_gcs_service
    gcs_service = get_gcs_service()

    for voice_data in result.data:
        # Check if signed URL needs refresh (within 1 hour of expiry)
        expires_at = datetime.fromisoformat(voice_data['sample_audio_signed_url_expires_at'].replace('Z', '+00:00'))
        if datetime.now(timezone.utc) >= expires_at - timedelta(hours=1):
            # Refresh signed URL
            new_signed_url = await gcs_service.generate_signed_url(
                voice_data['sample_audio_gcs_path'],
                expiration_hours=24
            )

            # Update in database
            supabase_client.table('custom_voices')\
                .update({
                    'sample_audio_signed_url': new_signed_url,
                    'sample_audio_signed_url_expires_at': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
                })\
                .eq('id', voice_data['id'])\
                .execute()

            voice_data['sample_audio_signed_url'] = new_signed_url

        voices.append(CustomVoiceResponse(
            id=voice_data['id'],
            voice_name=voice_data['voice_name'],
            description=voice_data.get('description'),
            provider=voice_data.get('provider') or 'elevenlabs',
            voice_id=voice_data['elevenlabs_voice_id'],
            elevenlabs_voice_id=voice_data['elevenlabs_voice_id'],
            status=voice_data['status'],
            preview_url=voice_data['sample_audio_signed_url'],
            created_at=voice_data['created_at']
        ))

    return CustomVoiceListResponse(
        voices=voices,
        total_count=len(voices),
        max_voices=MAX_CUSTOM_VOICES
    )


@router.post("/minimax/clone-voice", response_model=CustomVoiceResponse)
async def clone_minimax_custom_voice(
    voice_name: str = Form(...),
    description: Optional[str] = Form(None),
    preview_text: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    supabase_client = Depends(get_supabase_client)
):
    """
    Upload audio sample and clone a MiniMax voice.

    Limit: 5 voices per user
    Audio: 10 seconds to 5 minutes, MP3/WAV/M4A, max 20MB
    """
    user_id = current_user.id

    has_provider_column = _can_use_provider_column(supabase_client)

    existing_query = supabase_client.table('custom_voices')\
        .select('id,provider' if has_provider_column else 'id')\
        .eq('user_id', user_id)\
        .eq('status', 'completed')

    if has_provider_column:
        existing_query = existing_query.eq('provider', 'minimax')

    existing_voices = existing_query.execute()
    minimax_voice_count = len(existing_voices.data or [])

    if minimax_voice_count >= MAX_CUSTOM_VOICES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_CUSTOM_VOICES} MiniMax custom voices reached. Delete a voice to add a new one."
        )

    if not file.content_type or not file.content_type.startswith('audio/'):
        raise HTTPException(status_code=400, detail="File must be an audio file")

    file_extension = (file.filename or '').split('.')[-1].lower()
    if file_extension not in ['mp3', 'wav', 'm4a']:
        raise HTTPException(status_code=400, detail="MiniMax supports MP3, WAV, and M4A audio files")

    audio_bytes = await file.read()

    if len(audio_bytes) > MINIMAX_MAX_AUDIO_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 20MB for MiniMax voice cloning)")

    with tempfile.NamedTemporaryFile(suffix=f'.{file_extension}', delete=False) as temp_file:
        temp_file.write(audio_bytes)
        temp_path = temp_file.name

    try:
        cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', temp_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        duration = float(result.stdout.strip())

        if duration < MINIMAX_MIN_AUDIO_DURATION or duration > MINIMAX_MAX_AUDIO_DURATION:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"MiniMax audio duration must be between 10 seconds and 5 minutes. "
                    f"Your audio is {duration:.1f} seconds."
                )
            )
    except HTTPException:
        raise
    except (subprocess.CalledProcessError, ValueError):
        raise HTTPException(status_code=400, detail="Could not validate audio duration")
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    voice_record_id = str(uuid.uuid4())

    from services.gcs_service import get_gcs_service
    gcs_service = get_gcs_service()

    gcs_result = await gcs_service.upload_audio_bytes(
        audio_bytes=audio_bytes,
        user_id=user_id,
        file_extension=file_extension,
        audio_id=voice_record_id,
        metadata={
            'purpose': 'minimax_voice_clone_sample',
            'voice_name': voice_name,
            'duration': duration
        }
    )

    from services.minimax_voice_clone_service import get_minimax_voice_clone_service
    minimax_service = get_minimax_voice_clone_service()

    clone_result = await minimax_service.clone_voice(
        voice_name=voice_name,
        audio_bytes=audio_bytes,
        filename=file.filename or f"voice.{file_extension}",
        content_type=file.content_type,
        description=description,
        preview_text=preview_text,
    )

    if not clone_result['success']:
        await gcs_service.delete_video(gcs_result['gcs_path'])
        raise HTTPException(status_code=500, detail=f"MiniMax voice cloning failed: {clone_result['error']}")

    voice_data = {
        'id': voice_record_id,
        'user_id': user_id,
        # Historical column name; stores the provider voice ID for all custom voice providers.
        'elevenlabs_voice_id': clone_result['voice_id'],
        'voice_name': voice_name,
        'description': description,
        'sample_audio_gcs_path': gcs_result['gcs_path'],
        'sample_audio_signed_url': gcs_result['signed_url'],
        'sample_audio_signed_url_expires_at': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        'sample_duration_seconds': duration,
        'status': 'completed'
    }
    if has_provider_column:
        voice_data['provider'] = 'minimax'

    try:
        result = supabase_client.table('custom_voices').insert(voice_data).execute()

        if not result.data:
            raise Exception("Database insert failed - no data returned")

        logger.info(f"✅ MiniMax custom voice created: {voice_name} (ID: {clone_result['voice_id']})")

        return CustomVoiceResponse(
            id=voice_record_id,
            voice_name=voice_name,
            description=description,
            provider='minimax',
            voice_id=clone_result['voice_id'],
            elevenlabs_voice_id=clone_result['voice_id'],
            status='completed',
            preview_url=gcs_result['signed_url'],
            created_at=datetime.now(timezone.utc).isoformat()
        )

    except Exception as db_error:
        logger.error(f"❌ MiniMax custom voice database error: {type(db_error).__name__}: {str(db_error)}")
        await minimax_service.delete_cloned_voice(clone_result['voice_id'])
        await gcs_service.delete_video(gcs_result['gcs_path'])
        raise HTTPException(status_code=500, detail=f"Failed to save MiniMax voice: {str(db_error)}")


@router.get("/minimax/custom-voices", response_model=CustomVoiceListResponse)
async def list_minimax_custom_voices(
    current_user: dict = Depends(get_current_user),
    supabase_client = Depends(get_supabase_client)
):
    """List user's MiniMax custom voices with auto-refresh of expired URLs."""
    user_id = current_user.id

    has_provider_column = _can_use_provider_column(supabase_client)

    query = supabase_client.table('custom_voices')\
        .select('*')\
        .eq('user_id', user_id)\
        .eq('status', 'completed')\
        .order('created_at', desc=True)

    if has_provider_column:
        query = query.eq('provider', 'minimax')

    result = query.execute()

    voices = []
    from services.gcs_service import get_gcs_service
    gcs_service = get_gcs_service()

    for voice_data in result.data:
        expires_at = datetime.fromisoformat(voice_data['sample_audio_signed_url_expires_at'].replace('Z', '+00:00'))
        if datetime.now(timezone.utc) >= expires_at - timedelta(hours=1):
            new_signed_url = await gcs_service.generate_signed_url(
                voice_data['sample_audio_gcs_path'],
                expiration_hours=24
            )

            supabase_client.table('custom_voices')\
                .update({
                    'sample_audio_signed_url': new_signed_url,
                    'sample_audio_signed_url_expires_at': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
                })\
                .eq('id', voice_data['id'])\
                .execute()

            voice_data['sample_audio_signed_url'] = new_signed_url

        voices.append(CustomVoiceResponse(
            id=voice_data['id'],
            voice_name=voice_data['voice_name'],
            description=voice_data.get('description'),
            provider='minimax',
            voice_id=voice_data['elevenlabs_voice_id'],
            elevenlabs_voice_id=voice_data['elevenlabs_voice_id'],
            status=voice_data['status'],
            preview_url=voice_data['sample_audio_signed_url'],
            created_at=voice_data['created_at']
        ))

    return CustomVoiceListResponse(
        voices=voices,
        total_count=len(voices),
        max_voices=MAX_CUSTOM_VOICES
    )


@router.delete("/minimax/custom-voices/{voice_id}")
async def delete_minimax_custom_voice(
    voice_id: str,
    current_user: dict = Depends(get_current_user),
    supabase_client = Depends(get_supabase_client)
):
    """Delete a MiniMax custom voice."""
    user_id = current_user.id

    has_provider_column = _can_use_provider_column(supabase_client)

    query = supabase_client.table('custom_voices')\
        .select('*')\
        .eq('id', voice_id)\
        .eq('user_id', user_id)

    if has_provider_column:
        query = query.eq('provider', 'minimax')

    result = query.execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="MiniMax voice not found")

    voice_data = result.data[0]

    from services.minimax_voice_clone_service import get_minimax_voice_clone_service
    minimax_service = get_minimax_voice_clone_service()
    await minimax_service.delete_cloned_voice(voice_data['elevenlabs_voice_id'])

    from services.gcs_service import get_gcs_service
    gcs_service = get_gcs_service()
    await gcs_service.delete_video(voice_data['sample_audio_gcs_path'])

    supabase_client.table('custom_voices')\
        .delete()\
        .eq('id', voice_id)\
        .execute()

    logger.info(f"✅ Deleted MiniMax custom voice: {voice_data['voice_name']} (ID: {voice_id})")

    return {"success": True, "message": f"Voice '{voice_data['voice_name']}' deleted successfully"}


@router.delete("/elevenlabs/custom-voices/{voice_id}")
async def delete_custom_voice(
    voice_id: str,
    current_user: dict = Depends(get_current_user),
    supabase_client = Depends(get_supabase_client)
):
    """Delete custom voice"""
    raise HTTPException(status_code=410, detail="ElevenLabs is disabled in local mode. Use /api/generate/minimax/custom-voices/{voice_id}.")

    user_id = current_user.id

    # Get voice data
    result = supabase_client.table('custom_voices')\
        .select('*')\
        .eq('id', voice_id)\
        .eq('user_id', user_id)\
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Voice not found")

    voice_data = result.data[0]

    # Delete from ElevenLabs
    elevenlabs_service = get_elevenlabs_service()
    await elevenlabs_service.delete_cloned_voice(voice_data['elevenlabs_voice_id'])

    # Delete from GCS
    from services.gcs_service import get_gcs_service
    gcs_service = get_gcs_service()
    await gcs_service.delete_video(voice_data['sample_audio_gcs_path'])

    # Delete from database
    supabase_client.table('custom_voices')\
        .delete()\
        .eq('id', voice_id)\
        .execute()

    logger.info(f"✅ Deleted custom voice: {voice_data['voice_name']} (ID: {voice_id})")

    return {"success": True, "message": f"Voice '{voice_data['voice_name']}' deleted successfully"}


@router.post("/audio-for-timeline", response_model=TimelineAudioResponse)
async def generate_audio_for_timeline(
    request: TimelineAudioRequest,
    user_data: dict = Depends(get_current_user),
    supabase_client = Depends(get_supabase_client)
) -> TimelineAudioResponse:
    """
    Generate audio for timeline editing and create video project
    
    Args:
        request: Audio generation request with text and voice settings
        user_data: Current authenticated user data
        supabase_client: Supabase client dependency
    
    Returns:
        Audio file information and project ID
    """
    logger.info(f"🚀🚀🚀🚀🚀🚀 Request: {request}")
    logger.info(f"🆔 Extracted user_id: {user_data}")
    logger.info(f"🆔 Supabase user id: {user_data.id}")
    try:
        if len(request.text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        
        if len(request.text) > 1000000:
            raise HTTPException(status_code=400, detail="Text too long (max 1,000,000 characters)")
        
        user_id = user_data.id

        # Check for existing draft project to reuse audio_id
        temp_project_id = None
        try:
            logger.info("🔍 Checking for existing draft project to reuse...")
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
                    logger.info(f"✅ Found existing draft project: {temp_project_id}")
                    break

            if not temp_project_id:
                logger.info("ℹ️ No existing draft project found, will create new one")
        except Exception as e:
            logger.warning(f"⚠️ Failed to check for existing project: {e}")

        # For multi-language support: Check if language already has an audio_file_id
        # If yes, reuse it. If no, generate a new UUID for this language.
        language_audio_id = temp_project_id
        if temp_project_id and request.language_code:
            try:
                from db.supabase_client import supabase_client as sb_client
                supabase = sb_client.supabase

                # Check if this language already has an audio_file_id
                lang_result = supabase.table("video_project_languages")\
                    .select("audio_file_id")\
                    .eq("project_id", temp_project_id)\
                    .eq("language_code", request.language_code)\
                    .execute()

                if lang_result.data and lang_result.data[0].get("audio_file_id"):
                    language_audio_id = lang_result.data[0]["audio_file_id"]
                    logger.info(f"🌐 Reusing existing audio ID for language {request.language_code}: {language_audio_id}")
                else:
                    # Generate new UUID for this language
                    language_audio_id = str(uuid.uuid4())
                    logger.info(f"🌐 Generated new audio ID for language {request.language_code}: {language_audio_id}")
            except Exception as e:
                logger.error(f"❌ Error checking language audio ID: {e}")
                # Fall back to temp_project_id
                language_audio_id = temp_project_id

        if request.tts_provider not in ("minimax", "google"):
            raise HTTPException(status_code=400, detail="Unsupported TTS provider. Use 'minimax' or 'google'.")

        # Get the appropriate TTS service based on provider
        tts_service = get_tts_service(request.tts_provider)

        # Set up voice settings with the selected voice_id
        voice_settings = request.voice_settings or VoiceSettings()
        voice_settings.voice_id = request.voice_id

        #logger.info(f"🆔 Audio settings: {request.audio_settings}")
        # Generate audio and wait for completion
        # Pass language_audio_id to create unique audio files per language
        # Track if ElevenLabs provided timestamps (skip AssemblyAI if so)
        elevenlabs_has_timestamps = False

        if request.tts_provider == "elevenlabs":
            # ElevenLabs uses convert_with_timestamps which returns timestamps directly
            # This saves API cost and time by skipping AssemblyAI transcription
            logger.info("🎤 Using ElevenLabs TTS with timestamps...")
            result = await tts_service.text_to_speech_auto_and_wait(
                text=request.text,
                voice_settings=voice_settings,
                audio_settings=request.audio_settings,
                user_id=user_id,
                audio_speed=request.audio_speed,
                audio_id=language_audio_id,
                voice_system_prompt=request.voice_system_prompt,
                project_id=temp_project_id,  # Pass project_id for timestamp storage
                language_code=request.language_code  # Pass language code for filename
            )
            # ElevenLabs returns dict with audio_file, word_segments, has_timestamps
            audio_file = result['audio_file']
            elevenlabs_has_timestamps = result.get('has_timestamps', False)
            if elevenlabs_has_timestamps:
                logger.info(f"✅ ElevenLabs provided {len(result.get('word_segments', []))} word timestamps - skipping AssemblyAI")
            else:
                logger.warning("⚠️ ElevenLabs did not return timestamps - AssemblyAI will be used for transcription")

        elif request.tts_provider in ["deepgram", "google"]:
            # Deepgram and Google use text_to_speech_auto which automatically completes
            # These providers don't support native speed adjustment
            audio_file = await tts_service.text_to_speech_auto(
                text=request.text,
                voice_settings=voice_settings,
                audio_settings=request.audio_settings,
                user_id=user_id,
                audio_speed=request.audio_speed,
                audio_id=language_audio_id,  # Use language-specific audio_id
                voice_system_prompt=request.voice_system_prompt  # Pass custom voice prompt
            )

            # For providers that don't support native speed, adjust post-generation if needed
            if request.audio_speed and request.audio_speed != 1.0:
                provider_name = request.tts_provider.capitalize()
                logger.info(f"🔄 Adjusting {provider_name} audio speed to {request.audio_speed}x...")
                try:
                    # Calculate target duration based on speed
                    # If speed is 1.5x, target duration = current_duration / 1.5
                    current_duration = audio_file.duration
                    target_duration = current_duration / request.audio_speed

                    logger.info(f"📊 Current duration: {current_duration:.2f}s, Target duration: {target_duration:.2f}s (speed: {request.audio_speed}x)")

                    # Use the TTS service to adjust the audio duration
                    # Import the TTSService to access adjust_audio_file_duration
                    from services.tts_service import TTSService
                    minimax_service = TTSService()
                    adjusted_audio_file = await minimax_service.adjust_audio_file_duration(
                        audio_file=audio_file,
                        target_duration=target_duration
                    )
                    audio_file = adjusted_audio_file
                    logger.info(f"✅ {provider_name} audio speed adjusted successfully to {request.audio_speed}x (duration: {audio_file.duration:.2f}s)")
                except Exception as speed_error:
                    logger.error(f"❌ Failed to adjust {provider_name} audio speed: {str(speed_error)}")
                    # Continue with original audio file instead of failing completely
                    logger.warning("⚠️ Continuing with original audio (1.0x speed)")
        else:
            # Minimax uses text_to_speech_auto_and_wait with native speed support
            audio_file = await tts_service.text_to_speech_auto_and_wait(
                text=request.text,
                voice_settings=voice_settings,
                audio_settings=request.audio_settings,
                user_id=user_id,
                audio_speed=request.audio_speed,
                audio_id=language_audio_id,  # Use language-specific audio_id
                voice_system_prompt=request.voice_system_prompt  # Pass custom voice prompt
            )

        logger.info("🔄 Starting video project creation process...")
        
        # Create video project with audio_ready status
        try:
            logger.info("🔧 Creating VideoProjectRepository instance...")
            from db.supabase_client import supabase_client
            video_project_repo = VideoProjectRepository(supabase_client)
            logger.info("✅ VideoProjectRepository created successfully")
        except Exception as repo_error:
            logger.error(f"❌ Failed to create VideoProjectRepository: {str(repo_error)}")
            raise HTTPException(status_code=500, detail=f"Failed to initialize repository: {str(repo_error)}")
        
        # Handle user_id conversion properly
        logger.info(f"🔄 Processing user_id: {user_id} (type: {type(user_id)})")
        if isinstance(user_id, str):
            try:
                user_uuid = uuid.UUID(user_id)
                logger.info(f"✅ Converted user_id to UUID: {user_uuid}")
            except ValueError:
                logger.error(f"Invalid user_id format: {user_id}")
                raise HTTPException(status_code=400, detail="Invalid user ID format")
        else:
            user_uuid = user_id
            logger.info(f"✅ Using existing UUID: {user_uuid}")
        
        logger.info(f"🔄 Creating project data with audio_file.id: {audio_file.id}, duration: {audio_file.duration}")
        
        try:
            project_data = VideoProjectCreate(
                user_id=user_uuid,
                title=request.project_title or f"Dynamic Image Video {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                status="audio_ready",
                duration=audio_file.duration or 0.0,
                file_size=0,
                processing_options={"mode": "dynamic_images", "audio_generated": True},
                audio_file_id=str(audio_file.id)
            )
            logger.info(f"✅ Project data created successfully")
            logger.info(f"🆔 Project data: {project_data}")
        except Exception as data_error:
            logger.error(f"❌ Failed to create VideoProjectCreate object: {str(data_error)}")
            raise HTTPException(status_code=500, detail=f"Failed to create project data: {str(data_error)}")
        
        logger.info("🔄 Attempting to save project to database...")
        try:
            project = await video_project_repo.create(project_data)
            logger.info(f"✅ Video project created successfully: {project.id}")
        except Exception as create_error:
            logger.error(f"❌ Failed to create video project: {str(create_error)}")
            logger.error(f"❌ Error type: {type(create_error)}")
            logger.error(f"❌ Project data that failed: {project_data}")
            import traceback
            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Failed to create video project: {str(create_error)}")

        # Store project assets (audio metadata) to video_project_assets table
        try:
            from services.project_assets_service import get_project_assets_service
            assets_service = get_project_assets_service()

            # Prepare audio file data
            audio_file_data = {
                'id': str(audio_file.id),
                'gcs_path': getattr(audio_file, 'gcs_path', None),
                'url': audio_file.url,
                'duration': audio_file.duration
            }

            # Prepare generation request dict for assets service
            generation_request_dict = {
                'text': request.text,
                'voice_id': request.voice_id,
                'project_title': request.project_title,
                'tts_provider': request.tts_provider,
                'language_code': request.language_code,
                'user_input_text': request.user_input_text
            }

            # Store all assets used in this generation
            asset_storage_success = await assets_service.store_project_assets(
                project_id=project.id,
                generation_request=generation_request_dict,
                audio_file_data=audio_file_data
            )

            if asset_storage_success:
                logger.info(f"📦 Successfully stored project assets for project {project.id}")
            else:
                logger.warning(f"⚠️ Failed to store project assets for project {project.id}")

        except Exception as asset_error:
            logger.error(f"❌ Error storing project assets: {str(asset_error)}")
            # Don't fail the request, just log the error

        # Update language-specific audio_file_id if language_code is provided
        if request.language_code:
            try:
                logger.info(f"🌐 Updating language record for {request.language_code} with audio_file_id: {audio_file.id}")
                from db.supabase_client import supabase_client as sb_client
                supabase = sb_client.supabase

                # Update the video_project_languages table with the audio_file_id
                result = supabase.table("video_project_languages")\
                    .update({"audio_file_id": str(audio_file.id)})\
                    .eq("project_id", str(project.id))\
                    .eq("language_code", request.language_code)\
                    .execute()

                if result.data:
                    logger.info(f"✅ Updated language {request.language_code} with audio_file_id: {audio_file.id}")
                else:
                    logger.warning(f"⚠️ No language record found for {request.language_code} in project {project.id}")
            except Exception as lang_update_error:
                logger.error(f"❌ Failed to update language record: {str(lang_update_error)}")
                # Don't fail the whole request, just log the error

        # Automatically transcribe the generated audio (skip if ElevenLabs already provided timestamps)
        if elevenlabs_has_timestamps:
            logger.info(f"⏭️ Skipping AssemblyAI transcription - ElevenLabs already provided timestamps for audio file {audio_file.id}")
            logger.info("💰 Saved API cost and time by using ElevenLabs timestamps directly")
        else:
            try:
                logger.info(f"🎤 Starting automatic transcription for audio file {audio_file.id}")
                transcription_selector = TranscriptionServiceSelector()

                # Configure transcription with proper styling options
                transcription_config = {
                    "service": "faster-whisper",
                    "caption_style": "karaoke",
                    "font_size": 52,
                    "font_family": "Arial",
                    "position": "bottom",
                    "default_color": "&HFFFFFF",
                    "highlight_color": "&H00FFFF"
                }

                # Start transcription in background - don't wait for completion
                await transcription_selector.transcribe_with_service(
                    audio_url=audio_file.url,
                    service_name="faster-whisper",  # Use AssemblyAI as default
                    config=transcription_config,
                    user_id=str(user_id),
                    job_id=str(project.id),
                    user_input_text=request.user_input_text,
                    language_code=request.language_code  # Pass language code for language-specific file naming
                )
                logger.info(f"✅ Transcription started successfully for audio file {audio_file.id}")

            except Exception as transcription_error:
                # Log the error but don't fail the audio generation
                logger.error(f"⚠️ Failed to start transcription for audio file {audio_file.id}: {str(transcription_error)}")
                logger.warning("⚠️ Audio generation succeeded but transcription failed - continuing")

        return TimelineAudioResponse(
            audio_file=audio_file,
            project_id=str(project.id),
            message="Audio generated successfully for timeline editing"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating audio for timeline: {str(e)}")
