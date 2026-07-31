"""
Image Folder API Endpoints
Provides REST API for organizing generated images into folders
"""

from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
import logging
from datetime import datetime

from middleware.auth_middleware import get_current_user
from models.auth_models import UserProfile
from models.image_folder_models import (
    ImageFolder,
    CreateFolderRequest,
    UpdateFolderRequest,
    MoveImageToFolderRequest,
    BulkMoveImagesRequest,
    FolderResponse,
    FoldersListResponse,
    ErrorResponse
)
from services.supabase import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/folders", tags=["Image Folders"])

# Initialize Supabase client
supabase = get_supabase_client()


@router.get("", response_model=FoldersListResponse, responses={
    401: {"model": ErrorResponse, "description": "Authentication required"},
    500: {"model": ErrorResponse, "description": "Internal server error"}
})
async def list_folders(
    current_user: UserProfile = Depends(get_current_user)
) -> FoldersListResponse:
    """
    Get all folders for the current user with image counts.

    Returns a list of folders ordered by sort_order and creation date,
    including the number of images in each folder.
    """
    try:
        user_id = current_user.id
        logger.info(f"Fetching folders for user {user_id}")

        # Query folders with image counts using a subquery/join
        # First, get all folders for the user
        folders_response = supabase.table('image_folders')\
            .select('*')\
            .eq('user_id', user_id)\
            .order('sort_order')\
            .order('created_at')\
            .execute()

        folders = folders_response.data if folders_response.data else []

        # Get image counts for each folder
        result_folders = []
        for folder in folders:
            # Count images in this folder
            count_response = supabase.table('generated_images')\
                .select('id', count='exact')\
                .eq('user_id', user_id)\
                .eq('folder_id', folder['id'])\
                .execute()

            image_count = count_response.count if hasattr(count_response, 'count') else 0

            result_folders.append(ImageFolder(
                id=folder['id'],
                user_id=folder['user_id'],
                name=folder['name'],
                color=folder.get('color', '#6366f1'),
                sort_order=folder.get('sort_order', 0),
                image_count=image_count,
                created_at=folder['created_at'],
                updated_at=folder['updated_at']
            ))

        logger.info(f"Returning {len(result_folders)} folders for user {user_id}")

        return FoldersListResponse(
            folders=result_folders,
            total=len(result_folders)
        )

    except Exception as e:
        logger.error(f"Error fetching folders for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "fetch_failed",
                "message": f"Failed to fetch folders: {str(e)}"
            }
        )


@router.post("", response_model=FolderResponse, responses={
    400: {"model": ErrorResponse, "description": "Invalid request or duplicate name"},
    401: {"model": ErrorResponse, "description": "Authentication required"},
    500: {"model": ErrorResponse, "description": "Internal server error"}
})
async def create_folder(
    request: CreateFolderRequest,
    current_user: UserProfile = Depends(get_current_user)
) -> FolderResponse:
    """
    Create a new folder for organizing images.

    - **name**: Folder name (1-100 characters, unique per user)
    - **color**: Optional hex color code (default: #6366f1)
    """
    try:
        user_id = current_user.id
        logger.info(f"Creating folder '{request.name}' for user {user_id}")

        # Check for duplicate name (case-insensitive)
        existing = supabase.table('image_folders')\
            .select('id')\
            .eq('user_id', user_id)\
            .ilike('name', request.name)\
            .execute()

        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "duplicate_name",
                    "message": f"A folder named '{request.name}' already exists"
                }
            )

        # Create folder
        folder_data = {
            'user_id': user_id,
            'name': request.name,
            'color': request.color or '#6366f1',
            'sort_order': 0,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }

        response = supabase.table('image_folders').insert(folder_data).execute()

        if not response.data:
            raise Exception("Failed to create folder")

        created_folder = response.data[0]

        logger.info(f"Created folder {created_folder['id']} for user {user_id}")

        return FolderResponse(
            folder=ImageFolder(
                id=created_folder['id'],
                user_id=created_folder['user_id'],
                name=created_folder['name'],
                color=created_folder.get('color', '#6366f1'),
                sort_order=created_folder.get('sort_order', 0),
                image_count=0,
                created_at=created_folder['created_at'],
                updated_at=created_folder['updated_at']
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating folder for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "creation_failed",
                "message": f"Failed to create folder: {str(e)}"
            }
        )


