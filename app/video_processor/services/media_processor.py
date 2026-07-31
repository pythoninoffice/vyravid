"""
Media processor service for Cloud Video Processor
"""

import asyncio
import os
import time
import structlog
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from urllib.parse import urlparse

from video_processor.models.requests import (
    MediaProcessingRequest,
    TranscriptionRequest,
    VideoCombineRequest,
    AudioVideoSyncRequest,
    VideoSplitRequest,
    SubtitleBurnRequest
)
from video_processor.models.responses import JobStatusResponse, JobStatus
from video_processor.config.settings import get_settings

logger = structlog.get_logger()
settings = get_settings()

class MediaProcessorService:
    """
    Service for handling media processing operations
    """

    def __init__(self):
        self.job_statuses: Dict[str, Dict[str, Any]] = {}

    async def _resolve_audio_url_with_fallback(
        self,
        audio_url: Optional[str],
        user_id: Optional[str],
        job_id: str
    ) -> Optional[str]:
        """
        Resolve an audio URL for processing.

        Order:
        1. Use provided audio_url if present.
        2. Fallback to predictable local storage path:
           audio/{user_id}/{job_id}.{wav|mp3|m4a|ogg|flac}
        """
        gcs_service = None
        if audio_url:
            try:
                from video_processor.services.gcs_service import get_gcs_service

                gcs_service = get_gcs_service()
                info = await gcs_service.get_file_info(audio_url)
                if info.get("exists"):
                    return audio_url

                parsed = urlparse(audio_url)
                is_local_media_url = (
                    parsed.path.startswith("/media/")
                    and parsed.hostname in {"localhost", "127.0.0.1", "0.0.0.0", None}
                )
                if not is_local_media_url:
                    return audio_url

                logger.warning(
                    "Provided local audio URL did not resolve; trying predictable fallback",
                    audio_url=audio_url,
                    user_id=user_id,
                    job_id=job_id,
                )
            except Exception as e:
                logger.warning("Could not validate provided audio URL; using it as-is", audio_url=audio_url, error=str(e))
                return audio_url

        if not user_id or not job_id:
            return None

        try:
            if gcs_service is None:
                from video_processor.services.gcs_service import get_gcs_service
                gcs_service = get_gcs_service()
            if not gcs_service.is_available():
                logger.warning("Local storage unavailable while resolving fallback audio URL", user_id=user_id, job_id=job_id)
                return None

            candidate_exts = ["wav", "mp3", "m4a", "ogg", "flac"]

            for ext in candidate_exts:
                blob_name = f"audio/{user_id}/{job_id}.{ext}"
                info = await gcs_service.get_file_info(blob_name)
                if not info or not info.get("exists"):
                    continue

                signed_url = await gcs_service.generate_signed_url(blob_name)
                if signed_url:
                    logger.info(
                        "Resolved fallback audio URL from predictable local storage path",
                        job_id=job_id,
                        user_id=user_id,
                        blob_name=blob_name
                    )
                    return signed_url

        except Exception as e:
            logger.error("Failed resolving fallback audio URL", job_id=job_id, user_id=user_id, error=str(e))

        return None

    def _get_transcript_filename(self, index: int, extension: str, language_code: Optional[str] = None) -> str:
        """
        Generate language-specific transcript filename

        Args:
            index: Transcript index
            extension: File extension (e.g., 'srt', 'ass')
            language_code: Language code (e.g., 'en', 'es') or None for default

        Returns:
            Filename in format 'transcript_{index}_{language_code}.{ext}' or 'transcript_{index}.{ext}'
        """
        if language_code:
            return f"transcript_{index}_{language_code}.{extension}"
        return f"transcript_{index}.{extension}"
        
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
                logger.info("FFmpeg check passed", ffmpeg_version=ffmpeg_version_line)
                logger.info("Media processor FFmpeg availability confirmed")
                return True
            else:
                logger.error("ffmpeg_check_failed", stderr=stderr.decode())
                return False
                
        except Exception as e:
            logger.error("ffmpeg_availability_check_error", error=str(e))
            return False
    
    async def check_gcs_connectivity(self) -> bool:
        """Check storage connectivity (local filesystem in Vyravid)."""
        logger.info("storage_connectivity_check_passed", mode="local")
        return True
    
    def _resolve_watermark_url(self, request: MediaProcessingRequest) -> Optional[str]:
        """Return a usable watermark URL from request URL or raw GCS path."""
        if request.watermark_logo_url:
            return request.watermark_logo_url
        if request.watermark_logo_gcs_path:
            path = request.watermark_logo_gcs_path
            if path.startswith(("gs://", "http://", "https://")):
                return path
            return f"/media/{path.lstrip('/')}"
        return None

    async def process_media_pipeline_simplified(self, request: MediaProcessingRequest):
        """
        Simplified media pipeline processing (based on debug endpoint approach)
        
        Direct execution without background tasks or complex orchestration.
        Follows the same pattern as debug/isolated-video-processing for better performance.
        """
        job_id = request.job_id
        start_time = time.time()
        results = {}
        
        try:
            logger.info("simplified_pipeline_started", job_id=job_id, operation=request.operation)
            
            # Route to specific pipeline based on operation type
            if request.operation == "transcribe_only":
                results = await self._process_transcription_simplified(request)
            elif request.operation == "video_only":
                results = await self._process_video_simplified(request)
            elif request.operation == "full_pipeline":
                results = await self._process_full_pipeline_simplified(request)
            else:
                raise Exception(f"Unknown operation type: {request.operation}")
            
            total_time = time.time() - start_time
            results["total_time_seconds"] = round(total_time, 2)
            results["success"] = True
            
            logger.info("simplified_pipeline_completed", 
                       job_id=job_id, 
                       operation=request.operation,
                       total_time=total_time)
            
            return results
            
        except Exception as e:
            total_time = time.time() - start_time
            logger.error("simplified_pipeline_failed", 
                        job_id=job_id, 
                        error=str(e),
                        total_time=total_time)
            raise
    
    async def _process_transcription_simplified(self, request: MediaProcessingRequest):
        """Simplified transcription-only processing"""
        from video_processor.services.transcription_service import TranscriptionServiceSelector
        from video_processor.services.gcs_service import get_gcs_service
        
        job_id = request.job_id
        transcription_service = TranscriptionServiceSelector()
        gcs_service = get_gcs_service()
        results = {}
        
        logger.info("Starting transcription", job_id=job_id)
        transcription_start = time.time()
        
        all_transcripts = []
        all_output_files = []
        total_cost = 0.0
        
        for i, audio_source in enumerate(request.audio_sources):
            logger.info(f"Transcribing audio {i+1}/{len(request.audio_sources)}", 
                       job_id=job_id, audio_url=audio_source.url)
            
            # Transcribe audio
            transcription_config = request.transcription_config
            service_name = transcription_config.get('service', None)  # Use transcription service default
            
            # For transcription-only, default to video background type
            enhanced_config = transcription_config.copy()
            enhanced_config['background_type'] = 'video'
            enhanced_config['video_parameters'] = {}
            
            result = await transcription_service.transcribe_with_service(
                audio_url=audio_source.url,
                service_name=service_name,
                config=enhanced_config,
                user_id=getattr(request, 'user_id', None),
                job_id=getattr(request, 'job_id', None)
            )
            
            all_transcripts.append(result.transcript)
            total_cost += result.cost or 0.0
            
            # Upload SRT file
            srt_filename = self._get_transcript_filename(i, "srt", request.language_code)
            srt_url = await gcs_service.upload_content(
                result.srt_content,
                request.user_id or 0,
                job_id,
                srt_filename,
                "output"
            )
            all_output_files.append(srt_url)

            # Upload ASS file if available
            if result.ass_content:
                ass_filename = self._get_transcript_filename(i, "ass", request.language_code)
                ass_url = await gcs_service.upload_content(
                    result.ass_content,
                    request.user_id or 0,
                    job_id,
                    ass_filename,
                    "output"
                )
                all_output_files.append(ass_url)
        
        transcription_time = time.time() - transcription_start
        
        results["transcription"] = {
            "completed": True,
            "time_seconds": round(transcription_time, 2),
            "transcripts_count": len(all_transcripts),
            "cost": total_cost,
            "output_files": all_output_files
        }
        
        # Combined transcript
        full_transcript = "\n\n".join(all_transcripts)
        results["transcript"] = full_transcript
        results["output_files"] = all_output_files
        
        return results
    
    async def _process_video_simplified(self, request: MediaProcessingRequest):
        """Simplified video-only processing"""
        from video_processor.services.ffmpeg_processor import get_ffmpeg_processor
        from video_processor.services.transcription_service import TranscriptionServiceSelector
        from video_processor.services.gcs_service import get_gcs_service
        from video_processor.config.preset_music import get_music_url_by_id, DEFAULT_MUSIC_OPTIONS

        job_id = request.job_id
        ffmpeg_processor = get_ffmpeg_processor(language_code=request.language_code)
        transcription_service = TranscriptionServiceSelector()
        gcs_service = get_gcs_service()
        results = {}

        logger.info("Starting video processing", job_id=job_id, language_code=request.language_code)
        video_start = time.time()

        # Determine background type
        background_type = request.background_type or 'video'

        # Resolve audio URL first so image_timeline can include audio when available.
        # Resolution order: explicit video_parameters.audio_url -> audio_sources -> first video URL -> predictable GCS fallback.
        audio_url = request.video_parameters.get('audio_url')
        if not audio_url and request.audio_sources:
            audio_url = request.audio_sources[0].url
        if not audio_url and request.video_files:
            video_file = request.video_files[0]
            audio_url = video_file.url if hasattr(video_file, 'url') else video_file
        audio_url = await self._resolve_audio_url_with_fallback(audio_url, str(request.user_id or ""), job_id)

        # Handle image_timeline mode.
        if background_type == 'image_timeline' and request.image_timeline:
            logger.info(
                "Processing image_timeline",
                job_id=job_id,
                segments_count=len(request.image_timeline),
                has_audio=bool(audio_url)
            )

            # Convert Pydantic models to dicts for the processor
            timeline_segments = []
            for segment in request.image_timeline:
                timeline_segments.append({
                    'image_url': segment.image_url,
                    'start_time': segment.start_time,
                    'end_time': segment.end_time,
                    'transition_type': segment.transition_type,
                    'transition_duration': segment.transition_duration,
                    'camera_movement': segment.camera_movement or 'static',
                    'greenscreen_effect': segment.greenscreen_effect
                })

            # Calculate total duration from timeline
            total_duration = max(segment.end_time for segment in request.image_timeline)

            # Extract camera movements from individual segments
            camera_movements = [segment.get('camera_movement', 'static') for segment in timeline_segments]
            logger.info("🎬 Extracted camera movements:", camera_movements=camera_movements)

            image_config = {
                'type': 'image_timeline',
                'timeline_segments': timeline_segments
            }

            # Create timeline background video first.
            # If no audio is available, this is the final video.
            # If audio is available, this is an intermediate video and we mux audio next.
            timeline_video_url = await ffmpeg_processor.create_video_from_images(
                image_config,
                total_duration,
                request.user_id or '0',
                job_id,
                request.video_parameters,
                camera_movements=camera_movements,
                is_final_video=not bool(audio_url)
            )

            if audio_url:
                caption_style = (request.transcription_config or {}).get('caption_style', 'none')
                captions_enabled = caption_style != 'none'

                if captions_enabled:
                    logger.info("Generating captions for image_timeline video", job_id=job_id, caption_style=caption_style)

                    enhanced_config = (request.transcription_config or {}).copy()
                    enhanced_config['background_type'] = background_type
                    enhanced_config['video_parameters'] = request.video_parameters
                    service_name = enhanced_config.get('service', None)

                    transcription_result = await transcription_service.transcribe_with_service(
                        audio_url=audio_url,
                        service_name=service_name,
                        config=enhanced_config,
                        user_id=getattr(request, 'user_id', None),
                        job_id=getattr(request, 'job_id', None)
                    )

                    srt_filename = self._get_transcript_filename(0, "srt", request.language_code)
                    srt_url = await gcs_service.upload_content(
                        transcription_result.srt_content,
                        request.user_id or 0,
                        job_id,
                        srt_filename,
                        "output"
                    )

                    subtitle_url = srt_url
                    if transcription_result.ass_content:
                        ass_filename = self._get_transcript_filename(0, "ass", request.language_code)
                        subtitle_url = await gcs_service.upload_content(
                            transcription_result.ass_content,
                            request.user_id or 0,
                            job_id,
                            ass_filename,
                            "output"
                        )

                    style_config = request.video_parameters.get('subtitle_style', {})
                    transcription_style = {
                        'font_name': request.transcription_config.get('font_family'),
                        'font_size': request.transcription_config.get('font_size'),
                        'font_color': request.transcription_config.get('default_color', 'white'),
                        'outline_color': request.transcription_config.get('outline_color', 'black'),
                        'outline_width': request.transcription_config.get('outline_width', 2)
                    }
                    transcription_style = {k: v for k, v in transcription_style.items() if v is not None}
                    merged_style = {**transcription_style, **style_config}

                    result_url = await ffmpeg_processor.combine_videos_with_subtitles(
                        [timeline_video_url],
                        audio_url,
                        subtitle_url,
                        request.user_id or 0,
                        job_id,
                        request.video_parameters,
                        merged_style,
                        known_video_durations={timeline_video_url: total_duration}
                    )
                else:
                    logger.info("Muxing audio into image_timeline video (captions disabled)", job_id=job_id)
                    result_url = await ffmpeg_processor.combine_videos(
                        [timeline_video_url],
                        audio_url,
                        request.user_id or 0,
                        job_id,
                        request.video_parameters,
                        is_final_video=True
                    )

                result_url = await ffmpeg_processor.enforce_audio_track(
                    result_url,
                    audio_url,
                    request.user_id or '0',
                    job_id,
                    upload_result=True
                )
            else:
                result_url = timeline_video_url

            watermark_url = self._resolve_watermark_url(request)
            if watermark_url and result_url:
                logger.info("Applying watermark/logo to image_timeline video", job_id=job_id)
                result_url = await ffmpeg_processor.apply_watermark_overlay(
                    result_url,
                    watermark_url,
                    request.user_id or '0',
                    job_id,
                    upload_result=True,
                    position=request.watermark_logo_position or "bottom_right"
                )

            video_time = time.time() - video_start

            results["video_processing"] = {
                "completed": True,
                "time_seconds": round(video_time, 2),
                "result_url": result_url
            }
            results["output_files"] = [result_url]

            return results

        # Check for music
        music_url = None
        music_options = None
        
        if request.background_music_id:
            logger.info("🎵 MUSIC: Retrieving music URL for background music", 
                       job_id=job_id, 
                       background_music_id=request.background_music_id)
            music_url = get_music_url_by_id(request.background_music_id)
            logger.info("🎵 MUSIC: Retrieved music URL", 
                       job_id=job_id, 
                       background_music_id=request.background_music_id,
                       music_url=music_url,
                       music_url_length=len(music_url) if music_url else 0)
            if music_url:
                music_options = {
                    **DEFAULT_MUSIC_OPTIONS,
                    "volume": request.music_volume or 0.25,
                    "fade_in_duration": request.music_fade_in or 2.0,
                    "fade_out_duration": request.music_fade_out or 3.0
                }
        
        # Combine videos with or without music
        if music_url:
            logger.info("Combining videos with music (video-only processing)", job_id=job_id)
            result_url = await ffmpeg_processor.combine_videos_with_music(
                request.video_files,
                audio_url,
                music_url,
                request.user_id or 0,
                job_id,
                request.video_parameters,
                music_options,
                upload_result=True
            )
        else:
            logger.info("Standard video combination (video-only processing)", job_id=job_id)
            result_url = await ffmpeg_processor.combine_videos(
                request.video_files,
                audio_url,
                request.user_id or 0,
                job_id,
                request.video_parameters,
                is_final_video=True  # This is a final video, use user-specific path
            )

        # If an audio source was provided, guarantee final output includes an audio stream.
        if result_url and audio_url:
            result_url = await ffmpeg_processor.enforce_audio_track(
                result_url,
                audio_url,
                request.user_id or '0',
                job_id,
                upload_result=True
            )
            logger.info("✅ Video-only output audio presence verified/enforced", job_id=job_id, result_url=result_url)
        
        video_time = time.time() - video_start
        
        results["video_processing"] = {
            "completed": True,
            "time_seconds": round(video_time, 2),
            "result_url": result_url
        }
        results["output_files"] = [result_url]
        
        return results
    
    #this is what we use most of the time
    async def _process_full_pipeline_simplified(self, request: MediaProcessingRequest):
        """Simplified full pipeline processing (like debug endpoint)"""
        from video_processor.services.transcription_service import TranscriptionServiceSelector
        from video_processor.services.ffmpeg_processor import get_ffmpeg_processor
        from video_processor.services.gcs_service import get_gcs_service
        from video_processor.config.preset_music import get_music_url_by_id, DEFAULT_MUSIC_OPTIONS
        
        job_id = request.job_id
        transcription_service = TranscriptionServiceSelector()
        ffmpeg_processor = get_ffmpeg_processor(language_code=request.language_code)
        gcs_service = get_gcs_service()
        results = {}
        all_output_files = []
        
        # Determine background type early for proper caption scaling
        background_type = request.background_type or 'video'
        logger.info("Processing background type", job_id=job_id, background_type=background_type)
        
        # Step 1: Transcription
        if request.audio_sources:
            logger.info("Step 1: Starting transcription", job_id=job_id)
            step1_start = time.time()
            
            all_transcripts = []
            all_srt_files = []
            all_ass_files = []
            total_cost = 0.0
            
            for i, audio_source in enumerate(request.audio_sources):
                # Transcribe audio
                transcription_config = request.transcription_config
                service_name = transcription_config.get('service', None)  # Use transcription service default
                
                # Add background_type and video_parameters to transcription config for proper caption scaling
                enhanced_config = transcription_config.copy()
                enhanced_config['background_type'] = background_type
                enhanced_config['video_parameters'] = request.video_parameters
                
                result = await transcription_service.transcribe_with_service(
                    audio_url=audio_source.url,
                    service_name=service_name,
                    config=enhanced_config,
                    user_id=getattr(request, 'user_id', None),
                    job_id=getattr(request, 'job_id', None)
                )
                
                all_transcripts.append(result.transcript)
                total_cost += result.cost or 0.0
                
                # Upload SRT file
                srt_filename = self._get_transcript_filename(i, "srt", request.language_code)
                srt_url = await gcs_service.upload_content(
                    result.srt_content,
                    request.user_id or 0,
                    job_id,
                    srt_filename,
                    "output"
                )
                all_srt_files.append(srt_url)
                all_output_files.append(srt_url)

                # Upload ASS file if available
                if result.ass_content:
                    ass_filename = self._get_transcript_filename(i, "ass", request.language_code)
                    ass_url = await gcs_service.upload_content(
                        result.ass_content,
                        request.user_id or 0,
                        job_id,
                        ass_filename,
                        "output"
                    )
                    all_ass_files.append(ass_url)
                    all_output_files.append(ass_url)
            
            step1_time = time.time() - step1_start
            results["step1_transcription"] = {
                "completed": True,
                "time_seconds": round(step1_time, 2),
                "transcripts_count": len(all_transcripts),
                "cost": total_cost
            }
            
            #full_transcript = "\n\n".join(all_transcripts)
            #results["transcript"] = full_transcript
        
        # Step 2: Background Video Generation (if needed for image backgrounds)
        background_video_urls = []
        
        if background_type == 'image':
            # Single image background - create video from image
            if request.background_image_url:
                logger.info("Creating video from single image", job_id=job_id, image_url=request.background_image_url)
                
                # Estimate duration from audio if available
                audio_duration = 30.0  # Default duration
                if request.audio_sources:
                    # TODO: Get actual audio duration, for now use estimated
                    audio_duration = request.audio_sources[0].duration or 30.0
                
                image_config = {
                    'type': 'single_image',
                    'background_image_url': request.background_image_url
                }
                
                background_video_url = await ffmpeg_processor.create_video_from_images(
                    image_config,
                    audio_duration,
                    request.user_id or '0',
                    job_id,
                    request.video_parameters,
                    camera_movements=request.camera_movements
                )
                
                background_video_urls.append(background_video_url)
                logger.info("Background video created from image", job_id=job_id, video_url=background_video_url)
                
        elif background_type == 'image_timeline':
            # Multiple images with timeline - create video from timeline
            if request.image_timeline:
                logger.info("Creating video from image timeline", job_id=job_id, segments_count=len(request.image_timeline))
                
                # Convert Pydantic models to dicts for the processor
                timeline_segments = []
                for segment in request.image_timeline:
                    timeline_segments.append({
                        'image_url': segment.image_url,
                        'start_time': segment.start_time,
                        'end_time': segment.end_time,
                        'transition_type': segment.transition_type,
                        'transition_duration': segment.transition_duration,
                        'camera_movement': segment.camera_movement or 'static',
                        'greenscreen_effect': segment.greenscreen_effect
                    })
                
                # Calculate total duration from timeline
                total_duration = max(segment.end_time for segment in request.image_timeline) if request.image_timeline else 30.0
                
                # Extract camera movements from individual segments
                logger.info("🎬 Processing timeline segments:",
                           segments_data=[{
                               'camera_movement': segment.get('camera_movement', 'static'),
                               'transition_type': segment.get('transition_type', 'cut'),
                               'start_time': segment.get('start_time'),
                               'end_time': segment.get('end_time')
                           } for segment in timeline_segments])

                camera_movements = [segment.get('camera_movement', 'static') for segment in timeline_segments]
                logger.info("🎬 Extracted camera movements:", camera_movements=camera_movements)

                image_config = {
                    'type': 'image_timeline',
                    'timeline_segments': timeline_segments
                }

                background_video_url = await ffmpeg_processor.create_video_from_images(
                    image_config,
                    total_duration,
                    request.user_id or '0',
                    job_id,
                    request.video_parameters,
                    camera_movements=camera_movements
                )
                
                background_video_urls.append(background_video_url)
                logger.info("Background video created from timeline", job_id=job_id, video_url=background_video_url)
                
        elif background_type == 'video':
            # Standard video backgrounds - use existing video files
            background_video_urls = [vf.url if hasattr(vf, 'url') else vf for vf in request.video_files]
            
        # Resolve music parameters
        music_url = None
        music_options = None
        
        if request.background_music_id:
            logger.info("🎵 MUSIC: Retrieving music URL for full pipeline", 
                       job_id=job_id, 
                       background_music_id=request.background_music_id)
            music_url = get_music_url_by_id(request.background_music_id)
            logger.info("🎵 MUSIC: Retrieved music URL for full pipeline", 
                       job_id=job_id, 
                       background_music_id=request.background_music_id,
                       music_url=music_url,
                       music_url_length=len(music_url) if music_url else 0)
            if music_url and music_url.strip():  # Check for non-empty URL
                logger.info("🎵 MUSIC: Music track resolved", job_id=job_id, music_id=request.background_music_id, music_url=music_url)
                music_options = {
                    **DEFAULT_MUSIC_OPTIONS,
                    "volume": request.music_volume or 0.25,
                    "fade_in_duration": request.music_fade_in or 2.0,
                    "fade_out_duration": request.music_fade_out or 3.0
                }
            elif music_url == "":  # Empty URL = no music intended
                logger.info("🎵 MUSIC: Music track is 'no music' option", job_id=job_id, music_id=request.background_music_id)
                music_url = None
                music_options = None
            else:
                logger.warning("🎵 MUSIC: Music track not found", job_id=job_id, music_id=request.background_music_id)
                music_url = None
                music_options = None

        # Step 3: Final Video Processing with Subtitles and Music
        if background_video_urls:
            logger.info("Step 2: Starting video+audio+subtitles+music processing", job_id=job_id, has_music=bool(music_url))
            step2_start = time.time()

            # Get audio URL (now optional)
            audio_url = request.video_parameters.get('audio_url')
            if not audio_url and request.audio_sources:
                audio_source = request.audio_sources[0]
                audio_url = audio_source.url
            elif not audio_url and request.video_files:
                video_file = request.video_files[0]
                audio_url = video_file.url if hasattr(video_file, 'url') else video_file
            audio_url = await self._resolve_audio_url_with_fallback(audio_url, str(request.user_id or ""), job_id)

            # Check if we have audio
            has_audio = bool(audio_url)
            logger.info(f"Audio availability: {has_audio}", job_id=job_id, audio_url=audio_url if has_audio else "None")

            # Full pipeline should not silently degrade to muted output.
            # If we expected audio but could not resolve an audio URL, fail fast.
            if not has_audio:
                raise Exception("No audio URL resolved for full_pipeline request")
            
            # Create VideoFile objects from background videos
            class SimpleVideoFile:
                def __init__(self, url: str):
                    self.url = url
                    self.duration = None

            video_files = [
                SimpleVideoFile(url) for url in background_video_urls
            ]

            # Check if caption_style is 'none' to skip subtitle burning
            caption_style = request.transcription_config.get('caption_style')
            skip_subtitles = caption_style == 'none'

            if skip_subtitles:
                logger.info("Skipping subtitle burning (caption_style='none')", job_id=job_id)

            # Use single-step processing if we have subtitles and caption_style is not 'none'
            if request.audio_sources and all_ass_files and not skip_subtitles:
                subtitle_url = all_ass_files[0]  # Use first ASS file
                
                # Extract style options
                style_config = request.video_parameters.get('subtitle_style', {})
                transcription_style = {
                    'font_name': request.transcription_config.get('font_family'),
                    'font_size': request.transcription_config.get('font_size'),
                    'font_color': request.transcription_config.get('default_color', 'white'),
                    'outline_color': request.transcription_config.get('outline_color', 'black'),
                    'outline_width': request.transcription_config.get('outline_width', 2)
                }
                # Remove None values
                transcription_style = {k: v for k, v in transcription_style.items() if v is not None}
                merged_style = {**transcription_style, **style_config}
                
                # Single-step processing with subtitles
                if music_url:
                    # TODO: Implement combine_videos_with_subtitles_and_music method
                    # For now, we'll use a two-step process: first combine with music, then add subtitles
                    logger.info("Using two-step process: music+video, then subtitles", job_id=job_id)
                    
                    # Step 1: Combine videos with music
                    temp_video_url = await ffmpeg_processor.combine_videos_with_music(
                        video_files,
                        audio_url,
                        music_url,
                        request.user_id or 0,
                        job_id + "_temp",
                        request.video_parameters,
                        music_options,
                        upload_result=False  # Keep as local file for next step
                    )
                    
                    # Step 2: Add subtitles to the result
                    final_video_url = await ffmpeg_processor.burn_subtitles(
                        temp_video_url,
                        subtitle_url,
                        request.user_id or 0,
                        job_id,
                        merged_style,
                        upload_result=True
                    )
                else:
                    # No music, just subtitles
                    final_video_url = await ffmpeg_processor.combine_videos_with_subtitles(
                        video_files,
                        audio_url,
                        subtitle_url,
                        request.user_id or 0,
                        job_id,
                        request.video_parameters,
                        merged_style
                    )
            else:
                # Video combination without subtitles
                if music_url:
                    # Combine videos with music (no subtitles)
                    logger.info("Combining videos with music (no subtitles)", job_id=job_id)
                    final_video_url = await ffmpeg_processor.combine_videos_with_music(
                        video_files,
                        audio_url,
                        music_url,
                        request.user_id or 0,
                        job_id,
                        request.video_parameters,
                        music_options,
                        upload_result=True
                    )
                else:
                    # Standard video combination (no music, no subtitles, but has audio)
                    logger.info("Standard video combination (no music, no subtitles)", job_id=job_id)
                    final_video_url = await ffmpeg_processor.combine_videos(
                        video_files,
                        audio_url,
                        request.user_id or 0,
                        job_id,
                        request.video_parameters,
                        is_final_video=True  # This is a final video, use user-specific path
                    )
            
            # Apply text overlays if provided
            if request.text_overlays and final_video_url:
                logger.info(f"Applying {len(request.text_overlays)} text overlays", job_id=job_id)
                text_overlays_data = [tl.model_dump() for tl in request.text_overlays]
                final_video_url = await ffmpeg_processor.apply_text_overlays(
                    final_video_url,
                    text_overlays_data,
                    request.user_id or '0',
                    job_id + "_tl",
                    upload_result=True
                )
                logger.info(f"✅ Text overlays applied: {final_video_url}", job_id=job_id)

            watermark_url = self._resolve_watermark_url(request)
            if watermark_url and final_video_url:
                logger.info("Applying watermark/logo to final video", job_id=job_id)
                final_video_url = await ffmpeg_processor.apply_watermark_overlay(
                    final_video_url,
                    watermark_url,
                    request.user_id or '0',
                    job_id,
                    upload_result=True,
                    position=request.watermark_logo_position or "bottom_right"
                )
                logger.info(f"✅ Watermark/logo applied: {final_video_url}", job_id=job_id)

            # Defensive step: ensure final output contains audio.
            # This catches any late-stage re-encode path that accidentally drops audio.
            if final_video_url and audio_url:
                final_video_url = await ffmpeg_processor.enforce_audio_track(
                    final_video_url,
                    audio_url,
                    request.user_id or '0',
                    job_id,
                    upload_result=True
                )
                logger.info("✅ Final audio presence verified/enforced", job_id=job_id, final_video_url=final_video_url)

            all_output_files.append(final_video_url)

            step2_time = time.time() - step2_start
            results["step2_video_processing"] = {
                "completed": True,
                "time_seconds": round(step2_time, 2),
                "result_url": final_video_url
            }
        
        results["output_files"] = all_output_files
        return results
    
    async def process_media_pipeline(self, request: MediaProcessingRequest):
        """
        Process complete media pipeline (transcription + video processing)
        
        This orchestrates the complete workflow:
        1. Transcription (if audio sources provided)
        2. SRT/ASS generation from transcripts
        3. Video processing (combining, subtitle burning, etc.)
        
        Args:
            request: Media processing request
        """
        job_id = request.job_id
        
        try:
            # Update job status
            self._update_job_status(job_id, JobStatus.PROCESSING, "Starting media pipeline")
            
            logger.info(
                "media_pipeline_started",
                job_id=job_id,
                operation=request.operation,
                audio_count=len(request.audio_sources),
                video_count=len(request.video_files)
            )
            
            # Route to specific pipeline based on operation type
            if request.operation == "transcribe_only":
                await self._process_transcription_pipeline(request)
            elif request.operation == "video_only":
                await self._process_video_pipeline(request)
            elif request.operation == "full_pipeline":
                await self._process_full_pipeline(request)
            else:
                raise Exception(f"Unknown operation type: {request.operation}")
            
            logger.info("media_pipeline_completed", job_id=job_id)
            
        except Exception as e:
            logger.error("media_pipeline_failed", job_id=job_id, error=str(e))
            self._update_job_status(
                job_id, 
                JobStatus.FAILED, 
                "Pipeline processing failed",
                error_message=f"Pipeline failed: {str(e)}"
            )
    
    async def _process_transcription_pipeline(self, request: MediaProcessingRequest):
        """Process transcription-only pipeline"""
        job_id = request.job_id
        
        self._update_job_status(job_id, JobStatus.PROCESSING, "Processing transcription pipeline")
        
        if not request.audio_sources:
            raise Exception("No audio sources provided for transcription")
        
        # Create transcription request and process
        transcription_request = TranscriptionRequest(
            job_id=job_id,
            audio_sources=request.audio_sources,
            transcription_config=request.transcription_config,
            webhook_url=request.webhook_url,
            user_id=request.user_id
        )
        
        await self.transcribe_audio_only(transcription_request)
    
    async def _process_video_pipeline(self, request: MediaProcessingRequest):
        """Process video-only pipeline"""
        job_id = request.job_id
        
        self._update_job_status(job_id, JobStatus.PROCESSING, "Processing video pipeline")
        
        if not request.video_files:
            raise Exception("No video files provided for video processing")
        
        # Create video combine request and process
        video_combine_request = VideoCombineRequest(
            job_id=job_id,
            video_files=request.video_files,
            video_parameters=request.video_parameters,
            webhook_url=request.webhook_url,
            user_id=request.user_id
        )
        
        await self.combine_video_clips(video_combine_request)
    
    async def _process_full_pipeline(self, request: MediaProcessingRequest):
        """Process complete pipeline: transcription + video processing"""
        job_id = request.job_id
        
        try:
            all_output_files = []
            full_transcript = ""
            total_cost = 0.0
            processing_errors = []
            
            # Determine background type early for proper caption scaling
            background_type = getattr(request, 'background_type', 'video') or 'video'
            
            # Validate pipeline requirements
            if not request.audio_sources and not request.video_files:
                raise Exception("At least audio sources or video files must be provided for full pipeline")
            
            # Step 1: Transcription (if audio sources provided)
            if request.audio_sources:
                self._update_job_status(
                    job_id, 
                    JobStatus.PROCESSING, 
                    "Step 1/3: Processing audio transcription"
                )
                
                # Import transcription services
                from video_processor.services.transcription_service import get_transcription_service
                from video_processor.services.gcs_service import get_gcs_service
                
                transcription_service = get_transcription_service()
                gcs_service = get_gcs_service()
                
                # Process each audio source with error handling
                all_transcripts = []
                all_srt_files = []
                all_ass_files = []
                
                for i, audio_source in enumerate(request.audio_sources):
                    try:
                        self._update_job_status(
                            job_id, 
                            JobStatus.PROCESSING, 
                            f"Step 1/3: Transcribing audio {i+1}/{len(request.audio_sources)}"
                        )
                        
                        # Get transcription service name from config
                        service_name = request.transcription_config.get('service', None)  # Use transcription service default
                        
                        # Add background_type and video_parameters to transcription config for proper caption scaling
                        enhanced_config = request.transcription_config.copy()
                        enhanced_config['background_type'] = background_type
                        enhanced_config['video_parameters'] = request.video_parameters
                        
                        # Transcribe audio
                        result = await transcription_service.transcribe_with_service(
                            audio_source.url,
                            service_name,
                            enhanced_config,
                            user_id=request.user_id,
                            job_id=job_id
                        )
                        
                        if not result or not result.transcript:
                            raise Exception(f"Transcription returned empty result for audio {i+1}")
                        
                        all_transcripts.append(result.transcript)
                        total_cost += result.cost or 0.0
                        
                        # Upload SRT file to GCS with error handling
                        try:
                            srt_filename = self._get_transcript_filename(i, "srt", request.language_code)
                            srt_url = await gcs_service.upload_content(
                                result.srt_content,
                                request.user_id or 0,
                                job_id,
                                srt_filename,
                                "output"
                            )
                            all_srt_files.append(srt_url)
                        except Exception as upload_error:
                            logger.error(
                                "srt_upload_failed",
                                job_id=job_id,
                                audio_index=i,
                                error=str(upload_error)
                            )
                            processing_errors.append(f"Failed to upload SRT file for audio {i+1}: {upload_error}")
                            # Continue processing - transcript is still available

                        # Upload ASS file if available
                        if result.ass_content:
                            try:
                                ass_filename = self._get_transcript_filename(i, "ass", request.language_code)
                                ass_url = await gcs_service.upload_content(
                                    result.ass_content,
                                    request.user_id or 0,
                                    job_id,
                                    ass_filename,
                                    "output"
                                )
                                all_ass_files.append(ass_url)
                                all_output_files.append(ass_url)
                            except Exception as ass_upload_error:
                                logger.error(
                                    "ass_upload_failed",
                                    job_id=job_id,
                                    audio_index=i,
                                    error=str(ass_upload_error)
                                )
                                processing_errors.append(f"Failed to upload ASS file for audio {i+1}: {ass_upload_error}")
                                # Continue processing
                    
                    except Exception as transcription_error:
                        logger.error(
                            "audio_transcription_failed",
                            job_id=job_id,
                            audio_index=i,
                            audio_url=audio_source.url,
                            error=str(transcription_error)
                        )
                        processing_errors.append(f"Failed to transcribe audio {i+1}: {transcription_error}")
                        
                        # Continue with next audio source unless this was the only one
                        if len(request.audio_sources) == 1:
                            raise Exception(f"Transcription failed for only audio source: {transcription_error}")
                        # Otherwise, continue processing other audio sources
                
                # Check if we got any successful transcriptions
                if not all_transcripts:
                    raise Exception("All audio transcription attempts failed")
                elif len(all_transcripts) < len(request.audio_sources):
                    logger.warning(
                        "partial_transcription_success",
                        job_id=job_id,
                        successful=len(all_transcripts),
                        total=len(request.audio_sources)
                    )
                
                # Combine all transcripts
                full_transcript = "\n\n".join(all_transcripts)
                all_output_files.extend(all_srt_files)
                
                logger.info(
                    "transcription_phase_completed",
                    job_id=job_id,
                    transcripts_count=len(all_transcripts),
                    cost=total_cost
                )
            
            logger.info("Starting video processing check", job_id=job_id, 
                       video_files_count=len(request.video_files))
            
            # Step 2: Video Processing (if video files provided)
            if request.video_files:
                logger.info("Entering video processing block", job_id=job_id)
                try:
                    self._update_job_status(
                        job_id, 
                        JobStatus.PROCESSING, 
                        "Step 2/3: Processing video combination"
                    )
                    
                    logger.info("Importing FFmpeg processor", job_id=job_id)
                    try:
                        from video_processor.services.ffmpeg_processor import get_ffmpeg_processor
                        logger.info("FFmpeg processor imported successfully", job_id=job_id)
                    except Exception as import_error:
                        logger.error("Failed to import FFmpeg processor", job_id=job_id, error=str(import_error))
                        raise
                    
                    logger.info("Getting FFmpeg processor instance", job_id=job_id, language_code=request.language_code)
                    try:
                        ffmpeg_processor = get_ffmpeg_processor(language_code=request.language_code)
                        logger.info("FFmpeg processor initialized", job_id=job_id, language_code=request.language_code)
                    except Exception as init_error:
                        logger.error("Failed to initialize FFmpeg processor", job_id=job_id, error=str(init_error))
                        raise
                    
                    # Determine audio source for video combination with fallbacks
                    logger.info("Determining audio source for video", job_id=job_id)
                    audio_url = request.video_parameters.get('audio_url')
                    audio_duration = None
                    
                    if not audio_url and request.audio_sources:
                        # Use first audio source if no specific audio URL provided
                        audio_source = request.audio_sources[0]
                        audio_url = audio_source.url
                        audio_duration = audio_source.duration
                        logger.info(
                            "using_transcribed_audio_for_video",
                            job_id=job_id,
                            audio_url=audio_url,
                            audio_duration=audio_duration
                        )
                    elif not audio_url:
                        # Use first video file's audio track
                        video_file = request.video_files[0]
                        audio_url = video_file.url if hasattr(video_file, 'url') else video_file
                        logger.info(
                            "using_video_audio_track",
                            job_id=job_id,
                            video_file=audio_url
                        )
                    
                    # Check if we have subtitle files for potential single-step processing
                    subtitle_files_available = all_ass_files or all_srt_files
                    
                    # Use single-step processing if subtitles are available
                    if full_transcript and subtitle_files_available:
                        logger.info(
                            "Using single-step video+audio+subtitles processing",
                            job_id=job_id,
                            has_srt_files=bool(all_srt_files),
                            srt_files_count=len(all_srt_files),
                            has_ass_files=bool(all_ass_files),
                            ass_files_count=len(all_ass_files)
                        )
                        
                        try:
                            self._update_job_status(
                                job_id, 
                                JobStatus.PROCESSING, 
                                "Step 2/2: Processing video+audio+subtitles in single operation"
                            )
                            
                            # Prefer ASS files over SRT files for better styling support
                            if all_ass_files:
                                subtitle_url = all_ass_files[0]
                                subtitle_type = "ASS"
                            else:
                                subtitle_url = all_srt_files[0]
                                subtitle_type = "SRT"
                            
                            # Extract subtitle styling from both video parameters and transcription config
                            raw_style_config = request.video_parameters.get('subtitle_style', {})
                            
                            # Ensure video parameters style is a dict
                            if isinstance(raw_style_config, dict):
                                style_config = raw_style_config
                            else:
                                logger.warning(
                                    "video_parameters.subtitle_style is not a dict, using empty dict",
                                    provided_type=type(raw_style_config).__name__,
                                    provided_value=raw_style_config
                                )
                                style_config = {}
                            
                            # Also get font/style info from transcription_config (for backwards compatibility)
                            transcription_style = {
                                'font_name': request.transcription_config.get('font_family'),
                                'font_size': request.transcription_config.get('font_size'),
                                'font_color': request.transcription_config.get('default_color', 'white'),
                                'outline_color': request.transcription_config.get('outline_color', 'black'),
                                'outline_width': request.transcription_config.get('outline_width', 2),
                                'position': request.transcription_config.get('position', 'bottom')
                            }
                            
                            # Remove None values
                            transcription_style = {k: v for k, v in transcription_style.items() if v is not None}
                            
                            # Merge transcription config style with video parameters (video params take precedence)
                            merged_style_config = {**transcription_style, **style_config}
                            
                            # Ensure style_config is a proper dictionary
                            if not isinstance(merged_style_config, dict):
                                logger.warning(
                                    "Invalid style_config, using empty dict",
                                    provided_type=type(merged_style_config).__name__,
                                    provided_value=merged_style_config
                                )
                                style_config = {}
                            else:
                                style_config = merged_style_config
                            
                            logger.info(
                                "Starting single-step processing",
                                job_id=job_id,
                                subtitle_url=subtitle_url,
                                subtitle_type=subtitle_type,
                                style_config=style_config
                            )
                            
                            # Use new single-step method instead of two separate steps
                            final_video_url = await ffmpeg_processor.combine_videos_with_subtitles(
                                request.video_files,
                                audio_url,
                                subtitle_url,
                                request.user_id or 0,
                                job_id,
                                request.video_parameters,
                                style_config,
                                audio_duration=audio_duration
                            )
                            
                            if not final_video_url:
                                raise Exception("Single-step processing returned empty result")
                            
                            # Add the final video to output files
                            all_output_files.append(final_video_url)
                            
                            logger.info(
                                "Single-step processing completed",
                                job_id=job_id,
                                final_video=final_video_url
                            )
                            
                        except Exception as processing_error:
                            logger.error(
                                "Single-step processing failed, falling back to two-step process",
                                job_id=job_id,
                                error=str(processing_error)
                            )
                            
                            # Fallback to original two-step process
                            try:
                                self._update_job_status(
                                    job_id, 
                                    JobStatus.PROCESSING, 
                                    "Fallback: Step 2/3: Combining videos with audio"
                                )
                                
                                # First step: combine videos with audio
                                combined_video_url = await ffmpeg_processor.combine_videos(
                                    request.video_files,
                                    audio_url,
                                    request.user_id or 0,
                                    job_id,
                                    request.video_parameters,
                                    audio_duration=audio_duration
                                )
                                
                                if not combined_video_url:
                                    raise Exception("Fallback video combination returned empty result")
                                
                                self._update_job_status(
                                    job_id, 
                                    JobStatus.PROCESSING, 
                                    "Fallback: Step 3/3: Burning subtitles into video"
                                )
                                
                                logger.info(
                                    "Using fallback two-step process",
                                    job_id=job_id,
                                    combined_video_url=combined_video_url,
                                    subtitle_url=subtitle_url
                                )
                                
                                # Second step: burn subtitles into the combined video
                                final_video_url = await ffmpeg_processor.burn_subtitles(
                                    combined_video_url,
                                    subtitle_url,
                                    request.user_id or 0,
                                    job_id,
                                    style_config
                                )
                                
                                if not final_video_url:
                                    raise Exception("Fallback subtitle burning returned empty result")
                                
                                # Add the final video to output files  
                                all_output_files.append(final_video_url)
                                
                                logger.info(
                                    "Fallback subtitle burning completed",
                                    job_id=job_id,
                                    final_video=final_video_url,
                                    original_video=combined_video_url
                                )
                                
                            except Exception as subtitle_error:
                                logger.error(
                                    "Fallback two-step process also failed",
                                    job_id=job_id,
                                    error=str(subtitle_error)
                                )
                                processing_errors.append(f"Both single-step and fallback processing failed: {subtitle_error}")
                                # As a last resort, just do video combination without subtitles
                                try:
                                    combined_video_url = await ffmpeg_processor.combine_videos(
                                        request.video_files,
                                        audio_url,
                                        request.user_id or 0,
                                        job_id,
                                        request.video_parameters,
                                        audio_duration=audio_duration
                                    )
                                    if combined_video_url:
                                        all_output_files.append(combined_video_url)
                                        logger.info("Fallback: video combination without subtitles succeeded", job_id=job_id)
                                except Exception:
                                    logger.error("Complete failure: even basic video combination failed", job_id=job_id)
                                    raise Exception("Complete processing failure")
                    else:
                        # Standard video combination without subtitles
                        logger.info(
                            "Using standard video combination (no subtitles)",
                            job_id=job_id,
                            has_full_transcript=bool(full_transcript),
                            subtitle_files_available=subtitle_files_available
                        )
                        
                        self._update_job_status(
                            job_id, 
                            JobStatus.PROCESSING, 
                            "Step 2/2: Combining videos with audio"
                        )
                        
                        # Standard video combination
                        combined_video_url = await ffmpeg_processor.combine_videos(
                            request.video_files,
                            audio_url,
                            request.user_id or 0,
                            job_id,
                            request.video_parameters,
                            audio_duration=audio_duration
                        )
                        
                        if not combined_video_url:
                            raise Exception("Standard video combination returned empty result")
                        
                        all_output_files.append(combined_video_url)
                        
                        logger.info(
                            "Standard video combination completed",
                            job_id=job_id,
                            combined_video=combined_video_url
                        )
                        
                        # Log warnings for skipped subtitle processing if applicable
                        if full_transcript and not subtitle_files_available:
                            logger.warning(
                                "subtitle_burning_skipped_no_subtitle_files",
                                job_id=job_id,
                                reason="Transcripts available but no subtitle files (SRT/ASS) uploaded",
                                srt_files_count=len(all_srt_files),
                                ass_files_count=len(all_ass_files)
                            )
                            processing_errors.append("Subtitle burning skipped: transcript available but no subtitle files")
                            
                        elif not full_transcript and request.audio_sources:
                            logger.warning(
                                "subtitle_burning_skipped_no_transcript",
                                job_id=job_id,
                                reason="Audio sources provided but no successful transcription"
                            )
                            processing_errors.append("Subtitle burning skipped: no successful transcription")
                
                except Exception as video_error:
                    logger.error(
                        "video_processing_failed",
                        job_id=job_id,
                        error=str(video_error),
                        video_files=request.video_files
                    )
                    
                    # If transcription succeeded but video failed, still return transcription results
                    if full_transcript:
                        processing_errors.append(f"Video processing failed: {video_error}")
                        logger.info(
                            "partial_pipeline_success",
                            job_id=job_id,
                            reason="Transcription succeeded, video processing failed"
                        )
                    else:
                        # Both transcription and video failed - this is a complete failure
                        raise Exception(f"Video processing failed: {video_error}")
            
            # Determine completion status based on results and errors
            if processing_errors:
                # Partial success - some operations failed but we have results
                status_message = f"Pipeline completed with warnings: {len(processing_errors)} issue(s) encountered"
                if all_output_files:
                    status_message += f" ({len(all_output_files)} files generated)"
                    
                logger.warning(
                    "pipeline_completed_with_warnings",
                    job_id=job_id,
                    errors=processing_errors,
                    output_files=all_output_files
                )
            else:
                # Complete success
                status_message = "Complete media pipeline finished successfully"
                
            # Update final job status
            self._update_job_status(
                job_id,
                JobStatus.COMPLETED,
                status_message,
                transcript=full_transcript,
                output_files=all_output_files
            )
            
            # Update job with comprehensive information
            if job_id in self.job_statuses:
                self.job_statuses[job_id]['transcription_cost'] = total_cost
                self.job_statuses[job_id]['processing_steps'] = {
                    'transcription': bool(request.audio_sources and all_transcripts),
                    'video_combination': bool(request.video_files and any('video' in f for f in all_output_files)),
                    'subtitle_burning': bool(
                        full_transcript and 
                        request.video_files and 
                        not any('subtitle burning failed' in err.lower() for err in processing_errors)
                    )
                }
                self.job_statuses[job_id]['processing_errors'] = processing_errors
                self.job_statuses[job_id]['partial_success'] = len(processing_errors) > 0
            
            logger.info(
                "full_pipeline_completed",
                job_id=job_id,
                total_cost=total_cost,
                output_files_count=len(all_output_files),
                transcript_length=len(full_transcript) if full_transcript else 0,
                errors_count=len(processing_errors),
                partial_success=len(processing_errors) > 0
            )
            
        except Exception as e:
            logger.error("full_pipeline_failed", job_id=job_id, error=str(e))
            raise  # Re-raise to be caught by main pipeline handler
    
    async def transcribe_audio_only(self, request: TranscriptionRequest):
        """
        Process audio transcription only
        
        Args:
            request: Transcription request
        """
        job_id = request.job_id
        
        try:
            logger.info(
                "transcribe_audio_only_called",
                job_id=job_id,
                audio_sources_count=len(request.audio_sources),
                transcription_service=request.transcription_config.get("service", "whisper"),
                webhook_url=request.webhook_url
            )
            
            self._update_job_status(job_id, JobStatus.PROCESSING, "Starting transcription")
            
            logger.info("transcription_started", job_id=job_id)
            
            # Import transcription service
            logger.info("importing_transcription_services", job_id=job_id)
            
            try:
                from video_processor.services.transcription_service import get_transcription_service
                from video_processor.services.gcs_service import get_gcs_service
                logger.info("transcription_services_imported", job_id=job_id)
            except Exception as import_error:
                logger.error("failed_to_import_services", job_id=job_id, error=str(import_error))
                raise
            
            try:
                transcription_service = get_transcription_service()
                gcs_service = get_gcs_service()
                logger.info("transcription_services_initialized", job_id=job_id)
            except Exception as init_error:
                logger.error("failed_to_initialize_services", job_id=job_id, error=str(init_error))
                raise
            
            # Process each audio source
            all_transcripts = []
            all_srt_files = []
            total_cost = 0.0
            
            logger.info(
                "starting_audio_processing",
                job_id=job_id,
                audio_sources_count=len(request.audio_sources)
            )
            
            for i, audio_source in enumerate(request.audio_sources):
                logger.info(
                    "processing_audio_source",
                    job_id=job_id,
                    source_index=i,
                    source_url=audio_source.url,
                    source_type=audio_source.type
                )
                self._update_job_status(
                    job_id, 
                    JobStatus.PROCESSING, 
                    f"Transcribing {audio_source.url}"
                )
                
                # Get transcription service name from config
                service_name = request.transcription_config.get('service', 'whisper')
                logger.info(
                    "calling_transcription_service",
                    job_id=job_id,
                    service_name=service_name,
                    audio_url=audio_source.url
                )
                
                try:
                    # For transcription-only, default to video background type
                    enhanced_config = request.transcription_config.copy()
                    enhanced_config['background_type'] = 'video'
                    enhanced_config['video_parameters'] = request.video_parameters
                    
                    # Transcribe audio
                    result = await transcription_service.transcribe_with_service(
                        audio_source.url,
                        service_name,
                        enhanced_config,
                        user_id=request.user_id,
                        job_id=job_id
                    )
                    logger.info(
                        "transcription_completed",
                        job_id=job_id,
                        transcript_length=len(result.transcript) if result.transcript else 0,
                        cost=result.cost
                    )
                except Exception as transcribe_error:
                    logger.error(
                        "transcription_service_error",
                        job_id=job_id,
                        service_name=service_name,
                        audio_url=audio_source.url,
                        error=str(transcribe_error)
                    )
                    raise
                
                all_transcripts.append(result.transcript)
                total_cost += result.cost or 0.0
                
                # Upload SRT file to GCS
                srt_filename = f"transcript_{len(all_srt_files)}.srt"
                srt_url = await gcs_service.upload_content(
                    result.srt_content,
                    request.user_id or 0,
                    job_id,
                    srt_filename,
                    "output"
                )
                all_srt_files.append(srt_url)
                
                # Upload ASS file if available
                if result.ass_content:
                    ass_filename = f"transcript_{len(all_srt_files)-1}.ass"
                    await gcs_service.upload_content(
                        result.ass_content,
                        request.user_id or 0,
                        job_id,
                        ass_filename,
                        "output"
                    )
            
            # Combine all transcripts
            full_transcript = "\n\n".join(all_transcripts)
            
            self._update_job_status(
                job_id,
                JobStatus.COMPLETED,
                "Transcription completed",
                transcript=full_transcript,
                output_files=all_srt_files
            )
            
            # Update job with cost information
            if job_id in self.job_statuses:
                self.job_statuses[job_id]['transcription_cost'] = total_cost
            
            logger.info(
                "transcription_completed", 
                job_id=job_id,
                cost=total_cost,
                files_count=len(all_srt_files)
            )
            
            # Send webhook notification if provided
            if request.webhook_url:
                logger.info("sending_webhook_notification", job_id=job_id, webhook_url=request.webhook_url)
                try:
                    from video_processor.api.endpoints import send_webhook_notification
                    
                    # Get final job status
                    job_status = await self.get_job_status(job_id)
                    
                    await send_webhook_notification(
                        request.webhook_url,
                        job_id,
                        "completed",
                        job_status.model_dump(),
                        cost_breakdown={"transcription_cost": total_cost, "total_cost": total_cost}
                    )
                    logger.info("webhook_notification_sent", job_id=job_id)
                except Exception as webhook_error:
                    logger.error(
                        "webhook_notification_failed",
                        job_id=job_id,
                        webhook_url=request.webhook_url,
                        error=str(webhook_error)
                    )
            else:
                logger.info("no_webhook_url_provided", job_id=job_id)
            
        except Exception as e:
            logger.error("transcription_failed", job_id=job_id, error=str(e))
            self._update_job_status(
                job_id,
                JobStatus.FAILED,
                f"Transcription failed: {str(e)}"
            )
    
    async def combine_video_clips(self, request: VideoCombineRequest):
        """
        Combine multiple video clips
        
        Args:
            request: Video combine request
        """
        job_id = request.job_id
        
        try:
            self._update_job_status(job_id, JobStatus.PROCESSING, "Combining video clips")
            
            logger.info("video_combine_started", job_id=job_id)
            
            # Import FFmpeg processor
            from video_processor.services.ffmpeg_processor import get_ffmpeg_processor

            ffmpeg_processor = get_ffmpeg_processor()  # No language_code for VideoCombineRequest

            # Extract audio URL from video parameters (if provided)
            audio_url = request.video_parameters.get('audio_url')
            if not audio_url:
                # If no separate audio, use first video's audio
                audio_url = request.video_files[0] if request.video_files else None
            
            if not audio_url:
                raise Exception("No audio source provided for video combination")
            
            # Combine videos using FFmpeg processor  
            # Note: This function doesn't extract audio duration from request yet
            result_url = await ffmpeg_processor.combine_videos(
                request.video_files,
                audio_url,
                request.user_id or 0,
                job_id,
                request.video_parameters,
                audio_duration=None  # Will use ffprobe for now
            )
            
            self._update_job_status(
                job_id,
                JobStatus.COMPLETED,
                "Video combination completed",
                output_files=[result_url]
            )
            
            logger.info("video_combine_completed", job_id=job_id, result_url=result_url)
            
        except Exception as e:
            logger.error("video_combine_failed", job_id=job_id, error=str(e))
            self._update_job_status(
                job_id,
                JobStatus.FAILED,
                f"Video combination failed: {str(e)}"
            )
    
    async def sync_audio_video(self, request: AudioVideoSyncRequest):
        """
        Synchronize audio with video
        
        Args:
            request: Audio/video sync request
        """
        job_id = request.job_id
        
        try:
            self._update_job_status(job_id, JobStatus.PROCESSING, "Synchronizing audio and video")
            
            logger.info("audio_video_sync_started", job_id=job_id)
            
            # Import FFmpeg processor
            from video_processor.services.ffmpeg_processor import get_ffmpeg_processor
            
            ffmpeg_processor = get_ffmpeg_processor()
            
            # Extract video and audio URLs from request
            video_url = request.video_file
            audio_url = request.audio_file
            
            if not video_url or not audio_url:
                raise Exception("Both video and audio URLs are required for synchronization")
            
            # Synchronize audio with video using FFmpeg processor
            result_url = await ffmpeg_processor.sync_audio_video(
                video_url,
                audio_url,
                request.user_id or 0,
                job_id,
                request.sync_parameters
            )
            
            self._update_job_status(
                job_id,
                JobStatus.COMPLETED,
                "Audio/video sync completed",
                output_files=[result_url]
            )
            
            logger.info("audio_video_sync_completed", job_id=job_id, result_url=result_url)
            
        except Exception as e:
            logger.error("audio_video_sync_failed", job_id=job_id, error=str(e))
            self._update_job_status(
                job_id,
                JobStatus.FAILED,
                f"Audio/video sync failed: {str(e)}"
            )
    
    async def split_video_segments(self, request: VideoSplitRequest):
        """
        Split video into segments
        
        Args:
            request: Video split request
        """
        job_id = request.job_id
        
        try:
            self._update_job_status(job_id, JobStatus.PROCESSING, "Splitting video segments")
            
            logger.info("video_split_started", job_id=job_id, segments_count=len(request.segments))
            
            # Import FFmpeg processor
            from video_processor.services.ffmpeg_processor import get_ffmpeg_processor
            
            ffmpeg_processor = get_ffmpeg_processor()
            
            # Extract video URL and segments from request
            video_url = request.video_file
            
            if not video_url:
                raise Exception("Video URL is required for splitting")
            
            if not request.segments:
                raise Exception("At least one segment definition is required")
            
            # Split video using FFmpeg processor  
            # Convert VideoSegment objects to dict format expected by FFmpeg processor
            segments_dict = []
            for segment in request.segments:
                segments_dict.append({
                    'start_time': segment.start_time,
                    'end_time': segment.end_time,
                    'output_name': segment.output_name
                })
            
            segment_urls = await ffmpeg_processor.split_video(
                video_url,
                segments_dict,
                request.user_id or 0,
                job_id,
                {}  # Default split options
            )
            
            self._update_job_status(
                job_id,
                JobStatus.COMPLETED,
                "Video splitting completed",
                output_files=segment_urls
            )
            
            logger.info(
                "video_split_completed", 
                job_id=job_id, 
                segments_created=len(segment_urls),
                segment_urls=segment_urls
            )
            
        except Exception as e:
            logger.error("video_split_failed", job_id=job_id, error=str(e))
            self._update_job_status(
                job_id,
                JobStatus.FAILED,
                f"Video splitting failed: {str(e)}"
            )
    
    async def burn_subtitles_to_video(self, request: SubtitleBurnRequest):
        """
        Burn subtitles into video
        
        Args:
            request: Subtitle burn request
        """
        job_id = request.job_id
        
        try:
            self._update_job_status(job_id, JobStatus.PROCESSING, "Burning subtitles to video")
            
            logger.info("subtitle_burn_started", job_id=job_id)
            
            # Import FFmpeg processor
            from video_processor.services.ffmpeg_processor import get_ffmpeg_processor
            
            ffmpeg_processor = get_ffmpeg_processor()
            
            # Extract video and subtitle URLs from request
            video_url = request.video_file
            subtitle_url = request.subtitle_file
            
            if not video_url:
                raise Exception("Video URL is required for subtitle burning")
            
            if not subtitle_url:
                raise Exception("Subtitle URL is required for subtitle burning")
            
            # Burn subtitles using FFmpeg processor
            result_url = await ffmpeg_processor.burn_subtitles(
                video_url,
                subtitle_url,
                request.user_id or 0,
                job_id,
                request.style_config
            )
            
            self._update_job_status(
                job_id,
                JobStatus.COMPLETED,
                "Subtitle burning completed",
                output_files=[result_url]
            )
            
            logger.info("subtitle_burn_completed", job_id=job_id, result_url=result_url)
            
        except Exception as e:
            logger.error("subtitle_burn_failed", job_id=job_id, error=str(e))
            self._update_job_status(
                job_id,
                JobStatus.FAILED,
                f"Subtitle burning failed: {str(e)}"
            )
    
    async def get_job_status(self, job_id: str) -> JobStatusResponse:
        """
        Get status for a specific job
        
        Args:
            job_id: Job identifier
            
        Returns:
            JobStatusResponse with current status
        """
        if job_id not in self.job_statuses:
            return JobStatusResponse(
                job_id=job_id,
                status=JobStatus.FAILED,
                error_message="Job not found"
            )
        
        job_data = self.job_statuses[job_id]
        
        return JobStatusResponse(
            job_id=job_id,
            status=job_data.get('status', JobStatus.PENDING),
            current_step=job_data.get('current_step'),
            transcript=job_data.get('transcript'),
            output_files=job_data.get('output_files', []),
            error_message=job_data.get('error_message'),
            created_at=job_data.get('created_at'),
            updated_at=job_data.get('updated_at')
        )
    
    def _update_job_status(
        self, 
        job_id: str, 
        status: JobStatus, 
        current_step: str,
        transcript: Optional[str] = None,
        output_files: Optional[List[str]] = None,
        error_message: Optional[str] = None
    ):
        """
        Update job status in memory
        
        Args:
            job_id: Job identifier
            status: New status
            current_step: Current processing step
            transcript: Transcribed text (optional)
            output_files: List of output file URLs (optional)
            error_message: Error message if failed (optional)
        """
        now = datetime.now(timezone.utc)
        
        if job_id not in self.job_statuses:
            self.job_statuses[job_id] = {
                'created_at': now
            }
        
        self.job_statuses[job_id].update({
            'status': status,
            'current_step': current_step,
            'updated_at': now
        })
        
        if transcript:
            self.job_statuses[job_id]['transcript'] = transcript
            
        if output_files:
            self.job_statuses[job_id]['output_files'] = output_files
            
        if error_message:
            self.job_statuses[job_id]['error_message'] = error_message
