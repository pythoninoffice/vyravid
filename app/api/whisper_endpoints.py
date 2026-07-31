from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, status
from fastapi.responses import FileResponse
from typing import Optional, Any
from pydantic import BaseModel
import tempfile
import os
import uuid

from auth import get_current_user
from services.gcs_service import get_gcs_service
from services.transcription_service import TranscriptionServiceSelector
from services.whisper_service import WhisperService
from services.tts_service import TTSService
from models.story_models import (
    TranscriptionResult, CaptionSettings, AudioFile, WordSegment, Caption
)

router = APIRouter(prefix="/api/captions", tags=["captions"])
whisper_service = WhisperService()
tts_service = TTSService()

class TranscriptionRequest(BaseModel):
    audio_file_id: str

class CaptionGenerationRequest(BaseModel):
    audio_file_id: str
    caption_type: str = "animated"  # "animated" or "srt"
    settings: Optional[CaptionSettings] = None

class TranscriptionResponse(BaseModel):
    result: TranscriptionResult
    message: str


class UploadedAssemblyAiTranscriptResponse(BaseModel):
    transcript: str
    language_code: Optional[str] = None
    duration: Optional[float] = None
    confidence: Optional[float] = None
    processing_time: Optional[float] = None
    service_name: str = "faster-whisper"
    audio_url: Optional[str] = None
    gcs_path: Optional[str] = None
    bucket_name: Optional[str] = None


