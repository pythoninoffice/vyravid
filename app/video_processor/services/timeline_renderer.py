"""
Timeline Renderer Service for Cloud Video Processor

This module provides video rendering from timeline JSON data with support for:
- Multiple tracks with z-index layering
- Video, image, audio, and text clips
- Transformations (position, scale, rotation, opacity)
- FFmpeg-based compositing with filtergraph generation
"""

import asyncio
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone

import ffmpeg
import structlog
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
from video_processor.models.requests import TimelineData, TimelineClip, TimelineTrack

logger = structlog.get_logger(__name__)


class TimelineRenderError(Exception):
    """Base exception for timeline rendering operations"""
    pass


class AssetDownloadError(TimelineRenderError):
    """Exception raised when asset download fails"""
    pass


class FiltergraphBuildError(TimelineRenderError):
    """Exception raised when filtergraph generation fails"""
    pass


class RenderExecutionError(TimelineRenderError):
    """Exception raised when FFmpeg execution fails"""
    pass


class TimelineRenderer:
    """
    Render videos from timeline JSON data using FFmpeg.

    Supports multiple tracks with video, image, audio, and text clips,
    with transformations and layer compositing based on z-index ordering.
    """

    def __init__(self):
        self.settings = get_settings()
        self.gcs_service = get_gcs_service()

        # Create temporary directory for processing
        self.temp_dir = Path(self.settings.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Processing limits for Cloud Run
        self.max_processing_time = self.settings.max_processing_time_minutes * 60
        self.max_file_size = self.settings.max_file_size_mb * 1024 * 1024

    async def render_timeline(
        self,
        timeline: TimelineData,
        job_id: str,
        output_format: str = "mp4",
        quality: str = "high",
        upscale_mode: str = "none",
        user_id: str = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Render a timeline to video file and upload to GCS.

        Args:
            timeline: Timeline data with tracks and clips
            job_id: Unique job identifier
            output_format: Output format (mp4, webm)
            quality: Quality preset (low, medium, high)

        Returns:
            Tuple of (GCS URL, metadata dict)

        Raises:
            TimelineRenderError: If rendering fails
        """
        start_time = time.time()
        temp_files = []

        try:
            logger.info(
                "timeline_render_started",
                job_id=job_id,
                tracks_count=len(timeline.tracks),
                total_clips=sum(len(track.clips) for track in timeline.tracks),
                duration=timeline.duration,
                canvas_size=f"{timeline.canvas.width}x{timeline.canvas.height}"
            )

            # Log clips with effects for debugging
            clips_with_effects = []
            for track in timeline.tracks:
                for clip in track.clips:
                    has_effect = False
                    if hasattr(clip, 'cameraMovement') and clip.cameraMovement:
                        logger.info(f"📹 Clip '{clip.name}' has camera movement: {clip.cameraMovement}")
                        has_effect = True
                    if hasattr(clip, 'greenscreenEffect') and clip.greenscreenEffect:
                        logger.info(f"🎬 Clip '{clip.name}' has greenscreen effect: {clip.greenscreenEffect}")
                        has_effect = True
                    if hasattr(clip, 'transitionType') and clip.transitionType:
                        logger.info(f"✨ Clip '{clip.name}' has transition: {clip.transitionType}")
                        has_effect = True
                    if has_effect:
                        clips_with_effects.append(clip.name)

            if not clips_with_effects:
                logger.warning("⚠️ No clips with effects found in timeline! Camera movements, greenscreen effects, and transitions will not be applied.")

            # Step 1: Download all assets from GCS
            logger.info("Downloading assets from GCS", job_id=job_id)
            asset_paths = await self._download_assets(timeline, job_id)
            temp_files.extend(asset_paths.values())

            asset_paths = await self._upscale_timeline_images_if_requested(
                timeline,
                asset_paths,
                job_id,
                upscale_mode,
            )
            temp_files.extend(
                path for path in asset_paths.values() if path not in temp_files
            )

            # Step 2: Build FFmpeg filtergraph for compositing
            logger.info("Building FFmpeg filtergraph", job_id=job_id)
            output_path = self.temp_dir / f"{job_id}_output.{output_format}"
            temp_files.append(str(output_path))

            # Step 3: Execute FFmpeg rendering
            logger.info("Executing FFmpeg render", job_id=job_id)
            await self._execute_render(
                timeline,
                asset_paths,
                output_path,
                output_format,
                quality
            )

            # Step 4: Upload result to GCS
            logger.info("Uploading rendered video to GCS", job_id=job_id)
            video_url = await self.gcs_service.upload_final_video(
                local_path=str(output_path),
                user_id=user_id or "timeline_editor",
                job_id=job_id,
                video_title=f"timeline_{job_id}",
                make_public=False
            )

            processing_time = time.time() - start_time

            metadata = {
                "processing_time": processing_time,
                "output_format": output_format,
                "quality": quality,
                "upscale_mode": normalize_upscale_mode(upscale_mode),
                "canvas_size": f"{timeline.canvas.width}x{timeline.canvas.height}",
                "duration": timeline.duration,
                "tracks_count": len(timeline.tracks),
                "total_clips": sum(len(track.clips) for track in timeline.tracks)
            }

            logger.info(
                "timeline_render_completed",
                job_id=job_id,
                processing_time=processing_time,
                video_url=video_url
            )

            return video_url, metadata

        except Exception as e:
            logger.error(
                "timeline_render_failed",
                job_id=job_id,
                error=str(e),
                exc_info=True
            )
            raise TimelineRenderError(f"Timeline rendering failed: {str(e)}")

        finally:
            # Clean up temporary files
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception as e:
                    logger.warning(f"Failed to clean up temp file {temp_file}: {e}")

    async def _upscale_timeline_images_if_requested(
        self,
        timeline: TimelineData,
        asset_paths: Dict[str, str],
        job_id: str,
        upscale_mode: Optional[str],
    ) -> Dict[str, str]:
        """Pre-upscale image clip assets for timeline renders when requested."""
        mode = normalize_upscale_mode(upscale_mode)
        if mode == "none":
            return asset_paths

        image_urls = []
        for track in timeline.tracks:
            for clip in track.clips:
                if clip.src and clip.type == "image" and clip.src in asset_paths:
                    image_urls.append(clip.src)

        unique_image_urls = list(dict.fromkeys(image_urls))
        if not unique_image_urls:
            return asset_paths

        updated_paths = dict(asset_paths)
        for idx, url in enumerate(unique_image_urls):
            input_path = asset_paths[url]
            output_path = str(self.temp_dir / f"timeline_upscaled_{job_id}_{idx:03d}.png")
            logger.info(
                "Pre-upscaling timeline image",
                job_id=job_id,
                image_index=idx,
                mode=mode,
                src=url,
            )
            updated_paths[url] = await asyncio.to_thread(
                upscale_image,
                input_path,
                output_path,
                mode,
                2,
            )

        return updated_paths

    async def _download_assets(
        self,
        timeline: TimelineData,
        job_id: str
    ) -> Dict[str, str]:
        """
        Download all media assets from GCS.

        Args:
            timeline: Timeline data
            job_id: Job identifier

        Returns:
            Dict mapping clip src URLs to local file paths

        Raises:
            AssetDownloadError: If any download fails
        """
        asset_paths = {}
        download_tasks = []

        # Collect all unique asset URLs
        asset_urls = set()
        for track in timeline.tracks:
            for clip in track.clips:
                if clip.src and clip.type in ['video', 'image', 'audio']:
                    asset_urls.add(clip.src)

        logger.info(f"Found {len(asset_urls)} unique assets to download", job_id=job_id)

        # Download assets in parallel
        for i, url in enumerate(asset_urls):
            # Generate local filename
            ext = Path(url.split('?')[0]).suffix or '.mp4'  # Remove query params for ext
            local_path = str(self.temp_dir / f"{job_id}_asset_{i}{ext}")

            download_tasks.append(
                self._download_single_asset(url, local_path, job_id)
            )

        # Wait for all downloads
        try:
            results = await asyncio.gather(*download_tasks, return_exceptions=True)

            # Check for errors
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    raise AssetDownloadError(f"Asset download failed: {result}")

                url, local_path = result
                asset_paths[url] = local_path

            logger.info(
                f"Successfully downloaded {len(asset_paths)} assets",
                job_id=job_id
            )

            return asset_paths

        except Exception as e:
            raise AssetDownloadError(f"Failed to download assets: {str(e)}")

    async def _download_single_asset(
        self,
        url: str,
        local_path: str,
        job_id: str
    ) -> Tuple[str, str]:
        """Download or resolve a single asset."""
        try:
            if os.path.exists(url):
                logger.debug(f"Using local asset: {url}", job_id=job_id)
                return (url, url)

            # Check if it's a GCS URL or HTTP URL
            if url.startswith("gs://") or url.startswith("https://storage.googleapis.com/"):
                await self.gcs_service.download_file(url, local_path)
            else:
                # For HTTP URLs, download using aiohttp
                import aiohttp
                import aiofiles

                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        response.raise_for_status()
                        async with aiofiles.open(local_path, 'wb') as f:
                            await f.write(await response.read())

            logger.debug(f"Downloaded asset: {url} -> {local_path}", job_id=job_id)
            return (url, local_path)

        except Exception as e:
            logger.error(f"Failed to download {url}: {e}", job_id=job_id)
            raise

    async def _download_asset(self, url: str) -> str:
        """
        Download or resolve a single asset (like greenscreen effect) and return local path.

        Args:
            url: URL to download

        Returns:
            Local file path
        """
        if os.path.exists(url):
            return url

        # Generate local filename
        ext = Path(url.split('?')[0]).suffix or '.mp4'
        local_path = str(self.temp_dir / f"effect_{uuid.uuid4()}{ext}")

        # Download using existing method
        _, path = await self._download_single_asset(url, local_path, job_id="greenscreen")
        return path

    async def _pre_render_clip(
        self,
        clip: 'TimelineClip',
        asset_path: str,
        job_id: str,
        canvas_width: int,
        canvas_height: int,
        quality_settings: Dict[str, Any],
        clip_index: int
    ) -> str:
        """
        Pre-render a single clip with all its effects applied.
        This is the hybrid approach: render clips individually (low memory),
        then overlay them on the timeline (supports overlaps).

        Args:
            clip: Timeline clip to render
            asset_path: Path to the clip's source asset
            job_id: Job identifier
            canvas_width: Canvas width in pixels
            canvas_height: Canvas height in pixels
            quality_settings: Rendering quality settings
            clip_index: Index of clip for naming

        Returns:
            Path to pre-rendered clip file
        """
        try:
            # Create output path for pre-rendered clip
            output_path = self.temp_dir / f"{job_id}_prerender_{clip_index:03d}.mp4"

            # Extract settings
            width = canvas_width
            height = canvas_height
            fps = quality_settings['output_params'].get('r', 30)

            # Create looped input stream for images
            if clip.type == 'image':
                input_stream = ffmpeg.input(asset_path, loop=1, t=clip.duration, r=fps)
            else:
                input_stream = ffmpeg.input(asset_path)

            # Apply camera movement if specified
            if hasattr(clip, 'cameraMovement') and clip.cameraMovement:
                logger.info(f"Pre-rendering clip {clip_index} with camera movement: {clip.cameraMovement}")
                # Detect if source is a video
                is_video = clip.type == 'video' if hasattr(clip, 'type') else False
                processed_stream = self._apply_camera_movement(
                    input_stream,
                    clip.cameraMovement,
                    clip.duration,
                    width,
                    height,
                    fps=fps,
                    asset_path=asset_path,
                    is_video=is_video
                )
            else:
                # No camera movement - just scale
                processed_stream = ffmpeg.filter(input_stream, 'scale', width, height)

            # Apply greenscreen effect if specified
            if hasattr(clip, 'greenscreenEffect') and clip.greenscreenEffect:
                logger.info(f"Pre-rendering clip {clip_index} with greenscreen: {clip.greenscreenEffect}")
                greenscreen_url = self._convert_greenscreen_effect_name_to_url(clip.greenscreenEffect)
                greenscreen_path = await self._download_asset(greenscreen_url)

                # Create greenscreen input with looping to match clip duration
                greenscreen_input = ffmpeg.input(str(greenscreen_path), stream_loop=-1, t=clip.duration, r=fps)

                # Scale greenscreen to match dimensions
                greenscreen_scaled = greenscreen_input.filter('scale', width, height)

                # Detect chroma key color
                chroma_color = self._get_greenscreen_chroma_key_color(greenscreen_url)

                # Apply colorkey filter
                greenscreen_keyed = greenscreen_scaled.filter('colorkey', chroma_color, 0.1, 0.8)

                # For green chroma key, apply additional filter for darker green
                if chroma_color == '00FF00':
                    greenscreen_keyed = greenscreen_keyed.filter('colorkey', '008000', 0.1, 0.8)

                # Overlay greenscreen on top of processed stream
                processed_stream = ffmpeg.overlay(processed_stream, greenscreen_keyed)

            # Encode pre-rendered clip
            output = ffmpeg.output(
                processed_stream,
                str(output_path),
                vcodec=quality_settings['vcodec'],
                pix_fmt='yuv420p',
                r=fps,
                preset=quality_settings['output_params'].get('preset', 'medium'),
                crf=quality_settings['output_params'].get('crf', 23),
                fps_mode='cfr',
                color_range='tv'
            )

            # Log the FFmpeg command for debugging
            cmd = output.compile()
            logger.info(f"FFmpeg command for pre-render: {' '.join(cmd)}")

            # Run FFmpeg
            await asyncio.to_thread(
                output.overwrite_output().run,
                capture_stdout=True,
                capture_stderr=True
            )

            if not output_path.exists():
                raise RenderExecutionError(f"Pre-render failed for clip {clip_index}")

            logger.info(f"✓ Pre-rendered clip {clip_index}: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Pre-render failed for clip {clip_index}: {e}")
            raise RenderExecutionError(f"Pre-render failed: {e}")

    async def _concat_simple(
        self,
        prerendered_paths: Dict[int, str],
        media_clips: list,
        audio_clips: list,
        asset_paths: Dict[str, str],
        output_path: Path,
        quality_settings: Dict[str, Any],
        timeline: 'TimelineData'
    ) -> None:
        """
        Simple concatenation using concat demuxer (no transitions).
        Fast and memory-efficient for sequential clips without transitions.
        """
        try:
            # Create concat file listing all pre-rendered clips in order
            concat_file = self.temp_dir / f"concat_{uuid.uuid4().hex[:8]}.txt"

            with open(concat_file, 'w') as f:
                for idx in sorted(prerendered_paths.keys()):
                    clip_path = prerendered_paths[idx]
                    # Escape single quotes in path for concat demuxer
                    escaped_path = str(clip_path).replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            logger.info(f"Created concat file with {len(prerendered_paths)} clips: {concat_file}")

            # Use concat demuxer to concatenate all pre-rendered clips
            video_stream = ffmpeg.input(str(concat_file), format='concat', safe=0)

            # Process audio if present
            if audio_clips:
                logger.info(f"Processing {len(audio_clips)} audio clip(s)")
                audio_inputs = []

                for _, clip in audio_clips:
                    clip_path = asset_paths.get(clip.src)
                    if not clip_path:
                        logger.warning(f"Skipping audio clip, asset not found: {clip.src}")
                        continue

                    audio_stream = ffmpeg.input(clip_path)
                    audio_stream = audio_stream.filter('atrim', start=0, duration=clip.duration)

                    if clip.startTime > 0:
                        delay_ms = int(clip.startTime * 1000)
                        audio_stream = audio_stream.filter('adelay', f'{delay_ms}|{delay_ms}')

                    audio_inputs.append(audio_stream)

                if audio_inputs:
                    if len(audio_inputs) == 1:
                        mixed_audio = audio_inputs[0]
                    else:
                        mixed_audio = ffmpeg.filter(audio_inputs, 'amix', inputs=len(audio_inputs), duration='longest')

                    mixed_audio = mixed_audio.filter('apad', whole_dur=timeline.duration)

                    # Output with audio
                    stream = ffmpeg.output(
                        video_stream,
                        mixed_audio,
                        str(output_path),
                        vcodec=quality_settings['vcodec'],
                        **quality_settings['output_params']
                    )
                else:
                    # Output video only
                    stream = video_stream.output(
                        str(output_path),
                        vcodec=quality_settings['vcodec'],
                        **quality_settings['output_params']
                    )
            else:
                # No audio - output video only
                stream = video_stream.output(
                    str(output_path),
                    vcodec=quality_settings['vcodec'],
                    **quality_settings['output_params']
                )

            # Run FFmpeg
            logger.info(f"Concatenating {len(prerendered_paths)} pre-rendered clips")
            await asyncio.to_thread(
                stream.overwrite_output().run,
                capture_stdout=True,
                capture_stderr=True
            )

            logger.info(f"Concat completed successfully")

        except Exception as e:
            logger.error("Concat execution failed", error=str(e), exc_info=True)
            raise RenderExecutionError(f"Concat failed: {str(e)}")

    async def _concat_prerendered_clips(
        self,
        prerendered_paths: Dict[int, str],
        media_clips: list,
        audio_clips: list,
        asset_paths: Dict[str, str],
        output_path: Path,
        quality_settings: Dict[str, Any],
        timeline: 'TimelineData'
    ) -> None:
        """
        Concatenate pre-rendered clips with xfade transitions support.
        Applies transition effects between sequential clips.
        """
        try:
            # Check if any clips have transitions
            has_transitions = any(
                hasattr(clip, 'transitionType') and clip.transitionType and clip.transitionType != 'cut'
                for _, clip in media_clips
            )

            if not has_transitions:
                # Use simple concat demuxer if no transitions
                logger.info("No transitions detected, using simple concat demuxer")
                return await self._concat_simple(prerendered_paths, media_clips, audio_clips, asset_paths, output_path, quality_settings, timeline)

            # Apply xfade transitions between clips
            logger.info(f"Applying xfade transitions between {len(prerendered_paths)} clips")

            # Load all pre-rendered clips as inputs
            inputs = []
            for idx in sorted(prerendered_paths.keys()):
                clip_path = prerendered_paths[idx]
                inputs.append(ffmpeg.input(clip_path))

            # Apply transitions sequentially
            # Note: xfade transitions cause clips to overlap, so we need to adjust offsets
            current_video = inputs[0]
            current_offset = media_clips[0][1].duration  # Duration of first clip

            for i in range(1, len(inputs)):
                _, clip = media_clips[i]

                # Get transition settings
                transition_type = getattr(clip, 'transitionType', 'fade') or 'fade'
                transition_duration = getattr(clip, 'transitionDuration', 0.5) or 0.5

                # Skip if cut transition
                if transition_type == 'cut':
                    # No transition - just concatenate
                    logger.info(f"Clip {i}: cut transition (no effect)")
                    current_video = ffmpeg.concat(current_video, inputs[i])
                    current_offset += clip.duration
                    continue

                # For xfade: offset is when transition starts (before current video ends)
                # The transition overlaps, so we start it transition_duration before the clip would end
                xfade_offset = current_offset - transition_duration
                logger.info(f"Applying transition {i}: {transition_type} (duration: {transition_duration}s, offset: {xfade_offset}s)")

                # Apply xfade between current video and next input
                current_video = ffmpeg.filter(
                    [current_video, inputs[i]],
                    'xfade',
                    transition=transition_type,
                    duration=transition_duration,
                    offset=xfade_offset
                )

                # Update offset for next transition: add clip duration minus transition overlap
                current_offset += clip.duration - transition_duration

            video_stream = current_video

            # Process audio if present
            if audio_clips:
                logger.info(f"Processing {len(audio_clips)} audio clip(s)")
                audio_inputs = []

                for _, clip in audio_clips:
                    clip_path = asset_paths.get(clip.src)
                    if not clip_path:
                        logger.warning(f"Skipping audio clip, asset not found: {clip.src}")
                        continue

                    audio_stream = ffmpeg.input(clip_path)
                    audio_stream = audio_stream.filter('atrim', start=0, duration=clip.duration)

                    if clip.startTime > 0:
                        delay_ms = int(clip.startTime * 1000)
                        audio_stream = audio_stream.filter('adelay', f'{delay_ms}|{delay_ms}')

                    audio_inputs.append(audio_stream)

                if audio_inputs:
                    if len(audio_inputs) == 1:
                        mixed_audio = audio_inputs[0]
                    else:
                        mixed_audio = ffmpeg.filter(audio_inputs, 'amix', inputs=len(audio_inputs), duration='longest')

                    mixed_audio = mixed_audio.filter('apad', whole_dur=timeline.duration)

                    # Output with audio
                    stream = ffmpeg.output(
                        video_stream,
                        mixed_audio,
                        str(output_path),
                        vcodec=quality_settings['vcodec'],
                        **quality_settings['output_params']
                    )
                else:
                    # Output video only
                    stream = video_stream.output(
                        str(output_path),
                        vcodec=quality_settings['vcodec'],
                        **quality_settings['output_params']
                    )
            else:
                # No audio - output video only
                stream = video_stream.output(
                    str(output_path),
                    vcodec=quality_settings['vcodec'],
                    **quality_settings['output_params']
                )

            # Run FFmpeg
            logger.info(f"Rendering {len(prerendered_paths)} pre-rendered clips with xfade transitions")
            await asyncio.to_thread(
                stream.overwrite_output().run,
                capture_stdout=True,
                capture_stderr=True
            )

            logger.info(f"Xfade transitions applied successfully")

        except Exception as e:
            logger.error("Xfade transition rendering failed", error=str(e), exc_info=True)
            raise RenderExecutionError(f"Xfade rendering failed: {str(e)}")

    async def _execute_render(
        self,
        timeline: TimelineData,
        asset_paths: Dict[str, str],
        output_path: Path,
        output_format: str,
        quality: str
    ) -> None:
        """
        Execute FFmpeg rendering with hybrid approach:
        1. Pre-render clips with effects individually (low memory)
        2. Overlay pre-rendered clips on timeline (supports overlaps)

        Args:
            timeline: Timeline data
            asset_paths: Mapping of URLs to local paths
            output_path: Output video path
            output_format: Output format
            quality: Quality preset
        """
        try:
            # Get quality settings
            quality_settings = self._get_quality_settings(quality)

            # Collect all clips with their track info
            all_clips = []
            for track in timeline.tracks:
                for clip in track.clips:
                    all_clips.append((track.zIndex, clip))

            # Separate media clips (image/video), audio clips, and text clips
            media_clips = [(z, c) for z, c in all_clips if c.type in ['image', 'video'] and c.src]
            audio_clips = [(z, c) for z, c in all_clips if c.type == 'audio' and c.src]
            text_clips = [(z, c) for z, c in all_clips if c.type == 'text']

            if not media_clips and not text_clips and not audio_clips:
                raise RenderExecutionError("No clips found in timeline")

            # Sort media clips by startTime for sequential rendering (timeline order)
            # This ensures clips appear in the video in the order they're placed on the timeline
            media_clips.sort(key=lambda x: x[1].startTime)
            logger.info(f"Sorted {len(media_clips)} media clips by timeline startTime")

            # ===== PHASE 1: Pre-render all clips =====
            logger.info(f"Phase 1: Pre-rendering {len(media_clips)} media clips")
            prerendered_paths: Dict[int, str] = {}  # Map clip index to pre-rendered path
            job_id = str(uuid.uuid4())[:8]

            for idx, (_, clip) in enumerate(media_clips):
                # Check if clip has any effects (for logging purposes)
                has_camera = hasattr(clip, 'cameraMovement') and clip.cameraMovement
                has_greenscreen = hasattr(clip, 'greenscreenEffect') and clip.greenscreenEffect
                has_effects = has_camera or has_greenscreen

                logger.info(f"Clip {idx} ({clip.name}): cameraMovement={getattr(clip, 'cameraMovement', 'None')}, greenscreenEffect={getattr(clip, 'greenscreenEffect', 'None')}, has_effects={has_effects}")

                # Pre-render ALL clips (even those without effects) for consistent timeline ordering
                clip_path = asset_paths.get(clip.src)
                if not clip_path:
                    logger.warning(f"Skipping clip {idx}, asset not found: {clip.src}")
                    continue

                logger.info(f"Pre-rendering clip {idx}/{len(media_clips)-1}" + (" with effects" if has_effects else " (no effects)"))
                prerendered_path = await self._pre_render_clip(
                    clip, clip_path, job_id,
                    timeline.canvas.width, timeline.canvas.height,
                    quality_settings, idx
                )
                prerendered_paths[idx] = prerendered_path
                logger.info(f"✓ Clip {idx} pre-rendered: {prerendered_path}")

            logger.info(f"Phase 1 complete: {len(prerendered_paths)} clips pre-rendered")

            # ===== PHASE 2: Concatenate or overlay clips =====
            # If all clips are pre-rendered and sequential, use concat for better reliability
            all_prerendered = len(prerendered_paths) == len(media_clips)

            if all_prerendered:
                logger.info(f"Phase 2: Concatenating {len(prerendered_paths)} pre-rendered clips")
                # All clips have effects and are pre-rendered - use concat demuxer
                return await self._concat_prerendered_clips(
                    prerendered_paths, media_clips, audio_clips, asset_paths, output_path, quality_settings, timeline
                )

            # Otherwise, fall back to overlay method for mixed content
            logger.info(f"Phase 2: Overlaying clips on timeline canvas")

            # Start with base canvas or first media clip
            if media_clips:
                # Use first media clip as base
                _, base_clip = media_clips[0]

                # Check if clip was pre-rendered (has effects)
                if 0 in prerendered_paths:
                    # Use pre-rendered clip (effects already applied)
                    input_path = prerendered_paths[0]
                    logger.info(f"Using pre-rendered base clip: {input_path}")
                else:
                    # Use original asset
                    input_path = asset_paths.get(base_clip.src)
                    if not input_path:
                        raise RenderExecutionError(f"Asset not found: {base_clip.src}")

                # Get clip dimensions and position
                transform = base_clip.transform
                x = int(transform.x if transform else 0)
                y = int(transform.y if transform else 0)
                scale_x = transform.scaleX if transform else 1.0
                scale_y = transform.scaleY if transform else 1.0

                # Create input stream
                if 0 in prerendered_paths:
                    # Pre-rendered clips are already encoded videos - trim to exact duration
                    base_stream = ffmpeg.input(input_path)

                    # Trim to exact clip duration and reset PTS
                    base_stream = base_stream.filter('trim', duration=base_clip.duration)
                    base_stream = base_stream.filter('setpts', 'PTS-STARTPTS')

                    # Apply user scale if needed
                    if scale_x != 1.0 or scale_y != 1.0:
                        base_stream = base_stream.filter('scale', f'iw*{scale_x}', f'ih*{scale_y}')
                elif base_clip.type == 'image':
                    # For images without effects, create looped input
                    base_stream = ffmpeg.input(input_path, loop=1, t=base_clip.duration, r=quality_settings['output_params'].get('r', 30))

                    # Apply scaling
                    if scale_x != 1.0 or scale_y != 1.0:
                        target_w = f'if(gt(iw,{timeline.canvas.width}),{timeline.canvas.width},-2)*{scale_x}'
                        target_h = f'if(gt(ih,{timeline.canvas.height}),{timeline.canvas.height},-2)*{scale_y}'
                        base_stream = base_stream.filter('scale', target_w, target_h)
                    else:
                        base_stream = base_stream.filter(
                            'scale',
                            f'if(gt(iw,{timeline.canvas.width}),{timeline.canvas.width},-2)',
                            f'if(gt(ih,{timeline.canvas.height}),{timeline.canvas.height},-2)'
                        )

                    # Extend to full timeline duration if needed
                    if base_clip.duration < timeline.duration:
                        base_stream = base_stream.filter('loop', loop=-1, size=1, start=0)
                        base_stream = base_stream.filter('trim', duration=timeline.duration)
                        base_stream = base_stream.filter('setpts', 'PTS-STARTPTS')
                else:
                    base_stream = ffmpeg.input(input_path)

                # Create canvas
                canvas = ffmpeg.input(
                    f'color=c={timeline.canvas.background}:s={timeline.canvas.width}x{timeline.canvas.height}:d={timeline.duration}',
                    f='lavfi'
                )

                # Overlay base clip on canvas at specified position with timing
                start = base_clip.startTime
                end = start + base_clip.duration
                enable_expr = f'between(t,{start},{end})'
                result = ffmpeg.overlay(canvas, base_stream, x=x, y=y, enable=enable_expr)

                # Overlay additional media clips
                for i in range(1, len(media_clips)):
                    _, clip = media_clips[i]

                    # Check if clip was pre-rendered (has effects)
                    if i in prerendered_paths:
                        # Use pre-rendered clip (effects already applied)
                        clip_path = prerendered_paths[i]
                        logger.info(f"✓ Overlay: Using PRE-RENDERED clip {i} ({clip.name}): {clip_path}")
                    else:
                        # Use original asset
                        clip_path = asset_paths.get(clip.src)
                        logger.info(f"Overlay: Using ORIGINAL asset for clip {i} ({clip.name}): {clip_path}")
                        if not clip_path:
                            logger.warning(f"Skipping clip {i}, asset not found: {clip.src}")
                            continue

                    # Get transformations
                    transform = clip.transform
                    x = int(transform.x if transform else 0)
                    y = int(transform.y if transform else 0)
                    scale_x = transform.scaleX if transform else 1.0
                    scale_y = transform.scaleY if transform else 1.0

                    # Create input stream
                    if i in prerendered_paths:
                        # Pre-rendered clips are already encoded videos
                        # We need to pad them to timeline duration with TRANSPARENT frames
                        clip_stream = ffmpeg.input(clip_path)

                        # Trim to exact clip duration
                        clip_stream = clip_stream.filter('trim', duration=clip.duration)
                        clip_stream = clip_stream.filter('setpts', 'PTS-STARTPTS')

                        # Apply user scale if needed
                        if scale_x != 1.0 or scale_y != 1.0:
                            clip_stream = clip_stream.filter('scale', f'iw*{scale_x}', f'ih*{scale_y}')

                        # Add alpha channel for transparent padding
                        clip_stream = clip_stream.filter('format', 'yuva420p')

                        # Pad video to full timeline duration with transparent frames:
                        # - Add transparent frames before (start_time seconds)
                        # - Add transparent frames after (to reach timeline.duration)
                        start_padding = int(clip.startTime * quality_settings['output_params'].get('r', 30))
                        end_padding = int((timeline.duration - clip.startTime - clip.duration) * quality_settings['output_params'].get('r', 30))

                        if start_padding > 0 or end_padding > 0:
                            logger.info(f"Padding pre-rendered clip {i}: start={start_padding} frames, end={end_padding} frames (transparent)")
                            clip_stream = clip_stream.filter('tpad', start=start_padding, stop=end_padding, color='black@0')
                    elif clip.type == 'image':
                        # For images without effects, create looped input
                        clip_stream = ffmpeg.input(clip_path, loop=1, t=clip.duration, r=quality_settings['output_params'].get('r', 30))

                        # Apply scaling
                        if scale_x != 1.0 or scale_y != 1.0:
                            target_w = f'if(gt(iw,{timeline.canvas.width}),{timeline.canvas.width},-2)*{scale_x}'
                            target_h = f'if(gt(ih,{timeline.canvas.height}),{timeline.canvas.height},-2)*{scale_y}'
                            clip_stream = clip_stream.filter('scale', target_w, target_h)
                        else:
                            clip_stream = clip_stream.filter(
                                'scale',
                                f'if(gt(iw,{timeline.canvas.width}),{timeline.canvas.width},-2)',
                                f'if(gt(ih,{timeline.canvas.height}),{timeline.canvas.height},-2)'
                            )

                        # Extend to full timeline duration if needed
                        if clip.duration < timeline.duration:
                            clip_stream = clip_stream.filter('loop', loop=-1, size=1, start=0)
                            clip_stream = clip_stream.filter('trim', duration=timeline.duration)
                            clip_stream = clip_stream.filter('setpts', 'PTS-STARTPTS')
                    else:
                        clip_stream = ffmpeg.input(clip_path)

                    # Overlay this clip
                    if i in prerendered_paths:
                        # Pre-rendered clips are padded to timeline duration, overlay without enable
                        result = ffmpeg.overlay(result, clip_stream, x=x, y=y)
                    else:
                        # Images and other assets use enable expression for timing
                        start = clip.startTime
                        end = start + clip.duration
                        enable_expr = f'between(t,{start},{end})'
                        result = ffmpeg.overlay(result, clip_stream, x=x, y=y, enable=enable_expr)

            else:
                # No media clips, just create a blank canvas
                result = ffmpeg.input(
                    f'color=c={timeline.canvas.background}:s={timeline.canvas.width}x{timeline.canvas.height}:d={timeline.duration}',
                    f='lavfi'
                )

            # Add text overlays (skip if drawtext not supported)
            if text_clips:
                logger.warning(
                    f"Text rendering requested but may not be supported by FFmpeg build. "
                    f"Skipping {len(text_clips)} text clip(s). "
                    f"To enable text rendering, install FFmpeg with --enable-libfreetype --enable-drawtext"
                )
                # TODO: Add text rendering when FFmpeg supports drawtext filter
                # For now, text clips will be skipped to allow video to render

            # Process audio clips
            audio_inputs = []
            if audio_clips:
                logger.info(f"Processing {len(audio_clips)} audio clip(s)")

                for _, clip in audio_clips:
                    clip_path = asset_paths.get(clip.src)
                    if not clip_path:
                        logger.warning(f"Skipping audio clip, asset not found: {clip.src}")
                        continue

                    # Load audio file
                    audio_stream = ffmpeg.input(clip_path)

                    # Apply trimming and timing based on clip's startTime and duration
                    # Use atrim to cut the audio, then adelay to position it in the timeline
                    audio_stream = audio_stream.filter('atrim', start=0, duration=clip.duration)

                    # Delay the audio by startTime (convert to milliseconds)
                    if clip.startTime > 0:
                        delay_ms = int(clip.startTime * 1000)
                        audio_stream = audio_stream.filter('adelay', f'{delay_ms}|{delay_ms}')

                    audio_inputs.append(audio_stream)

                # Mix all audio clips together if we have any
                if audio_inputs:
                    if len(audio_inputs) == 1:
                        # Single audio clip - just use it directly
                        mixed_audio = audio_inputs[0]
                    else:
                        # Multiple audio clips - mix them with amix filter
                        mixed_audio = ffmpeg.filter(audio_inputs, 'amix', inputs=len(audio_inputs), duration='longest')

                    # Pad audio to match video duration
                    mixed_audio = mixed_audio.filter('apad', whole_dur=timeline.duration)

                    logger.info(f"Mixed {len(audio_inputs)} audio stream(s)")

            # Output with quality settings
            if audio_clips and audio_inputs:
                # Output with both video and audio
                stream = ffmpeg.output(
                    result,  # video stream
                    mixed_audio,  # audio stream
                    str(output_path),
                    vcodec=quality_settings['vcodec'],
                    **quality_settings['output_params']
                )
            else:
                # Output with video only (no audio)
                stream = result.output(
                    str(output_path),
                    vcodec=quality_settings['vcodec'],
                    **quality_settings['output_params']
                )

            # Run FFmpeg
            logger.info(f"Running FFmpeg command with {len(media_clips)} media clips, {len(audio_clips)} audio clips, and {len(text_clips)} text clips")
            await asyncio.to_thread(
                stream.overwrite_output().run,
                capture_stdout=True,
                capture_stderr=True
            )

            logger.info(f"FFmpeg render completed successfully")

        except ffmpeg.Error as e:
            logger.error(
                "FFmpeg execution failed",
                error=e.stderr.decode() if e.stderr else str(e),
                exc_info=True
            )
            raise RenderExecutionError(f"FFmpeg failed: {e.stderr.decode() if e.stderr else str(e)}")
        except Exception as e:
            logger.error("Render execution failed", error=str(e), exc_info=True)
            raise RenderExecutionError(f"Render failed: {str(e)}")

    def _build_filtergraph(
        self,
        timeline: TimelineData,
        asset_paths: Dict[str, str],
        quality_settings: Dict[str, Any]
    ) -> List[str]:
        """
        Build FFmpeg filtergraph for complex timeline compositing.

        This will be implemented in the next iteration to support:
        - Multiple overlapping clips
        - Transformations (scale, rotate, position)
        - Text overlays
        - Audio mixing

        Args:
            timeline: Timeline data
            asset_paths: Asset path mapping
            quality_settings: Quality configuration

        Returns:
            List of filtergraph strings
        """
        # TODO: Implement full filtergraph generation
        # For now, return empty list (we're using simple approach)
        return []

    def _get_quality_settings(self, quality: str) -> Dict[str, Any]:
        """Get FFmpeg quality settings based on preset."""
        presets = {
            'low': {
                'vcodec': 'libx264',
                'output_params': {
                    'preset': 'veryfast',
                    'crf': 28,
                    'acodec': 'aac',
                    'audio_bitrate': '96k',
                    'r': 24
                }
            },
            'medium': {
                'vcodec': 'libx264',
                'output_params': {
                    'preset': 'medium',
                    'crf': 23,
                    'acodec': 'aac',
                    'audio_bitrate': '128k',
                    'r': 30
                }
            },
            'high': {
                'vcodec': 'libx264',
                'output_params': {
                    'preset': 'slow',
                    'crf': 18,
                    'acodec': 'aac',
                    'audio_bitrate': '192k',
                    'r': 30
                }
            }
        }

        return presets.get(quality, presets['medium'])

    def _get_greenscreen_chroma_key_color(self, greenscreen_url: str) -> str:
        """
        Determine the chroma key color based on greenscreen filename
        (Adapted from ffmpeg_processor)

        Args:
            greenscreen_url: URL or path to greenscreen file

        Returns:
            Hex color code for chroma keying ('000000' for black, '00FF00' for green)
        """
        from urllib.parse import urlparse, unquote
        parsed = urlparse(greenscreen_url)
        path = unquote(parsed.path)
        filename = path.split('/')[-1].lower()

        # Files with black background
        black_background_files = [
            'fire1_v.mp4', 'fire1_h.mp4', 'fire2_v.mp4', 'fire2_h.mp4',
            'pink_particle_v', 'pink_particle_h', 'rain1_v', 'rain1_h',
            'stars_v', 'stars_h', 'thunder_v', 'thunder_h',
            'old_film_black_v', 'old_film_black_h'
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

        # Check filename matches
        for black_file in black_background_files:
            if black_file in filename:
                logger.info(f"Using black chroma key for {filename}")
                return '000000'

        for green_file in green_background_files:
            if green_file in filename:
                logger.info(f"Using green chroma key for {filename}")
                return '00FF00'

        for white_file in white_background_files:
            if white_file in filename:
                logger.info(f"Using white chroma key for {filename}")
                return 'FFFFFF'

        logger.warning(f"Unknown greenscreen file {filename}, defaulting to black chroma key")
        return '000000'

    def _convert_greenscreen_effect_name_to_url(self, effect_name_or_url: str) -> str:
        """
        Convert greenscreen effect name to a local file path if needed.
        (Adapted from ffmpeg_processor)

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

    def _create_doodle_effect_video(self, image_path: str, duration: float, width: int, height: int, fps: int = 24, speed: str = 'fast') -> Path:
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

        Returns:
            Path to the generated MP4 file
        """
        if cv2 is None or cairo is None or np is None:
            raise TimelineRenderError(
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
            raise TimelineRenderError(f"Could not load image: {image_path}")

        # Resize and center
        h, w = img.shape[:2]
        scale = min(width / w, height / h) * 0.8
        new_w, new_h = int(w * scale), int(h * scale)
        img_resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

        offset_x = (width - new_w) // 2
        offset_y = (height - new_h) // 2

        # Extract black outlines (threshold < 80)
        gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
        black_threshold = 80
        black_mask = gray < black_threshold
        img_black_only = np.ones_like(img_resized) * 255
        img_black_only[black_mask] = img_resized[black_mask]

        # Full color image
        img_final_color = img_resized.astype(np.uint8)

        # Edge detection for drawing paths
        blurred = cv2.GaussianBlur(gray, (7, 7), 0)
        edges = cv2.Canny(blurred, 100, 200)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Build paths from contours
        paths = []
        total_pixels = 0

        for cnt in contours:
            if cv2.arcLength(cnt, False) < 200:
                continue
            epsilon = 0.01 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, False)

            points = []
            for point in approx:
                x, y = point[0]
                points.append((x + offset_x, y + offset_y))

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
                target_dist = progress * total_pixels

                color_mask = cairo.ImageSurface(cairo.FORMAT_A8, width, height)
                color_ctx = cairo.Context(color_mask)
                color_ctx.set_source_rgba(1, 1, 1, 1)
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

                ctx.save()
                ctx.set_source_surface(full_col_surf, 0, 0)
                ctx.mask_surface(color_mask, 0, 0)
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
            size=f"{width}x{height}"
        )

        return output_path

    def _apply_camera_movement(
        self,
        input_stream,
        movement_type: str,
        duration: float,
        width: int,
        height: int,
        fps: int = 30,
        asset_path: str = None,
        is_video: bool = False
    ):
        """
        Apply camera movement effects to video/image clips
        (Adapted from ffmpeg_processor._apply_pan_movement)

        Args:
            input_stream: FFmpeg input stream
            movement_type: Type of movement ('pan_right', 'pan_left', 'pan_up', 'pan_down', 'zoom_in', 'zoom_out', 'doodle', 'static')
            duration: Duration of the movement in seconds
            width: Target output width
            height: Target output height
            fps: Frames per second
            asset_path: Path to source file (required for zoom effects and doodle)
            is_video: Whether the source is a video file (doodle not supported for videos)

        Returns:
            FFmpeg stream with movement applied
        """
        # Handle doodle effect (images only)
        if movement_type == 'doodle' or movement_type.startswith('doodle_'):
            if is_video:
                logger.warning("Doodle effect not supported for videos, using static")
                return ffmpeg.filter(input_stream, 'scale', width, height)
            if not asset_path:
                raise ValueError("asset_path required for doodle effect")

            # Extract speed from movement_type
            speed = 'slow' if movement_type == 'doodle_slow' else 'fast'

            doodle_video_path = self._create_doodle_effect_video(
                asset_path, duration, width, height, fps, speed=speed
            )
            return ffmpeg.input(str(doodle_video_path))

        if not movement_type or movement_type == 'static':
            # No movement - just scale
            return ffmpeg.filter(input_stream, 'scale', width, height)

        # Pan movements
        scale_factor = 3
        bg_width = width * scale_factor
        bg_height = height * scale_factor
        fg_width = width * 4
        fg_height = height * 4

        if movement_type == 'pan_right':
            # Use input stream directly (no split needed with new approach)
            bg = ffmpeg.filter(input_stream, 'scale', bg_width, bg_height)
            fg = ffmpeg.filter(input_stream, 'scale', fg_width, fg_height)
            speed = width / duration
            overlayed = ffmpeg.filter([bg, fg], 'overlay', f'-{width}+t*{speed}', 0)
            return ffmpeg.filter(overlayed, 'scale', width, height)

        elif movement_type == 'pan_left':
            # Use input stream directly (no split needed with new approach)
            bg = ffmpeg.filter(input_stream, 'scale', bg_width, bg_height)
            fg = ffmpeg.filter(input_stream, 'scale', fg_width, fg_height)
            speed = width / duration
            overlayed = ffmpeg.filter([bg, fg], 'overlay', f'0-t*{speed}', 0)
            return ffmpeg.filter(overlayed, 'scale', width, height)

        elif movement_type == 'pan_down':
            # Use input stream directly (no split needed with new approach)
            bg = ffmpeg.filter(input_stream, 'scale', bg_width, bg_height)
            fg = ffmpeg.filter(input_stream, 'scale', fg_width, fg_height)
            speed = height / duration
            overlayed = ffmpeg.filter([bg, fg], 'overlay', 0, f'-{height}+t*{speed}')
            return ffmpeg.filter(overlayed, 'scale', width, height)

        elif movement_type == 'pan_up':
            # Use input stream directly (no split needed with new approach)
            bg = ffmpeg.filter(input_stream, 'scale', bg_width, bg_height)
            fg = ffmpeg.filter(input_stream, 'scale', fg_width, fg_height)
            speed = height / duration
            overlayed = ffmpeg.filter([bg, fg], 'overlay', 0, f'0-t*{speed}')
            return ffmpeg.filter(overlayed, 'scale', width, height)

        elif movement_type == 'zoom_in':
            frames = int(duration * fps)
            if not asset_path:
                logger.warning("asset_path required for zoom_in, falling back to static")
                return ffmpeg.filter(input_stream, 'scale', width, height)

            zoom_input = ffmpeg.input(str(asset_path))
            scaled = ffmpeg.filter(zoom_input, 'scale', width*6, height*6, force_original_aspect_ratio='increase')
            cropped = ffmpeg.filter(scaled, 'crop', width*6, height*6, '(iw-ow)/2', '(ih-oh)/2')
            return ffmpeg.filter(
                cropped,
                'zoompan',
                z='min(zoom+0.002,3)',
                x='iw/2-(iw/zoom/2)',
                y='ih/2-(ih/zoom/2)',
                d=frames,
                s=f'{width}x{height}',
                fps=fps
            )

        elif movement_type == 'zoom_out':
            frames = int(duration * fps)
            logger.info(f"Applying zoom_out movement: duration={duration}s, fps={fps}, frames={frames}, asset_path={asset_path}")

            if not asset_path:
                logger.warning("asset_path required for zoom_out, falling back to static")
                return ffmpeg.filter(input_stream, 'scale', width, height)

            # Create fresh input WITHOUT loop/duration - let zoompan generate all frames
            zoom_input = ffmpeg.input(str(asset_path))
            logger.info(f"Created zoom_input from {asset_path}, applying zoompan filter")

            # Apply fast_zoom.py filter chain with center crop
            scaled = ffmpeg.filter(zoom_input, 'scale', width*6, height*6, force_original_aspect_ratio='increase')
            cropped = ffmpeg.filter(scaled, 'crop', width*6, height*6, '(iw-ow)/2', '(ih-oh)/2')

            return ffmpeg.filter(
                cropped,
                'zoompan',
                z='max(3-on*0.01,1.0)',   # Zoom out from 3.0x to 1.0x
                x='iw/2-(iw/zoom/2)',      # Keep centered horizontally
                y='ih/2-(ih/zoom/2)',      # Keep centered vertically
                d=frames,                  # Generate this many frames
                s=f'{width}x{height}',     # Output at final resolution
                fps=fps
            )

        # Unknown movement type - just scale
        return ffmpeg.filter(input_stream, 'scale', width, height)


# Singleton instance
_timeline_renderer = None


def get_timeline_renderer() -> TimelineRenderer:
    """Get or create timeline renderer singleton."""
    global _timeline_renderer
    if _timeline_renderer is None:
        _timeline_renderer = TimelineRenderer()
    return _timeline_renderer
