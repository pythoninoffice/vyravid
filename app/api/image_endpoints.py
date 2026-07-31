"""
Image Generation API Endpoints
Provides REST API for AI image generation functionality
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query, UploadFile, File, Form
from typing import List, Optional
import logging
import uuid
from types import SimpleNamespace
from datetime import datetime, timedelta
from pydantic import BaseModel

from middleware.auth_middleware import get_current_user
from models.auth_models import UserProfile
from models.image_generation_models import (
    ImageGenerationRequest,
    ImageGenerationResponse,
    GeneratedImage,
    ImageModel,
    UserGenerationsResponse,
    ErrorResponse,
    DeleteImageResponse,
    ImageGenerationStatus
)
from services.image_generation_service import ImageGenerationService
from services.gcs_service import GCSService
from services.providers.replicate_provider import ReplicateProvider, SensitiveContentError, is_sensitive_content_error
from services.providers.google_provider import GoogleProvider, GEMINI_OMNI_FLASH_MODEL
from services.background_task_service import get_background_task_service, TaskStatus
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/image-generation", tags=["Image Generation"])

# Initialize services
image_service = ImageGenerationService()
gcs_service = GCSService()
replicate_provider = ReplicateProvider()
google_provider = GoogleProvider()


def _is_google_veo_model(model: str) -> bool:
    return model == "veo-3.1-fast-generate-preview" or model.startswith("veo-")


def _is_google_omni_model(model: str) -> bool:
    return model == GEMINI_OMNI_FLASH_MODEL


def _is_google_video_model(model: str) -> bool:
    return _is_google_veo_model(model) or _is_google_omni_model(model)


def _is_seedance_2_model(model: str) -> bool:
    return (model or "").lower().startswith("bytedance/seedance-2")


def _is_kling_v3_video_model(model: str) -> bool:
    return (model or "").lower() == "kwaivgi/kling-v3-video"


def _supports_end_frame_model(model: str) -> bool:
    return (
        model.startswith("wan-video/")
        or _is_google_veo_model(model)
        or _is_seedance_2_model(model)
        or _is_kling_v3_video_model(model)
    )


def _canonical_video_aspect_ratio(aspect_ratio: Optional[str]) -> Optional[str]:
    if not aspect_ratio:
        return None
    normalized = str(aspect_ratio).strip().lower()
    if normalized in {"16:9", "3:2", "4:3"}:
        return "16:9"
    if normalized in {"9:16", "2:3", "3:4"}:
        return "9:16"
    if normalized == "1:1":
        return "1:1"
    if ":" in normalized:
        try:
            width_text, height_text = normalized.split(":", 1)
            width = float(width_text)
            height = float(height_text)
            if width > 0 and height > 0:
                ratio = width / height
                if ratio > 1.15:
                    return "16:9"
                if ratio < 0.87:
                    return "9:16"
                return "1:1"
        except (TypeError, ValueError):
            return None
    return None


def _aspect_ratio_from_image_record(image_record: dict) -> str:
    stored_aspect_ratio = _canonical_video_aspect_ratio(
        image_record.get("aspect_ratio") or image_record.get("aspectRatio")
    )
    if stored_aspect_ratio:
        return stored_aspect_ratio

    width = image_record.get("width") or 0
    height = image_record.get("height") or 0
    if width and height:
        ratio = width / height
        if ratio > 1.15:
            return "16:9"
        if ratio < 0.87:
            return "9:16"
        return "1:1"
    return "16:9"


def _normalize_video_aspect_ratio(aspect_ratio: Optional[str], image_record: dict) -> str:
    normalized_aspect_ratio = _canonical_video_aspect_ratio(aspect_ratio)
    if normalized_aspect_ratio:
        return normalized_aspect_ratio
    return _aspect_ratio_from_image_record(image_record)


class RefreshUrlRequest(BaseModel):
    current_url: Optional[str] = None


def _is_admin_only_model(model: str) -> bool:
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

@router.post("/generate", response_model=ImageGenerationResponse, responses={
    400: {"model": ErrorResponse, "description": "Invalid request parameters"},
    401: {"model": ErrorResponse, "description": "Authentication required"},
    500: {"model": ErrorResponse, "description": "Internal server error"}
})
async def generate_image(
    request: ImageGenerationRequest,
    current_user: UserProfile = Depends(get_current_user)
) -> ImageGenerationResponse:
    """
    Generate an image from a text prompt.
    
    This endpoint creates AI-generated images using the specified model and parameters.
    - **prompt**: Text description of the desired image
    - **model**: AI model to use for generation (default: Stable Diffusion XL)
    - **width**: Image width in pixels (512-2048, default: 1024)
    - **height**: Image height in pixels (512-2048, default: 1024)
    - **num_outputs**: Number of images to generate (1-4, default: 1)
    """
    try:
        user_id = current_user.id
        logger.info(f"Image generation request from user {user_id}: {request.prompt[:50]}...")
        
        # Check if service is available
        if not image_service.is_available():
            logger.error("Image generation service not available")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Image generation service is currently unavailable. Please try again later."
                }
            )

        # Vyravid local: all models available (no plan/user-type gates)
        user_type = getattr(current_user, 'type', None)

        # Determine provider based on model
        # Google models start with 'gemini-'
        provider = "google" if request.model.startswith("gemini-") else "replicate"

        logger.info(f"Using provider: {provider} for model: {request.model}")

        # Generate image
        result = await image_service.generate_image(
            user_id=user_id,
            prompt=request.prompt,
            provider=provider,
            model=request.model,
            width=request.width,
            height=request.height,
            num_outputs=request.num_outputs,
            aspect_ratio=request.aspect_ratio,
            reference_images=request.reference_images,
            tags=request.tags,
            image_size='2K',
            user_type=getattr(current_user, 'type', None),
            input=request.input  # Pass custom input params for specific models
        )
        
        logger.info(f"Image generation completed for user {user_id}: {result['generation_id']}")
        
        return ImageGenerationResponse(
            id=result['generation_id'],
            prompt=result['prompt'],
            model_name=result['model'],
            status=ImageGenerationStatus.COMPLETED,
            prediction_id=result.get('prediction_id'),
            estimated_time=result.get('generation_time_ms', 0) // 1000,
            created_at=result.get('database_record', {}).get('created_at', '2024-01-01T00:00:00Z')
        )
        
    except HTTPException:
        raise
    except SensitiveContentError as e:
        logger.warning(
            "Sensitive image generation failure for user %s after %s attempts: %s",
            current_user.id,
            getattr(e, "attempts", None),
            str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "content_blocked",
                "code": "CONTENT_BLOCKED",
                "message": "The image prompt or generated output was flagged as sensitive after multiple attempts. Please update the prompt and try again.",
                "details": {
                    "attempts": getattr(e, "attempts", None),
                    "action": "update_prompt"
                }
            }
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error generating image for user {current_user.id}: {error_msg}")

        if is_sensitive_content_error(error_msg):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "content_blocked",
                    "code": "CONTENT_BLOCKED",
                    "message": "The image prompt or generated output was flagged as sensitive after multiple attempts. Please update the prompt and try again.",
                    "details": {
                        "action": "update_prompt"
                    }
                }
            )

        # Generic error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "generation_failed",
                "message": f"Image generation failed: {error_msg}"
            }
        )

@router.get("/generations", responses={
    401: {"model": ErrorResponse, "description": "Authentication required"},
    500: {"model": ErrorResponse, "description": "Internal server error"}
})
async def get_user_generations(
    current_user: UserProfile = Depends(get_current_user),
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum number of results to return"),
    status_filter: Optional[str] = Query(default=None, description="Filter by status (completed, failed, pending)"),
    folder_id: Optional[str] = Query(default=None, description="Filter by folder ID (null for uncategorized, omit for all)")
):
    """
    Get the current user's generated images.
    
    Returns a paginated list of images generated by the authenticated user,
    ordered by creation date (newest first).
    
    - **limit**: Maximum number of results (1-100, default: 20)
    - **offset**: Number of results to skip for pagination (default: 0)
    - **status_filter**: Optional status filter (completed, failed, pending)
    """
    try:
        user_id = current_user.id
        offset = (page - 1) * limit
        logger.info(f"Fetching generations for user {user_id} (page: {page}, limit: {limit}, offset: {offset})")
        
        # Validate status filter
        if status_filter and status_filter not in ['completed', 'failed', 'pending', 'processing']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_status_filter",
                    "message": f"Invalid status filter '{status_filter}'. Valid options: completed, failed, pending, processing"
                }
            )
        
        # Get actual total count
        count_query = image_service.supabase.table('generated_images').select('*', count='exact').eq('user_id', user_id)
        if status_filter:
            count_query = count_query.eq('status', status_filter)
        # Filter by folder if specified
        if folder_id is not None:
            if folder_id == "uncategorized":
                count_query = count_query.is_('folder_id', 'null')
            else:
                count_query = count_query.eq('folder_id', folder_id)
        # Exclude character reference images by default
        count_query = count_query.eq('is_character_reference', False)
        count_response = count_query.execute()
        total_count = count_response.count if hasattr(count_response, 'count') else 0

        # Get user generations
        generations = await image_service.get_user_generations(
            user_id=user_id,
            limit=limit + 1,  # Get one extra to check if there are more
            offset=offset,
            status_filter=status_filter,
            folder_id=folder_id
        )

        # Check if there are more results
        has_more = len(generations) > limit
        if has_more:
            generations = generations[:limit]  # Remove the extra record

        # Convert to response models
        images = []
        for gen in generations:
            images.append(GeneratedImage(
                id=gen['id'],
                prompt=gen['prompt'],
                model_name=gen['model_name'],
                provider=gen.get('provider', 'replicate'),
                status=ImageGenerationStatus(gen['status']),
                signed_url=gen.get('gcs_signed_url') or gen.get('signed_url'),
                thumbnail_signed_url=gen.get('thumbnail_signed_url'),
                width=gen.get('width'),
                height=gen.get('height'),
                file_size=gen.get('file_size'),
                generation_time_ms=gen.get('generation_time_ms'),
                error_message=gen.get('error_message'),
                created_at=gen['created_at'],
                updated_at=gen['updated_at'],
                media_type=gen.get('media_type', 'image'),
                folder_id=gen.get('folder_id')
            ))
        
        logger.info(f"Returning {len(images)} generations for user {user_id}")
        
        return {
            "images": images,
            "total": total_count,
            "page": page,
            "limit": limit,
            "has_more": has_more
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching generations for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "fetch_failed",
                "message": f"Failed to fetch generated images: {str(e)}"
            }
        )

@router.get("/models", response_model=List[ImageModel], responses={
    500: {"model": ErrorResponse, "description": "Internal server error"}
})
async def get_available_models() -> List[ImageModel]:
    """
    Get available image generation models.
    
    Returns a list of AI models available for image generation,
    including their capabilities.
    """
    try:
        logger.info("Fetching available image generation models")
        
        models = image_service.get_available_models(provider="replicate")
        
        # Convert to response models
        model_list = []
        for model in models:
            model_list.append(ImageModel(
                id=model['id'],
                name=model['name'],
                description=model['description'],
                max_width=model.get('max_width', 2048),
                max_height=model.get('max_height', 2048),
                supports_batch=model.get('supports_batch', True)
            ))
        
        logger.info(f"Returning {len(model_list)} available models")
        return model_list
        
    except Exception as e:
        logger.error(f"Error fetching available models: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "models_fetch_failed",
                "message": f"Failed to fetch available models: {str(e)}"
            }
        )

@router.delete("/generations/{generation_id}", response_model=DeleteImageResponse, responses={
    401: {"model": ErrorResponse, "description": "Authentication required"},
    404: {"model": ErrorResponse, "description": "Image not found"},
    500: {"model": ErrorResponse, "description": "Internal server error"}
})
async def delete_generated_image(
    generation_id: str,
    current_user: UserProfile = Depends(get_current_user)
) -> DeleteImageResponse:
    """
    Delete a generated image.
    
    Removes the generated image and its associated files from storage.
    Only the user who generated the image can delete it.
    
    - **generation_id**: ID of the generated image to delete
    """
    try:
        user_id = current_user.id
        logger.info(f"Deleting image {generation_id} for user {user_id}")
        
        # Delete the image
        success = await image_service.delete_generation(
            user_id=user_id,
            generation_id=generation_id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "image_not_found",
                    "message": "Generated image not found or you don't have permission to delete it"
                }
            )
        
        logger.info(f"Successfully deleted image {generation_id} for user {user_id}")
        
        return DeleteImageResponse(
            success=True,
            message="Image deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting image {generation_id} for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "deletion_failed",
                "message": f"Failed to delete image: {str(e)}"
            }
        )

@router.post("/refresh-urls/{generation_id}", responses={
    401: {"model": ErrorResponse, "description": "Authentication required"},
    404: {"model": ErrorResponse, "description": "Image not found"},
    500: {"model": ErrorResponse, "description": "Internal server error"}
})
async def refresh_image_urls(
    generation_id: str,
    request: Optional[RefreshUrlRequest] = None,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Refresh signed URLs for a generated image.
    
    Returns fresh signed URLs for the image and thumbnail that are valid for 24 hours.
    This is useful when URLs have expired or are about to expire.
    
    - **generation_id**: ID of the generated image
    """
    try:
        user_id = current_user.id
        logger.info(f"Refreshing URLs for generation {generation_id} for user {user_id}")

        async def refresh_from_current_url(current_url: Optional[str]):
            if not current_url or 'storage.googleapis.com' not in current_url:
                return None

            try:
                url_parts = current_url.split('?', 1)[0]
                path_parts = url_parts.split('storage.googleapis.com/', 1)
                if len(path_parts) != 2:
                    return None
                bucket_and_path = path_parts[1]
                parts = bucket_and_path.split('/', 1)
                if len(parts) != 2 or not parts[1]:
                    return None
                gcs_path = parts[1]
                new_signed_url = await image_service.gcs_service.generate_signed_url(
                    gcs_path,
                    expiration_hours=24
                )
                if new_signed_url:
                    expires_at = (datetime.utcnow() + timedelta(hours=24)).isoformat() + "Z"
                    logger.info(f"✅ Refreshed URL directly from current_url for asset {generation_id}")
                    return {
                        "signed_url": new_signed_url,
                        "expires_at": expires_at,
                    }
            except Exception as url_error:
                logger.warning(f"Failed URL-based refresh fallback for {generation_id}: {str(url_error)}")

            return None
        
        # Get the specific generation from database
        if not image_service.supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "service_unavailable",
                    "message": "Database service not available"
                }
            )
        
        # Query with retry logic for JWT expired errors
        try:
            response = image_service.supabase.table('generated_images').select('*').eq('id', generation_id).eq('user_id', user_id).single().execute()
        except Exception as db_error:
            error_msg = str(db_error)
            # Check if it's a "no rows found" error (PGRST116)
            if 'PGRST116' in error_msg or 'multiple (or no) rows returned' in error_msg:
                fallback_urls = await refresh_from_current_url(request.current_url if request else None)
                if fallback_urls:
                    logger.info(
                        f"Generation {generation_id} not found in generated_images; used current_url fallback"
                    )
                    return fallback_urls
                logger.warning(f"Image generation {generation_id} not found for user {user_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "image_not_found",
                        "message": "Generated image not found or you don't have permission to access it"
                    }
                )
            # Check if it's a JWT expired error
            elif 'JWT expired' in error_msg or 'PGRST301' in error_msg:
                logger.error(f"❌ JWT expired error detected: {error_msg}")
                logger.info("🔄 Recreating Supabase client with fresh connection...")
                # Recreate the Supabase client to get a fresh connection
                from services.supabase import get_supabase_client
                image_service.supabase = get_supabase_client(force_recreate=True)
                logger.info("✅ Supabase client recreated, retrying query...")
                # Retry the query
                response = image_service.supabase.table('generated_images').select('*').eq('id', generation_id).eq('user_id', user_id).single().execute()
                logger.info("✅ Retry successful after client recreation")
            else:
                raise

        if not response.data:
            fallback_urls = await refresh_from_current_url(request.current_url if request else None)
            if fallback_urls:
                logger.info(
                    f"Generation {generation_id} returned no database row; used current_url fallback"
                )
                return fallback_urls
            logger.warning(f"Image generation {generation_id} returned no data for user {user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "image_not_found",
                    "message": "Generated image not found or you don't have permission to access it"
                }
            )
        
        generation = response.data
        
        # Generate fresh signed URLs
        fresh_urls = {}
        
        if generation.get('gcs_path'):
            try:
                new_signed_url = await image_service.gcs_service.generate_signed_url(
                    generation['gcs_path'], expiration_hours=24
                )
                if new_signed_url:
                    fresh_urls['signed_url'] = new_signed_url
            except Exception as e:
                logger.warning(f"Failed to refresh main image URL for {generation_id}: {str(e)}")
        
        if generation.get('thumbnail_gcs_path'):
            try:
                new_thumbnail_url = await image_service.gcs_service.generate_signed_url(
                    generation['thumbnail_gcs_path'], expiration_hours=24
                )
                if new_thumbnail_url:
                    fresh_urls['thumbnail_signed_url'] = new_thumbnail_url
            except Exception as e:
                logger.warning(f"Failed to refresh thumbnail URL for {generation_id}: {str(e)}")
        
        if not fresh_urls:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "no_files_found",
                    "message": "No image files found for this generation"
                }
            )
        
        # Add expiration info
        expires_at = (datetime.utcnow() + timedelta(hours=24)).isoformat() + "Z"
        fresh_urls['expires_at'] = expires_at

        # Update the database with fresh signed URLs so future fetches get them
        try:
            update_data = {}
            if 'signed_url' in fresh_urls:
                update_data['gcs_signed_url'] = fresh_urls['signed_url']
            if 'thumbnail_signed_url' in fresh_urls:
                update_data['thumbnail_signed_url'] = fresh_urls['thumbnail_signed_url']

            if update_data:
                image_service.supabase.table('generated_images')\
                    .update(update_data)\
                    .eq('id', generation_id)\
                    .eq('user_id', user_id)\
                    .execute()
                logger.info(f"✅ Updated database with fresh signed URLs for generation {generation_id}")
        except Exception as db_error:
            # Log but don't fail the request if database update fails
            logger.warning(f"⚠️ Failed to update database with fresh URLs for {generation_id}: {str(db_error)}")

        logger.info(f"Successfully refreshed URLs for generation {generation_id}")

        return fresh_urls
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing URLs for generation {generation_id} for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "refresh_failed",
                "message": f"Failed to refresh image URLs: {str(e)}"
            }
        )

