import asyncio
import uuid
import json
import logging
from datetime import datetime
from typing import Dict, Optional, List
import aiohttp
from pathlib import Path

from models.story_models import VideoProcessingJob, GenerationStatus
from services.gcs_service import get_gcs_service

logger = logging.getLogger(__name__)

class CloudRunVideoProcessingService:
    def __init__(self, cloud_run_url: str, max_concurrent_jobs: int = 10):
        """
        Simplified video processing service using Google Cloud Run
        
        Args:
            cloud_run_url: URL of the Cloud Run video processing service
            max_concurrent_jobs: Max concurrent jobs to send to Cloud Run
        """
        self.cloud_run_url = cloud_run_url
        self.max_concurrent_jobs = max_concurrent_jobs
        
        # Lightweight job tracking (no heavy processing queue)
        self.active_jobs: Dict[str, VideoProcessingJob] = {}
        self.job_semaphore = asyncio.Semaphore(max_concurrent_jobs)
        
        # Directories for metadata only
        self.videos_dir = Path("data/videos")
        self.videos_dir.mkdir(parents=True, exist_ok=True)
    
    async def create_video_processing_job(
        self,
        audio_file_path: str,
        background_video_paths: List[str],
        caption_file_path: Optional[str] = None,
        processing_options: Optional[Dict] = None,
        user_id: Optional[str] = None,
        project_title: Optional[str] = None
    ) -> VideoProcessingJob:
        """
        Create job and immediately send to Cloud Run (no local queue)
        """
        job_id = str(uuid.uuid4())
        
        job = VideoProcessingJob(
            id=uuid.UUID(job_id),
            output_file_path=f"cloud_run_output_{job_id}.mp4",  # Required field
            background_video_paths=background_video_paths,
            caption_file_path=caption_file_path,
            processing_options=processing_options or {},
            created_at=datetime.now(),
            user_id=user_id or "unknown-user",
            project_title=project_title,
            status=GenerationStatus.QUEUED
        )
        
        # Track job
        self.active_jobs[job_id] = job
        
        # Send to Cloud Run immediately (no local queue)
        asyncio.create_task(self._send_to_cloud_run(job))
        
        return job
    
    async def _send_to_cloud_run(self, job: VideoProcessingJob):
        """Send job to Cloud Run service"""
        async with self.job_semaphore:  # Limit concurrent Cloud Run calls
            try:
                job.status = GenerationStatus.GENERATING
                job.started_at = datetime.now()
                
                # Prepare payload for Cloud Run
                payload = {
                    "job_id": str(job.id),
                    "audio_file_path": job.audio_file_path,
                    "background_video_paths": job.background_video_paths,
                    "caption_file_path": job.caption_file_path,
                    "processing_options": job.processing_options,
                    "user_id": job.user_id
                }
                
                # Send to Cloud Run
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.cloud_run_url}/process-video",
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=300)  # 5 min timeout
                    ) as response:
                        
                        if response.status == 200:
                            result = await response.json()
                            
                            # Update job with Cloud Run result
                            job.status = GenerationStatus.COMPLETED
                            job.output_file_path = result.get("output_file_path")
                            job.gcs_path = result.get("gcs_path")
                            job.signed_url = result.get("signed_url")
                            job.completed_at = datetime.now()
                            
                            logger.info(f"Cloud Run job completed: {job.id}")
                            
                        else:
                            raise Exception(f"Cloud Run returned {response.status}")
                            
            except Exception as e:
                logger.error(f"Cloud Run job failed: {job.id}, error: {e}")
                job.status = GenerationStatus.FAILED
                job.error_message = str(e)
                job.completed_at = datetime.now()
            
            finally:
                # Save job metadata
                await self._save_job_metadata(job)
    
    async def get_job_status(self, job_id: str) -> Optional[VideoProcessingJob]:
        """Get job status (from memory or metadata file)"""
        if job_id in self.active_jobs:
            return self.active_jobs[job_id]
        
        return await self._load_job_metadata(job_id)
    
    async def _save_job_metadata(self, job: VideoProcessingJob):
        """Save job metadata to file"""
        try:
            metadata_file = self.videos_dir / f"job_{job.id}.json"
            metadata = job.model_dump()
            
            # Convert non-serializable objects
            if 'id' in metadata:
                metadata['id'] = str(metadata['id'])
            if 'created_at' in metadata and metadata['created_at']:
                metadata['created_at'] = metadata['created_at'].isoformat()
            if 'started_at' in metadata and metadata['started_at']:
                metadata['started_at'] = metadata['started_at'].isoformat()
            if 'completed_at' in metadata and metadata['completed_at']:
                metadata['completed_at'] = metadata['completed_at'].isoformat()
            
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving job metadata: {e}")
    
    async def _load_job_metadata(self, job_id: str) -> Optional[VideoProcessingJob]:
        """Load job metadata from file"""
        try:
            metadata_file = self.videos_dir / f"job_{job_id}.json"
            
            if not metadata_file.exists():
                return None
            
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            # Convert datetime strings back
            if metadata.get('created_at'):
                metadata['created_at'] = datetime.fromisoformat(metadata['created_at'])
            if metadata.get('started_at'):
                metadata['started_at'] = datetime.fromisoformat(metadata['started_at'])
            if metadata.get('completed_at'):
                metadata['completed_at'] = datetime.fromisoformat(metadata['completed_at'])
            
            return VideoProcessingJob(**metadata)
            
        except Exception as e:
            logger.error(f"Error loading job metadata: {e}")
            return None