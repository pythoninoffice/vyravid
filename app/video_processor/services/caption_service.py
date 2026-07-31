"""
Caption service for Cloud Video Processor

This module provides caption generation and subtitle formatting services
for the cloud video processing pipeline. It handles different subtitle styles
and formats (SRT, ASS) with proper timing and styling.
"""

import asyncio
import os
import re
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import structlog
from video_processor.models.caption_models import (
    WordSegment,
    CaptionSettings,
    SubtitleStyle,
    CaptionGenerationRequest,
    CaptionGenerationResult
)
from video_processor.services.gcs_service import get_gcs_service, GCSError

logger = structlog.get_logger(__name__)


class CaptionError(Exception):
    """Base exception for caption operations"""
    pass


class CaptionGenerationError(CaptionError):
    """Exception raised when caption generation fails"""
    pass


class CloudCaptionService:
    """
    Cloud-based caption service for generating styled subtitles
    
    Provides caption generation with multiple styles (karaoke, word-by-word, sentence)
    and formats (SRT, ASS) with proper timing and styling support.
    """
    
    def __init__(self):
        self.gcs_service = get_gcs_service()
        
        # Font mappings for common font files
        self._font_mappings = {
            "LuckiestGuy-Regular.ttf": "Luckiest Guy",
            "PermanentMarker-Regular.ttf": "Permanent Marker", 
            "Poppins-BoldItalic.ttf": "Poppins Bold Italic",
            "Arial-Bold.ttf": "Arial Bold",
            "Times-Roman.ttf": "Times New Roman",
            "Helvetica.ttf": "Helvetica",
            "Impact.ttf": "Impact",
            "Roboto-Regular.ttf": "Roboto",
            "OpenSans-Regular.ttf": "Open Sans"
        }
    def _get_font_name_from_path(self, font_path: str) -> str:
        """Extract font family name from TTF file path"""
        if not font_path:
            return "Arial"
        
        font_filename = Path(font_path).name
        
        # Check if we have a mapping for this font
        if font_filename in self._font_mappings:
            return self._font_mappings[font_filename]
        
        # Otherwise, try to extract from filename
        # Remove extension and common suffixes
        font_name = Path(font_path).stem
        font_name = font_name.replace("-Regular", "").replace("-Bold", " Bold").replace("-Italic", " Italic")
        
        # Handle camelCase font names (like PermanentMarker -> Permanent Marker)
        import re
        font_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', font_name)
        
        font_name = font_name.replace("_", " ").replace("-", " ")
        
        return font_name.title() if font_name else "Arial"
    
    def _get_aspect_ratio_from_video_parameters(self, video_parameters: Optional[Dict[str, Any]]) -> Optional[float]:
        """
        Extract aspect ratio from video parameters
        
        Args:
            video_parameters: Video processing parameters that may contain resolution
            
        Returns:
            Aspect ratio as width/height, or None if not available
        """
        if not video_parameters:
            return None
        
        resolution = video_parameters.get('resolution')
        if not resolution:
            return None
        
        try:
            # Parse resolution string like "1920x1080" or "1280x720"
            if 'x' in str(resolution):
                width_str, height_str = str(resolution).split('x', 1)
                width = int(width_str.strip())
                height = int(height_str.strip())
                
                if height > 0:
                    aspect_ratio = width / height
                    logger.debug("Calculated aspect ratio from resolution", 
                               resolution=resolution, width=width, height=height, aspect_ratio=aspect_ratio)
                    return aspect_ratio
        except (ValueError, AttributeError) as e:
            logger.warning("Failed to parse resolution for aspect ratio", resolution=resolution, error=str(e))
        
        return None
    
    def _format_srt_time(self, seconds: float) -> str:
        """Format time for SRT subtitle format (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
    
    def _format_ass_time(self, seconds: float) -> str:
        """Format time for ASS subtitle format (H:MM:SS.CC)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:05.2f}"
    
    def _get_ass_header(self, settings: CaptionSettings) -> str:
        """
        Generate ASS subtitle header with styles
        
        Args:
            settings: Caption styling settings
            
        Returns:
            ASS header string with style definitions
        """
        # Determine alignment and margins based on position
        # Get aspect ratio to adjust margins accordingly
        aspect_ratio = self._get_aspect_ratio_from_video_parameters(settings.video_parameters)
        is_landscape = aspect_ratio and abs(aspect_ratio - (16/9)) < 0.1  # 16:9 aspect ratio

        if settings.position == "top":
            alignment = 8  # Top center
            margin_v = 20  # Top margin
        elif settings.position == "middle":
            alignment = 5  # Middle center
            margin_v = 0   # No vertical margin, positive number means down from center, vice versa for negative
        else:  # bottom (default)
            alignment = 2  # Bottom center
            # For 16:9 landscape, use smaller margin; for 9:16 portrait, keep existing margin
            margin_v = 50 if is_landscape else 200
        
        # Determine font name - use font_file_path if provided, otherwise use font_family
        if settings.font_file_path and Path(settings.font_file_path).exists():
            font_name = self._get_font_name_from_path(settings.font_file_path)
            logger.info("Using custom font", font_name=font_name, font_path=settings.font_file_path)
        else:
            font_name = settings.font_family
            logger.info("Using font family", font_name=font_name)
        
        # Determine ScaleX value based on background type and aspect ratio
        # For background videos, use 100 for proper text scaling
        # For image-based generation, check aspect ratio: 16:9 uses 100, 9:16 uses 50, others use 300
        if settings.background_type == "video":
            scale_x = 100
            logger.info("Using ScaleX=100 for video background", background_type=settings.background_type)
        else:
            # For image-based backgrounds, check aspect ratio
            aspect_ratio = self._get_aspect_ratio_from_video_parameters(settings.video_parameters)
            if aspect_ratio and abs(aspect_ratio - (16/9)) < 0.1:  # 16:9 aspect ratio (with tolerance)
                scale_x = 100
                logger.info("Using ScaleX=100 for 16:9 image background", background_type=settings.background_type, aspect_ratio=aspect_ratio)
            elif aspect_ratio and abs(aspect_ratio - (9/16)) < 0.1:  # 9:16 aspect ratio (with tolerance)
                scale_x = 100
                logger.info("Using ScaleX=50 for 9:16 image background", background_type=settings.background_type, aspect_ratio=aspect_ratio)
            else:
                scale_x = 300
                logger.info("Using ScaleX=300 for other aspect ratio image background", background_type=settings.background_type, aspect_ratio=aspect_ratio)
        
        return f"""[Script Info]
Title: Animated Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{settings.font_size},{settings.default_color},&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,{scale_x},100,4,0,1,4,3,{alignment},50,50,{margin_v},1
Style: Highlight,{font_name},{settings.font_size},{settings.highlight_color},&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,{scale_x},100,4,0,1,4,3,{alignment},50,50,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    def _generate_srt_content(self, word_segments: List[WordSegment], settings: CaptionSettings) -> str:
        """
        Generate SRT subtitle content from word segments

        Args:
            word_segments: List of word timing data
            settings: Caption styling settings

        Returns:
            SRT formatted subtitle content
        """
        srt_lines = []
        subtitle_index = 1

        if settings.subtitle_style == SubtitleStyle.WORD_BY_WORD:
            # Each word gets its own subtitle
            for word_data in word_segments:
                start_time = self._format_srt_time(word_data.start)
                end_time = self._format_srt_time(word_data.end)

                srt_lines.extend([
                    str(subtitle_index),
                    f"{start_time} --> {end_time}",
                    word_data.word,
                    ""
                ])
                subtitle_index += 1

        else:
            # Group words into sentences for karaoke and sentence styles
            current_sentence = []
            sentence_start = None

            # Determine max words per sentence based on aspect ratio
            aspect_ratio = self._get_aspect_ratio_from_video_parameters(settings.video_parameters)
            if aspect_ratio and abs(aspect_ratio - (9/16)) < 0.1:  # 9:16 aspect ratio
                max_words_per_sentence = 5  # Shorter sentences for vertical videos
            else:
                max_words_per_sentence = 8  # Default for other aspect ratios

            for i, word_data in enumerate(word_segments):
                if sentence_start is None:
                    sentence_start = word_data.start

                current_sentence.append(word_data)

                # End sentence on punctuation or max words limit
                is_sentence_end = (
                    word_data.word.endswith(('.', '!', '?', ',', ';', ':')) or
                    len(current_sentence) >= max_words_per_sentence or
                    i == len(word_segments) - 1
                )
                
                if is_sentence_end and len(current_sentence) > 0:
                    full_text = ' '.join([w.word for w in current_sentence])
                    sentence_end = word_data.end + 0.5  # Add buffer
                    
                    start_time = self._format_srt_time(sentence_start)
                    end_time = self._format_srt_time(sentence_end)
                    
                    srt_lines.extend([
                        str(subtitle_index),
                        f"{start_time} --> {end_time}",
                        full_text,
                        ""
                    ])
                    
                    subtitle_index += 1
                    current_sentence = []
                    sentence_start = None
        
        return "\n".join(srt_lines)
    
    def _generate_karaoke_style(self, word_segments: List[WordSegment], settings: CaptionSettings) -> List[str]:
        """Generate karaoke-style ASS subtitles where words are highlighted as spoken"""
        events = []

        # Group words into sentences for better display
        current_sentence = []
        sentence_start = None

        # Determine max words per sentence based on aspect ratio
        aspect_ratio = self._get_aspect_ratio_from_video_parameters(settings.video_parameters)
        if aspect_ratio and abs(aspect_ratio - (9/16)) < 0.1:  # 9:16 aspect ratio
            max_words_per_sentence = 5  # Shorter sentences for vertical videos
        else:
            max_words_per_sentence = 8  # Default for other aspect ratios

        for i, word_data in enumerate(word_segments):
            if sentence_start is None:
                sentence_start = word_data.start

            current_sentence.append(word_data)

            # End sentence on punctuation or max words limit
            is_sentence_end = (
                word_data.word.endswith(('.', '!', '?', ',', ';', ':')) or
                len(current_sentence) >= max_words_per_sentence or
                i == len(word_segments) - 1
            )
            
            if is_sentence_end and len(current_sentence) > 0:
                # For each word's time window, create a custom event that shows the
                # entire sentence but with only the current word highlighted
                for j, word in enumerate(current_sentence):
                    # Build the sentence with just the current word highlighted
                    parts = []
                    for k, w in enumerate(current_sentence):
                        # Remove trailing punctuation for consistent positioning
                        word_cleaned = w.word.rstrip('.,!?;:')

                        if k == j:
                            # Only this word is highlighted
                            parts.append(f"{{\\c&H00FFFF&}}{word_cleaned}{{\\c&HFFFFFF&}}")
                        else:
                            # All other words are default color
                            parts.append(word_cleaned)

                    # Join with spaces based on whether any word in sentence contains English characters
                    has_english = any(re.search(r'[a-zA-Z]', w.word) for w in current_sentence)
                    if has_english:
                        text_line = ' '.join(parts)
                    else:
                        # For non-English characters, join without spaces
                        text_line = ''.join(parts)
                    #text_line = ' '.join(parts)

                    # Set timing for just this word
                    start_time = self._format_ass_time(word.start)
                    end_time = self._format_ass_time(word.end)

                    # Add this frame to the events list
                    events.append(f"Dialogue: 0,{start_time},{end_time},Default,,,,,,{text_line}")
                
                # Reset for next sentence
                current_sentence = []
                sentence_start = None
        
        return events
    
    def _generate_word_by_word_style(self, word_segments: List[WordSegment]) -> List[str]:
        """Generate word-by-word ASS subtitles where only the current word is shown"""
        events = []

        for word_data in word_segments:
            # Show only the current word, remove trailing punctuation
            text_line = word_data.word.rstrip('.,!?;:')

            # Set timing for this word
            start_time = self._format_ass_time(word_data.start)
            end_time = self._format_ass_time(word_data.end)

            # Add this word to the events list
            events.append(f"Dialogue: 0,{start_time},{end_time},Highlight,,,,,,{text_line}")

        return events
    
    def _generate_sentence_style(self, word_segments: List[WordSegment], settings: CaptionSettings) -> List[str]:
        """Generate sentence-style ASS subtitles where full sentences are shown"""
        events = []

        # Group words into sentences
        current_sentence = []
        sentence_start = None

        # Determine max words per sentence based on aspect ratio
        aspect_ratio = self._get_aspect_ratio_from_video_parameters(settings.video_parameters)
        if aspect_ratio and abs(aspect_ratio - (9/16)) < 0.1:  # 9:16 aspect ratio
            max_words_per_sentence = 5  # Shorter sentences for vertical videos
        else:
            max_words_per_sentence = 8  # Default for other aspect ratios

        for i, word_data in enumerate(word_segments):
            if sentence_start is None:
                sentence_start = word_data.start

            current_sentence.append(word_data)

            # End sentence on punctuation or max words limit
            is_sentence_end = (
                word_data.word.endswith(('.', '!', '?', ',', ';', ':')) or
                len(current_sentence) >= max_words_per_sentence or
                i == len(word_segments) - 1
            )
            
            if is_sentence_end and len(current_sentence) > 0:
                # Create the full sentence text and strip punctuation
                words_in_sentence = [w.word for w in current_sentence]

                # Remove trailing punctuation from each word for consistent vertical positioning
                words_cleaned = []
                for word in words_in_sentence:
                    # Strip trailing punctuation (. ! ? , ; :)
                    cleaned_word = word.rstrip('.,!?;:')
                    if cleaned_word:  # Only add if word is not empty after stripping
                        words_cleaned.append(cleaned_word)

                # Check if any word contains English characters to determine spacing
                has_english = any(re.search(r'[a-zA-Z]', word) for word in words_cleaned)

                if has_english:
                    full_text = ' '.join(words_cleaned)
                else:
                    # For non-English characters, join without spaces
                    full_text = ''.join(words_cleaned)


                # Set timing for the entire sentence
                sentence_end = word_data.end + 0.01  # Add a small buffer
                start_time = self._format_ass_time(sentence_start)
                end_time = self._format_ass_time(sentence_end)

                # Use absolute positioning for pixel-perfect consistency
                # \an2 = bottom center alignment, \pos(540,880) = center horizontally, 880px from top
                # PlayResX=1080, PlayResY=1080, so 880 is ~18.5% from bottom (200px margin)
                full_text_with_pos = f"{{\\an2\\pos(540,1000)}}{full_text}"
                events.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{full_text_with_pos}")
                
                # Reset for next sentence
                current_sentence = []
                sentence_start = None
        
        return events
    
    def _generate_ass_content(self, word_segments: List[WordSegment], settings: CaptionSettings) -> str:
        """
        Generate ASS subtitle content from word segments
        
        Args:
            word_segments: List of word timing data
            settings: Caption styling settings
            
        Returns:
            ASS formatted subtitle content
        """
        # Get ASS header
        ass_header = self._get_ass_header(settings)
        
        # Generate events based on selected style
        if settings.subtitle_style == SubtitleStyle.KARAOKE:
            events = self._generate_karaoke_style(word_segments, settings)
            logger.info("Generated karaoke-style subtitles", style="karaoke")
        elif settings.subtitle_style == SubtitleStyle.WORD_BY_WORD:
            events = self._generate_word_by_word_style(word_segments)
            logger.info("Generated word-by-word subtitles", style="word_by_word")
        elif settings.subtitle_style == SubtitleStyle.SENTENCE:
            events = self._generate_sentence_style(word_segments, settings)
            logger.info("Generated sentence-style subtitles", style="sentence")
        else:
            logger.warning("Unknown subtitle style, using karaoke", style=settings.subtitle_style)
            events = self._generate_karaoke_style(word_segments, settings)
        
        return ass_header + '\n'.join(events)
    

    async def generate_captions(self, request: CaptionGenerationRequest) -> CaptionGenerationResult:
        """
        Generate caption files from word segments
        
        Args:
            request: Caption generation request with word segments and settings
            
        Returns:
            CaptionGenerationResult with generated content and file URLs
            
        Raises:
            CaptionGenerationError: If caption generation fails
        """
        try:
            job_id = request.job_id
            word_segments = request.word_segments
            settings = request.settings
            
            logger.info(
                "Starting caption generation",
                job_id=job_id,
                word_count=len(word_segments),
                style=settings.subtitle_style.value
            )
            
            if not word_segments:
                raise CaptionGenerationError("No word segments provided for caption generation")
            
            # Calculate duration
            duration = max(word.end for word in word_segments) if word_segments else 0.0
            
            # Generate SRT content
            srt_content = self._generate_srt_content(word_segments, settings)
            
            # Generate ASS content
            ass_content = self._generate_ass_content(word_segments, settings)
            
            # Prepare filenames
            base_filename = request.output_filename or f"captions_{job_id}"
            srt_filename = f"{base_filename}-{settings.subtitle_style.value}.{request.language}.srt"
            ass_filename = f"{base_filename}-{settings.subtitle_style.value}.{request.language}.ass"
            
            # Upload files to GCS
            srt_file_url = None
            ass_file_url = None
            
            if request.user_id is not None:
                try:
                    # Upload SRT file
                    srt_file_url = await self.gcs_service.upload_content(
                        srt_content,
                        request.user_id,
                        job_id,
                        srt_filename,
                        "output",
                        "text/plain"
                    )
                    
                    # Upload ASS file
                    ass_file_url = await self.gcs_service.upload_content(
                        ass_content,
                        request.user_id,
                        job_id,
                        ass_filename,
                        "output",
                        "text/plain"
                    )
                    
                    logger.info(
                        "Caption files uploaded to GCS",
                        job_id=job_id,
                        srt_url=srt_file_url,
                        ass_url=ass_file_url
                    )
                    
                except GCSError as e:
                    logger.warning("Failed to upload caption files to GCS", error=str(e))
                    # Continue without GCS upload - files are still generated
            
            result = CaptionGenerationResult(
                job_id=job_id,
                srt_content=srt_content,
                ass_content=ass_content,
                srt_file_url=srt_file_url,
                ass_file_url=ass_file_url,
                word_count=len(word_segments),
                duration=duration,
                style_used=settings.subtitle_style
            )
            
            logger.info(
                "Caption generation completed",
                job_id=job_id,
                word_count=len(word_segments),
                duration=duration,
                style=settings.subtitle_style.value
            )
            
            return result
            
        except Exception as e:
            logger.error("Caption generation failed", job_id=request.job_id, error=str(e))
            raise CaptionGenerationError(f"Failed to generate captions: {e}")
    
    async def generate_caption_files_to_disk(
        self,
        word_segments: List[WordSegment],
        settings: CaptionSettings,
        output_path: str,
        language: str = "en"
    ) -> Tuple[str, str]:
        """
        Generate caption files and save to local disk
        
        Args:
            word_segments: List of word timing data
            settings: Caption styling settings
            output_path: Base path for output files (without extension)
            language: Language code for filename
            
        Returns:
            Tuple of (srt_file_path, ass_file_path)
            
        Raises:
            CaptionGenerationError: If file generation fails
        """
        try:
            # Generate content
            srt_content = self._generate_srt_content(word_segments, settings)
            ass_content = self._generate_ass_content(word_segments, settings)
            
            # Create filenames
            srt_file = f"{output_path}-{settings.subtitle_style.value}.{language}.srt"
            ass_file = f"{output_path}-{settings.subtitle_style.value}.{language}.ass"
            
            # Ensure output directory exists
            os.makedirs(os.path.dirname(srt_file), exist_ok=True)
            
            # Write SRT file
            with open(srt_file, 'w', encoding='utf-8') as f:
                f.write(srt_content)
            
            # Write ASS file
            with open(ass_file, 'w', encoding='utf-8') as f:
                f.write(ass_content)
            
            logger.info(
                "Caption files written to disk",
                srt_file=srt_file,
                ass_file=ass_file,
                word_count=len(word_segments)
            )
            
            return srt_file, ass_file
            
        except Exception as e:
            logger.error("Failed to write caption files to disk", error=str(e))
            raise CaptionGenerationError(f"Failed to write caption files: {e}")


# Singleton instance
_caption_service = None


def get_caption_service() -> CloudCaptionService:
    """Get singleton caption service instance"""
    global _caption_service
    if _caption_service is None:
        _caption_service = CloudCaptionService()
    return _caption_service