def _current_user_id(current_user: Any) -> str:
    if isinstance(current_user, dict):
        user_id = current_user.get("id") or current_user.get("sub") or current_user.get("user_id")
    else:
        user_id = getattr(current_user, "id", None) or getattr(current_user, "sub", None) or getattr(current_user, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found in token")
    return str(user_id)

@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(request: TranscriptionRequest) -> TranscriptionResponse:
    """
    Transcribe audio file using local Whisper
    
    Args:
        request: Transcription request with audio file ID
    
    Returns:
        Transcription result with segments and word-level timestamps
    """
    try:
        # Load audio file metadata
        audio_file = await tts_service.load_audio_metadata(request.audio_file_id)
        
        if not audio_file:
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        # Check if audio file exists
        from pathlib import Path
        if not Path(audio_file.file_path).exists():
            raise HTTPException(status_code=404, detail="Audio file not found on disk")
        
        # Transcribe the audio
        result = await whisper_service.transcribe_from_audio_file(audio_file)
        
        return TranscriptionResponse(
            result=result,
            message=f"Transcription completed. Language: {result.language}, {len(result.segments)} segments, {len(result.word_segments)} words"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error transcribing audio: {str(e)}")

@router.post("/transcribe/upload")
async def transcribe_uploaded_audio(
    audio_file: UploadFile = File(...),
    model_size: str = Form("small")
) -> TranscriptionResponse:
    """
    Transcribe uploaded audio file
    
    Args:
        audio_file: Uploaded audio file
        model_size: Whisper model size to use
    
    Returns:
        Transcription result
    """
    try:
        # Validate file type
        if not audio_file.content_type.startswith('audio/'):
            raise HTTPException(status_code=400, detail="File must be an audio file")
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            content = await audio_file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        try:
            # Create Whisper service with specified model size
            temp_whisper_service = WhisperService(model_size=model_size)
            
            # Transcribe the audio
            result = await temp_whisper_service.transcribe_audio_file(temp_file_path)
            
            return TranscriptionResponse(
                result=result,
                message=f"Transcription completed. Language: {result.language}, {len(result.segments)} segments, {len(result.word_segments)} words"
            )
            
        finally:
            # Clean up temporary file
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error transcribing uploaded audio: {str(e)}")


@router.post("/transcribe/upload-assemblyai", response_model=UploadedAssemblyAiTranscriptResponse)
async def transcribe_uploaded_audio_with_assemblyai(
    audio_file: UploadFile = File(...),
    current_user: Any = Depends(get_current_user),
) -> UploadedAssemblyAiTranscriptResponse:
    """
    Transcribe uploaded audio locally with faster-whisper and optionally persist
    the source audio to local media storage so the caller can attach it to chat.
    """
    temp_file_path = ""
    try:
        if not audio_file.content_type or not audio_file.content_type.startswith("audio/"):
            raise HTTPException(status_code=400, detail="File must be an audio file")

        user_id = _current_user_id(current_user)
        file_bytes = await audio_file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded audio file is empty")

        file_extension = os.path.splitext(audio_file.filename or "")[1].lstrip(".") or "mp3"

        gcs_result = None
        gcs_service = get_gcs_service()
        if gcs_service and gcs_service.is_available():
            try:
                gcs_result = await gcs_service.upload_audio_bytes(
                    audio_bytes=file_bytes,
                    user_id=user_id,
                    file_extension=file_extension,
                    audio_id=f"ask-vyra-audio-{uuid.uuid4().hex}",
                    metadata={
                        "original_filename": audio_file.filename or f"audio.{file_extension}",
                        "content_type": audio_file.content_type,
                        "upload_source": "ask_vyra_audio_transcript",
                    },
                )
            except Exception:
                gcs_result = None

        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as temp_file:
            temp_file.write(file_bytes)
            temp_file_path = temp_file.name

        transcription_selector = TranscriptionServiceSelector()
        result = await transcription_selector.transcribe_with_service(
            audio_url=temp_file_path,
            service_name="faster-whisper",
            config={
                "punctuate": True,
                "format_text": True,
                "language_detection": True,
            },
            user_id=user_id,
            job_id=f"ask_vyra_audio_{uuid.uuid4().hex}",
            user_input_text=None,
        )

        transcript = (result.transcript or "").strip()
        if not transcript:
            raise HTTPException(status_code=500, detail="Local transcription returned an empty transcript")

        metadata = result.metadata or {}
        return UploadedAssemblyAiTranscriptResponse(
            transcript=transcript,
            language_code=metadata.get("language_code"),
            duration=metadata.get("duration"),
            confidence=metadata.get("confidence"),
            processing_time=result.processing_time,
            service_name=result.service_name or "faster-whisper",
            audio_url=(gcs_result or {}).get("signed_url"),
            gcs_path=(gcs_result or {}).get("gcs_path"),
            bucket_name=(gcs_result or {}).get("bucket_name"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error transcribing uploaded audio locally: {str(e)}")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

@router.post("/generate")
async def generate_captions(request: CaptionGenerationRequest):
    """
    Generate caption files from transcribed audio
    
    Args:
        request: Caption generation request
    
    Returns:
        Information about generated caption file
    """
    try:
        # Load audio file metadata
        audio_file = await tts_service.load_audio_metadata(request.audio_file_id)
        
        if not audio_file:
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        # Check if transcription exists
        transcription_metadata = await whisper_service.load_transcription_metadata(request.audio_file_id)
        
        if not transcription_metadata:
            raise HTTPException(status_code=400, detail="Audio file has not been transcribed yet. Please transcribe first.")
        
        # Transcribe to get the actual data (this should be cached/optimized in production)
        result = await whisper_service.transcribe_from_audio_file(audio_file)
        
        if request.caption_type == "animated":
            # Generate animated ASS captions
            caption_file_path = await whisper_service.generate_animated_captions(
                word_segments=result.word_segments,
                language=result.language,
                settings=request.settings
            )
            caption_type = "ASS"
        else:
            # Generate SRT captions
            caption_file_path = await whisper_service.generate_srt_captions(
                segments=result.segments,
                language=result.language
            )
            caption_type = "SRT"
        
        return {
            "caption_file_path": caption_file_path,
            "caption_type": caption_type,
            "language": result.language,
            "segments_count": len(result.segments),
            "words_count": len(result.word_segments),
            "message": f"{caption_type} captions generated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating captions: {str(e)}")

@router.get("/download/{caption_file_name}")
async def download_caption_file(caption_file_name: str):
    """
    Download generated caption file
    
    Args:
        caption_file_name: Name of the caption file to download
    
    Returns:
        Caption file for download
    """
    try:
        from pathlib import Path
        caption_file_path = whisper_service.captions_dir / caption_file_name
        
        if not caption_file_path.exists():
            raise HTTPException(status_code=404, detail="Caption file not found")
        
        # Determine media type based on file extension
        if caption_file_path.suffix == '.ass':
            media_type = "text/plain"
        elif caption_file_path.suffix == '.srt':
            media_type = "text/plain"
        else:
            media_type = "text/plain"
        
        return FileResponse(
            path=str(caption_file_path),
            filename=caption_file_name,
            media_type=media_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading caption file: {str(e)}")

@router.get("/settings")
async def get_caption_settings():
    """
    Get available caption settings and options
    
    Returns:
        Available caption configuration options
    """
    return {
        "positions": ["top", "middle", "bottom"],
        "font_sizes": [48, 56, 64, 72, 80, 88, 96],
        "font_families": [
            "LuckiestGuy-Regular.ttf",
            "Arial",
            "Helvetica",
            "Times New Roman",
            "Courier New"
        ],
        "colors": {
            "white": "&H00FFFFFF",
            "yellow": "&H0000FFFF",
            "red": "&H000000FF",
            "green": "&H0000FF00",
            "blue": "&H00FF0000",
            "cyan": "&H00FFFF00",
            "magenta": "&H00FF00FF"
        },
        "whisper_models": ["tiny", "base", "small", "medium", "large"],
        "default_settings": {
            "position": "middle",
            "font_size": 72,
            "font_family": "LuckiestGuy-Regular.ttf",
            "highlight_color": "&H00FFFF&",
            "default_color": "&HFFFFFF&"
        }
    }

@router.get("/transcription/{audio_file_id}/metadata")
async def get_transcription_metadata(audio_file_id: str):
    """
    Get transcription metadata for an audio file
    
    Args:
        audio_file_id: ID of the audio file
    
    Returns:
        Transcription metadata
    """
    try:
        metadata = await whisper_service.load_transcription_metadata(audio_file_id)
        
        if not metadata:
            raise HTTPException(status_code=404, detail="Transcription metadata not found")
        
        return metadata
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading transcription metadata: {str(e)}")

@router.post("/cleanup")
async def cleanup_temp_files():
    """
    Clean up temporary files
    
    Returns:
        Cleanup status
    """
    try:
        await whisper_service.cleanup_temp_files()
        return {"message": "Temporary files cleaned up successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cleaning up files: {str(e)}")