@router.put("/{folder_id}", response_model=FolderResponse, responses={
    400: {"model": ErrorResponse, "description": "Invalid request or duplicate name"},
    401: {"model": ErrorResponse, "description": "Authentication required"},
    404: {"model": ErrorResponse, "description": "Folder not found"},
    500: {"model": ErrorResponse, "description": "Internal server error"}
})
async def update_folder(
    folder_id: str,
    request: UpdateFolderRequest,
    current_user: UserProfile = Depends(get_current_user)
) -> FolderResponse:
    """
    Update a folder's name, color, or sort order.

    - **name**: New folder name (optional)
    - **color**: New hex color code (optional)
    - **sort_order**: New sort order (optional)
    """
    try:
        user_id = current_user.id
        logger.info(f"Updating folder {folder_id} for user {user_id}")

        # Check folder exists and belongs to user
        existing = supabase.table('image_folders')\
            .select('*')\
            .eq('id', folder_id)\
            .eq('user_id', user_id)\
            .execute()

        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "folder_not_found",
                    "message": "Folder not found or access denied"
                }
            )

        # Check for duplicate name if renaming
        if request.name:
            duplicate = supabase.table('image_folders')\
                .select('id')\
                .eq('user_id', user_id)\
                .ilike('name', request.name)\
                .neq('id', folder_id)\
                .execute()

            if duplicate.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "duplicate_name",
                        "message": f"A folder named '{request.name}' already exists"
                    }
                )

        # Build update data
        update_data = {'updated_at': datetime.utcnow().isoformat()}
        if request.name is not None:
            update_data['name'] = request.name
        if request.color is not None:
            update_data['color'] = request.color
        if request.sort_order is not None:
            update_data['sort_order'] = request.sort_order

        # Update folder
        response = supabase.table('image_folders')\
            .update(update_data)\
            .eq('id', folder_id)\
            .eq('user_id', user_id)\
            .execute()

        if not response.data:
            raise Exception("Failed to update folder")

        updated_folder = response.data[0]

        # Get image count
        count_response = supabase.table('generated_images')\
            .select('id', count='exact')\
            .eq('user_id', user_id)\
            .eq('folder_id', folder_id)\
            .execute()

        image_count = count_response.count if hasattr(count_response, 'count') else 0

        logger.info(f"Updated folder {folder_id} for user {user_id}")

        return FolderResponse(
            folder=ImageFolder(
                id=updated_folder['id'],
                user_id=updated_folder['user_id'],
                name=updated_folder['name'],
                color=updated_folder.get('color', '#6366f1'),
                sort_order=updated_folder.get('sort_order', 0),
                image_count=image_count,
                created_at=updated_folder['created_at'],
                updated_at=updated_folder['updated_at']
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating folder {folder_id} for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "update_failed",
                "message": f"Failed to update folder: {str(e)}"
            }
        )


