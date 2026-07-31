"""
Image Generation Service
Orchestrates image generation using various providers and integrates with existing services
"""

import asyncio
import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
import requests
from io import BytesIO

from services.providers.replicate_provider import ReplicateProvider
from services.providers.google_provider import GoogleProvider
from services.gcs_service import GCSService
from services.supabase import get_supabase_client

logger = logging.getLogger(__name__)

class ImageGenerationService:
    """Service for orchestrating image generation with multiple providers"""
    
    def __init__(self):
        """Initialize image generation service"""
        self.providers = {
            'replicate': ReplicateProvider(),
            'google': GoogleProvider()
        }
        self.gcs_service = GCSService()
        self.supabase = get_supabase_client()
    
    def is_available(self) -> bool:
        """Check if image generation service is available"""
        return (
            any(provider.is_available() for provider in self.providers.values()) and
            self.gcs_service.is_available() and
            self.supabase is not None
        )

    async def generate_image(
        self,
        user_id: str,
        prompt: str,
        provider: str = "replicate",
        model: str = "prunaai/z-image-turbo:7ea16386290ff5977c7812e66e462d7ec3954d8e007a8cd18ded3e7d41f5d7cf",
        width: int = 1024,
        height: int = 1024,
        num_outputs: int = 1,
        is_character_reference: bool = False,
        character_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        user_type: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate image and upload to GCS

        Args:
            user_id: ID of the user requesting generation
            prompt: Text prompt for image generation
            provider: Provider to use (default: replicate)
            model: Model to use for generation
            width: Image width
            height: Image height
            num_outputs: Number of images to generate
            is_character_reference: Whether this is a character reference image (hidden from main gallery)
            character_id: Optional character ID if this is a character reference
            user_type: Optional user type for permission checking (e.g., 'admin')
            **kwargs: Additional provider-specific parameters

        Returns:
            Dict with generation result including database record
        """
        if not self.is_available():
            raise Exception("Image generation service not available")

        if provider not in self.providers:
            raise Exception(f"Provider '{provider}' not available")

        if not self.providers[provider].is_available():
            raise Exception(f"Provider '{provider}' not initialized")

        # Check if user has permission to use admin-only models
        if self._is_admin_only_model(model) and user_type != 'admin':
            raise Exception(f"The model '{model}' is only available to admin users")

        if self._is_premium_model(model) and (user_type not in ['premium', 'admin']):
            raise Exception(f"The model '{model}' is only availabe to premium users")

        normalized_prompt = prompt.strip()

        # Validate inputs
        if not normalized_prompt:
            raise Exception("Prompt cannot be empty")

        generation_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        try:
            logger.info(f"Starting image generation for user {user_id}: {prompt[:50]}...")
            
            if model in ['bytedance/seedream-4','bytedance/seedream-4.5']:
                if width < 1024:
                    width = 1024
                    height = 1820
                elif height < 1024:
                    height = 1024
                    width = 1820
           
            # Create initial database record
            db_record = await self._create_generation_record(
                generation_id=generation_id,
                user_id=user_id,
                prompt=normalized_prompt,
                model=model,
                provider=provider,
                width=width,
                height=height,
                num_outputs=num_outputs,
                is_character_reference=is_character_reference,
                character_id=character_id,
                tags=tags
            )
            
            # Generate image using provider


            generation_result = await self.providers[provider].generate_image(
                prompt=normalized_prompt,
                model=model,
                width=width,
                height=height,
                num_outputs=num_outputs,
                **kwargs
            )
            
            if generation_result['status'] != 'completed':
                # Delete the pending record since generation failed
                try:
                    if self.supabase:
                        self.supabase.table('generated_images').delete().eq('id', generation_id).execute()
                        logger.info(f"Deleted failed generation record: {generation_id}")
                except Exception as delete_error:
                    logger.error(f"Failed to delete generation record {generation_id}: {str(delete_error)}")

                raise Exception(f"Image generation failed: {generation_result.get('error', 'Unknown error')}")
            
            # Download and upload images to GCS
            uploaded_images = []

            # Handle different provider response formats
            # Google provider returns 'images' with direct image_data
            # Replicate provider returns 'image_urls' with URLs to download
            if 'images' in generation_result and generation_result['images']:
                # Provider returned image data directly (Google)
                for i, image_info in enumerate(generation_result['images']):
                    try:
                        image_bytes = image_info['image_data']
                        actual_width = image_info.get('width', width)
                        actual_height = image_info.get('height', height)

                        # Generate unique image ID for each image in the batch
                        image_id = f"{generation_id}_{i+1}" if i > 0 else generation_id

                        # Upload to GCS
                        upload_result = await self.gcs_service.upload_image(
                            image_bytes=image_bytes,
                            user_id=user_id,
                            image_id=image_id,
                            original_name=f"ai_generated_{i+1}.png",
                            mime_type="image/png",
                            metadata={
                                'generation_id': generation_id,
                                'prompt': normalized_prompt,
                                'model': model,
                                'provider': provider,
                                'image_index': i + 1
                            }
                        )

                        if upload_result:
                            uploaded_images.append({
                                'index': i + 1,
                                'gcs_path': upload_result['gcs_path'],
                                'signed_url': upload_result['signed_url'],
                                'thumbnail_gcs_path': upload_result.get('thumbnail_gcs_path'),
                                'thumbnail_signed_url': upload_result.get('thumbnail_signed_url'),
                                'width': actual_width,
                                'height': actual_height,
                                'file_size': upload_result.get('file_size', 0)
                            })

                            logger.info(f"Uploaded image {i+1} to GCS: {upload_result['gcs_path']}")
                        else:
                            logger.error(f"Failed to upload image {i+1} to GCS")

                    except Exception as e:
                        logger.error(f"Error processing image {i+1}: {str(e)}")
                        continue

            elif 'image_urls' in generation_result:
                # Provider returned URLs to download (Replicate)
                for i, image_url in enumerate(generation_result['image_urls']):
                    try:
                        # Download image from provider
                        image_bytes = await self._download_image(image_url)

                        # Generate unique image ID for each image in the batch
                        image_id = f"{generation_id}_{i+1}" if i > 0 else generation_id

                        # Upload to GCS
                        upload_result = await self.gcs_service.upload_image(
                            image_bytes=image_bytes,
                            user_id=user_id,
                            image_id=image_id,
                            original_name=f"ai_generated_{i+1}.jpg",
                            mime_type="image/jpeg",
                            metadata={
                                'generation_id': generation_id,
                                'prompt': normalized_prompt,
                                'model': model,
                                'provider': provider,
                                'image_index': i + 1
                            }
                        )

                        if upload_result:
                            uploaded_images.append({
                                'index': i + 1,
                                'gcs_path': upload_result['gcs_path'],
                                'signed_url': upload_result['signed_url'],
                                'thumbnail_gcs_path': upload_result.get('thumbnail_gcs_path'),
                                'thumbnail_signed_url': upload_result.get('thumbnail_signed_url'),
                                'width': upload_result.get('width', width),
                                'height': upload_result.get('height', height),
                                'file_size': upload_result.get('file_size', 0)
                            })

                            logger.info(f"Uploaded image {i+1} to GCS: {upload_result['gcs_path']}")
                        else:
                            logger.error(f"Failed to upload image {i+1} to GCS")

                    except Exception as e:
                        logger.error(f"Error processing image {i+1}: {str(e)}")
                        continue
            
            if not uploaded_images:
                # Delete the pending record since upload failed
                try:
                    if self.supabase:
                        self.supabase.table('generated_images').delete().eq('id', generation_id).execute()
                        logger.info(f"Deleted failed generation record (upload failed): {generation_id}")
                except Exception as delete_error:
                    logger.error(f"Failed to delete generation record {generation_id}: {str(delete_error)}")

                raise Exception("Failed to upload generated images to storage")

            # Update database record with success
            total_time = (datetime.now() - start_time).total_seconds() * 1000
            await self._update_generation_record(
                generation_id,
                status='completed',
                images_data=uploaded_images,
                generation_time_ms=int(total_time)
            )
            
            logger.info(f"Image generation completed successfully: {generation_id}")
            
            return {
                'generation_id': generation_id,
                'status': 'completed',
                'images': uploaded_images,
                'prompt': normalized_prompt,
                'model': model,
                'provider': provider,
                'generation_time_ms': int(total_time),
                'database_record': db_record
            }
            
        except Exception as e:
            # Delete the pending record since generation failed
            try:
                if self.supabase:
                    self.supabase.table('generated_images').delete().eq('id', generation_id).execute()
                    logger.info(f"Deleted failed generation record: {generation_id}")
            except Exception as delete_error:
                logger.error(f"Failed to delete generation record {generation_id}: {str(delete_error)}")

            logger.error(f"Image generation failed for {generation_id}: {str(e)}")
            raise
    
    async def get_user_generations(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        status_filter: Optional[str] = None,
        include_character_references: bool = False,
        folder_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get user's generated images from database

        Args:
            user_id: User ID
            limit: Maximum number of records to return
            offset: Number of records to skip
            status_filter: Optional status filter ('completed', 'failed', 'pending')
            include_character_references: Whether to include character reference images (default: False)
            folder_id: Optional folder filter (None = all images, "uncategorized" = no folder, UUID = specific folder)

        Returns:
            List of generation records
        """
        if not self.supabase:
            return []

        try:
            query = self.supabase.table('generated_images').select('*').eq('user_id', user_id)

            # By default, exclude character reference images from main gallery
            if not include_character_references:
                query = query.eq('is_character_reference', False)

            if status_filter:
                query = query.eq('status', status_filter)

            # Filter by folder if specified
            if folder_id is not None:
                if folder_id == "uncategorized":
                    query = query.is_('folder_id', 'null')
                else:
                    query = query.eq('folder_id', folder_id)

            query = query.order('created_at', desc=True).range(offset, offset + limit - 1)

            response = query.execute()

            # Return records as-is without automatic URL refresh
            # URLs will be refreshed on-demand when:
            # 1. User actually views/uses an image (frontend handles this)
            # 2. Image load error occurs (frontend error handler refreshes)
            # This prevents N+1 query problem - no longer making individual refresh calls for each image
            return response.data
            
        except Exception as e:
            logger.error(f"Error fetching user generations: {str(e)}")
            return []
    
    def get_available_models(self, provider: str = "replicate") -> List[Dict[str, Any]]:
        """
        Get available models from provider
        
        Args:
            provider: Provider name
            
        Returns:
            List of available models
        """
        if provider not in self.providers:
            return []
        
        if not self.providers[provider].is_available():
            return []
        
        return self.providers[provider].get_available_models()
    
    async def delete_generation(self, user_id: str, generation_id: str) -> bool:
        """
        Delete a generated image and its files
        
        Args:
            user_id: User ID (for authorization)
            generation_id: Generation ID to delete
            
        Returns:
            True if deleted successfully, False otherwise
        """
        if not self.supabase:
            return False
        
        try:
            # Get the record to verify ownership and get file paths
            response = self.supabase.table('generated_images').select('*').eq('id', generation_id).eq('user_id', user_id).single().execute()
            
            if not response.data:
                logger.warning(f"Generation {generation_id} not found for user {user_id}")
                return False
            
            record = response.data
            
            # Delete files from GCS
            deleted_files = []
            if record.get('gcs_path'):
                try:
                    if await self.gcs_service.delete_video(record['gcs_path']):  # Using delete_video as it's generic file delete
                        deleted_files.append(record['gcs_path'])
                except Exception as e:
                    logger.warning(f"Failed to delete main image {record['gcs_path']}: {str(e)}")
            
            if record.get('thumbnail_gcs_path'):
                try:
                    if await self.gcs_service.delete_video(record['thumbnail_gcs_path']):
                        deleted_files.append(record['thumbnail_gcs_path'])
                except Exception as e:
                    logger.warning(f"Failed to delete thumbnail {record['thumbnail_gcs_path']}: {str(e)}")
            
            # Delete database record
            self.supabase.table('generated_images').delete().eq('id', generation_id).eq('user_id', user_id).execute()
            
            logger.info(f"Deleted generation {generation_id} and {len(deleted_files)} files")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting generation {generation_id}: {str(e)}")
            return False
    
    async def _create_generation_record(
        self,
        generation_id: str,
        user_id: str,
        prompt: str,
        model: str,
        provider: str,
        width: int,
        height: int,
        num_outputs: int,
        is_character_reference: bool = False,
        character_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create initial generation record in database"""
        if not self.supabase:
            return {}

        try:
            record_data = {
                'id': generation_id,
                'user_id': user_id,
                'prompt': prompt,
                'model_name': model,
                'provider': provider,
                'status': 'pending',
                'width': width,
                'height': height,
                'num_outputs': num_outputs,
                'is_character_reference': is_character_reference,
                'character_id': character_id,
                'tags': tags if tags else [],
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            response = self.supabase.table('generated_images').insert(record_data).execute()
            
            if response.data:
                return response.data[0]
            
            return record_data
            
        except Exception as e:
            logger.error(f"Error creating generation record: {str(e)}")
            return {}
    
    async def _update_generation_record(
        self,
        generation_id: str,
        status: str,
        images_data: Optional[List[Dict]] = None,
        generation_time_ms: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Update generation record in database"""
        if not self.supabase:
            return False
        
        try:
            # If we have multiple images, create separate records for each
            if images_data and len(images_data) > 1:
                # Update the original record with the first image's data
                first_image = images_data[0]
                update_data = {
                    'status': status,
                    'updated_at': datetime.now().isoformat(),
                    'gcs_path': first_image['gcs_path'],
                    'gcs_signed_url': first_image['signed_url'],
                    'thumbnail_gcs_path': first_image.get('thumbnail_gcs_path'),
                    'thumbnail_signed_url': first_image.get('thumbnail_signed_url'),
                    'width': first_image.get('width'),
                    'height': first_image.get('height'),
                    'file_size': first_image.get('file_size')
                }
                
                if generation_time_ms is not None:
                    update_data['generation_time_ms'] = generation_time_ms
                
                if error_message:
                    update_data['error_message'] = error_message
                
                # Update the original record
                self.supabase.table('generated_images').update(update_data).eq('id', generation_id).execute()
                
                # Get the original record to copy shared data
                original_response = self.supabase.table('generated_images').select('*').eq('id', generation_id).execute()
                if not original_response.data:
                    return False
                
                original_record = original_response.data[0]
                
                # Create new records for additional images (starting from index 1)
                for i, image_data in enumerate(images_data[1:], start=1):
                    new_record_id = f"{generation_id}_{i+1}"
                    
                    new_record = {
                        'id': new_record_id,
                        'user_id': original_record['user_id'],
                        'prompt': f"{original_record['prompt']} (Image {i+1})",
                        'model_name': original_record['model_name'],
                        'provider': original_record['provider'],
                        'status': status,
                        'width': image_data.get('width', original_record['width']),
                        'height': image_data.get('height', original_record['height']),
                        'num_outputs': 1,  # Each record represents one image
                        'gcs_path': image_data['gcs_path'],
                        'gcs_signed_url': image_data['signed_url'],
                        'thumbnail_gcs_path': image_data.get('thumbnail_gcs_path'),
                        'thumbnail_signed_url': image_data.get('thumbnail_signed_url'),
                        'file_size': image_data.get('file_size'),
                        'generation_time_ms': generation_time_ms,
                        'error_message': error_message,
                        'created_at': original_record['created_at'],  # Same creation time
                        'updated_at': datetime.now().isoformat()
                    }
                    
                    try:
                        self.supabase.table('generated_images').insert(new_record).execute()
                        logger.info(f"Created additional record for image {i+1}: {new_record_id}")
                    except Exception as e:
                        logger.error(f"Failed to create record for image {i+1}: {str(e)}")
                        
            else:
                # Single image or no images - use original logic
                update_data = {
                    'status': status,
                    'updated_at': datetime.now().isoformat()
                }
                
                if generation_time_ms is not None:
                    update_data['generation_time_ms'] = generation_time_ms
                
                if error_message:
                    update_data['error_message'] = error_message
                
                if images_data and len(images_data) > 0:
                    # Store the image's data in the record
                    first_image = images_data[0]
                    update_data.update({
                        'gcs_path': first_image['gcs_path'],
                        'gcs_signed_url': first_image['signed_url'],
                        'thumbnail_gcs_path': first_image.get('thumbnail_gcs_path'),
                        'thumbnail_signed_url': first_image.get('thumbnail_signed_url'),
                        'width': first_image.get('width'),
                        'height': first_image.get('height'),
                        'file_size': first_image.get('file_size')
                    })

                # Update with retry logic for JWT expired errors
                try:
                    self.supabase.table('generated_images').update(update_data).eq('id', generation_id).execute()
                except Exception as db_error:
                    error_msg = str(db_error)
                    # Check if it's a JWT expired error
                    if 'JWT expired' in error_msg or 'PGRST301' in error_msg:
                        logger.error(f"❌ JWT expired error when updating generation: {error_msg}")
                        logger.info("🔄 Recreating Supabase client and retrying update...")
                        # Recreate the Supabase client
                        from services.supabase import get_supabase_client
                        self.supabase = get_supabase_client(force_recreate=True)
                        logger.info("✅ Supabase client recreated, retrying update...")
                        # Retry the update
                        self.supabase.table('generated_images').update(update_data).eq('id', generation_id).execute()
                        logger.info("✅ Update successful after client recreation")
                    else:
                        raise

            return True

        except Exception as e:
            logger.error(f"Error updating generation record: {str(e)}")
            return False
    
    async def _download_image(self, image_url: str) -> bytes:
        """Download image from URL with automatic signed URL refresh on expiration"""

        # Helper function to check if URL is likely expired
        def is_url_likely_expired(url: str) -> bool:
            """Check if a GCS signed URL is likely expired by parsing the X-Goog-Date parameter"""
            if 'X-Goog-Date=' not in url or 'X-Goog-Expires=' not in url:
                return False

            try:
                from datetime import datetime, timedelta
                import re

                # Extract X-Goog-Date (format: 20251006T052900Z)
                date_match = re.search(r'X-Goog-Date=(\d{8}T\d{6}Z)', url)
                # Extract X-Goog-Expires (in seconds)
                expires_match = re.search(r'X-Goog-Expires=(\d+)', url)

                if date_match and expires_match:
                    date_str = date_match.group(1)
                    expires_seconds = int(expires_match.group(1))

                    # Parse the date
                    signed_date = datetime.strptime(date_str, '%Y%m%dT%H%M%SZ')
                    expiry_date = signed_date + timedelta(seconds=expires_seconds)

                    # Check if expired (with 5 minute buffer)
                    now = datetime.utcnow()
                    return now >= expiry_date - timedelta(minutes=5)
            except Exception as e:
                logger.debug(f"Could not parse URL expiration: {e}")

            return False

        # Helper function to refresh GCS signed URL
        async def refresh_gcs_url(url: str) -> Optional[str]:
            """Extract GCS path and generate new signed URL"""
            try:
                # Extract GCS path from signed URL
                # Format: https://storage.googleapis.com/bucket-name/path/to/file.jpg?X-Goog-Algorithm=...
                url_parts = url.split('?')[0]  # Remove query parameters
                path_parts = url_parts.split('storage.googleapis.com/')
                if len(path_parts) > 1:
                    # Extract bucket and path
                    bucket_and_path = path_parts[1]
                    parts = bucket_and_path.split('/', 1)
                    if len(parts) == 2:
                        bucket_name = parts[0]
                        gcs_path = parts[1]

                        logger.info(f"Refreshing signed URL for: bucket={bucket_name}, path={gcs_path}")

                        # Generate new signed URL (24 hours expiration)
                        from services.gcs_service import GCSService
                        gcs_service = GCSService()
                        new_signed_url = await gcs_service.generate_signed_url(gcs_path, expiration_hours=24)

                        if new_signed_url:
                            logger.info(f"✅ Successfully generated fresh signed URL")
                            return new_signed_url
            except Exception as e:
                logger.error(f"Error refreshing signed URL: {str(e)}")

            return None

        # Check if URL is likely expired before attempting download
        is_gcs_url = 'storage.googleapis.com' in image_url
        if is_gcs_url and is_url_likely_expired(image_url):
            logger.warning(f"⚠️ Signed URL appears expired based on timestamp, refreshing before download...")
            new_url = await refresh_gcs_url(image_url)
            if new_url:
                image_url = new_url
            else:
                logger.warning(f"Could not refresh URL, will attempt download anyway")

        try:
            response = requests.get(image_url, timeout=30)

            # Check if response contains GCS error XML
            if response.status_code == 400 and b'<Error>' in response.content and b'ExpiredToken' in response.content:
                logger.warning(f"Received ExpiredToken error from GCS, attempting to refresh URL...")
                if is_gcs_url:
                    new_url = await refresh_gcs_url(image_url)
                    if new_url:
                        # Retry with fresh URL
                        response = requests.get(new_url, timeout=30)
                        response.raise_for_status()
                        return response.content

            response.raise_for_status()
            return response.content

        except requests.exceptions.HTTPError as e:
            # Handle other HTTP errors
            if e.response.status_code in [400, 403] and is_gcs_url:
                logger.warning(f"Signed URL failed with HTTP {e.response.status_code}, attempting to refresh...")
                new_url = await refresh_gcs_url(image_url)
                if new_url:
                    # Retry with fresh URL
                    response = requests.get(new_url, timeout=30)
                    response.raise_for_status()
                    return response.content

            # If refresh failed or not a GCS URL, raise original error
            logger.error(f"Error downloading image from {image_url[:100]}: {str(e)}")
            raise Exception(f"Failed to download image: {str(e)}")

        except Exception as e:
            logger.error(f"Error downloading image from {image_url[:100]}: {str(e)}")
            raise Exception(f"Failed to download image: {str(e)}")
    
    def _is_admin_only_model(self, model: str) -> bool:
        """
        Check if a model requires admin privileges

        Args:
            model: Model identifier

        Returns:
            True if model is admin-only, False otherwise
        """
        model_lower = model.lower()

        # Seedream and Imagen models are admin-only
        if 'seedream' in model_lower or 'imagen' in model_lower:
            return True

        return False

    def _is_premium_model(self, model: str) -> bool:
        "check if is premium model"

        model_lower = model.lower()
        return False


    def _should_refresh_url(self, updated_at: Optional[str]) -> bool:
        """Check if signed URL should be refreshed based on age"""
        if not updated_at:
            return True

        try:
            updated_time = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
            age_hours = (datetime.now() - updated_time.replace(tzinfo=None)).total_seconds() / 3600
            return age_hours > 1  # Refresh if older than 1 hour
        except Exception:
            return True
