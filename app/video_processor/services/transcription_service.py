"""
Transcription services for Cloud Video Processor

This module provides multiple transcription services including Deepgram API,
cloud Whisper service, and compatibility with existing CaptionSettings.
"""

import asyncio
import codecs
import json
import os
import re
import tempfile
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse


import aiofiles
import aiohttp
import structlog
from google.api_core import exceptions as gcs_exceptions
from google import genai


from video_processor.config.settings import get_settings
from video_processor.services.gcs_service import get_gcs_service, GCSError, ensure_valid_signed_url

logger = structlog.get_logger(__name__)

from dotenv import load_dotenv
load_dotenv()
# Configuration
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')

class TranscriptionError(Exception):
    """Base exception for transcription operations"""
    pass


class TranscriptionServiceError(TranscriptionError):
    """Exception raised when transcription service fails"""
    pass


class TranscriptionResult:
    """Result of transcription operation"""
    
    def __init__(
        self,
        transcript: str,
        srt_content: str,
        ass_content: Optional[str] = None,
        cost: Optional[float] = None,
        processing_time: Optional[float] = None,
        service_name: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.transcript = transcript
        self.srt_content = srt_content
        self.ass_content = ass_content
        self.cost = cost
        self.processing_time = processing_time
        self.service_name = service_name
        self.metadata = metadata or {}
        self.created_at = datetime.now(timezone.utc)


class BaseTranscriptionService(ABC):
    """Base class for all transcription services"""
    
    def __init__(self):
        self.settings = get_settings()
        self.gcs_service = get_gcs_service()
    
    @abstractmethod
    async def transcribe_audio(
        self,
        audio_url: str,
        config: Optional[Dict[str, Any]] = None
    ) -> TranscriptionResult:
        """
        Transcribe audio from URL or GCS path
        
        Args:
            audio_url: URL or GCS path to audio file
            config: Service-specific configuration
            
        Returns:
            TranscriptionResult with transcript and subtitle files
            
        Raises:
            TranscriptionServiceError: If transcription fails
        """
        pass
    
    @abstractmethod
    def get_service_name(self) -> str:
        """Get the name of this transcription service"""
        pass
    
    @abstractmethod
    def estimate_cost(self, duration_seconds: float) -> float:
        """
        Estimate transcription cost for given duration
        
        Args:
            duration_seconds: Audio duration in seconds
            
        Returns:
            Estimated cost in USD
        """
        pass
    
    async def _download_audio_file(self, audio_url: str) -> str:
        """
        Download audio file to temporary location
        
        Args:
            audio_url: URL or GCS path to audio file
            
        Returns:
            Path to downloaded file
            
        Raises:
            TranscriptionError: If download fails
        """
        try:
            # Create temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix='.audio')
            os.close(temp_fd)

            local_info = await self.gcs_service.get_file_info(audio_url)
            if local_info.get("exists"):
                await self.gcs_service.download_file(audio_url, temp_path)
                logger.info("Audio file resolved from local media storage", audio_url=audio_url, temp_path=temp_path)
                return temp_path
            
            if audio_url.startswith(('gs://', 'https://storage.googleapis.com/')):
                raise TranscriptionError(
                    "External Google Cloud Storage audio URLs are not supported in local mode"
                )
            elif audio_url.startswith(('http://', 'https://')):
                # Download from HTTP URL
                async with aiohttp.ClientSession() as session:
                    async with session.get(audio_url) as response:
                        if response.status != 200:
                            raise TranscriptionError(f"Failed to download audio: HTTP {response.status}")
                        
                        async with aiofiles.open(temp_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                await f.write(chunk)
            elif audio_url.startswith('file://'):
                # Handle local file URLs
                local_path = audio_url.replace('file://', '')
                
                # If path is not absolute, make it relative to current working directory
                if not os.path.isabs(local_path):
                    local_path = os.path.join(os.getcwd(), local_path)
                
                # Also try relative to project root if not found
                if not os.path.exists(local_path):
                    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    alt_path = os.path.join(project_root, local_path.lstrip('/'))
                    if os.path.exists(alt_path):
                        local_path = alt_path
                    else:
                        raise TranscriptionError(f"Local file not found: {local_path} (also tried: {alt_path})")
                
                # Copy local file to temp location
                import shutil
                shutil.copy2(local_path, temp_path)
                logger.info("Local file copied", source_path=local_path, temp_path=temp_path)
            else:
                raise TranscriptionError(f"Unsupported audio URL format: {audio_url}")
            
            logger.info("Audio file downloaded", audio_url=audio_url, temp_path=temp_path)
            return temp_path
            
        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            logger.error("Failed to download audio file", audio_url=audio_url, error=str(e))
            raise TranscriptionError(f"Failed to download audio file: {e}")
    
    def _generate_srt_content(self, segments: List[Dict[str, Any]]) -> str:
        """
        Generate SRT subtitle content from transcript segments
        
        Args:
            segments: List of transcript segments with timing
            
        Returns:
            SRT formatted subtitle content
        """
        srt_lines = []
        
        for i, segment in enumerate(segments, 1):
            start_time = self._format_srt_timestamp(segment.get('start', 0))
            end_time = self._format_srt_timestamp(segment.get('end', 0))
            text = segment.get('text', '').strip()

            if text:
                srt_lines.extend([
                    str(i),
                    f"{start_time} --> {end_time}",
                    text,
                    ""
                ])
        
        return "\n".join(srt_lines)
    
    def _generate_ass_content(self, segments: List[Dict[str, Any]], style_config: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate ASS subtitle content from transcript segments
        
        Args:
            segments: List of transcript segments with timing
            style_config: ASS styling configuration
            
        Returns:
            ASS formatted subtitle content
        """
        # Default ASS style configuration
        default_style = {
            'font_name': 'Arial',
            'font_size': 20,
            'primary_color': '&H00FFFFFF',
            'secondary_color': '&H00FFFFFF',
            'outline_color': '&H00FFFFFF',
            'back_color': '&H00000000',
            'bold': 0,
            'italic': 0,
            'underline': 0,
            'strike_out': 0,
            'scale_x': 100,
            'scale_y': 100,
            'spacing': 0,
            'angle': 0,
            'border_style': 1,
            'outline': 2,
            'shadow': 0,
            'alignment': 2,
            'margin_l': 10,
            'margin_r': 10,
            'margin_v': 10,
            'encoding': 1
        }
        
        if style_config:
            default_style.update(style_config)
        
        # ASS header
        ass_content = [
            "[Script Info]",
            "Title: Generated Subtitles",
            "ScriptType: v4.00+",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Default,{default_style['font_name']},{default_style['font_size']},{default_style['primary_color']},{default_style['secondary_color']},{default_style['outline_color']},{default_style['back_color']},{default_style['bold']},{default_style['italic']},{default_style['underline']},{default_style['strike_out']},{default_style['scale_x']},{default_style['scale_y']},{default_style['spacing']},{default_style['angle']},{default_style['border_style']},{default_style['outline']},{default_style['shadow']},{default_style['alignment']},{default_style['margin_l']},{default_style['margin_r']},{default_style['margin_v']},{default_style['encoding']}",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
        ]
        
        # Add dialogue lines
        for segment in segments:
            start_time = self._format_ass_timestamp(segment.get('start', 0))
            end_time = self._format_ass_timestamp(segment.get('end', 0))
            text = segment.get('text', '').strip()

            if text:
                ass_content.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}")
        
        return "\n".join(ass_content)
    
    def _format_srt_timestamp(self, seconds: float) -> str:
        """Format timestamp for SRT format (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
    
    def _format_ass_timestamp(self, seconds: float) -> str:
        """Format timestamp for ASS format (H:MM:SS.cc)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centiseconds = int(round((seconds % 1) * 100))
        
        return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


class DeepgramTranscriptionService(BaseTranscriptionService):
    """Deepgram API transcription service"""
    
    def __init__(self):
        super().__init__()
        self.api_key = self.settings.deepgram_api_key
        self.base_url = "https://api.deepgram.com/v1/listen"
        
        if not self.api_key:
            logger.warning("Deepgram API key not configured")
        
        
    
    def get_service_name(self) -> str:
        return "deepgram"
    
    def estimate_cost(self, duration_seconds: float) -> float:
        """
        Estimate Deepgram transcription cost
        
        Deepgram pricing (as of 2024):
        - Nova-2: $0.0043 per minute
        - Base: $0.0025 per minute
        """
        minutes = duration_seconds / 60
        # Using Nova-2 pricing as default
        cost_per_minute = 0.0043
        return minutes * cost_per_minute
    
    async def transcribe_audio(
        self,
        audio_url: str,
        config: Optional[Dict[str, Any]] = None
    ) -> TranscriptionResult:
        """
        Transcribe audio using Deepgram API
        
        Args:
            audio_url: URL or GCS path to audio file
            config: Deepgram-specific configuration
            
        Returns:
            TranscriptionResult with transcript and subtitle files
        """
        if not self.api_key:
            raise TranscriptionServiceError("Deepgram API key not configured")
        
        start_time = time.time()
        
        try:
            # Default Deepgram configuration optimized for timing accuracy
            deepgram_config = {
                'model': 'nova-2',  # Nova-2 has better timing accuracy than Nova-3
                'language': 'en',
                'punctuate': True,
                'diarize': False,
                'timestamps': True,
                'paragraphs': True,
                'utterances': True,
                'smart_format': True,  # Better formatting and timing
                'profanity_filter': False,  # Avoid timing shifts from censoring
                'redact': False,  # Avoid timing shifts from redaction
                'alternatives': 1,  # Focus on single best result for consistent timing
                'numerals': True,  # Better handling of numbers
                'search': [],  # No search terms that could affect timing
                'keywords': [],  # No keyword boosting that could affect timing
                'tag': [],  # No tags
                'multichannel': False,  # Single channel for consistent timing
                'interim_results': False,  # Only final results for stable timing
                'endpointing': 300,  # Milliseconds of silence before endpoint (affects timing)
                'vad_turnoff': 300,  # Voice activity detection turnoff time
                'encoding': 'linear16',  # Ensure consistent audio encoding
                'sample_rate': 16000,  # Standard sample rate for best accuracy
                'channels': 1  # Mono audio for consistent timing
            }
            
            # Filter config to only include Deepgram-specific parameters
            if config:
                # Only allow valid Deepgram parameters
                valid_deepgram_params = {
                    'model', 'language', 'punctuate', 'diarize', 'timestamps',
                    'paragraphs', 'utterances', 'smart_format', 'profanity_filter',
                    'redact', 'alternatives', 'numerals', 'search', 'keywords',
                    'tag', 'multichannel', 'interim_results', 'endpointing',
                    'vad_turnoff', 'encoding', 'sample_rate', 'channels'
                }
                
                filtered_config = {k: v for k, v in config.items() if k in valid_deepgram_params}
                deepgram_config.update(filtered_config)
            
            logger.info('starting deepgram api call')
            logger.info(
                "Starting Deepgram transcription",
                audio_url=audio_url,
                config=deepgram_config
            )
            
            # # Download audio file
            # temp_audio_path = await self._download_audio_file(audio_url)
            
            try:
                # Prepare API request
                headers = {
                    'Authorization': f'Token {self.api_key}',
                    'Content-Type': 'audio/*'
                }
                
                # Build query parameters - convert boolean values to strings for Deepgram API
                params = {
                    'model': deepgram_config['model'],
                    'language': deepgram_config['language'],
                    'punctuate': str(deepgram_config['punctuate']).lower(),
                    'diarize': str(deepgram_config['diarize']).lower(),
                    'timestamps': str(deepgram_config['timestamps']).lower(),
                    'paragraphs': str(deepgram_config['paragraphs']).lower(),
                    'utterances': str(deepgram_config['utterances']).lower(),
                    'smart_format': str(deepgram_config['smart_format']).lower(),
                    'numerals': str(deepgram_config['numerals']).lower(),
                    #'multichannel': str(deepgram_config['multichannel']).lower(),
                    'encoding': deepgram_config['encoding'],
                }
                
                # Make API request
                api_start_time = time.time()
                async with aiohttp.ClientSession() as session:
                    if audio_url.startswith("https://"): #remote file
                        logger.info('Deepgram APi gets remote file')
                        logger.info(self.base_url)
                        logger.info(headers)
                        logger.info(params)
                        logger.info(audio_url)
                        async with session.post(
                            self.base_url,
                            headers = {**headers, "Content-Type": "application/json"},
                            params=params,
                            json={"url": audio_url},
                            timeout = aiohttp.ClientTimeout(total=300)
                        ) as response:
                            logger.info(response)
                            if response.status != 200:
                                error_text = await response.text()
                                raise TranscriptionServiceError(
                                    f"Deepgram API error: {response.status} - {error_text}"
                                )
                            result_data = await response.json()
                            api_time = time.time() - api_start_time
                            logger.info("Deepgram API request completed", 
                                       api_time_seconds=round(api_time, 2),
                                       audio_url=audio_url)
                    else: #local file
                        logger.info('Deepgram APi gets local file')
                        async with aiofiles.open(audio_url, 'rb') as audio_file:
                            async with session.post(
                                self.base_url,
                                headers=headers,
                                params=params,
                                data=audio_file,
                                timeout=aiohttp.ClientTimeout(total=300)  # 5 minute timeout
                            ) as response:
                                if response.status != 200:
                                    error_text = await response.text()
                                    raise TranscriptionServiceError(
                                        f"Deepgram API error: {response.status} - {error_text}"
                                    )
                                
                                result_data = await response.json()
                                api_time = time.time() - api_start_time
                                logger.info("Deepgram API request completed", 
                                           api_time_seconds=round(api_time, 2),
                                           audio_url=audio_url)

                # Process Deepgram response
                processing_start = time.time()
                transcript, segments = self._process_deepgram_response(result_data)
                response_processing_time = time.time() - processing_start
                
                # Generate subtitle files
                subtitle_start = time.time()

                # Check caption style
                caption_style = config.get('caption_style')

                # Skip subtitle generation if caption_style is 'none'
                if caption_style == 'none':
                    logger.info("Skipping subtitle generation (caption_style='none')", audio_url=audio_url)
                    srt_content = ""
                    ass_content = ""
                else:
                    srt_content = self._generate_srt_content(segments)

                    # Check if advanced styling is requested
                    use_advanced_styling = caption_style in ['karaoke', 'word_by_word', 'sentence']

                    if use_advanced_styling and segments:
                        # Use advanced caption service for styled ASS
                        ass_content = await self._generate_advanced_ass_content(
                            segments,
                            caption_style,
                            config
                        )
                    else:
                        # Use basic ASS generation
                        ass_content = self._generate_ass_content(segments)
                
                subtitle_processing_time = time.time() - subtitle_start
                
                # Calculate cost and processing time
                processing_time = time.time() - start_time
                duration = result_data.get('metadata', {}).get('duration', 0)
                cost = self.estimate_cost(duration)
                
                logger.info(
                    "Deepgram transcription completed",
                    audio_url=audio_url,
                    duration=duration,
                    cost=cost,
                    processing_time=processing_time,
                    api_time_seconds=round(api_time, 2),
                    response_processing_time_seconds=round(response_processing_time, 2),
                    subtitle_processing_time_seconds=round(subtitle_processing_time, 2)
                )
                
                return TranscriptionResult(
                    transcript=transcript,
                    srt_content=srt_content,
                    ass_content=ass_content,
                    cost=cost,
                    processing_time=processing_time,
                    service_name=self.get_service_name(),
                    metadata={
                        'duration': duration,
                        'model': deepgram_config['model'],
                        'language': deepgram_config['language'],
                        'deepgram_response': result_data
                    }
                )
                
            finally:
                # Clean up temporary file
                # if os.path.exists(temp_audio_path):
                #     os.unlink(temp_audio_path)
                pass
        
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                "Deepgram transcription failed",
                audio_url=audio_url,
                error=str(e),
                processing_time=processing_time
            )
            raise TranscriptionServiceError(f"Deepgram transcription failed: {e}")
    
    def _process_deepgram_response(self, response_data: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Process Deepgram API response to extract transcript and segments
        
        Args:
            response_data: Deepgram API response
            
        Returns:
            Tuple of (full_transcript, segments_list)
        """
        try:
            results = response_data.get('results', {})
            channels = results.get('channels', [])
            
            if not channels:
                return "", []
            
            # Get the first channel
            channel = channels[0]
            alternatives = channel.get('alternatives', [])
            
            if not alternatives:
                return "", []
            
            # Get the best alternative
            alternative = alternatives[0]
            transcript = alternative.get('transcript', '')
            
            # Extract segments with timestamps
            segments = []
            words = alternative.get('words', [])
            
            if words:
                # Group words into segments with improved timing handling
                current_segment = {
                    'start': words[0].get('start', 0),
                    'end': words[0].get('end', 0),
                    'text': '',
                    'words': []  # Track individual words for better timing
                }
                
                for word in words:
                    word_text = word.get('word', '')
                    word_start = word.get('start', 0)
                    word_end = word.get('end', 0)
                    confidence = word.get('confidence', 1.0)
                    
                    # Only use words with reasonable confidence for timing
                    if confidence < 0.3:
                        logger.debug(f"Skipping low confidence word: {word_text} (confidence: {confidence})")
                        continue
                    
                    # If there's a significant gap (>1.5s) or punctuation, start new segment
                    time_gap = word_start - current_segment['end'] if current_segment['text'] else 0
                    is_punctuation_end = word_text.rstrip().endswith(('.', '!', '?', ';'))
                    is_long_segment = len(current_segment['text']) > 80
                    
                    if (time_gap > 1.5 or is_punctuation_end or is_long_segment):
                        if current_segment['text'].strip():
                            # Fine-tune segment timing based on word boundaries
                            if current_segment['words']:
                                current_segment['start'] = current_segment['words'][0]['start']
                                current_segment['end'] = current_segment['words'][-1]['end']
                            segments.append(current_segment)
                        
                        current_segment = {
                            'start': word_start,
                            'end': word_end,
                            'text': word_text,
                            'words': [{'word': word_text, 'start': word_start, 'end': word_end, 'confidence': confidence}]
                        }
                    else:
                        if current_segment['text']:
                            current_segment['text'] += ' ' + word_text
                        else:
                            current_segment['text'] = word_text
                        current_segment['end'] = word_end
                        current_segment['words'].append({
                            'word': word_text, 
                            'start': word_start, 
                            'end': word_end, 
                            'confidence': confidence
                        })
                
                # Add the last segment with fine-tuned timing
                if current_segment['text'].strip():
                    if current_segment['words']:
                        current_segment['start'] = current_segment['words'][0]['start']
                        current_segment['end'] = current_segment['words'][-1]['end']
                    segments.append(current_segment)
            
            # If no word-level timestamps, create segments from paragraphs
            if not segments:
                paragraphs = alternative.get('paragraphs', {}).get('paragraphs', [])
                for paragraph in paragraphs:
                    sentences = paragraph.get('sentences', [])
                    for sentence in sentences:
                        segments.append({
                            'start': sentence.get('start', 0),
                            'end': sentence.get('end', 0),
                            'text': sentence.get('text', '')
                        })
            
            return transcript, segments
            
        except Exception as e:
            logger.error("Failed to process Deepgram response", error=str(e))
            return "", []

    async def _generate_advanced_ass_content(
        self, 
        segments: List[Dict[str, Any]], 
        caption_style: str, 
        transcription_config: Dict[str, Any]
    ) -> str:
        """
        Generate advanced styled ASS content using the caption service
        
        Args:
            segments: Transcript segments with timing
            caption_style: Style type ('karaoke', 'word_by_word', 'sentence')
            transcription_config: Configuration settings
            
        Returns:
            Styled ASS content
        """
        try:
            from .caption_service import CloudCaptionService
            from video_processor.models.caption_models import WordSegment, CaptionSettings, SubtitleStyle
            
            # Convert segments to WordSegment objects
            word_segments = []
            for segment in segments:
                # Split segment text into words with estimated timing
                words = segment['text'].strip().split()
                if not words:
                    continue
                    
                start_time = segment.get('start', 0)
                end_time = segment.get('end', start_time + 1)
                duration = end_time - start_time
                word_duration = duration / len(words)
                
                for i, word in enumerate(words):
                    word_start = start_time + (i * word_duration)
                    word_end = word_start + word_duration
                    
                    word_segments.append(WordSegment(
                        word=word,
                        start=word_start,
                        end=word_end,
                        confidence=segment.get('confidence', 1.0)
                    ))
            
            # Create caption settings
            style_mapping = {
                'karaoke': SubtitleStyle.KARAOKE,
                'word_by_word': SubtitleStyle.WORD_BY_WORD,
                'sentence': SubtitleStyle.SENTENCE
            }
            
            settings = CaptionSettings(
                subtitle_style=style_mapping.get(caption_style, SubtitleStyle.KARAOKE),
                font_size=transcription_config.get('font_size', 48),
                font_family=transcription_config.get('font_family', 'Arial'),
                position=transcription_config.get('position', 'bottom'),
                default_color=transcription_config.get('default_color', '&HFFFFFF'),
                highlight_color=transcription_config.get('highlight_color', '&H00FFFF'),
                background_type=transcription_config.get('background_type', 'video'),
                video_parameters=transcription_config.get('video_parameters', {})
            )
            
            # Generate styled ASS content
            caption_service = CloudCaptionService()
            ass_content = caption_service._generate_ass_content(word_segments, settings)
            
            logger.info(
                "Advanced ASS content generated",
                style=caption_style,
                word_count=len(word_segments),
                segment_count=len(segments)
            )
            
            return ass_content
            
        except Exception as e:
            logger.error(
                "Failed to generate advanced ASS content", 
                style=caption_style, 
                error=str(e)
            )
            # Fallback to basic ASS generation
            return self._generate_ass_content(segments)


class AssemblyAITranscriptionService(BaseTranscriptionService):
    """AssemblyAI transcription service"""

    def __init__(self):
        super().__init__()
        self.api_key = self.settings.assemblyai_api_key
        self.base_url = "https://api.assemblyai.com/v2"
        self.upload_url = f"{self.base_url}/upload"
        self.transcript_url = f"{self.base_url}/transcript"

        if not self.api_key:
            logger.warning("AssemblyAI API key not configured")

    def get_service_name(self) -> str:
        return "assemblyai"

    def estimate_cost(self, duration_seconds: float) -> float:
        """
        Estimate AssemblyAI transcription cost

        AssemblyAI pricing (as of 2024):
        - Core transcription: $0.00037 per second ($0.022 per minute)
        """
        cost_per_second = 0.00037
        return duration_seconds * cost_per_second

    async def transcribe_audio(
        self,
        audio_url: str,
        config: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        job_id: Optional[str] = None
    ) -> TranscriptionResult:
        """
        Transcribe audio using AssemblyAI API

        Args:
            audio_url: URL or GCS path to audio file
            config: AssemblyAI-specific configuration
            user_id: User ID for saving raw transcript data to GCS (optional)
            job_id: Job ID for saving raw transcript data to GCS (optional)

        Returns:
            TranscriptionResult with transcript and subtitle files
        """
        if not self.api_key:
            raise TranscriptionServiceError("AssemblyAI API key not configured")
        
        start_time = time.time()
        
        try:
            # Default AssemblyAI configuration - minimal set for testing
            assemblyai_config = {
                'punctuate': True,
                'format_text': True,
                'language_detection': True,
            }
            
            # Filter config to only include AssemblyAI-specific parameters
            if config:
                # Only allow valid AssemblyAI parameters
                valid_assemblyai_params = {
                    'language_code', 'punctuate', 'format_text', 'dual_channel',
                    'speaker_labels', 'speakers_expected', 'content_safety',
                    'iab_categories', 'filter_profanity', 'redact_pii',
                    'redact_pii_audio', 'redact_pii_policies', 'redact_pii_sub',
                    'auto_highlights', 'summarization', 'summary_model', 'summary_type',
                    'custom_spelling', 'disfluencies', 'sentiment_analysis',
                    'auto_chapters', 'entity_detection', 'speech_threshold'
                }
                
                filtered_config = {k: v for k, v in config.items() if k in valid_assemblyai_params}
                assemblyai_config.update(filtered_config)
            
            logger.info(
                "Starting AssemblyAI transcription",
                audio_url=audio_url,
                config=assemblyai_config
            )

            # Check and refresh signed URL if expired
            if audio_url.startswith('https://storage.googleapis.com/') and 'X-Goog-Algorithm' in audio_url:
                logger.info("Checking if signed URL is expired", url=audio_url[:100] + "...")
                try:
                    # Refresh URL if expired (24 hour expiration for new URL)
                    refreshed_url = await ensure_valid_signed_url(audio_url, expiration_minutes=1440)
                    if refreshed_url != audio_url:
                        logger.info("Using refreshed signed URL for AssemblyAI",
                                  old_url=audio_url[:100] + "...",
                                  new_url=refreshed_url[:100] + "...")
                        audio_url = refreshed_url
                    else:
                        logger.debug("Signed URL is still valid, proceeding with original")
                except Exception as e:
                    logger.warning("Failed to refresh signed URL, proceeding with original",
                                 error=str(e), url=audio_url[:100] + "...")
                    # Continue with original URL - let AssemblyAI handle the error

            headers = {
                'Authorization': self.api_key,
                'Content-Type': 'application/json'
            }

            # Debug logging
            logger.info("AssemblyAI API Key configured",
                       api_key_present=bool(self.api_key),
                       api_key_length=len(self.api_key) if self.api_key else 0)

            # Prepare transcript request - only include valid AssemblyAI parameters
            transcript_request = {
                'audio_url': audio_url,
                **assemblyai_config
            }
            
            logger.info("AssemblyAI request prepared",
                       transcript_request=transcript_request,
                       headers_keys=list(headers.keys()))
            
            # If audio_url is a local file or needs to be uploaded
            if not audio_url.startswith(('http://', 'https://')):
                # Upload file first
                upload_url = await self._upload_audio_file(audio_url)
                transcript_request['audio_url'] = upload_url
            
            # Submit transcription job
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.transcript_url,
                    headers=headers,
                    json=transcript_request,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error("AssemblyAI transcript submission failed", 
                                   status=response.status, 
                                   error_text=error_text,
                                   audio_url=audio_url)
                        raise TranscriptionServiceError(
                            f"AssemblyAI API error: {response.status} - {error_text}"
                        )
                    
                    # Handle encoding issues in submit response
                    try:
                        # Try direct JSON parsing first
                        submit_response = await response.json()
                    except Exception as e:
                        logger.warning(f"Direct JSON parsing failed for submit: {e}, trying text parsing")
                        # Fallback to text parsing if direct JSON fails
                        response_text = await response.text()
                        try:
                            submit_response = json.loads(response_text)
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse submit response JSON: {e}")
                            logger.error(f"Submit response text: {response_text[:200]}...")
                            raise TranscriptionServiceError(f"Invalid JSON response from AssemblyAI submit: {e}")

                    transcript_id = submit_response['id']
                    
                    logger.info("1111111111111111111111AssemblyAI transcription job submitted",
                              transcript_id=transcript_id,
                              audio_url=audio_url)

            # Check if transcript file already exists
            existing_transcript = None
            if user_id and job_id:
                existing_transcript = await self._check_existing_transcript(user_id, job_id)

            if existing_transcript:
                existing_words = existing_transcript['words']
                existing_user_text = existing_transcript.get('user_input_text', '')

                if existing_transcript.get('caption_edited'):
                    # Respect manual caption edits exactly; do not auto-correct.
                    logger.info("Using manually edited transcript directly (skip Gemini correction)")
                    transcript_text = ' '.join([str(w.get('text', '')).strip() for w in existing_words]).strip()
                    result_data = {
                        'text': transcript_text,
                        'words': existing_words,
                        'confidence': sum(w.get('confidence', 1.0) for w in existing_words) / len(existing_words) if existing_words else 1.0,
                        'audio_duration': existing_words[-1].get('end', 0) if existing_words else 0,
                        'language_code': 'auto'
                    }
                elif existing_user_text:
                    # Use existing transcript and correct it with Gemini
                    logger.info("Using existing transcript and correcting with Gemini")
                    result_data = await self._correct_transcript_with_gemini(
                        existing_words,
                        existing_user_text
                    )
                else:
                    # Fallback: use existing words without correction
                    logger.info("Using existing transcript words directly (no user_input_text)")
                    transcript_text = ' '.join([str(w.get('text', '')).strip() for w in existing_words]).strip()
                    result_data = {
                        'text': transcript_text,
                        'words': existing_words,
                        'confidence': sum(w.get('confidence', 1.0) for w in existing_words) / len(existing_words) if existing_words else 1.0,
                        'audio_duration': existing_words[-1].get('end', 0) if existing_words else 0,
                        'language_code': 'auto'
                    }
            else:
                # Poll for completion
                result_data = await self._poll_for_completion(
                    transcript_id,
                    headers,
                    user_id=user_id,
                    job_id=job_id
                )

            # Process AssemblyAI response
            transcript, segments = self._process_assemblyai_response(result_data)

            # Check caption style
            caption_style = config.get('caption_style')

            # Skip subtitle generation if caption_style is 'none'
            if caption_style == 'none':
                logger.info("Skipping subtitle generation (caption_style='none')", audio_url=audio_url, transcript_id=transcript_id)
                srt_content = ""
                ass_content = ""
            else:
                # Generate subtitle files
                srt_content = self._generate_srt_content(segments)

                # Debug logging for Chinese character verification
                # if segments:
                #     sample_text = segments[0].get('text', '')
                #     logger.info(f'Sample Chinese text (raw): {repr(sample_text)}')
                #     logger.info(f'Sample Chinese text (display): {sample_text}')
                #     logger.info(f'Sample Chinese text type: {type(sample_text)}')

                #     if sample_text:
                #         logger.info(f'Contains Chinese chars: {any("\u4e00" <= char <= "\u9fff" for char in sample_text)}')
                #         logger.info(f'Contains escape sequences: {"\\u" in sample_text}')
                #     else:
                #         logger.warning('Sample text is empty')

                logger.info(f'Processed segments count: {len(segments)}')
                logger.info(f'SRT content length: {len(srt_content) if srt_content else 0}')

                # Check if advanced styling is requested
                use_advanced_styling = caption_style in ['karaoke', 'word_by_word', 'sentence']

                if use_advanced_styling and segments:
                    # Use advanced caption service for styled ASS
                    ass_content = await self._generate_advanced_ass_content(
                        segments,
                        caption_style,
                        config
                    )
                else:
                    # Use basic ASS generation
                    ass_content = self._generate_ass_content(segments)
            
            # Calculate cost and processing time
            processing_time = time.time() - start_time
            duration = result_data.get('audio_duration', 0)
            cost = self.estimate_cost(duration)
            
            logger.info(
                "AssemblyAI transcription completed",
                audio_url=audio_url,
                transcript_id=transcript_id,
                duration=duration,
                cost=cost,
                processing_time=processing_time
            )
            logger.info(result_data)
            
            return TranscriptionResult(
                transcript=transcript,
                srt_content=srt_content,
                ass_content=ass_content,
                cost=cost,
                processing_time=processing_time,
                service_name=self.get_service_name(),
                metadata={
                    'duration': duration,
                    'transcript_id': transcript_id,
                    'confidence': result_data.get('confidence', 0),
                    'language_code': result_data.get('language_code', 'en'),
                    'assemblyai_response': result_data
                }
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                "AssemblyAI transcription failed",
                audio_url=audio_url,
                error=str(e),
                processing_time=processing_time
            )
            raise TranscriptionServiceError(f"AssemblyAI transcription failed: {e}")
    
    async def _upload_audio_file(self, file_path: str) -> str:
        """
        Upload audio file to AssemblyAI and return the upload URL
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Upload URL from AssemblyAI
        """
        headers = {
            'Authorization': self.api_key
        }
        
        # Debug the upload headers too
        logger.info("AssemblyAI upload headers", 
                   api_key_present=bool(self.api_key),
                   headers_keys=list(headers.keys()))
        
        # Download file if it's a local-storage-compatible URL
        if file_path.startswith(('gs://', 'https://storage.googleapis.com/')):
            temp_file_path = await self._download_audio_file(file_path)
        else:
            temp_file_path = file_path
        
        try:
            async with aiohttp.ClientSession() as session:
                async with aiofiles.open(temp_file_path, 'rb') as audio_file:
                    audio_data = await audio_file.read()
                    
                    async with session.post(
                        self.upload_url,
                        headers=headers,
                        data=audio_data,
                        timeout=aiohttp.ClientTimeout(total=300)
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise TranscriptionServiceError(
                                f"AssemblyAI upload error: {response.status} - {error_text}"
                            )
                        
                        upload_response = await response.json()
                        return upload_response['upload_url']
        finally:
            # Clean up temp file if we downloaded it
            if file_path != temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    async def _check_existing_transcript(
        self,
        user_id: str,
        project_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if a transcript file already exists in GCS

        Args:
            user_id: User ID
            project_id: Project ID (job_id)

        Returns:
            Dict with transcript data if file exists, None otherwise
        """
        try:
            bucket = self.gcs_service.client.bucket(GCS_BUCKET_NAME)
            candidate_blob_names = [
                f"output/{user_id}/{project_id}/raw_transcript_data.txt"
            ]

            # Also check language-specific files (raw_transcript_data_en.txt, etc.)
            for blob_info in bucket.list_blobs(prefix=f"output/{user_id}/{project_id}/raw_transcript_data_"):
                if blob_info.name.endswith(".txt") and blob_info.name not in candidate_blob_names:
                    candidate_blob_names.append(blob_info.name)

            logger.info("Checking for existing transcript", candidates=candidate_blob_names)

            for blob_name in candidate_blob_names:
                blob = bucket.blob(blob_name)
                if not blob.exists():
                    continue

                logger.info("Existing transcript found, downloading...", blob_name=blob_name)
                content = blob.download_as_text()
                data = json.loads(content)

                words = data.get('words', []) or []
                user_input_text = (data.get('user_input_text') or data.get('text') or '').strip()
                caption_edited = bool(data.get('caption_edited'))

                if not words:
                    logger.warning("Existing transcript file has no words", blob_name=blob_name)
                    continue

                logger.info(
                    "Existing transcript loaded successfully",
                    blob_name=blob_name,
                    word_count=len(words),
                    text_length=len(user_input_text),
                    caption_edited=caption_edited
                )

                return {
                    'words': words,
                    'user_input_text': user_input_text,
                    'caption_edited': caption_edited
                }

            logger.info("No usable existing transcript found")
            return None

        except Exception as e:
            logger.info("Could not load existing transcript", error=str(e))
            return None

    async def _correct_transcript_with_gemini(
        self,
        words: List[Dict[str, Any]],
        user_input_text: str
    ) -> Dict[str, Any]:
        """
        Use Gemini to correct transcription data based on user input

        Args:
            words: List of word dictionaries from transcription
            user_input_text: Original text input from user

        Returns:
            Corrected response data in AssemblyAI format
        """
        try:
            # Configure Gemini client
            logger.info(f"Gemini API key: {self.settings.gemini_api_key}")
            client = genai.Client(api_key=self.settings.gemini_api_key)

            # Prepare prompt
            system_prompt = """Your task is to correct and sync the following speech to text data.
'user_input_text' is the original input from user.
'words' contains data from the transcription model and this data can be incorrect.

Use 'user_input_text' as a reference, and correct all 'text' within 'words' only if the 'text' is clearly incorrect transcription.
Do not change or modify text if already correct.
Do not modify anything else in the words array (keep start, end, confidence unchanged).

Return ONLY a valid JSON object with this exact structure:
{
  "words": [<corrected words array>]
}

Do not include any markdown formatting, code blocks, or explanatory text. Return only the raw JSON."""

            data_to_correct = {
                'user_input_text': user_input_text,
                'words': words
            }

            prompt = f"{system_prompt}\n\nData to correct:\n{json.dumps(data_to_correct, ensure_ascii=False)}"

            logger.info("Sending transcription to Gemini for correction...")

            # Call Gemini
            response = client.models.generate_content(
                model='gemini-2.5-flash-lite',
                contents=prompt
            )
            response_text = response.text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                # Remove ```json or ``` at start and ``` at end
                lines = response_text.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                response_text = '\n'.join(lines)
            logger.info(f'data sent to gemini: {json.dumps(data_to_correct, ensure_ascii=False)}')
            logger.info(f'Gemini response direct: {response_text}')
            logger.info("Received Gemini response", response_length=len(response_text))

            # Parse response
            corrected_data = json.loads(response_text)
            corrected_words = corrected_data.get('words', words)

            # Reconstruct full transcript from corrected words
            transcript_text = ' '.join([w.get('text', '') for w in corrected_words])

            # Create AssemblyAI-compatible response
            result_data = {
                'text': transcript_text,
                'words': corrected_words,
                'confidence': sum(w.get('confidence', 1.0) for w in corrected_words) / len(corrected_words) if corrected_words else 1.0,
                'audio_duration': corrected_words[-1].get('end', 0) if corrected_words else 0,
                'language_code': 'auto'
            }

            logger.info("Gemini correction completed successfully",
                       corrected_word_count=len(corrected_words))

            return result_data

        except Exception as e:
            logger.error("Gemini correction failed", error=str(e))
            # Return original data as fallback
            return {
                'text': user_input_text,
                'words': words,
                'confidence': 1.0,
                'audio_duration': words[-1].get('end', 0) if words else 0,
                'language_code': 'auto'
            }

    async def _poll_for_completion(
        self,
        transcript_id: str,
        headers: Dict[str, str],
        max_wait_time: int = 600,
        poll_interval: int = 5,
        save_raw_data: bool = True,
        user_id: str = None,
        job_id: str = None
    ) -> Dict[str, Any]:
        """
        Poll AssemblyAI for transcription completion

        Args:
            transcript_id: AssemblyAI transcript ID
            headers: HTTP headers for API requests
            max_wait_time: Maximum time to wait in seconds
            poll_interval: Time between polls in seconds
            save_raw_data: Whether to save raw response data to GCS
            user_id: User ID for GCS path (required if save_raw_data=True)
            job_id: Job ID for GCS path (required if save_raw_data=True)

        Returns:
            Completed transcript data
        """
        start_time = time.time()
        get_url = f"{self.transcript_url}/{transcript_id}"
        
        logger.info("Polling AssemblyAI for completion", 
                   transcript_id=transcript_id,
                   max_wait_time=max_wait_time)
        
        async with aiohttp.ClientSession() as session:
            while time.time() - start_time < max_wait_time:
                async with session.get(get_url, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error("AssemblyAI polling failed", 
                                   status=response.status,
                                   error_text=error_text,
                                   get_url=get_url)
                        raise TranscriptionServiceError(
                            f"AssemblyAI polling error: {response.status} - {error_text}"
                        )
                    
                    # Handle potential encoding issues in the response
                    # First, let's get the raw response text to debug what's actually coming from AssemblyAI
                    response_text = await response.text()
                    logger.info(f"Raw response text sample: {response_text[:500]}...")

                    # Parse the response text as JSON
                    result = json.loads(response_text)

                    status = result.get('status')
                    logger.debug("AssemblyAI poll response",
                               status=status,
                               transcript_id=transcript_id,
                               elapsed=time.time() - start_time)
                    
                    if status == 'completed':
                        logger.info("AssemblyAI transcription completed",
                                   transcript_id=transcript_id,
                                   elapsed_time=time.time() - start_time)

                        # Save raw response data to GCS if requested
                        logger.info(f'save_raw_data: {save_raw_data}')
                        logger.info(f'user_id: {user_id}')
                        logger.info(f'job_id: {job_id}')

                        # Debug the text encoding in the response
                        # if 'text' in result:
                        #     text_field = result['text']
                        #     logger.info(f'Raw text field type: {type(text_field)}')
                        #     logger.info(f'Raw text field repr: {repr(text_field[:100])}')
                        #     logger.info(f'Raw text field display: {text_field[:100]}')

                        #     # Try to fix the encoding issue
                        #     try:
                        #         # If it's garbled, it might be UTF-8 decoded as latin-1
                        #         if isinstance(text_field, str) and any(ord(c) > 127 for c in text_field):
                        #             # Try to re-encode as latin-1 then decode as utf-8
                        #             fixed_text = text_field.encode('latin-1').decode('utf-8')
                        #             logger.info(f'Fixed text: {fixed_text[:100]}')
                        #             result['text'] = fixed_text

                        #             # Also fix the words array
                        #             if 'words' in result and result['words']:
                        #                 for word in result['words']:
                        #                     if 'text' in word and isinstance(word['text'], str):
                        #                         try:
                        #                             word['text'] = word['text'].encode('latin-1').decode('utf-8')
                        #                         except:
                        #                             pass  # Keep original if fixing fails

                        #     except Exception as e:
                        #         logger.warning(f'Failed to fix text encoding: {e}')

                        if save_raw_data and user_id and job_id:
                            try:
                                # Convert the raw response to pretty-printed JSON
                                raw_data_json = json.dumps(result, indent=2, ensure_ascii=False)
                                logger.info('Saving raw data to GCS...')
                                # Upload to GCS in the same location as other transcript files
                                raw_data_url = await self.gcs_service.upload_content(
                                    raw_data_json,
                                    user_id,
                                    job_id,
                                    "raw_transcript_data.txt",
                                    "output"
                                )

                                logger.info("Raw transcript data saved to GCS",
                                          url=raw_data_url,
                                          transcript_id=transcript_id,
                                          size=len(raw_data_json))

                            except Exception as e:
                                logger.error("Failed to save raw transcript data to GCS",
                                           error=str(e),
                                           transcript_id=transcript_id)
                                # Don't fail the transcription if raw data saving fails

                        return result
                    elif status == 'error':
                        error_msg = result.get('error', 'Unknown error')
                        raise TranscriptionServiceError(
                            f"AssemblyAI transcription failed: {error_msg}"
                        )
                    elif status in ['queued', 'processing']:
                        logger.info("AssemblyAI transcription in progress", 
                                   transcript_id=transcript_id,
                                   status=status,
                                   elapsed_time=time.time() - start_time)
                        await asyncio.sleep(poll_interval)
                    else:
                        logger.warning("Unknown AssemblyAI status", 
                                     transcript_id=transcript_id,
                                     status=status)
                        await asyncio.sleep(poll_interval)
        
        raise TranscriptionServiceError(
            f"AssemblyAI transcription timed out after {max_wait_time} seconds"
        )
    
    def _process_assemblyai_response(self, response_data: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Process AssemblyAI API response to extract transcript and segments
        
        Args:
            response_data: AssemblyAI API response
            
        Returns:
            Tuple of (full_transcript, segments_list)
        """
        try:
            # Get the raw transcript text and fix encoding issues
            raw_transcript = response_data.get('text', '')
            logger.info(f'Raw transcript type: {type(raw_transcript)}, value: {repr(raw_transcript)}')

            if raw_transcript is None:
                logger.warning("Raw transcript is None, using empty string")
                raw_transcript = ''

            transcript = self._fix_text_encoding(raw_transcript)
            logger.info(f'Fixed transcript type: {type(transcript)}, value: {repr(transcript[:100])}...')

            if transcript is None:
                logger.error("Fixed transcript is None! This should not happen")
                transcript = str(raw_transcript) if raw_transcript else ''

            logger.info(f'Raw transcript length: {len(raw_transcript)}, Fixed transcript: {transcript[:100]}...')

            # Extract segments from words array
            words = response_data.get('words', [])
            if not words:
                # If no word-level data, create basic segments from transcript
                return transcript, [{
                    'start': 0,
                    'end': response_data.get('audio_duration', 0) / 1000,  # Convert ms to seconds
                    'text': transcript
                }]
            
            # Group words into segments (similar to Deepgram approach)
            segments = []
            if words:
                current_segment = {
                    'start': words[0].get('start', 0) / 1000,  # Convert ms to seconds
                    'end': words[0].get('end', 0) / 1000,
                    'text': '',
                    'confidence': words[0].get('confidence', 1.0)
                }
                
                for word in words:
                    raw_word_text = word.get('text', '')
                    word_text = self._fix_text_encoding(raw_word_text)
                    word_start = word.get('start', 0) / 1000  # Convert ms to seconds
                    word_end = word.get('end', 0) / 1000
                    confidence = word.get('confidence', 1.0)
                    
                    # If there's a significant gap (>1.5s) or segment is getting long, start new segment
                    time_gap = word_start - current_segment['end'] if current_segment['text'] else 0
                    is_long_segment = len(current_segment['text']) > 80
                    
                    if time_gap > 1.5 or is_long_segment:
                        if current_segment['text'].strip():
                            segments.append(current_segment)
                        
                        current_segment = {
                            'start': word_start,
                            'end': word_end,
                            'text': word_text,
                            'confidence': confidence
                        }
                    else:
                        if current_segment['text']:
                            current_segment['text'] += ' ' + word_text
                        else:
                            current_segment['text'] = word_text
                        current_segment['end'] = word_end
                        # Update confidence to average
                        current_segment['confidence'] = (current_segment['confidence'] + confidence) / 2
                
                # Add the last segment
                if current_segment['text'].strip():
                    segments.append(current_segment)
            
            return transcript, segments
            
        except Exception as e:
            logger.error("Failed to process AssemblyAI response", error=str(e))
            return "", []

    def _fix_text_encoding(self, text: str) -> str:
        """
        Fix encoding issues with text from AssemblyAI response

        Args:
            text: Raw text that may have encoding issues

        Returns:
            Properly encoded text
        """
        #logger.info(f"_fix_text_encoding called with: {repr(text[:100])}")

        if not text:
            logger.info("Text is empty, returning as-is")
            return text

        try:
            # Handle Unicode escape sequences that might be in the text
            if isinstance(text, str):
                # Check if text contains Unicode escape sequences like \u968f
                #logger.info(f"Checking for Unicode escape sequences in: {repr(text[:50])}")
                #logger.info(f"Contains \\u: {'\\u' in text}")

                if '\\u' in text:
                    logger.info(f"FOUND Unicode escape sequences! Attempting to decode: {text[:100]}...")

                    # Method 1: Try to decode Unicode escape sequences using unicode_escape
                    try:
                        decoded_text = codecs.decode(text, 'unicode_escape')
                        logger.info(f"SUCCESS: Decoded with codecs.decode: '{decoded_text[:50]}...'")
                        return decoded_text
                    except Exception as e:
                        logger.debug(f"Method 1 failed: {e}")

                    # Method 2: Manual replacement approach (most reliable for this case)
                    try:
                        def decode_unicode_match(match):
                            unicode_value = int(match.group(1), 16)
                            return chr(unicode_value)

                        decoded_text = re.sub(r'\\u([0-9a-fA-F]{4})', decode_unicode_match, text)
                        if decoded_text != text:  # Only if we actually made changes
                            #logger.info(f"SUCCESS: Decoded with regex: '{decoded_text[:50]}...'")
                            return decoded_text
                        else:
                            logger.debug("Regex method didn't change the text")
                    except Exception as e:
                        logger.debug(f"Method 2 (regex) failed: {e}")

                    # Method 3: Try with encode/decode approach
                    try:
                        # First encode as latin1 to preserve the literal backslashes, then decode
                        decoded_text = text.encode('latin1').decode('unicode_escape')
                        #logger.info(f"SUCCESS: Decoded with latin1/unicode_escape: '{decoded_text[:50]}...'")
                        return decoded_text
                    except Exception as e:
                        logger.debug(f"Method 3 failed: {e}")

                    # Method 4: Try using literal_eval for JSON-like strings
                    try:
                        import ast
                        # Wrap in quotes to make it a valid Python string literal
                        wrapped_text = f'"{text}"'
                        decoded_text = ast.literal_eval(wrapped_text)
                        #logger.info(f"SUCCESS: Decoded with ast.literal_eval: '{decoded_text[:50]}...'")
                        return decoded_text
                    except Exception as e:
                        logger.debug(f"Method 4 (ast.literal_eval) failed: {e}")

                    logger.warning(f"All Unicode decoding methods failed for text: {text[:100]}...")
                else:
                    #logger.debug("No Unicode escape sequences found in text")
                    pass
                # Check if text already contains proper characters (Chinese or normal text)
                if any('\u4e00' <= char <= '\u9fff' for char in text):
                    #logger.info("Text already contains proper Chinese characters")
                    return text

                # Check if text appears to be normal ASCII/English text
                # Only try re-encoding if we detect garbled characters or encoding issues
                try:
                    # Test if text is valid ASCII or already proper UTF-8
                    text.encode('ascii')
                    # If we get here, text is plain ASCII/English - return as-is
                    #logger.debug("Text is plain ASCII/English, returning as-is")
                    return text
                except UnicodeEncodeError:
                    # Text contains non-ASCII characters - might be garbled, let's check
                    logger.debug("Text contains non-ASCII characters, checking if garbled")

                    # Try to handle improperly encoded strings ONLY if they look garbled
                    try:
                        # If it's a string that was improperly decoded, encode it back and decode correctly
                        encoded_bytes = text.encode('latin1')  # Use latin1 to preserve all bytes

                        # Try different decodings
                        for encoding in ['utf-8', 'utf-16', 'gb2312', 'gbk', 'big5']:
                            try:
                                decoded_text = encoded_bytes.decode(encoding)
                                # Check if the decoded text looks reasonable (contains Chinese characters)
                                if any('\u4e00' <= char <= '\u9fff' for char in decoded_text):
                                    logger.info(f"Successfully decoded text using {encoding}")
                                    return decoded_text
                            except (UnicodeDecodeError, UnicodeError):
                                continue

                        # If no encoding produced Chinese characters, return original text (might be other language)
                        logger.debug("No encoding produced Chinese characters, returning original text")
                        return text

                    except (UnicodeEncodeError, UnicodeDecodeError):
                        # If encoding/decoding fails, fall back to original text
                        logger.debug("Encoding/decoding failed, returning original text")
                        pass

            # If text is bytes, decode it directly
            elif isinstance(text, bytes):
                # Try different encodings for Chinese text
                for encoding in ['utf-8', 'utf-16', 'gb2312', 'gbk', 'big5']:
                    try:
                        decoded_text = text.decode(encoding)
                        logger.info(f"Successfully decoded bytes using {encoding}")
                        return decoded_text
                    except (UnicodeDecodeError, UnicodeError):
                        continue

                # Fallback to UTF-8 with error handling
                return text.decode('utf-8', errors='ignore')

            # If it's some other type, convert to string
            return str(text)

        except Exception as e:
            logger.error(f"Failed to fix text encoding: {e}")
            # Return original text as fallback, ensuring it's always a string
            if text is None:
                logger.warning("Text is None, returning empty string")
                return ""
            return str(text)

    async def _generate_advanced_ass_content(
        self, 
        segments: List[Dict[str, Any]], 
        caption_style: str, 
        transcription_config: Dict[str, Any]
    ) -> str:
        """
        Generate advanced styled ASS content using the caption service
        
        Args:
            segments: Transcript segments with timing
            caption_style: Style type ('karaoke', 'word_by_word', 'sentence')
            transcription_config: Configuration settings
            
        Returns:
            Styled ASS content
        """
        try:
            from .caption_service import CloudCaptionService
            from video_processor.models.caption_models import WordSegment, CaptionSettings, SubtitleStyle
            
            # Convert segments to WordSegment objects
            word_segments = []
            for segment in segments:
                # Split segment text into words with estimated timing
                words = segment['text'].strip().split()
                if not words:
                    continue
                    
                start_time = segment.get('start', 0)
                end_time = segment.get('end', start_time + 1)
                duration = end_time - start_time
                word_duration = duration / len(words)
                
                for i, word in enumerate(words):
                    word_start = start_time + (i * word_duration)
                    word_end = word_start + word_duration
                    
                    word_segments.append(WordSegment(
                        word=word,
                        start=word_start,
                        end=word_end,
                        confidence=segment.get('confidence', 1.0)
                    ))
            
            # Create caption settings
            style_mapping = {
                'karaoke': SubtitleStyle.KARAOKE,
                'word_by_word': SubtitleStyle.WORD_BY_WORD,
                'sentence': SubtitleStyle.SENTENCE
            }
            
            settings = CaptionSettings(
                subtitle_style=style_mapping.get(caption_style, SubtitleStyle.KARAOKE),
                font_size=transcription_config.get('font_size', 48),
                font_family=transcription_config.get('font_family', 'Arial'),
                position=transcription_config.get('position', 'bottom'),
                default_color=transcription_config.get('default_color', '&HFFFFFF'),
                highlight_color=transcription_config.get('highlight_color', '&H00FFFF'),
                background_type=transcription_config.get('background_type', 'video'),
                video_parameters=transcription_config.get('video_parameters', {})
            )
            
            # Generate styled ASS content
            caption_service = CloudCaptionService()
            ass_content = caption_service._generate_ass_content(word_segments, settings)
            
            logger.info(
                "Advanced ASS content generated",
                style=caption_style,
                word_count=len(word_segments),
                segment_count=len(segments)
            )
            
            return ass_content
            
        except Exception as e:
            logger.error(
                "Failed to generate advanced ASS content", 
                style=caption_style, 
                error=str(e)
            )
            # Fallback to basic ASS generation
            return self._generate_ass_content(segments)


class WhisperTranscriptionService(BaseTranscriptionService):
    """Cloud Whisper transcription service using faster-whisper"""
    
    def __init__(self):
        super().__init__()
        self.model_size = os.getenv("FASTER_WHISPER_MODEL", "large-v3")
        self._model = None
    
    def get_service_name(self) -> str:
        return "whisper"
    
    def estimate_cost(self, duration_seconds: float) -> float:
        """
        Estimate Whisper transcription cost (compute-based)
        
        This is primarily compute cost, very low compared to API services
        """
        # Minimal cost for compute time
        minutes = duration_seconds / 60
        cost_per_minute = 0.001  # Very low cost for self-hosted
        return minutes * cost_per_minute
    
    async def transcribe_audio(
        self,
        audio_url: str,
        config: Optional[Dict[str, Any]] = None
    ) -> TranscriptionResult:
        """
        Transcribe audio using faster-whisper
        
        Args:
            audio_url: URL or GCS path to audio file
            config: Whisper-specific configuration
            
        Returns:
            TranscriptionResult with transcript and subtitle files
        """
        start_time = time.time()
        
        try:
            # Default Whisper configuration
            whisper_config = {
                'model_size': os.getenv("FASTER_WHISPER_MODEL", "large-v3"),
                'language': None,  # Auto-detect
                'task': 'transcribe',
                'beam_size': 5,
                'best_of': 5,
                'temperature': 0.0,
                'condition_on_previous_text': True,
                'word_timestamps': True
            }
            
            if config:
                whisper_config.update(config)
            
            logger.info(
                "Starting Whisper transcription",
                audio_url=audio_url,
                config=whisper_config
            )
            
            # Download audio file
            temp_audio_path = await self._download_audio_file(audio_url)
            
            try:
                # Import faster-whisper (lazy import to avoid startup issues)
                try:
                    from faster_whisper import WhisperModel
                except ImportError:
                    raise TranscriptionServiceError(
                        "faster-whisper not installed. Install with: pip install faster-whisper"
                    )
                
                # Initialize model if needed
                if self._model is None or self.model_size != whisper_config['model_size']:
                    self.model_size = whisper_config['model_size']
                    self._model = WhisperModel(
                        self.model_size,
                        device="cpu",  # Use CPU for Cloud Run compatibility
                        compute_type="int8"  # Optimize for memory usage
                    )
                
                # Run transcription in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                segments, info = await loop.run_in_executor(
                    None,
                    self._run_whisper_transcription,
                    temp_audio_path,
                    whisper_config
                )
                
                # Process results
                transcript_segments = []
                full_transcript = []
                
                for segment in segments:
                    segment_data = {
                        'start': segment.start,
                        'end': segment.end,
                        'text': segment.text.strip()
                    }
                    transcript_segments.append(segment_data)
                    full_transcript.append(segment.text.strip())
                
                transcript = ' '.join(full_transcript)
                
                # Generate subtitle files
                srt_content = self._generate_srt_content(transcript_segments)
                ass_content = self._generate_ass_content(transcript_segments)
                
                # Calculate processing time and cost
                processing_time = time.time() - start_time
                duration = info.duration if info else 0
                cost = self.estimate_cost(duration)
                
                logger.info(
                    "Whisper transcription completed",
                    audio_url=audio_url,
                    duration=duration,
                    cost=cost,
                    processing_time=processing_time,
                    model_size=self.model_size
                )
                
                return TranscriptionResult(
                    transcript=transcript,
                    srt_content=srt_content,
                    ass_content=ass_content,
                    cost=cost,
                    processing_time=processing_time,
                    service_name=self.get_service_name(),
                    metadata={
                        'duration': duration,
                        'model_size': self.model_size,
                        'language': info.language if info else 'unknown',
                        'language_probability': info.language_probability if info else 0.0
                    }
                )
                
            finally:
                # Clean up temporary file
                if os.path.exists(temp_audio_path):
                    os.unlink(temp_audio_path)
        
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                "Whisper transcription failed",
                audio_url=audio_url,
                error=str(e),
                processing_time=processing_time
            )
            raise TranscriptionServiceError(f"Whisper transcription failed: {e}")
    
    def _run_whisper_transcription(self, audio_path: str, config: Dict[str, Any]):
        """
        Run Whisper transcription in synchronous context
        
        Args:
            audio_path: Path to audio file
            config: Whisper configuration
            
        Returns:
            Tuple of (segments, info)
        """
        return self._model.transcribe(
            audio_path,
            language=config.get('language'),
            task=config.get('task', 'transcribe'),
            beam_size=config.get('beam_size', 5),
            best_of=config.get('best_of', 5),
            temperature=config.get('temperature', 0.0),
            condition_on_previous_text=config.get('condition_on_previous_text', True),
            word_timestamps=config.get('word_timestamps', True)
        )


class TranscriptionServiceSelector:
    """Service selector for choosing appropriate transcription service"""
    
    def __init__(self):
        self.services = {
            'whisper': WhisperTranscriptionService(),
            'faster-whisper': WhisperTranscriptionService(),
        }
        self.default_service = os.getenv("TRANSCRIPTION_SERVICE", "whisper")
    
    def get_service(self, service_name: Optional[str] = None) -> BaseTranscriptionService:
        """
        Get transcription service by name
        
        Args:
            service_name: Name of service ('whisper' or 'faster-whisper') or None for default
            
        Returns:
            BaseTranscriptionService instance
            
        Raises:
            TranscriptionServiceError: If service not found
        """
        if service_name is None:
            service_name = self.default_service
        if service_name in ("local", "whisper-local"):
            service_name = "whisper"
            
        logger.info("Transcription service selected", 
                   requested_service=service_name, 
                   default_service=self.default_service,
                   available_services=list(self.services.keys()))
        
        if service_name not in self.services:
            available = ', '.join(self.services.keys())
            raise TranscriptionServiceError(
                f"Unknown transcription service: {service_name}. Available: {available}"
            )
        
        return self.services[service_name]
    
    def get_available_services(self) -> List[str]:
        """Get list of available transcription services"""
        return list(self.services.keys())
    
    async def transcribe_with_service(
        self,
        audio_url: str,
        service_name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        job_id: Optional[str] = None
    ) -> TranscriptionResult:
        """
        Transcribe audio using specified service

        Args:
            audio_url: URL or GCS path to audio file
            service_name: Name of transcription service
            config: Service-specific configuration
            user_id: User ID for saving raw data (AssemblyAI only)
            job_id: Job ID for saving raw data (AssemblyAI only)

        Returns:
            TranscriptionResult
        """
        service = self.get_service(service_name)

        # For AssemblyAI service, pass user_id and job_id for raw data saving
        if service_name == 'assemblyai' and hasattr(service, 'transcribe_audio'):
            # Check if the service supports the extra parameters
            import inspect
            sig = inspect.signature(service.transcribe_audio)
            if 'user_id' in sig.parameters:
                return await service.transcribe_audio(audio_url, config, user_id, job_id)

        # For other services, use the standard call
        return await service.transcribe_audio(audio_url, config)


# Singleton instance
_transcription_selector = None


def get_transcription_service() -> TranscriptionServiceSelector:
    """Get singleton transcription service selector"""
    global _transcription_selector
    if _transcription_selector is None:
        _transcription_selector = TranscriptionServiceSelector()
    return _transcription_selector

def reset_transcription_service():
    """Reset the singleton transcription service selector (for testing/debugging)"""
    global _transcription_selector
    _transcription_selector = None