@router.delete("/{folder_id}", responses={
    204: {"description": "Folder deleted successfully"},
    401: {"model": ErrorResponse, "description": "Authentication required"},
    404: {"model": ErrorResponse, "description": "Folder not found"},
    500: {"model": ErrorResponse, "description": "Internal server error"}
})
async def delete_folder(
    folder_id: str,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Delete a folder.

    Images in the folder will have their folder_id set to NULL (uncategorized).
    """
    try:
        user_id = current_user.id
        logger.info(f"Deleting folder {folder_id} for user {user_id}")

        # Check folder exists and belongs to user
        existing = supabase.table('image_folders')\
            .select('*')\
            .eq('id', folder_id)\
            .eq('user_id', user_id)\
            .execute()

        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "folder_not_found",
                    "message": "Folder not found or access denied"
                }
            )

        # Delete folder (images will be set to NULL automatically by ON DELETE SET NULL)
        supabase.table('image_folders')\
            .delete()\
            .eq('id', folder_id)\
            .eq('user_id', user_id)\
            .execute()

        logger.info(f"Deleted folder {folder_id} for user {user_id}")

        return {"message": "Folder deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting folder {folder_id} for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "deletion_failed",
                "message": f"Failed to delete folder: {str(e)}"
            }
        )


@router.put("/images/{image_id}/folder", responses={
    200: {"description": "Image moved successfully"},
    401: {"model": ErrorResponse, "description": "Authentication required"},
    404: {"model": ErrorResponse, "description": "Image or folder not found"},
    500: {"model": ErrorResponse, "description": "Internal server error"}
})
async def move_image_to_folder(
    image_id: str,
    request: MoveImageToFolderRequest,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Move an image to a folder or remove it from its current folder.

    - **folder_id**: Folder ID to move to (null to remove from folder)
    """
    try:
        user_id = current_user.id
        logger.info(f"Moving image {image_id} to folder {request.folder_id} for user {user_id}")

        # Check image exists and belongs to user
        image_check = supabase.table('generated_images')\
            .select('id')\
            .eq('id', image_id)\
            .eq('user_id', user_id)\
            .execute()

        if not image_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "image_not_found",
                    "message": "Image not found or access denied"
                }
            )

        # If folder_id provided, check folder exists and belongs to user
        if request.folder_id:
            folder_check = supabase.table('image_folders')\
                .select('id')\
                .eq('id', request.folder_id)\
                .eq('user_id', user_id)\
                .execute()

            if not folder_check.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "folder_not_found",
                        "message": "Folder not found or access denied"
                    }
                )

        # Update image folder_id
        supabase.table('generated_images')\
            .update({'folder_id': request.folder_id})\
            .eq('id', image_id)\
            .eq('user_id', user_id)\
            .execute()

        folder_name = "Uncategorized" if not request.folder_id else "folder"
        logger.info(f"Moved image {image_id} to {folder_name} for user {user_id}")

        return {"message": "Image moved successfully", "folder_id": request.folder_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error moving image {image_id} for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "move_failed",
                "message": f"Failed to move image: {str(e)}"
            }
        )


@router.post("/images/bulk-move", responses={
    200: {"description": "Images moved successfully"},
    400: {"model": ErrorResponse, "description": "Invalid request"},
    401: {"model": ErrorResponse, "description": "Authentication required"},
    404: {"model": ErrorResponse, "description": "Folder not found"},
    500: {"model": ErrorResponse, "description": "Internal server error"}
})
async def bulk_move_images(
    request: BulkMoveImagesRequest,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Move multiple images to a folder or remove them from their current folders.

    - **image_ids**: List of image IDs to move (max 100)
    - **folder_id**: Folder ID to move to (null to remove from folders)
    """
    try:
        user_id = current_user.id
        logger.info(f"Bulk moving {len(request.image_ids)} images to folder {request.folder_id} for user {user_id}")

        # If folder_id provided, check folder exists and belongs to user
        if request.folder_id:
            folder_check = supabase.table('image_folders')\
                .select('id')\
                .eq('id', request.folder_id)\
                .eq('user_id', user_id)\
                .execute()

            if not folder_check.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "folder_not_found",
                        "message": "Folder not found or access denied"
                    }
                )

        # Update all images (only those belonging to user)
        # Supabase will only update images that belong to the user due to RLS
        supabase.table('generated_images')\
            .update({'folder_id': request.folder_id})\
            .in_('id', request.image_ids)\
            .eq('user_id', user_id)\
            .execute()

        folder_name = "Uncategorized" if not request.folder_id else "folder"
        logger.info(f"Bulk moved {len(request.image_ids)} images to {folder_name} for user {user_id}")

        return {
            "message": f"Successfully moved {len(request.image_ids)} images",
            "folder_id": request.folder_id,
            "image_count": len(request.image_ids)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error bulk moving images for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "bulk_move_failed",
                "message": f"Failed to move images: {str(e)}"
            }
        )
