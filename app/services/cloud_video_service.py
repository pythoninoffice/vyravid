"""
Cloud Video Service for integrating with cloud-video-processor

This service handles communication between the webapp and the cloud-video-processor
running on Google Cloud Run, including authentication, request/response transformation,
and error handling.
"""

import os
import asyncio
import aiohttp
import json
import uuid
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

from google.oauth2 import service_account
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

class CloudVideoServiceError(Exception):
    """Custom exception for cloud video service errors"""
    pass

class CloudVideoService:
    """
    Service for communicating with cloud-video-processor
    
    Handles:
    - Authentication with Google Service Account
    - Request transformation (webapp format → cloud format)
    - Response transformation (cloud format → webapp format)  
    - Error handling and retry logic
    """
    
    def __init__(self):
        """Initialize cloud video service with configuration"""
        self.cloud_processor_url = os.getenv('CLOUD_VIDEO_PROCESSOR_URL') or (os.getenv('VYRAVID_PUBLIC_BASE', 'http://localhost:8000').rstrip('/') + '/vp')
        self.use_cloud_processing = os.getenv('USE_CLOUD_PROCESSING', 'true').lower() == 'true'
        self.webhook_base_url = os.getenv('WEBHOOK_BASE_URL', 'http://localhost:8000')
        
        if not self.cloud_processor_url and self.use_cloud_processing:
            raise ValueError("CLOUD_VIDEO_PROCESSOR_URL must be set when USE_CLOUD_PROCESSING is true")
            
        # Service account for authentication
        self.service_account_file = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        self.credentials = None
        self.access_token = None
        self.token_expiry = None
        
        if self.use_cloud_processing:
            self._initialize_auth()
    
    def _initialize_auth(self):
        """Initialize auth — local mode skips Google credentials."""
        if os.getenv("VYRAVID_LOCAL", "true").lower() == "true":
            logger.info("🔓 Local mode: skipping Google service account auth")
            self.credentials = None
            self.access_token = "local-token"
            return
        try:
            logger.info(f"🔐 Initializing authentication...")
            logger.info(f"🔐 Service account file from env: {self.service_account_file}")
            
            if self.service_account_file:
                # Try to use service account file first (for local development)
                try:
                    # Handle both absolute and relative paths
                    service_account_path = Path(self.service_account_file)
                    logger.info(f"🔐 Trying service account file: {service_account_path}")
                    
                    if not service_account_path.is_absolute():
                        # Convert relative path to absolute (relative to app directory)
                        app_dir = Path(__file__).parent.parent  # Go up from services/ to app/
                        service_account_path = app_dir / self.service_account_file
                        logger.info(f"🔐 Resolved to absolute path: {service_account_path}")
                    
                    if service_account_path.exists():
                        self.credentials = service_account.Credentials.from_service_account_file(
                            str(service_account_path),
                            scopes=['https://www.googleapis.com/auth/cloud-platform']
                        )
                        logger.info("✅ Service account credentials loaded from file")
                    else:
                        logger.warning(f"⚠️ Service account file not found at: {service_account_path}")
                        logger.info("🔄 Falling back to Application Default Credentials")
                        from google.auth import default
                        self.credentials, _ = default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
                        logger.info("✅ Application Default Credentials loaded")
                        
                except Exception as file_error:
                    logger.warning(f"⚠️ Failed to load service account file: {str(file_error)}")
                    logger.info("🔄 Falling back to Application Default Credentials")
                    from google.auth import default
                    self.credentials, _ = default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
                    logger.info("✅ Application Default Credentials loaded")
            else:
                logger.info("🔄 No service account file specified, using Application Default Credentials")
                # Use Application Default Credentials (for Cloud Run environment with attached service account)
                from google.auth import default
                self.credentials, _ = default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
                logger.info("✅ Application Default Credentials loaded")
        except Exception as e:
            logger.error(f"❌ Failed to initialize authentication: {str(e)}")
            if self.use_cloud_processing:
                raise CloudVideoServiceError(f"Authentication setup failed: {str(e)}")
    
    async def _get_access_token(self) -> str:
        """Get or refresh access token"""
        try:
            if os.getenv("VYRAVID_LOCAL", "true").lower() == "true":
                return "local-token"
            if not self.credentials:
                raise CloudVideoServiceError("No credentials available")
            
            # Check if token needs refresh
            if not self.access_token or (self.token_expiry and datetime.now() >= self.token_expiry):
                logger.info("🔄 Refreshing access token...")
                
                # Refresh token
                request = Request()
                self.credentials.refresh(request)
                self.access_token = self.credentials.token
                
                # Set expiry time (tokens typically expire in 1 hour)
                from datetime import timedelta
                self.token_expiry = datetime.now() + timedelta(minutes=55)  # Refresh 5 min early
                
                logger.info("✅ Access token refreshed successfully")
            
            return self.access_token
            
        except Exception as e:
            logger.error(f"❌ Failed to get access token: {str(e)}")
            raise CloudVideoServiceError(f"Token generation failed: {str(e)}")
    
    def _transform_webapp_to_cloud_request(self,
                                         audio_url: Optional[str] = None,
                                         background_video_url: Optional[str] = None,
                                         background_image_url: Optional[str] = None,
                                         background_type: str = "video",
                                         image_timeline: Optional[List[Dict[str, Any]]] = None,
                                         use_xfade_transitions: bool = False,
                                         caption_settings: Dict[str, Any] = None,
                                         processing_options: Dict[str, Any] = None,
                                         project_id: str = None,
                                         user_id: str = None,
                                         background_music_id: Optional[str] = None,
                                         music_volume: Optional[float] = None,
                                         music_fade_in: Optional[float] = None,
                                         music_fade_out: Optional[float] = None,
                                         language_code: Optional[str] = None,
                                         text_overlays: Optional[List[Dict[str, Any]]] = None,
                                         watermark_logo_url: Optional[str] = None,
                                         watermark_logo_gcs_path: Optional[str] = None,
                                         watermark_logo_position: Optional[str] = None) -> Dict[str, Any]:
        """
        Transform webapp request format to cloud-video-processor MediaProcessingRequest
        
        Args:
            audio_url: URL from MiniMax TTS API
            background_video_url: GCS URL for background video template
            caption_settings: Webapp caption configuration
            processing_options: Webapp processing configuration  
            project_id: Video project ID (used as job identifier)
            user_id: User identifier
            
        Returns:
            Cloud-video-processor request format
        """
        # Extract caption settings with defaults
        font_family = caption_settings.get('font_family', 'Luckiest Guy')
        font_size = caption_settings.get('font_size', 32)
        position = caption_settings.get('position', 'middle')
        highlight_color = caption_settings.get('highlight_color', '&H00FFFF&')
        default_color = caption_settings.get('default_color', '&HFFFFFF&')
        subtitle_style = caption_settings.get('subtitle_style', 'karaoke')
        
        # Map webapp colors to cloud format (remove &H and & wrappers)
        # def clean_color(color_str: str) -> str:
        #     """Convert &HFFFFFF& format to white or hex"""
        #     if isinstance(color_str, str):
        #         color_str = color_str.replace('&H', '').replace('&', '')
        #         if color_str.upper() == 'FFFFFF':
        #             return 'white'
        #         elif color_str.upper() == '000000':
        #             return 'black'
        #         elif color_str.upper() == '00FFFF':
        #             return 'cyan'  
        #         return f"#{color_str}"
        #     return 'white'
        
        # Build cloud request
        # Ensure we have a valid job_id (use project_id or generate fallback)
        job_id = project_id if project_id else str(uuid.uuid4())
        logger.warning(f"⚠️ Using job_id: {job_id} (project_id was: {project_id})")

        # Determine operation type based on whether audio is provided
        operation = "full_pipeline" if audio_url else "video_only"
        logger.info(f"🎬 Cloud processing operation: {operation} (audio: {'yes' if audio_url else 'no'})")

        cloud_request = {
            "job_id": job_id,
            "operation": operation,
            "background_type": background_type,
            "video_parameters": {
                "resolution": processing_options.get("resolution", "1280x720"),
                "aspect_ratio": processing_options.get("aspect_ratio", "16:9"),
                "resolution_label": processing_options.get("resolution_label"),
                "upscale_mode": processing_options.get("upscale_mode", "none"),
                "fps": processing_options.get("fps", 30),
                "subtitle_style": {
                    "font_name": font_family,
                    "font_size": font_size,
                    "font_color": default_color,
                    "outline_color": "&H000000&",  # Black outline
                    "outline_width": 2
                }
            },
            "webhook_url": f"{self.webhook_base_url}/api/video/webhook/cloud-processing",
            "user_id": user_id,  # Include user_id for proper file organization
            # Music parameters
            "background_music_id": background_music_id,
            "music_volume": music_volume,
            "music_fade_in": music_fade_in,
            "music_fade_out": music_fade_out,
            # Language code for multi-language support
            "language_code": language_code,
            "watermark_logo_url": watermark_logo_url,
            "watermark_logo_gcs_path": watermark_logo_gcs_path,
            "watermark_logo_position": watermark_logo_position or "bottom_right"
        }

        # Always pass transcription/caption preferences so cloud can decide whether to render captions
        # even in fallback video-only flows where audio is resolved server-side.
        transcription_service = os.getenv(
            "TRANSCRIPTION_SERVICE",
            "faster-whisper" if os.getenv("VYRAVID_LOCAL", "true").lower() == "true" else "assemblyai"
        )
        cloud_request["transcription_config"] = {
            "service": transcription_service,
            "caption_style": subtitle_style,
            "font_size": font_size,
            "font_family": font_family,
            "position": position.lower(),
            "default_color": default_color,
            "highlight_color": highlight_color
        }

        # Add text overlays if provided
        if text_overlays:
            cloud_request["text_overlays"] = text_overlays
            logger.info(f"📝 Added {len(text_overlays)} text overlays to cloud request")

        # Add audio-specific fields only if audio is provided
        if audio_url:
            cloud_request["audio_sources"] = [
                {
                    "url": audio_url,
                    "type": "url",
                    "duration": 0  # Will be determined by cloud service
                }
            ]
            logger.info(f"🎵 Audio URL provided - including audio_sources and transcription_config")
        else:
            logger.info(f"🎵 No audio URL - video-only mode (no transcription)")

        # Add background-specific fields
        if background_type == "video" and background_video_url:
            cloud_request["video_files"] = [
                {
                    "url": background_video_url,
                    "duration": 0  # Will be determined by cloud service
                }
            ]
        elif background_type == "image" and background_image_url:
            cloud_request["background_image_url"] = background_image_url
        elif background_type == "image_timeline" and image_timeline:
            # Validate that all timeline segments have valid image_url
            validated_timeline = []
            for i, segment in enumerate(image_timeline):
                image_url = segment.get('image_url')
                if image_url and image_url.strip():
                    validated_timeline.append(segment)
                    logger.info(f"✅ Timeline segment {i} has valid image_url: {image_url[:50]}...")
                else:
                    logger.warning(f"⚠️  Skipping timeline segment {i} - missing or empty image_url: {image_url}")

            if validated_timeline:
                cloud_request["image_timeline"] = validated_timeline
                cloud_request["use_xfade_transitions"] = use_xfade_transitions
                logger.info(f"🎬 Added {len(validated_timeline)} validated timeline segments (out of {len(image_timeline)} original)")
                logger.info(f"🎬 XFADE DEBUG: Adding use_xfade_transitions={use_xfade_transitions} to cloud request for image_timeline")
            else:
                logger.error("❌ No valid timeline segments found - all segments have missing or empty image_url")
                raise CloudVideoServiceError("All timeline segments have invalid image URLs")
        
        logger.info(f"📤 Transformed webapp request to cloud format for project {project_id}")
        return cloud_request
    
    def _transform_cloud_to_webapp_response(self, 
                                          cloud_response: Dict[str, Any],
                                          original_audio_file_id: str,
                                          original_duration: float) -> Dict[str, Any]:
        """
        Transform cloud-video-processor response to webapp format
        
        Args:
            cloud_response: Response from cloud-video-processor webhook
            original_audio_file_id: Original audio file ID from MiniMax
            original_duration: Original audio duration
            
        Returns:
            Webapp response format
        """
        try:
            result = cloud_response.get('result', {})
            output_files = result.get('output_files', [])
            
            # Find the video file (typically the last in the list)
            video_url = None
            for file_url in output_files:
                if any(ext in file_url.lower() for ext in ['.mp4', '.mov', '.avi']):
                    video_url = file_url
                    break
            
            if not video_url and output_files:
                # Fallback to last file if no video extension found
                video_url = output_files[-1]
            
            # Build webapp response
            webapp_response = {
                "video_url": video_url,
                "audio_file_id": original_audio_file_id,
                "duration": original_duration,
                "job_id": cloud_response.get('job_id'),
                "message": "Video generated successfully using cloud processing",
                "cloud_hosted": True,
                "gcs_info": {
                    "gcs_path": video_url,
                    "public_url": video_url,
                    "signed_url": video_url,  # Assuming cloud returns signed URLs
                    "cloud_storage": True
                },
                "processing_time": result.get('total_time_seconds', 0),
                "output_files": output_files
            }
            
            logger.info(f"📥 Transformed cloud response to webapp format for project {cloud_response.get('job_id')}")
            return webapp_response
            
        except Exception as e:
            logger.error(f"❌ Failed to transform cloud response: {str(e)}")
            raise CloudVideoServiceError(f"Response transformation failed: {str(e)}")
    
    async def submit_video_processing_job(self,
                                        audio_url: Optional[str] = None,
                                        background_video_url: Optional[str] = None,
                                        background_image_url: Optional[str] = None,
                                        background_type: str = "video",
                                        image_timeline: Optional[List[Dict[str, Any]]] = None,
                                        use_xfade_transitions: bool = False,
                                        caption_settings: Dict[str, Any] = None,
                                        processing_options: Dict[str, Any] = None,
                                        user_id: str = None,
                                        project_id: str = None,
                                        project_title: str = None,
                                        background_music_id: Optional[str] = None,
                                        music_volume: Optional[float] = None,
                                        music_fade_in: Optional[float] = None,
                                        music_fade_out: Optional[float] = None,
                                        language_code: Optional[str] = None,
                                        text_overlays: Optional[List[Dict[str, Any]]] = None,
                                        watermark_logo_url: Optional[str] = None,
                                        watermark_logo_gcs_path: Optional[str] = None,
                                        watermark_logo_position: Optional[str] = None) -> Dict[str, Any]:
        """
        Submit video processing job to cloud-video-processor
        
        Args:
            audio_url: URL from MiniMax TTS API
            background_video_url: GCS URL for background video
            caption_settings: Caption configuration
            processing_options: Processing configuration
            user_id: User identifier
            project_id: Video project ID (used as cloud job identifier)
            project_title: Optional project title
            
        Returns:
            Job submission response
        """
        try:
            logger.info(f"🚀 CloudVideoService.submit_video_processing_job called")
            logger.info(f"📦 Parameters received:")
            logger.info(f"  - audio_url: {audio_url}")
            logger.info(f"  - background_video_url: {background_video_url}")
            logger.info(f"  - background_type: {background_type}")
            logger.info(f"  - image_timeline: {len(image_timeline) if image_timeline else 0} segments")
            logger.info(f"  - use_xfade_transitions: {use_xfade_transitions}")
            logger.info(f"  - caption_settings: {caption_settings}")
            logger.info(f"  - processing_options: {processing_options}")
            logger.info(f"  - user_id: {user_id}")
            logger.info(f"  - project_id: {project_id}")
            logger.info(f"  - project_title: {project_title}")
            logger.info(f"  - background_music_id: {background_music_id}")
            logger.info(f"  - music_volume: {music_volume}")
            logger.info(f"  - music_fade_in: {music_fade_in}")
            logger.info(f"  - music_fade_out: {music_fade_out}")
            logger.info(f"  - language_code: {language_code}")
            logger.info(f"  - watermark_logo_url: {watermark_logo_url[:80] + '...' if watermark_logo_url else None}")
            logger.info(f"  - watermark_logo_gcs_path: {watermark_logo_gcs_path}")
            logger.info(f"  - watermark_logo_position: {watermark_logo_position}")

            if not self.use_cloud_processing:
                logger.error("❌ Cloud processing is disabled")
                raise CloudVideoServiceError("Cloud processing is disabled")
            
            # Get access token
            logger.info("🔑 Getting access token...")
            access_token = await self._get_access_token()
            logger.info("✅ Access token retrieved successfully")
            
            # Transform request (using project_id as job_id)
            logger.info("🔄 Transforming webapp request to cloud format...")
            cloud_request = self._transform_webapp_to_cloud_request(
                audio_url=audio_url,
                background_video_url=background_video_url,
                background_image_url=background_image_url,
                background_type=background_type,
                image_timeline=image_timeline,
                use_xfade_transitions=use_xfade_transitions,
                caption_settings=caption_settings or {},
                processing_options=processing_options or {},
                project_id=project_id,
                user_id=user_id,
                background_music_id=background_music_id,
                music_volume=music_volume,
                music_fade_in=music_fade_in,
                music_fade_out=music_fade_out,
                language_code=language_code,
                text_overlays=text_overlays,
                watermark_logo_url=watermark_logo_url,
                watermark_logo_gcs_path=watermark_logo_gcs_path,
                watermark_logo_position=watermark_logo_position
            )
            logger.info(f"📤 Cloud request transformed: {json.dumps(cloud_request, indent=2)}")
            
            # Make HTTP request to cloud-video-processor
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {access_token}'
            }
            
            url = f"{self.cloud_processor_url}/process-media"
            
            logger.info(f"🚀 Submitting project {project_id} to cloud-video-processor")
            logger.info(f"   URL: {url}")
            logger.info(f"   Audio URL: {audio_url[:50] + '...' if audio_url else 'None (video-only mode)'}")
            logger.info(f"   Background Type: {background_type}")
            logger.info(f"   Background Video: {background_video_url}")
            logger.info(f"   Background Image: {background_image_url}")
            
            timeout = aiohttp.ClientTimeout(total=3600)  # 60 minute timeout for cloud submission
            
            logger.info(f"🌐 Starting HTTP session to cloud processor...")
            
            # Retry logic for network resilience
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        logger.info(f"📡 Sending POST request to {url} (attempt {attempt + 1}/{max_retries})")
                        logger.info(f"📋 Headers: {headers}")
                        
                        async with session.post(url, json=cloud_request, headers=headers) as response:
                            logger.info(f"📨 Received response with status: {response.status}")
                            
                            if response.status == 200:
                                response_data = await response.json()
                                logger.info(f"✅ Project {project_id} submitted successfully to cloud")
                                logger.info(f"📊 Response data: {response_data}")
                                
                                return {
                                    "job_id": project_id,
                                    "status": "submitted",
                                    "message": "Video processing job submitted to cloud",
                                    "project_id": project_id,
                                    "submitted_at": datetime.now().isoformat()
                                }
                            else:
                                error_text = await response.text()
                                logger.error(f"❌ Cloud submission failed with status {response.status}")
                                logger.error(f"❌ Error response body: {error_text}")
                                logger.error(f"❌ Response headers: {dict(response.headers)}")
                                if attempt == max_retries - 1:  # Last attempt
                                    raise CloudVideoServiceError(f"Cloud submission failed: {response.status} - {error_text}")
                                else:
                                    logger.info(f"🔄 Retrying in 5 seconds...")
                                    await asyncio.sleep(5)
                                    continue
                                    
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.error(f"❌ Network error during cloud submission (attempt {attempt + 1}/{max_retries}): {type(e).__name__}: {str(e)}")
                    if attempt == max_retries - 1:  # Last attempt
                        import traceback
                        logger.error(f"❌ Final attempt failed, traceback: {traceback.format_exc()}")
                        raise CloudVideoServiceError(f"Network error after {max_retries} attempts: {str(e)}")
                    else:
                        logger.info(f"🔄 Retrying in 10 seconds...")
                        await asyncio.sleep(10)
                        continue
                        
            # This should never be reached due to the return/raise in the loop
            raise CloudVideoServiceError("All retry attempts exhausted")
                        
        except Exception as e:
            logger.error(f"❌ Unexpected error during cloud submission: {type(e).__name__}: {str(e)}")
            logger.error(f"❌ Error details: {repr(e)}")
            import traceback
            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
            raise CloudVideoServiceError(f"Cloud submission failed: {str(e)}")
    
    def is_cloud_processing_enabled(self) -> bool:
        """Check if cloud processing is enabled"""
        return self.use_cloud_processing
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on cloud-video-processor service
        
        Returns:
            Health status information
        """
        try:
            if not self.use_cloud_processing:
                return {"status": "disabled", "message": "Cloud processing is disabled"}
            
            # Health checks typically don't require authentication
            url = f"{self.cloud_processor_url}/health"
            timeout = aiohttp.ClientTimeout(total=10)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return {"status": "healthy", "cloud_service": "available"}
                    else:
                        return {"status": "unhealthy", "error": f"HTTP {response.status}"}
                        
        except Exception as e:
            logger.warning(f"Cloud service health check failed: {str(e)}")
            return {"status": "unhealthy", "error": str(e)}

# Global instance for use across the application
cloud_video_service = CloudVideoService()