@router.get("/generations/{generation_id}", response_model=GeneratedImage, responses={
    401: {"model": ErrorResponse, "description": "Authentication required"},
    404: {"model": ErrorResponse, "description": "Image not found"},
    500: {"model": ErrorResponse, "description": "Internal server error"}
})
async def get_generation_details(
    generation_id: str,
    current_user: UserProfile = Depends(get_current_user)
) -> GeneratedImage:
    """
    Get details of a specific generated image.
    
    Returns detailed information about a generated image,
    including current status and download URLs.
    
    - **generation_id**: ID of the generated image
    """
    try:
        user_id = current_user.id
        logger.info(f"Fetching generation details {generation_id} for user {user_id}")
        
        # Get user generations with no limit to find the specific one
        generations = await image_service.get_user_generations(
            user_id=user_id,
            limit=1000,  # Large limit to search through user's generations
            offset=0
        )
        
        # Find the specific generation
        generation = None
        for gen in generations:
            if gen['id'] == generation_id:
                generation = gen
                break
        
        if not generation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "image_not_found",
                    "message": "Generated image not found or you don't have permission to access it"
                }
            )
        
        logger.info(f"Found generation {generation_id} for user {user_id}")
        
        return GeneratedImage(
            id=generation['id'],
            prompt=generation['prompt'],
            model_name=generation['model_name'],
            provider=generation.get('provider', 'replicate'),
            status=ImageGenerationStatus(generation['status']),
            signed_url=generation.get('gcs_signed_url') or generation.get('signed_url'),
            thumbnail_signed_url=generation.get('thumbnail_signed_url'),
            width=generation.get('width'),
            height=generation.get('height'),
            file_size=generation.get('file_size'),
            generation_time_ms=generation.get('generation_time_ms'),
            error_message=generation.get('error_message'),
            created_at=generation['created_at'],
            updated_at=generation['updated_at'],
            media_type=generation.get('media_type', 'image')  # Add media_type field
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching generation {generation_id} for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "fetch_failed",
                "message": f"Failed to fetch generation details: {str(e)}"
            }
        )

