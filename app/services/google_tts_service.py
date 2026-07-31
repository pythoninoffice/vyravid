"""
Google Gemini TTS service for text-to-speech generation
"""

import os
import uuid
import asyncio
import aiofiles
import wave
import re
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from dotenv import load_dotenv
import logging

from google import genai
from google.genai import types

from models.story_models import AudioFile, VoiceSettings, AudioSettings, GenerationStatus

load_dotenv()

logger = logging.getLogger(__name__)

# Configuration
GOOGLE_GEMINI_API_KEY = os.getenv('GOOGLE_GEMINI_API_KEY')
DEFAULT_MODEL = "gemini-2.5-flash-preview-tts"  # Fast, good quality
PRO_MODEL = "gemini-2.5-pro-preview-tts"  # Higher quality, slower
MAX_CHUNK_SIZE = 2500  # Maximum characters per chunk for long text

# Available Google Gemini TTS voices
GOOGLE_VOICES = [
    "Zephyr", "Puck", "Charon", "Fenrir", "Leda", "Orus", "Aoede", "Callirrhoe",
    "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba", "Despina", "Erinome",
    "Algenib", "Rasalgethi", "Laomedeia", "Achernar", "Alnilam", "Schedar", "Gacrux",
    "Pulcherrima", "Achird", "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat"
]


class GoogleTTSError(Exception):
    """Custom exception for Google TTS errors"""
    pass


def get_audio_duration_from_wav(file_path: str) -> float:
    """
    Get the actual duration of a WAV audio file using wave library

    Args:
        file_path: Path to the audio file

    Returns:
        Duration in seconds as float
    """
    try:
        with wave.open(file_path, 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            duration = frames / float(rate)
            return duration
    except Exception as e:
        logger.warning(f"Failed to get audio duration for {file_path}: {e}")
        return 0.0


def get_audio_duration_ffmpeg(file_path: str) -> float:
    """
    Get the duration of an audio file using ffmpeg (works with all formats including WAV)

    Args:
        file_path: Path to the audio file

    Returns:
        Duration in seconds as float

    Raises:
        GoogleTTSError: If duration extraction fails
    """
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip())
        return duration

    except (subprocess.CalledProcessError, ValueError) as e:
        raise GoogleTTSError(f"Failed to get audio duration: {str(e)}")


