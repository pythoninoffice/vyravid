import math
from typing import List, Dict, Any
from pathlib import Path
import logging

from models.story_models import WordSegment, CaptionSettings, SubtitleStyle

logger = logging.getLogger(__name__)

class CaptionService:
    """Service for generating different styles of captions/subtitles"""
    
    def __init__(self):
        pass
    
    def _get_font_name_from_path(self, font_path: str) -> str:
        """Extract font family name from TTF file path"""
        if not font_path:
            return "Arial"
        
        # Common font file name to family name mappings
        font_mappings = {
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
        
        font_filename = Path(font_path).name
        
        # Check if we have a mapping for this font
        if font_filename in font_mappings:
            return font_mappings[font_filename]
        
        # Otherwise, try to extract from filename
        # Remove extension and common suffixes
        font_name = Path(font_path).stem
        font_name = font_name.replace("-Regular", "").replace("-Bold", " Bold").replace("-Italic", " Italic")
        
        # Handle camelCase font names (like PermanentMarker -> Permanent Marker)
        import re
        font_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', font_name)
        
        font_name = font_name.replace("_", " ").replace("-", " ")
        
        return font_name
    
    def format_ass_time(self, seconds: float) -> str:
        """Format time for ASS subtitle format (H:MM:SS.CC)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:05.2f}"
    
    def get_ass_header(self, settings: CaptionSettings) -> str:
        """Generate ASS subtitle header with styles"""
        # Determine alignment and margins based on position
        if settings.position == "top":
            alignment = 8  # Top center
            margin_v = 20  # Top margin
        elif settings.position == "middle":
            alignment = 5  # Middle center
            margin_v = 0   # No vertical margin
        else:  # bottom (default)
            alignment = 2  # Bottom center
            margin_v = 30  # Bottom margin
        
        # Determine font name - use font_file_path if provided, otherwise use font_family
        if settings.font_file_path and Path(settings.font_file_path).exists():
            font_name = self._get_font_name_from_path(settings.font_file_path)
            logger.info(f"Using custom font: {font_name} from {settings.font_file_path}")
        else:
            font_name = settings.font_family
            logger.info(f"Using font family: {font_name}")
        
        return f"""[Script Info]
Title: Animated Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{settings.font_size},{settings.default_color},&H000000FF,&H00000000,&H80000000,1,0,0,0,300,100,4,0,1,4,3,{alignment},50,50,{margin_v},1
Style: Highlight,{font_name},{settings.font_size},{settings.highlight_color},&H000000FF,&H00000000,&H80000000,1,0,0,0,300,100,4,0,1,4,3,{alignment},50,50,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    def generate_karaoke_style(self, word_segments: List[WordSegment]) -> List[str]:
        """Generate karaoke-style subtitles where words are highlighted as spoken"""
        events = []
        
        # Group words into sentences for better display
        current_sentence = []
        sentence_start = None
        
        for i, word_data in enumerate(word_segments):
            if sentence_start is None:
                sentence_start = word_data.start
            
            current_sentence.append(word_data)
            
            # End sentence on punctuation or every 8-10 words
            is_sentence_end = (
                word_data.word.endswith(('.', '!', '?', ',', ';', ':')) or 
                len(current_sentence) >= 8 or 
                i == len(word_segments) - 1
            )
            
            if is_sentence_end and len(current_sentence) > 0:
                # For each word's time window, create a custom event that shows the 
                # entire sentence but with only the current word highlighted
                for j, word in enumerate(current_sentence):
                    # Build the sentence with just the current word highlighted
                    parts = []
                    for k, w in enumerate(current_sentence):
                        if k == j:
                            # Only this word is highlighted
                            parts.append(f"{{\\c&H00FFFF&}}{w.word}{{\\c&HFFFFFF&}}")
                        else:
                            # All other words are default color
                            parts.append(w.word)
                    
                    # Join with spaces
                    text_line = ' '.join(parts)
                    
                    # Set timing for just this word
                    start_time = self.format_ass_time(word.start)
                    end_time = self.format_ass_time(word.end)
                    
                    # Add this frame to the events list
                    events.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text_line}")
                
                # Reset for next sentence
                current_sentence = []
                sentence_start = None
        
        return events
    
    def generate_word_by_word_style(self, word_segments: List[WordSegment]) -> List[str]:
        """Generate word-by-word subtitles where only the current word is shown"""
        events = []
        
        for word_data in word_segments:
            # Show only the current word
            text_line = word_data.word
            
            # Set timing for this word
            start_time = self.format_ass_time(word_data.start)
            end_time = self.format_ass_time(word_data.end)
            
            # Add this word to the events list
            events.append(f"Dialogue: 0,{start_time},{end_time},Highlight,,0,0,0,,{text_line}")
        
        return events
    
    def generate_sentence_style(self, word_segments: List[WordSegment]) -> List[str]:
        """Generate sentence-style subtitles where full sentences are shown"""
        events = []
        
        # Group words into sentences
        current_sentence = []
        sentence_start = None
        
        for i, word_data in enumerate(word_segments):
            if sentence_start is None:
                sentence_start = word_data.start
            
            current_sentence.append(word_data)
            
            # End sentence on punctuation or every 8-10 words
            is_sentence_end = (
                word_data.word.endswith(('.', '!', '?', ',', ';', ':')) or 
                len(current_sentence) >= 8 or 
                i == len(word_segments) - 1
            )
            
            if is_sentence_end and len(current_sentence) > 0:
                # Create the full sentence text
                full_text = ' '.join([w.word for w in current_sentence])
                
                # Set timing for the entire sentence
                sentence_end = word_data.end + 0.5  # Add a small buffer
                start_time = self.format_ass_time(sentence_start)
                end_time = self.format_ass_time(sentence_end)
                
                # Add this sentence to the events list
                events.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{full_text}")
                
                # Reset for next sentence
                current_sentence = []
                sentence_start = None
        
        return events
    
    def generate_animated_subtitle_file(
        self, 
        word_segments: List[WordSegment], 
        settings: CaptionSettings,
        output_path: str,
        language: str = "en"
    ) -> str:
        """Generate animated subtitle file based on selected style"""
        
        # Create filename with style suffix
        subtitle_file = f"{output_path}-{settings.subtitle_style.value}.{language}.ass"
        
        # Get ASS header
        ass_header = self.get_ass_header(settings)
        
        # Generate events based on selected style
        if settings.subtitle_style == SubtitleStyle.KARAOKE:
            events = self.generate_karaoke_style(word_segments)
            logger.info(f"Generated karaoke-style subtitles (words highlighted as spoken)")
        elif settings.subtitle_style == SubtitleStyle.WORD_BY_WORD:
            events = self.generate_word_by_word_style(word_segments)
            logger.info(f"Generated word-by-word subtitles (only current word shown)")
        elif settings.subtitle_style == SubtitleStyle.SENTENCE:
            events = self.generate_sentence_style(word_segments)
            logger.info(f"Generated sentence-style subtitles (full sentences shown)")
        else:
            logger.warning(f"Unknown subtitle style '{settings.subtitle_style}', using karaoke style")
            events = self.generate_karaoke_style(word_segments)
        
        # Write ASS file
        with open(subtitle_file, 'w', encoding='utf-8') as f:
            f.write(ass_header)
            f.write('\n'.join(events))
        
        logger.info(f"Generated subtitle file: {subtitle_file}")
        return subtitle_file