@router.post("/upload", responses={
    400: {"model": ErrorResponse, "description": "Invalid file or request parameters"},
    401: {"model": ErrorResponse, "description": "Authentication required"},
    413: {"model": ErrorResponse, "description": "File too large"},
    500: {"model": ErrorResponse, "description": "Internal server error"}
})
async def upload_images(
    files: List[UploadFile] = File(...),
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Upload user images or videos to storage.

    Allows users to upload their own images or videos for use in video generation.
    Media files are validated, optimized, and stored in Google Cloud Storage.

    - **files**: Image or video files to upload (JPEG, PNG, WebP, MP4)
    - Maximum file size: 10MB per file
    - Maximum files per request: 10
    """
    try:
        user_id = current_user.id
        logger.info(f"Image upload request from user {user_id}: {len(files)} files")
        
        # Validate file count
        if not files or len(files) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "no_files",
                    "message": "No files provided for upload"
                }
            )
        
        if len(files) > 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "too_many_files",
                    "message": "Maximum 10 files per upload"
                }
            )
        
        # Check if services are available
        if not gcs_service.is_available():
            logger.error("GCS service not available")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Upload service is currently unavailable. Please try again later."
                }
            )
        
        uploaded_images = []
        
        for i, file in enumerate(files):
            try:
                # Validate file type
                if not file.content_type or not (file.content_type.startswith('image/') or file.content_type == 'video/mp4'):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "invalid_file_type",
                            "message": f"File {i+1} ({file.filename}): Must be an image file or MP4 video"
                        }
                    )
                
                # Check supported formats
                supported_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'video/mp4']
                if file.content_type not in supported_types:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "unsupported_format",
                            "message": f"File {i+1} ({file.filename}): Unsupported format. Supported: JPEG, PNG, WebP, MP4"
                        }
                    )
                
                # Read file content
                file_content = await file.read()
                file_size = len(file_content)
                
                # Validate file size (50MB limit)
                max_size = 50 * 1024 * 1024
                if file_size > max_size:
                    size_mb = file_size / (1024 * 1024)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail={
                            "error": "file_too_large",
                            "message": f"File {i+1} ({file.filename}): Too large ({size_mb:.1f}MB). Maximum: 50MB"
                        }
                    )
                
                if file_size == 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "empty_file",
                            "message": f"File {i+1} ({file.filename}): File is empty"
                        }
                    )
                
                # Generate UUID for image
                image_id = str(uuid.uuid4())

                # Upload to GCS using existing service
                upload_result = await gcs_service.upload_image(
                    image_bytes=file_content,
                    user_id=user_id,
                    image_id=image_id,
                    original_name=file.filename or f"upload_{i+1}.jpg",
                    mime_type=file.content_type,
                    metadata={
                        'upload_source': 'user_upload',
                        'upload_type': 'manual'
                    }
                )
                
                if not upload_result:
                    logger.error(f"Failed to upload image {i+1} to GCS")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail={
                            "error": "upload_failed",
                            "message": f"Failed to upload file {i+1} ({file.filename})"
                        }
                    )
                
                # Create database record in generated_images table
                if file.content_type.startswith('image/'):
                    media_type = "image"
                elif file.content_type == 'video/mp4':
                    media_type = "video"
                record_data = {
                    'user_id': user_id,
                    'prompt': f"User uploaded: {file.filename}",  # Use filename as prompt
                    'model_name': 'user_upload',
                    'provider': 'user_upload',
                    'status': 'completed',
                    'gcs_path': upload_result.get('gcs_path'),
                    'gcs_signed_url': upload_result.get('signed_url'),
                    'thumbnail_gcs_path': upload_result.get('thumbnail_gcs_path'),
                    'thumbnail_signed_url': upload_result.get('thumbnail_signed_url'),
                    'width': upload_result.get('width'),
                    'height': upload_result.get('height'),
                    'file_size': file_size,
                    'num_outputs': 1,
                    'generation_time_ms': 0,
                    'media_type': media_type
                }
                
                if image_service.supabase:
                    db_response = image_service.supabase.table('generated_images').insert(record_data).execute()
                    if db_response.data:
                        # Use the complete database record which includes the generated ID and all fields
                        db_record = db_response.data[0]
                        logger.info(f"Created database record for uploaded image: {db_record['id']}")

                        # Append the complete database record to match GeneratedImage interface
                        uploaded_images.append({
                            'id': db_record['id'],
                            'prompt': db_record['prompt'],
                            'model_name': db_record['model_name'],
                            'provider': db_record['provider'],
                            'status': db_record['status'],
                            'gcs_path': db_record.get('gcs_path'),
                            'bucket_name': gcs_service.settings.gcs_bucket_name if gcs_service.is_available() else None,
                            'signed_url': db_record.get('gcs_signed_url'),
                            'thumbnail_signed_url': db_record.get('thumbnail_signed_url'),
                            'width': db_record.get('width'),
                            'height': db_record.get('height'),
                            'file_size': db_record.get('file_size'),
                            'mime_type': file.content_type,
                            'generation_time_ms': db_record.get('generation_time_ms'),
                            'created_at': db_record['created_at'],
                            'updated_at': db_record['updated_at'],
                            'media_type': db_record.get('media_type', 'image')
                        })
                    else:
                        logger.error(f"Failed to get database record for uploaded image {i+1}")
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail={
                                "error": "upload_failed",
                                "message": f"Failed to save database record for file {i+1}"
                            }
                        )
                else:
                    logger.error("Supabase client not available")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail={
                            "error": "service_unavailable",
                            "message": "Database service not available"
                        }
                    )
                
                logger.info(f"Successfully uploaded image {i+1}: {file.filename}")
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error uploading file {i+1} ({file.filename}): {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "error": "upload_failed",
                        "message": f"Failed to upload file {i+1} ({file.filename}): {str(e)}"
                    }
                )
        
        logger.info(f"Successfully uploaded {len(uploaded_images)} images for user {user_id}")
        
        return {
            "success": True,
            "message": f"Successfully uploaded {len(uploaded_images)} image(s)",
            "images": uploaded_images,
            "total_uploaded": len(uploaded_images)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading images for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "upload_failed",
                "message": f"Image upload failed: {str(e)}"
            }
        )

@router.post("/animate", responses={
    400: {"model": ErrorResponse, "description": "Invalid request parameters"},
    401: {"model": ErrorResponse, "description": "Authentication required"},
    404: {"model": ErrorResponse, "description": "Image not found"},
    500: {"model": ErrorResponse, "description": "Internal server error"}
})
async def animate_image(
    image_id: str = Form(...),
    animation_prompt: str = Form(...),
    model: str = Form("wan-video/wan-2.2-i2v-fast"),
    resolution: str = Form("480p"),
    end_frame_image_id: Optional[str] = Form(None),
    audio_url: Optional[str] = Form(None),
    duration: Optional[int] = Form(None),
    aspect_ratio: Optional[str] = Form(None),
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Animate an image into a video using AI.

    Takes a generated image and converts it into an animated video using the
    selected video model.

    - **image_id**: ID of the image to animate
    - **animation_prompt**: Text description of desired animation
    - **model**: Video generation model (default: wan-video/wan-2.2-i2v-fast)
    - **resolution**: Video resolution (default: 480p, options: 480p, 720p, 1080p)
    - **end_frame_image_id**: Optional ID of the end frame image (WAN, Veo, Seedance 2)
    - **audio_url**: Optional audio file URL (required for kling-avatar-v2)
    """
    try:
        user_id = current_user.id
        logger.info(f"Video animation request from user {user_id} for image {image_id}")

        # Validate prompt
        if not animation_prompt or len(animation_prompt.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_prompt",
                    "message": "Animation prompt cannot be empty"
                }
            )

        is_google_video_model = _is_google_video_model(model)

        # Check if the selected provider is available
        if is_google_video_model:
            if not google_provider.is_available():
                logger.error("Google video provider not available")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": "service_unavailable",
                        "message": "Google video generation service is currently unavailable"
                    }
                )
        elif not replicate_provider.is_available():
            logger.error("Replicate provider not available")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Video animation service is currently unavailable"
                }
            )

        # Get the source image from database
        if not image_service.supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "service_unavailable",
                    "message": "Database service not available"
                }
            )

        response = image_service.supabase.table('generated_images').select('*').eq('id', image_id).eq('user_id', user_id).single().execute()

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "image_not_found",
                    "message": "Image not found or you don't have permission to access it"
                }
            )

        source_image = response.data

        # Refresh the image URL to ensure it's not expired
        gcs_path = source_image.get('gcs_path')
        if not gcs_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "no_gcs_path",
                    "message": "Source image does not have a GCS path"
                }
            )

        # Generate a fresh signed URL
        logger.info(f"Refreshing signed URL for image: {gcs_path}")
        image_url = await gcs_service.generate_signed_url(gcs_path, expiration_hours=24)

        if not image_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "url_generation_failed",
                    "message": "Failed to generate signed URL for source image"
                }
            )

        logger.info(f"Using fresh signed URL for animation")

        # Fetch end frame URL if provided and supported by selected model
        end_frame_url = None
        if end_frame_image_id and _supports_end_frame_model(model):
            end_frame_response = image_service.supabase.table('generated_images') \
                .select('*').eq('id', end_frame_image_id).eq('user_id', user_id).single().execute()
            if end_frame_response.data and end_frame_response.data.get('gcs_path'):
                end_frame_url = await gcs_service.generate_signed_url(
                    end_frame_response.data['gcs_path'], expiration_hours=24
                )
                logger.info(f"Using end frame image: {end_frame_image_id}")

        logger.info(f"Starting video animation with model '{model}', resolution '{resolution}' and prompt: {animation_prompt[:100]}")
        source_aspect_ratio = _normalize_video_aspect_ratio(aspect_ratio, source_image)
        logger.info(f"Using source image aspect ratio for video animation: {source_aspect_ratio}")

        # Generate video using the selected provider
        extra_kwargs = {}
        if duration is not None:
            extra_kwargs['duration'] = duration
        if is_google_video_model:
            video_result = await google_provider.animate_image(
                image_url=image_url,
                prompt=animation_prompt,
                model=model,
                resolution=resolution,
                aspect_ratio=source_aspect_ratio,
                last_image=end_frame_url,
                **extra_kwargs
            )
            provider_name = "google"
            video_bytes = video_result.get("video_bytes")
            if not video_bytes:
                raise Exception("Google video generation failed or no video bytes returned")
            logger.info("Google video generated successfully")
        else:
            video_result = await replicate_provider.animate_image(
                image_url=image_url,
                prompt=animation_prompt,
                model=model,
                resolution=resolution,
                aspect_ratio=source_aspect_ratio,
                last_image=end_frame_url,
                audio_url=audio_url,
                **extra_kwargs
            )
            provider_name = "replicate"

            if video_result['status'] != 'completed' or not video_result.get('video_url'):
                raise Exception("Video generation failed or no video URL returned")

            video_url = video_result['video_url']
            logger.info(f"Video generated successfully: {video_url}")

            # Download video from Replicate
            async with httpx.AsyncClient(timeout=300.0) as client:
                video_response = await client.get(video_url)
                video_response.raise_for_status()
                video_bytes = video_response.content

        logger.info(f"Downloaded video: {len(video_bytes)} bytes")

        # Generate video ID
        video_id = str(uuid.uuid4())

        # Upload video to GCS
        gcs_result = await gcs_service.upload_video_bytes(
            video_bytes=video_bytes,
            user_id=user_id,
            video_id=video_id,
            file_extension="mp4",
            metadata={
                'source_image_id': image_id,
                'animation_prompt': animation_prompt,
                'model': model,
                'generation_type': 'image_to_video'
            }
        )

        if not gcs_result:
            raise Exception("Failed to upload video to GCS")

        logger.info(f"Video uploaded to GCS: {gcs_result['gcs_path']}")

        # Create database record
        video_record = {
            'user_id': user_id,
            'prompt': animation_prompt,
            'model_name': model,
            'provider': provider_name,
            'status': 'completed',
            'gcs_path': gcs_result['gcs_path'],
            'gcs_signed_url': gcs_result['signed_url'],
            'file_size': len(video_bytes),
            'generation_time_ms': video_result.get('generation_time_ms', 0),
            'media_type': 'video',
            'source_image_id': image_id,
            'animation_prompt': animation_prompt,
            'video_duration': video_result.get('duration', 5.0),
            'model_used': model
        }

        db_response = image_service.supabase.table('generated_images').insert(video_record).execute()

        if not db_response.data:
            raise Exception("Failed to create database record")

        video_id = db_response.data[0]['id']
        logger.info(f"Created video record in database: {video_id}")

        logger.info(f"Video animation completed for user {user_id}: {video_id}")

        return {
            "success": True,
            "video_id": video_id,
            "signed_url": gcs_result['signed_url'],
            "duration": video_result.get('duration', 5.0),
            "generation_time_ms": video_result.get('generation_time_ms', 0),
            "source_image_id": image_id,
            "animation_prompt": animation_prompt
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error animating image {image_id} for user {current_user.id}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "animation_failed",
                "message": f"Video animation failed: {str(e)}"
            }
        )