class GoogleTTSService:
    """Google Gemini Text-to-Speech service"""

    def __init__(self, api_key: str = None, model: str = DEFAULT_MODEL):
        """Initialize Google TTS service"""
        if not api_key:
            api_key = GOOGLE_GEMINI_API_KEY

        if not api_key:
            raise GoogleTTSError("Please set GOOGLE_GEMINI_API_KEY environment variable")

        self.api_key = api_key
        self.model = model
        # Ensure TTS stays on API-key Gemini path (non-Vertex), even if
        # GOOGLE_GENAI_USE_VERTEXAI is enabled elsewhere in the process.
        prev_use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")
        try:
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"
            self.client = genai.Client(api_key=api_key)
        finally:
            if prev_use_vertex is None:
                os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
            else:
                os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = prev_use_vertex

        # Create audio directory for file storage
        self.audio_dir = Path("data/audio")
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        logger.info("✅ Google Gemini TTS client initialized successfully")

    def _pcm_to_wav(self, pcm_data: bytes, channels: int = 1, sample_rate: int = 24000, sample_width: int = 2) -> bytes:
        """
        Convert raw PCM audio data to WAV format

        Args:
            pcm_data: Raw PCM audio bytes
            channels: Number of audio channels (1 for mono, 2 for stereo)
            sample_rate: Sample rate in Hz (24000 for Google TTS)
            sample_width: Sample width in bytes (2 for 16-bit audio)

        Returns:
            WAV formatted audio bytes
        """
        # Create WAV file in memory
        wav_buffer = BytesIO()

        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_data)

        # Get the WAV data
        wav_buffer.seek(0)
        wav_data = wav_buffer.read()

        return wav_data

    def _is_transient_tts_error(self, error: Exception) -> bool:
        """Detect provider/transient errors worth retrying."""
        msg = str(error).lower()
        transient_tokens = [
            "500",
            "internal",
            "503",
            "service unavailable",
            "resource_exhausted",
            "rate limit",
            "quota",
            "timeout",
            "deadline exceeded",
            "temporarily unavailable",
        ]
        return any(token in msg for token in transient_tokens)

    def _tts_retry_delay(self, attempt: int) -> float:
        """Exponential backoff in seconds, capped."""
        return min(8.0, 0.6 * (2 ** (attempt - 1)))

    async def _generate_content_with_retry(
        self,
        *,
        prompt: str,
        config: types.GenerateContentConfig,
        context: str,
        max_attempts: int = 4,
    ):
        """Call Gemini TTS with retry for transient upstream failures."""
        loop = asyncio.get_event_loop()
        last_error: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(
                    "Google TTS request (%s) attempt %s/%s using model=%s",
                    context,
                    attempt,
                    max_attempts,
                    self.model,
                )
                return await loop.run_in_executor(
                    None,
                    lambda p=prompt, c=config: self.client.models.generate_content(
                        model=self.model,
                        contents=p,
                        config=c,
                    ),
                )
            except Exception as e:
                last_error = e
                is_transient = self._is_transient_tts_error(e)
                logger.warning(
                    "Google TTS request failed (%s) attempt %s/%s using model=%s: %s",
                    context,
                    attempt,
                    max_attempts,
                    self.model,
                    str(e),
                )

                if attempt < max_attempts and is_transient:
                    await asyncio.sleep(self._tts_retry_delay(attempt))
                    continue
                raise

        # Defensive fallback; the loop either returns or raises above.
        if last_error:
            raise last_error

    def chunk_text(self, text: str) -> List[str]:
        """
        Intelligently chunk text into pieces that fit within Google's character limit.
        Prioritizes sentence boundaries to maintain natural speech flow.

        Args:
            text: Text to chunk

        Returns:
            List of text chunks
        """
        if len(text) <= MAX_CHUNK_SIZE:
            return [text.strip()]

        chunks = []
        current_chunk = ""

        # Split by sentences first
        sentences = re.split(r'(?<=[.!?])\s+', text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # If a single sentence is too long, split by clauses/phrases
            if len(sentence) > MAX_CHUNK_SIZE:
                # Split by commas, semicolons, or other natural breaks
                parts = re.split(r'(?<=[,;])\s+', sentence)
                for part in parts:
                    part = part.strip()
                    if len(current_chunk) + len(part) + 1 <= MAX_CHUNK_SIZE:
                        current_chunk += (" " + part if current_chunk else part)
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = part
            else:
                # Check if adding this sentence would exceed the limit
                if len(current_chunk) + len(sentence) + 1 <= MAX_CHUNK_SIZE:
                    current_chunk += (" " + sentence if current_chunk else sentence)
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence

        # Add the last chunk if it exists
        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    async def concatenate_wav_files(self, wav_files: List[str], output_file: str) -> None:
        """
        Concatenate multiple WAV files using ffmpeg.

        Args:
            wav_files: List of WAV file paths to concatenate
            output_file: Output file path

        Raises:
            GoogleTTSError: If concatenation fails
        """
        if not wav_files:
            raise GoogleTTSError("No audio files to concatenate")

        if len(wav_files) == 1:
            # If only one file, just copy it
            import shutil
            shutil.copy2(wav_files[0], output_file)
            logger.info(f"Single WAV file copied to {output_file}")
            return

        # Create a temporary file list for ffmpeg
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            for wav_file in wav_files:
                f.write(f"file '{os.path.abspath(wav_file)}'\n")
            concat_file = f.name

        try:
            # Use ffmpeg to concatenate
            cmd = [
                'ffmpeg', '-f', 'concat', '-safe', '0',
                '-i', concat_file, '-c', 'copy',
                '-y', output_file
            ]

            loop = asyncio.get_event_loop()
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise GoogleTTSError(f"ffmpeg concatenation failed: {error_msg}")

            logger.info(f"Successfully concatenated {len(wav_files)} WAV files to {output_file}")

        finally:
            # Clean up the temporary concat file
            try:
                os.unlink(concat_file)
            except OSError:
                pass

    def adjust_audio_speed(self, input_file: str, target_duration: float, output_file: str = None) -> str:
        """
        Adjust audio speed to match a target duration using ffmpeg.

        Args:
            input_file: Path to input audio file
            target_duration: Desired duration in seconds
            output_file: Path for output file (optional, will generate if not provided)

        Returns:
            Path to the speed-adjusted audio file

        Raises:
            GoogleTTSError: If speed adjustment fails or parameters are invalid
        """
        if not os.path.exists(input_file):
            raise GoogleTTSError(f"Input file does not exist: {input_file}")

        if target_duration <= 0:
            raise GoogleTTSError(f"Target duration must be positive: {target_duration}")

        # Get current duration using ffmpeg
        current_duration = get_audio_duration_ffmpeg(input_file)

        if current_duration <= 0:
            raise GoogleTTSError(f"Invalid current duration: {current_duration}")

        # Calculate speed factor
        speed_factor = current_duration / target_duration

        # Validate speed factor (ffmpeg atempo filter has limits)
        if speed_factor < 0.25 or speed_factor > 4.0:
            raise GoogleTTSError(
                f"Speed factor {speed_factor:.3f} is outside valid range (0.25-4.0). "
                f"Current: {current_duration:.2f}s, Target: {target_duration:.2f}s"
            )

        # Generate output filename if not provided
        if output_file is None:
            base_name = os.path.splitext(input_file)[0]
            extension = os.path.splitext(input_file)[1]
            output_file = f"{base_name}_speed_{speed_factor:.3f}{extension}"

        logger.info(f"Adjusting audio speed:")
        logger.info(f"  Input: {input_file} ({current_duration:.2f}s)")
        logger.info(f"  Target duration: {target_duration:.2f}s")
        logger.info(f"  Speed factor: {speed_factor:.3f}x")
        logger.info(f"  Output: {output_file}")

        try:
            # Use ffmpeg atempo filter for speed adjustment
            # For large speed changes, chain multiple atempo filters
            atempo_filters = []
            remaining_factor = speed_factor

            while remaining_factor > 2.0:
                atempo_filters.append("atempo=2.0")
                remaining_factor /= 2.0

            while remaining_factor < 0.5:
                atempo_filters.append("atempo=0.5")
                remaining_factor /= 0.5

            if remaining_factor != 1.0:
                atempo_filters.append(f"atempo={remaining_factor:.6f}")

            if not atempo_filters:
                # No speed change needed, just copy
                cmd = ['ffmpeg', '-i', input_file, '-c', 'copy', '-y', output_file]
            else:
                # Apply speed change
                filter_chain = ",".join(atempo_filters)
                cmd = [
                    'ffmpeg', '-i', input_file,
                    '-filter:a', filter_chain,
                    '-y', output_file
                ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise GoogleTTSError(f"ffmpeg speed adjustment failed: {result.stderr}")

            # Verify the output duration
            output_duration = get_audio_duration_ffmpeg(output_file)
            duration_diff = abs(output_duration - target_duration)

            logger.info(f"Speed adjustment completed:")
            logger.info(f"  Output duration: {output_duration:.2f}s")
            logger.info(f"  Target duration: {target_duration:.2f}s")
            logger.info(f"  Difference: {duration_diff:.2f}s")

            if duration_diff > 0.1:  # Allow 0.1s tolerance
                logger.warning(f"Warning: Output duration differs from target by {duration_diff:.2f}s")

            return output_file

        except subprocess.CalledProcessError as e:
            raise GoogleTTSError(f"Speed adjustment failed: {str(e)}")

    async def text_to_speech_auto_and_wait(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        processed_story_id: Optional[str] = None,
        user_id: Optional[str] = None,
        audio_speed: Optional[float] = None,
        audio_id: Optional[str] = None,
        voice_system_prompt: Optional[str] = None
    ) -> AudioFile:
        """
        Convert text to speech and wait for completion (Google TTS completes synchronously)

        This method exists for API compatibility with other TTS providers.
        Since Google TTS is synchronous, it just calls text_to_speech_auto.

        Args:
            text: Text to convert to speech
            voice_settings: Voice configuration settings
            audio_settings: Audio quality settings
            processed_story_id: ID of the processed story
            user_id: User ID for organizing files in GCS
            audio_speed: Audio speed multiplier
            audio_id: Optional audio ID to use
            voice_system_prompt: Custom system prompt for voice generation

        Returns:
            AudioFile object with COMPLETED status
        """
        return await self.text_to_speech_auto(
            text=text,
            voice_settings=voice_settings,
            audio_settings=audio_settings,
            processed_story_id=processed_story_id,
            user_id=user_id,
            audio_speed=audio_speed,
            audio_id=audio_id,
            voice_system_prompt=voice_system_prompt
        )

    async def text_to_speech_auto(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        processed_story_id: Optional[str] = None,
        user_id: Optional[str] = None,
        audio_speed: Optional[float] = None,
        audio_id: Optional[str] = None,
        voice_system_prompt: Optional[str] = None
    ) -> AudioFile:
        """
        Convert text to speech using Google Gemini TTS API

        Args:
            text: Text to convert to speech
            voice_settings: Voice configuration settings (voice_id should be a Google voice name)
            audio_settings: Audio quality settings
            processed_story_id: ID of the processed story
            user_id: User ID for organizing files in GCS
            audio_speed: Audio speed multiplier (not supported by Google API, will adjust post-generation)
            audio_id: Optional audio ID to use (for overwriting existing audio)
            voice_system_prompt: Custom system prompt for voice generation (e.g., "speak energetically")

        Returns:
            AudioFile object with generated audio information
        """
        if voice_settings is None:
            voice_settings = VoiceSettings()
            voice_settings.voice_id = "Puck"  # Default voice

        if audio_settings is None:
            audio_settings = AudioSettings()

        # Use provided audio_id or generate new UUID
        audio_file_id = audio_id if audio_id else str(uuid.uuid4())

        # Google TTS outputs WAV format by default
        file_name = f"audio_{audio_file_id}.wav"
        file_path = self.audio_dir / file_name

        logger.info(f"🎵 Using audio_file_id: {audio_file_id} (provided: {bool(audio_id)})")

        try:
            logger.info(f"Starting Google TTS generation for text length: {len(text)}")
            logger.info(f"Voice: {voice_settings.voice_id}, Model: {self.model}")

            # Check if text is too long and needs chunking
            if len(text) > MAX_CHUNK_SIZE:
                logger.info(f"Text exceeds {MAX_CHUNK_SIZE} characters, using chunking approach")
                return await self._synthesize_long_text(
                    text=text,
                    voice_settings=voice_settings,
                    audio_settings=audio_settings,
                    processed_story_id=processed_story_id,
                    user_id=user_id,
                    audio_file_id=audio_file_id,
                    file_path=file_path,
                    audio_speed=audio_speed,
                    voice_system_prompt=voice_system_prompt
                )

            # Prepare the prompt with emotion/context
            # Use custom voice_system_prompt if provided, otherwise use default
            #default_prompt = "you are recording a voiceover for youtube script, read this with emotion"
            # system_prompt = voice_system_prompt if voice_system_prompt else ""
            # prompt = f"{system_prompt}: {text}"
            if voice_system_prompt:
                    prompt = f"{voice_system_prompt}: {text}"
            else:
                prompt = text

            # Configure TTS request
            config = types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_settings.voice_id,
                        )
                    )
                ),
            )

            logger.info("=" * 80)
            logger.info("📤 GOOGLE GEMINI TTS API REQUEST")
            logger.info(f"Model: {self.model}")
            logger.info(f"Voice: {voice_settings.voice_id}")
            logger.info(f"Text length: {len(text)} characters")
            logger.info(f"Prompt: {prompt[:300]}...")
            logger.info("=" * 80)

            response = await self._generate_content_with_retry(
                prompt=prompt,
                config=config,
                context=f"single-text len={len(text)}",
            )

            # Extract raw PCM audio data from response
            pcm_data = response.candidates[0].content.parts[0].inline_data.data

            logger.info(f"✅ Received raw PCM data: {len(pcm_data)} bytes")

            # Convert raw PCM data to proper WAV format
            # Google TTS returns 24kHz, mono, 16-bit PCM data
            wav_data = self._pcm_to_wav(pcm_data, channels=1, sample_rate=24000, sample_width=2)

            logger.info(f"✅ Converted to WAV format: {len(wav_data)} bytes")

            # Upload to GCS if user_id is provided, otherwise save locally
            gcs_result = None
            if user_id:
                try:
                    from services.gcs_service import get_gcs_service
                    gcs_service = get_gcs_service()

                    # Upload WAV audio bytes to GCS
                    gcs_result = await gcs_service.upload_audio_bytes(
                        audio_bytes=wav_data,
                        user_id=user_id,
                        file_extension="wav",
                        audio_id=audio_file_id,
                        metadata={
                            'text_length': len(text),
                            'voice_id': voice_settings.voice_id,
                            'model': self.model,
                            'provider': 'google',
                            'processed_story_id': str(processed_story_id) if processed_story_id else None
                        }
                    )

                    if gcs_result:
                        logger.info(f"✅ Audio uploaded to GCS: {gcs_result['gcs_path']}")
                        # Update file_path to use GCS signed URL for access
                        file_path = gcs_result['signed_url']
                    else:
                        logger.warning("⚠️ GCS upload failed, falling back to local storage")
                        raise Exception("GCS upload failed")

                except Exception as gcs_error:
                    logger.warning(f"⚠️ GCS upload failed ({str(gcs_error)}), falling back to local storage")
                    gcs_result = None

            # Fallback to local storage if no user_id or GCS failed
            if not gcs_result:
                # Save audio file locally as WAV
                async with aiofiles.open(file_path, 'wb') as f:
                    await f.write(wav_data)
                logger.info(f"📁 Audio saved locally: {file_path}")

            # Get real duration from the generated audio file
            real_duration = 0.0
            if not gcs_result:
                # For local files, we can get the real duration immediately
                real_duration = get_audio_duration_from_wav(str(file_path))
            else:
                # For GCS files, create temporary file from wav_data to get duration
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                    temp_file.write(wav_data)
                    temp_path = temp_file.name

                try:
                    real_duration = get_audio_duration_from_wav(temp_path)
                    # Clean up temp file
                    Path(temp_path).unlink()
                except Exception as e:
                    logger.warning(f"⚠️ Could not get duration from temp file: {e}")
                    # Clean up temp file even on error
                    try:
                        Path(temp_path).unlink()
                    except:
                        pass

            # Use real duration if available, otherwise estimate
            if real_duration > 0:
                duration = real_duration
                logger.info(f"🎵 Using real duration: {duration:.3f}s")
            else:
                # Estimate duration based on text length (~150 WPM average)
                duration = len(text.split()) / 150 * 60
                logger.warning(f"⚠️ Could not get real duration, using estimated: {duration:.3f}s")

            # Apply audio speed adjustment if requested
            if audio_speed and audio_speed != 1.0:
                logger.info(f"🎛️  Applying audio speed adjustment: {audio_speed}x")
                target_duration = duration / audio_speed

                # Handle speed adjustment for local vs GCS files
                if not gcs_result:
                    # Local file - adjust directly
                    try:
                        adjusted_file_path = self.adjust_audio_speed(
                            input_file=str(file_path),
                            target_duration=target_duration
                        )
                        file_path = Path(adjusted_file_path)
                        duration = get_audio_duration_ffmpeg(str(file_path))
                        logger.info(f"✅ Audio speed adjusted (local): {duration:.3f}s")
                    except Exception as speed_error:
                        logger.error(f"Failed to adjust audio speed: {str(speed_error)}")
                        raise GoogleTTSError(f"Audio speed adjustment failed: {str(speed_error)}")
                else:
                    # GCS file - download, adjust, re-upload
                    try:
                        # Create temporary file from wav_data
                        import tempfile
                        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_input:
                            temp_input.write(wav_data)
                            temp_input_path = temp_input.name

                        # Adjust speed
                        adjusted_temp_path = self.adjust_audio_speed(
                            input_file=temp_input_path,
                            target_duration=target_duration
                        )

                        # Read adjusted audio
                        async with aiofiles.open(adjusted_temp_path, 'rb') as f:
                            adjusted_wav_data = await f.read()

                        # Re-upload to GCS
                        from services.gcs_service import get_gcs_service
                        gcs_service = get_gcs_service()

                        gcs_result = await gcs_service.upload_audio_bytes(
                            audio_bytes=adjusted_wav_data,
                            user_id=user_id,
                            file_extension="wav",
                            audio_id=audio_file_id,
                            metadata={
                                'text_length': len(text),
                                'voice_id': voice_settings.voice_id,
                                'model': self.model,
                                'provider': 'google',
                                'processed_story_id': str(processed_story_id) if processed_story_id else None,
                                'audio_speed': audio_speed
                            }
                        )

                        if gcs_result:
                            file_path = gcs_result['signed_url']
                            duration = get_audio_duration_ffmpeg(adjusted_temp_path)
                            logger.info(f"✅ Audio speed adjusted (GCS): {duration:.3f}s")
                        else:
                            raise Exception("GCS re-upload failed after speed adjustment")

                        # Clean up temp files
                        try:
                            Path(temp_input_path).unlink()
                            Path(adjusted_temp_path).unlink()
                        except:
                            pass

                    except Exception as speed_error:
                        logger.error(f"Failed to adjust audio speed for GCS file: {str(speed_error)}")
                        raise GoogleTTSError(f"Audio speed adjustment failed: {str(speed_error)}")

            # Convert processed_story_id to UUID if provided, otherwise None
            processed_story_uuid = None
            if processed_story_id and processed_story_id.strip():
                try:
                    processed_story_uuid = uuid.UUID(processed_story_id)
                except ValueError:
                    logger.warning(f"Invalid UUID format for processed_story_id: {processed_story_id}")

            audio_file = AudioFile(
                id=audio_file_id,
                processed_story_id=processed_story_uuid,
                file_path=str(file_path),
                duration=duration,
                format="wav",
                voice_settings=voice_settings,
                audio_settings=audio_settings,
                status=GenerationStatus.COMPLETED,
                created_at=datetime.now()
            )

            # Add GCS information if available
            if gcs_result:
                audio_file.url = gcs_result['signed_url']
                audio_file.gcs_path = gcs_result['gcs_path']
                audio_file.public_url = gcs_result['public_url']

            # Store user_id for later use (e.g., duration adjustment)
            if user_id:
                audio_file.__dict__['user_id'] = user_id

            # Save metadata to JSON
            await self._save_audio_metadata(audio_file)

            logger.info(f"Successfully generated Google TTS audio file: {file_path}")
            return audio_file

        except Exception as e:
            logger.error(f"Error in Google TTS generation: {str(e)}")

            # Convert processed_story_id to UUID if provided, otherwise None
            processed_story_uuid = None
            if processed_story_id and processed_story_id.strip():
                try:
                    processed_story_uuid = uuid.UUID(processed_story_id)
                except ValueError:
                    logger.warning(f"Invalid UUID format for processed_story_id: {processed_story_id}")

            # Create failed audio file record
            audio_file = AudioFile(
                id=audio_file_id,
                processed_story_id=processed_story_uuid,
                file_path=str(file_path),
                format="wav",
                voice_settings=voice_settings,
                audio_settings=audio_settings,
                status=GenerationStatus.FAILED,
                created_at=datetime.now()
            )

            await self._save_audio_metadata(audio_file)
            raise GoogleTTSError(f"Google TTS generation failed: {str(e)}")

    async def _synthesize_long_text(
        self,
        text: str,
        voice_settings: VoiceSettings,
        audio_settings: AudioSettings,
        processed_story_id: Optional[str],
        user_id: Optional[str],
        audio_file_id: str,
        file_path: Path,
        audio_speed: Optional[float] = None,
        voice_system_prompt: Optional[str] = None
    ) -> AudioFile:
        """
        Synthesize long text by chunking it and concatenating the results.

        Args:
            text: Long text to synthesize
            voice_settings: Voice configuration
            audio_settings: Audio settings
            processed_story_id: Story ID
            user_id: User ID
            audio_file_id: Audio file ID
            file_path: Output file path
            audio_speed: Audio speed multiplier (optional)
            voice_system_prompt: Custom system prompt for voice generation

        Returns:
            AudioFile object with concatenated audio
        """
        logger.info(f"Starting long text synthesis: {len(text)} characters")

        # Chunk the text
        chunks = self.chunk_text(text)
        logger.info(f"Split text into {len(chunks)} chunks")

        # Create temporary directory for chunk files
        temp_dir = tempfile.mkdtemp(prefix="google_tts_chunks_")
        temp_wav_files = []

        try:
            # Synthesize each chunk
            for i, chunk in enumerate(chunks):
                # Prepare the prompt with emotion/context
                # Use custom voice_system_prompt if provided, otherwise use default
                #default_prompt = "you are recording a voiceover for youtube script, read this with emotion"
                if voice_system_prompt:
                    prompt = f"{voice_system_prompt}: {chunk}"
                else:
                    prompt = chunk

                logger.info(f"Synthesizing chunk {i + 1}/{len(chunks)}: {len(chunk)} characters")
                logger.info(f"Preview prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")

                # Configure TTS request
                config = types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_settings.voice_id,
                            )
                        )
                    ),
                )

                response = await self._generate_content_with_retry(
                    prompt=prompt,
                    config=config,
                    context=f"chunk {i + 1}/{len(chunks)} len={len(chunk)}",
                )

                # Extract and convert PCM data to WAV
                pcm_data = response.candidates[0].content.parts[0].inline_data.data
                wav_data = self._pcm_to_wav(pcm_data, channels=1, sample_rate=24000, sample_width=2)

                # Save chunk to temporary file
                chunk_file = os.path.join(temp_dir, f"chunk_{i:03d}.wav")
                async with aiofiles.open(chunk_file, 'wb') as f:
                    await f.write(wav_data)

                temp_wav_files.append(chunk_file)
                logger.info(f"✅ Chunk {i + 1} saved: {len(wav_data)} bytes")

                # Small delay to be respectful to the API
                await asyncio.sleep(0.1)

            # Concatenate all chunks
            logger.info(f"Concatenating {len(temp_wav_files)} WAV files...")
            temp_concat_file = os.path.join(temp_dir, f"concatenated_{audio_file_id}.wav")
            await self.concatenate_wav_files(temp_wav_files, temp_concat_file)

            # Read the concatenated file
            async with aiofiles.open(temp_concat_file, 'rb') as f:
                wav_data = await f.read()

            logger.info(f"✅ Concatenated WAV file: {len(wav_data)} bytes")

            # Upload to GCS if user_id is provided, otherwise save locally
            gcs_result = None
            if user_id:
                try:
                    from services.gcs_service import get_gcs_service
                    gcs_service = get_gcs_service()

                    # Upload WAV audio bytes to GCS
                    gcs_result = await gcs_service.upload_audio_bytes(
                        audio_bytes=wav_data,
                        user_id=user_id,
                        file_extension="wav",
                        audio_id=audio_file_id,
                        metadata={
                            'text_length': len(text),
                            'voice_id': voice_settings.voice_id,
                            'model': self.model,
                            'provider': 'google',
                            'processed_story_id': str(processed_story_id) if processed_story_id else None,
                            'chunk_count': len(chunks)
                        }
                    )

                    if gcs_result:
                        logger.info(f"✅ Concatenated audio uploaded to GCS: {gcs_result['gcs_path']}")
                        file_path = gcs_result['signed_url']
                    else:
                        logger.warning("⚠️ GCS upload failed, falling back to local storage")
                        raise Exception("GCS upload failed")

                except Exception as gcs_error:
                    logger.warning(f"⚠️ GCS upload failed ({str(gcs_error)}), falling back to local storage")
                    gcs_result = None

            # Fallback to local storage if no user_id or GCS failed
            if not gcs_result:
                async with aiofiles.open(file_path, 'wb') as f:
                    await f.write(wav_data)
                logger.info(f"📁 Concatenated audio saved locally: {file_path}")

            # Get real duration from the concatenated audio file
            real_duration = 0.0
            if not gcs_result:
                real_duration = get_audio_duration_from_wav(str(file_path))
            else:
                # For GCS files, use the temp concatenated file
                real_duration = get_audio_duration_from_wav(temp_concat_file)

            # Use real duration if available, otherwise estimate
            if real_duration > 0:
                duration = real_duration
                logger.info(f"🎵 Using real duration: {duration:.3f}s")
            else:
                # Estimate duration based on text length (~150 WPM average)
                duration = len(text.split()) / 150 * 60
                logger.warning(f"⚠️ Could not get real duration, using estimated: {duration:.3f}s")

            # Apply audio speed adjustment if requested
            if audio_speed and audio_speed != 1.0:
                logger.info(f"🎛️  Applying audio speed adjustment to long text: {audio_speed}x")
                target_duration = duration / audio_speed

                # Handle speed adjustment for local vs GCS files
                if not gcs_result:
                    # Local file - adjust directly
                    try:
                        adjusted_file_path = self.adjust_audio_speed(
                            input_file=str(file_path),
                            target_duration=target_duration
                        )
                        file_path = Path(adjusted_file_path)
                        duration = get_audio_duration_ffmpeg(str(file_path))
                        logger.info(f"✅ Long text audio speed adjusted (local): {duration:.3f}s")
                    except Exception as speed_error:
                        logger.error(f"Failed to adjust audio speed: {str(speed_error)}")
                        raise GoogleTTSError(f"Audio speed adjustment failed: {str(speed_error)}")
                else:
                    # GCS file - adjust the temp file and re-upload
                    try:
                        # Adjust speed on the temp concatenated file
                        adjusted_temp_path = self.adjust_audio_speed(
                            input_file=temp_concat_file,
                            target_duration=target_duration
                        )

                        # Read adjusted audio
                        async with aiofiles.open(adjusted_temp_path, 'rb') as f:
                            adjusted_wav_data = await f.read()

                        # Re-upload to GCS
                        from services.gcs_service import get_gcs_service
                        gcs_service = get_gcs_service()

                        gcs_result = await gcs_service.upload_audio_bytes(
                            audio_bytes=adjusted_wav_data,
                            user_id=user_id,
                            file_extension="wav",
                            audio_id=audio_file_id,
                            metadata={
                                'text_length': len(text),
                                'voice_id': voice_settings.voice_id,
                                'model': self.model,
                                'provider': 'google',
                                'processed_story_id': str(processed_story_id) if processed_story_id else None,
                                'chunk_count': len(chunks),
                                'audio_speed': audio_speed
                            }
                        )

                        if gcs_result:
                            file_path = gcs_result['signed_url']
                            duration = get_audio_duration_ffmpeg(adjusted_temp_path)
                            logger.info(f"✅ Long text audio speed adjusted (GCS): {duration:.3f}s")
                        else:
                            raise Exception("GCS re-upload failed after speed adjustment")

                        # Clean up adjusted temp file
                        try:
                            Path(adjusted_temp_path).unlink()
                        except:
                            pass

                    except Exception as speed_error:
                        logger.error(f"Failed to adjust audio speed for GCS file: {str(speed_error)}")
                        raise GoogleTTSError(f"Audio speed adjustment failed: {str(speed_error)}")

            # Convert processed_story_id to UUID if provided
            processed_story_uuid = None
            if processed_story_id and processed_story_id.strip():
                try:
                    processed_story_uuid = uuid.UUID(processed_story_id)
                except ValueError:
                    logger.warning(f"Invalid UUID format for processed_story_id: {processed_story_id}")

            audio_file = AudioFile(
                id=audio_file_id,
                processed_story_id=processed_story_uuid,
                file_path=str(file_path),
                duration=duration,
                format="wav",
                voice_settings=voice_settings,
                audio_settings=audio_settings,
                status=GenerationStatus.COMPLETED,
                created_at=datetime.now()
            )

            # Add GCS information if available
            if gcs_result:
                audio_file.url = gcs_result['signed_url']
                audio_file.gcs_path = gcs_result['gcs_path']
                audio_file.public_url = gcs_result['public_url']

            # Store user_id for later use
            if user_id:
                audio_file.__dict__['user_id'] = user_id

            # Save metadata
            await self._save_audio_metadata(audio_file)

            logger.info(f"✅ Successfully generated long text audio from {len(chunks)} chunks")
            return audio_file

        except Exception as e:
            logger.error(f"Error in long text synthesis: {str(e)}")
            raise GoogleTTSError(f"Long text synthesis failed: {str(e)}")

        finally:
            # Clean up temporary files and directory
            for temp_file in temp_wav_files:
                try:
                    if os.path.exists(temp_file):
                        os.unlink(temp_file)
                except OSError:
                    pass

            # Clean up concatenated file
            try:
                temp_concat_file = os.path.join(temp_dir, f"concatenated_{audio_file_id}.wav")
                if os.path.exists(temp_concat_file):
                    os.unlink(temp_concat_file)
            except (OSError, NameError):
                pass

            # Remove temp directory
            try:
                os.rmdir(temp_dir)
            except OSError:
                pass

    async def _save_audio_metadata(self, audio_file: AudioFile):
        """Save audio file metadata to JSON"""
        try:
            import json
            metadata_file = self.audio_dir / f"metadata_{audio_file.id}.json"

            # Convert to dict for JSON serialization
            metadata = audio_file.model_dump()

            # Add user_id field if it exists in the object
            if hasattr(audio_file, 'user_id') or 'user_id' in audio_file.__dict__:
                metadata['user_id'] = getattr(audio_file, 'user_id', None)

            # Convert UUID objects to strings
            if 'id' in metadata and hasattr(metadata['id'], '__str__'):
                metadata['id'] = str(metadata['id'])
            if 'processed_story_id' in metadata and metadata['processed_story_id'] is not None:
                metadata['processed_story_id'] = str(metadata['processed_story_id'])

            # Convert datetime to ISO format
            if 'created_at' in metadata:
                metadata['created_at'] = metadata['created_at'].isoformat()

            async with aiofiles.open(metadata_file, 'w') as f:
                await f.write(json.dumps(metadata, indent=2))

        except Exception as e:
            logger.error(f"Error saving audio metadata: {str(e)}")

    async def load_audio_metadata(self, audio_id: str) -> Optional[AudioFile]:
        """Load audio file metadata from JSON"""
        try:
            import json
            metadata_file = self.audio_dir / f"metadata_{audio_id}.json"

            if not metadata_file.exists():
                return None

            async with aiofiles.open(metadata_file, 'r') as f:
                content = await f.read()
                metadata = json.loads(content)

            # Convert datetime back
            metadata['created_at'] = datetime.fromisoformat(metadata['created_at'])

            # Extract special fields that aren't part of AudioFile model
            user_id = metadata.pop('user_id', None)

            audio_file = AudioFile(**metadata)

            # Add the special attributes back
            if user_id:
                audio_file.__dict__['user_id'] = user_id

            return audio_file

        except Exception as e:
            logger.error(f"Error loading audio metadata: {str(e)}")
            return None

    @staticmethod
    def get_available_voices() -> List[Dict[str, Any]]:
        """
        Get list of available Google Gemini TTS voices

        Returns:
            List of voice dictionaries with metadata
        """
        voices = []
        for voice_name in GOOGLE_VOICES:
            voices.append({
                "voice_id": voice_name,
                "name": voice_name,
                "language": "English",
                "description": f"Google Gemini {voice_name} voice",
                "provider": "google"
            })
        return voices
