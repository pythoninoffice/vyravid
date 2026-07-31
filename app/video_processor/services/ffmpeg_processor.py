"""
FFmpeg video processing operations for Cloud Video Processor

This module provides cloud-optimized FFmpeg operations including video combining,
audio-video synchronization, video splitting, and subtitle burning capabilities.
Adapted from the existing video processing service for cloud environment.
"""

import asyncio
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse

import ffmpeg
import structlog
from google.api_core import exceptions as gcs_exceptions
import math
try:
    import cv2
except ImportError:
    cv2 = None
try:
    import cairo
except ImportError:
    cairo = None
try:
    import numpy as np
except ImportError:
    np = None
try:
    from moviepy.editor import VideoClip
except ImportError:
    from moviepy import VideoClip

from video_processor.config.settings import get_settings
from video_processor.services.greenscreen_effects import resolve_greenscreen_effect_path
from video_processor.services.gcs_service import get_gcs_service, GCSError
from video_processor.services.upscale_service import normalize_upscale_mode, upscale_image

logger = structlog.get_logger(__name__)


class FFmpegProcessingError(Exception):
    """Base exception for FFmpeg processing operations"""
    pass


class VideoProcessingError(FFmpegProcessingError):
    """Exception raised when video processing fails"""
    pass


class AudioVideoSyncError(FFmpegProcessingError):
    """Exception raised when audio-video sync fails"""
    pass


class VideoSplitError(FFmpegProcessingError):
    """Exception raised when video splitting fails"""
    pass


class SubtitleBurnError(FFmpegProcessingError):
    """Exception raised when subtitle burning fails"""
    pass