@router.post("/video/text", responses={
    400: {"model": ErrorResponse, "description": "Invalid request parameters"},
    401: {"model": ErrorResponse, "description": "Authentication required"},
    500: {"model": ErrorResponse, "description": "Internal server error"}
})
async def generate_text_video(
    prompt: str = Form(...),
    model: str = Form(GEMINI_OMNI_FLASH_MODEL),
    resolution: str = Form("720p"),
    duration: Optional[int] = Form(None),
    aspect_ratio: Optional[str] = Form("16:9"),
    current_user: UserProfile = Depends(get_current_user)
):
    """Generate a video directly from a text prompt with Gemini Omni Flash."""
    try:
        user_id = current_user.id
        if not prompt or len(prompt.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_prompt",
                    "message": "Video prompt cannot be empty"
                }
            )

        if not _is_google_omni_model(model):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "unsupported_text_to_video_model",
                    "message": "Text-to-video is currently supported by Gemini Omni Flash only."
                }
            )

        if not google_provider.is_available():
            logger.error("Google video provider not available")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Google video generation service is currently unavailable"
                }
            )

        if not image_service.supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "service_unavailable",
                    "message": "Database service not available"
                }
            )

        source_aspect_ratio = _canonical_video_aspect_ratio(aspect_ratio) or "16:9"
        logger.info(
            "Starting text-to-video generation with model '%s', aspect_ratio '%s' and prompt: %s",
            model,
            source_aspect_ratio,
            prompt[:100],
        )

        video_result = await google_provider.generate_omni_video(
            prompt=prompt,
            model=model,
            aspect_ratio=source_aspect_ratio,
            task="text_to_video",
        )
        video_bytes = video_result.get("video_bytes")
        if not video_bytes:
            raise Exception("Text-to-video generation failed or no video bytes returned")

        video_id = str(uuid.uuid4())
        gcs_result = await gcs_service.upload_video_bytes(
            video_bytes=video_bytes,
            user_id=user_id,
            video_id=video_id,
            file_extension="mp4",
            metadata={
                'prompt': prompt,
                'model': model,
                'generation_type': 'text_to_video'
            }
        )

        if not gcs_result:
            raise Exception("Failed to upload video to GCS")

        video_record = {
            'user_id': user_id,
            'prompt': prompt,
            'model_name': model,
            'provider': "google",
            'status': 'completed',
            'gcs_path': gcs_result['gcs_path'],
            'gcs_signed_url': gcs_result['signed_url'],
            'file_size': len(video_bytes),
            'generation_time_ms': video_result.get('generation_time_ms', 0),
            'media_type': 'video',
            'source_image_id': None,
            'animation_prompt': prompt,
            'video_duration': video_result.get('duration') or (duration or 8),
            'model_used': model
        }

        db_response = image_service.supabase.table('generated_images').insert(video_record).execute()
        if not db_response.data:
            raise Exception("Failed to create database record")

        generated_video_id = db_response.data[0]['id']

        logger.info(f"Text-to-video generation completed for user {user_id}: {generated_video_id}")
        return {
            "success": True,
            "video_id": generated_video_id,
            "signed_url": gcs_result['signed_url'],
            "duration": video_record['video_duration'],
            "generation_time_ms": video_result.get('generation_time_ms', 0),
            "source_image_id": None,
            "animation_prompt": prompt
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating text video for user {current_user.id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "text_to_video_failed",
                "message": f"Text-to-video generation failed: {str(e)}"
            }
        )


