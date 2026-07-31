"""
API endpoints for saving and loading project scenes
"""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from uuid import UUID
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import asyncio
import json
import tempfile
import subprocess
import uuid
import aiohttp
import logging

from models.auth_models import UserProfile
from models.video_project_models import (
    SaveProjectScenesRequest,
    SaveProjectScenesResponse,
    LoadProjectScenesResponse,
    SaveTextLayersRequest,
    SaveTextLayersResponse,
    LoadTextLayersResponse,
    GenerateSceneAudioRequest,
    GenerateSceneAudioResponse,
    VideoProjectUpdate,
)
from middleware.auth_middleware import get_current_user
from repositories.project_scenes_repository import get_project_scenes_repository
from repositories.video_project_repository import VideoProjectRepository
from db.supabase_client import SupabaseClient
from models.story_models import AudioFile, VoiceSettings, AudioSettings, GenerationStatus
from services.tts_factory import get_tts_service
from services.tts_service import TTSService
from services.gcs_service import get_gcs_service
from services.transcription_service import TranscriptionServiceSelector

router = APIRouter(prefix="/api/scenes", tags=["scenes"])
logger = logging.getLogger(__name__)


class AdjustSceneAudioSpeedRequest(BaseModel):
    """Request to post-process generated scene audio and keep timestamps aligned."""
    audio_speed: float = Field(..., ge=0.5, le=2.0)
    current_audio_speed: Optional[float] = Field(default=1.0, ge=0.5, le=2.0)
    language_code: Optional[str] = "en"


class AdjustSceneAudioSpeedResponse(BaseModel):
    project_id: str
    audio_speed: float
    duration_scale: float
    combined_audio: Optional[Dict[str, Any]] = None
    scenes: List[Dict[str, Any]]
    updated_transcript_files: List[str] = []
    message: str


async def _download_to_path(url: str, output_path: Path) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            output_path.write_bytes(await response.read())


def _probe_duration(audio_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float((result.stdout or "0").strip() or 0)


def _concat_audio_files(input_paths: List[Path], output_path: Path) -> None:
    concat_file = output_path.with_suffix(".txt")
    concat_file.write_text("".join([f"file '{path.as_posix()}'\n" for path in input_paths]))
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def _create_silence_file(duration: float, output_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", "anullsrc=r=16000:cl=mono",
            "-t", str(max(duration, 0.1)),
            "-q:a", "9",
            "-acodec", "libmp3lame",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def _scale_numeric(value: Any, scale: float, precision: int = 3) -> Any:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value) * scale, precision)
    return value


def _scale_scene_timestamps(scene: Dict[str, Any], scale: float) -> None:
    """Scale scene and per-dialogue timestamps stored in seconds."""
    for key in ("start_time", "end_time", "target_duration"):
        if scene.get(key) is not None:
            scene[key] = _scale_numeric(scene[key], scale)

    scene_audio = scene.get("scene_audio")
    if isinstance(scene_audio, dict) and scene_audio.get("duration") is not None:
        scene_audio["duration"] = _scale_numeric(scene_audio["duration"], scale)

    dialogue_turns = scene.get("dialogue_turns") or []
    if isinstance(dialogue_turns, list):
        for turn in dialogue_turns:
            if not isinstance(turn, dict):
                continue
            for key in ("start_time", "end_time", "duration"):
                if turn.get(key) is not None:
                    turn[key] = _scale_numeric(turn[key], scale)


def _scale_transcript_time_fields(payload: Any, scale: float) -> None:
    """
    Scale timestamp fields in transcript JSON.

    AssemblyAI raw transcripts and derived transcript_sentences files store
    numeric time fields. Scaling is dimension-agnostic, so seconds and
    milliseconds use the same multiplier.
    """
    time_keys = {"start", "end", "start_time", "end_time", "duration", "audio_duration"}
    if isinstance(payload, dict):
        for key, value in list(payload.items()):
            if key in time_keys and isinstance(value, (int, float)) and not isinstance(value, bool):
                payload[key] = _scale_numeric(value, scale)
            else:
                _scale_transcript_time_fields(value, scale)
    elif isinstance(payload, list):
        for item in payload:
            _scale_transcript_time_fields(item, scale)


