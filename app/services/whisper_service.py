import os
import uuid
import math
import asyncio
import aiofiles
import ffmpeg
from datetime import datetime
from typing import List, Optional, Tuple
from pathlib import Path
import logging
import json
from concurrent.futures import ThreadPoolExecutor

from faster_whisper import WhisperModel
from models.story_models import (
    WordSegment, Caption, CaptionSettings, TranscriptionResult, 
    AudioFile, GenerationStatus
)
from services.caption_service import CaptionService

logger = logging.getLogger(__name__)

class WhisperService:
    def __init__(
        self,
        model_size: str = None,
        device: str = None,
        compute_type: str = None,
    ):
        """
        Initialize Whisper service with faster-whisper
        
        Args:
            model_size: Whisper model size ("tiny", "base", "small", "medium", "large-v3")
            device: Device to run on ("cpu", "cuda")
            compute_type: Compute type ("int8", "float16", "float32")
        """
        import os
        self.model_size = model_size or os.getenv("FASTER_WHISPER_MODEL", "large-v3")
        self.device = device or os.getenv("FASTER_WHISPER_DEVICE", "cpu")
        default_compute = "float16" if self.device == "cuda" else "int8"
        self.compute_type = compute_type or os.getenv("FASTER_WHISPER_COMPUTE", default_compute)
        self.model = None
        
        # Create directories for file storage
        self.captions_dir = Path("data/captions")
        self.captions_dir.mkdir(parents=True, exist_ok=True)
        
        self.temp_dir = Path("data/temp")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Thread pool for CPU-intensive operations
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        # Caption service for generating different subtitle styles
        self.caption_service = CaptionService()
    
    def _load_model(self):
        """Load the Whisper model (lazy loading)"""
        if self.model is None:
            logger.info(f"Loading Whisper model: {self.model_size}")
            self.model = WhisperModel(
                self.model_size, 
                device=self.device, 
                compute_type=self.compute_type
            )
            logger.info("Whisper model loaded successfully")
    
    async def transcribe_audio_file(self, audio_file_path: str) -> TranscriptionResult:
        """
        Transcribe audio file using local Whisper
        
        Args:
            audio_file_path: Path to the audio file
        
        Returns:
            TranscriptionResult with segments and word-level timestamps
        """
        try:
            logger.info(f"Starting Whisper transcription for: {audio_file_path}")
            
            # Ensure model is loaded
            self._load_model()
            
            # Run transcription in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor, 
                self._transcribe_sync, 
                audio_file_path
            )
            
            logger.info(f"Whisper transcription completed. Language: {result.language}")
            return result
            
        except Exception as e:
            logger.error(f"Error in Whisper transcription: {str(e)}")
            raise
    
    def _transcribe_sync(self, audio_file_path: str) -> TranscriptionResult:
        """Synchronous transcription method (runs in thread pool)"""
        # Enable word timestamps
        segments, info = self.model.transcribe(audio_file_path, word_timestamps=True)
        
        language = info.language
        language_probability = getattr(info, 'language_probability', None)
        
        # Log detected language with confidence
        if language_probability:
            logger.info(f"Detected language: {language} (confidence: {language_probability:.3f})")
        else:
            logger.info(f"Detected language: {language}")
        
        segments = list(segments)
        
        # Extract word-level timestamps
        word_segments = []
        caption_segments = []
        
        for segment in segments:
            # Create caption segment
            caption = Caption(
                id=uuid.uuid4(),
                audio_file_id=None,  # Will be set by caller if needed
                text=segment.text.strip(),
                start_time=segment.start,
                end_time=segment.end,
                confidence=getattr(segment, 'avg_logprob', None)
            )
            caption_segments.append(caption)
            
            # Extract word segments
            if hasattr(segment, 'words') and segment.words:
                for word in segment.words:
                    word_segment = WordSegment(
                        word=word.word.strip(),
                        start=word.start,
                        end=word.end,
                        confidence=getattr(word, 'probability', None)
                    )
                    word_segments.append(word_segment)
        
        # Calculate total duration
        duration = segments[-1].end if segments else 0.0
        
        return TranscriptionResult(
            language=language,
            segments=caption_segments,
            word_segments=word_segments,
            duration=duration,
            confidence=info.language_probability if hasattr(info, 'language_probability') else None
        )
    
    async def transcribe_from_audio_file(self, audio_file: AudioFile) -> TranscriptionResult:
        """
        Transcribe from AudioFile object
        
        Args:
            audio_file: AudioFile object with file path
        
        Returns:
            TranscriptionResult with audio_file_id set
        """
        result = await self.transcribe_audio_file(audio_file.file_path)
        
        # Set audio_file_id for all segments
        for segment in result.segments:
            segment.audio_file_id = audio_file.id if audio_file.id else None
        
        # Save transcription metadata
        await self._save_transcription_metadata(str(audio_file.id), result)
        
        return result
    
    async def extract_audio_from_video(self, video_file_path: str) -> str:
        """
        Extract audio from video file for transcription
        
        Args:
            video_file_path: Path to the video file
        
        Returns:
            Path to extracted audio file
        """
        try:
            video_path = Path(video_file_path)
            audio_file_name = f"extracted_audio_{uuid.uuid4().hex}.wav"
            audio_file_path = self.temp_dir / audio_file_name
            
            logger.info(f"Extracting audio from video: {video_file_path}")
            
            # Use ffmpeg to extract audio
            stream = ffmpeg.input(str(video_path))
            stream = ffmpeg.output(stream.audio, str(audio_file_path))
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self.executor,
                lambda: ffmpeg.run(stream, overwrite_output=True, quiet=True)
            )
            
            logger.info(f"Audio extracted to: {audio_file_path}")
            return str(audio_file_path)
            
        except Exception as e:
            logger.error(f"Error extracting audio from video: {str(e)}")
            raise
    
    async def generate_animated_captions(
        self, 
        word_segments: List[WordSegment], 
        language: str,
        settings: Optional[CaptionSettings] = None
    ) -> str:
        """
        Generate animated ASS subtitle file from word segments using the new caption service
        
        Args:
            word_segments: List of word segments with timing
            language: Language code for the subtitles
            settings: Caption styling settings
        
        Returns:
            Path to generated ASS subtitle file
        """
        if settings is None:
            settings = CaptionSettings()
        
        try:
            # Create output path
            subtitle_file_name = f"animated_captions_{uuid.uuid4().hex}"
            subtitle_file_path = str(self.captions_dir / subtitle_file_name)
            
            logger.info(f"Generating animated captions with {len(word_segments)} words using {settings.subtitle_style.value} style")
            
            # Use the caption service to generate the subtitle file
            result_path = self.caption_service.generate_animated_subtitle_file(
                word_segments=word_segments,
                settings=settings,
                output_path=subtitle_file_path,
                language=language
            )
            
            logger.info(f"Generated animated captions: {result_path}")
            return result_path
            
        except Exception as e:
            logger.error(f"Error generating animated captions: {str(e)}")
            raise
    
    async def generate_srt_captions(
        self, 
        segments: List[Caption], 
        language: str
    ) -> str:
        """
        Generate SRT subtitle file from caption segments
        
        Args:
            segments: List of caption segments
            language: Language code for the subtitles
        
        Returns:
            Path to generated SRT subtitle file
        """
        try:
            subtitle_file_name = f"captions_{uuid.uuid4().hex}.{language}.srt"
            subtitle_file_path = self.captions_dir / subtitle_file_name
            
            logger.info(f"Generating SRT captions with {len(segments)} segments")
            
            srt_content = ""
            for index, segment in enumerate(segments):
                start_time = self._format_srt_time(segment.start_time)
                end_time = self._format_srt_time(segment.end_time)
                
                srt_content += f"{index + 1}\n"
                srt_content += f"{start_time} --> {end_time}\n"
                srt_content += f"{segment.text}\n\n"
            
            async with aiofiles.open(subtitle_file_path, 'w', encoding='utf-8') as f:
                await f.write(srt_content)
            
            logger.info(f"Generated SRT captions: {subtitle_file_path}")
            return str(subtitle_file_path)
            
        except Exception as e:
            logger.error(f"Error generating SRT captions: {str(e)}")
            raise
    
    def _format_ass_time(self, seconds: float) -> str:
        """Format time for ASS subtitle format (H:MM:SS.CC)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:05.2f}"
    
    def _format_srt_time(self, seconds: float) -> str:
        """Format time for SRT subtitle format"""
        hours = math.floor(seconds / 3600)
        seconds %= 3600
        minutes = math.floor(seconds / 60)
        seconds %= 60
        milliseconds = round((seconds - math.floor(seconds)) * 1000)
        seconds = math.floor(seconds)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    
    async def _save_transcription_metadata(self, audio_file_id: str, result: TranscriptionResult):
        """Save transcription metadata to JSON file"""
        try:
            metadata_file = self.captions_dir / f"transcription_{audio_file_id}.json"
            
            # Convert to dict for JSON serialization
            metadata = {
                "audio_file_id": audio_file_id,
                "language": result.language,
                "duration": result.duration,
                "confidence": result.confidence,
                "segments_count": len(result.segments),
                "words_count": len(result.word_segments),
                "created_at": datetime.now().isoformat()
            }
            
            async with aiofiles.open(metadata_file, 'w') as f:
                await f.write(json.dumps(metadata, indent=2))
            
            logger.info(f"Saved transcription metadata: {metadata_file}")
            
        except Exception as e:
            logger.error(f"Error saving transcription metadata: {str(e)}")
    
    async def load_transcription_metadata(self, audio_file_id: str) -> Optional[dict]:
        """Load transcription metadata from JSON file"""
        try:
            metadata_file = self.captions_dir / f"transcription_{audio_file_id}.json"
            
            if not metadata_file.exists():
                return None
            
            async with aiofiles.open(metadata_file, 'r') as f:
                content = await f.read()
                metadata = json.loads(content)
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error loading transcription metadata: {str(e)}")
            return None
    
    async def cleanup_temp_files(self):
        """Clean up temporary audio files"""
        try:
            for temp_file in self.temp_dir.glob("extracted_audio_*.wav"):
                if temp_file.exists():
                    temp_file.unlink()
                    logger.info(f"Cleaned up temp file: {temp_file}")
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {str(e)}")
    
    def __del__(self):
        """Cleanup when service is destroyed"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)