@router.post("/video/text/start")
async def start_generate_text_video(
    prompt: str = Form(...),
    model: str = Form(GEMINI_OMNI_FLASH_MODEL),
    resolution: str = Form("720p"),
    duration: Optional[int] = Form(None),
    aspect_ratio: Optional[str] = Form("16:9"),
    current_user: UserProfile = Depends(get_current_user)
):
    """Start text-to-video generation in the background."""
    try:
        if not prompt or len(prompt.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_prompt",
                    "message": "Video prompt cannot be empty"
                }
            )

        user_id = current_user.id
        task_service = get_background_task_service()
        task_id = task_service.create_task(
            task_type="text_to_video",
            user_id=user_id,
            metadata={
                "model": model,
                "resolution": resolution,
                "duration": duration,
                "aspect_ratio": aspect_ratio,
            }
        )

        task_service.start_background_task(
            task_id,
            generate_text_video,
            prompt=prompt,
            model=model,
            resolution=resolution,
            duration=duration,
            aspect_ratio=aspect_ratio,
            current_user=SimpleNamespace(id=user_id),
        )

        logger.info("Started async text-to-video task %s for user %s", task_id, user_id)
        return {
            "task_id": task_id,
            "status": TaskStatus.PENDING.value,
            "message": "Text-to-video generation started. Poll /api/image-generation/animate/status/{task_id} for progress."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start async text-to-video task: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "text_to_video_start_failed",
                "message": "Failed to start text-to-video generation. Please try again."
            }
        )