async def _gcs_blob_exists(gcs_service: Any, blob_path: str) -> bool:
    loop = asyncio.get_event_loop()
    blob = gcs_service.bucket.blob(blob_path)
    return await loop.run_in_executor(gcs_service.executor, blob.exists)


async def _scale_gcs_json_file(gcs_service: Any, blob_path: str, scale: float) -> bool:
    if not gcs_service.is_available():
        return False
    if not await _gcs_blob_exists(gcs_service, blob_path):
        return False

    loop = asyncio.get_event_loop()
    blob = gcs_service.bucket.blob(blob_path)
    content = await loop.run_in_executor(
        gcs_service.executor,
        lambda: blob.download_as_text(encoding="utf-8"),
    )
    data = json.loads(content)
    _scale_transcript_time_fields(data, scale)
    scaled_content = json.dumps(data, ensure_ascii=False)
    await loop.run_in_executor(
        gcs_service.executor,
        lambda: blob.upload_from_string(scaled_content, content_type="application/json; charset=utf-8"),
    )
    return True


async def _scale_project_transcript_files(
    *,
    gcs_service: Any,
    user_id: str,
    project_id: str,
    language_code: Optional[str],
    scale: float,
) -> List[str]:
    filenames = {"raw_transcript_data.txt", "transcript_sentences.json"}
    if language_code:
        filenames.add(f"raw_transcript_data_{language_code}.txt")
        filenames.add(f"transcript_sentences_{language_code}.json")

    updated: List[str] = []
    for filename in sorted(filenames):
        blob_path = f"output/{user_id}/{project_id}/{filename}"
        try:
            if await _scale_gcs_json_file(gcs_service, blob_path, scale):
                updated.append(filename)
        except json.JSONDecodeError:
            logger.warning(f"Skipping non-JSON transcript timestamp file during audio-speed scaling: {blob_path}")
        except Exception as exc:
            logger.warning(f"Failed to scale transcript timestamps in {blob_path}: {exc}")
    return updated


async def _prepare_audio_file_for_duration_adjustment(
    audio_file: AudioFile,
    *,
    user_id: str,
    gcs_service: Any,
) -> AudioFile:
    """Ensure TTSService.adjust_audio_file_duration can download and re-upload the asset."""
    source_url = audio_file.url
    if audio_file.gcs_path:
        source_url = await gcs_service.generate_signed_url(audio_file.gcs_path, expiration_hours=24) or source_url
    elif audio_file.file_path and not audio_file.file_path.startswith(("http://", "https://")):
        source_url = await gcs_service.generate_signed_url(audio_file.file_path, expiration_hours=24) or source_url
        audio_file.gcs_path = audio_file.gcs_path or audio_file.file_path

    if not source_url:
        raise RuntimeError("Audio file is missing a downloadable URL")

    audio_file.file_path = source_url
    audio_file.url = source_url
    audio_file.__dict__["user_id"] = user_id
    return audio_file


async def _load_audio_metadata_or_400(metadata_service: TTSService, audio_id: str) -> AudioFile:
    try:
        return await metadata_service.load_audio_metadata(audio_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not load audio metadata for {audio_id}: {exc}",
        )


def _audio_payload(audio_file: AudioFile) -> Dict[str, Any]:
    return {
        "file_id": str(audio_file.id),
        "url": audio_file.url,
        "duration": audio_file.duration or 0,
    }


async def _synthesize_audio(
    *,
    text: str,
    user_id: str,
    provider: str,
    voice_id: str,
    audio_speed: float,
    audio_id: str,
) -> AudioFile:
    tts_service = get_tts_service(provider)
    voice_settings = VoiceSettings(voice_id=voice_id)
    audio_settings = AudioSettings()

    if provider in ["deepgram", "google"]:
        audio_file = await tts_service.text_to_speech_auto(
            text=text,
            voice_settings=voice_settings,
            audio_settings=audio_settings,
            user_id=user_id,
            audio_speed=audio_speed,
            audio_id=audio_id,
        )
    else:
        audio_file = await tts_service.text_to_speech_auto_and_wait(
            text=text,
            voice_settings=voice_settings,
            audio_settings=audio_settings,
            user_id=user_id,
            audio_speed=audio_speed,
            audio_id=audio_id,
    )
    return audio_file


