"""
Image processing service for background images and video generation
"""

import os
import uuid
import asyncio
import ffmpeg
import tempfile
import io
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
import logging
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
from services.gcs_service import get_gcs_service
from db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

class ImageService:
    def __init__(self, max_concurrent_jobs: int = 2):
        """Initialize image processing service"""
        self.max_concurrent_jobs = max_concurrent_jobs
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent_jobs)
        self.gcs_service = get_gcs_service()
        self.supabase_client = None
        
        # Try to initialize database connection
        try:
            self.supabase_client = SupabaseClient()
            logger.info("ImageService initialized with database integration")
        except Exception as e:
            logger.warning(f"Failed to initialize database connection: {str(e)}")
            self.supabase_client = None
        
        # Create temporary directory for processing
        self.temp_dir = Path("data/temp/image_processing")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Image validation methods
    async def validate_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Validate image format, size, and dimensions
        
        Args:
            image_bytes: Image data as bytes
            
        Returns:
            Dict with validation results
        """
        try:
            # Run validation in executor to avoid blocking
            return await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._validate_image_sync,
                image_bytes
            )
        except Exception as e:
            logger.error(f"Error validating image: {str(e)}")
            return {
                'valid': False,
                'error': f'Validation failed: {str(e)}'
            }
    
    def _validate_image_sync(self, image_bytes: bytes) -> Dict[str, Any]:
        """Synchronous image validation"""
        try:
            # Check file size (max 10MB)
            max_size_mb = 10
            if len(image_bytes) > max_size_mb * 1024 * 1024:
                return {
                    'valid': False,
                    'error': f'Image too large. Maximum size is {max_size_mb}MB'
                }
            
            # Try to open image with PIL
            try:
                image = Image.open(io.BytesIO(image_bytes))
                width, height = image.size
                format_type = image.format
                mode = image.mode
                
                # Check if it's a valid image format
                supported_formats = {'JPEG', 'PNG', 'WebP', 'GIF'}
                if format_type not in supported_formats:
                    return {
                        'valid': False,
                        'error': f'Unsupported format: {format_type}. Supported: {", ".join(supported_formats)}'
                    }
                
                # Check minimum dimensions (at least 100x100)
                if width < 100 or height < 100:
                    return {
                        'valid': False,
                        'error': f'Image too small. Minimum dimensions are 100x100 pixels. Got: {width}x{height}'
                    }
                
                # Check maximum dimensions (max 4096x4096)
                if width > 4096 or height > 4096:
                    return {
                        'valid': False,
                        'error': f'Image too large. Maximum dimensions are 4096x4096 pixels. Got: {width}x{height}'
                    }
                
                return {
                    'valid': True,
                    'width': width,
                    'height': height,
                    'format': format_type,
                    'mode': mode,
                    'size_bytes': len(image_bytes),
                    'aspect_ratio': round(width / height, 2) if height > 0 else 0
                }
                
            except Exception as e:
                return {
                    'valid': False,
                    'error': f'Invalid image data: {str(e)}'
                }
                
        except Exception as e:
            return {
                'valid': False,
                'error': f'Validation error: {str(e)}'
            }
    
    async def optimize_for_video(
        self, 
        image_bytes: bytes, 
        target_size: tuple = (1080, 1920),
        quality: int = 90
    ) -> Optional[bytes]:
        """
        Optimize image for video use (resize, format conversion)
        
        Args:
            image_bytes: Original image bytes
            target_size: Target dimensions (width, height)
            quality: JPEG quality (1-100)
            
        Returns:
            Optimized image bytes or None if failed
        """
        try:
            return await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._optimize_for_video_sync,
                image_bytes,
                target_size,
                quality
            )
        except Exception as e:
            logger.error(f"Error optimizing image for video: {str(e)}")
            return None
    
    def _optimize_for_video_sync(
        self, 
        image_bytes: bytes, 
        target_size: tuple,
        quality: int
    ) -> Optional[bytes]:
        """Synchronous image optimization"""
        try:
            # Open image
            image = Image.open(io.BytesIO(image_bytes))
            
            # Convert to RGB if necessary
            if image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')
            
            # Calculate new size maintaining aspect ratio
            original_width, original_height = image.size
            target_width, target_height = target_size
            
            # Calculate scaling to fit within target size
            width_ratio = target_width / original_width
            height_ratio = target_height / original_height
            scale_ratio = min(width_ratio, height_ratio)
            
            new_width = int(original_width * scale_ratio)
            new_height = int(original_height * scale_ratio)
            
            # Resize image
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Create output buffer
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=quality, optimize=True)
            
            optimized_bytes = output.getvalue()
            logger.info(f"Optimized image: {len(image_bytes)} -> {len(optimized_bytes)} bytes, size: {new_width}x{new_height}")
            
            return optimized_bytes
            
        except Exception as e:
            logger.error(f"Error in sync image optimization: {str(e)}")
            return None
    
    # Video generation from images
    async def create_video_from_images(
        self,
        timeline: List[Dict[str, Any]],
        audio_duration: float,
        output_path: str,
        video_size: tuple = (1080, 1920),
        fps: int = 30
    ) -> bool:
        """
        Create video from image timeline using FFmpeg
        
        Args:
            timeline: List of timeline segments with image info and timing
            audio_duration: Duration of audio track in seconds
            output_path: Path for output video file
            video_size: Target video resolution (width, height)
            fps: Frames per second
            
        Returns:
            True if successful, False otherwise
        """
        if not timeline:
            logger.error("Empty timeline provided")
            return False
        
        try:
            # Validate timeline
            validation_result = await self._validate_timeline(timeline, audio_duration)
            if not validation_result['valid']:
                logger.error(f"Timeline validation failed: {validation_result['error']}")
                return False
            
            # Process timeline segments
            processed_segments = await self._process_timeline_segments(timeline, video_size)
            if not processed_segments:
                logger.error("Failed to process timeline segments")
                return False
            
            # Generate video using FFmpeg
            success = await self._generate_video_from_segments(
                processed_segments, 
                audio_duration,
                output_path,
                video_size,
                fps
            )
            
            return success
            
        except Exception as e:
            logger.error(f"Error creating video from images: {str(e)}")
            return False
    
    async def _validate_timeline(
        self, 
        timeline: List[Dict[str, Any]], 
        audio_duration: float
    ) -> Dict[str, Any]:
        """Validate timeline for consistency and coverage"""
        try:
            if not timeline:
                return {'valid': False, 'error': 'Empty timeline'}
            
            # Sort timeline by start_time
            sorted_timeline = sorted(timeline, key=lambda x: x.get('start_time', 0))
            
            # Check for gaps and overlaps
            total_coverage = 0
            previous_end = 0
            
            for segment in sorted_timeline:
                start_time = segment.get('start_time', 0)
                end_time = segment.get('end_time', 0)
                
                # Check segment validity
                if end_time <= start_time:
                    return {
                        'valid': False, 
                        'error': f'Invalid segment: end_time ({end_time}) must be greater than start_time ({start_time})'
                    }
                
                # Check for gaps
                if start_time > previous_end and previous_end > 0:
                    logger.warning(f"Gap detected: {previous_end} to {start_time} seconds")
                
                # Check for overlaps
                if start_time < previous_end:
                    return {
                        'valid': False,
                        'error': f'Overlap detected: segment starts at {start_time} but previous ends at {previous_end}'
                    }
                
                total_coverage += (end_time - start_time)
                previous_end = end_time
                
                # Validate image reference
                if 'image_url' not in segment and 'gcs_path' not in segment:
                    return {
                        'valid': False,
                        'error': 'Segment missing image reference (image_url or gcs_path)'
                    }
            
            # Check total coverage vs audio duration
            if total_coverage < audio_duration * 0.95:  # Allow 5% tolerance
                logger.warning(f"Timeline coverage ({total_coverage}s) is less than audio duration ({audio_duration}s)")
            
            return {
                'valid': True,
                'total_coverage': total_coverage,
                'segments': len(sorted_timeline)
            }
            
        except Exception as e:
            return {'valid': False, 'error': f'Timeline validation error: {str(e)}'}
    
    async def _process_timeline_segments(
        self, 
        timeline: List[Dict[str, Any]], 
        video_size: tuple
    ) -> Optional[List[Dict[str, Any]]]:
        """Process and prepare timeline segments for video generation"""
        try:
            processed_segments = []
            
            for segment in timeline:
                try:
                    # Download image if from GCS
                    image_path = None
                    if 'gcs_path' in segment:
                        # Download from GCS to local temp file
                        image_path = await self._download_image_from_gcs(segment['gcs_path'])
                    elif 'image_url' in segment and segment['image_url'].startswith('http'):
                        # Download from URL to local temp file  
                        image_path = await self._download_image_from_url(segment['image_url'])
                    elif 'local_path' in segment:
                        # Use local path directly
                        image_path = segment['local_path']
                    
                    if not image_path or not os.path.exists(image_path):
                        logger.error(f"Could not get image for segment: {segment}")
                        continue
                    
                    # Optimize image for video
                    optimized_path = await self._optimize_image_for_segment(
                        image_path, 
                        video_size,
                        segment.get('start_time', 0)
                    )
                    
                    if optimized_path:
                        processed_segments.append({
                            'image_path': optimized_path,
                            'start_time': segment.get('start_time', 0),
                            'end_time': segment.get('end_time', 0),
                            'duration': segment.get('end_time', 0) - segment.get('start_time', 0),
                            'transition_type': segment.get('transition_type', 'cut'),
                            'transition_duration': segment.get('transition_duration', 0.0)
                        })
                    
                except Exception as e:
                    logger.error(f"Error processing segment: {segment}, error: {str(e)}")
                    continue
            
            return processed_segments if processed_segments else None
            
        except Exception as e:
            logger.error(f"Error processing timeline segments: {str(e)}")
            return None
    
    async def _download_image_from_gcs(self, gcs_path: str) -> Optional[str]:
        """Download image from GCS to temporary file"""
        try:
            # Generate signed URL
            signed_url = await self.gcs_service.generate_signed_url(gcs_path, 1)  # 1 hour expiry
            
            if signed_url:
                return await self._download_image_from_url(signed_url)
            else:
                logger.error(f"Could not generate signed URL for: {gcs_path}")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading image from GCS: {str(e)}")
            return None
    
    async def _download_image_from_url(self, url: str) -> Optional[str]:
        """Download image from URL to temporary file"""
        try:
            import aiohttp
            import aiofiles
            
            # Generate temp file path
            temp_filename = f"img_{uuid.uuid4().hex}.jpg"
            temp_path = self.temp_dir / temp_filename
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.read()
                        
                        async with aiofiles.open(temp_path, 'wb') as f:
                            await f.write(content)
                        
                        logger.info(f"Downloaded image to: {temp_path}")
                        return str(temp_path)
                    else:
                        logger.error(f"Failed to download image: HTTP {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error downloading image from URL: {str(e)}")
            return None
    
    async def _optimize_image_for_segment(
        self, 
        image_path: str, 
        video_size: tuple,
        segment_start: float
    ) -> Optional[str]:
        """Optimize image for specific video segment"""
        try:
            # Generate output path
            output_filename = f"opt_img_{segment_start}_{uuid.uuid4().hex}.jpg"
            output_path = self.temp_dir / output_filename
            
            # Run optimization in executor
            success = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._optimize_image_file_sync,
                image_path,
                str(output_path),
                video_size
            )
            
            return str(output_path) if success else None
            
        except Exception as e:
            logger.error(f"Error optimizing image for segment: {str(e)}")
            return None
    
    def _optimize_image_file_sync(
        self, 
        input_path: str, 
        output_path: str,
        target_size: tuple
    ) -> bool:
        """Synchronous file-based image optimization"""
        try:
            with Image.open(input_path) as image:
                # Convert to RGB
                if image.mode not in ('RGB', 'L'):
                    image = image.convert('RGB')
                
                # Resize to target size maintaining aspect ratio
                image.thumbnail(target_size, Image.Resampling.LANCZOS)
                
                # Create final image with exact target dimensions (letterbox/pillarbox if needed)
                final_image = Image.new('RGB', target_size, (0, 0, 0))
                
                # Center the image
                x_offset = (target_size[0] - image.width) // 2
                y_offset = (target_size[1] - image.height) // 2
                final_image.paste(image, (x_offset, y_offset))
                
                # Save optimized image
                final_image.save(output_path, format='JPEG', quality=90, optimize=True)
                
                logger.info(f"Optimized image saved to: {output_path}")
                return True
                
        except Exception as e:
            logger.error(f"Error in sync image file optimization: {str(e)}")
            return False
    
    async def _generate_video_from_segments(
        self,
        segments: List[Dict[str, Any]],
        audio_duration: float,
        output_path: str,
        video_size: tuple,
        fps: int
    ) -> bool:
        """Generate final video from processed segments using FFmpeg"""
        try:
            # Run FFmpeg processing in executor
            return await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._generate_video_sync,
                segments,
                audio_duration,
                output_path,
                video_size,
                fps
            )
            
        except Exception as e:
            logger.error(f"Error generating video from segments: {str(e)}")
            return False
    
    def _generate_video_sync(
        self,
        segments: List[Dict[str, Any]],
        audio_duration: float,
        output_path: str,
        video_size: tuple,
        fps: int
    ) -> bool:
        """Synchronous video generation using FFmpeg"""
        try:
            width, height = video_size
            temp_files = []
            
            # Generate individual video segments
            for i, segment in enumerate(segments):
                segment_output = self.temp_dir / f"segment_{i}_{uuid.uuid4().hex}.mp4"
                temp_files.append(segment_output)
                
                # Create video segment from image
                (
                    ffmpeg
                    .input(segment['image_path'], loop=1, t=segment['duration'])
                    .output(
                        str(segment_output),
                        vcodec='libx264',
                        r=fps,
                        s=f'{width}x{height}',
                        pix_fmt='yuv420p',
                        preset='fast'
                    )
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True, quiet=True)
                )
                
                logger.info(f"Generated segment {i}: {segment['duration']}s")
            
            # Concatenate segments
            if len(temp_files) == 1:
                # Single segment - just copy
                import shutil
                shutil.copy(str(temp_files[0]), output_path)
            else:
                # Multiple segments - concatenate
                inputs = [ffmpeg.input(str(f)) for f in temp_files]
                video_streams = [inp.video for inp in inputs]
                
                concat_video = ffmpeg.concat(*video_streams, v=1, a=0)
                
                ffmpeg.output(
                    concat_video,
                    output_path,
                    vcodec='libx264',
                    r=fps,
                    preset='fast'
                ).overwrite_output().run(capture_stdout=True, capture_stderr=True, quiet=True)
            
            # Clean up temporary segment files
            for temp_file in temp_files:
                if temp_file.exists():
                    temp_file.unlink()
            
            logger.info(f"Generated video from image timeline: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error in sync video generation: {str(e)}")
            return False
    
    def __del__(self):
        """Cleanup when service is destroyed"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)

# Global instance
_image_service = None

def get_image_service() -> ImageService:
    """Get or create ImageService instance"""
    global _image_service
    if _image_service is None:
        _image_service = ImageService()
    return _image_service