import os
import uuid
import asyncio
import aiofiles
import ffmpeg
import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
import logging
from concurrent.futures import ThreadPoolExecutor
import tempfile
import shutil

from models.story_models import (
    VideoFile, VideoProcessingJob, VideoProcessingOptions, 
    GenerationStatus, AudioFile, CaptionSettings
)
from models.video_project_models import VideoProjectCreate, VideoProject
from services.gcs_service import get_gcs_service
from services.image_service import get_image_service
from repositories.video_project_repository import VideoProjectRepository
from db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

class VideoProcessingService:
    def __init__(self, max_concurrent_jobs: int = 2, video_project_repository: Optional[VideoProjectRepository] = None):
        """
        Initialize video processing service with queue management and database integration
        
        Args:
            max_concurrent_jobs: Maximum number of concurrent video processing jobs
            video_project_repository: Repository for database operations (optional for backward compatibility)
        """
        self.max_concurrent_jobs = max_concurrent_jobs
        self.processing_queue = asyncio.Queue()
        self.active_jobs: Dict[str, VideoProcessingJob] = {}
        self.job_semaphore = asyncio.Semaphore(max_concurrent_jobs)
        
        # Database integration
        self.video_project_repository = video_project_repository
        self.supabase_client = None
        
        # Initialize database connection if repository is provided
        if self.video_project_repository is None:
            try:
                self.supabase_client = SupabaseClient()
                self.video_project_repository = VideoProjectRepository(self.supabase_client)
                logger.info("VideoProcessingService initialized with database integration")
            except Exception as e:
                logger.warning(f"Failed to initialize database integration: {str(e)}")
                logger.info("VideoProcessingService will operate without database integration")
                # Set both to None to indicate no database integration
                self.supabase_client = None
                self.video_project_repository = None
        
        # Create directories
        self.videos_dir = Path("data/videos")
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        
        self.background_videos_dir = Path("data/background_videos")
        self.background_videos_dir.mkdir(parents=True, exist_ok=True)
        
        self.temp_dir = Path("data/temp/video_processing")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize image service for image background processing
        self.image_service = get_image_service()
        
        # Thread pool for CPU-intensive operations
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent_jobs)
        
        # Start background processing
        self._processing_task = None
        try:
            self._start_background_processing()
        except RuntimeError as e:
            # Handle case where no event loop is running (e.g., during testing)
            if "no running event loop" in str(e):
                logger.info("No event loop available, background processing will be started when needed")
                self._processing_task = None
            else:
                raise
    
    async def verify_database_connectivity(self) -> bool:
        """
        Verify database connectivity for project operations
        
        Returns:
            True if database is available, False otherwise
        """
        try:
            if not self.video_project_repository or not self.supabase_client:
                logger.warning("Database integration not initialized")
                return False
            
            # Simple connectivity test - try to query the video_projects table
            # This will fail gracefully if the table doesn't exist or connection is down
            test_result = self.supabase_client.supabase.table("video_projects").select("id").limit(1).execute()
            
            logger.info("Database connectivity verified successfully")
            return True
            
        except Exception as e:
            logger.error(f"Database connectivity check failed: {str(e)}")
            return False
    
    async def _safe_database_operation(self, operation_func, *args, max_retries: int = 3, base_delay: float = 1.0, **kwargs):
        """
        Execute database operation with error handling, retry logic, and graceful degradation
        
        Args:
            operation_func: The database operation function to execute
            *args: Arguments to pass to the operation function
            max_retries: Maximum number of retry attempts (default: 3)
            base_delay: Base delay in seconds for exponential backoff (default: 1.0)
            **kwargs: Keyword arguments to pass to the operation function
            
        Returns:
            Result of the operation or None if it failed after all retries
        """
        if not self.video_project_repository:
            logger.debug("Database integration not available, skipping operation")
            return None
        
        operation_name = getattr(operation_func, '__name__', str(operation_func))
        
        for attempt in range(max_retries + 1):  # +1 to include initial attempt
            try:
                # Log attempt for monitoring (only log retries, not initial attempt)
                if attempt > 0:
                    logger.info(f"Retrying database operation '{operation_name}' (attempt {attempt + 1}/{max_retries + 1})")
                
                result = await operation_func(*args, **kwargs)
                
                # Log successful operation after retries
                if attempt > 0:
                    logger.info(f"Database operation '{operation_name}' succeeded after {attempt + 1} attempts")
                
                return result
                
            except Exception as e:
                # Log detailed error information for monitoring and debugging
                error_details = {
                    'operation': operation_name,
                    'attempt': attempt + 1,
                    'max_attempts': max_retries + 1,
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'args_count': len(args),
                    'kwargs_keys': list(kwargs.keys()) if kwargs else []
                }
                
                if attempt < max_retries:
                    # Calculate exponential backoff delay
                    delay = base_delay * (2 ** attempt)
                    
                    logger.warning(
                        f"Database operation '{operation_name}' failed on attempt {attempt + 1}/{max_retries + 1}: "
                        f"{type(e).__name__}: {str(e)}. Retrying in {delay:.1f}s..."
                    )
                    
                    # Log detailed error for debugging (only on retries)
                    logger.debug(f"Database operation error details: {error_details}")
                    
                    # Wait before retry with exponential backoff
                    await asyncio.sleep(delay)
                else:
                    # Final attempt failed - log comprehensive error
                    logger.error(
                        f"Database operation '{operation_name}' failed after {max_retries + 1} attempts. "
                        f"Final error: {type(e).__name__}: {str(e)}"
                    )
                    
                    # Log detailed error information for debugging and monitoring
                    logger.error(f"Final database operation failure details: {error_details}")
                    
                    # Log operation context for debugging
                    logger.debug(
                        f"Failed operation context - Function: {operation_name}, "
                        f"Args: {[type(arg).__name__ for arg in args]}, "
                        f"Kwargs: {kwargs}"
                    )
        
        # All retries exhausted - ensure video processing continues
        logger.info(f"Database operation '{operation_name}' failed permanently. Video processing will continue without database integration.")
        return None
    
    def _extract_story_content(self, job: VideoProcessingJob) -> Optional[str]:
        """
        Extract story content from job context for title generation
        
        Args:
            job: Video processing job
            
        Returns:
            Story content string or None if not available
        """
        try:
            # Check if story content is already in the job
            if hasattr(job, 'story_content') and job.story_content:
                return job.story_content
            
            # Try to extract from processing options
            if job.processing_options and isinstance(job.processing_options, dict):
                story_content = job.processing_options.get('story_content')
                if story_content:
                    return str(story_content)
            
            # Could add more extraction logic here in the future
            # For example, loading from audio metadata or related story records
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting story content: {str(e)}")
            return None
    
    def _generate_project_title(self, job: VideoProcessingJob) -> str:
        """
        Generate meaningful project title from job context and story content
        
        Args:
            job: Video processing job
            
        Returns:
            Generated project title
        """
        try:
            # Debug logging
            logger.info(f"🏷️ Generating project title:")
            logger.info(f"  - Job project_title: '{job.project_title}'")
            logger.info(f"  - Job ID: {job.id}")
            
            # Priority 1: Use user-provided project title if available
            logger.info(f"  - job.project_title type: {type(job.project_title)}")
            logger.info(f"  - job.project_title repr: {repr(job.project_title)}")
            
            if job.project_title and job.project_title.strip():
                generated_title = job.project_title.strip()[:100]  # Limit to 100 characters
                logger.info(f"  - Using user-provided title: '{generated_title}'")
                return generated_title
            else:
                logger.info(f"  - Skipping user-provided title (empty or None)")
            
            # Priority 2: Extract from story content if available
            story_content = self._extract_story_content(job)
            if story_content:
                # Take first 50 characters and clean up
                title = story_content.strip()[:50]
                # Remove newlines and extra spaces
                title = ' '.join(title.split())
                if title:
                    return title
            
            # Priority 2: Use audio file metadata if present
            if job.audio_file_id:
                try:
                    # Look for audio metadata files
                    audio_metadata_path = Path("data/audio") / f"metadata_{job.audio_file_id}.json"
                    if audio_metadata_path.exists():
                        with open(audio_metadata_path, 'r') as f:
                            metadata = json.load(f)
                            if metadata.get('title'):
                                return metadata['title'][:100]
                except Exception as e:
                    logger.debug(f"Could not extract title from audio metadata: {e}")
            
            # Priority 3: Generate from timestamp
            if job.created_at:
                formatted_date = job.created_at.strftime("%Y-%m-%d %H:%M")
                fallback_title = f"Video Generated {formatted_date}"
                logger.info(f"  - Using timestamp fallback: '{fallback_title}'")
                return fallback_title
            
            # Priority 4: Fallback to job ID
            final_fallback = f"Generated Video {str(job.id)[:8]}"
            logger.info(f"  - Using job ID fallback: '{final_fallback}'")
            return final_fallback
            
        except Exception as e:
            logger.error(f"Error generating project title: {str(e)}")
            return f"Generated Video {str(job.id)[:8]}"
    
    async def _create_project_record(self, job: VideoProcessingJob) -> Optional[uuid.UUID]:
        """
        Create initial project record in database when video job is created
        
        Args:
            job: Video processing job
            
        Returns:
            Project ID if created successfully, None otherwise
        """
        try:
            if not self.video_project_repository:
                logger.debug("Database integration not available, skipping project creation")
                return None
            
            # Generate project title
            title = self._generate_project_title(job)
            
            # Extract story content for storage
            story_content = self._extract_story_content(job)
            
            # Convert user_id to UUID if it's a string
            user_uuid = None
            if job.user_id:
                try:
                    if isinstance(job.user_id, str):
                        user_uuid = uuid.UUID(job.user_id)
                    else:
                        user_uuid = job.user_id
                except ValueError:
                    logger.warning(f"Invalid user_id format: {job.user_id}, using default")
                    # Create a deterministic UUID from the string
                    user_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, job.user_id)
            
            if not user_uuid:
                logger.warning("No valid user_id available, using default")
                user_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, "unknown-user")
            
            # Create project data
            project_data = VideoProjectCreate(
                user_id=user_uuid,
                title=title,
                status="processing",  # Initial status
                duration=0.0,  # Will be updated when video is completed
                file_size=0,   # Will be updated when video is completed
                processing_options=job.processing_options,
                story_content=story_content
            )
            
            # Create project record using safe database operation
            project = await self._safe_database_operation(
                self.video_project_repository.create,
                project_data
            )
            
            if project:
                logger.info(f"Created project record: {project.id} for job: {job.id}")
                return project.id
            else:
                logger.warning(f"Failed to create project record for job: {job.id}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating project record for job {job.id}: {str(e)}")
            return None
    
    async def _update_project_record(self, job: VideoProcessingJob) -> Optional[VideoProject]:
        """
        Update project record with current job status and metadata
        
        Args:
            job: Video processing job with current status and metadata
            
        Returns:
            Updated VideoProject if successful, None otherwise
        """
        try:
            if not self.video_project_repository or not hasattr(job, 'project_id') or not job.project_id:
                logger.debug("Database integration not available or no project_id, skipping project update")
                return None
            
            from models.video_project_models import VideoProjectUpdate
            
            # Prepare update data based on job status and available information
            update_data = VideoProjectUpdate()
            
            # Always update status based on job status
            if job.status == GenerationStatus.GENERATING:
                update_data.status = "processing"
            elif job.status == GenerationStatus.COMPLETED:
                update_data.status = "completed"
                update_data.completed_at = job.completed_at or datetime.now()
                
                # Add completion metadata if available
                if job.output_file_path and Path(job.output_file_path).exists():
                    try:
                        # Get file size
                        file_size = Path(job.output_file_path).stat().st_size
                        update_data.file_size = file_size
                        
                        # Get video duration
                        duration = self._get_duration(job.output_file_path)
                        if duration > 0:
                            update_data.duration = duration
                            
                    except Exception as e:
                        logger.warning(f"Could not extract video metadata: {str(e)}")
                
                # Add GCS information if available
                if hasattr(job, 'gcs_path') and job.gcs_path:
                    update_data.gcs_path = job.gcs_path
                
                if hasattr(job, 'signed_url') and job.signed_url:
                    update_data.gcs_signed_url = job.signed_url
                    # Set expiration time (typically 1 hour from now for signed URLs)
                    update_data.gcs_signed_url_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
                
            elif job.status == GenerationStatus.FAILED:
                update_data.status = "failed"
                update_data.completed_at = job.completed_at or datetime.now()
            
            # Update project record using safe database operation
            updated_project = await self._safe_database_operation(
                self.video_project_repository.update,
                job.project_id,
                update_data
            )
            
            if updated_project:
                logger.info(f"Updated project record: {job.project_id} for job: {job.id} with status: {update_data.status}")
                return updated_project
            else:
                logger.warning(f"Failed to update project record: {job.project_id} for job: {job.id}")
                return None
                
        except Exception as e:
            logger.error(f"Error updating project record for job {job.id}: {str(e)}")
            return None
    
    def _start_background_processing(self):
        """Start the background video processing task"""
        if self._processing_task is None or self._processing_task.done():
            self._processing_task = asyncio.create_task(self._process_queue())
    
    async def _process_queue(self):
        """Background task to process video jobs from the queue"""
        while True:
            try:
                # Get next job from queue
                job = await self.processing_queue.get()
                
                # Process job with semaphore to limit concurrency
                async with self.job_semaphore:
                    await self._process_video_job(job)
                
                # Mark task as done
                self.processing_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in video processing queue: {str(e)}")
                continue
    
    async def create_video_processing_job(
        self,
        audio_file: AudioFile,
        background_video_paths: List[str],
        caption_file_path: Optional[str] = None,
        processing_options: Optional[VideoProcessingOptions] = None,
        user_id: Optional[str] = None,
        project_title: Optional[str] = None
    ) -> VideoProcessingJob:
        """
        Create a new video processing job and add it to the queue
        
        Args:
            audio_file: AudioFile object with audio to use
            background_video_paths: List of paths to background video files
            caption_file_path: Optional path to caption file (ASS or SRT)
            processing_options: Video processing configuration
            user_id: User ID for project association
            project_title: User-provided project title
        
        Returns:
            VideoProcessingJob object
        """
        try:
            if processing_options is None:
                processing_options = VideoProcessingOptions()
            
            job_id = str(uuid.uuid4())
            output_filename = f"final_video_{job_id}.mp4"
            output_path = self.videos_dir / output_filename
            
            # Debug logging
            logger.info(f"🎬 Creating VideoProcessingJob:")
            logger.info(f"  - Job ID: {job_id}")
            logger.info(f"  - User ID: {user_id}")
            logger.info(f"  - Project title: '{project_title}'")
            
            job = VideoProcessingJob(
                id=uuid.UUID(job_id),
                audio_file_id=audio_file.id,
                audio_file_path=audio_file.file_path,
                background_video_paths=background_video_paths,  # Use paths instead of IDs
                caption_file_path=caption_file_path,
                output_file_path=str(output_path),
                processing_options=processing_options.model_dump(),
                created_at=datetime.now(),
                user_id=user_id or "unknown-user",
                project_title=project_title
            )
            
            # Create project record in database
            project_id = await self._create_project_record(job)
            if project_id:
                job.project_id = project_id
                logger.info(f"Linked job {job_id} to project {project_id}")
            else:
                logger.warning(f"Job {job_id} created without database project record")
            
            # Save job metadata (including project_id if created)
            await self._save_job_metadata(job)
            
            # Add to active jobs
            self.active_jobs[job_id] = job
            
            # Add to processing queue
            await self.processing_queue.put(job)
            
            logger.info(f"Created video processing job: {job_id}")
            return job
            
        except Exception as e:
            logger.error(f"Error creating video processing job: {str(e)}")
            raise
    
    async def _process_video_job(self, job: VideoProcessingJob):
        """Process a single video job"""
        try:
            logger.info(f"Starting video processing job: {job.id}")
            
            # Update job status
            job.status = GenerationStatus.GENERATING
            job.started_at = datetime.now()
            job.progress = 0.1
            await self._save_job_metadata(job)
            
            # Update project status when video processing starts (processing → generating)
            await self._update_project_record(job)
            
            # Get audio file path from job (supports both local paths and GCS URLs)
            audio_file_path = job.audio_file_path
            
            if not audio_file_path:
                raise Exception(f"Audio file path not specified for job {job.id}")
            
            # Check if it's a GCS URL or local file
            is_gcs_url = audio_file_path.startswith('https://storage.googleapis.com') or audio_file_path.startswith('gs://')
            
            if not is_gcs_url and not Path(audio_file_path).exists():
                raise Exception(f"Local audio file not found for job {job.id}: {audio_file_path}")
            
            logger.info(f"Using audio file: {audio_file_path[:100]}{'...' if len(audio_file_path) > 100 else ''}")
            logger.info(f"Audio source type: {'GCS URL' if is_gcs_url else 'Local file'}")
            
            # Validate background videos and estimate bandwidth usage
            valid_video_paths = []
            total_estimated_download = 0
            
            # Use background_video_paths if available, otherwise fall back to background_video_ids
            video_sources = job.background_video_paths or job.background_video_ids or []
            
            # Get audio duration for download estimation
            audio_duration = self._get_duration(audio_file_path)
            
            for video_path in video_sources:
                # Convert to string if it's a UUID
                video_path_str = str(video_path) if video_path else ""
                
                # Check if video exists (local) or is accessible (remote)
                if video_path_str:
                    if self._is_remote_url(video_path_str):
                        # For remote URLs, try to probe without downloading
                        try:
                            duration = self._get_duration(video_path_str)
                            if duration > 0:
                                valid_video_paths.append(video_path_str)
                                # Estimate download size
                                estimated_size = self._estimate_download_size(video_path_str, min(audio_duration, duration))
                                total_estimated_download += estimated_size
                                logger.info(f"Remote video validated: {Path(video_path_str).name}, estimated download: {estimated_size:.1f} MB")
                            else:
                                logger.warning(f"Could not probe remote video: {video_path_str}")
                        except Exception as e:
                            logger.warning(f"Remote video not accessible: {video_path_str}, error: {e}")
                    elif Path(video_path_str).exists():
                        valid_video_paths.append(video_path_str)
                        logger.info(f"Local video validated: {Path(video_path_str).name}")
                    else:
                        logger.warning(f"Background video not found: {video_path_str}")
            
            if not valid_video_paths:
                raise Exception("No valid background videos found")
            
            logger.info(f"Total estimated download size: {total_estimated_download:.1f} MB for {audio_duration:.1f}s audio")
            
            job.progress = 0.3
            await self._save_job_metadata(job)
            
            # Process video in thread pool
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                self.executor,
                self._combine_audio_video_sync,
                audio_file_path,
                valid_video_paths,
                job.output_file_path,
                job.processing_options
            )
            
            if not success:
                raise Exception("Video combination failed")
            
            job.progress = 0.8
            await self._save_job_metadata(job)
            
            # Add captions if provided
            if job.caption_file_path and Path(job.caption_file_path).exists():
                await self._add_captions_to_video(job)
            
            # Upload to Google Cloud Storage
            job.progress = 0.9
            await self._save_job_metadata(job)
            
            gcs_upload_result = await self._upload_to_gcs(job)
            if gcs_upload_result:
                job.gcs_path = gcs_upload_result.get('gcs_path')
                job.public_url = gcs_upload_result.get('public_url')
                job.signed_url = gcs_upload_result.get('signed_url')
                logger.info(f"Video uploaded to GCS: {job.gcs_path}")
            
            # Update job completion
            job.status = GenerationStatus.COMPLETED
            job.progress = 1.0
            job.completed_at = datetime.now()
            await self._save_job_metadata(job)
            
            # Update project with completion data when video processing finishes
            # Add GCS information to project record after successful upload
            await self._update_project_record(job)
            
            logger.info(f"Video processing job completed: {job.id}")
            
        except Exception as e:
            logger.error(f"Error processing video job {job.id}: {str(e)}")
            
            # Update job with error
            job.status = GenerationStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.now()
            await self._save_job_metadata(job)
            
            # Update project status when video processing fails
            await self._update_project_record(job)
        
        finally:
            # Remove from active jobs
            job_id_str = str(job.id)
            if job_id_str in self.active_jobs:
                del self.active_jobs[job_id_str]
    
    def _combine_audio_video_sync(
        self,
        audio_file: str,
        video_files: List[str],
        output_file: str,
        processing_options: Dict[str, Any]
    ) -> bool:
        """
        Optimized synchronous video combination with efficient video handling
        - Only downloads/processes video duration needed based on audio length
        - Repeats video if audio is longer than video
        """
        try:
            # Get audio duration first
            audio_duration = self._get_duration(audio_file)
            if audio_duration <= 0:
                logger.error("Could not get audio duration")
                return False
            
            logger.info(f"Audio duration: {audio_duration:.2f} seconds")
            
            # Get video durations efficiently (probe without downloading full files for remote URLs)
            video_info = []
            for video_file in video_files:
                duration = self._get_duration(video_file)
                if duration > 0:
                    video_info.append({
                        'file': video_file,
                        'duration': duration,
                        'is_remote': video_file.startswith(('http://', 'https://'))
                    })
                    logger.info(f"Video '{Path(video_file).name}' duration: {duration:.2f} seconds")
            
            if not video_info:
                logger.error("No valid video files found")
                return False
            
            # Log optimization benefits
            self._log_optimization_benefits(video_info, audio_duration)
            
            # Create optimized video processing plan
            video_plan = self._create_optimized_video_plan(video_info, audio_duration)
            logger.info(f"Video processing plan: {len(video_plan)} segments")
            
            # Process video with optimized approach
            temp_video = self.temp_dir / f"temp_combined_{uuid.uuid4().hex}.mp4"
            
            try:
                success = self._process_optimized_video_plan(video_plan, temp_video, processing_options)
                if not success:
                    return False
                
                # Combine optimized video with audio
                video_input = ffmpeg.input(str(temp_video))
                audio_input = ffmpeg.input(audio_file)
                
                output = ffmpeg.output(
                    video_input.video,
                    audio_input.audio,
                    output_file,
                    vcodec=processing_options.get('video_codec', 'libx264'),
                    acodec=processing_options.get('audio_codec', 'aac'),
                    preset='fast',
                    shortest=None  # Ensure video matches audio duration exactly
                )
                
                ffmpeg.run(output, overwrite_output=True, quiet=False)
                
                logger.info(f"Successfully created optimized video: {output_file}")
                return True
                
            finally:
                # Clean up temporary file
                if temp_video.exists():
                    temp_video.unlink()
            
        except Exception as e:
            logger.error(f"Error in optimized video combination: {str(e)}")
            return False
    
    def _create_optimized_video_plan(self, video_info: List[Dict], audio_duration: float) -> List[Dict]:
        """
        Create an optimized plan for video processing based on audio duration
        
        Args:
            video_info: List of video file info with duration and remote status
            audio_duration: Target audio duration in seconds
            
        Returns:
            List of video segments with optimized start/duration for efficient processing
        """
        plan = []
        current_time = 0
        video_index = 0
        
        while current_time < audio_duration:
            current_video = video_info[video_index % len(video_info)]
            remaining_time = audio_duration - current_time
            
            # Determine optimal segment duration
            if current_video['duration'] >= remaining_time:
                # Video is longer than remaining time - only use what we need
                segment_duration = remaining_time
                start_time = 0  # Always start from beginning for simplicity
            else:
                # Video is shorter than remaining time - use full video
                segment_duration = current_video['duration']
                start_time = 0
            
            plan.append({
                'file': current_video['file'],
                'start': start_time,
                'duration': segment_duration,
                'is_remote': current_video['is_remote'],
                'original_duration': current_video['duration']
            })
            
            current_time += segment_duration
            video_index += 1
            
            # Prevent infinite loop
            if video_index > len(video_info) * 100:  # Safety check
                logger.warning("Video plan generation exceeded safety limit")
                break
        
        return plan
    
    def _process_optimized_video_plan(self, plan: List[Dict], output_path: Path, processing_options: Dict) -> bool:
        """
        Process video plan with optimizations for remote files and duration limiting
        """
        try:
            resolution = processing_options.get('resolution', '1280x720')
            width, height = map(int, resolution.split('x'))
            
            if len(plan) == 1:
                # Single segment - optimize for remote files
                segment = plan[0]
                return self._process_single_optimized_segment(segment, output_path, width, height, processing_options)
            else:
                # Multiple segments
                return self._process_multiple_optimized_segments(plan, output_path, width, height, processing_options)
                
        except Exception as e:
            logger.error(f"Error processing optimized video plan: {str(e)}")
            return False
    
    def _process_single_optimized_segment(self, segment: Dict, output_path: Path, width: int, height: int, processing_options: Dict) -> bool:
        """
        Process a single video segment with optimizations for remote files
        """
        try:
            # For remote files, use efficient seeking and duration limiting
            if segment['is_remote']:
                # Use input seeking for remote files to avoid downloading unnecessary data
                input_stream = ffmpeg.input(
                    segment['file'],
                    ss=segment['start'],  # Seek to start position (server-side for remote files)
                    t=segment['duration']  # Limit duration (reduces download)
                )
                video_stream = input_stream.video
            else:
                # For local files, use standard approach
                input_stream = ffmpeg.input(segment['file'])
                if segment['duration'] < segment['original_duration']:
                    video_stream = input_stream.video.filter('trim', start=segment['start'], duration=segment['duration']).filter('setpts', 'PTS-STARTPTS')
                else:
                    video_stream = input_stream.video
            
            # Scale to target resolution
            video_stream = video_stream.filter('scale', width, height)
            
            # Output with optimized settings
            ffmpeg.output(
                video_stream,
                str(output_path),
                vcodec=processing_options.get('video_codec', 'libx264'),
                r=processing_options.get('fps', 30),
                preset='fast',
                avoid_negative_ts='make_zero'  # Handle timestamp issues
            ).run(overwrite_output=True, quiet=False)
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing single optimized segment: {str(e)}")
            return False
    
    def _process_multiple_optimized_segments(self, plan: List[Dict], output_path: Path, width: int, height: int, processing_options: Dict) -> bool:
        """
        Process multiple video segments with optimizations
        """
        try:
            temp_files = []
            
            # Process each segment optimally
            for i, segment in enumerate(plan):
                temp_segment_file = self.temp_dir / f"temp_segment_{i}_{uuid.uuid4().hex}.mp4"
                temp_files.append(temp_segment_file)
                
                # Process segment with optimization for remote files
                if segment['is_remote']:
                    # Use input seeking for remote files
                    input_stream = ffmpeg.input(
                        segment['file'],
                        ss=segment['start'],
                        t=segment['duration']
                    )
                    video_stream = input_stream.video
                else:
                    # Local file processing
                    input_stream = ffmpeg.input(segment['file'])
                    if segment['duration'] < segment['original_duration']:
                        video_stream = input_stream.video.filter('trim', start=segment['start'], duration=segment['duration']).filter('setpts', 'PTS-STARTPTS')
                    else:
                        video_stream = input_stream.video
                
                # Scale and process segment
                video_stream = video_stream.filter('scale', width, height)
                
                ffmpeg.output(
                    video_stream,
                    str(temp_segment_file),
                    vcodec=processing_options.get('video_codec', 'libx264'),
                    r=processing_options.get('fps', 30),
                    preset='fast',
                    avoid_negative_ts='make_zero'
                ).run(overwrite_output=True, quiet=True)
            
            # Concatenate all processed segments
            inputs = [ffmpeg.input(str(f)) for f in temp_files]
            video_streams = [inp.video for inp in inputs]
            
            concat_video = ffmpeg.concat(*video_streams, v=1, a=0)
            
            ffmpeg.output(
                concat_video,
                str(output_path),
                vcodec=processing_options.get('video_codec', 'libx264'),
                r=processing_options.get('fps', 30),
                preset='fast'
            ).run(overwrite_output=True, quiet=False)
            
            # Clean up temporary segment files
            for temp_file in temp_files:
                if temp_file.exists():
                    temp_file.unlink()
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing multiple optimized segments: {str(e)}")
            return False
    
    def _get_duration(self, file_path: str) -> float:
        """
        Get duration of audio or video file in seconds
        Optimized for remote files to minimize data transfer
        """
        try:
            # For remote files, use minimal probing to get duration without downloading much data
            if file_path.startswith(('http://', 'https://')):
                probe = ffmpeg.probe(file_path, analyzeduration='1000000', probesize='1000000')
            else:
                probe = ffmpeg.probe(file_path)
            
            # Try to get duration from format first (more reliable)
            if 'format' in probe and 'duration' in probe['format']:
                duration = float(probe['format']['duration'])
                return duration
            
            # Fallback to stream duration
            for stream in probe['streams']:
                if 'duration' in stream:
                    duration = float(stream['duration'])
                    return duration
            
            logger.warning(f"Could not find duration in probe data for {file_path}")
            return 0
            
        except Exception as e:
            logger.error(f"Error getting duration for {file_path}: {e}")
            return 0
    
    def _is_remote_url(self, file_path: str) -> bool:
        """Check if file path is a remote URL"""
        return file_path.startswith(('http://', 'https://', 'ftp://', 'ftps://'))
    
    def _estimate_download_size(self, file_path: str, duration_needed: float) -> float:
        """
        Estimate download size in MB for a given duration of video
        This helps with bandwidth planning for remote files
        """
        try:
            if not self._is_remote_url(file_path):
                return 0  # Local file, no download needed
            
            # Get video bitrate for estimation
            probe = ffmpeg.probe(file_path, analyzeduration='1000000', probesize='1000000')
            
            total_bitrate = 0
            for stream in probe['streams']:
                if 'bit_rate' in stream:
                    total_bitrate += int(stream['bit_rate'])
            
            if total_bitrate == 0:
                # Estimate based on typical video bitrates (conservative estimate)
                total_bitrate = 2000000  # 2 Mbps default
            
            # Calculate estimated size in MB
            estimated_size_mb = (total_bitrate * duration_needed) / (8 * 1024 * 1024)
            
            logger.info(f"Estimated download size for {duration_needed:.1f}s: {estimated_size_mb:.1f} MB")
            return estimated_size_mb
            
        except Exception as e:
            logger.error(f"Error estimating download size: {e}")
            return 0
    
    async def _add_captions_to_video(self, job: VideoProcessingJob):
        """Add captions to the processed video"""
        try:
            if not job.caption_file_path or not Path(job.caption_file_path).exists():
                return
            
            # Create output path for captioned video
            output_path = Path(job.output_file_path)
            captioned_output = output_path.parent / f"captioned_{output_path.name}"
            
            # Add captions using ffmpeg
            video_input = ffmpeg.input(job.output_file_path)
            
            # Escape the subtitle path for ffmpeg
            subtitle_path = str(Path(job.caption_file_path)).replace('\\', '\\\\').replace(':', '\\:')
            
            output = ffmpeg.output(
                video_input,
                str(captioned_output),
                vf=f"subtitles='{subtitle_path}'",
                **{"c:a": "copy"}
            )
            
            # Run in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self.executor,
                lambda: ffmpeg.run(output, overwrite_output=True, quiet=True)
            )
            
            # Replace original with captioned version
            if captioned_output.exists():
                shutil.move(str(captioned_output), job.output_file_path)
                logger.info(f"Added captions to video: {job.id}")
            
        except Exception as e:
            logger.error(f"Error adding captions to video {job.id}: {str(e)}")
            # Don't fail the entire job for caption errors
    
    async def get_job_status(self, job_id: str) -> Optional[VideoProcessingJob]:
        """Get the status of a video processing job"""
        try:
            # Check active jobs first
            if job_id in self.active_jobs:
                return self.active_jobs[job_id]
            
            # Load from metadata file
            return await self._load_job_metadata(job_id)
            
        except Exception as e:
            logger.error(f"Error getting job status: {str(e)}")
            return None
    
    async def get_user_jobs(self, user_id: str, limit: Optional[int] = None, status_filter: Optional[str] = None) -> List[VideoProcessingJob]:
        """Get all video processing jobs for a specific user"""
        try:
            user_jobs = []
            
            # Check active jobs first
            for job in self.active_jobs.values():
                if hasattr(job, 'user_id') and job.user_id == user_id:
                    if not status_filter or job.status == status_filter:
                        user_jobs.append(job)
            
            # Load completed jobs from metadata files
            metadata_dir = self.videos_dir / "metadata"
            if metadata_dir.exists():
                for metadata_file in metadata_dir.glob("*.json"):
                    try:
                        job = await self._load_job_metadata(metadata_file.stem)
                        if job and hasattr(job, 'user_id') and job.user_id == user_id:
                            # Avoid duplicates from active jobs
                            if job.id not in [active_job.id for active_job in self.active_jobs.values()]:
                                if not status_filter or job.status == status_filter:
                                    user_jobs.append(job)
                    except Exception as e:
                        logger.warning(f"Error loading job metadata from {metadata_file}: {str(e)}")
                        continue
            
            # Sort by creation date (newest first)
            user_jobs.sort(key=lambda x: x.created_at or datetime.min, reverse=True)
            
            # Apply limit if specified
            if limit:
                user_jobs = user_jobs[:limit]
            
            logger.info(f"Found {len(user_jobs)} jobs for user {user_id}")
            return user_jobs
            
        except Exception as e:
            logger.error(f"Error getting user jobs: {str(e)}")
            return []
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a video processing job"""
        try:
            if job_id in self.active_jobs:
                job = self.active_jobs[job_id]
                job.status = GenerationStatus.FAILED
                job.error_message = "Job cancelled by user"
                job.completed_at = datetime.now()
                
                await self._save_job_metadata(job)
                del self.active_jobs[job_id]
                
                logger.info(f"Cancelled video processing job: {job_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error cancelling job: {str(e)}")
            return False
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status and statistics"""
        try:
            return {
                "queue_size": self.processing_queue.qsize(),
                "active_jobs": len(self.active_jobs),
                "max_concurrent": self.max_concurrent_jobs,
                "active_job_ids": list(self.active_jobs.keys())
            }
        except Exception as e:
            logger.error(f"Error getting queue status: {str(e)}")
            return {"error": str(e)}
    
    async def _save_job_metadata(self, job: VideoProcessingJob):
        """Save job metadata to JSON file"""
        try:
            metadata_file = self.videos_dir / f"job_{job.id}.json"
            
            # Convert to dict for JSON serialization
            metadata = job.model_dump()
            
            # Convert UUID objects to strings
            if 'id' in metadata and hasattr(metadata['id'], '__str__'):
                metadata['id'] = str(metadata['id'])
            if 'audio_file_id' in metadata and metadata['audio_file_id'] is not None:
                metadata['audio_file_id'] = str(metadata['audio_file_id'])
            if 'project_id' in metadata and metadata['project_id'] is not None:
                metadata['project_id'] = str(metadata['project_id'])
            if 'background_video_ids' in metadata and metadata['background_video_ids'] is not None:
                metadata['background_video_ids'] = [str(vid_id) for vid_id in metadata['background_video_ids']]
            
            # Convert datetime objects to ISO format
            if 'created_at' in metadata and metadata['created_at']:
                metadata['created_at'] = metadata['created_at'].isoformat()
            if 'started_at' in metadata and metadata['started_at']:
                metadata['started_at'] = metadata['started_at'].isoformat()
            if 'completed_at' in metadata and metadata['completed_at']:
                metadata['completed_at'] = metadata['completed_at'].isoformat()
            
            async with aiofiles.open(metadata_file, 'w') as f:
                await f.write(json.dumps(metadata, indent=2))
            
        except Exception as e:
            logger.error(f"Error saving job metadata: {str(e)}")
    
    async def _load_job_metadata(self, job_id: str) -> Optional[VideoProcessingJob]:
        """Load job metadata from JSON file"""
        try:
            metadata_file = self.videos_dir / f"job_{job_id}.json"
            
            if not metadata_file.exists():
                return None
            
            async with aiofiles.open(metadata_file, 'r') as f:
                content = await f.read()
                metadata = json.loads(content)
            
            # Convert datetime strings back
            metadata['created_at'] = datetime.fromisoformat(metadata['created_at'])
            if metadata['started_at']:
                metadata['started_at'] = datetime.fromisoformat(metadata['started_at'])
            if metadata['completed_at']:
                metadata['completed_at'] = datetime.fromisoformat(metadata['completed_at'])
            
            return VideoProcessingJob(**metadata)
            
        except Exception as e:
            logger.error(f"Error loading job metadata: {str(e)}")
            return None
    
    async def cleanup_temp_files(self):
        """Clean up temporary video processing files"""
        try:
            # Clean up combined video files
            for temp_file in self.temp_dir.glob("temp_combined_*.mp4"):
                if temp_file.exists():
                    temp_file.unlink()
                    logger.info(f"Cleaned up temp file: {temp_file}")
            
            # Clean up segment files
            for temp_file in self.temp_dir.glob("temp_segment_*.mp4"):
                if temp_file.exists():
                    temp_file.unlink()
                    logger.info(f"Cleaned up temp segment: {temp_file}")
                    
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {str(e)}")
    
    def _log_optimization_benefits(self, video_info: List[Dict], audio_duration: float):
        """Log the benefits of the optimization approach"""
        try:
            total_video_duration = sum(info['duration'] for info in video_info)
            total_remote_duration = sum(info['duration'] for info in video_info if info['is_remote'])
            
            if total_remote_duration > 0:
                time_saved = max(0, total_remote_duration - audio_duration)
                if time_saved > 0:
                    logger.info(f"Optimization benefit: Avoiding download of {time_saved:.1f}s of remote video content")
                    
                    # Estimate bandwidth saved
                    bandwidth_saved = 0
                    for info in video_info:
                        if info['is_remote'] and info['duration'] > audio_duration:
                            excess_duration = info['duration'] - audio_duration
                            bandwidth_saved += self._estimate_download_size(info['file'], excess_duration)
                    
                    if bandwidth_saved > 0:
                        logger.info(f"Estimated bandwidth saved: {bandwidth_saved:.1f} MB")
                        
        except Exception as e:
            logger.error(f"Error logging optimization benefits: {e}")
    
    async def list_background_videos(self) -> List[VideoFile]:
        """List available background videos"""
        try:
            video_files = []
            
            for video_path in self.background_videos_dir.glob("*.mp4"):
                try:
                    duration = self._get_duration(str(video_path))
                    
                    video_file = VideoFile(
                        id=str(uuid.uuid4()),
                        file_path=str(video_path),
                        duration=duration,
                        format="mp4",
                        created_at=datetime.fromtimestamp(video_path.stat().st_mtime)
                    )
                    video_files.append(video_file)
                    
                except Exception as e:
                    logger.error(f"Error processing video file {video_path}: {e}")
                    continue
            
            return video_files
            
        except Exception as e:
            logger.error(f"Error listing background videos: {str(e)}")
            return []
    
    async def _upload_to_gcs(self, job: VideoProcessingJob) -> Optional[Dict[str, Any]]:
        """
        Upload completed video to Google Cloud Storage
        
        Args:
            job: Video processing job with completed video
            
        Returns:
            Dict with GCS upload information or None if failed
        """
        try:
            if not Path(job.output_file_path).exists():
                logger.error(f"Output file not found for GCS upload: {job.output_file_path}")
                return None
            
            gcs_service = get_gcs_service()
            
            if not gcs_service.is_available():
                logger.warning("GCS service not available, skipping upload")
                return None
            
            # Generate video title from job ID
            video_title = f"Generated Video {job.id}"
            
            # Prepare metadata
            metadata = {
                'job_id': str(job.id),
                'audio_file_id': str(job.audio_file_id) if job.audio_file_id else None,
                'processing_options': json.dumps(job.processing_options) if job.processing_options else None,
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None
            }
            
            # Get user ID from job
            user_id = getattr(job, 'user_id', 'unknown-user')
            logger.info(f"Uploading video for user: {user_id}")
            
            # Upload to GCS
            upload_result = await gcs_service.upload_video(
                local_file_path=job.output_file_path,
                user_id=user_id,
                video_title=video_title,
                metadata=metadata
            )
            
            return upload_result
            
        except Exception as e:
            logger.error(f"Error uploading video to GCS: {str(e)}")
            return None
    
    def generate_caption_preview_gif(
        self,
        caption_file_path: str,
        output_gif_path: str,
        duration: float = 8.0,
        width: int = 400,
        height: int = 200,
        font_size: int = 24,
        font_family: str = "Arial",
        font_file_path: str = None
    ) -> bool:
        """
        Generate a transparent GIF preview of captions for UI preview
        
        Args:
            caption_file_path: Path to SRT/ASS caption file
            output_gif_path: Output path for the GIF
            duration: Duration of the GIF in seconds
            width: Width of the GIF
            height: Height of the GIF  
            font_size: Font size for captions
            font_family: Font family for captions
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not Path(caption_file_path).exists():
                logger.error(f"Caption file not found: {caption_file_path}")
                return False
            
            logger.info(f"Generating caption preview GIF: {output_gif_path}")
            
            # Create a transparent background video with the specified duration
            # Using color filter to create transparent background
            background = ffmpeg.input(
                'color=c=black@0.0:s={}x{}:d={}'.format(width, height, duration),
                f='lavfi'
            )
            
            # Handle custom font if provided
            if font_file_path and Path(font_file_path).exists():
                abs_font_path = Path(font_file_path).resolve()
                abs_font_dir = abs_font_path.parent
                
                # Apply subtitles with custom font directory
                video_with_subs = background.filter('subtitles', caption_file_path, 
                                                  fontsdir=str(abs_font_dir),
                                                  force_style=f'FontName={font_family},FontSize={font_size},PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Shadow=1')
                logger.info(f"Using custom font directory: {abs_font_dir}")
            else:
                # Apply subtitles with default styling
                video_with_subs = background.filter('subtitles', caption_file_path, 
                                                  force_style=f'FontName={font_family},FontSize={font_size},PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Shadow=1')
            
            # Generate palette for better GIF quality
            palette_path = str(Path(output_gif_path).parent / "palette.png")
            
            # Create palette
            palette = video_with_subs.filter('palettegen', reserve_transparent=1)
            ffmpeg.output(palette, palette_path).run(overwrite_output=True, quiet=True)
            
            # Create GIF with transparency
            palette_input = ffmpeg.input(palette_path)
            
            gif_output = ffmpeg.output(
                video_with_subs, palette_input,
                output_gif_path,
                filter_complex='[0:v][1:v]paletteuse=alpha_threshold=128',
                r=10  # 10 FPS for smaller file size
            )
            
            ffmpeg.run(gif_output, overwrite_output=True, quiet=False)
            
            # Clean up palette file
            if Path(palette_path).exists():
                Path(palette_path).unlink()
            
            logger.info(f"Successfully generated caption preview GIF: {output_gif_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error generating caption preview GIF: {str(e)}")
            return False
    
    def generate_caption_style_preview_gif(
        self,
        caption_text: str,
        output_gif_path: str,
        style_name: str = "default",
        duration: float = 4.0,
        width: int = 400,
        height: int = 200
    ) -> bool:
        """
        Generate a GIF preview showing different caption styles
        
        Args:
            caption_text: Text to display in the caption
            output_gif_path: Output path for the GIF
            style_name: Style name (karaoke, word_by_word, sentence)
            duration: Duration of the GIF
            width: Width of the GIF
            height: Height of the GIF
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create temporary SRT file with the provided text
            temp_srt_path = self.temp_dir / f"temp_preview_{uuid.uuid4().hex}.srt"
            
            # Create SRT content based on style
            if style_name == "karaoke":
                # Simulate karaoke style with word highlighting
                words = caption_text.split()
                srt_content = ""
                word_duration = duration / len(words)
                
                for i, word in enumerate(words):
                    start_time = i * word_duration
                    end_time = (i + 1) * word_duration
                    
                    # Create highlighted version
                    highlighted_text = " ".join([
                        f"<font color='yellow'>{w}</font>" if j == i else w 
                        for j, w in enumerate(words)
                    ])
                    
                    srt_content += f"{i+1}\n"
                    srt_content += f"{self._seconds_to_srt_time(start_time)} --> {self._seconds_to_srt_time(end_time)}\n"
                    srt_content += f"{highlighted_text}\n\n"
                    
            elif style_name == "word_by_word":
                # Show one word at a time
                words = caption_text.split()
                srt_content = ""
                word_duration = duration / len(words)
                
                for i, word in enumerate(words):
                    start_time = i * word_duration
                    end_time = (i + 1) * word_duration
                    
                    srt_content += f"{i+1}\n"
                    srt_content += f"{self._seconds_to_srt_time(start_time)} --> {self._seconds_to_srt_time(end_time)}\n"
                    srt_content += f"{word}\n\n"
                    
            else:  # sentence style
                srt_content = f"1\n00:00:00,000 --> {self._seconds_to_srt_time(duration)}\n{caption_text}\n\n"
            
            # Write temporary SRT file
            with open(temp_srt_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)
            
            # Generate GIF using the main method
            success = self.generate_caption_preview_gif(
                str(temp_srt_path),
                output_gif_path,
                duration=duration,
                width=width,
                height=height,
                font_size=28,
                font_family="Arial Bold"
            )
            
            # Clean up temporary file
            if temp_srt_path.exists():
                temp_srt_path.unlink()
            
            return success
            
        except Exception as e:
            logger.error(f"Error generating caption style preview GIF: {str(e)}")
            return False
    
    def _seconds_to_srt_time(self, seconds: float) -> str:
        """Convert seconds to SRT time format (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    
    async def update_audio_file_path_in_jobs(self, audio_file_id: str, old_path: str, new_path: str) -> int:
        """
        Update audio file path in any video processing jobs that reference it
        
        This is critical for async TTS where the audio file path gets updated to GCS URL
        after the video job is created with the original local path.
        
        Args:
            audio_file_id: The audio file ID to search for
            old_path: The old file path (typically local path)
            new_path: The new file path (typically GCS URL)
            
        Returns:
            Number of jobs updated
        """
        updated_count = 0
        
        try:
            # Search through active jobs for ones that reference this audio file
            jobs_to_update = []
            
            for job_id, job in self.active_jobs.items():
                # Check if this job references the audio file by ID or path
                if (str(job.audio_file_id) == audio_file_id or 
                    job.audio_file_path == old_path):
                    jobs_to_update.append((job_id, job))
            
            # Update the jobs
            for job_id, job in jobs_to_update:
                logger.info(f"🔄 Updating video job {job_id} audio path:")
                logger.info(f"   From: {job.audio_file_path}")
                logger.info(f"   To:   {new_path}")
                
                # Update the audio file path to the new GCS URL
                job.audio_file_path = new_path
                
                # Also update the job in active_jobs dict
                self.active_jobs[job_id] = job
                updated_count += 1
                
                logger.info(f"✅ Updated video job {job_id} with GCS audio URL")
            
            return updated_count
            
        except Exception as e:
            logger.error(f"❌ Error updating video jobs with new audio path: {str(e)}")
            return 0
    
    async def process_image_background(
        self,
        background_config: Dict[str, Any],
        audio_duration: float,
        temp_background_path: str,
        processing_options: Optional[Any] = None
    ) -> bool:
        """
        Process image background configuration into video file
        
        Args:
            background_config: Configuration for image background
            audio_duration: Duration of audio track in seconds
            temp_background_path: Output path for generated background video
            processing_options: Video processing options including resolution and aspect ratio
            
        Returns:
            True if successful, False otherwise
        """
        try:
            background_type = background_config.get('type', 'unknown')
            logger.info(f"Processing image background: {background_type}")
            
            if background_type == 'single_image':
                return await self._process_single_image_background(
                    background_config,
                    audio_duration,
                    temp_background_path,
                    processing_options
                )
            elif background_type == 'image_timeline':
                return await self._process_image_timeline_background(
                    background_config,
                    audio_duration,
                    temp_background_path,
                    processing_options
                )
            else:
                logger.error(f"Unsupported image background type: {background_type}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing image background: {str(e)}")
            return False
    
    async def _process_single_image_background(
        self,
        background_config: Dict[str, Any],
        audio_duration: float,
        output_path: str,
        processing_options: Optional[Any] = None
    ) -> bool:
        """Process single static image background"""
        try:
            image_url = background_config.get('image_url')
            gcs_path = background_config.get('gcs_path')
            
            if not image_url and not gcs_path:
                logger.error("No image URL or GCS path provided")
                return False
            
            # Create timeline with single segment
            timeline = [{
                'image_url': image_url,
                'gcs_path': gcs_path,
                'start_time': 0,
                'end_time': audio_duration,
                'transition_type': 'cut',
                'transition_duration': 0
            }]
            
            # Extract video dimensions from processing options
            video_size = (1080, 1920)  # Default vertical video format
            fps = 30  # Default fps
            
            if processing_options:
                try:
                    # Get resolution from processing options (e.g., "607x1080")
                    resolution = processing_options.resolution if hasattr(processing_options, 'resolution') else processing_options.get('resolution', '1080x1920')
                    if isinstance(resolution, str) and 'x' in resolution:
                        width, height = map(int, resolution.split('x'))
                        video_size = (width, height)
                        logger.info(f"Using video dimensions from processing options: {video_size}")
                    
                    # Get fps from processing options if available
                    if hasattr(processing_options, 'fps'):
                        fps = processing_options.fps
                    elif isinstance(processing_options, dict) and 'fps' in processing_options:
                        fps = processing_options['fps']
                        
                except Exception as e:
                    logger.warning(f"Error parsing processing options, using defaults: {e}")
            
            # Use image service to create video
            success = await self.image_service.create_video_from_images(
                timeline=timeline,
                audio_duration=audio_duration,
                output_path=output_path,
                video_size=video_size,
                fps=fps
            )
            
            if success:
                logger.info(f"Successfully created single image background video: {output_path}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error processing single image background: {str(e)}")
            return False
    
    async def _process_image_timeline_background(
        self,
        background_config: Dict[str, Any],
        audio_duration: float,
        output_path: str,
        processing_options: Optional[Any] = None
    ) -> bool:
        """Process image timeline background with multiple images"""
        try:
            video_project_id = background_config.get('video_project_id')
            timeline_segments = background_config.get('timeline_segments', [])
            
            if not video_project_id and not timeline_segments:
                logger.error("No video project ID or timeline segments provided")
                return False
            
            # If we have a project ID, fetch timeline from database
            if video_project_id and not timeline_segments:
                timeline_segments = await self._fetch_image_timeline(video_project_id)
                if not timeline_segments:
                    logger.error(f"No timeline found for project: {video_project_id}")
                    return False
            
            # Convert timeline segments to format expected by image service
            timeline = []
            for segment in timeline_segments:
                timeline_item = {
                    'start_time': segment.get('start_time', 0),
                    'end_time': segment.get('end_time', 0),
                    'transition_type': segment.get('transition_type', 'cut'),
                    'transition_duration': segment.get('transition_duration', 0)
                }
                
                # Add image reference
                if 'image_url' in segment:
                    timeline_item['image_url'] = segment['image_url']
                elif 'gcs_path' in segment:
                    timeline_item['gcs_path'] = segment['gcs_path']
                elif 'image_id' in segment:
                    # Fetch image info from database
                    image_info = await self._fetch_image_info(segment['image_id'])
                    if image_info:
                        timeline_item['gcs_path'] = image_info.get('gcs_path')
                    else:
                        logger.warning(f"Image not found for ID: {segment['image_id']}")
                        continue
                
                timeline.append(timeline_item)
            
            if not timeline:
                logger.error("No valid timeline segments found")
                return False
            
            # Extract video dimensions from processing options
            video_size = (1080, 1920)  # Default vertical video format
            fps = 30  # Default fps
            
            if processing_options:
                try:
                    # Get resolution from processing options (e.g., "607x1080")
                    resolution = processing_options.resolution if hasattr(processing_options, 'resolution') else processing_options.get('resolution', '1080x1920')
                    if isinstance(resolution, str) and 'x' in resolution:
                        width, height = map(int, resolution.split('x'))
                        video_size = (width, height)
                        logger.info(f"Using video dimensions from processing options: {video_size}")
                    
                    # Get fps from processing options if available
                    if hasattr(processing_options, 'fps'):
                        fps = processing_options.fps
                    elif isinstance(processing_options, dict) and 'fps' in processing_options:
                        fps = processing_options['fps']
                        
                except Exception as e:
                    logger.warning(f"Error parsing processing options, using defaults: {e}")
            
            # Use image service to create video
            success = await self.image_service.create_video_from_images(
                timeline=timeline,
                audio_duration=audio_duration,
                output_path=output_path,
                video_size=video_size,
                fps=fps
            )
            
            if success:
                logger.info(f"Successfully created image timeline background video: {output_path}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error processing image timeline background: {str(e)}")
            return False
    
    async def _fetch_image_timeline(self, video_project_id: str) -> List[Dict[str, Any]]:
        """Fetch image timeline from database"""
        try:
            if not self.supabase_client:
                logger.error("Database not available")
                return []
            
            # Get timeline segments with image information
            result = self.supabase_client.supabase.table('video_image_timelines').select('''
                *,
                user_images (
                    gcs_path,
                    gcs_signed_url,
                    width,
                    height
                )
            ''').eq('video_project_id', video_project_id).order('sort_order').execute()
            
            timeline_segments = []
            for item in result.data:
                image_info = item.get('user_images', {})
                
                timeline_segments.append({
                    'image_id': item['image_id'],
                    'gcs_path': image_info.get('gcs_path'),
                    'start_time': item['start_time'],
                    'end_time': item['end_time'],
                    'transition_type': item['transition_type'],
                    'transition_duration': item['transition_duration'],
                    'sort_order': item['sort_order']
                })
            
            logger.info(f"Fetched {len(timeline_segments)} timeline segments for project: {video_project_id}")
            return timeline_segments
            
        except Exception as e:
            logger.error(f"Error fetching image timeline: {str(e)}")
            return []
    
    async def _fetch_image_info(self, image_id: str) -> Optional[Dict[str, Any]]:
        """Fetch image information from database"""
        try:
            if not self.supabase_client:
                logger.error("Database not available")
                return None
            
            result = self.supabase_client.supabase.table('user_images').select('*').eq('id', image_id).single().execute()
            
            if result.data:
                return result.data
            else:
                logger.warning(f"Image not found: {image_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching image info: {str(e)}")
            return None
    
    async def _generate_background_video_from_config(
        self,
        background_config: Dict[str, Any],
        audio_duration: float
    ) -> Optional[str]:
        """
        Generate background video from configuration (supports both video and image backgrounds)
        
        Args:
            background_config: Background configuration
            audio_duration: Duration of audio track in seconds
            
        Returns:
            Path to generated background video or None if failed
        """
        try:
            background_type = background_config.get('type', 'video')
            
            if background_type in ['single_image', 'image_timeline']:
                # Generate temporary background video from images
                temp_bg_filename = f"temp_bg_{uuid.uuid4().hex}.mp4"
                temp_bg_path = self.temp_dir / temp_bg_filename
                
                success = await self.process_image_background(
                    background_config,
                    audio_duration,
                    str(temp_bg_path)
                )
                
                if success and temp_bg_path.exists():
                    logger.info(f"Generated image background video: {temp_bg_path}")
                    return str(temp_bg_path)
                else:
                    logger.error("Failed to generate image background video")
                    return None
            
            elif background_type == 'video':
                # Use existing video background logic
                video_url = background_config.get('video_url', background_config.get('background_video_url'))
                if video_url:
                    return video_url
                else:
                    logger.error("No video URL provided for video background")
                    return None
            
            else:
                logger.error(f"Unsupported background type: {background_type}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating background video from config: {str(e)}")
            return None

    def __del__(self):
        """Cleanup when service is destroyed"""
        if hasattr(self, '_processing_task') and self._processing_task:
            self._processing_task.cancel()
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)


# Global instance
_video_service = None

def get_video_service() -> VideoProcessingService:
    """Get or create video processing service instance"""
    global _video_service
    if _video_service is None:
        _video_service = VideoProcessingService()
    return _video_service