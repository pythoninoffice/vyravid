import requests
import json
import uuid
import asyncio
import aiohttp
import aiofiles
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
import logging
import os
from dotenv import load_dotenv
import ffmpeg

from models.story_models import AudioFile, VoiceSettings, AudioSettings, GenerationStatus

load_dotenv()

logger = logging.getLogger(__name__)

def get_audio_duration(file_path: str) -> float:
    """
    Get the actual duration of an audio file using ffprobe
    
    Args:
        file_path: Path to the audio file
        
    Returns:
        Duration in seconds as float
    """
    try:
        probe = ffmpeg.probe(file_path, v='quiet', print_format='json', show_entries='format=duration')
        duration_str = probe['format']['duration']
        return float(duration_str)
    except Exception as e:
        logger.warning(f"Failed to get audio duration for {file_path}: {e}")
        # Fallback to estimated duration based on file size (very rough estimate)
        try:
            import os
            file_size = os.path.getsize(file_path)
            # Very rough estimate: ~128kbps MP3 = 16KB per second
            estimated_seconds = file_size / 16000
            logger.info(f"Using rough file-size based estimate: {estimated_seconds}s")
            return estimated_seconds
        except:
            return 0.0

# Constants for text length limits
SYNC_TTS_MAX_LENGTH = 5000
ASYNC_TTS_MAX_LENGTH = 200000  # Regular async TTS limit
LONG_TTS_MAX_LENGTH = 1000000  # Long TTS limit (1M characters)

# Constants for async polling behavior
DEFAULT_POLL_INTERVAL = 5  # seconds
DEFAULT_MAX_WAIT_TIME = 3000  # 50 minutes
LONG_TTS_MAX_WAIT_TIME = 3000  # 50 minutes for long TTS