def _resolve_turn_voice(
    turn: Dict[str, Any],
    request: GenerateSceneAudioRequest,
) -> tuple[str, str, float]:
    character_voice_map = request.character_voice_map or {}
    speaker_id = str(turn.get("speaker_id") or "").strip()
    character_assignment = character_voice_map.get(speaker_id) or {}

    if turn.get("voice_override") and turn.get("voice_id"):
        provider = str(turn.get("provider") or request.tts_provider)
        audio_speed = float(turn.get("audio_speed") or request.audio_speed or 1.0)
        return str(turn.get("voice_id")), provider, audio_speed

    voice_id = str(character_assignment.get("voice_id") or request.default_voice_id)
    provider = str(character_assignment.get("provider") or request.tts_provider)
    audio_speed = float(character_assignment.get("audio_speed") or request.audio_speed or 1.0)
    return voice_id, provider, audio_speed

@router.post("/save", response_model=SaveProjectScenesResponse)
async def save_project_scenes(
    request: SaveProjectScenesRequest,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Save scenes for a project

    This endpoint:
    1. Validates the project exists and belongs to the current user
    2. Saves all scenes (replacing any existing scenes)
    3. Returns a success message with the count of saved scenes
    """
    try:
        project_id = UUID(request.project_id)

        # Verify project exists and user owns it
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)
        project = await project_repo.get_by_id(project_id)

        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )

        if str(project.user_id) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to modify this project"
            )

        # Save scenes
        scenes_repo = get_project_scenes_repository()
        scenes_data = [scene.model_dump() for scene in request.scenes]

        success = await scenes_repo.save_scenes(project_id, scenes_data)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save scenes"
            )

        return SaveProjectScenesResponse(
            project_id=str(project_id),
            scenes_count=len(request.scenes),
            message=f"Successfully saved {len(request.scenes)} scenes"
        )

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid project ID format"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving scenes: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save scenes: {str(e)}"
        )

@router.get("/{project_id}", response_model=LoadProjectScenesResponse)
async def load_project_scenes(
    project_id: str,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Load scenes for a project

    This endpoint:
    1. Validates the project exists and belongs to the current user
    2. Retrieves all scenes ordered by scene_index
    3. Returns the scenes array with metadata
    """
    try:
        project_uuid = UUID(project_id)

        # Verify project exists and user owns it
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)
        project = await project_repo.get_by_id(project_uuid)

        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )

        if str(project.user_id) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this project"
            )

        # Load scenes (repository automatically refreshes expired URLs)
        scenes_repo = get_project_scenes_repository()
        scenes = await scenes_repo.get_scenes_by_project(project_uuid)

        return LoadProjectScenesResponse(
            project_id=project_id,
            scenes=scenes,
            scenes_count=len(scenes)
        )

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid project ID format"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading scenes: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load scenes: {str(e)}"
        )