@router.post("/animate/start")
async def start_animate_image(
    image_id: str = Form(...),
    animation_prompt: str = Form(...),
    model: str = Form("wan-video/wan-2.2-i2v-fast"),
    resolution: str = Form("480p"),
    end_frame_image_id: Optional[str] = Form(None),
    audio_url: Optional[str] = Form(None),
    duration: Optional[int] = Form(None),
    aspect_ratio: Optional[str] = Form(None),
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Start image-to-video generation in the background.

    This is used by slower providers/models (for example Seedance 2) so the
    client can poll instead of holding an HTTP request open long enough to hit
    proxy 524 timeouts.
    """
    try:
        if not animation_prompt or len(animation_prompt.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_prompt",
                    "message": "Animation prompt cannot be empty"
                }
            )

        user_id = current_user.id
        task_service = get_background_task_service()
        task_id = task_service.create_task(
            task_type="image_animation",
            user_id=user_id,
            metadata={
                "image_id": image_id,
                "model": model,
                "resolution": resolution,
                "end_frame_image_id": end_frame_image_id,
                "duration": duration,
                "aspect_ratio": aspect_ratio,
            }
        )

        task_service.start_background_task(
            task_id,
            animate_image,
            image_id=image_id,
            animation_prompt=animation_prompt,
            model=model,
            resolution=resolution,
            end_frame_image_id=end_frame_image_id,
            audio_url=audio_url,
            duration=duration,
            aspect_ratio=aspect_ratio,
            current_user=SimpleNamespace(id=user_id),
        )

        logger.info("Started async image animation task %s for user %s", task_id, user_id)

        return {
            "task_id": task_id,
            "status": TaskStatus.PENDING.value,
            "message": "Video animation started. Poll /api/image-generation/animate/status/{task_id} for progress."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start async image animation task: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "animation_start_failed",
                "message": "Failed to start video animation. Please try again."
            }
        )


@router.get("/animate/status/{task_id}")
async def get_animate_image_status(
    task_id: str,
    current_user: UserProfile = Depends(get_current_user)
):
    """Get status/result for an async image-to-video generation task."""
    task_service = get_background_task_service()
    task_data = task_service.get_task(task_id)

    if not task_data:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    user_id = current_user.id
    if task_data.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="You don't have permission to access this task")

    return {
        "task_id": task_data["task_id"],
        "task_type": task_data["task_type"],
        "status": task_data["status"],
        "progress": task_data["progress"],
        "message": task_data["message"],
        "result": task_data.get("result"),
        "error": task_data.get("error"),
        "created_at": task_data["created_at"],
        "updated_at": task_data["updated_at"],
    }
