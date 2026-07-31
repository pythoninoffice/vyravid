"""
Character Design API Endpoints
Provides REST API for character management functionality
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional
import logging

from middleware.auth_middleware import get_current_user
from models.auth_models import UserProfile
from models.character_models import (
    CharacterDesign,
    CharacterDesignCreate,
    CharacterDesignUpdate,
    CharacterDesignDetailed,
    CharacterListResponse,
    CharacterCollection,
    CharacterCollectionCreate,
    CharacterCollectionUpdate,
    CollectionListResponse,
    CharacterReferenceImage,
    CharacterReferenceImageCreate,
    CharacterReferenceImageUpdate,
    ReorderReferenceImagesRequest,
    DeleteCharacterResponse,
    SetPrimaryImageResponse,
    GenerateScenePromptRequest,
    GenerateScenePromptResponse,
    CharacterErrorResponse
)
from services.character_service import CharacterService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/characters", tags=["Character Design"])

# Security scheme for Bearer token
security = HTTPBearer()

# Initialize service
character_service = CharacterService()

# =============================================
# Character CRUD Endpoints
# =============================================

@router.post("", response_model=CharacterDesign, status_code=status.HTTP_201_CREATED, responses={
    400: {"model": CharacterErrorResponse, "description": "Invalid request parameters"},
    401: {"model": CharacterErrorResponse, "description": "Authentication required"},
    500: {"model": CharacterErrorResponse, "description": "Internal server error"}
})
async def create_character(
    request: CharacterDesignCreate,
    current_user: UserProfile = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> CharacterDesign:
    """
    Create a new character design.

    Characters help maintain consistency across video scenes by storing
    reference images and text descriptions.

    - **name**: Character name (required)
    - **description**: Text description/prompt for the character
    - **tags**: Tags like novel/game/anime names
    - **visual_style_notes**: Additional visual style notes
    - **collection_id**: Optional collection/folder ID
    """
    try:
        user_id = current_user.id
        logger.info(f"Creating character for user {user_id}: {request.name}")

        if not character_service.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Character service is currently unavailable"
                }
            )

        character = await character_service.create_character(
            access_token=credentials.credentials,
            user_id=user_id,
            name=request.name,
            description=request.description,
            tags=request.tags,
            visual_style_notes=request.visual_style_notes,
            collection_id=str(request.collection_id) if request.collection_id else None
        )

        return CharacterDesign(**character)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "validation_error",
                "message": str(e)
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating character: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "creation_failed",
                "message": f"Failed to create character: {str(e)}"
            }
        )

@router.get("", response_model=CharacterListResponse, responses={
    401: {"model": CharacterErrorResponse, "description": "Authentication required"},
    500: {"model": CharacterErrorResponse, "description": "Internal server error"}
})
async def list_characters(
    current_user: UserProfile = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    collection_id: Optional[str] = Query(default=None, description="Filter by collection ID"),
    search: Optional[str] = Query(default=None, description="Search in name and description"),
    tags: Optional[str] = Query(default=None, description="Comma-separated tags to filter by")
) -> CharacterListResponse:
    """
    Get the current user's characters with pagination and filters.

    Returns a paginated list of characters created by the authenticated user.

    - **page**: Page number (1-based)
    - **limit**: Items per page (1-100)
    - **collection_id**: Filter by collection
    - **search**: Search in character names and descriptions
    - **tags**: Filter by tags (comma-separated)
    """
    try:
        user_id = current_user.id

        if not character_service.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Character service is currently unavailable"
                }
            )

        # Parse tags if provided
        tag_list = [t.strip() for t in tags.split(',')] if tags else None

        result = await character_service.list_characters(
            access_token=credentials.credentials,
            user_id=user_id,
            page=page,
            limit=limit,
            collection_id=collection_id,
            search=search,
            tags=tag_list
        )

        return CharacterListResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing characters: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "fetch_failed",
                "message": f"Failed to fetch characters: {str(e)}"
            }
        )

@router.get("/{character_id}", response_model=CharacterDesignDetailed, responses={
    401: {"model": CharacterErrorResponse, "description": "Authentication required"},
    404: {"model": CharacterErrorResponse, "description": "Character not found"},
    500: {"model": CharacterErrorResponse, "description": "Internal server error"}
})
async def get_character(
    character_id: str,
    current_user: UserProfile = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> CharacterDesignDetailed:
    """
    Get detailed information about a specific character.

    Returns the character with all reference images and metadata.

    - **character_id**: UUID of the character
    """
    try:
        user_id = current_user.id

        if not character_service.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Character service is currently unavailable"
                }
            )

        character = await character_service.get_character(
            access_token=credentials.credentials,
            user_id=user_id,
            character_id=character_id,
            include_references=True
        )

        if not character:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "not_found",
                    "message": "Character not found or access denied"
                }
            )

        return CharacterDesignDetailed(**character)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting character {character_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "fetch_failed",
                "message": f"Failed to fetch character: {str(e)}"
            }
        )

@router.put("/{character_id}", response_model=CharacterDesignDetailed, responses={
    400: {"model": CharacterErrorResponse, "description": "Invalid request parameters"},
    401: {"model": CharacterErrorResponse, "description": "Authentication required"},
    404: {"model": CharacterErrorResponse, "description": "Character not found"},
    500: {"model": CharacterErrorResponse, "description": "Internal server error"}
})
async def update_character(
    character_id: str,
    request: CharacterDesignUpdate,
    current_user: UserProfile = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> CharacterDesignDetailed:
    """
    Update a character's information.

    - **character_id**: UUID of the character to update
    """
    try:
        user_id = current_user.id

        if not character_service.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Character service is currently unavailable"
                }
            )

        # Convert request to dict, excluding None values
        updates = request.dict(exclude_none=True)

        # Convert UUID to string if present
        if 'collection_id' in updates and updates['collection_id']:
            updates['collection_id'] = str(updates['collection_id'])
        if 'thumbnail_image_id' in updates and updates['thumbnail_image_id']:
            updates['thumbnail_image_id'] = str(updates['thumbnail_image_id'])

        character = await character_service.update_character(
            access_token=credentials.credentials,
            user_id=user_id,
            character_id=character_id,
            **updates
        )

        if not character:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "not_found",
                    "message": "Character not found or access denied"
                }
            )

        return CharacterDesignDetailed(**character)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "validation_error",
                "message": str(e)
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating character {character_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "update_failed",
                "message": f"Failed to update character: {str(e)}"
            }
        )

@router.delete("/{character_id}", response_model=DeleteCharacterResponse, responses={
    401: {"model": CharacterErrorResponse, "description": "Authentication required"},
    404: {"model": CharacterErrorResponse, "description": "Character not found"},
    500: {"model": CharacterErrorResponse, "description": "Internal server error"}
})
async def delete_character(
    character_id: str,
    current_user: UserProfile = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> DeleteCharacterResponse:
    """
    Delete a character and all its relationships.

    This will remove the character and its reference image links.
    The actual generated images will remain in the system.

    - **character_id**: UUID of the character to delete
    """
    try:
        user_id = current_user.id

        if not character_service.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Character service is currently unavailable"
                }
            )

        success = await character_service.delete_character(
            access_token=credentials.credentials,
            user_id=user_id,
            character_id=character_id
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "not_found",
                    "message": "Character not found or access denied"
                }
            )

        return DeleteCharacterResponse(
            success=True,
            message="Character deleted successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting character {character_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "deletion_failed",
                "message": f"Failed to delete character: {str(e)}"
            }
        )

# =============================================
# Reference Image Endpoints
# =============================================

@router.post("/{character_id}/reference-images", response_model=CharacterReferenceImage, status_code=status.HTTP_201_CREATED, responses={
    400: {"model": CharacterErrorResponse, "description": "Invalid request parameters"},
    401: {"model": CharacterErrorResponse, "description": "Authentication required"},
    404: {"model": CharacterErrorResponse, "description": "Character or image not found"},
    500: {"model": CharacterErrorResponse, "description": "Internal server error"}
})
async def add_reference_image(
    character_id: str,
    request: CharacterReferenceImageCreate,
    current_user: UserProfile = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> CharacterReferenceImage:
    """
    Add a reference image to a character.

    Links an existing generated image as a reference for this character.
    The image will be marked as a character reference and hidden from the main gallery.

    - **character_id**: UUID of the character
    - **generated_image_id**: UUID of the generated image to use
    - **angle_description**: Optional description (e.g., "front view", "side profile")
    - **is_primary**: Whether this should be the primary thumbnail
    - **display_order**: Sort order for displaying references
    """
    try:
        user_id = current_user.id

        if not character_service.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Character service is currently unavailable"
                }
            )

        reference = await character_service.add_reference_image(
            access_token=credentials.credentials,
            user_id=user_id,
            character_id=character_id,
            generated_image_id=str(request.generated_image_id),
            angle_description=request.angle_description,
            is_primary=request.is_primary,
            display_order=request.display_order
        )

        return CharacterReferenceImage(**reference)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": str(e)
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding reference image: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "add_failed",
                "message": f"Failed to add reference image: {str(e)}"
            }
        )

@router.delete("/{character_id}/reference-images/{reference_id}", response_model=DeleteCharacterResponse, responses={
    401: {"model": CharacterErrorResponse, "description": "Authentication required"},
    404: {"model": CharacterErrorResponse, "description": "Reference image not found"},
    500: {"model": CharacterErrorResponse, "description": "Internal server error"}
})
async def remove_reference_image(
    character_id: str,
    reference_id: str,
    current_user: UserProfile = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> DeleteCharacterResponse:
    """
    Remove a reference image from a character.

    Unlinks the reference image from the character.
    The generated image itself is not deleted.

    - **character_id**: UUID of the character
    - **reference_id**: UUID of the reference image link to remove
    """
    try:
        user_id = current_user.id

        if not character_service.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Character service is currently unavailable"
                }
            )

        success = await character_service.remove_reference_image(
            access_token=credentials.credentials,
            user_id=user_id,
            character_id=character_id,
            reference_id=reference_id
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "not_found",
                    "message": "Reference image not found or access denied"
                }
            )

        return DeleteCharacterResponse(
            success=True,
            message="Reference image removed successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing reference image: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "removal_failed",
                "message": f"Failed to remove reference image: {str(e)}"
            }
        )

@router.put("/{character_id}/reference-images/reorder", response_model=DeleteCharacterResponse, responses={
    400: {"model": CharacterErrorResponse, "description": "Invalid request parameters"},
    401: {"model": CharacterErrorResponse, "description": "Authentication required"},
    404: {"model": CharacterErrorResponse, "description": "Character not found"},
    500: {"model": CharacterErrorResponse, "description": "Internal server error"}
})
async def reorder_reference_images(
    character_id: str,
    request: ReorderReferenceImagesRequest,
    current_user: UserProfile = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> DeleteCharacterResponse:
    """
    Reorder reference images for a character.

    Updates the display order of reference images.

    - **character_id**: UUID of the character
    - **image_orders**: List of {id: UUID, display_order: int}
    """
    try:
        user_id = current_user.id

        if not character_service.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Character service is currently unavailable"
                }
            )

        success = await character_service.reorder_references(
            access_token=credentials.credentials,
            user_id=user_id,
            character_id=character_id,
            image_orders=request.image_orders
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "not_found",
                    "message": "Character not found or access denied"
                }
            )

        return DeleteCharacterResponse(
            success=True,
            message="Reference images reordered successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reordering reference images: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "reorder_failed",
                "message": f"Failed to reorder reference images: {str(e)}"
            }
        )

@router.post("/{character_id}/set-primary/{image_id}", response_model=SetPrimaryImageResponse, responses={
    401: {"model": CharacterErrorResponse, "description": "Authentication required"},
    404: {"model": CharacterErrorResponse, "description": "Character or image not found"},
    500: {"model": CharacterErrorResponse, "description": "Internal server error"}
})
async def set_primary_image(
    character_id: str,
    image_id: str,
    current_user: UserProfile = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> SetPrimaryImageResponse:
    """
    Set a reference image as the primary thumbnail for a character.

    - **character_id**: UUID of the character
    - **image_id**: UUID of the generated image to set as primary
    """
    try:
        user_id = current_user.id

        if not character_service.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Character service is currently unavailable"
                }
            )

        success = await character_service.set_primary_reference(
            access_token=credentials.credentials,
            user_id=user_id,
            character_id=character_id,
            generated_image_id=image_id
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "not_found",
                    "message": "Character or image not found"
                }
            )

        return SetPrimaryImageResponse(
            success=True,
            message="Primary thumbnail updated successfully",
            thumbnail_image_id=image_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting primary image: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "set_primary_failed",
                "message": f"Failed to set primary image: {str(e)}"
            }
        )

# =============================================
# Collection Endpoints
# =============================================

@router.post("/collections", response_model=CharacterCollection, status_code=status.HTTP_201_CREATED, responses={
    400: {"model": CharacterErrorResponse, "description": "Invalid request parameters"},
    401: {"model": CharacterErrorResponse, "description": "Authentication required"},
    500: {"model": CharacterErrorResponse, "description": "Internal server error"}
})
async def create_collection(
    request: CharacterCollectionCreate,
    current_user: UserProfile = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> CharacterCollection:
    """
    Create a character collection/folder.

    Collections help organize characters into groups.

    - **name**: Collection name (required)
    - **description**: Optional description
    """
    try:
        user_id = current_user.id

        if not character_service.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Character service is currently unavailable"
                }
            )

        collection = await character_service.create_collection(
            access_token=credentials.credentials,
            user_id=user_id,
            name=request.name,
            description=request.description
        )

        return CharacterCollection(**collection)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating collection: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "creation_failed",
                "message": f"Failed to create collection: {str(e)}"
            }
        )

@router.get("/collections", response_model=CollectionListResponse, responses={
    401: {"model": CharacterErrorResponse, "description": "Authentication required"},
    500: {"model": CharacterErrorResponse, "description": "Internal server error"}
})
async def list_collections(
    current_user: UserProfile = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> CollectionListResponse:
    """
    Get all character collections for the current user.

    Returns collections with character counts.
    """
    try:
        user_id = current_user.id

        if not character_service.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Character service is currently unavailable"
                }
            )

        collections = await character_service.list_collections(
            access_token=credentials.credentials,
            user_id=user_id
        )

        return CollectionListResponse(
            collections=collections,
            total=len(collections)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing collections: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "fetch_failed",
                "message": f"Failed to fetch collections: {str(e)}"
            }
        )

@router.delete("/collections/{collection_id}", response_model=DeleteCharacterResponse, responses={
    401: {"model": CharacterErrorResponse, "description": "Authentication required"},
    500: {"model": CharacterErrorResponse, "description": "Internal server error"}
})
async def delete_collection(
    collection_id: str,
    current_user: UserProfile = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> DeleteCharacterResponse:
    """
    Delete a character collection.

    Characters in the collection will become uncategorized.

    - **collection_id**: UUID of the collection to delete
    """
    try:
        user_id = current_user.id

        if not character_service.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Character service is currently unavailable"
                }
            )

        await character_service.delete_collection(
            access_token=credentials.credentials,
            user_id=user_id,
            collection_id=collection_id
        )

        return DeleteCharacterResponse(
            success=True,
            message="Collection deleted successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting collection: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "deletion_failed",
                "message": f"Failed to delete collection: {str(e)}"
            }
        )

# =============================================
# Scene Integration Endpoints
# =============================================

@router.post("/generate-scene-prompt", response_model=GenerateScenePromptResponse, responses={
    400: {"model": CharacterErrorResponse, "description": "Invalid request parameters"},
    401: {"model": CharacterErrorResponse, "description": "Authentication required"},
    500: {"model": CharacterErrorResponse, "description": "Internal server error"}
})
async def generate_scene_prompt(
    request: GenerateScenePromptRequest,
    current_user: UserProfile = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> GenerateScenePromptResponse:
    """
    Generate a combined prompt for scene generation with characters.

    Combines the base scene description with character descriptions and
    returns reference image URLs for image generation.

    - **scene_prompt**: Base scene description
    - **character_ids**: List of character IDs to include
    - **include_visual_notes**: Whether to include visual style notes
    """
    try:
        user_id = current_user.id

        if not character_service.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "message": "Character service is currently unavailable"
                }
            )

        character_ids_str = [str(cid) for cid in request.character_ids]

        result = await character_service.generate_scene_prompt(
            access_token=credentials.credentials,
            user_id=user_id,
            scene_prompt=request.scene_prompt,
            character_ids=character_ids_str,
            include_visual_notes=request.include_visual_notes
        )

        return GenerateScenePromptResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating scene prompt: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "generation_failed",
                "message": f"Failed to generate scene prompt: {str(e)}"
            }
        )