class FFmpegProcessor:
    """
    Cloud-optimized FFmpeg video processing operations.
    
    Provides video combining, audio-video synchronization, video splitting,
    and subtitle burning with GCS integration and cloud-specific optimizations.
    Includes template video system for background video processing.
    """
    
    def __init__(self, language_code: str = None):
        self.settings = get_settings()
        self.gcs_service = get_gcs_service()
        self.language_code = language_code  # Store language code for multi-language video support

        # Create temporary directory for processing
        self.temp_dir = Path(self.settings.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up custom fonts directory (relative to project root)
        project_root = Path(__file__).parent.parent  # Go up from services/ to project root
        self.fonts_dir = project_root / "fonts"
        self.available_fonts = self._scan_available_fonts()
        
        # Initialize template cache
        self._template_cache = {}
        
        # Processing limits for Cloud Run
        self.max_processing_time = self.settings.max_processing_time_minutes * 60  # Convert to seconds
        self.max_file_size = self.settings.max_file_size_mb * 1024 * 1024  # Convert to bytes
        
        # Template video configuration
        self.template_videos_bucket = getattr(self.settings, 'template_videos_bucket', 'cloud-video-templates')
        self.template_videos_prefix = getattr(self.settings, 'template_videos_prefix', 'background_videos/')
        
        # Log environment diagnostics
        # self._log_environment_info()

    def _get_storyboard_upscale_mode(self, options: Optional[Dict[str, Any]]) -> str:
        """Return the requested storyboard image upscale mode, if any."""
        if not options:
            return "none"
        return normalize_upscale_mode(
            options.get("upscale_mode")
            or options.get("upscale")
            or options.get("image_upscale_mode")
            or options.get("resolution_label")
        )

    async def _upscale_storyboard_image_if_requested(
        self,
        image_path: str,
        job_id: str,
        image_index: int,
        options: Optional[Dict[str, Any]],
    ) -> str:
        """Pre-upscale a downloaded storyboard image before video/camera filters."""
        mode = self._get_storyboard_upscale_mode(options)
        if mode == "none":
            return image_path

        output_path = self.temp_dir / f"upscaled_{job_id}_{image_index:03d}.png"
        logger.info(
            "Pre-upscaling storyboard image",
            job_id=job_id,
            image_index=image_index,
            mode=mode,
            input_path=str(image_path),
            output_path=str(output_path),
        )
        return await asyncio.to_thread(
            upscale_image,
            str(image_path),
            str(output_path),
            mode,
            2,
        )

    def _is_video_segment(self, media_url: str) -> bool:
        """
        Detect if a media URL points to a video based on file extension

        Args:
            media_url: URL or path to media file

        Returns:
            True if video file (.mp4), False if image file
        """
        from urllib.parse import urlparse, unquote

        # Parse URL to remove query parameters
        parsed = urlparse(media_url)
        # Get path and decode any URL encoding
        path = unquote(parsed.path)

        # Check if path contains .mp4 extension
        return path.lower().endswith('.mp4') or '.mp4' in path.lower()

    async def _create_single_segment_video(
        self,
        segment: Dict[str, Any],
        duration: float,
        user_id: str,
        job_id: str,
        options: Dict[str, Any]
    ) -> str:
        """
        Create video from a single timeline segment (image or video)

        Args:
            segment: Timeline segment with media_url, start_time, end_time
            duration: Total video duration in seconds
            user_id: User ID for GCS path organization
            job_id: Job ID for GCS path organization
            options: Video processing configuration

        Returns:
            GCS URL of created video

        Raises:
            VideoProcessingError: If video creation fails
        """
        try:
            media_url = segment.get('image_url')
            if not media_url:
                raise ValueError("Segment must have image_url")

            # Detect media type
            is_video = self._is_video_segment(media_url)
            media_type = "video" if is_video else "image"

            logger.info(f"Creating single segment video from {media_type}", job_id=job_id, media_url=media_url)

            # Download media
            media_path = await self._download_media_file(media_url, media_type)
            if not is_video:
                media_path = await self._upscale_storyboard_image_if_requested(
                    media_path,
                    job_id,
                    0,
                    options,
                )

            # Parse resolution
            width, height = map(int, options['resolution'].split('x'))
            fps = options.get('fps', 25)

            # Create output path
            output_path = self.temp_dir / f"single_segment_{job_id}.mp4"

            if is_video:
                # VIDEO PROCESSING
                logger.info("Processing single video segment")

                # Get actual video duration
                video_duration = await self._get_duration(str(media_path))
                logger.info(f"Video duration: {video_duration:.2f}s, needed: {duration:.2f}s")

                # Create input stream without audio
                input_stream = ffmpeg.input(str(media_path))
                video_stream = input_stream.video  # Strip audio

                # Handle duration mismatch
                if video_duration < duration:
                    # Loop video
                    import math
                    loops_needed = math.ceil(duration / video_duration)
                    logger.info(f"Looping video {loops_needed} times to fill duration")

                    video_stream = video_stream.filter('loop', loop=loops_needed-1, size=32767)
                    video_stream = video_stream.filter('trim', duration=duration)
                    video_stream = video_stream.filter('setpts', 'PTS-STARTPTS')
                else:
                    # Trim to duration
                    video_stream = video_stream.filter('trim', duration=duration)
                    video_stream = video_stream.filter('setpts', 'PTS-STARTPTS')

                # Scale to target resolution
                processed_stream = ffmpeg.filter(video_stream, 'scale', width, height)

            else:
                # IMAGE PROCESSING
                logger.info("Processing single image segment")

                # Create input stream
                input_stream = ffmpeg.input(str(media_path), loop=1, t=duration, r=fps)

                # Scale preserving aspect ratio, pad to target resolution with black bars
                processed_stream = ffmpeg.filter(
                    ffmpeg.filter(input_stream, 'scale', width, height, force_original_aspect_ratio='decrease'),
                    'pad', width, height, '(ow-iw)/2', '(oh-ih)/2', color='black'
                )

            # Encode video
            output = ffmpeg.output(
                processed_stream,
                str(output_path),
                vcodec=options.get('video_codec', 'libx264'),
                pix_fmt=options.get('pix_fmt', 'yuv420p'),
                r=fps,
                preset=options.get('preset', 'ultrafast'),
                crf=options.get('crf', 23)
            )

            # Run FFmpeg
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._run_ffmpeg_with_logging,
                output
            )

            if not output_path.exists():
                raise VideoProcessingError("Single segment video creation failed - output not created")

            # Upload to GCS
            from video_processor.services.gcs_service import get_gcs_service
            gcs_service = get_gcs_service()

            video_url = await gcs_service.upload_file(
                str(output_path),
                user_id,
                job_id,
                f"single_segment_{job_id}.mp4",
                "output"
            )

            logger.info(f"Single segment video created successfully", job_id=job_id, media_type=media_type)
            return video_url

        except Exception as e:
            logger.error(f"Single segment video creation failed: {e}", job_id=job_id)
            raise VideoProcessingError(f"Single segment video creation failed: {e}")

    def _scan_available_fonts(self) -> Dict[str, str]:
        """
        Scan the fonts directory and create a mapping of font names to file paths
        
        Returns:
            Dict mapping font names to absolute font file paths
        """
        fonts = {}
        
        if not self.fonts_dir.exists():
            logger.warning(f"Fonts directory not found: {self.fonts_dir}")
            return fonts
        
        # Common font file extensions
        font_extensions = {'.ttf', '.otf', '.woff', '.woff2'}
        
        try:
            for font_file in self.fonts_dir.iterdir():
                if font_file.is_file() and font_file.suffix.lower() in font_extensions:
                    # Extract font name from filename (remove extension and clean up)
                    font_name = font_file.stem
                    
                    # Clean up common naming patterns
                    font_name = font_name.replace('-Regular', '').replace('-Bold', ' Bold')
                    font_name = font_name.replace('-Italic', ' Italic').replace('-BoldItalic', ' Bold Italic')
                    
                    # Convert CamelCase to spaced names
                    import re
                    font_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', font_name)
                    
                    fonts[font_name] = str(font_file.absolute())
                    
            logger.info(f"Found {len(fonts)} custom fonts", fonts=list(fonts.keys()))
            return fonts
            
        except Exception as e:
            logger.error(f"Error scanning fonts directory: {e}")
            return fonts
    
    def get_font_path(self, font_name: str) -> Optional[str]:
        """
        Get the absolute path to a font file by name
        
        Args:
            font_name: Name of the font (e.g., "Luckiest Guy", "Permanent Marker")
            
        Returns:
            Absolute path to font file or None if not found
        """
        return self.available_fonts.get(font_name)
    
    def list_available_fonts(self) -> List[str]:
        """
        Get list of available custom font names
        
        Returns:
            List of font names
        """
        return list(self.available_fonts.keys())
    
    def _should_use_center_crop(self, aspect_ratio: str) -> bool:
        """
        Determine if center crop should be used for the given aspect ratio
        
        Center crop is particularly useful for vertical formats like 9:16 (TikTok/Shorts)
        where we want to fill the entire frame rather than letterbox
        
        Args:
            aspect_ratio: Aspect ratio string like "9:16", "16:9", "1:1"
            
        Returns:
            bool: True if center crop should be used
        """
        if not aspect_ratio or ':' not in aspect_ratio:
            return False
        
        try:
            width_ratio, height_ratio = aspect_ratio.split(':')
            width_ratio, height_ratio = int(width_ratio), int(height_ratio)
            
            # Validate that both ratios are positive
            if width_ratio <= 0 or height_ratio <= 0:
                logger.warning(f"Invalid aspect ratio with zero/negative values: {aspect_ratio}, defaulting to scale-to-fit")
                return False
            
            # Use center crop for vertical formats (height > width)
            # This is especially important for 9:16 videos where we want to 
            # crop the middle section rather than letterbox
            if height_ratio > width_ratio:
                logger.info(f"Using center crop for vertical aspect ratio: {aspect_ratio}")
                return True
            
            # Could also enable for square formats if desired
            # if width_ratio == height_ratio:
            #     return True
            
            return False
            
        except (ValueError, ZeroDivisionError):
            logger.warning(f"Invalid aspect ratio format: {aspect_ratio}, defaulting to scale-to-fit")
            return False

    def _get_greenscreen_chroma_key_color(self, greenscreen_url: str) -> str:
        """
        Determine the chroma key color based on greenscreen filename

        Args:
            greenscreen_url: URL or path to greenscreen file

        Returns:
            Hex color code for chroma keying ('000000' for black, '00FF00' for green)
        """
        # Extract filename from URL
        from urllib.parse import urlparse, unquote
        parsed = urlparse(greenscreen_url)
        path = unquote(parsed.path)
        filename = path.split('/')[-1].lower()

        # Files with black background
        black_background_files = [
            'fire1_v.mp4', 'fire1_h.mp4', 'fire2_v.mp4', 'fire2_h.mp4',
            'pink_particle_v', 'pink_particle_h', 'rain1_v', 'rain1_h',
            'stars_v', 'stars_h', 'thunder_v', 'thunder_h', 'old_film_black_v', 'old_film_black_h'
        ]

        # Files with green background
        green_background_files = [
            'electric_v', 'electric_h', 'speed_v', 'speed_h',
            'white_particle_v', 'white_particle_h'
        ]

        # Files with white background
        white_background_files = [
            'old_film_white_v', 'old_film_white_h'
        ]

        # Check if filename matches any black background pattern
        for black_file in black_background_files:
            if black_file in filename:
                logger.info(f"Using black chroma key for {filename}")
                return '000000'  # Black

        # Check if filename matches any green background pattern
        for green_file in green_background_files:
            if green_file in filename:
                logger.info(f"Using green chroma key for {filename}")
                return '00FF00'  # Green

        # Check if filename matches any white background pattern
        for white_file in white_background_files:
            if white_file in filename:
                logger.info(f"Using white chroma key for {filename}")
                return 'FFFFFF'  # White

        # Default to black if no match found
        logger.warning(f"Unknown greenscreen file {filename}, defaulting to black chroma key")
        return '000000'

    def _convert_greenscreen_effect_name_to_url(self, effect_name_or_url: str) -> str:
        """
        Convert greenscreen effect name to a local file path if needed.

        Args:
            effect_name_or_url: Either an effect name (e.g., 'fire1_v') or a full URL

        Returns:
            Local file path to the greenscreen effect file
        """
        local_path = resolve_greenscreen_effect_path(effect_name_or_url)
        logger.info("Resolved greenscreen effect to local file",
                    effect_name=effect_name_or_url,
                    local_path=local_path)
        return local_path

    async def check_ffmpeg_availability(self) -> bool:
        """
        Check if FFmpeg is available and working
        
        Returns:
            bool: True if FFmpeg is available
        """
        try:
            process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-version',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                version_info = stdout.decode()
                # Extract just the version line for clear display
                version_lines = version_info.split('\n')
                ffmpeg_version_line = version_lines[0] if version_lines else "Unknown version"
                logger.info("FFmpeg availability check passed", ffmpeg_version=ffmpeg_version_line)
                logger.info("Full FFmpeg version info", version_info=version_info[:500])
                
                # Also check codec availability  
                try:
                    codec_process = await asyncio.create_subprocess_exec(
                        'ffmpeg', '-codecs',
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    codec_stdout, codec_stderr = await codec_process.communicate()
                    if codec_process.returncode == 0:
                        codecs = codec_stdout.decode()
                        has_h264 = "h264" in codecs.lower()
                        has_aac = "aac" in codecs.lower() 
                        has_mp3 = "mp3" in codecs.lower()
                        logger.info("FFmpeg codecs checked", 
                                   has_h264=has_h264, has_aac=has_aac, has_mp3=has_mp3)
                except Exception as codec_error:
                    logger.warning("Could not check FFmpeg codecs", error=str(codec_error))
                
                return True
            else:
                logger.error("FFmpeg availability check failed", stderr=stderr.decode())
                return False
                
        except Exception as e:
            logger.error("FFmpeg availability check error", error=str(e))
            return False
    
    async def combine_videos(
        self,
        video_files: List,  # Can be List[str] or List[VideoFile] 
        audio_url: str,
        user_id: str,
        job_id: str,
        processing_options: Optional[Dict[str, Any]] = None,
        use_templates_as_fallback: bool = True,
        audio_duration: Optional[float] = None,
        upload_result: bool = True,
        is_final_video: bool = False
    ) -> str:
        """
        Combine multiple video clips with audio track
        
        Args:
            video_urls: List of GCS URLs or HTTP URLs to video files
            audio_url: GCS URL or HTTP URL to audio file
            user_id: User ID for GCS path organization
            job_id: Job ID for GCS path organization
            processing_options: Video processing configuration
            
        Returns:
            GCS URL of combined video
            
        Raises:
            VideoProcessingError: If video combination fails
        """
        start_time = time.time()

        try:
            if not video_files:
                raise VideoProcessingError("Video files are required")

            # Convert video_files to consistent format and extract URLs and durations
            video_urls = []
            video_durations = {}

            for video_file in video_files:
                if isinstance(video_file, str):
                    # Legacy format: just URL string
                    video_urls.append(video_file)
                else:
                    # New format: VideoFile object with url and duration
                    video_urls.append(video_file.url)
                    if hasattr(video_file, 'duration') and video_file.duration:
                        video_durations[video_file.url] = video_file.duration
            
            # Default processing options
            options = {
                'resolution': '1280x720',
                'fps': 25,
                'video_codec': 'libx264',
                'audio_codec': 'aac',
                'preset': 'ultrafast',
                'threads': 0  # Use all available CPU cores
            }
            if processing_options:
                options.update(processing_options)
                
            # For video backgrounds, preserve original aspect ratio by not applying resolution scaling
            # The combine_videos function is used for video backgrounds, so we should preserve the original video dimensions
            preserve_video_aspect_ratio = True
            logger.info("Video background processing - will preserve original aspect ratio and resolution")
            
            # logger.info(
            #     "Processing video combination",
            #     video_count=len(video_urls),
            #     job_id=job_id,
            #     resolution=options['resolution'],
            #     provided_audio_duration=audio_duration,
            #     provided_video_durations=len(video_durations) if video_durations else 0
            # )
            
            # Get audio duration - use provided duration if available, otherwise probe
            # If no audio_url, we'll need to determine duration from videos instead
            if audio_url:
                if audio_duration is None:
                    audio_duration = await self._get_duration_from_url(audio_url)
                else:
                    logger.info("Using provided audio duration", duration=audio_duration)

                if audio_duration <= 0:
                    raise VideoProcessingError("Could not determine audio duration")

                # Download audio file for processing
                audio_path = await self._download_media_file(audio_url, "audio")
            else:
                # No audio - calculate duration from video durations
                logger.info("No audio URL provided - generating video without audio track")
                if audio_duration is None:
                    # Calculate total duration from videos
                    total_video_duration = 0
                    for video_url in video_urls:
                        if video_url in video_durations:
                            total_video_duration += video_durations[video_url]
                        else:
                            video_dur = await self._get_duration_from_url(video_url)
                            total_video_duration += video_dur
                            video_durations[video_url] = video_dur
                    audio_duration = total_video_duration if total_video_duration > 0 else 10.0  # Default to 10s if can't determine
                    logger.info("Calculated video duration from clips", total_duration=audio_duration)
                audio_path = None
            
            # Enhance video list with templates if needed
            enhanced_video_urls = await self._enhance_videos_with_templates(
                video_urls, audio_duration, use_templates_as_fallback, video_durations
            )
            
            # Process videos with cloud optimizations
            combined_video_path = await self._combine_videos_optimized(
                enhanced_video_urls, audio_duration, options, video_durations, preserve_video_aspect_ratio
            )
            
            # Combine video with audio (if audio is provided)
            output_path = self.temp_dir / f"final_video_{job_id}.mp4"

            if audio_path:
                # Combine video with audio
                # logger.info("About to combine video with audio",
                #            combined_video_path=combined_video_path,
                #            audio_path=audio_path,
                #            output_path=str(output_path))

                await self._combine_video_audio(combined_video_path, audio_path, output_path, options)
            else:
                # No audio - just use the combined video as final output
                logger.info("No audio to combine - using video-only output")
                import shutil
                shutil.copy2(combined_video_path, output_path)
            
            # Verify file was created
            file_exists = os.path.exists(output_path)
            # logger.info("Video-audio combination result", 
            #            output_path=str(output_path),
            #            file_exists=file_exists,
            #            file_size=os.path.getsize(output_path) if file_exists else 0)
            
            if not file_exists:
                raise FFmpegProcessingError(f"Video combination failed - output file not created: {output_path}")
            
            # Upload result to GCS (optional)
            if upload_result:
                if is_final_video:
                    # Use the new upload_final_video method for user-specific paths
                    result_url = await self.gcs_service.upload_final_video(
                        str(output_path),
                        str(user_id),  # Convert to string for user-specific path
                        job_id,
                        f"Combined Video {job_id}",  # Video title
                        language_code=self.language_code  # Pass language code for multi-language support
                    )
                else:
                    # Use regular upload for intermediate videos
                    result_url = await self.gcs_service.upload_file(
                        str(output_path),
                        user_id,
                        job_id,
                        f"combined_video_{job_id}.mp4",
                        "output"
                    )
            else:
                # Return local temp file path for further processing
                result_url = str(output_path)
            
            processing_time = time.time() - start_time
            # logger.info(
            #     "Video combination completed",
            #     job_id=job_id,
            #     result_url=result_url,
            #     processing_time=processing_time
            # )
            
            return result_url
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                "Video combination failed",
                job_id=job_id,
                error=str(e),
                processing_time=processing_time
            )
            raise VideoProcessingError(f"Video combination failed: {e}")
        
        finally:
            # Clean up temporary files (but preserve output if not uploaded)
            if upload_result:
                await self._cleanup_temp_files(job_id)
            else:
                # Only clean up input files, preserve output for further processing
                await self._cleanup_temp_files_except_output(job_id, str(output_path))
    
    async def sync_audio_video(
        self,
        video_url: str,
        audio_url: str,
        user_id: str,
        job_id: str,
        sync_options: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Synchronize audio with video
        
        Args:
            video_url: GCS URL or HTTP URL to video file
            audio_url: GCS URL or HTTP URL to audio file
            user_id: User ID for GCS path organization
            job_id: Job ID for GCS path organization
            sync_options: Audio/video sync configuration
            
        Returns:
            GCS URL of synchronized video
            
        Raises:
            AudioVideoSyncError: If synchronization fails
        """
        start_time = time.time()
        
        try:
            # Default sync options
            options = {
                'video_codec': 'libx264',
                'audio_codec': 'aac',
                'preset': 'ultrafast',
                'threads': 0,  # Use all available CPU cores
                'audio_offset': 0.0,  # Audio offset in seconds
                'sync_method': 'replace'  # 'replace' or 'mix'
            }
            if sync_options:
                options.update(sync_options)
            
            # logger.info(
            #     "Starting audio-video synchronization",
            #     video_url=video_url,
            #     audio_url=audio_url,
            #     job_id=job_id,
            #     options=options
            # )
            
            # Get durations directly from URLs (faster than temp files)
            video_duration = await self._get_duration_from_url(video_url)
            audio_duration = await self._get_duration_from_url(audio_url)
            
            # Download media files for processing
            video_path = await self._download_media_file(video_url, "video")
            audio_path = await self._download_media_file(audio_url, "audio")
            
            logger.info(
                "Media durations",
                video_duration=video_duration,
                audio_duration=audio_duration
            )
            
            # Perform synchronization
            output_path = self.temp_dir / f"synced_video_{job_id}.mp4"
            await self._sync_audio_video_ffmpeg(
                video_path, audio_path, output_path, options
            )
            
            # Upload result to GCS
            result_url = await self.gcs_service.upload_file(
                str(output_path),
                user_id,
                job_id,
                f"synced_video_{job_id}.mp4",
                "output"
            )
            
            processing_time = time.time() - start_time
            # logger.info(
            #     "Audio-video synchronization completed",
            #     job_id=job_id,
            #     result_url=result_url,
            #     processing_time=processing_time
            # )
            
            return result_url
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                "Audio-video synchronization failed",
                job_id=job_id,
                error=str(e),
                processing_time=processing_time
            )
            raise AudioVideoSyncError(f"Audio-video synchronization failed: {e}")
        
        finally:
            await self._cleanup_temp_files(job_id)
    
    async def split_video(
        self,
        video_url: str,
        segments: List[Dict[str, Any]],
        user_id: str,
        job_id: str,
        split_options: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        Split video into segments at specific timestamps
        
        Args:
            video_url: GCS URL or HTTP URL to video file
            segments: List of segment definitions with start_time, end_time, output_name
            user_id: User ID for GCS path organization
            job_id: Job ID for GCS path organization
            split_options: Video splitting configuration
            
        Returns:
            List of GCS URLs for split video segments
            
        Raises:
            VideoSplitError: If video splitting fails
        """
        start_time = time.time()
        
        try:
            if not segments:
                raise VideoSplitError("No segments specified for splitting")
            
            # Default split options
            options = {
                'video_codec': 'libx264',
                'audio_codec': 'aac',
                'preset': 'ultrafast',
                'threads': 0,  # Use all available CPU cores
                'copy_streams': False  # Set to True for faster processing without re-encoding
            }
            if split_options:
                options.update(split_options)
            
            # logger.info(
            #     "Starting video splitting",
            #     video_url=video_url,
            #     segment_count=len(segments),
            #     job_id=job_id,
            #     options=options
            # )
            
            # Get video duration directly from URL (faster than temp file)
            video_duration = await self._get_duration_from_url(video_url)
            
            # Download video file for processing
            video_path = await self._download_media_file(video_url, "video")
            
            # Validate segments
            validated_segments = self._validate_segments(segments, video_duration)
            
            # Split video into segments
            segment_urls = []
            for i, segment in enumerate(validated_segments):
                segment_path = await self._split_video_segment(
                    video_path, segment, i, job_id, options
                )
                
                # Upload segment to GCS
                segment_name = segment.get('output_name', f"segment_{i}_{job_id}.mp4")
                segment_url = await self.gcs_service.upload_file(
                    str(segment_path),
                    user_id,
                    job_id,
                    segment_name,
                    "output"
                )
                segment_urls.append(segment_url)
            
            processing_time = time.time() - start_time
            logger.info(
                "Video splitting completed",
                job_id=job_id,
                segment_count=len(segment_urls),
                processing_time=processing_time
            )
            
            return segment_urls
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                "Video splitting failed",
                job_id=job_id,
                error=str(e),
                processing_time=processing_time
            )
            raise VideoSplitError(f"Video splitting failed: {e}")
        
        finally:
            await self._cleanup_temp_files(job_id)
    
    async def burn_subtitles(
        self,
        video_url: str,
        subtitle_url: str,
        user_id: str,
        job_id: str,
        style_options: Optional[Dict[str, Any]] = None,
        upload_result: bool = True
    ) -> str:
        """
        Burn subtitles into video
        
        Args:
            video_url: GCS URL or HTTP URL to video file
            subtitle_url: GCS URL or HTTP URL to subtitle file (SRT format)
            user_id: User ID for GCS path organization
            job_id: Job ID for GCS path organization
            style_options: Subtitle styling configuration
            
        Returns:
            GCS URL of video with burned subtitles
            
        Raises:
            SubtitleBurnError: If subtitle burning fails
        """
        start_time = time.time()
        
        try:
            # Default style options
            options = {
                'font_name': 'Arial',
                'font_file': None,  # Path to custom font file
                'font_size': 24,
                'font_color': 'white',
                'outline_color': 'black',
                'outline_width': 2,
                'shadow_offset': 1,
                'alignment': 'bottom_center',
                'margin_v': 20,
                'video_codec': 'libx264',
                'audio_codec': 'copy',  # Copy audio without re-encoding
                'preset': 'ultrafast',
                'threads': 0  # Use all available CPU cores
            }
            
            # Debug and safely update style options
            if style_options:
                logger.info(
                    "Style options provided",
                    style_options=style_options,
                    style_options_type=type(style_options).__name__
                )
                
                if isinstance(style_options, dict):
                    options.update(style_options)
                    
                    # Handle custom font resolution
                    if 'font_name' in style_options and style_options['font_name']:
                        font_path = self.get_font_path(style_options['font_name'])
                        if font_path:
                            options['font_file'] = font_path
                            logger.info(f"Using custom font: {style_options['font_name']} -> {font_path}")
                        else:
                            logger.warning(f"Custom font not found: {style_options['font_name']}, available fonts: {self.list_available_fonts()}")
                else:
                    logger.warning(
                        "Invalid style_options type, expected dict",
                        provided_type=type(style_options).__name__,
                        provided_value=style_options
                    )
            
            logger.info(
                "Starting subtitle burning",
                video_url=video_url,
                subtitle_url=subtitle_url,
                job_id=job_id,
                options=options
            )
            
            # Download media files
            video_path = await self._download_media_file(video_url, "video")
            subtitle_path = await self._download_media_file(subtitle_url, "subtitle")
            
            # Validate subtitle format and content
            if not self._is_valid_subtitle_format(subtitle_path):
                raise SubtitleBurnError("Invalid subtitle format. Only SRT and ASS formats are supported.")
            
            # Log subtitle file info for debugging
            try:
                with open(subtitle_path, 'r', encoding='utf-8') as f:
                    subtitle_content = f.read()
                    
                logger.info(
                    "Subtitle file analysis",
                    subtitle_path=subtitle_path,
                    file_size=len(subtitle_content),
                    line_count=len(subtitle_content.splitlines()),
                    first_100_chars=subtitle_content[:100] if subtitle_content else "EMPTY",
                    is_ass_format="[V4+ Styles]" in subtitle_content,
                    is_srt_format=subtitle_content.strip().startswith(('1', '0')) and '-->' in subtitle_content
                )
            except Exception as content_error:
                logger.warning("Could not analyze subtitle content", error=str(content_error))
            
            # Burn subtitles into video
            output_path = self.temp_dir / f"subtitled_video_{job_id}.mp4"
            await self._burn_subtitles_ffmpeg(video_path, subtitle_path, output_path, options)
            
            # Upload result to GCS (optional)
            if upload_result:
                # Use the new upload_final_video method for user-specific paths
                result_url = await self.gcs_service.upload_final_video(
                    str(output_path),
                    str(user_id),  # Convert to string for user-specific path
                    job_id,
                    f"Subtitled Video {job_id}",  # Video title
                    language_code=self.language_code  # Pass language code for multi-language support
                )
            else:
                # Return local temp file path for further processing
                result_url = str(output_path)
            
            processing_time = time.time() - start_time
            logger.info(
                "Subtitle burning completed",
                job_id=job_id,
                result_url=result_url,
                processing_time=processing_time
            )
            
            return result_url
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                "Subtitle burning failed",
                job_id=job_id,
                error=str(e),
                processing_time=processing_time
            )
            raise SubtitleBurnError(f"Subtitle burning failed: {e}")
        
        finally:
            # Clean up temporary files (but preserve output if not uploaded)
            if upload_result:
                await self._cleanup_temp_files(job_id)
            else:
                # Only clean up input files, preserve output for further processing
                await self._cleanup_temp_files_except_output(job_id, str(output_path))
    
    async def _download_media_file(self, url: str, file_type: str) -> str:
        """
        Download media file from GCS or HTTP URL to temporary location
        
        Args:
            url: GCS URL or HTTP URL to media file
            file_type: Type of file for naming (video, audio, subtitle)
            
        Returns:
            Path to downloaded file
        """
        try:
            # Generate temporary file path
            file_extension = self._get_file_extension(url)
            temp_path = self.temp_dir / f"temp_{file_type}_{uuid.uuid4().hex}{file_extension}"
            
            # Special logging for music files with emoji
            if file_type == "music":
                logger.info("🎵 MUSIC: Processing music file download", 
                           url=url, 
                           file_type=file_type, 
                           temp_path=str(temp_path),
                           is_local_path=url.startswith('/'), 
                           file_exists=os.path.exists(url) if url.startswith('/') else False)
            else:
                logger.info("Processing media file", url=url, file_type=file_type, is_local_path=url.startswith('/'), file_exists=os.path.exists(url) if url.startswith('/') else False)
            
            # Check if this might be a greenscreen effect name and convert to URL
            if not url.startswith(('/', 'http://', 'https://', 'gs://')):
                # This looks like a greenscreen effect name - convert to full URL
                logger.info(f"Detected greenscreen effect name, converting to URL", effect_name=url)
                url = self._convert_greenscreen_effect_name_to_url(url)

            if url.startswith('/') and os.path.exists(url):
                # Local file path - return as-is
                logger.info("Using existing local file", local_path=url, file_type=file_type)
                return url
            elif url.startswith(('gs://', 'https://storage.googleapis.com/')):
                # Download from GCS
                await self.gcs_service.download_file(url, str(temp_path))
            elif url.startswith(('http://', 'https://')):
                parsed = urlparse(url)
                if parsed.path.startswith('/media/'):
                    # Local mode: resolve /media URLs through filesystem storage instead of localhost HTTP.
                    await self.gcs_service.download_file(url, str(temp_path))
                else:
                    # Download from HTTP URL
                    await self._download_http_file(url, str(temp_path))
            else:
                raise FFmpegProcessingError(f"Unsupported URL format: {url}")
            
            return str(temp_path)
            
        except Exception as e:
            logger.error("Failed to download media file", url=url, error=str(e))
            raise FFmpegProcessingError(f"Failed to download media file: {e}")
    
    async def _download_http_file(self, url: str, local_path: str):
        """Download file from HTTP URL"""
        import aiohttp
        import aiofiles
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise FFmpegProcessingError(f"HTTP download failed: {response.status}")
                
                async with aiofiles.open(local_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
    
    async def _get_duration(self, file_path: str) -> float:
        """
        Get duration of media file in seconds.

        For URLs, uses download-then-probe method to avoid FFmpeg HTTPS segmentation faults.
        For local files, probes directly.
        """
        # If it's a URL, use the download-then-probe method
        if file_path.startswith(('http', 'gs://', 'gcs://')):
            return await self._get_duration_from_url(file_path)

        # For local files, probe directly
        start_time = time.time()

        try:
            logger.info("Starting local file duration probe", file_path=file_path)

            loop = asyncio.get_event_loop()
            probe_start = time.time()

            # Add timeout for local file probe as well
            probe_task = loop.run_in_executor(None, ffmpeg.probe, file_path)
            try:
                probe = await asyncio.wait_for(probe_task, timeout=30.0)
            except asyncio.TimeoutError:
                logger.error("Local file probe timeout", file_path=file_path, timeout_seconds=30)
                return 0.0

            probe_time = time.time() - probe_start

            logger.info("Local file probe completed",
                       probe_time_seconds=round(probe_time, 2),
                       file_path=file_path)

            # Try to get duration from format first
            if 'format' in probe and 'duration' in probe['format']:
                duration = float(probe['format']['duration'])
                if duration > 0:
                    total_time = time.time() - start_time
                    logger.info("Duration extracted from format (local)",
                               duration=duration,
                               total_time_seconds=round(total_time, 2))
                    return duration

            # Fallback to stream duration
            for stream in probe['streams']:
                if 'duration' in stream:
                    duration = float(stream['duration'])
                    if duration > 0:
                        total_time = time.time() - start_time
                        logger.info("Duration extracted from stream (local)",
                                   duration=duration,
                                   total_time_seconds=round(total_time, 2))
                        return duration

            total_time = time.time() - start_time
            logger.warning("No valid duration found in local file probe result",
                          file_path=file_path,
                          total_time_seconds=round(total_time, 2))
            return 0.0

        except ffmpeg.Error as e:
            total_time = time.time() - start_time
            logger.error("FFmpeg error during local file probe",
                        file_path=file_path,
                        error=str(e),
                        stderr=e.stderr.decode() if e.stderr else None,
                        total_time_seconds=round(total_time, 2))
            return 0.0
        except Exception as e:
            total_time = time.time() - start_time
            logger.error("Unexpected error during local file duration probe",
                        file_path=file_path,
                        error=str(e),
                        error_type=type(e).__name__,
                        total_time_seconds=round(total_time, 2))
            return 0.0

    async def _get_duration_from_url(self, url: str, known_duration: Optional[float] = None) -> float:
        """
        Get duration using download-then-probe method for reliable GCS URL handling.

        This method works around FFmpeg static build HTTPS segmentation faults by downloading
        GCS files locally before probing them. For non-GCS URLs, it probes directly.

        Args:
            url: Media file URL (GCS or HTTP)
            known_duration: Pre-calculated duration to skip probing

        Returns:
            Duration in seconds, or 0.0 if unable to determine
        """
        start_time = time.time()
        temp_file = None

        # If duration is provided, use it directly
        if known_duration is not None and known_duration > 0:
            total_time = time.time() - start_time
            logger.info("Using provided duration",
                       url=url,
                       duration=known_duration,
                       total_time_seconds=round(total_time, 4))
            return known_duration

        try:
            logger.info("Starting duration probe with download-then-probe method", url=url)

            parsed_url = urlparse(url)
            is_local_media_url = parsed_url.path.startswith('/media/')

            # For GCS/local media URLs, use download-then-probe to avoid HTTP/protocol quirks.
            if url.startswith(('gs://', 'https://storage.googleapis.com/')) or is_local_media_url:
                logger.info("Downloading storage file for duration probe", url=url)
                temp_file = await self._download_media_file(url, "duration_probe")
                probe_target = temp_file
                logger.info("Using local file for probe", local_path=temp_file)
            else:
                # For non-GCS URLs, probe directly
                probe_target = url
                logger.info("Using direct URL for probe", url=url)

            # Probe with timeout to prevent hanging
            loop = asyncio.get_event_loop()
            probe_start = time.time()

            # Add timeout for ffmpeg.probe to prevent hanging
            probe_task = loop.run_in_executor(None, ffmpeg.probe, probe_target)
            try:
                probe = await asyncio.wait_for(probe_task, timeout=30.0)  # 30 second timeout
            except asyncio.TimeoutError:
                logger.error("FFmpeg probe timeout", url=url, timeout_seconds=30)
                return 0.0

            probe_time = time.time() - probe_start

            logger.info("Duration probe completed",
                       probe_time_seconds=round(probe_time, 2),
                       url=url)

            # Try to get duration from format first
            if 'format' in probe and 'duration' in probe['format']:
                duration = float(probe['format']['duration'])
                if duration > 0:
                    total_time = time.time() - start_time
                    logger.info("Duration extracted from format",
                               duration=duration,
                               total_time_seconds=round(total_time, 2))
                    return duration

            # Fallback to stream duration
            for stream in probe['streams']:
                if 'duration' in stream:
                    duration = float(stream['duration'])
                    if duration > 0:
                        total_time = time.time() - start_time
                        logger.info("Duration extracted from stream",
                                   duration=duration,
                                   total_time_seconds=round(total_time, 2))
                        return duration

            total_time = time.time() - start_time
            logger.warning("No valid duration found in probe result",
                          url=url,
                          total_time_seconds=round(total_time, 2))
            return 0.0

        except ffmpeg.Error as e:
            total_time = time.time() - start_time
            logger.error("FFmpeg probe error",
                        url=url,
                        error=str(e),
                        stderr=e.stderr.decode() if e.stderr else None,
                        total_time_seconds=round(total_time, 2))
            return 0.0
        except Exception as e:
            total_time = time.time() - start_time
            logger.error("Unexpected error during duration probe",
                        url=url,
                        error=str(e),
                        error_type=type(e).__name__,
                        total_time_seconds=round(total_time, 2))
            return 0.0

        finally:
            # Clean up temp file if we downloaded one
            if temp_file and temp_file != url:
                try:
                    import os
                    if os.path.exists(temp_file):
                        os.unlink(temp_file)
                        logger.debug("Cleaned up temp duration probe file", temp_file=temp_file)
                except Exception as cleanup_error:
                    logger.warning("Failed to cleanup temp duration probe file",
                                  temp_file=temp_file,
                                  error=str(cleanup_error))
    

    async def _combine_videos_optimized(
        self,
        video_urls: List[str],
        target_duration: float,
        options: Dict[str, Any],
        video_durations: Dict[str, float] = None,
        preserve_aspect_ratio: bool = False
    ) -> str:
        """
        Combine videos with cloud optimizations for bandwidth and processing time
        Enhanced with template video system and improved planning
        """
        try:
            # Analyze videos without downloading (for remote URLs)
            video_info = []
            for i, url in enumerate(video_urls):
                try:
                    # Use provided duration if available, otherwise probe
                    if video_durations and url in video_durations:
                        duration = video_durations[url]
                        logger.info(f"Video {i} using provided duration: {url}, duration: {duration:.2f}s")
                    else:
                        duration = await self._get_duration(url)
                        logger.info(f"Video {i} analyzed via probe: {url}, duration: {duration:.2f}s")
                    
                    if duration > 0:
                        video_info.append({
                            'url': url,
                            'duration': duration,
                            'index': i
                        })
                    else:
                        logger.warning(f"Could not determine duration for video {i}: {url}")
                except Exception as e:
                    logger.warning(f"Failed to analyze video {i} ({url}): {e}")
            
            if not video_info:
                raise VideoProcessingError("No valid videos found for processing")
            
            # Create optimized processing plan using migrated algorithm
            plan = self._create_optimized_video_plan(video_info, target_duration)
            
            if not plan:
                raise VideoProcessingError("Failed to create video processing plan")
            
            logger.info(f"Created optimized video plan with {len(plan)} segments")
            
            # Process videos according to plan with bandwidth optimization
            if len(plan) == 1:
                # Single segment - optimize for remote files
                logger.info("Processing single video segment", segment_info=plan[0])
                result = await self._process_single_optimized_video(plan[0], options, preserve_aspect_ratio)
                logger.info("Single video segment processing completed", output_path=result)
                return result
            else:
                # Multiple segments - process with concatenation
                logger.info(f"Processing {len(plan)} video segments with concatenation")
                result = await self._process_multiple_optimized_videos(plan, options, preserve_aspect_ratio)
                logger.info("Multiple video segments processing completed", output_path=result)
                return result
                
        except Exception as e:
            logger.error("Error in optimized video combination", error=str(e))
            raise VideoProcessingError(f"Optimized video combination failed: {e}")
    
    async def _process_single_optimized_video(self, segment: Dict, options: Dict, preserve_aspect_ratio: bool = False) -> str:
        """
        Process a single video segment with download-then-process for HTTPS safety
        """
        try:
            logger.info("Starting single video processing", segment_path=segment['path'],
                       segment_start=segment['start'], segment_duration=segment['duration'])

            output_path = self.temp_dir / f"single_optimized_{uuid.uuid4().hex}.mp4"
            width, height = map(int, options['resolution'].split('x'))

            # Always download remote files first to avoid FFmpeg HTTPS segmentation faults
            if segment.get('is_remote', False):
                logger.info("Downloading remote file for processing to avoid FFmpeg HTTPS segfaults")
                local_path = await self._download_media_file(segment['path'], "video_processing")
                logger.info("Remote file downloaded successfully", local_path=local_path)

                # Use local file with time-based trimming since we can't use server-side seeking
                logger.info("Processing downloaded file with local trimming")
                input_stream = ffmpeg.input(local_path)
                if segment['duration'] < segment['original_duration']:
                    logger.info("Applying trim filter to downloaded file")
                    video_stream = input_stream.video.filter(
                        'trim', start=segment['start'], duration=segment['duration']
                    ).filter('setpts', 'PTS-STARTPTS')
                else:
                    logger.info("Using full downloaded file duration")
                    video_stream = input_stream.video
            else:
                logger.info("Processing local file")
                # For local files
                input_stream = ffmpeg.input(segment['path'])
                if segment['duration'] < segment['original_duration']:
                    logger.info("Applying trim filter to local file")
                    video_stream = input_stream.video.filter(
                        'trim', start=segment['start'], duration=segment['duration']
                    ).filter('setpts', 'PTS-STARTPTS')
                else:
                    video_stream = input_stream.video
            
            # Conditionally apply scaling based on preserve_aspect_ratio flag
            if preserve_aspect_ratio:
                logger.info("Preserving original video aspect ratio and resolution (no scaling applied)")
                # Don't apply any scaling - keep original video dimensions
            else:
                logger.info("Applying scale filter", target_resolution=f"{width}x{height}")
                # Scale to target resolution (for image-generated backgrounds)
                video_stream = video_stream.filter('scale', width, height)

            # Handle padding if the segment is shorter than needed (last segment issue fix)
            if segment.get('needs_padding', False) and 'target_duration' in segment:
                padding_duration = segment['target_duration'] - segment['duration']
                if padding_duration > 0:
                    logger.info(f"Adding {padding_duration:.2f}s of padding to last segment to prevent looping")
                    # Use tpad to add black frames at the end
                    video_stream = video_stream.filter('tpad', stop_duration=padding_duration, stop_mode='clone')

            logger.info("About to start FFmpeg processing for single video segment")
            
            # Check system resources before FFmpeg execution
            import psutil
            import shutil
            memory_usage = psutil.virtual_memory()
            disk_usage = shutil.disk_usage('/tmp')
            logger.info("System resources before FFmpeg", 
                       memory_used_gb=round(memory_usage.used / (1024**3), 2),
                       memory_available_gb=round(memory_usage.available / (1024**3), 2),
                       disk_free_gb=round(disk_usage.free / (1024**3), 2))
            
            # Process with optimized settings
            logger.info("Starting FFmpeg execution", 
                       video_codec=options['video_codec'], 
                       fps=options['fps'], 
                       preset=options['preset'])
            
            try:
                logger.info("Step 1: Creating FFmpeg output configuration")
                # Build FFmpeg command and log it
                ffmpeg_output = ffmpeg.output(
                    video_stream,
                    str(output_path),
                    vcodec=options['video_codec'],
                    r=options['fps'],
                    preset=options['preset'],
                    threads=options['threads'],
                    avoid_negative_ts='make_zero'  # Handle timestamp issues
                )
                logger.info("Step 1 completed: FFmpeg output configuration created")
                
                logger.info("Step 2: Compiling FFmpeg command")
                # Log the actual command
                try:
                    cmd_args = ffmpeg.compile(ffmpeg_output, overwrite_output=True)
                    logger.info("Step 2 completed: FFmpeg command compiled", cmd_args=cmd_args)
                except Exception as compile_error:
                    logger.error("Step 2 failed: FFmpeg command compilation failed", error=str(compile_error))
                    raise
                
                logger.info("Step 3: Getting event loop for executor")
                # Execute FFmpeg
                loop = asyncio.get_event_loop()
                logger.info("Step 3 completed: Event loop obtained")
                
                logger.info("Step 4: Starting FFmpeg execution with timeout")
                start_time = time.time()
                
                # Use asyncio.wait_for to add timeout and better error handling
                try:
                    await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            self._run_ffmpeg_with_logging,
                            ffmpeg_output
                        ),
                        timeout=300  # 5 minute timeout
                    )
                    execution_time = time.time() - start_time
                    logger.info("Step 4 completed: FFmpeg execution finished", execution_time_seconds=execution_time)
                    
                except asyncio.TimeoutError:
                    execution_time = time.time() - start_time
                    logger.error("Step 4 failed: FFmpeg execution timed out", timeout_seconds=3000, partial_execution_time=execution_time)
                    raise VideoProcessingError("FFmpeg execution timed out after 50 minutes")
                except Exception as exec_error:
                    execution_time = time.time() - start_time
                    logger.error("Step 4 failed: FFmpeg execution error", error=str(exec_error), error_type=type(exec_error).__name__, partial_execution_time=execution_time)
                    raise
                
            except Exception as ffmpeg_error:
                logger.error("FFmpeg process failed", error=str(ffmpeg_error), error_type=type(ffmpeg_error).__name__)
                raise
            
            # Check output file was created successfully
            if Path(output_path).exists():
                output_size = Path(output_path).stat().st_size
                logger.info(f"Single video segment processed successfully", 
                           segment_path=segment['path'],
                           output_path=str(output_path),
                           output_size_mb=round(output_size / (1024*1024), 2))
            else:
                logger.error("Output file was not created", expected_path=str(output_path))
                raise VideoProcessingError("FFmpeg did not create output file")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error processing single optimized video: {e}", error_type=type(e).__name__)
            raise VideoProcessingError(f"Single video processing failed: {e}")
    
    async def _process_multiple_optimized_videos(self, plan: List[Dict], options: Dict, preserve_aspect_ratio: bool = False) -> str:
        """
        Process multiple video segments with bandwidth and processing optimizations
        """
        try:
            temp_segments = []
            width, height = map(int, options['resolution'].split('x'))
            
            # Process each segment with optimal settings
            for i, segment in enumerate(plan):
                segment_path = self.temp_dir / f"segment_{i}_{uuid.uuid4().hex}.mp4"
                temp_segments.append(segment_path)
                
                # Optimize processing based on segment type
                if segment.get('is_remote', False):
                    # Download remote file first to avoid FFmpeg HTTPS segmentation faults
                    logger.info("Downloading remote segment for processing", segment_index=i)
                    local_path = await self._download_media_file(segment['path'], f"segment_{i}")
                    logger.info("Remote segment downloaded successfully", local_path=local_path)

                    # Use local file with time-based trimming
                    input_stream = ffmpeg.input(local_path)
                    if segment['duration'] < segment['original_duration']:
                        video_stream = input_stream.video.filter(
                            'trim', start=segment['start'], duration=segment['duration']
                        ).filter('setpts', 'PTS-STARTPTS')
                    else:
                        video_stream = input_stream.video
                else:
                    # Local file processing (rare in cloud environment)
                    input_stream = ffmpeg.input(segment['path'])
                    if segment['duration'] < segment['original_duration']:
                        video_stream = input_stream.video.filter(
                            'trim', start=segment['start'], duration=segment['duration']
                        ).filter('setpts', 'PTS-STARTPTS')
                    else:
                        video_stream = input_stream.video
                
                # Conditionally apply scaling based on preserve_aspect_ratio flag
                if not preserve_aspect_ratio:
                    # Scale to target resolution (for image-generated backgrounds)
                    video_stream = video_stream.filter('scale', width, height)

                # Handle padding if the segment is shorter than needed (last segment issue fix)
                if segment.get('needs_padding', False) and 'target_duration' in segment:
                    padding_duration = segment['target_duration'] - segment['duration']
                    if padding_duration > 0:
                        logger.info(f"Adding {padding_duration:.2f}s of padding to segment {i+1} to prevent looping")
                        # Use tpad to add frames at the end by cloning the last frame
                        video_stream = video_stream.filter('tpad', stop_duration=padding_duration, stop_mode='clone')

                # Process segment with detailed logging
                logger.info(f"Processing video segment {i+1}/{len(plan)}",
                           segment_url=segment['path'],
                           segment_start=segment['start'],
                           segment_duration=segment['duration'])
                
                try:
                    ffmpeg_output = ffmpeg.output(
                        video_stream,
                        str(segment_path),
                        vcodec=options['video_codec'],
                        r=options['fps'],
                        preset=options['preset'],
                        threads=options['threads'],
                        avoid_negative_ts='make_zero'
                    )
                    
                    # Log command for this segment
                    cmd_args = ffmpeg.compile(ffmpeg_output, overwrite_output=True)
                    logger.info(f"FFmpeg command for segment {i+1}", cmd_args=cmd_args)
                    
                    loop = asyncio.get_event_loop()
                    start_time = time.time()
                    await loop.run_in_executor(
                        None,
                        lambda: ffmpeg_output.run(overwrite_output=True, quiet=False)
                    )
                    execution_time = time.time() - start_time
                    
                    # Verify segment was created
                    if segment_path.exists():
                        segment_size = segment_path.stat().st_size
                        logger.info(f"Segment {i+1} processed successfully", 
                                   execution_time=execution_time,
                                   output_size_mb=round(segment_size / (1024*1024), 2))
                    else:
                        logger.error(f"Segment {i+1} output file not created", expected_path=str(segment_path))
                        raise VideoProcessingError(f"Segment {i+1} processing failed")
                        
                except Exception as segment_error:
                    logger.error(f"Error processing segment {i+1}", error=str(segment_error))
                    raise
                
                # This line is now handled in the detailed logging above
            
            # Concatenate all processed segments
            output_path = self.temp_dir / f"concatenated_optimized_{uuid.uuid4().hex}.mp4"
            
            # Create concat demuxer input list
            concat_file = self.temp_dir / f"concat_list_{uuid.uuid4().hex}.txt"
            with open(concat_file, 'w') as f:
                for segment_path in temp_segments:
                    f.write(f"file '{segment_path}'\n")
            
            # Run concatenation
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: ffmpeg.input(
                    str(concat_file), format='concat', safe=0
                ).output(
                    str(output_path),
                    vcodec=options['video_codec'],
                    r=options['fps'],
                    preset=options['preset'],
                    threads=options['threads']
                ).run(overwrite_output=True, quiet=True)
            )
            
            # Clean up temporary files
            for segment_path in temp_segments:
                if segment_path.exists():
                    segment_path.unlink()
            if concat_file.exists():
                concat_file.unlink()
            
            logger.info(f"Successfully concatenated {len(plan)} optimized video segments")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error processing multiple optimized videos: {e}")
            raise VideoProcessingError(f"Multiple video processing failed: {e}")
    
    
    
    async def combine_videos_with_music(
        self,
        video_files: List,
        audio_url: str,
        music_url: Optional[str],
        user_id: str,
        job_id: str,
        processing_options: Optional[Dict[str, Any]] = None,
        music_options: Optional[Dict[str, Any]] = None,
        audio_duration: Optional[float] = None,
        upload_result: bool = True
    ) -> str:
        """
        Combine videos with TTS audio and optional background music
        
        Args:
            video_files: List of VideoFile objects or URL strings
            audio_url: GCS URL to TTS audio file
            music_url: Optional GCS URL to background music file
            user_id: User ID for GCS path organization
            job_id: Job ID for GCS path organization
            processing_options: Video processing configuration
            music_options: Music mixing configuration
            audio_duration: Optional audio duration to skip probing
            upload_result: Whether to upload result to GCS or return local path
            
        Returns:
            GCS URL or local path of final video
        """
        start_time = time.time()
        
        # Log entry with music details
        logger.info("🎵 MUSIC: combine_videos_with_music called", 
                   job_id=job_id,
                   music_url=music_url,
                   music_url_provided=music_url is not None,
                   music_url_length=len(music_url) if music_url else 0,
                   has_music_options=music_options is not None,
                   music_options=music_options)
        
        try:
            # Convert video_files to consistent format and extract URLs and durations
            video_urls = []
            video_durations = {}
            
            for video_file in video_files:
                if isinstance(video_file, str):
                    video_urls.append(video_file)
                else:
                    video_urls.append(video_file.url)
                    if hasattr(video_file, 'duration') and video_file.duration:
                        video_durations[video_file.url] = video_file.duration
            
            # Default processing options
            options = {
                'resolution': '1280x720',
                'fps':25,
                'video_codec': 'libx264',
                'audio_codec': 'aac',
                'preset': 'ultrafast',
                'threads': 0
            }
            if processing_options:
                options.update(processing_options)
                
            # Default music options
            music_settings = {
                'volume': 0.25,
                'fade_in_duration': 2.0,
                'fade_out_duration': 3.0,
                'loop_music': True,
                'mix_mode': 'background'
            }
            if music_options:
                music_settings.update(music_options)
                
            preserve_video_aspect_ratio = True
            logger.info("Video processing with music - preserving original aspect ratio")
            
            logger.info(
                "Starting video+audio+music processing",
                video_count=len(video_urls),
                job_id=job_id,
                has_music=bool(music_url),
                music_settings=music_settings if music_url else None
            )
            
            # Get audio duration if not provided
            if audio_duration is None:
                audio_duration = await self._get_duration_from_url(audio_url)
            
            # Download audio file
            audio_path = await self._download_media_file(audio_url, "audio")
            
            # Download music file if provided
            music_path = None
            if music_url:
                music_path = await self._download_media_file(music_url, "music")
            
            # Enhance video list with templates if needed
            enhanced_video_urls = await self._enhance_videos_with_templates(
                video_urls, audio_duration, True, video_durations
            )
            
            # Process videos first to get combined video path
            combined_video_path = await self._combine_videos_optimized(
                enhanced_video_urls, audio_duration, options, video_durations, preserve_video_aspect_ratio
            )
            
            # Combine video with audio and music
            output_path = self.temp_dir / f"final_video_with_music_{job_id}.mp4"
            
            if music_path:
                await self._combine_video_audio_music(
                    combined_video_path,
                    audio_path,
                    music_path,
                    output_path,
                    {**options, **music_settings},
                    audio_duration
                )
            else:
                # No music - just combine video and audio
                await self._combine_video_audio(
                    combined_video_path,
                    audio_path,
                    output_path,
                    options
                )
            
            # Verify output file was created
            if not output_path.exists():
                raise VideoProcessingError(f"Video processing failed - output file not created: {output_path}")
            
            # Upload result to GCS (optional)
            if upload_result:
                result_url = await self.gcs_service.upload_final_video(
                    str(output_path),
                    str(user_id),
                    job_id,
                    f"Final Video {job_id}",
                    language_code=self.language_code  # Pass language code for multi-language support
                )
            else:
                result_url = str(output_path)
            
            processing_time = time.time() - start_time
            logger.info(
                "Video+audio+music processing completed",
                job_id=job_id,
                result_url=result_url,
                processing_time=processing_time
            )
            
            return result_url
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                "Video+audio+music processing failed",
                job_id=job_id,
                error=str(e),
                processing_time=processing_time
            )
            raise VideoProcessingError(f"Video processing with music failed: {e}")
        
        finally:
            if upload_result:
                await self._cleanup_temp_files(job_id)
            else:
                await self._cleanup_temp_files_except_output(job_id, str(output_path))

    async def combine_videos_with_subtitles(
        self,
        video_files: List,
        audio_url: str,
        subtitle_url: str,
        user_id: int,
        job_id: str,
        processing_options: Optional[Dict[str, Any]] = None,
        style_options: Optional[Dict[str, Any]] = None,
        audio_duration: Optional[float] = None,
        known_video_durations: Optional[Dict[str, float]] = None,
        upload_result: bool = True
    ) -> str:
        """
        Combine multiple video clips with audio and burn subtitles in a single FFmpeg operation
        
        This method optimizes the current two-step process (combine_videos + burn_subtitles)
        into a single FFmpeg command for better performance on Cloud Run.
        
        Args:
            video_files: List of VideoFile objects or URL strings
            audio_url: GCS URL or HTTP URL to audio file
            subtitle_url: GCS URL or HTTP URL to subtitle file (SRT/ASS format)
            user_id: User ID for GCS path organization
            job_id: Job ID for GCS path organization
            processing_options: Video processing configuration
            style_options: Subtitle styling configuration
            audio_duration: Optional audio duration to skip probing
            upload_result: Whether to upload result to GCS or return local path
            
        Returns:
            GCS URL or local path of final video with subtitles
        """
        start_time = time.time()
        
        try:
            # Convert video_files to consistent format and extract URLs and durations
            video_urls = []
            video_durations = {}
            
            for video_file in video_files:
                if isinstance(video_file, str):
                    video_urls.append(video_file)
                else:
                    video_urls.append(video_file.url)
                    if hasattr(video_file, 'duration') and video_file.duration:
                        video_durations[video_file.url] = video_file.duration
            if known_video_durations:
                video_durations.update(known_video_durations)
            
            # Default processing options
            options = {
                'resolution': '1280x720',
                'fps': 25,
                'video_codec': 'libx264',
                'audio_codec': 'aac',
                'preset': 'ultrafast',
                'threads': 0  # Use all available CPU cores
            }
            if processing_options:
                options.update(processing_options)
                
            # For video backgrounds, preserve original aspect ratio by not applying resolution scaling
            preserve_video_aspect_ratio = True
            logger.info("Video background processing with subtitles - will preserve original aspect ratio and resolution")
            
            # Default style options
            subtitle_options = {
                'font_name': 'Arial',
                'font_size': 24,
                'font_color': 'white',
                'outline_color': 'black',
                'outline_width': 2,
                'alignment': 'bottom_center',
                'margin_v': 20
            }
            if style_options:
                subtitle_options.update(style_options)
            
            logger.info(
                "Starting single-step video+audio+subtitles processing",
                video_count=len(video_urls),
                job_id=job_id,
                audio_duration=audio_duration
            )
            
            # Get audio duration if not provided
            if audio_duration is None:
                audio_duration = await self._get_duration_from_url(audio_url)
            
            # Download audio and subtitle files
            audio_path = await self._download_media_file(audio_url, "audio")
            subtitle_path = await self._download_media_file(subtitle_url, "subtitle")
            
            # Enhance video list with templates if needed
            enhanced_video_urls = await self._enhance_videos_with_templates(
                video_urls, audio_duration, True, video_durations
            )
            
            # Process videos first to get combined video path
            combined_video_path = await self._combine_videos_optimized(
                enhanced_video_urls, audio_duration, options, video_durations, preserve_video_aspect_ratio
            )
            
            # Now use single-step processing for video+audio+subtitles
            output_path = self.temp_dir / f"final_video_with_subtitles_{job_id}.mp4"
            
            await self._combine_video_audio_subtitles(
                combined_video_path,
                audio_path,
                subtitle_path,
                output_path,
                {**options, **subtitle_options}
            )
            
            # Verify output file was created
            if not output_path.exists():
                raise VideoProcessingError(f"Single-step processing failed - output file not created: {output_path}")
            
            # Upload result to GCS (optional)
            if upload_result:
                # Use the new upload_final_video method for user-specific paths
                result_url = await self.gcs_service.upload_final_video(
                    str(output_path),
                    str(user_id),  # Convert to string for user-specific path
                    job_id,
                    f"Final Video {job_id}",  # Video title
                    language_code=self.language_code  # Pass language code for multi-language support
                )
            else:
                result_url = str(output_path)
            
            processing_time = time.time() - start_time
            logger.info(
                "Single-step video+audio+subtitles processing completed",
                job_id=job_id,
                result_url=result_url,
                processing_time=processing_time
            )
            
            return result_url
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                "Single-step video+audio+subtitles processing failed",
                job_id=job_id,
                error=str(e),
                processing_time=processing_time
            )
            raise VideoProcessingError(f"Single-step processing failed: {e}")
        
        finally:
            # Clean up temporary files (but preserve output if not uploaded)
            if upload_result:
                await self._cleanup_temp_files(job_id)
            else:
                await self._cleanup_temp_files_except_output(job_id, str(output_path))

    async def _combine_video_audio_music(
        self,
        video_path: str,
        audio_path: str,
        music_path: str,
        output_path: Path,
        options: Dict,
        target_duration: float
    ):
        """Combine processed video with TTS audio and background music"""
        try:
            video_input = ffmpeg.input(video_path)
            audio_input = ffmpeg.input(audio_path)
            music_input = ffmpeg.input(music_path)
            
            # Get music duration to determine if we need to loop
            music_duration = await self._get_duration(music_path)
            
            # Prepare music stream with effects
            music_stream = music_input.audio
            
            # Apply volume reduction to music
            music_volume = options.get('volume', 0.25)
            music_stream = music_stream.filter('volume', music_volume)
            
            # Apply fade effects if specified
            fade_in = options.get('fade_in_duration', 0)
            fade_out = options.get('fade_out_duration', 0)
            
            if fade_in > 0:
                music_stream = music_stream.filter('afade', type='in', duration=fade_in)
            
            if fade_out > 0 and target_duration > fade_out:
                music_stream = music_stream.filter('afade', type='out', start_time=target_duration - fade_out, duration=fade_out)
            
            # Loop music if it's shorter than target duration
            if options.get('loop_music', True) and music_duration > 0 and target_duration > music_duration:
                # Calculate how many loops we need
                loop_count = int(target_duration / music_duration) + 1
                logger.info(f"Looping music {loop_count} times to cover {target_duration:.2f}s duration")
                
                # Create looped music input
                music_stream = ffmpeg.input(music_path, stream_loop=loop_count).audio
                music_stream = music_stream.filter('volume', music_volume)
                
                # Trim to exact duration needed
                music_stream = music_stream.filter('atrim', duration=target_duration)
                
                # Apply fade effects after looping
                if fade_in > 0:
                    music_stream = music_stream.filter('afade', type='in', duration=fade_in)
                if fade_out > 0:
                    music_stream = music_stream.filter('afade', type='out', start_time=target_duration - fade_out, duration=fade_out)
            
            # Mix TTS audio with background music
            # Use amix filter to combine the two audio streams
            mixed_audio = ffmpeg.filter([audio_input.audio, music_stream], 'amix', inputs=2, duration='first', dropout_transition=3)
            
            logger.info("Starting video+audio+music combination")
            
            loop = asyncio.get_event_loop()
            combine_start = time.time()
            await loop.run_in_executor(
                None,
                lambda: ffmpeg.output(
                    video_input.video,
                    mixed_audio,
                    str(output_path),
                    vcodec=options['video_codec'],
                    acodec=options['audio_codec'],
                    preset=options['preset'],
                    threads=options.get('threads', 0),
                    shortest=None
                ).run(overwrite_output=True, quiet=True)
            )
            combine_time = time.time() - combine_start
            
            logger.info("Video+audio+music combination completed", 
                       combine_time_seconds=round(combine_time, 2),
                       output_path=str(output_path))
            
        except Exception as e:
            logger.error("Error combining video, audio and music", error=str(e))
            raise VideoProcessingError(f"Video-audio-music combination failed: {e}")

    async def _combine_video_audio_subtitles(
        self,
        video_path: str,
        audio_path: str,
        subtitle_path: str,
        output_path: Path,
        options: Dict
    ):
        """Combine processed video with audio and subtitles in one step"""
        try:
            video_input = ffmpeg.input(video_path)
            audio_input = ffmpeg.input(audio_path)
            
            # Escape the subtitle path for ffmpeg
            escaped_subtitle_path = str(Path(subtitle_path)).replace('\\', '\\\\').replace(':', '\\:')
            
            # Build subtitle filter
            if options.get('font_file') and Path(options['font_file']).exists():
                # Use custom font
                fonts_dir = str(Path(options['font_file']).parent)
                font_filename = Path(options['font_file']).name

                # Map font files to their proper font family names
                font_mappings = {
                    "qingsong.ttf": "JasonHandwriting1",
                    "LuckiestGuy-Regular.ttf": "Luckiest Guy",
                    "PermanentMarker-Regular.ttf": "Permanent Marker",
                    "Poppins-BoldItalic.ttf": "Poppins Bold Italic",
                    "laihu.ttf": "SetoFont",
                    "yangrendongzhushi.ttf": "YRDZST",
                    "zhankukuaile.ttf": "HappyZcool\-2016",
                    "yousheyufeitejiankangti.ttf": "YouSheShaYuFeiTeJianKangTi",
                    "nishiki-teki-2.ttf": "Nishiki\-teki"
                }

                # Get the proper font family name
                font_name = font_mappings.get(font_filename, Path(options['font_file']).stem)

                # Build force_style parameters for ASS files
                force_style_parts = [f"FontName={font_name}"]  # Always include font name first
                if options.get('font_size'):
                    force_style_parts.append(f"FontSize={options['font_size']}")
                if options.get('font_color'):
                    force_style_parts.append(f"PrimaryColour={options['font_color']}")
                if options.get('outline_color'):
                    force_style_parts.append(f"OutlineColour={options['outline_color']}")
                if options.get('outline_width'):
                    force_style_parts.append(f"Outline={options['outline_width']}")

                force_style = ','.join(force_style_parts)
                subtitle_filter = f"subtitles='{escaped_subtitle_path}':fontsdir='{fonts_dir}':force_style='{force_style}'"
            else:
                # Use default system fonts with Chinese support
                subtitle_filter = f"subtitles='{escaped_subtitle_path}':force_style='FontName=Noto Sans CJK SC'"
            
            logger.info("Starting single-step video+audio+subtitles combination")
            
            loop = asyncio.get_event_loop()
            combine_start = time.time()
            await loop.run_in_executor(
                None,
                lambda: ffmpeg.output(
                    video_input.video.filter('subtitles', escaped_subtitle_path),
                    audio_input.audio,
                    str(output_path),
                    vcodec=options['video_codec'],
                    acodec=options['audio_codec'],
                    preset=options['preset'],
                    threads=options.get('threads', 0),
                    shortest=None
                ).run(overwrite_output=True, quiet=True)
            )
            combine_time = time.time() - combine_start
            
            logger.info("Single-step video+audio+subtitles combination completed", 
                       combine_time_seconds=round(combine_time, 2),
                       output_path=str(output_path))

            if not self._has_audio_stream(str(output_path)):
                logger.warning(
                    "Subtitled output has no audio stream after default mux, retrying with explicit stream mapping",
                    output_path=str(output_path)
                )

                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(video_path),
                    "-i", str(audio_path),
                    "-vf", f"subtitles={escaped_subtitle_path}",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-c:v", str(options.get('video_codec', 'libx264')),
                    "-c:a", str(options.get('audio_codec', 'aac')),
                    "-preset", str(options.get('preset', 'ultrafast')),
                    "-threads", str(options.get('threads', 0)),
                    "-shortest",
                    str(output_path),
                ]

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: subprocess.run(cmd, check=True, capture_output=True, text=True))

                if not self._has_audio_stream(str(output_path)):
                    raise VideoProcessingError("Subtitled fallback mux completed but output still has no audio stream")
            
        except Exception as e:
            logger.error("Error combining video, audio and subtitles", error=str(e))
            raise VideoProcessingError(f"Video-audio-subtitles combination failed: {e}")

    async def _combine_video_audio(
        self,
        video_path: str,
        audio_path: str,
        output_path: Path,
        options: Dict
    ):
        """Combine processed video with audio (legacy method for backward compatibility)"""
        try:
            video_input = ffmpeg.input(video_path)
            audio_input = ffmpeg.input(audio_path)
            
            loop = asyncio.get_event_loop()
            combine_start = time.time()
            await loop.run_in_executor(
                None,
                lambda: ffmpeg.output(
                    video_input.video,
                    audio_input.audio,
                    str(output_path),
                    vcodec=options['video_codec'],
                    acodec=options['audio_codec'],
                    preset=options['preset'],
                    threads=options.get('threads', 0),
                    shortest=None
                ).run(overwrite_output=True, quiet=True)
            )
            combine_time = time.time() - combine_start
            
            logger.info("Video-audio combination completed", 
                       combine_time_seconds=round(combine_time, 2),
                       output_path=str(output_path))

            if not self._has_audio_stream(str(output_path)):
                logger.warning(
                    "Output has no audio stream after default mux, retrying with explicit stream mapping",
                    output_path=str(output_path)
                )
                await self._combine_video_audio_with_explicit_map(video_path, audio_path, output_path, options)
            
        except Exception as e:
            logger.error("Error combining video and audio", error=str(e))
            raise VideoProcessingError(f"Video-audio combination failed: {e}")

    def _has_audio_stream(self, media_path: str) -> bool:
        """Return True if media file contains at least one audio stream."""
        try:
            probe = ffmpeg.probe(media_path)
            streams = probe.get('streams', [])
            return any(stream.get('codec_type') == 'audio' for stream in streams)
        except Exception as e:
            logger.warning("Failed to probe media streams", media_path=media_path, error=str(e))
            return False

    async def _combine_video_audio_with_explicit_map(
        self,
        video_path: str,
        audio_path: str,
        output_path: Path,
        options: Dict
    ) -> None:
        """Fallback mux with explicit stream mapping to guarantee audio is preserved."""
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", str(options.get('video_codec', 'libx264')),
            "-c:a", str(options.get('audio_codec', 'aac')),
            "-preset", str(options.get('preset', 'ultrafast')),
            "-threads", str(options.get('threads', 0)),
            "-shortest",
            str(output_path),
        ]

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: subprocess.run(cmd, check=True, capture_output=True, text=True))

        if not self._has_audio_stream(str(output_path)):
            raise VideoProcessingError("Fallback mux completed but output still has no audio stream")

    async def _remux_video_with_audio_stream(
        self,
        video_path: str,
        audio_path: str,
        output_path: Path
    ) -> None:
        """
        Remux an existing rendered video with an explicit audio stream.

        Uses stream copy for video to preserve quality and speed, and AAC for audio
        for broad player compatibility.
        """
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(output_path),
        ]

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: subprocess.run(cmd, check=True, capture_output=True, text=True))

        if not self._has_audio_stream(str(output_path)):
            raise VideoProcessingError("Explicit remux completed but output still has no audio stream")

    async def enforce_audio_track(
        self,
        video_url: str,
        audio_url: str,
        user_id: str,
        job_id: str,
        upload_result: bool = True
    ) -> str:
        """
        Ensure final video contains an audio stream.

        If the input video already has audio, returns it unchanged.
        Otherwise remuxes the video with the provided audio track.
        """
        try:
            if not video_url or not audio_url:
                return video_url

            local_video = await self._download_media_file(video_url, "video")
            if self._has_audio_stream(local_video):
                logger.info("Final video already contains audio stream", job_id=job_id)
                return video_url

            logger.warning(
                "Final video missing audio stream, remuxing with source audio",
                job_id=job_id,
                video_url=video_url
            )

            local_audio = await self._download_media_file(audio_url, "audio")
            fixed_output_path = self.temp_dir / f"final_video_audio_fixed_{job_id}.mp4"

            await self._remux_video_with_audio_stream(local_video, local_audio, fixed_output_path)

            if upload_result:
                fixed_url = await self.gcs_service.upload_final_video(
                    str(fixed_output_path),
                    str(user_id),
                    job_id,
                    f"Final Video {job_id}",
                    language_code=self.language_code
                )
                logger.info("Uploaded audio-fixed final video", job_id=job_id, fixed_url=fixed_url)
                return fixed_url

            return str(fixed_output_path)
        except Exception as e:
            logger.error("Failed to enforce audio track on final video", job_id=job_id, error=str(e))
            raise VideoProcessingError(f"Audio enforcement failed: {e}")
    
    async def _sync_audio_video_ffmpeg(
        self,
        video_path: str,
        audio_path: str,
        output_path: Path,
        options: Dict
    ):
        """Synchronize audio with video using FFmpeg"""
        try:
            video_input = ffmpeg.input(video_path)
            audio_input = ffmpeg.input(audio_path)
            
            # Apply audio offset if specified
            if options.get('audio_offset', 0) != 0:
                audio_input = audio_input.filter('adelay', f"{int(options['audio_offset'] * 1000)}|{int(options['audio_offset'] * 1000)}")
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: ffmpeg.output(
                    video_input.video,
                    audio_input.audio,
                    str(output_path),
                    vcodec=options['video_codec'],
                    acodec=options['audio_codec'],
                    preset=options['preset'],
                    threads=options.get('threads', 0)
                ).run(overwrite_output=True, quiet=True)
            )
            
        except Exception as e:
            logger.error("Error in audio-video sync", error=str(e))
            raise AudioVideoSyncError(f"Audio-video sync failed: {e}")
    
    def _validate_segments(self, segments: List[Dict], video_duration: float) -> List[Dict]:
        """Validate and normalize segment definitions"""
        validated = []
        
        for segment in segments:
            start_time = self._parse_timestamp(segment.get('start_time', '00:00:00'))
            end_time = self._parse_timestamp(segment.get('end_time', '00:00:10'))
            
            # Validate timestamps
            if start_time < 0:
                start_time = 0
            if end_time > video_duration:
                end_time = video_duration
            if start_time >= end_time:
                continue  # Skip invalid segments
            
            validated.append({
                'start': start_time,
                'end': end_time,
                'duration': end_time - start_time,
                'output_name': segment.get('output_name')
            })
        
        return validated
    
    def _parse_timestamp(self, timestamp: str) -> float:
        """Parse timestamp string (HH:MM:SS) to seconds"""
        try:
            parts = timestamp.split(':')
            if len(parts) == 3:
                hours, minutes, seconds = map(float, parts)
                return hours * 3600 + minutes * 60 + seconds
            elif len(parts) == 2:
                minutes, seconds = map(float, parts)
                return minutes * 60 + seconds
            else:
                return float(parts[0])
        except (ValueError, IndexError):
            return 0.0
    
    async def _split_video_segment(
        self,
        video_path: str,
        segment: Dict,
        index: int,
        job_id: str,
        options: Dict
    ) -> str:
        """Split a single video segment"""
        try:
            output_path = self.temp_dir / f"split_segment_{index}_{job_id}.mp4"
            
            input_stream = ffmpeg.input(video_path)
            
            if options.get('copy_streams', False):
                # Fast copy without re-encoding
                output = ffmpeg.output(
                    input_stream,
                    str(output_path),
                    ss=segment['start'],
                    t=segment['duration'],
                    c='copy'
                )
            else:
                # Re-encode with specified options
                output = ffmpeg.output(
                    input_stream,
                    str(output_path),
                    ss=segment['start'],
                    t=segment['duration'],
                    vcodec=options['video_codec'],
                    acodec=options['audio_codec'],
                    preset=options['preset'],
                    threads=options.get('threads', 0)
                )
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: output.run(overwrite_output=True, quiet=True)
            )
            
            return str(output_path)
            
        except Exception as e:
            logger.error("Error splitting video segment", segment=segment, error=str(e))
            raise VideoSplitError(f"Video segment splitting failed: {e}")
    
    async def _burn_subtitles_ffmpeg(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: Path,
        options: Dict
    ):
        """Burn subtitles into video using FFmpeg - matches working local implementation"""
        try:
            logger.info(
                "Starting subtitle burning",
                video_path=video_path,
                subtitle_path=subtitle_path,
                output_path=str(output_path)
            )
            
            # Use the exact same approach as the working local implementation
            video_input = ffmpeg.input(video_path)
            
            # Escape the subtitle path for ffmpeg (same as local implementation)
            escaped_subtitle_path = str(Path(subtitle_path)).replace('\\', '\\\\').replace(':', '\\:')
            
            # Build subtitle filter with custom font support
            if options.get('font_file') and Path(options['font_file']).exists():
                # Use custom font with fontsdir parameter
                fonts_dir = str(Path(options['font_file']).parent)
                font_filename = Path(options['font_file']).name

                # Map font files to their proper font family names
                font_mappings = {
                    "qingsong.ttf": "JasonHandwriting1",
                    "LuckiestGuy-Regular.ttf": "Luckiest Guy",
                    "PermanentMarker-Regular.ttf": "Permanent Marker",
                    "Poppins-BoldItalic.ttf": "Poppins Bold Italic",
                    "laihu.ttf": "SetoFont",
                    "yangrendongzhushi.ttf": "YRDZST",
                    "zhankukuaile.ttf": "HappyZcool\-2016",
                    "yousheyufeitejiankangti.ttf": "YouSheShaYuFeiTeJianKangTi",
                    "nishiki-teki-2.ttf": "Nishiki\-teki"
                }

                # Get the proper font family name
                font_name = font_mappings.get(font_filename, Path(options['font_file']).stem)

                # Build force_style parameters for ASS files
                force_style_parts = [f"FontName={font_name}"]  # Always include font name first
                if options.get('font_size'):
                    force_style_parts.append(f"FontSize={options['font_size']}")
                if options.get('font_color'):
                    force_style_parts.append(f"PrimaryColour={options['font_color']}")
                if options.get('outline_color'):
                    force_style_parts.append(f"OutlineColour={options['outline_color']}")
                if options.get('outline_width'):
                    force_style_parts.append(f"Outline={options['outline_width']}")

                force_style = ','.join(force_style_parts)
                subtitle_filter = f"subtitles='{escaped_subtitle_path}':fontsdir='{fonts_dir}':force_style='{force_style}'"
                    
                logger.info(
                    "Building FFmpeg command with custom font",
                    escaped_subtitle_path=escaped_subtitle_path,
                    fonts_dir=fonts_dir,
                    font_file=options['font_file'],
                    force_style=force_style
                )
            else:
                # Use default system fonts with Chinese support
                subtitle_filter = f"subtitles='{escaped_subtitle_path}':force_style='FontName=Noto Sans CJK SC'"
                logger.info(
                    "Building FFmpeg command with system fonts",
                    escaped_subtitle_path=escaped_subtitle_path
                )
            
            # Use vf parameter approach (same as working local implementation)
            output = ffmpeg.output(
                video_input,
                str(output_path),
                vf=subtitle_filter,
                **{"c:a": "copy"}  # Copy audio without re-encoding
            )
            
            logger.info("Executing FFmpeg command")
            
            # Add debug: let's see the actual FFmpeg command
            try:
                cmd_args = ffmpeg.compile(output, overwrite_output=True)
                logger.info("FFmpeg command to execute", cmd_args=cmd_args)
            except Exception as cmd_error:
                logger.warning("Could not compile FFmpeg command for logging", error=str(cmd_error))
            
            loop = asyncio.get_event_loop()
            ffmpeg_start = time.time()
            await loop.run_in_executor(
                None,
                lambda: ffmpeg.run(output, overwrite_output=True, quiet=False)  # Changed to quiet=False for debugging
            )
            ffmpeg_time = time.time() - ffmpeg_start
            
            logger.info(
                "Subtitle burning completed successfully",
                output_path=str(output_path),
                ffmpeg_execution_time_seconds=round(ffmpeg_time, 2)
            )
            
        except Exception as e:
            logger.error("Error burning subtitles", error=str(e), video_path=video_path, subtitle_path=subtitle_path)
            raise SubtitleBurnError(f"Subtitle burning failed: {e}")
    
    def _is_valid_subtitle_format(self, subtitle_path: str) -> bool:
        """Check if subtitle file is in valid format (SRT or ASS)"""
        try:
            with open(subtitle_path, 'r', encoding='utf-8') as f:
                content = f.read(100)  # Read first 100 characters
                
            # Check for SRT format (starts with number)
            if content.strip().startswith('1'):
                return True
            
            # Check for ASS format
            if '[Script Info]' in content or '[V4+ Styles]' in content:
                return True
            
            return False
            
        except Exception:
            return False
    
    def _color_to_hex(self, color: str) -> str:
        """Convert color name to hex format for FFmpeg"""
        color_map = {
            'white': '&Hffffff',
            'black': '&H000000',
            'red': '&H0000ff',
            'green': '&H00ff00',
            'blue': '&Hff0000',
            'yellow': '&H00ffff',
            'cyan': '&Hffff00',
            'magenta': '&Hff00ff'
        }
        return color_map.get(color.lower(), '&Hffffff')
    
    def _get_file_extension(self, url: str) -> str:
        """Get file extension from URL"""
        parsed = urlparse(url)
        path = Path(parsed.path)
        return path.suffix or '.mp4'
    
    async def _enhance_videos_with_templates(
        self,
        user_videos: List[str],
        audio_duration: float,
        use_templates: bool = True,
        video_durations: Dict[str, float] = None
    ) -> List[str]:
        """
        Enhance user video list with template videos when needed
        
        Args:
            user_videos: List of user-provided video URLs
            audio_duration: Target audio duration in seconds
            use_templates: Whether to use template videos as fallback
            
        Returns:
            Enhanced list of video URLs including templates if needed
        """
        try:
            if not use_templates or not user_videos:
                return user_videos
            
            # Calculate total duration of user videos
            user_video_duration = 0.0
            valid_user_videos = []
            
            for video_url in user_videos:
                try:
                    # Use provided duration if available, otherwise probe
                    if video_durations and video_url in video_durations:
                        duration = video_durations[video_url]
                        logger.info(f"User video using provided duration: {video_url}, duration: {duration:.2f}s")
                    else:
                        duration = await self._get_duration(video_url)
                        logger.info(f"User video validated via probe: {video_url}, duration: {duration:.2f}s")
                    
                    if duration > 0:
                        user_video_duration += duration
                        valid_user_videos.append(video_url)
                except Exception as e:
                    logger.warning(f"Failed to validate user video {video_url}: {e}")
            
            # If user videos are sufficient, return them
            if user_video_duration >= audio_duration * 1.2:  # 20% buffer
                logger.info(f"User videos sufficient: {user_video_duration:.2f}s >= {audio_duration:.2f}s")
                return valid_user_videos
            
            # Get template videos to supplement user videos
            shortage_duration = (audio_duration * 1.5) - user_video_duration  # 50% buffer
            # template_videos = await self._get_template_videos(shortage_duration)
            
            # if template_videos:
            #     enhanced_videos = valid_user_videos + template_videos
            #     logger.info(
            #         f"Enhanced videos with templates: {len(valid_user_videos)} user + {len(template_videos)} templates"
            #     )
            #     return enhanced_videos
            # else:
            #     logger.warning("No template videos available, using user videos only")
            #     return valid_user_videos
            return valid_user_videos
            
        except Exception as e:
            logger.error(f"Error enhancing videos with templates: {e}")
            return user_videos
    
    async def _get_template_videos(self, target_duration: float) -> List[str]:
        """
        Get template videos from GCS to reach target duration
        
        Args:
            target_duration: Minimum total duration needed in seconds
            
        Returns:
            List of template video URLs
        """
        try:
            # Try to get template list from cache first
            if 'template_list' not in self._template_cache:
                await self._refresh_template_cache()
            
            template_list = self._template_cache.get('template_list', [])
            if not template_list:
                logger.warning("No template videos available in GCS bucket")
                return []
            
            # Select templates to meet target duration
            selected_templates = []
            total_duration = 0.0
            
            # Sort templates by duration (longer first for efficiency)
            sorted_templates = sorted(template_list, key=lambda x: x['duration'], reverse=True)
            
            for template in sorted_templates:
                if total_duration >= target_duration:
                    break
                
                selected_templates.append(template['url'])
                total_duration += template['duration']
                
                logger.info(
                    f"Selected template: {template['name']}, duration: {template['duration']:.2f}s"
                )
            
            logger.info(
                f"Selected {len(selected_templates)} templates for {total_duration:.2f}s (target: {target_duration:.2f}s)"
            )
            
            return selected_templates
            
        except Exception as e:
            logger.error(f"Error getting template videos: {e}")
            return []
    
    async def _refresh_template_cache(self):
        """
        Refresh the template video cache from GCS
        """
        try:
            # List template videos in GCS bucket
            template_blobs = await self.gcs_service.list_files_in_bucket(
                bucket_name=self.template_videos_bucket,
                prefix=self.template_videos_prefix
            )
            
            template_list = []
            
            for blob_info in template_blobs:
                if blob_info['name'].lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
                    try:
                        # Generate signed URL for template video
                        template_url = await self.gcs_service.generate_signed_url(
                            self.template_videos_bucket,
                            blob_info['name'],
                            expiration_minutes=60
                        )
                        
                        # Get duration (cached to avoid repeated probing)
                        cache_key = f"duration_{blob_info['name']}"
                        if cache_key in self._template_cache:
                            duration = self._template_cache[cache_key]
                        else:
                            duration = await self._get_duration(template_url)
                            self._template_cache[cache_key] = duration
                        
                        if duration > 0:
                            template_list.append({
                                'name': Path(blob_info['name']).name,
                                'url': template_url,
                                'duration': duration,
                                'size': blob_info.get('size', 0)
                            })
                            
                    except Exception as e:
                        logger.warning(f"Failed to process template {blob_info['name']}: {e}")
            
            self._template_cache['template_list'] = template_list
            self._template_cache['last_refresh'] = time.time()
            
            logger.info(f"Refreshed template cache with {len(template_list)} templates")
            
        except Exception as e:
            logger.error(f"Error refreshing template cache: {e}")
            self._template_cache['template_list'] = []
    
    def _create_optimized_video_plan(self, video_info: List[Dict], target_duration: float) -> List[Dict]:
        """
        Create optimized processing plan for videos based on audio duration
        Migrated from local video processing service with cloud optimizations

        Args:
            video_info: List of video file info with duration and URL
            target_duration: Target audio duration in seconds

        Returns:
            List of video segments with optimized start/duration for efficient processing
        """
        plan = []
        current_time = 0
        video_index = 0

        while current_time < target_duration:
            current_video = video_info[video_index % len(video_info)]
            remaining_time = target_duration - current_time

            # Determine optimal segment duration
            # CRITICAL FIX: Never request more duration than the video actually has
            # This prevents FFmpeg from looping back to the first frames
            max_available_duration = current_video['duration']

            if max_available_duration >= remaining_time:
                # Video is longer than remaining time - only use what we need
                segment_duration = remaining_time
                start_time = 0  # Always start from beginning for bandwidth optimization
                needs_padding = False
            else:
                # Video is shorter than remaining time - use full video and mark for padding
                segment_duration = max_available_duration
                start_time = 0
                needs_padding = True

                logger.info(f"Last segment is shorter than needed: has {max_available_duration:.2f}s, needs {remaining_time:.2f}s. Will pad the final video.")

            plan.append({
                'path': current_video['url'],
                'start': start_time,
                'duration': segment_duration,
                'original_duration': current_video['duration'],
                'needs_padding': needs_padding,
                'target_duration': remaining_time if needs_padding else segment_duration,
                'is_remote': self._is_remote_url(current_video['url']),
                'estimated_download_mb': self._estimate_download_size_sync(current_video['url'], segment_duration)
            })

            current_time += segment_duration
            video_index += 1

            # Safety check to prevent infinite loops
            if video_index > len(video_info) * 100:
                logger.warning("Video plan generation exceeded safety limit")
                break

        # Log optimization benefits
        self._log_optimization_benefits(plan, target_duration)

        return plan
    
    def _is_remote_url(self, url: str) -> bool:
        """
        Check if URL is remote
        """
        return url.startswith(('http://', 'https://', 'gs://', 'ftp://'))
    
    def _estimate_download_size_sync(self, url: str, duration: float) -> float:
        """
        Synchronous version of download size estimation
        
        Args:
            url: Video URL
            duration: Duration in seconds
            
        Returns:
            Estimated download size in MB
        """
        try:
            if not self._is_remote_url(url):
                return 0.0
            
            # Conservative estimate: 2 Mbps for decent quality video
            estimated_bitrate = 2000000  # 2 Mbps
            estimated_size_mb = (estimated_bitrate * duration) / (8 * 1024 * 1024)
            
            return estimated_size_mb
            
        except Exception:
            return 0.0
    
    def _log_optimization_benefits(self, plan: List[Dict], target_duration: float):
        """
        Log the benefits of the optimization approach
        """
        try:
            total_original_duration = sum(segment['original_duration'] for segment in plan)
            total_processing_duration = sum(segment['duration'] for segment in plan)
            total_estimated_download = sum(segment.get('estimated_download_mb', 0) for segment in plan)
            
            remote_segments = [s for s in plan if s.get('is_remote', False)]
            
            if remote_segments:
                logger.info(
                    f"Video processing optimization: "
                    f"Using {total_processing_duration:.1f}s of {total_original_duration:.1f}s available video content"
                )
                
                if total_estimated_download > 0:
                    logger.info(f"Estimated bandwidth usage: {total_estimated_download:.1f} MB")
                
                # time_saved = max(0, total_original_duration - target_duration)
                # if time_saved > 0:
                #     logger.info(f"Optimization benefit: Avoiding processing of {time_saved:.1f}s excess content")
            
        except Exception as e:
            logger.error(f"Error logging optimization benefits: {e}")
    
    def _log_environment_info(self):
        """Log system environment information for debugging"""
        try:
            import platform
            import os
            import psutil
            import socket
            
            # System info
            logger.info("System environment info",
                       platform=platform.platform(),
                       python_version=platform.python_version(),
                       cpu_count=os.cpu_count(),
                       hostname=socket.gethostname())
            
            # Memory info
            # memory = psutil.virtual_memory()
            # logger.info("Memory info",
            #            total_gb=round(memory.total / (1024**3), 2),
            #            available_gb=round(memory.available / (1024**3), 2),
            #            percent_used=memory.percent)
            
            # Network info
            # try:
            #     # Test DNS servers
            #     import subprocess
            #     result = subprocess.run(['nslookup', 'storage.googleapis.com'], 
            #                           capture_output=True, text=True, timeout=5)
            #     logger.info("DNS test result", 
            #                return_code=result.returncode,
            #                stdout_preview=result.stdout[:200] if result.stdout else None)
            # except Exception as dns_test_error:
            #     logger.warning("DNS test failed", error=str(dns_test_error))
            
            # Environment variables that might affect networking
            # relevant_env_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'GOOGLE_APPLICATION_CREDENTIALS']
            # env_info = {}
            # for var in relevant_env_vars:
            #     value = os.environ.get(var)
            #     env_info[var] = 'SET' if value else 'NOT_SET'
            
            # logger.info("Network environment variables", env_vars=env_info)
            
        except Exception as env_error:
            logger.warning("Environment info logging failed", error=str(env_error))
    
    async def _log_network_diagnostics(self, url: str):
        """Log network diagnostics for remote URLs"""
        try:
            import socket
            import time
            from urllib.parse import urlparse
            
            # Parse URL to get hostname
            parsed = urlparse(url)
            hostname = parsed.hostname or 'storage.googleapis.com'
            
            # DNS lookup timing
            dns_start = time.time()
            try:
                ip_address = socket.gethostbyname(hostname)
                dns_time = time.time() - dns_start
                logger.info("DNS resolution completed", 
                           hostname=hostname, 
                           ip_address=ip_address,
                           dns_time_ms=round(dns_time * 1000, 2))
            except Exception as dns_error:
                dns_time = time.time() - dns_start
                logger.error("DNS resolution failed", 
                            hostname=hostname,
                            dns_time_ms=round(dns_time * 1000, 2),
                            error=str(dns_error))
            
            # Test HTTP connectivity for GCS URLs
            if url.startswith(('http', 'gs://')):
                try:
                    # Convert gs:// to https:// for testing
                    if url.startswith('gs://'):
                        test_url = url.replace('gs://', 'https://storage.googleapis.com/')
                    else:
                        test_url = url
                    
                    # Test HEAD request timing
                    import aiohttp
                    head_start = time.time()
                    
                    timeout = aiohttp.ClientTimeout(total=10)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.head(test_url) as response:
                            head_time = time.time() - head_start
                            logger.info("HTTP HEAD request completed",
                                       url=test_url,
                                       status=response.status,
                                       head_time_ms=round(head_time * 1000, 2),
                                       content_length=response.headers.get('content-length'),
                                       content_type=response.headers.get('content-type'))
                            
                except Exception as http_error:
                    head_time = time.time() - head_start
                    logger.error("HTTP HEAD request failed",
                                url=url,
                                head_time_ms=round(head_time * 1000, 2),
                                error=str(http_error))
            
        except Exception as diag_error:
            logger.warning("Network diagnostics failed", error=str(diag_error))
    
    def _run_ffmpeg_with_logging(self, ffmpeg_output):
        """Run FFmpeg with real-time progress logging - synchronous method for executor"""
        try:
            logger.info("FFmpeg subprocess starting")
            import subprocess
            import time

            # Get the command as list
            cmd_list = ffmpeg.compile(ffmpeg_output, overwrite_output=True)
            logger.info("About to execute FFmpeg command", cmd=cmd_list)

            # Use Popen for real-time output streaming
            process = subprocess.Popen(
                cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Combine stderr with stdout
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True
            )

            logger.info("FFmpeg process started, monitoring output...")
            stdout_lines = []
            last_progress_time = time.time()

            # Read output line by line in real-time
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    line = output.strip()
                    stdout_lines.append(line)

                    # Log progress updates every 10 seconds or on frame/time updates
                    current_time = time.time()
                    if (current_time - last_progress_time >= 10.0) or \
                       any(keyword in line.lower() for keyword in ['frame=', 'time=', 'speed=']):
                        logger.info("FFmpeg progress", output=line)
                        last_progress_time = current_time

            # Wait for process to complete
            return_code = process.poll()

            logger.info("FFmpeg subprocess finished",
                       return_code=return_code,
                       total_output_lines=len(stdout_lines))

            # Join all output for potential error analysis
            full_output = '\n'.join(stdout_lines)

            if return_code != 0:
                logger.error("FFmpeg process failed",
                           return_code=return_code,
                           last_10_lines=stdout_lines[-10:] if len(stdout_lines) >= 10 else stdout_lines)
                raise subprocess.CalledProcessError(return_code, cmd_list, full_output, "")

            logger.info("FFmpeg process completed successfully")
            return full_output, ""

        except Exception as e:
            logger.error("Error in FFmpeg execution", error=str(e), error_type=type(e).__name__)
            raise
    
    async def apply_chroma_key(
        self,
        base_video_path: str,
        greenscreen_url: str,
        output_path: str,
        chroma_options: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Apply chroma key (green/black screen) effect to video

        Args:
            base_video_path: Path to the base video file (local)
            greenscreen_url: URL to the greenscreen effect video
            output_path: Path for the output video
            chroma_options: Chroma key configuration options
                - color: Color to key out (default: '000000' for black, '00FF00' for green)
                - similarity: Color similarity threshold 0.0-1.0 (default: 0.1)
                - blend: Blend amount 0.0-1.0 (default: 0.8)

        Returns:
            Path to the output video with chroma key applied

        FFmpeg command equivalent:
            ffmpeg -i sample.mp4 -i fire2_v.mp4 -filter_complex "[1:v]colorkey=000000:0.1:0.8[tmp];[0:v][tmp]overlay" out2.mp4
        """
        try:
            # Default chroma key options
            options = {
                'color': '000000',  # Black by default
                'similarity': 0.1,
                'blend': 0.8
            }
            if chroma_options:
                options.update(chroma_options)

            logger.info(
                "Starting chroma key processing",
                base_video=base_video_path,
                greenscreen_url=greenscreen_url,
                output_path=output_path,
                options=options
            )

            # Download greenscreen video
            greenscreen_path = await self._download_media_file(greenscreen_url, "greenscreen")

            # Create FFmpeg filter complex for chroma key
            # Input 0: base video
            # Input 1: greenscreen video
            base_input = ffmpeg.input(base_video_path)
            greenscreen_input = ffmpeg.input(greenscreen_path)

            # Apply colorkey filter to greenscreen video (makes specific color transparent)
            # Then overlay it on top of base video
            greenscreen_keyed = greenscreen_input.video.filter(
                'colorkey',
                options['color'],
                options['similarity'],
                options['blend']
            )

            # For green chroma key, apply additional filter for darker green (#008000)
            if options['color'] == '00FF00':
                greenscreen_keyed = greenscreen_keyed.filter(
                    'colorkey',
                    '008000',  # Darker green color
                    options['similarity'],
                    options['blend']
                )
                logger.info("Applied additional chroma key for darker green (#008000)")

            # Overlay the keyed greenscreen on the base video
            output_stream = ffmpeg.overlay(
                base_input.video,
                greenscreen_keyed
            )

            # Output with audio from base video
            output = ffmpeg.output(
                output_stream,
                base_input.audio,
                output_path,
                vcodec='libx264',
                acodec='aac',
                preset='ultrafast'
            )

            # Execute FFmpeg command
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: output.run(overwrite_output=True, quiet=False)
            )

            logger.info(
                "Chroma key processing completed",
                output_path=output_path
            )

            return output_path

        except Exception as e:
            logger.error("Chroma key processing failed", error=str(e))
            raise VideoProcessingError(f"Chroma key processing failed: {e}")

    async def _cleanup_temp_files(self, job_id: str):
        """Clean up temporary files for a job"""
        try:
            for temp_file in self.temp_dir.glob(f"*{job_id}*"):
                if temp_file.is_file():
                    temp_file.unlink()

            # Also clean up other temporary files
            for temp_file in self.temp_dir.glob("temp_*"):
                if temp_file.is_file():
                    # Remove files older than 1 hour
                    if time.time() - temp_file.stat().st_mtime > 3600:
                        temp_file.unlink()
                        
        except Exception as e:
            logger.warning("Error cleaning up temporary files", job_id=job_id, error=str(e))

    async def _cleanup_temp_files_except_output(self, job_id: str, output_path_to_preserve: str):
        """Clean up temporary files for a job but preserve the specified output file"""
        try:
            for temp_file in self.temp_dir.glob(f"*{job_id}*"):
                if temp_file.is_file() and str(temp_file) != output_path_to_preserve:
                    temp_file.unlink()
                    logger.info("Cleaned up temp file", file_path=str(temp_file))
            
            # Preserve the output file for further processing
            logger.info("Preserved output file for further processing", 
                       output_path=output_path_to_preserve,
                       file_exists=os.path.exists(output_path_to_preserve))
            
            # Also clean up other temporary files (but not job-specific ones)
            for temp_file in self.temp_dir.glob("temp_*"):
                if temp_file.is_file() and job_id not in str(temp_file):
                    # Remove files older than 1 hour
                    if time.time() - temp_file.stat().st_mtime > 3600:
                        temp_file.unlink()
                        
        except Exception as e:
            logger.warning("Error cleaning up temporary files", job_id=job_id, error=str(e))
    
    async def create_video_from_images(
        self,
        image_config: Dict[str, Any],
        audio_duration: float,
        user_id: str,
        job_id: str,
        options: Optional[Dict[str, Any]] = None,
        camera_movements: Optional[List[str]] = None,
        is_final_video: bool = False
    ) -> str:
        """
        Create video from image(s) - supports both single image and image timeline

        Args:
            image_config: Image configuration with type and data
            audio_duration: Duration of the audio file (determines video length)
            user_id: User ID for GCS path organization
            job_id: Job ID for GCS path organization (also used as project_id)
            options: FFmpeg processing options
            camera_movements: Optional list of camera movement effects for each clip
            is_final_video: If True, upload to 'videos' folder as final video (video-only mode).
                           If False, upload to 'output' folder as intermediate file (default).

        Returns:
            GCS URL of the generated video
        """
        start_time = time.time()
        
        try:
            logger.info(
                "Starting image-to-video conversion",
                job_id=job_id,
                config_type=image_config.get('type'),
                audio_duration=audio_duration
            )
            
            # Default options
            default_options = {
                'resolution': '1280x720',
                'fps': 25,
                'video_codec': 'libx264',
                'preset': 'ultrafast',
                'crf': 23
            }
            
            if options:
                default_options.update(options)
            
            config_type = image_config.get('type', 'single_image')
            
            if config_type == 'single_image':
                # video_url = await self._create_single_image_video(
                #     image_config, audio_duration, user_id, job_id, default_options
                # )
                pass

            elif config_type == 'image_timeline':
                video_url = await self._create_timeline_video(
                    image_config, audio_duration, user_id, job_id, default_options, camera_movements,
                    is_final_video=is_final_video
                )
            else:
                raise ValueError(f"Unsupported image config type: {config_type}")
            
            processing_time = time.time() - start_time
            logger.info(
                "Image-to-video conversion completed",
                job_id=job_id,
                processing_time=processing_time,
                result_url=video_url
            )
            
            return video_url
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                "Image-to-video conversion failed",
                job_id=job_id,
                error=str(e),
                processing_time=processing_time
            )
            raise VideoProcessingError(f"Image-to-video conversion failed: {e}")
    
    # async def _create_single_image_video(
    #     self,
    #     image_config: Dict[str, Any],
    #     duration: float,
    #     user_id: str,
    #     job_id: str,
    #     options: Dict[str, Any]
    # ) -> str:
    #     """Create video from a single image"""
        
    #     image_url = image_config.get('image_url') or image_config.get('background_image_url')
    #     if not image_url:
    #         raise ValueError("Image URL is required for single image video")
        
    #     # Download image file
    #     image_path = await self._download_media_file(image_url, "image")
        
    #     # Create output path
    #     output_filename = f"image_background_{job_id}.mp4"
    #     output_path = self.temp_dir / output_filename
        
    #     try:
    #         # Create video from single image using FFmpeg
    #         stream = ffmpeg.input(
    #             str(image_path),
    #             loop=1,
    #             t=duration,
    #             framerate=options['fps']
    #         )
            
    #         # Check if zoom effect is requested
    #         #enable_zoom = options.get('enable_zoom_effect', False)
    #         enable_zoom = True
    #         width, height = map(int, options['resolution'].split('x'))
            
    #         if enable_zoom:
    #             # Apply zoom effect using the clean ffmpeg-python implementation
    #             total_frames = int(duration * options['fps'])
                
    #             logger.info(f"Applying zoom effect: {width}x{height}, {total_frames} frames", 
    #                       job_id=job_id)
                
    #             # Apply zoom effect filter chain exactly as in zoom_effect_ffmpeg_python.py
    #             stream = (
    #                 stream
    #                 .video
    #                 .filter('scale', width, -2)
    #                 .filter('setsar', 1, 1)
    #                 .filter('crop', width, height)
    #                 .filter('scale', 8000, -1)
    #                 .filter('zoompan',
    #                        z='zoom+0.001',
    #                        x='iw/2-(iw/zoom/2)',
    #                        y='ih/2-(ih/zoom/2)',
    #                        d=total_frames,
    #                        s=f'{width}x{height}',
    #                        fps=options['fps'])
    #             )
                
    #             logger.info(f"Applied zoom effect successfully", job_id=job_id)
                
    #         else:
    #             # Original logic without zoom effect
    #             # Check if we should use center crop for aspect ratio handling
    #             aspect_ratio = options.get('aspect_ratio', '16:9')
    #             use_center_crop = self._should_use_center_crop(aspect_ratio)
                
    #             if use_center_crop:
    #                 # Apply center crop scaling for vertical formats like 9:16
                    
    #                 # Scale to fill the target dimensions (maintains original aspect ratio, may overflow)
    #                 stream = ffmpeg.filter(
    #                     stream,
    #                     'scale',
    #                     width=width,
    #                     height=height,
    #                     force_original_aspect_ratio='increase'  # Scale up to fill, may crop
    #                 )
                    
    #                 # Center crop to exact dimensions
    #                 stream = ffmpeg.filter(
    #                     stream,
    #                     'crop',
    #                     width,
    #                     height,
    #                     '(iw-ow)/2',  # Center horizontally
    #                     '(ih-oh)/2'   # Center vertically
    #                 )
                    
    #                 logger.info(f"Applied center crop for {aspect_ratio} aspect ratio", 
    #                           job_id=job_id, resolution=options['resolution'])
    #             else:
    #                 # Use traditional scale to fit (maintains aspect ratio, adds letterbox)
    #                 stream = ffmpeg.filter(
    #                     stream,
    #                     'scale',
    #                     options['resolution'],
    #                     force_original_aspect_ratio='decrease'
    #                 )
                    
    #                 logger.info(f"Applied scale to fit for {aspect_ratio} aspect ratio", 
    #                           job_id=job_id, resolution=options['resolution'])
            
    #         stream = ffmpeg.output(
    #             stream,
    #             str(output_path),
    #             vcodec=options['video_codec'],
    #             preset=options['preset'],
    #             crf=options['crf'],
    #             r=options['fps'],
    #             pix_fmt='yuv420p'
    #         )
            
    #         # Run FFmpeg
    #         ffmpeg.run(stream, overwrite_output=True, quiet=True)
            
    #         # Upload to GCS
    #         video_url = await self.gcs_service.upload_file(
    #             str(output_path),
    #             user_id,
    #             job_id,
    #             output_filename,
    #             "output"
    #         )
            
    #         # Generate signed URL for FFmpeg access (extract bucket and blob from GCS URL)
    #         if video_url.startswith('https://storage.googleapis.com/'):
    #             url_parts = video_url.replace('https://storage.googleapis.com/', '').split('/', 1)
    #             if len(url_parts) == 2:
    #                 bucket_name, blob_path = url_parts
    #                 signed_url = await self.gcs_service.generate_signed_url(
    #                     bucket_name=bucket_name,
    #                     blob_name=blob_path,
    #                     expiration_minutes=120  # 2 hours for video processing
    #                 )
    #                 if signed_url:
    #                     logger.info("Generated signed URL for image background video", 
    #                               original_url=video_url[:50] + "..." if len(video_url) > 50 else video_url,
    #                               signed_url_length=len(signed_url))
    #                     return signed_url
    #                 else:
    #                     logger.warning("Failed to generate signed URL for background video, using original", url=video_url)
    #                     return video_url
    #             else:
    #                 logger.warning("Could not parse GCS URL for signing", url=video_url)
    #                 return video_url
    #         else:
    #             return video_url
            
    #     finally:
    #         # Clean up temp files
    #         # if image_path.exists():
    #         #     image_path.unlink()
    #         # if output_path.exists():
    #         #     output_path.unlink()
    #         pass
    
    async def _create_timeline_video(
        self,
        image_config: Dict[str, Any],
        duration: float,
        user_id: str,
        job_id: str,
        options: Dict[str, Any],
        camera_movements: Optional[List[str]] = None,
        is_final_video: bool = False
    ) -> str:
        """Create video from image timeline with transitions"""

        # Check if xfade transitions are requested
        use_xfade_transitions = image_config.get('use_xfade_transitions', True)
        if use_xfade_transitions:
            logger.info("Using xfade transitions for timeline video", job_id=job_id)
            return await self._create_timeline_video_with_xfade(
                image_config, duration, user_id, job_id, options, camera_movements,
                is_final_video=is_final_video
            )

        # Use existing timeline video creation logic
        
        timeline_segments = image_config.get('timeline_segments', [])
        if not timeline_segments:
            raise ValueError("Timeline segments are required for timeline video")
        
        # Download all images and convert timeline positions to absolute seconds
        downloaded_images = []
        for i, segment in enumerate(timeline_segments):
            image_url = segment.get('image_url')
            if image_url:
                image_path = await self._download_media_file(image_url, "image")
                image_path = await self._upscale_storyboard_image_if_requested(
                    image_path,
                    job_id,
                    i,
                    options,
                )
                
                # Get timeline positions (might be normalized 0-1 or already in seconds)
                raw_start = segment.get('start_time', 0)
                raw_end = segment.get('end_time', 1)
                
                # Convert to absolute seconds based on audio duration
                # If values are between 0-1, they're normalized and need conversion
                if raw_start <= 1.0 and raw_end <= 1.0:
                    start_seconds = raw_start * duration
                    end_seconds = raw_end * duration
                    logger.info(f"Converting normalized timeline: {raw_start}-{raw_end} -> {start_seconds:.3f}s-{end_seconds:.3f}s")
                else:
                    # Values are already in seconds
                    start_seconds = raw_start
                    end_seconds = raw_end
                    logger.info(f"Using absolute timeline: {start_seconds:.3f}s-{end_seconds:.3f}s")
                
                downloaded_images.append({
                    'path': image_path,
                    'start_time': start_seconds,
                    'end_time': end_seconds,
                    'transition_type': segment.get('transition_type', 'cut'),
                    'raw_start': raw_start,  # Keep original for debugging
                    'raw_end': raw_end
                })
        
        if not downloaded_images:
            raise ValueError("No valid images found in timeline")
        
        try:
            logger.info("Creating timeline video", 
                       job_id=job_id, 
                       num_images=len(downloaded_images),
                       total_duration=duration,
                       options=options)
            
            # Create output path
            output_filename = f"timeline_background_{job_id}.mp4"
            output_path = self.temp_dir / output_filename
            
            # Log the actual timeline data for debugging
            logger.info(f"Input audio duration: {duration}s")
            for i, img_data in enumerate(downloaded_images):
                segment_duration = img_data['end_time'] - img_data['start_time']
                logger.info(f"Image {i}: start={img_data['start_time']}s, end={img_data['end_time']}s, duration={segment_duration}s")
            
            # Don't adjust durations - use the actual timeline positions
            # The issue might be that we're extending short durations unnecessarily
            
            # Sort images by start time to create proper timeline
            sorted_images = sorted(downloaded_images, key=lambda x: x['start_time'])
            logger.info(f"Creating timeline with {len(sorted_images)} images sorted by start time")
            
            # Parse resolution
            width, height = map(int, options['resolution'].split('x'))
            fps = min(options.get('fps', 25), 10)  # Cap at 10fps for image videos
            
            # Create a base timeline covering the full duration
            # We'll use the first image as base and overlay others at specific times
            base_image = sorted_images[0]
            
            # Create base stream for the actual audio duration (not sum of segments)
            base_stream = ffmpeg.input(
                str(base_image['path']),
                loop=1,
                t=duration,  # Use actual audio duration, not sum of segments
                framerate=fps
            )
            
            # Define aspect ratio handling variables (needed for overlay processing later)
            aspect_ratio = options.get('aspect_ratio', '16:9')
            use_center_crop = self._should_use_center_crop(aspect_ratio)
            enable_zoom = options.get('enable_zoom_effect', False)
            # Force enable zoom for testing
            enable_zoom = True
            logger.info(f"Zoom effect enabled: {enable_zoom}", job_id=job_id)
            # Apply standard scaling/cropping (zoom will be applied at the end)
            if use_center_crop:
                # Apply center crop scaling for vertical formats like 9:16
                base_stream = ffmpeg.filter(
                    base_stream,
                    'scale',
                    width=width,
                    height=height,
                    force_original_aspect_ratio='increase'  # Scale up to fill, may crop
                )
                
                # Center crop to exact dimensions
                base_stream = ffmpeg.filter(
                    base_stream,
                    'crop',
                    width,
                    height,
                    '(iw-ow)/2',  # Center horizontally
                    '(ih-oh)/2'   # Center vertically
                )

                # Normalize SAR and pixel format for compatibility
                base_stream = ffmpeg.filter(base_stream, 'setsar', '1/1')
                base_stream = ffmpeg.filter(base_stream, 'format', 'yuv420p')

                logger.info(f"Applied center crop for timeline base image, aspect ratio: {aspect_ratio}",
                          job_id=job_id, resolution=options['resolution'])
                
                # Zoom will be applied to final concatenated stream for efficiency
            else:
                # Use traditional scale to fit with padding (maintains aspect ratio, adds letterbox)
                base_stream = ffmpeg.filter(
                    base_stream,
                    'scale',
                    width=width,
                    height=height,
                    force_original_aspect_ratio='decrease'
                )
                
                base_stream = ffmpeg.filter(
                    base_stream,
                    'pad',
                    width=width,
                    height=height,
                    x='(ow-iw)/2',
                    y='(oh-ih)/2',
                    color='black'
                )

                # Normalize SAR and pixel format for compatibility
                base_stream = ffmpeg.filter(base_stream, 'setsar', '1/1')
                base_stream = ffmpeg.filter(base_stream, 'format', 'yuv420p')

                logger.info(f"Applied scale to fit with padding for timeline base image, aspect ratio: {aspect_ratio}",
                          job_id=job_id, resolution=options['resolution'])
                
                # Zoom will be applied to final concatenated stream for efficiency
            
            # If we have multiple images, create overlays at specific times
            if len(sorted_images) > 1:
                logger.info("Creating timeline with overlays for multiple images")
                current_stream = base_stream
                
                # For very short durations, use a simpler approach
                if duration < 5.0:  # If less than 5 seconds, use segment-based approach
                    logger.info("Using simplified approach for short duration video")
                    
                    # Create individual segments and concatenate them
                    segments = []
                    for i, img_data in enumerate(sorted_images):
                        start_time = img_data['start_time'] 
                        end_time = img_data['end_time']
                        segment_duration = max(0.1, end_time - start_time)  # Minimum 0.1s
                        
                        logger.info(f"Creating segment {i}: {start_time}s-{end_time}s (duration: {segment_duration}s)")
                        
                        # Create segment using the exact approach from zoom_effect_ffmpeg_python.py
                        logger.info(f"Creating segment {i} with zoom effect: {start_time}s-{end_time}s (duration: {segment_duration}s)")
                        
                        # Create input stream (no loop needed for zoompan)
                        input_stream = ffmpeg.input(str(img_data['path']))
                        
                        # Calculate total frames for this segment
                        segment_total_frames = int(segment_duration * fps)
                        
                        # Apply video filters using zoom_effect_ffmpeg_python.py approach
                        if enable_zoom:
                            # Use center crop method from zoom_effect_ffmpeg_python.py
                            segment_stream = (
                                input_stream
                                .filter('scale', width*4, height*4, force_original_aspect_ratio='increase')
                                .filter('crop', width*4, height*4, '(iw-ow)/2', '(ih-oh)/2')
                                .filter('zoompan',
                                       z='min(zoom+0.0008,1.3)',    # Zoom rate with max limit
                                       x='iw/2-(iw/zoom/2)',        # Center X
                                       y='ih/2-(ih/zoom/2)',        # Center Y
                                       d=segment_total_frames,       # Duration in frames
                                       s=f'{width}x{height}',       # Output size
                                       fps=fps)                     # FPS
                                .filter('setsar', '1/1')            # Normalize SAR for concat compatibility
                                .filter('format', 'yuv420p')        # Normalize pixel format for concat compatibility
                            )
                        else:
                            # No zoom - just apply standard scaling
                            segment_stream = (
                                input_stream
                                .filter('scale', width, height, force_original_aspect_ratio='increase')
                                .filter('crop', width, height, '(iw-ow)/2', '(ih-oh)/2')
                                .filter('setsar', '1/1')            # Normalize SAR for concat compatibility
                                .filter('format', 'yuv420p')        # Normalize pixel format for concat compatibility
                            )
                        
                        segments.append(segment_stream)
                    
                    # Concatenate segments
                    if not segments:
                        logger.warning("No segments created, using base stream")
                        concatenated = base_stream
                    elif len(segments) > 1:
                        concatenated = ffmpeg.concat(*segments, v=1, a=0)
                    else:
                        concatenated = segments[0]
                        
                else:
                    # Use same segment-based approach for longer videos too
                    logger.info("Using segment-based approach for longer duration video")
                    
                    # Create individual segments and concatenate them (same as short duration)
                    segments = []
                    for i, img_data in enumerate(sorted_images):
                        start_time = img_data['start_time'] 
                        end_time = img_data['end_time']
                        segment_duration = max(0.1, end_time - start_time)  # Minimum 0.1s
                        
                        logger.info(f"Creating segment {i}: {start_time}s-{end_time}s (duration: {segment_duration}s)")
                        
                        # Create segment using the exact approach from zoom_effect_ffmpeg_python.py
                        logger.info(f"Creating segment {i} with zoom effect: {start_time}s-{end_time}s (duration: {segment_duration}s)")
                        
                        # Create input stream (no loop needed for zoompan)
                        input_stream = ffmpeg.input(str(img_data['path']))
                        
                        # Calculate total frames for this segment
                        segment_total_frames = int(segment_duration * fps)
                        
                        # Apply video filters using zoom_effect_ffmpeg_python.py approach
                        if enable_zoom:
                            # Use center crop method from zoom_effect_ffmpeg_python.py
                            segment_stream = (
                                input_stream
                                .filter('scale', width*4, height*4, force_original_aspect_ratio='increase')
                                .filter('crop', width*4, height*4, '(iw-ow)/2', '(ih-oh)/2')
                                .filter('zoompan',
                                       z='min(zoom+0.0008,1.3)',    # Zoom rate with max limit
                                       x='iw/2-(iw/zoom/2)',        # Center X
                                       y='ih/2-(ih/zoom/2)',        # Center Y
                                       d=segment_total_frames,       # Duration in frames
                                       s=f'{width}x{height}',       # Output size
                                       fps=fps)                     # FPS
                                .filter('setsar', '1/1')            # Normalize SAR for concat compatibility
                                .filter('format', 'yuv420p')        # Normalize pixel format for concat compatibility
                            )
                        else:
                            # No zoom - just apply standard scaling
                            segment_stream = (
                                input_stream
                                .filter('scale', width, height, force_original_aspect_ratio='increase')
                                .filter('crop', width, height, '(iw-ow)/2', '(ih-oh)/2')
                                .filter('setsar', '1/1')            # Normalize SAR for concat compatibility
                                .filter('format', 'yuv420p')        # Normalize pixel format for concat compatibility
                            )
                        
                        segments.append(segment_stream)
                    
                    # Concatenate segments
                    if not segments:
                        logger.warning("No segments created, using base stream")
                        concatenated = base_stream
                    elif len(segments) > 1:
                        concatenated = ffmpeg.concat(*segments, v=1, a=0)
                    else:
                        concatenated = segments[0]
            else:
                logger.info("Using single image for entire timeline")
                # Apply the same zoom approach for single image
                if enable_zoom:
                    logger.info("Applying zoom effect to single image")
                    total_frames = int(duration * fps)
                    
                    # Create input stream (no loop needed for zoompan)
                    input_stream = ffmpeg.input(str(sorted_images[0]['path']))
                    
                    # Apply video filters using zoom_effect_ffmpeg_python.py approach
                    concatenated = (
                        input_stream
                        .filter('scale', width*4, height*4, force_original_aspect_ratio='increase')
                        .filter('crop', width*4, height*4, '(iw-ow)/2', '(ih-oh)/2')
                        .filter('zoompan',
                               z='min(zoom+0.0008,1.3)',    # Zoom rate with max limit
                               x='iw/2-(iw/zoom/2)',        # Center X
                               y='ih/2-(ih/zoom/2)',        # Center Y
                               d=total_frames,               # Duration in frames
                               s=f'{width}x{height}',       # Output size
                               fps=fps)                     # FPS
                        .filter('setsar', '1/1')            # Normalize SAR for consistency
                        .filter('format', 'yuv420p')        # Normalize pixel format for consistency
                    )
                else:
                    # No zoom - use the base stream we already created
                    concatenated = base_stream
            
            # Prepare output options with safe defaults
            output_options = {
                'vcodec': options.get('video_codec', 'libx264'),
                'preset': options.get('preset', 'ultrafast'),
                'r': min(options.get('fps', 25), 10),  # Cap framerate for image videos
                'pix_fmt': 'yuv420p'
            }
            
            # Add CRF only if specified (avoid undefined parameter error)
            if 'crf' in options:
                output_options['crf'] = options['crf']
            else:
                output_options['crf'] = 23  # Default CRF for good quality
            
            logger.info("Creating FFmpeg output with options", output_options=output_options)
            
            # Safety check: ensure concatenated is defined
            if 'concatenated' not in locals():
                logger.error("concatenated variable not defined - this should not happen")
                raise ValueError("Internal error: concatenated stream not properly initialized")
            
            # Zoom effect is now applied per segment using the working example approach
            
            # Output final video
            output = ffmpeg.output(
                concatenated,
                str(output_path),
                **output_options
            )
            
            # Run FFmpeg with better error handling
            logger.info("Starting FFmpeg execution for timeline video")
            try:
                ffmpeg.run(output, overwrite_output=True, quiet=False)  # Show errors
                logger.info("FFmpeg execution completed successfully")
            except ffmpeg.Error as e:
                logger.error("FFmpeg execution failed", 
                           stderr=e.stderr.decode() if e.stderr else "No stderr",
                           stdout=e.stdout.decode() if e.stdout else "No stdout")
                raise ValueError(f"FFmpeg execution failed: {e.stderr.decode() if e.stderr else str(e)}")
            
            # Upload to GCS
            video_url = await self.gcs_service.upload_file(
                str(output_path),
                user_id,
                job_id,
                output_filename,
                "output"
            )
            
            # Generate signed URL for FFmpeg access (extract bucket and blob from GCS URL)
            if video_url.startswith('https://storage.googleapis.com/'):
                url_parts = video_url.replace('https://storage.googleapis.com/', '').split('/', 1)
                if len(url_parts) == 2:
                    bucket_name, blob_path = url_parts
                    signed_url = await self.gcs_service.generate_signed_url(
                        bucket_name=bucket_name,
                        blob_name=blob_path,
                        expiration_minutes=120  # 2 hours for video processing
                    )
                    if signed_url:
                        logger.info("Generated signed URL for timeline background video", 
                                  original_url=video_url[:50] + "..." if len(video_url) > 50 else video_url,
                                  signed_url_length=len(signed_url))
                        return signed_url
                    else:
                        logger.warning("Failed to generate signed URL for timeline background video, using original", url=video_url)
                        return video_url
                else:
                    logger.warning("Could not parse GCS URL for signing", url=video_url)
                    return video_url
            else:
                return video_url
            
        finally:
            # Clean up temp files
            # for img_data in downloaded_images:
            #     if img_data['path'].exists():
            #         img_data['path'].unlink()
            # if output_path.exists():
            #     output_path.unlink()
            pass

    async def _create_timeline_video_with_xfade(
        self,
        image_config: Dict[str, Any],
        duration: float,
        user_id: str,
        job_id: str,
        options: Dict[str, Any],
        camera_movements: Optional[List[str]] = None,
        is_final_video: bool = False
    ) -> str:
        """Create timeline video using xfade transitions between images"""

        timeline_segments = image_config.get('timeline_segments', [])
        if not timeline_segments:
            raise ValueError("Timeline segments are required for xfade timeline video")

        # For single segment, create a simple video without transitions
        if len(timeline_segments) == 1:
            logger.info("Single timeline segment detected, creating video without transitions", job_id=job_id)
            return await self._create_single_segment_video(
                timeline_segments[0], duration, user_id, job_id, options
            )

        try:
            logger.info(
                "Creating timeline video with xfade transitions",
                job_id=job_id,
                num_segments=len(timeline_segments),
                total_duration=duration
            )

            # Extract image URLs from timeline segments
            image_urls = []
            transitions = []
            segment_durations = []
            greenscreen_effects = []

            for segment in timeline_segments:
                image_url = segment.get('image_url')

                if image_url:
                    image_urls.append(image_url)
                    # Get transition type, default to 'fade'
                    transition_type = segment.get('transition_type', 'fade')
                    # Map transition types if needed
                    if transition_type == 'cut':
                        transition_type = 'fade'  # Default fallback
                    transitions.append(transition_type)

                    # Calculate segment duration
                    start_seconds = segment.get('start_time', 0)
                    end_seconds = segment.get('end_time', 1)

                    # # Convert to absolute seconds if normalized
                    # if raw_start <= 1.0 and raw_end <= 1.0:
                    #     start_seconds = raw_start * duration
                    #     end_seconds = raw_end * duration
                    # else:
                    #     start_seconds = raw_start
                    #     end_seconds = raw_end

                    segment_duration = max(0.5, end_seconds - start_seconds)  # Minimum 0.5s
                    segment_durations.append(segment_duration)

                    # Extract greenscreen effect URL (None if not set)
                    greenscreen_effect = segment.get('greenscreen_effect')
                    greenscreen_effects.append(greenscreen_effect)

                    #logger.info(f'.......................................{segment}')
                    #logger.info(f'.......................................{segment_duration}')


            if len(image_urls) < 2:
                raise ValueError("Need at least 2 valid image URLs for xfade timeline")


            # Use the transition duration from options or default
            transition_duration = options.get('transition_duration', 0.5)

            # Get default transition types for multi-scene xfade
            default_transitions = ['fade', 'slidedown', 'smoothleft', 'pixelize', 'circleopen']

            # Use first few transitions or repeat as needed
            final_transitions = []
            for i in range(len(image_urls) - 1):  # n-1 transitions for n images
                if i < len(transitions):
                    final_transitions.append(transitions[i])
                else:
                    final_transitions.append(default_transitions[i % len(default_transitions)])

            logger.info(
                "Using xfade parameters",
                job_id=job_id,
                segment_duration=segment_duration,
                transition_duration=transition_duration,
                final_transitions=final_transitions
            )

            # OPTION 1: Use the multi-scene xfade method (single-pass, higher memory usage)
            # return await self.create_multi_scene_video_with_xfade(
            #     image_urls=image_urls,
            #     user_id=user_id,
            #     job_id=job_id,
            #     durations=segment_durations,
            #     transition_duration=transition_duration,
            #     transitions=final_transitions,
            #     camera_movements=camera_movements,
            #     processing_options=options,
            #     upload_result=True
            # )

            # OPTION 2: Use the concat demuxer method (memory-efficient, no re-encoding)
            # Uncomment below and comment out OPTION 1 above to test the concat demuxer approach
            return await self.create_multi_scene_video_concat_demuxer(
                image_urls=image_urls,
                user_id=user_id,
                job_id=job_id,
                durations=segment_durations,
                transition_duration=transition_duration,
                transitions=final_transitions,
                camera_movements=camera_movements,
                greenscreen_effects=greenscreen_effects,
                processing_options=options,
                upload_result=True,
                is_final_video=is_final_video
            )

        except Exception as e:
            logger.error(
                "Timeline video with xfade creation failed",
                job_id=job_id,
                error=str(e)
            )
            raise VideoProcessingError(f"Timeline video with xfade creation failed: {e}")

    def _create_doodle_effect_video(self, image_path: str, duration: float, width: int, height: int, fps: int = 24, speed: str = 'fast', color_fill_mode: str = 'dots') -> Path:
        """
        Create a doodle drawing effect video from a static image.
        Two-pass animation: first draws black outlines, then colors in, with hold at end.

        Args:
            image_path: Path to the source image file
            duration: Total duration of the effect
            width: Output video width
            height: Output video height
            fps: Frames per second
            speed: Animation speed ('slow' or 'fast')
            color_fill_mode: Color fill mode ('dots' for random dots top-to-bottom, 'path' for progressive path-following)

        Returns:
            Path to the generated MP4 file
        """
        logger.info(
            "Creating doodle effect video",
            image_path=image_path,
            duration=duration,
            speed=speed,
            color_fill_mode=color_fill_mode
        )

        if cv2 is None or cairo is None or np is None:
            raise VideoProcessingError(
                "Doodle effect requires opencv-python-headless, pycairo, and numpy"
            )

        # Dynamic timing based on speed
        if speed == 'slow':
            # Slow formula: (duration-1)/2 for each phase, 1s hold
            ANIMATION_DURATION = max(2.0, duration - 1.0)  # Ensure minimum 2s for animation
            OUTLINE_DURATION = ANIMATION_DURATION / 2
            COLOR_DURATION = ANIMATION_DURATION / 2
        else:  # 'fast'
            # Fast formula: duration/4 for each phase, 1/2 static hold
            OUTLINE_DURATION = duration / 4
            COLOR_DURATION = duration / 4

        OUTLINE_BRUSH = 8
        COLOR_BRUSH = 90

        # Load and process image
        img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise VideoProcessingError(f"Could not load image: {image_path}")

        # Resize and center
        h, w = img.shape[:2]
        scale = min(width / w, height / h)
        new_w, new_h = int(w * scale), int(h * scale)
        img_resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

        offset_x = (width - new_w) // 2
        offset_y = (height - new_h) // 2

        # Extract black outlines (threshold < 80)
        gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
        black_threshold = 200
        black_mask = gray < black_threshold
        img_black_only = np.ones_like(img_resized) * 255
        img_black_only[black_mask] = img_resized[black_mask]

        # Full color image
        img_final_color = img_resized.astype(np.uint8)

        # Edge detection for drawing paths
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)  # Less blur for more detail
        edges = cv2.Canny(blurred, 30, 100)  # Balanced edge detection
        # - Lower values (e.g., 50, 150) = MORE lines detected                                                                                                                                                                                                                     
        # - Higher values (e.g., 100, 200) = FEWER lines detected   

        # RETR_LIST gets all contours, CHAIN_APPROX_SIMPLE reduces redundant points
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        logger.info(f"Found {len(contours)} raw contours from edge detection")

        # Build paths from contours
        paths = []
        total_pixels = 0
        filtered_count = 0

        for cnt in contours:
            # Filter out small contours
            arc_len = cv2.arcLength(cnt, False)
            if arc_len < 50:  # Minimum contour length
                # - Lower value (e.g., 100) = MORE lines (includes shorter lines)                                                                                                                                                                                                          
                # - Higher value (e.g., 300-400) = FEWER lines (only longer lines)    
                continue
            filtered_count += 1
            # Light approximation for balance between detail and performance
            # - Lower value (e.g., 0.005) = MORE detailed/complex lines                                                                                                                                                                                                                
            # - Higher value (e.g., 0.02) = SIMPLER/straighter lines 
            epsilon = 0.01 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, False)
            approx = approx.reshape(-1, 2)  # Flatten to (n_points, 2)

            points = []
            for point in approx:
                x, y = point
                points.append((int(x) + offset_x, int(y) + offset_y))

            segment_len = 0
            for i in range(1, len(points)):
                p1 = points[i-1]
                p2 = points[i]
                dist = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
                segment_len += dist

            paths.append({
                "points": points,
                "length": segment_len,
                "start_y": points[0][1]
            })
            total_pixels += segment_len

        logger.info(f"Kept {filtered_count} contours after filtering (min length: 200px)")
        logger.info(f"Total path length: {total_pixels:.0f} pixels")

        # Sort paths top-to-bottom, left-to-right
        paths.sort(key=lambda p: p["points"][0][1] + (p["points"][0][0]/1000.0))

        # Create Cairo surfaces
        h_img, w_img, c = img_black_only.shape

        # Black outline surface
        black_rgb = cv2.cvtColor(img_black_only, cv2.COLOR_BGR2RGB).astype(np.uint8)
        black_rgbx = np.dstack([black_rgb, np.zeros((h_img, w_img), dtype=np.uint8)])
        black_bgrx = black_rgbx[:, :, [2, 1, 0, 3]].copy()
        black_pixel_data = black_bgrx.flatten()
        black_surf = cairo.ImageSurface.create_for_data(
            black_pixel_data, cairo.FORMAT_RGB24, w_img, h_img, w_img*4
        )

        # Color surface
        col_rgb = cv2.cvtColor(img_final_color, cv2.COLOR_BGR2RGB).astype(np.uint8)
        col_rgbx = np.dstack([col_rgb, np.zeros((h_img, w_img), dtype=np.uint8)])
        col_bgrx = col_rgbx[:, :, [2, 1, 0, 3]].copy()
        pixel_data = col_bgrx.flatten()
        col_surf = cairo.ImageSurface.create_for_data(
            pixel_data, cairo.FORMAT_RGB24, w_img, h_img, w_img*4
        )

        # Create full-size surfaces
        full_col_surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        tmp_ctx = cairo.Context(full_col_surf)
        tmp_ctx.set_source_surface(col_surf, offset_x, offset_y)
        tmp_ctx.paint()

        full_black_surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        tmp_ctx2 = cairo.Context(full_black_surf)
        tmp_ctx2.set_source_surface(black_surf, offset_x, offset_y)
        tmp_ctx2.paint()

        # Pre-generate random dots for 'dots' color fill mode (ensures consistency across frames)
        num_dots = 10000  # Total number of dots to cover the image
        dot_radius = 10   # Size of each dot
        np.random.seed(42)  # Fixed seed for reproducibility across frames
        dots_x = np.random.randint(0, width, num_dots)
        dots_y = np.random.randint(0, height, num_dots)
        # Add randomness to Y for sorting (so dots don't appear in perfect horizontal lines)
        random_offset = np.random.uniform(-80, 80, num_dots)
        sort_y = dots_y + random_offset
        # Sort dots by Y (with randomness) so they appear top to bottom
        sorted_indices = np.argsort(sort_y)
        dots_x = dots_x[sorted_indices]
        dots_y = dots_y[sorted_indices]

        def make_frame(t):
            """Generate frame at time t"""
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
            ctx = cairo.Context(surface)

            # White background
            ctx.set_source_rgb(1, 1, 1)
            ctx.paint()

            is_outline_phase = t < OUTLINE_DURATION
            is_color_phase = OUTLINE_DURATION <= t < (OUTLINE_DURATION + COLOR_DURATION)
            is_hold_phase = t >= (OUTLINE_DURATION + COLOR_DURATION)

            # PHASE 1: BLACK OUTLINES
            if is_outline_phase:
                progress = t / OUTLINE_DURATION
                target_dist = progress * total_pixels

                outline_mask = cairo.ImageSurface(cairo.FORMAT_A8, width, height)
                outline_ctx = cairo.Context(outline_mask)
                outline_ctx.set_source_rgba(1, 1, 1, 1)
                outline_ctx.set_line_width(OUTLINE_BRUSH)
                outline_ctx.set_line_cap(cairo.LINE_CAP_ROUND)
                outline_ctx.set_line_join(cairo.LINE_JOIN_ROUND)

                current_dist = 0
                for path in paths:
                    points = path["points"]
                    path_len = path["length"]

                    if current_dist + path_len < target_dist:
                        outline_ctx.move_to(*points[0])
                        for p in points[1:]:
                            outline_ctx.line_to(*p)
                        outline_ctx.stroke()
                        current_dist += path_len
                    elif current_dist < target_dist:
                        outline_ctx.move_to(*points[0])
                        seg_dist = current_dist
                        for i in range(1, len(points)):
                            p1, p2 = points[i-1], points[i]
                            dist = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
                            if seg_dist + dist >= target_dist:
                                ratio = (target_dist - seg_dist) / dist if dist > 0 else 0
                                cur_x = p1[0] + (p2[0]-p1[0]) * ratio
                                cur_y = p1[1] + (p2[1]-p1[1]) * ratio
                                outline_ctx.line_to(cur_x, cur_y)
                                break
                            else:
                                outline_ctx.line_to(*p2)
                                seg_dist += dist
                        outline_ctx.stroke()
                        break

                ctx.save()
                ctx.set_source_surface(full_black_surf, 0, 0)
                ctx.mask_surface(outline_mask, 0, 0)
                ctx.restore()

            # PHASE 2: COLOR IN
            if is_color_phase:
                # Show all completed black outlines
                outline_mask = cairo.ImageSurface(cairo.FORMAT_A8, width, height)
                outline_ctx = cairo.Context(outline_mask)
                outline_ctx.set_source_rgba(1, 1, 1, 1)
                outline_ctx.set_line_width(OUTLINE_BRUSH)
                outline_ctx.set_line_cap(cairo.LINE_CAP_ROUND)
                outline_ctx.set_line_join(cairo.LINE_JOIN_ROUND)

                for path in paths:
                    points = path["points"]
                    outline_ctx.move_to(*points[0])
                    for p in points[1:]:
                        outline_ctx.line_to(*p)
                    outline_ctx.stroke()

                ctx.save()
                ctx.set_source_surface(full_black_surf, 0, 0)
                ctx.mask_surface(outline_mask, 0, 0)
                ctx.restore()

                # Progressive color fill
                color_t = t - OUTLINE_DURATION
                progress = min(color_t / COLOR_DURATION, 1.0)

                color_mask = cairo.ImageSurface(cairo.FORMAT_A8, width, height)
                color_ctx = cairo.Context(color_mask)
                color_ctx.set_source_rgba(1, 1, 1, 1)

                if color_fill_mode == 'dots':
                    # Random dots color fill mode (top-to-bottom with random dots)
                    # Use pre-generated dots for consistency across frames
                    num_dots_to_draw = int(progress * num_dots)
                    for i in range(num_dots_to_draw):
                        color_ctx.arc(dots_x[i], dots_y[i], dot_radius, 0, 2 * math.pi)
                        color_ctx.fill()
                else:
                    # Path-following color fill mode (original progressive fill)
                    target_dist = progress * total_pixels
                    color_ctx.set_line_cap(cairo.LINE_CAP_ROUND)
                    color_ctx.set_line_join(cairo.LINE_JOIN_ROUND)

                    total_paths = len(paths)
                    last_n_paths = 4  # Last 4 paths get big brush

                    current_dist = 0
                    for path_idx, path in enumerate(paths):
                        points = path["points"]
                        path_len = path["length"]

                        # Use big brush for last 4 paths
                        if path_idx >= total_paths - last_n_paths:
                            color_ctx.set_line_width(1000)
                        else:
                            color_ctx.set_line_width(COLOR_BRUSH)

                        if current_dist + path_len < target_dist:
                            color_ctx.move_to(*points[0])
                            for p in points[1:]:
                                color_ctx.line_to(*p)
                            color_ctx.stroke()
                            current_dist += path_len
                        elif current_dist < target_dist:
                            color_ctx.move_to(*points[0])
                            seg_dist = current_dist
                            for i in range(1, len(points)):
                                p1, p2 = points[i-1], points[i]
                                dist = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
                                if seg_dist + dist >= target_dist:
                                    ratio = (target_dist - seg_dist) / dist if dist > 0 else 0
                                    cur_x = p1[0] + (p2[0]-p1[0]) * ratio
                                    cur_y = p1[1] + (p2[1]-p1[1]) * ratio
                                    color_ctx.line_to(cur_x, cur_y)
                                    break
                                else:
                                    color_ctx.line_to(*p2)
                                    seg_dist += dist
                            color_ctx.stroke()
                            break

                # Apply masked color fill
                ctx.save()
                ctx.set_source_surface(full_col_surf, 0, 0)
                ctx.mask_surface(color_mask, 0, 0)
                ctx.restore()

                # Gradually blend in full image at the end to avoid sudden jump
                # Start blending when progress > 0.75, fully blended at 1.0
                blend_threshold = 0.75
                if progress > blend_threshold:
                    # Calculate blend opacity (0 at threshold, 1 at progress=1.0)
                    blend_progress = (progress - blend_threshold) / (1.0 - blend_threshold)
                    blend_opacity = blend_progress

                    # Draw full image on top with increasing opacity to smoothly fill gaps
                    ctx.save()
                    ctx.set_source_surface(full_col_surf, 0, 0)
                    ctx.paint_with_alpha(blend_opacity)
                    ctx.restore()

            # PHASE 3: HOLD (show full original image)
            if is_hold_phase:
                # Display the complete original image without any masking
                ctx.set_source_surface(full_col_surf, 0, 0)
                ctx.paint()

            buf = surface.get_data()
            arr = np.ndarray(shape=(height, width, 4), dtype=np.uint8, buffer=buf)
            return cv2.cvtColor(arr, cv2.COLOR_BGRA2RGB)

        # Generate video using MoviePy
        video = VideoClip(make_frame, duration=duration)

        # Save to temp file
        output_path = Path(tempfile.mktemp(suffix='.mp4', dir='/tmp'))
        video.write_videofile(
            str(output_path),
            fps=fps,
            codec='libx264',
            preset='ultrafast',
            logger=None  # Disable MoviePy's progress bar
        )

        logger.info(
            "Doodle effect video created",
            output_path=str(output_path),
            duration=duration,
            size=f"{width}x{height}",
            speed=speed,
            color_fill_mode=color_fill_mode
        )

        return output_path

    def _apply_pan_movement(self, input_stream, movement_type: str, duration: float, width: int, height: int, fps: int = 25, image_path: str = None, is_video: bool = False):
        """
        Apply pan movement using proven overlay method from simple_pan_effect.py
        Apply zoom movement using zoompan filter
        Apply doodle drawing effect for images only

        Args:
            input_stream: FFmpeg input stream (looped for pan movements)
            movement_type: Type of movement ('pan_right', 'pan_left', 'pan_up', 'pan_down', 'zoom_in', 'zoom_out', 'doodle', 'static')
                          For doodle effects, supports:
                            - 'doodle' or 'doodle_fast' - fast speed, dots mode (default)
                            - 'doodle_slow' - slow speed, dots mode
                            - 'doodle_path' or 'doodle_fast_path' - fast speed, path mode
                            - 'doodle_slow_path' - slow speed, path mode
                            - 'doodle_dots' or 'doodle_fast_dots' - fast speed, dots mode (explicit)
                            - 'doodle_slow_dots' - slow speed, dots mode (explicit)
            duration: Duration of the movement in seconds
            width: Target output width
            height: Target output height
            fps: Frames per second
            image_path: Path to source image (required for zoom_in/zoom_out/doodle)
            is_video: Whether the source is a video file (doodle not supported for videos)

        Returns:
            FFmpeg stream with movement applied
        """
        # Handle doodle effect (images only)
        if movement_type == 'doodle' or movement_type.startswith('doodle_'):
            if is_video:
                logger.warning("Doodle effect not supported for videos, using static")
                return ffmpeg.filter(input_stream, 'scale', width, height)
            if not image_path:
                raise ValueError("image_path required for doodle effect")

            # Extract speed from movement_type (slow or fast)
            speed = 'slow' if 'slow' in movement_type else 'fast'

            # Extract color fill mode from movement_type (dots or path)
            # Default is 'dots' for random dots top-to-bottom effect
            color_fill_mode = 'path' if 'path' in movement_type else 'dots'

            logger.info(f"Doodle effect: speed={speed}, color_fill_mode={color_fill_mode}")

            doodle_video_path = self._create_doodle_effect_video(
                image_path, duration, width, height, fps, speed=speed, color_fill_mode=color_fill_mode
            )
            return ffmpeg.input(str(doodle_video_path))

        # Use the exact scaling factors from simple_pan_effect.py
        scale_factor = 3
        bg_width = width * scale_factor      # 3x scaling for background
        bg_height = height * scale_factor
        fg_width = width * 4                 # 4x scaling for foreground (more movement room)
        fg_height = height * 4

        if movement_type == 'pan_right':
            # Pan from left to right
            bg = ffmpeg.filter(ffmpeg.filter(input_stream, 'scale', bg_width, bg_height, force_original_aspect_ratio='increase'), 'crop', bg_width, bg_height, '(iw-ow)/2', '(ih-oh)/2')
            fg = ffmpeg.filter(ffmpeg.filter(input_stream, 'scale', fg_width, fg_height, force_original_aspect_ratio='increase'), 'crop', fg_width, fg_height, '(iw-ow)/2', '(ih-oh)/2')

            # Movement: -width to 0 over duration
            speed = width / duration
            overlayed = ffmpeg.filter([bg, fg], 'overlay', f'-{width}+t*{speed}', 0)
            effect = ffmpeg.filter(overlayed, 'scale', width, height)

        elif movement_type == 'pan_left':
            # Pan from right to left
            bg = ffmpeg.filter(ffmpeg.filter(input_stream, 'scale', bg_width, bg_height, force_original_aspect_ratio='increase'), 'crop', bg_width, bg_height, '(iw-ow)/2', '(ih-oh)/2')
            fg = ffmpeg.filter(ffmpeg.filter(input_stream, 'scale', fg_width, fg_height, force_original_aspect_ratio='increase'), 'crop', fg_width, fg_height, '(iw-ow)/2', '(ih-oh)/2')

            # Movement: 0 to -width over duration
            speed = width / duration
            overlayed = ffmpeg.filter([bg, fg], 'overlay', f'0-t*{speed}', 0)
            effect = ffmpeg.filter(overlayed, 'scale', width, height)

        elif movement_type == 'pan_down':
            # Pan from top to bottom
            bg = ffmpeg.filter(ffmpeg.filter(input_stream, 'scale', bg_width, bg_height, force_original_aspect_ratio='increase'), 'crop', bg_width, bg_height, '(iw-ow)/2', '(ih-oh)/2')
            fg = ffmpeg.filter(ffmpeg.filter(input_stream, 'scale', fg_width, fg_height, force_original_aspect_ratio='increase'), 'crop', fg_width, fg_height, '(iw-ow)/2', '(ih-oh)/2')

            # Movement: -height to 0 over duration
            speed = height / duration
            overlayed = ffmpeg.filter([bg, fg], 'overlay', 0, f'-{height}+t*{speed}')
            effect = ffmpeg.filter(overlayed, 'scale', width, height)

        elif movement_type == 'pan_up':
            # Pan from bottom to top
            bg = ffmpeg.filter(ffmpeg.filter(input_stream, 'scale', bg_width, bg_height, force_original_aspect_ratio='increase'), 'crop', bg_width, bg_height, '(iw-ow)/2', '(ih-oh)/2')
            fg = ffmpeg.filter(ffmpeg.filter(input_stream, 'scale', fg_width, fg_height, force_original_aspect_ratio='increase'), 'crop', fg_width, fg_height, '(iw-ow)/2', '(ih-oh)/2')

            # Movement: 0 to -height over duration
            speed = height / duration
            overlayed = ffmpeg.filter([bg, fg], 'overlay', 0, f'0-t*{speed}')
            effect = ffmpeg.filter(overlayed, 'scale', width, height)

        elif movement_type == 'zoom_in':
            # Zoom in effect using fast_zoom.py approach with fresh input (no loop)
            logger.info(f"Applying zoom_in movement for duration {duration}s, fps={fps}")
            frames = int(duration * fps)

            # Create fresh input WITHOUT loop/duration - let zoompan generate all frames
            if not image_path:
                raise ValueError("image_path is required for zoom_in movement")

            zoom_input = ffmpeg.input(str(image_path))

            # Apply fast_zoom.py filter chain with center crop
            # Step 1: Scale up significantly with aspect ratio increase
            scaled = ffmpeg.filter(zoom_input, 'scale', width*6, height*6, force_original_aspect_ratio='increase')

            # Step 2: Center crop to exact dimensions
            cropped = ffmpeg.filter(scaled, 'crop', width*6, height*6, '(iw-ow)/2', '(ih-oh)/2')

            # Step 3: Apply zoompan - generates all frames and outputs at final size
            effect = ffmpeg.filter(
                cropped,
                'zoompan',
                z='min(zoom+0.002,3)',   # Zoom speed with max limit of 1.3x
                x='iw/2-(iw/zoom/2)',      # Center X
                y='ih/2-(ih/zoom/2)',      # Center Y
                d=frames,                  # Generate this many frames
                s=f'{width}x{height}',     # Output at final resolution
                fps=fps
            )

        elif movement_type == 'zoom_out':
            logger.info(f"Applying zoom_out movement for duration {duration}s, fps={fps}")
            frames = int(duration * fps)

            if not image_path:
                raise ValueError("image_path is required for zoom_out movement")

            # Create fresh input WITHOUT loop/duration - let zoompan generate all frames
            zoom_input = ffmpeg.input(str(image_path))

            # Apply fast_zoom.py filter chain with center crop
            scaled = ffmpeg.filter(zoom_input, 'scale', width*6, height*6, force_original_aspect_ratio='increase')
            cropped = ffmpeg.filter(scaled, 'crop', width*6, height*6, '(iw-ow)/2', '(ih-oh)/2')

            effect = ffmpeg.filter(
                cropped,
                'zoompan',
                z='max(3-on*0.01,1.0)',   # Zoom out from 2.0x to 1.0x
                x='iw/2-(iw/zoom/2)',      # Keep centered horizontally
                y='ih/2-(ih/zoom/2)',      # Keep centered vertically
                d=frames,                  # Generate this many frames
                s=f'{width}x{height}',     # Output at final resolution
                fps=fps
            )

        else:
            # No movement or unknown movement type - scale preserving aspect ratio, pad with black
            effect = ffmpeg.filter(
                ffmpeg.filter(input_stream, 'scale', width, height, force_original_aspect_ratio='decrease'),
                'pad', width, height, '(ow-iw)/2', '(oh-ih)/2', color='black'
            )

        return effect

    async def create_multi_scene_video_with_xfade(
        self,
        image_urls: List[str],
        user_id: str,
        job_id: str,
        durations: List[float],
        transition_duration: float = 0.5,
        transitions: Optional[List[str]] = None,
        camera_movements: Optional[List[str]] = None,
        processing_options: Optional[Dict[str, Any]] = None,
        upload_result: bool = True
    ) -> str:
        """
        Create a video with multiple scenes, camera movements, and xfade transitions

        Args:
            image_urls: List of GCS URLs or HTTP URLs to image files
            user_id: User ID for GCS path organization
            job_id: Job ID for GCS path organization
            durations: List of durations for each image (seconds)
            transition_duration: Duration of the transition effect (seconds)
            transitions: List of transition types (if None, uses predefined transitions)
            camera_movements: List of camera movements per image ('pan_right', 'pan_left', 'pan_up', 'pan_down', 'zoom_in', 'zoom_out', 'static')
            processing_options: Video processing configuration
            upload_result: Whether to upload result to GCS or return local path

        Returns:
            GCS URL or local path of multi-scene video with xfade transitions

        Raises:
            VideoProcessingError: If video creation fails
        """
        start_time = time.time()

        try:
            if len(image_urls) < 2:
                raise VideoProcessingError("Need at least 2 images for multi-scene video")

            # Default processing options with explicit color range
            options = {
                'resolution': '1280x720',
                'fps': 25,
                'video_codec': 'libx264',
                'audio_codec': 'aac',
                'preset': 'ultrafast',
                'pix_fmt': 'yuv420p',
                'color_range': 'tv',  # Explicit color range to prevent warnings
                'threads': 0  # Use all available threads
            }
            if processing_options:
                options.update(processing_options)

            # Default transition types
            if transitions is None:
                transitions = ['fade', 'slidedown', 'pixelize', 'smoothleft', 'circleopen']

            # Ensure we have enough transitions
            num_transitions_needed = len(image_urls) - 1
            if len(transitions) < num_transitions_needed:
                # Repeat transitions if not enough provided
                transitions = (transitions * ((num_transitions_needed // len(transitions)) + 1))[:num_transitions_needed]

            # Handle camera movements - default, validate, and ensure enough movements
            if camera_movements is None:
                # Default movements cycle through available types
                default_movements = ['pan_right', 'pan_left', 'pan_down', 'pan_up', 'zoom_in', 'doodle', 'static']
                camera_movements = (default_movements * ((len(image_urls) // len(default_movements)) + 1))[:len(image_urls)]
            else:
                # Validate movement types
                valid_movements = {'pan_right', 'pan_left', 'pan_up', 'pan_down', 'zoom_in', 'zoom_out', 'doodle', 'doodle_slow', 'doodle_fast', 'static'}
                for movement in camera_movements:
                    if movement not in valid_movements:
                        logger.warning(f"Invalid camera movement '{movement}', using 'static' instead")
                        camera_movements = [m if m in valid_movements else 'static' for m in camera_movements]
                        break

                # Ensure we have enough movements for all images
                if len(camera_movements) < len(image_urls):
                    # Repeat movements if not enough provided
                    camera_movements = (camera_movements * ((len(image_urls) // len(camera_movements)) + 1))[:len(image_urls)]

            logger.info(
                "🎬 Starting multi-scene xfade video creation (SINGLE-PASS METHOD)",
                job_id=job_id,
                num_images=len(image_urls),
                duration=durations,
                transition_duration=transition_duration,
                transitions=transitions[:num_transitions_needed],
                camera_movements=camera_movements,
                camera_movements_count=len(camera_movements) if camera_movements else 0
            )

            # Download all images
            download_start = time.time()
            image_paths = []
            for i, image_url in enumerate(image_urls):
                image_path = await self._download_media_file(image_url, f"image_{i}")
                image_path = await self._upscale_storyboard_image_if_requested(
                    image_path,
                    job_id,
                    i,
                    options,
                )
                image_paths.append(image_path)
            download_time = time.time() - download_start
            logger.info(f"⏱️ [SINGLE-PASS] Image download completed in {download_time:.2f}s", job_id=job_id)

            # Create output path
            output_path = self.temp_dir / f"multi_scene_xfade_{job_id}.mp4"

            # Parse resolution
            width, height = map(int, options['resolution'].split('x'))

            # Create input streams for all images with camera movements and proper timing
            filter_graph_start = time.time()
            inputs = []
            for i, image_path in enumerate(image_paths):
                # Calculate timing for each image
                if i <= len(image_paths) -2:
                    # Check if the transition after this image is 'none'
                    next_transition = transitions[i] if i < len(transitions) else 'fade'
                    if next_transition == 'none':
                        # No transition after this image, so no extra duration needed
                        t = durations[i]
                        logger.info(f"Image {i+1}: no transition after, duration={durations[i]:.2f}s")
                    else:
                        # Add transition duration for overlap
                        t = durations[i] + transition_duration
                        logger.info(f"Image {i+1}: with {next_transition} transition, duration={t:.2f}s")
                else:
                    # Last image: duration only (no transition after)
                    t = durations[i]

                #logger.info(f'..................duration for segment {i} is: {t}')
                input_stream = ffmpeg.input(image_path, loop=1, t=t, r=options['fps'])

                # Apply camera movement for this image
                movement_type = camera_movements[i]
                logger.info(f"🎬 Applying camera movement for image {i+1}/{len(image_urls)}: '{movement_type}' (duration: {t}s)")

                # Detect if source is a video file
                is_video = self._is_video_segment(image_urls[i])

                if movement_type in ['pan_right', 'pan_left', 'pan_up', 'pan_down', 'zoom_in', 'zoom_out', 'doodle', 'doodle_slow', 'doodle_fast']:
                    # Apply movement using our helper function (includes zoom_in, zoom_out, and doodle)
                    processed_stream = self._apply_pan_movement(input_stream, movement_type, t, width, height, options['fps'], image_path, is_video)
                else:
                    # Static (no movement) - scale preserving aspect ratio, pad with black
                    processed_stream = ffmpeg.filter(
                        ffmpeg.filter(input_stream, 'scale', width, height, force_original_aspect_ratio='decrease'),
                        'pad', width, height, '(ow-iw)/2', '(oh-ih)/2', color='black'
                    )

                inputs.append(processed_stream)

            # Apply transitions sequentially
            current_video = inputs[0]
            current_offset = durations[0]

            for i in range(1, len(inputs)):
                transition_type = transitions[i-1]
                logger.info(f"Applying transition {i}: {transition_type}")

                # Skip transition if type is 'none' - use concat instead
                if transition_type == 'none':
                    logger.info(f"No transition for image {i} - using direct concat (hard cut)")
                    # For 'none', use concat filter for a hard cut (no overlap)
                    current_video = ffmpeg.filter(
                        [current_video, inputs[i]],
                        'concat',
                        n=2,
                        v=1,
                        a=0
                    )
                    # Update offset without transition overlap (no extra duration was added)
                    current_offset += durations[i]
                else:
                    # Apply xfade between current video and next input
                    current_video = ffmpeg.filter(
                        [current_video, inputs[i]],
                        'xfade',
                        transition=transition_type,
                        duration=transition_duration,
                        offset=current_offset
                    )
                    # Update offset accounting for transition overlap
                    current_offset += durations[i]

            filter_graph_time = time.time() - filter_graph_start
            logger.info(f"⏱️ [SINGLE-PASS] Filter graph construction completed in {filter_graph_time:.2f}s", job_id=job_id)

            # Create output with proper framerate control and color range
            output = ffmpeg.output(
                current_video,
                str(output_path),
                vcodec=options['video_codec'],
                pix_fmt=options['pix_fmt'],
                r=options['fps'],
                fps_mode='cfr',  # Use constant framerate mode instead of deprecated -vsync
                color_range='tv',  # Specify color range to avoid deprecated pixel format warning
                preset=options.get('preset', 'ultrafast'),
                threads=options.get('threads', 0)
            )

            logger.info("⏱️ [SINGLE-PASS] Starting FFmpeg execution for multi-scene xfade video", job_id=job_id)
            ffmpeg_start = time.time()

            # Run FFmpeg with proper error handling
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._run_ffmpeg_with_logging,
                output
            )

            ffmpeg_time = time.time() - ffmpeg_start
            logger.info(f"⏱️ [SINGLE-PASS] FFmpeg execution completed in {ffmpeg_time:.2f}s", job_id=job_id)

            # Verify output file was created
            if not output_path.exists():
                raise VideoProcessingError(f"Multi-scene xfade video creation failed - output file not created: {output_path}")

            logger.info(f"Multi-scene xfade video created successfully: {output_path}")

            # Upload result to GCS or return local path
            if upload_result:
                video_url = await self.gcs_service.upload_file(
                    str(output_path),
                    user_id,
                    job_id,
                    f"multi_scene_xfade_{job_id}.mp4",
                    "output"
                )
            else:
                video_url = str(output_path)

            processing_time = time.time() - start_time
            logger.info(
                f"⏱️ [SINGLE-PASS] TOTAL processing time: {processing_time:.2f}s "
                f"(download: {download_time:.2f}s, filter_graph: {filter_graph_time:.2f}s, ffmpeg: {ffmpeg_time:.2f}s)",
                job_id=job_id
            )

            # Generate signed URL for FFmpeg access (extract bucket and blob from GCS URL)
            if video_url.startswith('https://storage.googleapis.com/'):
                url_parts = video_url.replace('https://storage.googleapis.com/', '').split('/', 1)
                if len(url_parts) == 2:
                    bucket_name, blob_path = url_parts
                    signed_url = await self.gcs_service.generate_signed_url(
                        bucket_name=bucket_name,
                        blob_name=blob_path,
                        expiration_minutes=120  # 2 hours for video processing
                    )
                    if signed_url:
                        logger.info("Generated signed URL for timeline background video with XFADE", 
                                  original_url=video_url[:50] + "..." if len(video_url) > 50 else video_url,
                                  signed_url_length=len(signed_url))
                        return signed_url
                    else:
                        logger.warning("Failed to generate signed URL for timeline background video, using original", url=video_url)
                        return video_url
                else:
                    logger.warning("Could not parse GCS URL for signing", url=video_url)
                    return video_url
            else:
                return video_url

            # logger.info(
            #     "Multi-scene xfade video creation completed",
            #     job_id=job_id,
            #     result_url=video_url,
            #     processing_time=processing_time
            # )

            # return result_url

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                "Multi-scene xfade video creation failed",
                job_id=job_id,
                error=str(e),
                processing_time=processing_time
            )
            raise VideoProcessingError(f"Multi-scene xfade video creation failed: {e}")

        finally:
            # Clean up temporary files (but preserve output if not uploaded)
            if upload_result:
                await self._cleanup_temp_files(job_id)
            else:
                await self._cleanup_temp_files_except_output(job_id, str(output_path))

    async def create_multi_scene_video_concat_demuxer(
        self,
        image_urls: List[str],
        user_id: str,
        job_id: str,
        durations: List[float],
        transition_duration: float = 0.5,
        transitions: Optional[List[str]] = None,
        camera_movements: Optional[List[str]] = None,
        greenscreen_effects: Optional[List[Optional[str]]] = None,
        processing_options: Optional[Dict[str, Any]] = None,
        upload_result: bool = True,
        is_final_video: bool = False
    ) -> str:
        """
        Create a video with xfade transitions (memory-efficient hybrid approach)

        This method creates individual video clips first (memory-efficient), then applies
        xfade transitions between them. Benefits:
        - Lower memory per clip (processes one at a time)
        - Supports xfade transitions (fade, slidedown, etc.)
        - Better for Cloud Run memory limits than single-pass approach
        - Can parallelize clip creation in future

        Process:
        1. Create individual clips with camera movements (one at a time)
        2. Apply chroma key (greenscreen) effects if specified
        3. Load encoded clips and apply xfade filter chain
        4. Encode final video with transitions

        Note: This still requires loading all clips for xfade (but they're already encoded),
        which uses less memory than processing raw images in single-pass.

        Args:
            image_urls: List of GCS URLs or HTTP URLs to image files
            user_id: User ID for GCS path organization
            job_id: Job ID for GCS path organization
            durations: List of durations for each image (seconds)
            transition_duration: Duration of the transition effect (seconds)
            transitions: List of transition types (fade, slidedown, etc.)
            camera_movements: List of camera movements per image
            greenscreen_effects: List of greenscreen effect URLs per image (None if no effect)
            processing_options: Video processing configuration
            upload_result: Whether to upload result to GCS or return local path

        Returns:
            GCS URL or local path of video with xfade transitions

        Raises:
            VideoProcessingError: If video creation fails
        """
        start_time = time.time()
        clip_paths = []

        try:
            if len(image_urls) < 2:
                raise VideoProcessingError("Need at least 2 images for multi-scene video")

            # Default processing options
            options = {
                'resolution': '1280x720',
                'fps': 25,
                'video_codec': 'libx264',
                'preset': 'ultrafast',
                'pix_fmt': 'yuv420p',
                'crf': 23
            }
            if processing_options:
                options.update(processing_options)

            # Handle camera movements - default, validate, and ensure enough movements
            if camera_movements is None:
                default_movements = ['pan_right', 'pan_left', 'pan_down', 'pan_up', 'zoom_in', 'doodle', 'static']
                camera_movements = (default_movements * ((len(image_urls) // len(default_movements)) + 1))[:len(image_urls)]
            else:
                valid_movements = {'pan_right', 'pan_left', 'pan_up', 'pan_down', 'zoom_in', 'zoom_out', 'doodle', 'doodle_slow', 'doodle_fast', 'static'}
                for movement in camera_movements:
                    if movement not in valid_movements:
                        logger.warning(f"Invalid camera movement '{movement}', using 'static' instead")
                        camera_movements = [m if m in valid_movements else 'static' for m in camera_movements]
                        break

                if len(camera_movements) < len(image_urls):
                    camera_movements = (camera_movements * ((len(image_urls) // len(camera_movements)) + 1))[:len(image_urls)]

            logger.info(
                "🎬 Starting concat demuxer video creation (HYBRID METHOD - memory-efficient)",
                job_id=job_id,
                num_images=len(image_urls),
                durations=durations,
                camera_movements=camera_movements
            )

            # Parse resolution
            width, height = map(int, options['resolution'].split('x'))

            # Download all media (images and videos) first
            download_start = time.time()
            media_paths = []
            media_types = []  # Track which are videos vs images
            for i, media_url in enumerate(image_urls):
                # Detect media type
                is_video = self._is_video_segment(media_url)
                media_type = "video" if is_video else "image"
                media_types.append(is_video)

                # Download with appropriate type label
                media_path = await self._download_media_file(media_url, f"{media_type}_{i}")
                if not is_video:
                    media_path = await self._upscale_storyboard_image_if_requested(
                        media_path,
                        job_id,
                        i,
                        options,
                    )
                media_paths.append(media_path)

                logger.info(f"Downloaded {media_type} {i+1}/{len(image_urls)}: {media_url}")

            download_time = time.time() - download_start
            logger.info(f"⏱️ [HYBRID] Media download completed in {download_time:.2f}s",
                       job_id=job_id,
                       images_count=sum(1 for is_vid in media_types if not is_vid),
                       videos_count=sum(1 for is_vid in media_types if is_vid))

            # Validate transitions
            if transitions is None:
                transitions = ['fade'] * (len(image_urls) - 1)

            # Ensure we have enough transitions (n-1 for n clips)
            while len(transitions) < len(image_urls) - 1:
                transitions.append('fade')

            # Step 1: Create individual video clips with extended duration for transitions
            clip_creation_start = time.time()
            logger.info("⏱️ [HYBRID] Starting individual clip creation...", job_id=job_id)
            for i, media_path in enumerate(media_paths):
                clip_output_path = self.temp_dir / f"clip_{job_id}_{i:03d}.mp4"

                # Calculate clip duration with transition overlap
                # All clips except the last need extra duration for transition
                if i < len(media_paths) - 1:
                    # Check if the transition after this clip is 'none'
                    next_transition = transitions[i] if i < len(transitions) else 'fade'
                    if next_transition == 'none':
                        # No transition after this clip, so no extra duration needed
                        clip_duration = durations[i]
                        logger.info(f"Clip {i+1}: no transition after, duration={durations[i]:.2f}s")
                    else:
                        # Add transition duration for overlap
                        clip_duration = durations[i] + transition_duration
                        logger.info(f"Clip {i+1}: with {next_transition} transition, duration={clip_duration:.2f}s")
                else:
                    # Last clip - no transition after it
                    clip_duration = durations[i]

                movement_type = camera_movements[i]
                is_video = media_types[i]

                logger.info(
                    f"Creating clip {i+1}/{len(media_paths)}",
                    duration=clip_duration,
                    movement=movement_type,
                    is_video=is_video
                )

                # Branch based on media type
                if is_video:
                    # VIDEO PROCESSING - strip audio, loop if needed, skip camera movements
                    logger.info(f"Processing video segment {i+1}")

                    # Get actual video duration
                    video_duration = await self._get_duration(str(media_path))
                    logger.info(f"Video {i+1}: file duration={video_duration:.2f}s, needed duration={clip_duration:.2f}s")

                    # Create input stream without audio
                    input_stream = ffmpeg.input(str(media_path))
                    video_stream = input_stream.video  # Strip audio by taking only video stream

                    # Handle duration mismatch
                    if video_duration < clip_duration:
                        # Loop video to fill clip duration
                        import math
                        loops_needed = math.ceil(clip_duration / video_duration)
                        logger.info(f"Video {i+1} too short, looping {loops_needed} times")

                        # Use loop filter
                        video_stream = video_stream.filter('loop', loop=loops_needed-1, size=32767)
                        # Trim to exact duration
                        video_stream = video_stream.filter('trim', duration=clip_duration)
                        video_stream = video_stream.filter('setpts', 'PTS-STARTPTS')
                    else:
                        # Trim to clip duration
                        video_stream = video_stream.filter('trim', duration=clip_duration)
                        video_stream = video_stream.filter('setpts', 'PTS-STARTPTS')

                    # Apply only scaling (no camera movements for videos)
                    processed_stream = ffmpeg.filter(video_stream, 'scale', width, height)

                    logger.info(f"Video segment {i+1} processed: scaled, audio stripped, looped if needed")

                else:
                    # IMAGE PROCESSING - existing logic with camera movements
                    logger.info(f"Processing image segment {i+1}")

                    # Create input stream
                    input_stream = ffmpeg.input(str(media_path), loop=1, t=clip_duration, r=options['fps'])

                    # Apply camera movement
                    if movement_type in ['pan_right', 'pan_left', 'pan_up', 'pan_down', 'zoom_in', 'zoom_out', 'doodle', 'doodle_slow', 'doodle_fast']:
                        processed_stream = self._apply_pan_movement(
                            input_stream, movement_type, clip_duration, width, height, options['fps'], media_path, is_video=False
                        )
                    else:
                        # Static - scale preserving aspect ratio, pad with black
                        processed_stream = ffmpeg.filter(
                            ffmpeg.filter(input_stream, 'scale', width, height, force_original_aspect_ratio='decrease'),
                            'pad', width, height, '(ow-iw)/2', '(oh-ih)/2', color='black'
                        )

                # Apply greenscreen effect if specified for this clip
                if greenscreen_effects and i < len(greenscreen_effects) and greenscreen_effects[i]:
                    greenscreen_url = greenscreen_effects[i]
                    logger.info(f"Applying chroma key effect to clip {i}", greenscreen_url=greenscreen_url)

                    # Download greenscreen video
                    greenscreen_path = await self._download_media_file(greenscreen_url, f"greenscreen_{i}")

                    # Create greenscreen input with same duration and fps
                    greenscreen_input = ffmpeg.input(str(greenscreen_path), stream_loop=-1, t=clip_duration, r=options['fps'])

                    # Scale greenscreen to match output dimensions
                    greenscreen_scaled = ffmpeg.filter(greenscreen_input, 'scale', width, height)

                    # Determine chroma key color based on filename
                    chroma_color = self._get_greenscreen_chroma_key_color(greenscreen_url)

                    # Apply colorkey filter to greenscreen with detected background color
                    greenscreen_keyed = ffmpeg.filter(
                        greenscreen_scaled,
                        'colorkey',
                        chroma_color,  # Auto-detected color (black or green)
                        0.1,           # Similarity threshold
                        0.8            # Blend amount
                    )

                    # For green chroma key, apply additional filter for darker green (#008000)
                    if chroma_color == '00FF00':
                        greenscreen_keyed = ffmpeg.filter(
                            greenscreen_keyed,
                            'colorkey',
                            '008000',      # Darker green color
                            0.1,           # Similarity threshold
                            0.8            # Blend amount
                        )
                        logger.info(f"Applied additional chroma key for darker green (#008000) to clip {i}")

                    # Overlay the keyed greenscreen on top of the base video
                    processed_stream = ffmpeg.overlay(processed_stream, greenscreen_keyed)

                    logger.info(f"Chroma key effect applied to clip {i} using color {chroma_color}")

                # Encode individual clip with same settings
                output = ffmpeg.output(
                    processed_stream,
                    str(clip_output_path),
                    vcodec=options['video_codec'],
                    pix_fmt=options['pix_fmt'],
                    r=options['fps'],
                    preset=options['preset'],
                    crf=options['crf'],
                    fps_mode='cfr',
                    color_range='tv'
                )

                # Run FFmpeg for this clip
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    self._run_ffmpeg_with_logging,
                    output
                )

                if not clip_output_path.exists():
                    raise VideoProcessingError(f"Clip {i} creation failed - output not created")

                clip_paths.append(clip_output_path)
                logger.info(f"✓ Clip {i+1}/{len(media_paths)} created successfully")

            clip_creation_time = time.time() - clip_creation_start
            logger.info(f"⏱️ [HYBRID] All clips created in {clip_creation_time:.2f}s ({clip_creation_time/len(media_paths):.2f}s per clip)", job_id=job_id)

            # Step 2: Apply xfade transitions between clips
            xfade_start = time.time()
            logger.info(f"⏱️ [HYBRID] Applying xfade transitions between {len(clip_paths)} clips...", job_id=job_id)

            # Build xfade filter chain
            # Start with first clip
            inputs = []
            for clip_path in clip_paths:
                inputs.append(ffmpeg.input(str(clip_path)))

            # Apply xfade transitions sequentially
            current_video = inputs[0]
            current_offset = durations[0]

            for i in range(1, len(inputs)):
                transition_type = transitions[i-1] if i-1 < len(transitions) else 'fade'
                logger.info(f"Applying xfade transition {i}: {transition_type} at offset {current_offset}s")

                # Skip transition if type is 'none' - use concat instead
                if transition_type == 'none':
                    logger.info(f"No transition for clip {i} - using direct concat (hard cut)")
                    # For 'none', use concat filter for a hard cut (no overlap)
                    current_video = ffmpeg.filter(
                        [current_video, inputs[i]],
                        'concat',
                        n=2,
                        v=1,
                        a=0
                    )
                    # Update offset without transition overlap (no extra duration was added)
                    current_offset += durations[i]
                else:
                    # Apply xfade between current video and next input
                    current_video = ffmpeg.filter(
                        [current_video, inputs[i]],
                        'xfade',
                        transition=transition_type,
                        duration=transition_duration,
                        offset=current_offset
                    )
                    # Update offset accounting for transition overlap
                    current_offset += durations[i]

            # Step 3: Encode final video with xfade transitions
            output_path = self.temp_dir / f"multi_scene_concat_{job_id}.mp4"

            logger.info("⏱️ [HYBRID] Encoding final video with xfade transitions...", job_id=job_id)
            final_encode_start = time.time()

            output = ffmpeg.output(
                current_video,
                str(output_path),
                vcodec=options['video_codec'],
                pix_fmt=options['pix_fmt'],
                r=options['fps'],
                preset=options['preset'],
                crf=options['crf'],
                fps_mode='cfr',
                color_range='tv'
            )

            # Run FFmpeg
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._run_ffmpeg_with_logging,
                output
            )

            final_encode_time = time.time() - final_encode_start
            logger.info(f"⏱️ [HYBRID] Final encoding completed in {final_encode_time:.2f}s", job_id=job_id)

            if not output_path.exists():
                raise VideoProcessingError("Final xfade video creation failed - output not created")

            logger.info(f"✓ Concatenation completed successfully: {output_path}")

            # Upload result to GCS or return local path
            if upload_result:
                # Always upload to "output" folder first
                video_url = await self.gcs_service.upload_file(
                    str(output_path),
                    user_id,
                    job_id,
                    f"multi_scene_concat_{job_id}.mp4",
                    "output"
                )

                # If this is the final video (video-only mode, no audio), also upload to "videos" folder
                if is_final_video:
                    language_code = (processing_options or {}).get('language_code')
                    logger.info(f"🎬 Video-only mode: Uploading final video to 'videos' folder", job_id=job_id)
                    final_video_url = await self.gcs_service.upload_final_video(
                        str(output_path),
                        str(user_id),
                        job_id,
                        language_code=language_code,
                    )
                    logger.info(f"✅ Final video uploaded to 'videos' folder: {final_video_url}", job_id=job_id)
                    # Return the final video URL from "videos" folder
                    video_url = final_video_url
            else:
                video_url = str(output_path)

            processing_time = time.time() - start_time
            logger.info(
                f"⏱️ [HYBRID] TOTAL processing time: {processing_time:.2f}s "
                f"(download: {download_time:.2f}s, clip_creation: {clip_creation_time:.2f}s, final_encode: {final_encode_time:.2f}s)",
                job_id=job_id,
                num_clips=len(clip_paths)
            )

            # Generate signed URL if GCS
            if video_url.startswith('https://storage.googleapis.com/'):
                url_parts = video_url.replace('https://storage.googleapis.com/', '').split('/', 1)
                if len(url_parts) == 2:
                    bucket_name, blob_path = url_parts
                    signed_url = await self.gcs_service.generate_signed_url(
                        bucket_name=bucket_name,
                        blob_name=blob_path,
                        expiration_minutes=120
                    )
                    if signed_url:
                        logger.info("Generated signed URL for concat demuxer video")
                        return signed_url
                    else:
                        logger.warning("Failed to generate signed URL, using original")
                        return video_url
                else:
                    return video_url
            else:
                return video_url

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                "Concat demuxer video creation failed",
                job_id=job_id,
                error=str(e),
                processing_time=processing_time
            )
            raise VideoProcessingError(f"Concat demuxer video creation failed: {e}")

        finally:
            # Clean up temporary files
            try:
                # Remove individual clips
                for clip_path in clip_paths:
                    if clip_path.exists():
                        clip_path.unlink()

                # Remove concat list
                concat_list_path = self.temp_dir / f"concat_list_{job_id}.txt"
                if concat_list_path.exists():
                    concat_list_path.unlink()

                # Clean up other temp files
                if upload_result:
                    await self._cleanup_temp_files(job_id)
                else:
                    await self._cleanup_temp_files_except_output(job_id, str(output_path))
            except Exception as cleanup_error:
                logger.warning(f"Cleanup error: {cleanup_error}")

    async def apply_watermark_overlay(
        self,
        video_url: str,
        watermark_url: str,
        user_id: str,
        job_id: str,
        upload_result: bool = True,
        position: str = "bottom_right",
        opacity: float = 0.82,
        width_ratio: float = 0.18,
        margin_ratio: float = 0.035
    ) -> str:
        """
        Overlay a transparent logo/watermark image onto a corner of a video.

        The watermark is scaled to a conservative fraction of the video width and uses
        the source image alpha channel, so PNG/WebP transparency is preserved.
        """
        if not watermark_url:
            return video_url

        output_path = Path(self.temp_dir) / f"{job_id}_watermark.mp4"

        try:
            video_path = await self._download_media_file(video_url, "watermark_video")
            watermark_path = await self._download_media_file(watermark_url, "watermark_image")

            probe = ffmpeg.probe(video_path)
            video_stream = next((stream for stream in probe.get('streams', []) if stream.get('codec_type') == 'video'), None)
            if not video_stream:
                raise VideoProcessingError("No video stream found for watermark overlay")

            video_width = int(video_stream.get('width') or 1280)
            video_height = int(video_stream.get('height') or 720)
            target_width = max(96, int(video_width * width_ratio))
            margin = max(24, int(min(video_width, video_height) * margin_ratio))

            try:
                from PIL import Image
                with Image.open(watermark_path) as image:
                    image_width = image.width
                target_width = min(target_width, image_width)
            except Exception as image_probe_error:
                logger.warning("Could not probe watermark dimensions; using target width", job_id=job_id, error=str(image_probe_error))

            opacity = min(1.0, max(0.0, opacity))
            normalized_position = (position or "bottom_right").lower().replace("-", "_")
            overlay_positions = {
                "top_left": f"{margin}:{margin}",
                "top_right": f"W-w-{margin}:{margin}",
                "bottom_left": f"{margin}:H-h-{margin}",
                "bottom_right": f"W-w-{margin}:H-h-{margin}",
            }
            overlay_position = overlay_positions.get(normalized_position, overlay_positions["bottom_right"])
            filter_complex = (
                f"[1:v]format=rgba,scale={target_width}:-1,"
                f"colorchannelmixer=aa={opacity}[wm];"
                f"[0:v][wm]overlay={overlay_position}:format=auto[v]"
            )

            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-i", str(watermark_path),
                "-filter_complex", filter_complex,
                "-map", "[v]",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                "-movflags", "+faststart",
                str(output_path),
            ]

            logger.info(
                "Applying watermark overlay",
                job_id=job_id,
                video_width=video_width,
                video_height=video_height,
                watermark_width=target_width,
                margin=margin,
                position=normalized_position,
                opacity=opacity,
            )

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise VideoProcessingError(
                    f"Watermark overlay failed: {stderr.decode(errors='ignore')[:1000]}"
                )

            if not output_path.exists() or output_path.stat().st_size == 0:
                raise VideoProcessingError("Watermark overlay output file not created")

            if upload_result:
                result_url = await self.gcs_service.upload_final_video(
                    str(output_path),
                    str(user_id),
                    job_id,
                    f"Watermarked Video {job_id}",
                    language_code=self.language_code,
                )
            else:
                result_url = str(output_path)

            logger.info("✅ Watermark overlay applied", job_id=job_id, result_url=result_url)
            return result_url

        except Exception as e:
            logger.warning("Watermark overlay failed; returning original video", job_id=job_id, error=str(e))
            return video_url
        finally:
            if upload_result:
                try:
                    if output_path.exists():
                        output_path.unlink()
                except Exception:
                    pass

    async def apply_text_overlays(
        self,
        video_path: str,
        text_overlays: List[Dict],
        user_id: str,
        job_id: str,
        upload_result: bool = True
    ) -> str:
        """
        Burn text overlays onto a video using FFmpeg drawtext filter.

        Args:
            video_path: Local path or GCS URL to input video
            text_overlays: List of text overlay dicts with keys:
                text, startTime, endTime, x (0-100%), y (0-100%),
                fontSize, fontColor, fontWeight, fontFamily,
                backgroundColor, animation
            user_id: User ID for GCS upload path
            job_id: Job ID for temp file naming
            upload_result: Whether to upload result to GCS

        Returns:
            GCS URL or local path of video with text overlays
        """
        if not text_overlays:
            return video_path

        output_path = Path(self.temp_dir) / f"{job_id}_text_overlay.mp4"

        try:
            # Download video if it's a remote URL
            local_video = video_path
            if video_path.startswith('gs://') or video_path.startswith('http'):
                local_video = str(Path(self.temp_dir) / f"{job_id}_text_input.mp4")
                await self._download_http_file(video_path, local_video)

            # Probe video dimensions
            try:
                probe = ffmpeg.probe(local_video)
                video_stream = next(s for s in probe['streams'] if s['codec_type'] == 'video')
                vid_width = int(video_stream['width'])
                vid_height = int(video_stream['height'])
            except Exception:
                vid_width, vid_height = 1280, 720

            def hex_to_ffmpeg_color(hex_color: str, alpha: float = 1.0) -> str:
                """Convert #RRGGBB to FFmpeg 0xRRGGBBAA format"""
                h = hex_color.lstrip('#')
                if len(h) == 6:
                    alpha_hex = format(int(alpha * 255), '02x')
                    return f"0x{h}{alpha_hex}"
                return f"0xFFFFFF{format(int(alpha * 255), '02x')}"

            # Build drawtext filter chain
            drawtext_parts = []
            for tl in text_overlays:
                text = tl.get('text', '').replace("'", "\\'").replace(':', '\\:')
                start_t = float(tl.get('startTime', 0))
                end_t = float(tl.get('endTime', 5))
                x_pct = float(tl.get('x', 50)) / 100.0
                y_pct = float(tl.get('y', 50)) / 100.0
                font_size = int(tl.get('fontSize', 48))
                font_color = hex_to_ffmpeg_color(tl.get('fontColor', '#ffffff'))
                bg_color = tl.get('backgroundColor', 'transparent')
                animation = tl.get('animation', 'none')
                font_family = tl.get('fontFamily', 'Arial')
                font_weight = tl.get('fontWeight', 'bold')

                # Position: center text horizontally/vertically on the specified anchor
                x_expr = f"(w*{x_pct:.4f}-tw/2)"
                y_expr = f"(h*{y_pct:.4f}-th/2)"

                # Clamp to video bounds
                x_expr = f"max(0,min(w-tw,{x_expr}))"
                y_expr = f"max(0,min(h-th,{y_expr}))"

                # Time enable expression
                enable_expr = f"between(t\\,{start_t}\\,{end_t})"

                # Alpha for animation
                fade_dur = min(0.5, (end_t - start_t) * 0.2)
                if animation == 'fade-in':
                    alpha_expr = f"if(lt(t\\,{start_t}+{fade_dur:.3f})\\,(t-{start_t})/{fade_dur:.3f}\\,1)"
                elif animation == 'slide-up':
                    alpha_expr = f"if(lt(t\\,{start_t}+{fade_dur:.3f})\\,(t-{start_t})/{fade_dur:.3f}\\,1)"
                    slide_offset = int(vid_height * 0.05)
                    y_expr = f"({y_expr}-{slide_offset}*max(0,1-(t-{start_t})/{fade_dur:.3f}))"
                elif animation == 'slide-down':
                    alpha_expr = f"if(lt(t\\,{start_t}+{fade_dur:.3f})\\,(t-{start_t})/{fade_dur:.3f}\\,1)"
                    slide_offset = int(vid_height * 0.05)
                    y_expr = f"({y_expr}+{slide_offset}*max(0,1-(t-{start_t})/{fade_dur:.3f}))"
                else:
                    alpha_expr = "1"

                # Try to find font file
                font_path = self.get_font_path(font_family)
                if font_path:
                    font_spec = f"fontfile='{font_path}'"
                else:
                    font_spec = f"font='{font_family}'"

                # Background box
                if bg_color and bg_color != 'transparent':
                    box_color = hex_to_ffmpeg_color(bg_color, 0.7)
                    box_opts = f":box=1:boxcolor={box_color}:boxborderw=10"
                else:
                    box_opts = ""

                drawtext_filter = (
                    f"drawtext={font_spec}:text='{text}'"
                    f":fontsize={font_size}:fontcolor={font_color}@1"
                    f":alpha='{alpha_expr}'"
                    f":x='{x_expr}':y='{y_expr}'"
                    f":enable='{enable_expr}'"
                    f"{box_opts}"
                )
                drawtext_parts.append(drawtext_filter)

            vf_filter = ','.join(drawtext_parts)

            # Apply drawtext via FFmpeg
            video_input = ffmpeg.input(local_video)
            output = ffmpeg.output(
                video_input,
                str(output_path),
                vf=vf_filter,
                **{"c:a": "copy", "c:v": "libx264", "crf": "18", "preset": "fast", "pix_fmt": "yuv420p"}
            )

            cmd = output.compile()
            logger.info(f"Applying {len(text_overlays)} text overlays", job_id=job_id, cmd=' '.join(cmd))
            await asyncio.to_thread(
                output.overwrite_output().run,
                capture_stdout=True,
                capture_stderr=True
            )

            if not output_path.exists():
                raise VideoProcessingError("Text overlay output file not created")

            logger.info(f"✅ Text overlays applied successfully", job_id=job_id)

            if upload_result:
                from video_processor.services.gcs_service import get_gcs_service
                gcs_service = get_gcs_service()
                result_url = await gcs_service.upload_final_video(
                    str(output_path),
                    str(user_id),
                    job_id,
                    f"text_overlay_{job_id}",
                    make_public=False
                )
                return result_url
            else:
                return str(output_path)

        except ffmpeg.Error as e:
            stderr = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"FFmpeg drawtext failed: {stderr}", job_id=job_id)
            logger.warning("Text overlay failed, returning original video", job_id=job_id)
            return video_path
        except Exception as e:
            logger.error(f"Text overlay error: {e}", job_id=job_id)
            return video_path


def get_ffmpeg_processor(language_code: str = None) -> FFmpegProcessor:
    """
    Get FFmpeg processor instance with optional language code.

    Note: Creates a new instance per call to support language-specific processing.
    Previously used singleton pattern but changed to support multi-language videos.

    Args:
        language_code: Optional language code for multi-language support

    Returns:
        FFmpegProcessor instance
    """
    return FFmpegProcessor(language_code=language_code)