@router.post("/text-layers/save", response_model=SaveTextLayersResponse)
async def save_project_text_layers(
    request: SaveTextLayersRequest,
    current_user: UserProfile = Depends(get_current_user)
):
    """Save text layers for a project"""
    try:
        project_id = UUID(request.project_id)

        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)
        project = await project_repo.get_by_id(project_id)

        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        if str(project.user_id) != str(current_user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to modify this project")

        scenes_repo = get_project_scenes_repository()
        text_layers_data = [tl.model_dump() for tl in request.text_layers]
        success = await scenes_repo.save_text_layers(project_id, text_layers_data)

        if not success:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save text layers")

        return SaveTextLayersResponse(
            project_id=str(project_id),
            text_layers_count=len(request.text_layers),
            message=f"Successfully saved {len(request.text_layers)} text layers"
        )

    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid project ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving text layers: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save text layers: {str(e)}")


@router.get("/text-layers/{project_id}", response_model=LoadTextLayersResponse)
async def load_project_text_layers(
    project_id: str,
    current_user: UserProfile = Depends(get_current_user)
):
    """Load text layers for a project"""
    try:
        project_uuid = UUID(project_id)

        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)
        project = await project_repo.get_by_id(project_uuid)

        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        if str(project.user_id) != str(current_user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this project")

        scenes_repo = get_project_scenes_repository()
        text_layers = await scenes_repo.get_text_layers_by_project(project_uuid)

        return LoadTextLayersResponse(
            project_id=project_id,
            text_layers=text_layers,
            text_layers_count=len(text_layers)
        )

    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid project ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading text layers: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to load text layers: {str(e)}")


@router.post("/{project_id}/generate-audio", response_model=GenerateSceneAudioResponse)
async def generate_scene_audio(
    project_id: str,
    request: GenerateSceneAudioRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    """Generate scene-local audio for talking-scenes projects and concatenate a combined project track."""
    try:
        project_uuid = UUID(project_id)
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)
        project = await project_repo.get_by_id(project_uuid)

        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        if str(project.user_id) != str(current_user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to modify this project")

        scenes_repo = get_project_scenes_repository()
        scenes = await scenes_repo.get_scenes_by_project(project_uuid)
        if not scenes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No scenes found for project")

        user_id = str(current_user.id)
        gcs_service = get_gcs_service()
        metadata_service = TTSService()
        transcription_selector = TranscriptionServiceSelector()

        generated_count = 0
        combined_scene_inputs: List[Path] = []
        updated_scenes: List[Dict[str, Any]] = []
        elapsed = 0.0

        with tempfile.TemporaryDirectory(prefix="scene-audio-") as temp_dir:
            temp_root = Path(temp_dir)

            for index, scene in enumerate(scenes):
                local_paths: List[Path] = []
                dialogue_turns = list(scene.get("dialogue_turns") or [])
                scene_script = (scene.get("scene_script") or scene.get("description") or "").strip()
                scene_type = scene.get("scene_type") or ("dialogue" if dialogue_turns else "monologue")
                scene_audio: Optional[Dict[str, Any]] = None

                if scene_type == "broll" or (not scene_script and not dialogue_turns):
                    silence_duration = float(scene.get("target_duration") or max((scene.get("end_time") or 0) - (scene.get("start_time") or 0), 3.0))
                    silence_path = temp_root / f"scene_{index}_silence.mp3"
                    _create_silence_file(silence_duration, silence_path)
                    local_paths.append(silence_path)
                elif dialogue_turns:
                    turn_start = 0.0
                    for turn_index, turn in enumerate(dialogue_turns):
                        turn_text = (turn.get("text") or "").strip()
                        if not turn_text:
                            continue
                        turn_voice_id, turn_provider, turn_audio_speed = _resolve_turn_voice(turn, request)
                        turn_audio_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{scene.get('id')}-turn-{turn_index}"))
                        audio_file = await _synthesize_audio(
                            text=turn_text,
                            user_id=user_id,
                            provider=turn_provider,
                            voice_id=turn_voice_id,
                            audio_speed=turn_audio_speed,
                            audio_id=turn_audio_id,
                        )
                        turn_path = temp_root / f"scene_{index}_turn_{turn_index}.mp3"
                        await _download_to_path(audio_file.url, turn_path)
                        turn_duration = audio_file.duration or _probe_duration(turn_path)
                        turn["voice_id"] = turn_voice_id
                        turn["provider"] = turn_provider
                        turn["audio_speed"] = turn_audio_speed
                        turn["duration"] = turn_duration
                        turn["start_time"] = turn_start
                        turn["end_time"] = turn_start + turn_duration
                        turn_start += turn_duration
                        local_paths.append(turn_path)
                    generated_count += 1
                else:
                    scene_tts_audio_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{scene.get('id')}-scene-tts"))
                    audio_file = await _synthesize_audio(
                        text=scene_script,
                        user_id=user_id,
                        provider=request.tts_provider,
                        voice_id=request.default_voice_id,
                        audio_speed=request.audio_speed or 1.0,
                        audio_id=scene_tts_audio_id,
                    )
                    mono_path = temp_root / f"scene_{index}.mp3"
                    await _download_to_path(audio_file.url, mono_path)
                    local_paths.append(mono_path)
                    generated_count += 1

                if not local_paths:
                    fallback_duration = float(scene.get("target_duration") or max((scene.get("end_time") or 0) - (scene.get("start_time") or 0), 3.0))
                    fallback_path = temp_root / f"scene_{index}_fallback_silence.mp3"
                    _create_silence_file(fallback_duration, fallback_path)
                    local_paths.append(fallback_path)

                scene_output_path = temp_root / f"scene_{index}_combined.mp3"
                if len(local_paths) == 1:
                    scene_output_path.write_bytes(local_paths[0].read_bytes())
                else:
                    _concat_audio_files(local_paths, scene_output_path)

                scene_duration = _probe_duration(scene_output_path)
                scene_audio_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{scene.get('id')}-scene-audio"))
                upload_result = await gcs_service.upload_audio_bytes(
                    audio_bytes=scene_output_path.read_bytes(),
                    user_id=user_id,
                    file_extension="mp3",
                    audio_id=scene_audio_id,
                    metadata={
                        "project_id": project_id,
                        "scene_id": scene.get("id"),
                        "upload_source": "scene_audio_generation",
                    },
                )
                if not upload_result:
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to upload scene audio for scene {index + 1}")

                scene_audio_file = AudioFile(
                    id=uuid.UUID(scene_audio_id),
                    file_path=upload_result["gcs_path"],
                    duration=scene_duration,
                    format="mp3",
                    voice_settings=VoiceSettings(voice_id=request.default_voice_id),
                    audio_settings=AudioSettings(),
                    status=GenerationStatus.COMPLETED,
                    created_at=datetime.now(),
                    url=upload_result["signed_url"],
                    gcs_path=upload_result["gcs_path"],
                )
                await metadata_service._save_audio_metadata(scene_audio_file)

                scene_audio = {
                    "file_id": str(scene_audio_file.id),
                    "url": scene_audio_file.url,
                    "duration": scene_duration,
                    "transcript": " ".join([turn.get("text", "").strip() for turn in dialogue_turns if turn.get("text")]).strip() or scene_script,
                }
                scene["scene_audio"] = scene_audio
                scene["dialogue_turns"] = dialogue_turns
                scene["target_duration"] = scene_duration
                scene["start_time"] = elapsed
                scene["end_time"] = elapsed + scene_duration
                elapsed += scene_duration

                combined_scene_path = temp_root / f"scene_{index}_for_project.mp3"
                combined_scene_path.write_bytes(scene_output_path.read_bytes())
                combined_scene_inputs.append(combined_scene_path)
                updated_scenes.append(scene)

            combined_audio_payload = None
            if combined_scene_inputs:
                project_audio_path = temp_root / "project_scene_audio.mp3"
                if len(combined_scene_inputs) == 1:
                    project_audio_path.write_bytes(combined_scene_inputs[0].read_bytes())
                else:
                    _concat_audio_files(combined_scene_inputs, project_audio_path)

                combined_duration = _probe_duration(project_audio_path)
                combined_audio_id = project_id
                combined_upload = await gcs_service.upload_audio_bytes(
                    audio_bytes=project_audio_path.read_bytes(),
                    user_id=user_id,
                    file_extension="mp3",
                    audio_id=combined_audio_id,
                    metadata={
                        "project_id": project_id,
                        "upload_source": "talking_scenes_combined_audio",
                    },
                )
                if not combined_upload:
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to upload combined project audio")

                combined_audio_file = AudioFile(
                    id=uuid.UUID(combined_audio_id),
                    file_path=combined_upload["gcs_path"],
                    duration=combined_duration,
                    format="mp3",
                    voice_settings=VoiceSettings(voice_id=request.default_voice_id),
                    audio_settings=AudioSettings(),
                    status=GenerationStatus.COMPLETED,
                    created_at=datetime.now(),
                    url=combined_upload["signed_url"],
                    gcs_path=combined_upload["gcs_path"],
                )
                await metadata_service._save_audio_metadata(combined_audio_file)

                combined_audio_payload = {
                    "file_id": str(combined_audio_file.id),
                    "url": combined_audio_file.url,
                    "duration": combined_duration,
                }

                await project_repo.update(
                    project_uuid,
                    VideoProjectUpdate(
                        audio_file_id=str(combined_audio_file.id),
                        duration=combined_duration,
                        status="audio_ready",
                    ),
                )

                project_text = " ".join(
                    [
                        (scene.get("scene_audio") or {}).get("transcript", "").strip()
                        for scene in updated_scenes
                    ]
                ).strip()
                if project_text:
                    try:
                        await transcription_selector.transcribe_with_service(
                            audio_url=combined_audio_file.url,
                            service_name="faster-whisper",
                            config={
                                "service": "faster-whisper",
                                "caption_style": "karaoke",
                                "font_size": 52,
                                "font_family": "Arial",
                                "position": "bottom",
                                "default_color": "&HFFFFFF",
                                "highlight_color": "&H00FFFF",
                            },
                            user_id=user_id,
                            job_id=project_id,
                            user_input_text=project_text,
                            language_code=request.language_code,
                        )
                    except Exception as transcription_error:
                        logger.warning(f"Failed to start combined scene-audio transcription for project {project_id}: {transcription_error}")

        if updated_scenes:
            await scenes_repo.save_scenes(project_uuid, updated_scenes)

        refreshed_scenes = await scenes_repo.get_scenes_by_project(project_uuid)
        return GenerateSceneAudioResponse(
            project_id=project_id,
            scenes=refreshed_scenes,
            combined_audio=combined_audio_payload,
            generated_count=generated_count,
            message=f"Generated audio for {generated_count} scene{'s' if generated_count != 1 else ''}",
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid project ID format")
    except HTTPException:
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"Scene audio ffmpeg/ffprobe failure: {e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process scene audio")
    except Exception as e:
        logger.error(f"Error generating scene audio: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate scene audio: {str(e)}")


@router.post("/{project_id}/adjust-audio-speed", response_model=AdjustSceneAudioSpeedResponse)
async def adjust_scene_audio_speed(
    project_id: str,
    request: AdjustSceneAudioSpeedRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Post-process already generated audio to a new playback speed and scale timing metadata.

    This keeps final render inputs in sync when the user changes speed after TTS, scene
    generation, and transcription have already completed.
    """
    try:
        project_uuid = UUID(project_id)
        supabase_client = SupabaseClient()
        project_repo = VideoProjectRepository(supabase_client)
        project = await project_repo.get_by_id(project_uuid)

        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        if str(project.user_id) != str(current_user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to modify this project")

        current_speed = float(request.current_audio_speed or 1.0)
        requested_speed = float(request.audio_speed)
        if abs(requested_speed - current_speed) < 0.001:
            scenes_repo = get_project_scenes_repository()
            scenes = await scenes_repo.get_scenes_by_project(project_uuid)
            return AdjustSceneAudioSpeedResponse(
                project_id=project_id,
                audio_speed=requested_speed,
                duration_scale=1.0,
                combined_audio=None,
                scenes=scenes,
                message="Audio speed is already applied",
            )

        relative_speed = requested_speed / current_speed
        user_id = str(current_user.id)
        gcs_service = get_gcs_service()
        metadata_service = TTSService()
        scenes_repo = get_project_scenes_repository()
        scenes = await scenes_repo.get_scenes_by_project(project_uuid)

        if not scenes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No scenes found for project")

        combined_audio_payload: Optional[Dict[str, Any]] = None
        duration_scale = 1.0
        combined_audio_id = project.audio_file_id or project_id

        combined_audio_file = await _load_audio_metadata_or_400(metadata_service, combined_audio_id)
        combined_audio_file = await _prepare_audio_file_for_duration_adjustment(
            combined_audio_file,
            user_id=user_id,
            gcs_service=gcs_service,
        )
        current_duration = float(combined_audio_file.duration or project.duration or 0)
        if current_duration <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current audio duration is unavailable")

        target_duration = current_duration / relative_speed
        adjusted_combined_audio = await metadata_service.adjust_audio_file_duration(
            combined_audio_file,
            target_duration,
        )
        adjusted_duration = float(adjusted_combined_audio.duration or target_duration)
        duration_scale = adjusted_duration / current_duration
        combined_audio_payload = _audio_payload(adjusted_combined_audio)

        updated_scenes: List[Dict[str, Any]] = []
        for scene in scenes:
            _scale_scene_timestamps(scene, duration_scale)

            scene_audio = scene.get("scene_audio")
            if isinstance(scene_audio, dict) and scene_audio.get("file_id"):
                try:
                    original_scene_duration = float(scene_audio.get("duration") or 0) / duration_scale
                    scene_audio_file = await metadata_service.load_audio_metadata(str(scene_audio["file_id"]))
                    scene_audio_file = await _prepare_audio_file_for_duration_adjustment(
                        scene_audio_file,
                        user_id=user_id,
                        gcs_service=gcs_service,
                    )
                    target_scene_duration = max(
                        float(scene_audio_file.duration or original_scene_duration or 0) * duration_scale,
                        0.1,
                    )
                    adjusted_scene_audio = await metadata_service.adjust_audio_file_duration(
                        scene_audio_file,
                        target_scene_duration,
                    )
                    scene_audio.update(_audio_payload(adjusted_scene_audio))
                except Exception as scene_audio_error:
                    logger.warning(
                        f"Failed to post-process scene audio for scene {scene.get('id')}: {scene_audio_error}. "
                        "Keeping scaled timing metadata."
                    )
            updated_scenes.append(scene)

        await scenes_repo.save_scenes(project_uuid, updated_scenes)
        updated_transcript_files = await _scale_project_transcript_files(
            gcs_service=gcs_service,
            user_id=user_id,
            project_id=project_id,
            language_code=request.language_code,
            scale=duration_scale,
        )

        processing_options = dict(project.processing_options or {})
        processing_options["audio_speed"] = requested_speed
        processing_options["audio_duration_scale"] = duration_scale

        await project_repo.update(
            project_uuid,
            VideoProjectUpdate(
                audio_file_id=str(adjusted_combined_audio.id),
                duration=adjusted_duration,
                status="audio_ready",
                processing_options=processing_options,
            ),
        )

        try:
            supabase_client.supabase.table("video_project_languages").update({
                "audio_file_id": str(adjusted_combined_audio.id),
                "audio_url": adjusted_combined_audio.url,
                "duration": adjusted_duration,
                "updated_at": datetime.now().isoformat(),
            }).eq("project_id", project_id).eq("language_code", request.language_code or "en").execute()
        except Exception as language_update_error:
            logger.warning(f"Failed to update language audio reference after speed adjustment: {language_update_error}")

        refreshed_scenes = await scenes_repo.get_scenes_by_project(project_uuid)
        return AdjustSceneAudioSpeedResponse(
            project_id=project_id,
            audio_speed=requested_speed,
            duration_scale=duration_scale,
            combined_audio=combined_audio_payload,
            scenes=refreshed_scenes,
            updated_transcript_files=updated_transcript_files,
            message=f"Adjusted generated audio to {requested_speed:.2f}x and scaled scene timestamps",
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid project ID format")
    except HTTPException:
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"Audio speed ffmpeg/ffprobe failure: {e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to adjust audio speed")
    except Exception as e:
        logger.error(f"Error adjusting scene audio speed: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to adjust audio speed: {str(e)}")
