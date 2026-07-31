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


from config import get_settings
from services.gcs_service import get_gcs_service


logger = structlog.get_logger(__name__)


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
        Resolve audio to a local temp file path.

        Prefers local filesystem (Vyravid /media storage) so we never depend
        on external services fetching localhost URLs.
        """
        try:
            temp_fd, temp_path = tempfile.mkstemp(suffix='.audio')
            os.close(temp_fd)

            # 1) Local storage /media or relative path
            try:
                if hasattr(self.gcs_service, "path_from_url"):
                    local = self.gcs_service.path_from_url(audio_url)
                    if local and local.exists():
                        import shutil
                        shutil.copy2(local, temp_path)
                        logger.info("Local media resolved", source=str(local), temp_path=temp_path)
                        return temp_path
                if hasattr(self.gcs_service, "download_file"):
                    await self.gcs_service.download_file(audio_url, temp_path)
                    if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                        logger.info("Audio copied via storage service", temp_path=temp_path)
                        return temp_path
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.warning("Local resolve failed, trying other methods", error=str(e))

            if audio_url.startswith(('gs://', 'https://storage.googleapis.com/')):
                raise TranscriptionError(
                    "External Google Cloud Storage audio URLs are not supported in local mode"
                )
            elif audio_url.startswith(('http://', 'https://')):
                # Localhost URLs: map /media/... back to disk instead of HTTP self-fetch
                from urllib.parse import urlparse
                parsed = urlparse(audio_url)
                if parsed.hostname in ("localhost", "127.0.0.1") and parsed.path.startswith("/media/"):
                    rel = parsed.path[len("/media/"):]
                    if hasattr(self.gcs_service, "download_file"):
                        await self.gcs_service.download_file(rel, temp_path)
                    else:
                        raise TranscriptionError(f"Cannot resolve local media path: {rel}")
                else:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(audio_url) as response:
                            if response.status != 200:
                                raise TranscriptionError(f"Failed to download audio: HTTP {response.status}")
                            async with aiofiles.open(temp_path, 'wb') as f:
                                async for chunk in response.content.iter_chunked(8192):
                                    await f.write(chunk)
            elif audio_url.startswith('file://'):
                local_path = audio_url.replace('file://', '')
                if not os.path.isabs(local_path):
                    local_path = os.path.join(os.getcwd(), local_path)
                if not os.path.exists(local_path):
                    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    alt_path = os.path.join(project_root, local_path.lstrip('/'))
                    if os.path.exists(alt_path):
                        local_path = alt_path
                    else:
                        raise TranscriptionError(f"Local file not found: {local_path}")
                import shutil
                shutil.copy2(local_path, temp_path)
            elif os.path.exists(audio_url):
                import shutil
                shutil.copy2(audio_url, temp_path)
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
                srt_content = self._generate_srt_content(segments)
                
                # Check if advanced styling is requested
                caption_style = config.get('caption_style') if config else None
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
            from .caption_service import CaptionService
            from models.caption_models import WordSegment, CaptionSettings, SubtitleStyle
            
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
            caption_service = CaptionService()

            # Get ASS header
            ass_header = caption_service.get_ass_header(settings)

            # Generate events based on style
            if settings.subtitle_style == SubtitleStyle.KARAOKE:
                events = caption_service.generate_karaoke_style(word_segments)
            elif settings.subtitle_style == SubtitleStyle.WORD_BY_WORD:
                events = caption_service.generate_word_by_word_style(word_segments)
            elif settings.subtitle_style == SubtitleStyle.SENTENCE:
                events = caption_service.generate_sentence_style(word_segments)
            else:
                events = caption_service.generate_karaoke_style(word_segments)

            # Combine header and events
            ass_content = ass_header + '\n'.join(events)

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
        job_id: Optional[str] = None,
        user_input_text: Optional[str] = None,
        language_code: Optional[str] = None
    ) -> TranscriptionResult:
        """
        Transcribe audio using AssemblyAI API

        Args:
            audio_url: URL or GCS path to audio file
            config: AssemblyAI-specific configuration
            user_id: User ID for saving raw transcript data to GCS (optional)
            job_id: Job ID for saving raw transcript data to GCS (optional)
            user_input_text: User's input text from the editor (optional)
            language_code: Language code for language-specific file naming (optional)

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
            # if audio_url.startswith('https://storage.googleapis.com/') and 'X-Goog-Algorithm' in audio_url:
            #     logger.info("Checking if signed URL is expired", url=audio_url[:100] + "...")
            #     try:
            #         # Refresh URL if expired (24 hour expiration for new URL)
            #         refreshed_url = await ensure_valid_signed_url(audio_url, expiration_minutes=1440)
            #         if refreshed_url != audio_url:
            #             logger.info("Using refreshed signed URL for AssemblyAI",
            #                       old_url=audio_url[:100] + "...",
            #                       new_url=refreshed_url[:100] + "...")
            #             audio_url = refreshed_url
            #         else:
            #             logger.debug("Signed URL is still valid, proceeding with original")
            #     except Exception as e:
            #         logger.warning("Failed to refresh signed URL, proceeding with original",
            #                      error=str(e), url=audio_url[:100] + "...")
            #         # Continue with original URL - let AssemblyAI handle the error

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
                    
                    logger.info("AssemblyAI transcription job submitted", 
                              transcript_id=transcript_id,
                              audio_url=audio_url)
            
            # Poll for completion
            result_data = await self._poll_for_completion(
                transcript_id,
                headers,
                user_id=user_id,
                job_id=job_id,
                user_input_text=user_input_text,
                language_code=language_code
            )

            # Check if polling returned valid data
            if result_data is None:
                logger.error("Poll for completion returned None")
                raise TranscriptionServiceError("AssemblyAI polling returned invalid response")

            # Try to get sentences from AssemblyAI sentences endpoint first
            logger.info("Attempting to fetch sentences from AssemblyAI API")
            transcript, segments = await self._get_sentences_from_assemblyai(transcript_id, headers)

            # If sentence extraction failed, fall back to word-based processing
            if transcript is None or segments is None:
                logger.info("Sentence extraction failed, falling back to word-based segmentation")
                transcript, segments = self._process_assemblyai_response(result_data)
            else:
                logger.info(f"Successfully using sentence-based segmentation with {len(segments)} sentences")
            
            # Generate subtitle files
            #srt_content = self._generate_srt_content(segments)
            srt_content = ''

            # Debug logging for Chinese character verification
            if segments:
                sample_text = segments[0].get('text', '')
                logger.info(f'Sample Chinese text (raw): {repr(sample_text)}')
                logger.info(f'Sample Chinese text (display): {sample_text}')
                logger.info(f'Sample Chinese text type: {type(sample_text)}')

                if sample_text:
                    logger.info(f'Contains Chinese chars: {any("\u4e00" <= char <= "\u9fff" for char in sample_text)}')
                    logger.info(f'Contains escape sequences: {"\\u" in sample_text}')
                else:
                    logger.warning('Sample text is empty')

            logger.info(f'Processed segments count: {len(segments)}')
            logger.info(f'SRT content length: {len(srt_content) if srt_content else 0}')
            
            # Check if advanced styling is requested
            caption_style = config.get('caption_style')
            use_advanced_styling = caption_style in ['karaoke', 'word_by_word', 'sentence']
            
            #comme out
            # if use_advanced_styling and segments:
            #     # Use advanced caption service for styled ASS
            #     ass_content = await self._generate_advanced_ass_content(
            #         segments, 
            #         caption_style, 
            #         config
            #     )
            # else:
            #     # Use basic ASS generation
            #     ass_content = self._generate_ass_content(segments)
            
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
                # srt_content=srt_content,
                # ass_content=ass_content,
                srt_content='',
                ass_content='',
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
    
    async def _poll_for_completion(
        self,
        transcript_id: str,
        headers: Dict[str, str],
        max_wait_time: int = 600,
        poll_interval: int = 5,
        save_raw_data: bool = True,
        user_id: str = None,
        job_id: str = None,
        user_input_text: str = None,
        language_code: str = None
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
            user_input_text: User's original input text from editor (optional)
            language_code: Language code for language-specific file naming (optional)

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
                    

                    try:
                        # Parse the JSON from the text
                        result = json.loads(response_text)

                        # Debug: Check what we get from the parsed JSON
                        if 'text' in result and result['text'] is not None:
                            raw_text = result['text']
                           
                        else:
                            logger.info(f"Raw text from JSON: {repr(result.get('text', 'KEY_NOT_FOUND'))}")
                            if 'status' in result:
                                logger.info(f"Status: {result['status']} - transcription in progress")

                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON response: {e}")
                        logger.error(f"Response text: {response_text[:200]}...")
                        raise TranscriptionServiceError(f"Invalid JSON response from AssemblyAI: {e}")

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
                        if 'text' in result:
                            text_field = result['text']
                            logger.info(f'Raw text field type: {type(text_field)}')
                            logger.info(f'Raw text field repr: {repr(text_field[:100])}')
                            logger.info(f'Raw text field display: {text_field[:100]}')

                            # Try to fix the encoding issue
                            try:
                                # If it's garbled, it might be UTF-8 decoded as latin-1
                                if isinstance(text_field, str) and any(ord(c) > 127 for c in text_field):
                                    # Try to re-encode as latin-1 then decode as utf-8
                                    fixed_text = text_field.encode('latin-1').decode('utf-8')
                                    logger.info(f'Fixed text: {fixed_text[:100]}')
                                    result['text'] = fixed_text

                                    # Also fix the words array
                                    if 'words' in result and result['words']:
                                        for word in result['words']:
                                            if 'text' in word and isinstance(word['text'], str):
                                                try:
                                                    word['text'] = word['text'].encode('latin-1').decode('utf-8')
                                                except:
                                                    pass  # Keep original if fixing fails

                            except Exception as e:
                                logger.warning(f'Failed to fix text encoding: {e}')

                        # comment out the transcript correction as it takes lots of time
                        # Correct transcription with Gemini before saving
                        # if user_input_text and user_input_text.strip():
                        #     try:
                        #         logger.info("Correcting transcription with Gemini AI...")
                        #         result = await self._correct_transcription_with_gemini(result, user_input_text)
                        #         logger.info("Transcription correction completed")
                        #     except Exception as e:
                        #         logger.error(f"Failed to correct transcription with Gemini: {e}")
                        #         # Continue with uncorrected result

                        if save_raw_data and user_id and job_id:
                            try:
                                # Create a combined object with transcript result and user input text
                                raw_data_object = {
                                    **result,  # Include all AssemblyAI response data
                                    "user_input_text": user_input_text  # Add user's input text from editor
                                }
                                # Convert the raw response to pretty-printed JSON
                                raw_data_json = json.dumps(raw_data_object, indent=2, ensure_ascii=False)
                                logger.info('Saving raw data to GCS...')

                                # Create language-specific filename
                                filename = f"raw_transcript_data_{language_code}.txt" if language_code else "raw_transcript_data.txt"
                                logger.info(f"💾 Saving transcript with language-specific filename: {filename}")

                                # Upload to GCS in the same location as other transcript files
                                raw_data_url = await self.gcs_service.upload_content(
                                    raw_data_json,
                                    user_id,
                                    job_id,
                                    filename,
                                    "output"
                                )

                                logger.info("Raw transcript data saved to GCS",
                                          url=raw_data_url,
                                          transcript_id=transcript_id,
                                          filename=filename,
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
            # Check if response_data is None
            if response_data is None:
                logger.error("AssemblyAI response data is None")
                return "", []

            # Get the raw transcript text and fix encoding issues
            raw_transcript = response_data.get('text', '')
            logger.info(f'Raw transcript type: {type(raw_transcript)}, value: {repr(raw_transcript)}')

            if raw_transcript is None:
                logger.warning("Raw transcript is None, using empty string")
                raw_transcript = ''

            #transcript = self._fix_text_encoding(raw_transcript)
            transcript=raw_transcript
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
                    # word_text = self._fix_text_encoding(raw_word_text)
                    word_text = raw_word_text
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

    async def _get_sentences_from_assemblyai(
        self,
        transcript_id: str,
        headers: Dict[str, str]
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Get sentence-level segments from AssemblyAI's sentences endpoint

        Args:
            transcript_id: AssemblyAI transcript ID
            headers: HTTP headers for API requests

        Returns:
            Tuple of (full_transcript, segments_list) where segments are sentences
        """
        try:
            logger.info("Fetching sentences from AssemblyAI", transcript_id=transcript_id)

            # Get sentences from AssemblyAI sentences endpoint
            sentences_url = f"{self.transcript_url}/{transcript_id}/sentences"

            async with aiohttp.ClientSession() as session:
                async with session.get(sentences_url, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error("AssemblyAI sentences fetch failed",
                                   status=response.status,
                                   error_text=error_text)
                        # Fallback to regular response if sentences endpoint fails
                        logger.warning("Falling back to word-based segmentation")
                        return None, None

                    sentences_data = await response.json()

            # Process sentences into segments
            sentences = sentences_data.get('sentences', [])

            if not sentences:
                logger.warning("No sentences found in AssemblyAI response")
                return None, None

            # Build full transcript from sentences
            transcript = ' '.join(sentence.get('text', '') for sentence in sentences)

            # Convert sentences to segment format
            segments = []
            for sentence in sentences:
                segment = {
                    'start': sentence.get('start', 0) / 1000,  # Convert ms to seconds
                    'end': sentence.get('end', 0) / 1000,
                    'text': sentence.get('text', ''),
                    'confidence': sentence.get('confidence', 1.0)
                }
                segments.append(segment)

            logger.info(f"Successfully extracted {len(segments)} sentences from AssemblyAI",
                       transcript_id=transcript_id,
                       sentence_count=len(segments))

            return transcript, segments

        except Exception as e:
            logger.error("Failed to get sentences from AssemblyAI",
                       transcript_id=transcript_id,
                       error=str(e))
            # Return None to indicate failure, caller should fallback
            return None, None

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
                            logger.info(f"SUCCESS: Decoded with regex: '{decoded_text[:50]}...'")
                            return decoded_text
                        else:
                            logger.debug("Regex method didn't change the text")
                    except Exception as e:
                        logger.debug(f"Method 2 (regex) failed: {e}")

                    # Method 3: Try with encode/decode approach
                    try:
                        # First encode as latin1 to preserve the literal backslashes, then decode
                        decoded_text = text.encode('latin1').decode('unicode_escape')
                        logger.info(f"SUCCESS: Decoded with latin1/unicode_escape: '{decoded_text[:50]}...'")
                        return decoded_text
                    except Exception as e:
                        logger.debug(f"Method 3 failed: {e}")

                    # Method 4: Try using literal_eval for JSON-like strings
                    try:
                        import ast
                        # Wrap in quotes to make it a valid Python string literal
                        wrapped_text = f'"{text}"'
                        decoded_text = ast.literal_eval(wrapped_text)
                        logger.info(f"SUCCESS: Decoded with ast.literal_eval: '{decoded_text[:50]}...'")
                        return decoded_text
                    except Exception as e:
                        logger.debug(f"Method 4 (ast.literal_eval) failed: {e}")

                    logger.warning(f"All Unicode decoding methods failed for text: {text[:100]}...")
                else:
                    logger.debug("No Unicode escape sequences found in text")

                # Check if text already contains Chinese characters
                if any('\u4e00' <= char <= '\u9fff' for char in text):
                    logger.info("Text already contains proper Chinese characters")
                    return text

                # Try to handle improperly encoded strings
                try:
                    # If it's a string that was improperly decoded, encode it back and decode correctly
                    encoded_bytes = text.encode('latin1')  # Use latin1 to preserve all bytes

                    # Try different decodings
                    for encoding in ['utf-8', 'utf-16', 'gb2312', 'gbk', 'big5']:
                        try:
                            decoded_text = encoded_bytes.decode(encoding)
                            # Check if the decoded text looks reasonable (contains Chinese characters)
                            if any('\u4e00' <= char <= '\u9fff' for char in decoded_text):
                                #logger.info(f"Successfully decoded text using {encoding}")
                                return decoded_text
                        except (UnicodeDecodeError, UnicodeError):
                            continue

                    # If no encoding worked, try direct UTF-8 decode
                    return encoded_bytes.decode('utf-8', errors='ignore')

                except (UnicodeEncodeError, UnicodeDecodeError):
                    # If encoding/decoding fails, fall back to original text
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

    async def _correct_transcription_with_gemini(self, result: Dict[str, Any], user_input_text: str) -> Dict[str, Any]:
        """
        Correct/revise transcription words using Gemini AI based on user input text context

        Args:
            result: Raw transcription result from AssemblyAI containing 'words' array
            user_input_text: User's input text that should be more accurate than transcription

        Returns:
            Corrected result with revised text in 'words' array
        """
        try:
            from google.genai import types
            from services.google_genai_client import create_google_genai_api_client

            logger.info("Starting Gemini transcription correction")

            # Check if we have words to correct
            if 'words' not in result or not result['words']:
                logger.warning("No words array found in result, skipping correction")
                return result

            if not user_input_text or not user_input_text.strip():
                logger.warning("No user input text provided, skipping correction")
                return result

            # Initialize Gemini client
            google_api_key = self.settings.google_api_key
            if not google_api_key:
                logger.error("GOOGLE_API_KEY not found, skipping correction")
                return result

            client = create_google_genai_api_client(google_api_key)
            model = "gemini-flash-latest"

            # Build the system prompt
            system_prompt = """You are an expert transcription corrector. The 'text' data from 'words' key is a result from a transcription model, which is known to be inaccurate for non-english languages. The text data from 'user_input_text' is directly from user input, which should be more accurate.

Your task is to correct/revise the ['words']['text'] data with the given context from 'user_input_text'.

Instructions:
- Analyze the transcription words and the user input text
- Correct any inaccuracies in the word-level transcription based on the user input
- Maintain the same JSON structure with timing information
- Only modify the 'text' field in each word object
- Preserve all other fields (start, end, confidence, etc.)
- Return ONLY a valid JSON object with the corrected words array
- Do not add any explanations or comments outside the JSON"""

            # Prepare the data for correction
            words_data = result['words']

            # Build user prompt with both transcription and user input
            user_prompt = f"""Original transcription words:
{json.dumps(words_data, ensure_ascii=False, indent=2)}

User input text (more accurate reference):
{user_input_text}

Please correct the 'text' field in each word object based on the user input text context. Return the corrected words array as valid JSON."""

            logger.info(f"Sending {len(words_data)} words to Gemini for correction")

            # Call Gemini API (wrapped in asyncio.to_thread to avoid blocking the event loop)
            # This allows the worker to handle other requests while waiting for Gemini API
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json"
                ),
                contents=user_prompt
            )

            logger.info("Received response from Gemini API")

            # Parse the corrected words
            corrected_text = response.text.strip()

            # Try to parse JSON from the response
            try:
                corrected_data = json.loads(corrected_text)

                # Handle different possible response structures
                if isinstance(corrected_data, dict) and 'words' in corrected_data:
                    corrected_words = corrected_data['words']
                elif isinstance(corrected_data, list):
                    corrected_words = corrected_data
                else:
                    logger.error(f"Unexpected response structure: {type(corrected_data)}")
                    return result

                # Validate that we got the same number of words
                if len(corrected_words) != len(words_data):
                    logger.warning(f"Word count mismatch: original={len(words_data)}, corrected={len(corrected_words)}")
                    # Still use it but log warning

                # Update the result with corrected words
                result['words'] = corrected_words

                # Also update the main 'text' field by joining corrected words
                result['text'] = ' '.join(word.get('text', '') for word in corrected_words if word.get('text'))

                logger.info(f"Successfully corrected {len(corrected_words)} words using Gemini")

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Gemini response as JSON: {e}")
                logger.error(f"Response text: {corrected_text[:500]}")
                # Return original result if parsing fails
                return result

            return result

        except Exception as e:
            logger.error(f"Error during Gemini correction: {str(e)}")
            logger.exception("Full traceback:")
            # Return original result if correction fails
            return result

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
            from .caption_service import CaptionService
            from models.caption_models import WordSegment, CaptionSettings, SubtitleStyle
            
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
            caption_service = CaptionService()

            # Get ASS header
            ass_header = caption_service.get_ass_header(settings)

            # Generate events based on style
            if settings.subtitle_style == SubtitleStyle.KARAOKE:
                events = caption_service.generate_karaoke_style(word_segments)
            elif settings.subtitle_style == SubtitleStyle.WORD_BY_WORD:
                events = caption_service.generate_word_by_word_style(word_segments)
            elif settings.subtitle_style == SubtitleStyle.SENTENCE:
                events = caption_service.generate_sentence_style(word_segments)
            else:
                events = caption_service.generate_karaoke_style(word_segments)

            # Combine header and events
            ass_content = ass_header + '\n'.join(events)

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




class FasterWhisperTranscriptionService(BaseTranscriptionService):
    """
    Local transcription via faster-whisper (https://github.com/SYSTRAN/faster-whisper).

    Default for Vyravid local — no cloud download of audio required.
    Saves raw_transcript_data_{lang}.txt in AssemblyAI-compatible shape
    (word times in milliseconds) for scene generation.
    """

    def __init__(self, model_size: str = None, device: str = None, compute_type: str = None):
        super().__init__()
        # large-v3 is the most accurate default for local Vyravid
        self.model_size = model_size or os.getenv("FASTER_WHISPER_MODEL", "large-v3")
        self.device = device or os.getenv("FASTER_WHISPER_DEVICE", "cpu")
        # float16 is ideal on GPU; int8 is safer on CPU for large models
        default_compute = "float16" if (device or os.getenv("FASTER_WHISPER_DEVICE", "cpu")) == "cuda" else "int8"
        self.compute_type = compute_type or os.getenv("FASTER_WHISPER_COMPUTE", default_compute)
        self._model = None

    def get_service_name(self) -> str:
        return "faster-whisper"

    def estimate_cost(self, duration_seconds: float) -> float:
        return 0.0

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            logger.info(
                "Loading faster-whisper model",
                model=self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            logger.info("faster-whisper model ready")

    def _transcribe_sync(self, audio_path: str) -> Dict[str, Any]:
        self._load_model()
        segments_iter, info = self._model.transcribe(
            audio_path,
            word_timestamps=True,
            vad_filter=True,
        )
        words = []
        full_parts = []
        segments_out = []
        for seg in segments_iter:
            text = (seg.text or "").strip()
            if text:
                full_parts.append(text)
            segments_out.append({
                "text": text,
                "start": int(seg.start * 1000),
                "end": int(seg.end * 1000),
            })
            if getattr(seg, "words", None):
                for w in seg.words:
                    wtext = (w.word or "").strip()
                    if not wtext:
                        continue
                    words.append({
                        "text": wtext,
                        "start": int(w.start * 1000),
                        "end": int(w.end * 1000),
                        "confidence": float(getattr(w, "probability", 0.0) or 0.0),
                    })
        return {
            "text": " ".join(full_parts).strip(),
            "words": words,
            "segments": segments_out,
            "language_code": getattr(info, "language", None),
            "language_confidence": getattr(info, "language_probability", None),
            "status": "completed",
            "service": "faster-whisper",
            "model": self.model_size,
        }

    async def transcribe_audio(
        self,
        audio_url: str,
        config: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        job_id: Optional[str] = None,
        user_input_text: Optional[str] = None,
        language_code: Optional[str] = None,
    ) -> TranscriptionResult:
        start_time = time.time()
        temp_path = None
        try:
            temp_path = await self._download_audio_file(audio_url)
            loop = asyncio.get_event_loop()
            result_data = await loop.run_in_executor(None, self._transcribe_sync, temp_path)

            if user_id and job_id:
                try:
                    raw_data_object = {
                        **result_data,
                        "user_input_text": user_input_text,
                    }
                    raw_data_json = json.dumps(raw_data_object, indent=2, ensure_ascii=False)
                    filename = (
                        f"raw_transcript_data_{language_code}.txt"
                        if language_code
                        else "raw_transcript_data.txt"
                    )
                    raw_url = await self.gcs_service.upload_content(
                        raw_data_json,
                        str(user_id),
                        str(job_id),
                        filename,
                        "output",
                    )
                    logger.info(
                        "Raw transcript saved (faster-whisper)",
                        url=raw_url,
                        filename=filename,
                        words=len(result_data.get("words") or []),
                    )
                except Exception as e:
                    logger.error("Failed to save raw transcript data", error=str(e))
                    raise

            processing_time = time.time() - start_time
            # Minimal SRT for interface compatibility
            srt_lines = []
            for i, w in enumerate(result_data.get("words") or [], 1):
                # group-less single-word lines as fallback
                pass
            srt_content = self._words_to_srt(result_data.get("words") or [])

            return TranscriptionResult(
                transcript=result_data.get("text") or "",
                srt_content=srt_content,
                ass_content=None,
                cost=0.0,
                processing_time=processing_time,
                service_name="faster-whisper",
                metadata={
                    "language": result_data.get("language_code"),
                    "word_count": len(result_data.get("words") or []),
                    "model": self.model_size,
                },
            )
        except TranscriptionServiceError:
            raise
        except Exception as e:
            logger.error("faster-whisper transcription failed", error=str(e))
            raise TranscriptionServiceError(f"faster-whisper failed: {e}") from e
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    @staticmethod
    def _words_to_srt(words: List[Dict[str, Any]]) -> str:
        if not words:
            return ""
        # Group into ~0.8s chunks for readable SRT
        chunks = []
        cur = []
        cur_start = None
        for w in words:
            if cur_start is None:
                cur_start = w["start"]
            cur.append(w["text"])
            if w["end"] - cur_start >= 800 or w is words[-1]:
                chunks.append((cur_start, w["end"], " ".join(cur)))
                cur = []
                cur_start = None
        def fmt(ms: int) -> str:
            h = ms // 3600000
            m = (ms % 3600000) // 60000
            s = (ms % 60000) // 1000
            x = ms % 1000
            return f"{h:02d}:{m:02d}:{s:02d},{x:03d}"
        lines = []
        for i, (start, end, text) in enumerate(chunks, 1):
            lines.append(str(i))
            lines.append(f"{fmt(int(start))} --> {fmt(int(end))}")
            lines.append(text)
            lines.append("")
        return "\n".join(lines)


class TranscriptionServiceSelector:
    """Service selector for choosing appropriate transcription service"""
    
    def __init__(self):
        self.services = {
            'faster-whisper': FasterWhisperTranscriptionService(),
            'whisper': FasterWhisperTranscriptionService(),  # alias
        }
        # Local Vyravid default: faster-whisper (no cloud audio fetch)
        self.default_service = os.getenv("TRANSCRIPTION_SERVICE", "faster-whisper")
    
    def get_service(self, service_name: Optional[str] = None) -> BaseTranscriptionService:
        """
        Get transcription service by name
        
        Args:
            service_name: Name of service ('faster-whisper' or 'whisper') or None for default
            
        Returns:
            BaseTranscriptionService instance
            
        Raises:
            TranscriptionServiceError: If service not found
        """
        if service_name is None:
            service_name = self.default_service
        # Map legacy names
        if service_name in ("local", "whisper-local"):
            service_name = "faster-whisper"
            
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
        job_id: Optional[str] = None,
        user_input_text: Optional[str] = None,
        language_code: Optional[str] = None
    ) -> TranscriptionResult:
        """
        Transcribe audio using specified service

        Args:
            audio_url: URL or local media path to audio file
            service_name: Name of transcription service
            config: Service-specific configuration
            user_id: User ID for saving raw transcript
            job_id: Project/job ID for saving raw transcript
            user_input_text: Optional editor text
            language_code: Language code for file naming

        Returns:
            TranscriptionResult
        """
        if service_name is None:
            service_name = self.default_service
        service = self.get_service(service_name)

        import inspect
        sig = inspect.signature(service.transcribe_audio)
        kwargs = {}
        if 'user_id' in sig.parameters:
            kwargs['user_id'] = user_id
        if 'job_id' in sig.parameters:
            kwargs['job_id'] = job_id
        if 'user_input_text' in sig.parameters:
            kwargs['user_input_text'] = user_input_text
        if 'language_code' in sig.parameters:
            kwargs['language_code'] = language_code

        if kwargs:
            return await service.transcribe_audio(audio_url, config, **kwargs)
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