class TTSService:
    """
    Text-to-Speech service using Minimax API with support for various text lengths.
    
    Supported TTS Methods:
    - Synchronous TTS: Up to 5,000 characters (instant response)
    - Asynchronous TTS: Up to 50,000 characters (async processing)
    - Long Asynchronous TTS: Up to 1,000,000 characters (async processing for long content)
    - Split Processing: For texts exceeding 1M characters (splits into chunks)
    
    The service automatically chooses the best method based on text length,
    or you can force a specific method using the force_method parameter.
    
    Key Methods:
    - text_to_speech_auto(): Returns immediately, may be GENERATING status
    - text_to_speech_auto_and_wait(): Waits for completion, always returns COMPLETED
    - wait_for_async_completion(): Polls async jobs until completion
    """
    
    def __init__(self):
        """Initialize TTS service with Minimax configuration"""
        self.group_id = os.getenv("MINIMAX_GROUP_ID")
        self.api_key = os.getenv("MINIMAX_API_KEY")
        
        #logger.info(f'MINIMAX GROUPID: {self.group_id}')
        #logger.info(f'MINIMAX APIKEY: {self.api_key}')
        if not self.group_id or not self.api_key:
            logger.warning("MINIMAX_GROUP_ID / MINIMAX_API_KEY not set — Minimax TTS disabled until configured")
            self.group_id = self.group_id or ""
            self.api_key = self.api_key or ""
        
        #self.sync_url = f"https://api.minimax.io/v1/t2a_v2?GroupId={self.group_id}"
        self.sync_url = f"https://api.minimax.io/v1/t2a_v2"
        self.async_url = f"https://api.minimax.io/v1/t2a_async_v2?GroupId={self.group_id}"
        self.long_async_url = f"https://api.minimax.io/v1/t2a_async_long?GroupId={self.group_id}"
        
        # Create audio directory for file storage
        self.audio_dir = Path("data/audio")
        self.audio_dir.mkdir(parents=True, exist_ok=True)
    
    def determine_tts_method(self, text: str, force_method: Optional[str] = None) -> str:
        """
        Determine the best TTS method based on text length
        
        Args:
            text: Input text
            force_method: Force a specific method ('sync', 'async', 'long_async')
        
        Returns:
            TTS method to use: 'sync', 'async', or 'long_async'
        """
        if force_method:
            return force_method
        
        text_length = len(text)
        
        if text_length <= SYNC_TTS_MAX_LENGTH:
            return 'sync'
        elif text_length <= ASYNC_TTS_MAX_LENGTH:
            return 'async'
        elif text_length <= LONG_TTS_MAX_LENGTH:
            return 'long_async'
        else:
            raise ValueError(f"Text too long ({text_length} chars). Maximum supported length is {LONG_TTS_MAX_LENGTH} characters.")
    
    async def text_to_speech_auto(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        processed_story_id: Optional[str] = None,
        force_method: Optional[str] = None,
        user_id: Optional[str] = None,
        audio_speed: Optional[float] = None,
        audio_id: Optional[str] = None,
        voice_system_prompt: Optional[str] = None
    ) -> AudioFile:
        """
        Automatically choose the best TTS method based on text length and wait for completion
        
        Args:
            text: Text to convert to speech
            voice_settings: Voice configuration settings
            audio_settings: Audio quality settings
            processed_story_id: ID of the processed story
            force_method: Force a specific method ('sync', 'async', 'long_async')
            user_id: User ID for organizing files in GCS
        
        Returns:
            AudioFile object with completed audio (COMPLETED status)
        """
        method = self.determine_tts_method(text, force_method)
        
        logger.info(f"Using TTS method '{method}' for text length: {len(text)} characters")
        
        if method == 'sync':
            return await self.text_to_speech_sync(text, voice_settings, audio_settings, processed_story_id, user_id, audio_speed, audio_id)
        elif method == 'async':
            # Start async generation
            audio_file = await self.text_to_speech_async(text, voice_settings, audio_settings, processed_story_id, user_id, audio_speed, audio_id)
            # Wait for completion
            if audio_file.status == GenerationStatus.GENERATING:
                logger.info(f"🎵 Async TTS started, waiting for completion...")
                audio_file = await self.wait_for_async_completion(audio_file, DEFAULT_MAX_WAIT_TIME)
            return audio_file
        elif method == 'long_async':
            # Start long async generation
            audio_file = await self.text_to_speech_async_long(text, voice_settings, audio_settings, processed_story_id, user_id, audio_speed, audio_id)
            # Wait for completion with longer timeout
            if audio_file.status == GenerationStatus.GENERATING:
                logger.info(f"🎵 Long async TTS started, waiting for completion...")
                audio_file = await self.wait_for_async_completion(audio_file, LONG_TTS_MAX_WAIT_TIME)
            return audio_file
        else:
            raise ValueError(f"Unknown TTS method: {method}")
    
    def split_text_intelligently(self, text: str, max_length: int = LONG_TTS_MAX_LENGTH) -> List[str]:
        """
        Split text into chunks that respect sentence boundaries and character limits
        
        Args:
            text: Text to split
            max_length: Maximum length per chunk
        
        Returns:
            List of text chunks
        """
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # Split by paragraphs first
        paragraphs = text.split('\n\n')
        
        for paragraph in paragraphs:
            # If single paragraph is too long, split by sentences
            if len(paragraph) > max_length:
                sentences = paragraph.split('. ')
                for i, sentence in enumerate(sentences):
                    # Add period back except for last sentence
                    if i < len(sentences) - 1 and not sentence.endswith('.'):
                        sentence += '.'
                    
                    # If adding this sentence would exceed limit, start new chunk
                    if len(current_chunk) + len(sentence) + 1 > max_length and current_chunk:
                        chunks.append(current_chunk.strip())
                        current_chunk = sentence
                    else:
                        if current_chunk:
                            current_chunk += ' ' + sentence
                        else:
                            current_chunk = sentence
            else:
                # If adding this paragraph would exceed limit, start new chunk
                if len(current_chunk) + len(paragraph) + 2 > max_length and current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = paragraph
                else:
                    if current_chunk:
                        current_chunk += '\n\n' + paragraph
                    else:
                        current_chunk = paragraph
        
        # Add remaining chunk
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    async def text_to_speech_split_long(
        self, 
        text: str, 
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        processed_story_id: Optional[str] = None,
        wait_for_completion: bool = False
    ) -> List[AudioFile]:
        """
        Convert extremely long text to speech by splitting into multiple audio files
        
        Args:
            text: Text to convert (can exceed 1M characters)
            voice_settings: Voice configuration settings
            audio_settings: Audio quality settings
            processed_story_id: ID of the processed story
            wait_for_completion: If True, wait for all chunks to complete
        
        Returns:
            List of AudioFile objects for each chunk
        """
        chunks = self.split_text_intelligently(text)
        audio_files = []
        
        logger.info(f"Splitting text into {len(chunks)} chunks for TTS processing")
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)}, length: {len(chunk)} characters")
            
            # Use the appropriate method based on chunk length
            if wait_for_completion:
                audio_file = await self.text_to_speech_auto_and_wait(
                    chunk, 
                    voice_settings, 
                    audio_settings, 
                    processed_story_id,
                    audio_speed
                )
            else:
                audio_file = await self.text_to_speech_auto(
                    chunk, 
                    voice_settings, 
                    audio_settings, 
                    processed_story_id,
                    audio_speed
                )
            
            # Add chunk metadata
            audio_file.__dict__['chunk_index'] = i
            audio_file.__dict__['total_chunks'] = len(chunks)
            audio_file.__dict__['is_part_of_split'] = True
            
            await self._save_audio_metadata(audio_file)
            audio_files.append(audio_file)
        
        return audio_files
    
    async def wait_for_async_completion(
        self, 
        audio_file: AudioFile, 
        max_wait_time: int = DEFAULT_MAX_WAIT_TIME,
        poll_interval: int = DEFAULT_POLL_INTERVAL
    ) -> AudioFile:
        """
        Wait for async TTS generation to complete with polling
        
        Args:
            audio_file: AudioFile object with task_id and GENERATING status
            max_wait_time: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds
        
        Returns:
            Updated AudioFile object with COMPLETED or FAILED status
        """
        if not audio_file.task_id:
            raise ValueError("AudioFile must have task_id for async waiting")
        
        if audio_file.status != GenerationStatus.GENERATING:
            logger.info(f"Audio file {audio_file.id} is already in status: {audio_file.status}")
            return audio_file
        
        start_time = asyncio.get_event_loop().time()
        elapsed_time = 0
        
        logger.info(f"⏳ Waiting for async TTS completion. Task ID: {audio_file.task_id}")
        logger.info(f"   Max wait time: {max_wait_time}s, Poll interval: {poll_interval}s")
        
        while elapsed_time < max_wait_time:
            try:
                # Check status
                updated_audio_file = await self.check_async_status(audio_file)
                
                if updated_audio_file.status == GenerationStatus.COMPLETED:
                    logger.info(f"✅ Async TTS completed after {elapsed_time:.1f}s")
                    return updated_audio_file
                elif updated_audio_file.status == GenerationStatus.FAILED:
                    logger.error(f"❌ Async TTS failed after {elapsed_time:.1f}s")
                    return updated_audio_file
                
                # Still generating, wait and retry
                logger.info(f"🔄 TTS still generating... ({elapsed_time:.1f}s elapsed)")
                await asyncio.sleep(poll_interval)
                elapsed_time = asyncio.get_event_loop().time() - start_time
                
                # Update the audio_file reference for next iteration
                audio_file = updated_audio_file
                
            except Exception as e:
                logger.error(f"Error checking async status: {str(e)}")
                # Don't immediately fail, try again after a longer wait
                await asyncio.sleep(poll_interval * 2)
                elapsed_time = asyncio.get_event_loop().time() - start_time
        
        # Timeout reached
        logger.error(f"⏰ Timeout waiting for async TTS completion after {max_wait_time}s")
        audio_file.status = GenerationStatus.FAILED
        await self._save_audio_metadata(audio_file)
        
        raise TimeoutError(f"Async TTS generation timed out after {max_wait_time} seconds")
    
    async def text_to_speech_auto_and_wait(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        processed_story_id: Optional[str] = None,
        force_method: Optional[str] = None,
        max_wait_time: int = DEFAULT_MAX_WAIT_TIME,
        user_id: Optional[str] = None,
        audio_speed: Optional[float] = None,
        audio_id: Optional[str] = None,
        voice_system_prompt: Optional[str] = None
    ) -> AudioFile:
        """
        Convert text to speech and wait for completion if async

        This is the method to use for video processing pipelines where you need
        the audio file to be ready before proceeding.

        Args:
            text: Text to convert to speech
            voice_settings: Voice configuration settings
            audio_settings: Audio quality settings
            processed_story_id: ID of the processed story
            force_method: Force a specific method ('sync', 'async', 'long_async')
            max_wait_time: Maximum time to wait for async completion (seconds)
            audio_id: Optional audio ID to use (for overwriting existing audio)

        Returns:
            AudioFile object with COMPLETED status (ready to use)
        """
        # Start the TTS generation
        audio_file = await self.text_to_speech_auto(
            text, voice_settings, audio_settings, processed_story_id, force_method, user_id, audio_speed, audio_id, voice_system_prompt
        )
        
        # If it's async (GENERATING status), wait for completion
        if audio_file.status == GenerationStatus.GENERATING:
            logger.info(f"🎵 TTS started async generation, waiting for completion...")
            
            # Use longer timeout for long TTS operations
            is_long_form = getattr(audio_file, 'is_long_form', False) or 'audio_long_' in audio_file.file_path
            actual_timeout = LONG_TTS_MAX_WAIT_TIME if is_long_form else max_wait_time
            
            audio_file = await self.wait_for_async_completion(audio_file, actual_timeout)
        
        # Verify the audio file is ready
        if audio_file.status != GenerationStatus.COMPLETED:
            raise Exception(f"TTS generation failed with status: {audio_file.status}")
        
        # Verify the file exists (skip for GCS URLs)
        if not audio_file.url and not Path(audio_file.file_path).exists():
            raise Exception(f"Audio file not found on disk: {audio_file.file_path}")
        
        logger.info(f"🎉 TTS generation completed successfully: {audio_file.file_path}")
        return audio_file
    
    async def text_to_speech_sync(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        processed_story_id: Optional[str] = None,
        user_id: Optional[str] = None,
        audio_speed: Optional[float] = None,
        audio_id: Optional[str] = None
    ) -> AudioFile:
        """
        Convert text to speech using synchronous API

        Args:
            text: Text to convert to speech
            voice_settings: Voice configuration settings
            audio_settings: Audio quality settings
            processed_story_id: ID of the processed story

        Returns:
            AudioFile object with generated audio information
        """
        if voice_settings is None:
            voice_settings = VoiceSettings()
        if audio_settings is None:
            audio_settings = AudioSettings()

        # Use provided audio_id or generate new UUID
        audio_file_id = audio_id if audio_id else str(uuid.uuid4())
        file_name = f"audio_{audio_file_id}.{audio_settings.format}"
        file_path = self.audio_dir / file_name

        logger.info(f"🎵 Using audio_file_id: {audio_file_id} (provided: {bool(audio_id)})")
        
        try:
            logger.info(f"Starting synchronous TTS generation for text length: {len(text)}")
            
            # Use audio_speed if provided, otherwise fall back to voice_settings.speed
            speed_value = audio_speed if audio_speed is not None else voice_settings.speed

            payload = {
                #"model": "speech-02-hd",
                'model': "speech-02-turbo",
                "text": text,
                "stream": False,
                "voice_setting": {
                    "voice_id": voice_settings.voice_id,
                    "speed": float(speed_value), #Range: [0.5, 2] (default: 1.0).
                    "vol": float(voice_settings.volume), #Range: (0, 10] (default: 1.0).
                    "pitch": int(voice_settings.pitch), #Range: [-12, 12] (default: 0, original pitch).
                    "text_normalization": True
                },
                "audio_setting": {
                    "sample_rate": int(audio_settings.sample_rate),
                    "bitrate": int(audio_settings.bitrate),
                    "format": audio_settings.format,
                    "channel": int(audio_settings.channel)
                }
            }
            
            # Add optional settings
            if voice_settings.emotion:
                payload["voice_setting"]["emotion"] = voice_settings.emotion
            if voice_settings.english_normalization:
                payload["voice_setting"]["english_normalization"] = voice_settings.english_normalization
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }

            # Log all parameters being sent to Minimax API
            logger.info("=" * 80)
            logger.info("📤 MINIMAX API REQUEST (SYNC)")
            logger.info(f"URL: {self.sync_url}")
            logger.info(f"Headers: {headers}")
            logger.info(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
            logger.info("=" * 80)

            # Use aiohttp for async HTTP request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.sync_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=300)  # 5 minute timeout
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"TTS API error: {response.status} - {error_text}")
                    
                    response_data = await response.json()
            
            # Check for API-level errors in the response
            if 'base_resp' in response_data:
                base_resp = response_data['base_resp']
                if base_resp.get('status_code', 0) != 0:
                    error_msg = base_resp.get('status_msg', 'Unknown API error')
                    error_code = base_resp.get('status_code')
                    raise Exception(f"Sync TTS API error {error_code}: {error_msg}")
            
            # Extract and save audio data
            if 'data' not in response_data or 'audio' not in response_data['data']:
                raise Exception(f"Invalid response format: {response_data}")
            
            audio_hex = response_data['data']['audio']
            audio_bytes = bytes.fromhex(audio_hex)
            
            # Upload to GCS if user_id is provided, otherwise save locally
            gcs_result = None
            if user_id:
                try:
                    from services.gcs_service import get_gcs_service
                    gcs_service = get_gcs_service()
                    
                    # Upload audio bytes directly to GCS
                    gcs_result = await gcs_service.upload_audio_bytes(
                        audio_bytes=audio_bytes,
                        user_id=user_id,
                        file_extension=audio_settings.format,
                        audio_id=audio_file_id,
                        metadata={
                            'text_length': len(text),
                            'voice_id': voice_settings.voice_id,
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
                # Save audio file locally
                async with aiofiles.open(file_path, 'wb') as f:
                    await f.write(audio_bytes)
                logger.info(f"📁 Audio saved locally: {file_path}")
            
            # Initially use estimated duration, will be updated with real duration below
            estimated_duration = len(text.split()) / (150 * voice_settings.speed)  # ~150 WPM average
            
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
                duration=estimated_duration,
                format=audio_settings.format,
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

            # Get real duration from the generated audio file
            real_duration = 0.0
            if not gcs_result:
                # For local files, we can get the real duration immediately
                real_duration = get_audio_duration(str(file_path))
            else:
                # For GCS files, create temporary file from audio_bytes to get duration
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=f".{audio_settings.format}", delete=False) as temp_file:
                    temp_file.write(audio_bytes)
                    temp_path = temp_file.name
                
                try:
                    real_duration = get_audio_duration(temp_path)
                    # Clean up temp file
                    Path(temp_path).unlink()
                except Exception as e:
                    logger.warning(f"⚠️ Could not get duration from temp file: {e}")
                    # Clean up temp file even on error
                    try:
                        Path(temp_path).unlink()
                    except:
                        pass
            
            # Update duration if we got a valid measurement
            if real_duration > 0:
                audio_file.duration = real_duration
                logger.info(f"🎵 Updated duration from estimated {estimated_duration:.3f}s to real {real_duration:.3f}s")
            else:
                logger.warning(f"⚠️ Could not get real duration, keeping estimated: {estimated_duration:.3f}s")
            
            # Save metadata to JSON (with updated duration if available)
            await self._save_audio_metadata(audio_file)
            
            logger.info(f"Successfully generated audio file: {file_path}")
            return audio_file
            
        except Exception as e:
            logger.error(f"Error in synchronous TTS generation: {str(e)}")
            
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
                format=audio_settings.format,
                voice_settings=voice_settings,
                audio_settings=audio_settings,
                status=GenerationStatus.FAILED,
                created_at=datetime.now()
            )
            
            await self._save_audio_metadata(audio_file)
            raise
    
    async def text_to_speech_async(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        processed_story_id: Optional[str] = None,
        user_id: Optional[str] = None,
        audio_speed: Optional[float] = None,
        audio_id: Optional[str] = None
    ) -> AudioFile:
        """
        Convert text to speech using asynchronous API

        Args:
            text: Text to convert to speech
            voice_settings: Voice configuration settings
            audio_settings: Audio quality settings
            processed_story_id: ID of the processed story
            audio_id: Optional audio ID to use (for overwriting existing audio)

        Returns:
            AudioFile object with task information (status will be GENERATING)
        """
        if voice_settings is None:
            voice_settings = VoiceSettings()
        if audio_settings is None:
            audio_settings = AudioSettings()

        # Use provided audio_id or generate new UUID
        audio_file_id = audio_id if audio_id else str(uuid.uuid4())
        file_name = f"audio_{audio_file_id}.{audio_settings.format}"
        file_path = self.audio_dir / file_name

        logger.info(f"🎵 Async TTS using audio_file_id: {audio_file_id} (provided: {bool(audio_id)})")
        
        try:
            logger.info(f"Starting asynchronous TTS generation for text length: {len(text)}")

            # Use audio_speed if provided, otherwise fall back to voice_settings.speed
            speed_value = audio_speed if audio_speed is not None else voice_settings.speed

            payload = {
                "model": "speech-02-turbo",
                "text": text,
                "voice_setting": {
                    "voice_id": voice_settings.voice_id,
                    "speed": float(speed_value),
                    "vol": float(voice_settings.volume),
                    "pitch": int(voice_settings.pitch),
                    "text_normalization": True
                },
                "audio_setting": {
                    "sample_rate": int(audio_settings.sample_rate),
                    "bitrate": int(audio_settings.bitrate),
                    "format": audio_settings.format,
                    "channel": int(audio_settings.channel)
                }
            }
            
            # Add optional settings
            if voice_settings.emotion:
                payload["voice_setting"]["emotion"] = voice_settings.emotion
            if voice_settings.english_normalization:
                payload["voice_setting"]["english_normalization"] = voice_settings.english_normalization
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }

            # Log all parameters being sent to Minimax API
            logger.info("=" * 80)
            logger.info("📤 MINIMAX API REQUEST (ASYNC)")
            logger.info(f"URL: {self.async_url}")
            logger.info(f"Headers: {headers}")
            logger.info(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
            logger.info("=" * 80)

            # Submit async job
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.async_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=3000)  #  50 minute timeout
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"TTS API error: {response.status} - {error_text}")
                    
                    response_data = await response.json()
            
            logger.info(f"Response data: {response_data}")
            
            # Check for API-level errors in the response
            if 'base_resp' in response_data:
                base_resp = response_data['base_resp']
                if base_resp.get('status_code', 0) != 0:
                    error_msg = base_resp.get('status_msg', 'Unknown API error')
                    error_code = base_resp.get('status_code')
                    raise Exception(f"TTS API error {error_code}: {error_msg}")
            
            # Extract task ID
            if 'task_id' not in response_data:
                raise Exception(f"No task_id in response: {response_data}")
            
            task_id = response_data['task_id']
            if task_id == 0:
                raise Exception(f"Invalid task_id (0) in response: {response_data}")
                
            task_id = str(task_id)
            
            # Calculate estimated duration
            estimated_duration = len(text.split()) / (150 * voice_settings.speed)
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
                duration=estimated_duration,
                format=audio_settings.format,
                voice_settings=voice_settings,
                audio_settings=audio_settings,
                status=GenerationStatus.GENERATING,
                task_id=task_id,
                created_at=datetime.now()
            )
            
            # Store user_id for later use during download
            if user_id:
                audio_file.__dict__['user_id'] = user_id
            
            # Save metadata
            await self._save_audio_metadata(audio_file)
            
            logger.info(f"Successfully submitted async TTS job with task_id: {task_id}")
            return audio_file
            
        except Exception as e:
            logger.error(f"Error in asynchronous TTS generation: {str(e)}")
            raise
    
    async def text_to_speech_async_long(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        processed_story_id: Optional[str] = None,
        user_id: Optional[str] = None,
        audio_speed: Optional[float] = None,
        audio_id: Optional[str] = None
    ) -> AudioFile:
        """
        Convert text to speech using asynchronous long TTS API (up to 1M characters)

        Args:
            text: Text to convert to speech (up to 1M characters)
            voice_settings: Voice configuration settings
            audio_settings: Audio quality settings
            processed_story_id: ID of the processed story
            audio_id: Optional audio ID to use (for overwriting existing audio)

        Returns:
            AudioFile object with task information (status will be GENERATING)
        """
        if len(text) > LONG_TTS_MAX_LENGTH:
            raise ValueError(f"Text too long ({len(text)} chars). Maximum length for long TTS is {LONG_TTS_MAX_LENGTH} characters.")

        if voice_settings is None:
            voice_settings = VoiceSettings()
        if audio_settings is None:
            audio_settings = AudioSettings()

        # Use provided audio_id or generate new UUID
        audio_file_id = audio_id if audio_id else str(uuid.uuid4())
        file_name = f"audio_long_{audio_file_id}.{audio_settings.format}"

        logger.info(f"🎵 Long async TTS using audio_file_id: {audio_file_id} (provided: {bool(audio_id)})")
        file_path = self.audio_dir / file_name
        
        try:
            logger.info(f"Starting long asynchronous TTS generation for text length: {len(text)}")

            # Use audio_speed if provided, otherwise fall back to voice_settings.speed
            speed_value = audio_speed if audio_speed is not None else voice_settings.speed

            payload = {
                "model": "speech-02-turbo",
                "text": text,
                "voice_setting": {
                    "voice_id": voice_settings.voice_id,
                    "speed": int(speed_value),
                    "vol": int(voice_settings.volume),
                    "pitch": int(voice_settings.pitch)
                },
                "audio_setting": {
                    "sample_rate": int(audio_settings.sample_rate),
                    "bitrate": int(audio_settings.bitrate),
                    "format": audio_settings.format,
                    "channel": int(audio_settings.channel)
                }
            }
            
            # Add optional settings
            if voice_settings.emotion:
                payload["voice_setting"]["emotion"] = voice_settings.emotion
            if voice_settings.english_normalization:
                payload["voice_setting"]["english_normalization"] = voice_settings.english_normalization
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }

            # Log all parameters being sent to Minimax API
            logger.info("=" * 80)
            logger.info("📤 MINIMAX API REQUEST (LONG ASYNC)")
            logger.info(f"URL: {self.long_async_url}")
            logger.info(f"Headers: {headers}")
            logger.info(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
            logger.info("=" * 80)

            # Submit long async job
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.long_async_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=300)  # 5 minute timeout
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Long TTS API error: {response.status} - {error_text}")
                    
                    response_data = await response.json()
            
            # Check for API-level errors in the response
            if 'base_resp' in response_data:
                base_resp = response_data['base_resp']
                if base_resp.get('status_code', 0) != 0:
                    error_msg = base_resp.get('status_msg', 'Unknown API error')
                    error_code = base_resp.get('status_code')
                    raise Exception(f"Long TTS API error {error_code}: {error_msg}")
            
            # Extract task ID
            if 'task_id' not in response_data:
                raise Exception(f"No task_id in response: {response_data}")
            
            task_id = response_data['task_id']
            if task_id == 0:
                raise Exception(f"Invalid task_id (0) in response: {response_data}")
                
            task_id = str(task_id)
            
            # Calculate estimated duration (for long content, use a more conservative estimate)
            estimated_duration = len(text.split()) / (120 * voice_settings.speed)  # ~120 WPM for long content
            
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
                duration=estimated_duration,
                format=audio_settings.format,
                voice_settings=voice_settings,
                audio_settings=audio_settings,
                status=GenerationStatus.GENERATING,
                task_id=task_id,
                created_at=datetime.now()
            )
            
            # Add metadata to track this as a long TTS job
            audio_file.__dict__['is_long_form'] = True
            
            # Store user_id for later use during download
            if user_id:
                audio_file.__dict__['user_id'] = user_id
            
            # Save metadata
            await self._save_audio_metadata(audio_file)
            
            logger.info(f"Successfully submitted long async TTS job with task_id: {task_id}")
            return audio_file
            
        except Exception as e:
            logger.error(f"Error in long asynchronous TTS generation: {str(e)}")
            raise
    
    async def check_async_status(self, audio_file: AudioFile) -> AudioFile:
        """
        Check the status of an asynchronous TTS generation (supports both regular and long TTS)
        
        Args:
            audio_file: AudioFile object with task_id
        
        Returns:
            Updated AudioFile object
        """
        if not audio_file.task_id:
            raise ValueError("AudioFile must have task_id for status checking")
        
        try:
            # Determine if this is a long TTS job based on filename or metadata
            is_long_form = getattr(audio_file, 'is_long_form', False) or 'audio_long_' in audio_file.file_path
            
            # Use appropriate query endpoint
            if is_long_form:
                url = f"https://api.minimax.io/v1/query/t2a_async_long_query?GroupId={self.group_id}&task_id={audio_file.task_id}"
            else:
                url = f"https://api.minimax.io/v1/query/t2a_async_query_v2?GroupId={self.group_id}&task_id={audio_file.task_id}"
                
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Status check error: {response.status} - {error_text}")
                    
                    response_data = await response.json()
            
            # Check if generation is complete
            if response_data.get('status') == 'Success' and 'file_id' in response_data:
                # Download the completed audio file
                file_id = response_data['file_id']
                await self._download_async_audio(audio_file, file_id)
                audio_file.status = GenerationStatus.COMPLETED
                
            elif response_data.get('status') == 'Failed':
                audio_file.status = GenerationStatus.FAILED
                logger.error(f"Async TTS generation failed for task {audio_file.task_id}")
            
            # Save updated metadata
            await self._save_audio_metadata(audio_file)
            
            return audio_file
            
        except Exception as e:
            logger.error(f"Error checking async status: {str(e)}")
            audio_file.status = GenerationStatus.FAILED
            await self._save_audio_metadata(audio_file)
            raise
    
    async def _download_async_audio(self, audio_file: AudioFile, file_id: str):
        """Download completed audio file from async generation and optionally upload to GCS"""
        try:
            # Get download URL
            url = f'https://api.minimax.io/v1/files/retrieve?GroupId={self.group_id}&file_id={file_id}'
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                # Get download URL
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        raise Exception(f"Error getting download URL: {response.status}")
                    
                    url_response = await response.json()
                    download_url = url_response['file']['download_url']
                
                # Download the actual audio file
                async with session.get(download_url) as response:
                    if response.status != 200:
                        raise Exception(f"Error downloading audio: {response.status}")
                    
                    audio_data = await response.read()
                
                # Check if user_id is available for GCS upload
                user_id = getattr(audio_file, 'user_id', None) or audio_file.__dict__.get('user_id')
                gcs_result = None
                
                if user_id:
                    try:
                        from services.gcs_service import get_gcs_service
                        gcs_service = get_gcs_service()
                        
                        # Upload audio bytes directly to GCS
                        gcs_result = await gcs_service.upload_audio_bytes(
                            audio_bytes=audio_data,
                            user_id=user_id,
                            file_extension=audio_file.format,
                            audio_id=audio_file.id,
                            metadata={
                                'task_id': audio_file.task_id,
                                'processed_story_id': str(audio_file.processed_story_id) if audio_file.processed_story_id else None,
                                'is_async_download': True
                            }
                        )
                        
                        if gcs_result:
                            logger.info(f"✅ Async audio uploaded to GCS: {gcs_result['gcs_path']}")
                            
                            # Store old path for video job updates
                            old_file_path = audio_file.file_path
                            new_file_path = gcs_result['signed_url']
                            
                            # Update audio_file with GCS information
                            audio_file.url = gcs_result['signed_url']
                            audio_file.gcs_path = gcs_result['gcs_path']
                            audio_file.public_url = gcs_result['public_url']
                            # Update file_path to use GCS signed URL
                            audio_file.file_path = new_file_path
                            
                            # DEBUG: Log all URL fields for debugging
                            logger.info(f"🔗 ASYNC TTS - AudioFile URL fields after GCS upload:")
                            logger.info(f"   audio_file.url: {audio_file.url}")
                            logger.info(f"   audio_file.file_path: {audio_file.file_path}")
                            logger.info(f"   audio_file.gcs_path: {audio_file.gcs_path}")
                            logger.info(f"   audio_file.public_url: {audio_file.public_url}")
                            
                            # Update any existing video processing jobs that reference the old path
                            await self._update_video_jobs_with_new_audio_path(
                                audio_file_id=str(audio_file.id), 
                                old_path=old_file_path, 
                                new_path=new_file_path
                            )
                        else:
                            logger.warning("⚠️ GCS upload failed, falling back to local storage")
                            raise Exception("GCS upload failed")
                            
                    except Exception as gcs_error:
                        logger.warning(f"⚠️ GCS upload failed ({str(gcs_error)}), falling back to local storage")
                        gcs_result = None
                
                # Fallback to local storage if no user_id or GCS failed
                if not gcs_result:
                    # Save to local file
                    async with aiofiles.open(audio_file.file_path, 'wb') as f:
                        await f.write(audio_data)
                    logger.info(f"📁 Async audio saved locally: {audio_file.file_path}")
                
                # Get real duration from the downloaded audio file
                # For local files, get duration directly. For GCS files, save temporarily to get duration.
                real_duration = 0.0
                if not gcs_result:
                    # Local file - get duration directly
                    real_duration = get_audio_duration(str(audio_file.file_path))
                else:
                    # GCS file - create temporary file to get duration
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix=f".{audio_file.format}", delete=False) as temp_file:
                        temp_file.write(audio_data)
                        temp_path = temp_file.name
                    
                    try:
                        real_duration = get_audio_duration(temp_path)
                        # Clean up temp file
                        Path(temp_path).unlink()
                    except Exception as e:
                        logger.warning(f"⚠️ Could not get duration from temp file: {e}")
                        # Clean up temp file even on error
                        try:
                            Path(temp_path).unlink()
                        except:
                            pass
                
                # Update duration if we got a valid measurement
                if real_duration > 0:
                    old_duration = audio_file.duration
                    audio_file.duration = real_duration
                    logger.info(f"🎵 Updated async audio duration from estimated {old_duration:.3f}s to real {real_duration:.3f}s")
                else:
                    logger.warning(f"⚠️ Could not get real duration for async audio, keeping estimated: {audio_file.duration:.3f}s")
                
        except Exception as e:
            logger.error(f"Error downloading async audio: {str(e)}")
            raise
    
    async def _update_video_jobs_with_new_audio_path(self, audio_file_id: str, old_path: str, new_path: str):
        """Update any video processing jobs that reference the old audio file path"""
        try:
            # Import here to avoid circular imports
            from services.video_processing_service import get_video_service
            video_service = get_video_service()
            
            # Find and update any active jobs that reference this audio file
            updated_jobs = await video_service.update_audio_file_path_in_jobs(
                audio_file_id=audio_file_id,
                old_path=old_path, 
                new_path=new_path
            )
            
            if updated_jobs > 0:
                logger.info(f"✅ Updated {updated_jobs} video processing jobs with new audio path")
                logger.info(f"   Old path: {old_path}")
                logger.info(f"   New path: {new_path}")
            else:
                logger.debug(f"🔍 No video processing jobs found referencing audio file {audio_file_id}")
                
        except ImportError:
            logger.warning("⚠️ Could not import video service to update jobs - video processing may use old paths")
        except Exception as e:
            logger.warning(f"⚠️ Failed to update video jobs with new audio path: {str(e)}")
    
    async def _save_audio_metadata(self, audio_file: AudioFile):
        """Save audio file metadata to JSON"""
        try:
            metadata_file = self.audio_dir / f"metadata_{audio_file.id}.json"
            
            # Convert to dict for JSON serialization
            metadata = audio_file.model_dump()
            
            # Add is_long_form field if it exists in the object
            if hasattr(audio_file, 'is_long_form') or 'is_long_form' in audio_file.__dict__:
                metadata['is_long_form'] = getattr(audio_file, 'is_long_form', False)
            
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
            metadata_file = self.audio_dir / f"metadata_{audio_id}.json"
            
            if not metadata_file.exists():
                return None
            
            async with aiofiles.open(metadata_file, 'r') as f:
                content = await f.read()
                metadata = json.loads(content)
            
            # Convert datetime back
            metadata['created_at'] = datetime.fromisoformat(metadata['created_at'])
            
            # Extract special fields that aren't part of AudioFile model
            is_long_form = metadata.pop('is_long_form', False)
            user_id = metadata.pop('user_id', None)
            
            audio_file = AudioFile(**metadata)
            
            # Add the special attributes back
            if is_long_form:
                audio_file.__dict__['is_long_form'] = is_long_form
            if user_id:
                audio_file.__dict__['user_id'] = user_id
            
            return audio_file
            
        except Exception as e:
            logger.error(f"Error loading audio metadata: {str(e)}")
            return None
    
    async def get_audio_preview_info(self, audio_file: AudioFile) -> Dict[str, Any]:
        """Get audio file information for preview"""
        file_path = Path(audio_file.file_path)

        return {
            "id": audio_file.id,
            "file_exists": file_path.exists(),
            "file_size": file_path.stat().st_size if file_path.exists() else 0,
            "duration": audio_file.duration,
            "format": audio_file.format,
            "voice_settings": audio_file.voice_settings.model_dump(),
            "status": audio_file.status,
            "created_at": audio_file.created_at.isoformat()
        }

    async def adjust_audio_speed(self, input_file: str, target_duration: float, output_file: str = None) -> str:
        """
        Adjust audio speed to match a target duration using ffmpeg.

        Args:
            input_file: Path to input audio file
            target_duration: Desired duration in seconds
            output_file: Path for output file (optional, will generate if not provided)

        Returns:
            Path to the speed-adjusted audio file

        Raises:
            Exception: If speed adjustment fails or parameters are invalid
        """
        if not os.path.exists(input_file):
            raise Exception(f"Input file does not exist: {input_file}")

        if target_duration <= 0:
            raise Exception(f"Target duration must be positive: {target_duration}")

        # Get current duration
        current_duration = get_audio_duration(input_file)

        if current_duration <= 0:
            raise Exception(f"Invalid current duration: {current_duration}")

        # Calculate speed factor
        speed_factor = current_duration / target_duration

        # Validate speed factor (ffmpeg atempo filter has limits)
        if speed_factor < 0.25 or speed_factor > 4.0:
            raise Exception(
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
            import subprocess

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
                raise Exception(f"ffmpeg speed adjustment failed: {result.stderr}")

            # Verify the output duration
            output_duration = get_audio_duration(output_file)
            duration_diff = abs(output_duration - target_duration)

            logger.info(f"Speed adjustment completed:")
            logger.info(f"  Output duration: {output_duration:.2f}s")
            logger.info(f"  Target duration: {target_duration:.2f}s")
            logger.info(f"  Difference: {duration_diff:.2f}s")

            if duration_diff > 0.1:  # Allow 0.1s tolerance
                logger.warning(f"Output duration differs from target by {duration_diff:.2f}s")

            return output_file

        except subprocess.CalledProcessError as e:
            raise Exception(f"Speed adjustment failed: {str(e)}")

    async def adjust_audio_file_duration(self, audio_file: AudioFile, target_duration: float) -> AudioFile:
        """
        Adjust an existing AudioFile to match a target duration.

        Args:
            audio_file: The AudioFile to adjust
            target_duration: Desired duration in seconds

        Returns:
            New AudioFile with adjusted duration
        """
        import tempfile
        import aiohttp

        # Check if file is on GCS (URL) or local
        is_gcs_file = audio_file.file_path and (
            audio_file.file_path.startswith('http://') or
            audio_file.file_path.startswith('https://')
        )

        temp_input_file = None
        temp_output_file = None
        adjusted_file_path = None

        try:
            if is_gcs_file:
                # Download from GCS to temporary file
                logger.info(f"📥 Downloading audio from GCS for duration adjustment: {audio_file.file_path[:100]}...")
                temp_input_file = tempfile.NamedTemporaryFile(suffix=f".{audio_file.format}", delete=False)

                async with aiohttp.ClientSession() as session:
                    async with session.get(audio_file.file_path) as response:
                        if response.status != 200:
                            raise Exception(f"Failed to download audio from GCS: {response.status}")
                        audio_data = await response.read()
                        temp_input_file.write(audio_data)
                        temp_input_file.flush()

                input_file_path = temp_input_file.name
                logger.info(f"✅ Downloaded to temporary file: {input_file_path}")
            else:
                # Local file
                if not audio_file.file_path or not os.path.exists(audio_file.file_path):
                    raise Exception("Audio file path does not exist")
                input_file_path = audio_file.file_path

            # Create temporary output file
            temp_output_file = tempfile.NamedTemporaryFile(suffix=f"_duration_{target_duration}s.{audio_file.format}", delete=False)
            output_file_path = temp_output_file.name
            temp_output_file.close()

            # Adjust the audio speed
            logger.info(f"🔧 Adjusting audio speed from {audio_file.duration:.2f}s to {target_duration:.2f}s")
            adjusted_file_path = await self.adjust_audio_speed(
                input_file=input_file_path,
                target_duration=target_duration,
                output_file=output_file_path
            )

            # If original was on GCS, upload adjusted file back to GCS
            adjusted_audio_file_id = str(uuid.uuid4())

            if is_gcs_file:
                # Get user_id from the audio_file
                user_id = getattr(audio_file, 'user_id', None) or audio_file.__dict__.get('user_id')

                if user_id:
                    # Upload adjusted audio to GCS
                    logger.info(f"📤 Uploading adjusted audio to GCS...")
                    from services.gcs_service import get_gcs_service
                    gcs_service = get_gcs_service()

                    # Read adjusted audio file
                    with open(adjusted_file_path, 'rb') as f:
                        adjusted_audio_bytes = f.read()

                    gcs_result = await gcs_service.upload_audio_bytes(
                        audio_bytes=adjusted_audio_bytes,
                        user_id=user_id,
                        file_extension=audio_file.format,
                        audio_id=adjusted_audio_file_id,
                        metadata={
                            'original_audio_id': str(audio_file.id),
                            'target_duration': target_duration,
                            'is_duration_adjusted': True
                        }
                    )

                    if gcs_result:
                        logger.info(f"✅ Adjusted audio uploaded to GCS: {gcs_result['gcs_path']}")

                        # Create AudioFile with GCS information
                        adjusted_audio_file = AudioFile(
                            id=adjusted_audio_file_id,
                            file_path=gcs_result['signed_url'],
                            duration=target_duration,
                            format=audio_file.format,
                            voice_settings=audio_file.voice_settings,
                            audio_settings=audio_file.audio_settings,
                            status=GenerationStatus.COMPLETED,
                            created_at=datetime.now(),
                            url=gcs_result['signed_url'],
                            gcs_path=gcs_result['gcs_path'],
                            public_url=gcs_result['public_url']
                        )

                        # Store user_id for future use
                        adjusted_audio_file.__dict__['user_id'] = user_id
                    else:
                        raise Exception("Failed to upload adjusted audio to GCS")
                else:
                    raise Exception("User ID not found for GCS upload")
            else:
                # Local file - keep it local
                adjusted_audio_file = AudioFile(
                    id=adjusted_audio_file_id,
                    file_path=adjusted_file_path,
                    duration=target_duration,
                    format=audio_file.format,
                    voice_settings=audio_file.voice_settings,
                    audio_settings=audio_file.audio_settings,
                    status=GenerationStatus.COMPLETED,
                    created_at=datetime.now(),
                    url=None,
                    gcs_path=None
                )

        finally:
            # Clean up temporary files
            if temp_input_file:
                try:
                    os.unlink(temp_input_file.name)
                    logger.debug(f"🧹 Cleaned up temporary input file: {temp_input_file.name}")
                except:
                    pass

            # For GCS files, also clean up the adjusted local file after upload
            if is_gcs_file and adjusted_file_path and os.path.exists(adjusted_file_path):
                try:
                    os.unlink(adjusted_file_path)
                    logger.debug(f"🧹 Cleaned up temporary adjusted file: {adjusted_file_path}")
                except:
                    pass

        # Save the new audio file metadata
        await self._save_audio_metadata(adjusted_audio_file)

        logger.info(f"Audio file adjusted from {audio_file.duration:.2f}s to {target_duration:.2f}s")

        return adjusted_audio_file