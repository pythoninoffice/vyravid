"""
Character Design Service
Handles business logic for character management, reference images, and scene integration
"""

import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from services.supabase import get_supabase_client
from services.gcs_service import GCSService
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class CharacterService:
    """Service for managing character designs and their reference images"""

    def __init__(self):
        """Initialize character service"""
        self.supabase = get_supabase_client()
        self.gcs_service = GCSService()

    def is_available(self) -> bool:
        """Check if character service is available"""
        return self.supabase is not None

    def _get_authenticated_client(self, access_token: str = None):
        """Local mode: return the shared SQLite client (no JWT / RLS)."""
        return get_supabase_client()

    # =============================================
    # Character CRUD Operations
    # =============================================

    async def create_character(
        self,
        access_token: str,
        user_id: str,
        name: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        visual_style_notes: Optional[str] = None,
        collection_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new character design

        Args:
            access_token: User's JWT access token
            user_id: ID of the user creating the character
            name: Character name
            description: Text description/prompt for the character
            tags: List of tags (e.g., novel/game/anime names)
            visual_style_notes: Visual style notes for consistency
            collection_id: Optional collection ID

        Returns:
            Created character record
        """
        if not self.is_available():
            raise Exception("Character service not available")

        # Validate inputs
        if not name or not name.strip():
            raise ValueError("Character name is required")

        # Create character record
        character_data = {
            'user_id': user_id,
            'name': name.strip(),
            'description': description,
            'tags': tags or [],
            'visual_style_notes': visual_style_notes,
            'collection_id': collection_id
        }

        try:
            supabase = self._get_authenticated_client(access_token)
            response = supabase.table('character_designs').insert(character_data).execute()

            if not response.data:
                raise Exception("Failed to create character")

            character = response.data[0]
            logger.info(f"Created character {character['id']} for user {user_id}")

            return character

        except Exception as e:
            logger.error(f"Error creating character: {str(e)}")
            raise

    async def get_character(
        self,
        access_token: str,
        user_id: str,
        character_id: str,
        include_references: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Get a character by ID

        Args:
            access_token: User's JWT access token
            user_id: ID of the user
            character_id: ID of the character
            include_references: Whether to include reference images

        Returns:
            Character record with optional reference images
        """
        if not self.is_available():
            raise Exception("Character service not available")

        try:
            supabase = self._get_authenticated_client(access_token)

            # Get character
            response = supabase.table('character_designs')\
                .select('*')\
                .eq('id', character_id)\
                .eq('user_id', user_id)\
                .single()\
                .execute()

            if not response.data:
                return None

            character = response.data

            # Get collection name if in a collection
            if character.get('collection_id'):
                collection_response = supabase.table('character_collections')\
                    .select('name')\
                    .eq('id', character['collection_id'])\
                    .single()\
                    .execute()
                if collection_response.data:
                    character['collection_name'] = collection_response.data['name']

            # Get reference images if requested
            if include_references:
                references = await self.get_character_references(access_token, character_id)
                character['reference_images'] = references

                # Get thumbnail URL if thumbnail_image_id is set
                if character.get('thumbnail_image_id'):
                    for ref in references:
                        if ref['generated_image_id'] == character['thumbnail_image_id']:
                            character['thumbnail_url'] = ref.get('image_url')
                            break

            return character

        except Exception as e:
            logger.error(f"Error getting character {character_id}: {str(e)}")
            raise

    async def list_characters(
        self,
        access_token: str,
        user_id: str,
        page: int = 1,
        limit: int = 20,
        collection_id: Optional[str] = None,
        search: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        List characters for a user with pagination and filters

        Args:
            access_token: User's JWT access token
            user_id: ID of the user
            page: Page number (1-based)
            limit: Items per page
            collection_id: Filter by collection
            search: Search in name and description
            tags: Filter by tags

        Returns:
            Dict with characters list and pagination info
        """
        if not self.is_available():
            raise Exception("Character service not available")

        try:
            supabase = self._get_authenticated_client(access_token)
            offset = (page - 1) * limit

            # Build query
            query = supabase.table('character_designs')\
                .select('*', count='exact')\
                .eq('user_id', user_id)

            # Apply filters
            if collection_id:
                query = query.eq('collection_id', collection_id)

            if search:
                # Note: Supabase supports ilike for case-insensitive search
                query = query.or_(f'name.ilike.%{search}%,description.ilike.%{search}%')

            if tags and len(tags) > 0:
                # Filter by tags using array overlap
                query = query.overlaps('tags', tags)

            # Order and paginate
            query = query.order('created_at', desc=True)\
                .range(offset, offset + limit)

            response = query.execute()

            characters = response.data or []
            total_count = response.count or 0
            has_more = (offset + len(characters)) < total_count

            # Enrich characters with thumbnail URLs and collection names - BATCH OPTIMIZED
            # Step 1: Batch fetch collection names
            collection_ids = [c['collection_id'] for c in characters if c.get('collection_id')]
            collection_map = {}
            if collection_ids:
                logger.info(f"🚀 Batch fetching {len(set(collection_ids))} collection names")
                collections_response = supabase.table('character_collections')\
                    .select('id, name')\
                    .in_('id', list(set(collection_ids)))\
                    .execute()
                if collections_response.data:
                    collection_map = {c['id']: c['name'] for c in collections_response.data}

            # Step 2: Batch fetch thumbnail images
            thumbnail_ids = [c['thumbnail_image_id'] for c in characters if c.get('thumbnail_image_id')]
            image_map = {}
            if thumbnail_ids:
                logger.info(f"🚀 Batch fetching {len(set(thumbnail_ids))} thumbnail images")
                images_response = supabase.table('generated_images')\
                    .select('id, gcs_path, thumbnail_gcs_path, gcs_signed_url, thumbnail_signed_url')\
                    .in_('id', list(set(thumbnail_ids)))\
                    .execute()
                if images_response.data:
                    image_map = {img['id']: img for img in images_response.data}

            # Step 3: Apply enrichment data to characters (no database queries in loop!)
            for character in characters:
                # Apply collection name from batch data
                if character.get('collection_id') and character['collection_id'] in collection_map:
                    character['collection_name'] = collection_map[character['collection_id']]

                # Apply thumbnail URL from batch data (no refresh for list view to avoid delays)
                if character.get('thumbnail_image_id') and character['thumbnail_image_id'] in image_map:
                    image_data = image_map[character['thumbnail_image_id']]
                    # Use existing signed URL without refreshing (refresh only on-demand when image fails to load)
                    character['thumbnail_url'] = image_data.get('thumbnail_signed_url') or image_data.get('gcs_signed_url')

            logger.info(f"✅ Enriched {len(characters)} characters with batch data")

            return {
                'characters': characters,
                'total': total_count,
                'page': page,
                'limit': limit,
                'has_more': has_more
            }

        except Exception as e:
            logger.error(f"Error listing characters: {str(e)}")
            raise

    async def update_character(
        self,
        access_token: str,
        user_id: str,
        character_id: str,
        **updates
    ) -> Optional[Dict[str, Any]]:
        """
        Update a character

        Args:
            access_token: User's JWT access token
            user_id: ID of the user
            character_id: ID of the character
            **updates: Fields to update

        Returns:
            Updated character record
        """
        if not self.is_available():
            raise Exception("Character service not available")

        try:
            supabase = self._get_authenticated_client(access_token)

            # Verify ownership
            existing = await self.get_character(access_token, user_id, character_id, include_references=False)
            if not existing:
                raise ValueError("Character not found or access denied")

            # Filter allowed updates
            allowed_fields = ['name', 'description', 'tags', 'visual_style_notes', 'collection_id', 'thumbnail_image_id']
            update_data = {k: v for k, v in updates.items() if k in allowed_fields}

            if not update_data:
                return existing

            # Update character
            response = supabase.table('character_designs')\
                .update(update_data)\
                .eq('id', character_id)\
                .eq('user_id', user_id)\
                .execute()

            if not response.data:
                raise Exception("Failed to update character")

            logger.info(f"Updated character {character_id} for user {user_id}")

            return await self.get_character(access_token, user_id, character_id)

        except Exception as e:
            logger.error(f"Error updating character {character_id}: {str(e)}")
            raise

    async def delete_character(
        self,
        access_token: str,
        user_id: str,
        character_id: str
    ) -> bool:
        """
        Delete a character and its relationships

        Args:
            access_token: User's JWT access token
            user_id: ID of the user
            character_id: ID of the character

        Returns:
            True if deleted successfully
        """
        if not self.is_available():
            raise Exception("Character service not available")

        try:
            supabase = self._get_authenticated_client(access_token)

            # Verify ownership
            existing = await self.get_character(access_token, user_id, character_id, include_references=False)
            if not existing:
                return False

            # Delete character (cascade will handle reference_images and scene_characters)
            response = supabase.table('character_designs')\
                .delete()\
                .eq('id', character_id)\
                .eq('user_id', user_id)\
                .execute()

            logger.info(f"Deleted character {character_id} for user {user_id}")

            return True

        except Exception as e:
            logger.error(f"Error deleting character {character_id}: {str(e)}")
            raise

    # =============================================
    # Reference Image Operations
    # =============================================

    async def add_reference_image(
        self,
        access_token: str,
        user_id: str,
        character_id: str,
        generated_image_id: str,
        angle_description: Optional[str] = None,
        is_primary: bool = False,
        display_order: int = 0
    ) -> Dict[str, Any]:
        """
        Add a reference image to a character

        Args:
            access_token: User's JWT access token
            user_id: ID of the user
            character_id: ID of the character
            generated_image_id: ID of the generated image
            angle_description: Description of the angle/view
            is_primary: Whether this should be the primary thumbnail
            display_order: Display order for sorting

        Returns:
            Created reference image record
        """
        if not self.is_available():
            raise Exception("Character service not available")

        try:
            supabase = self._get_authenticated_client(access_token)

            # Verify character ownership
            character = await self.get_character(access_token, user_id, character_id, include_references=False)
            if not character:
                raise ValueError("Character not found or access denied")

            # Verify image ownership and get paths for URL refresh
            image_response = supabase.table('generated_images')\
                .select('id, gcs_path, thumbnail_gcs_path, gcs_signed_url, thumbnail_signed_url, width, height')\
                .eq('id', generated_image_id)\
                .eq('user_id', user_id)\
                .single()\
                .execute()

            if not image_response.data:
                raise ValueError("Image not found or access denied")

            image_data = image_response.data

            # Generate fresh signed URLs for the response (but don't update database)
            if image_data.get('gcs_path'):
                try:
                    fresh_url = await self.gcs_service.generate_signed_url(
                        image_data['gcs_path'],
                        expiration_hours=24
                    )
                    if fresh_url:
                        image_data['gcs_signed_url'] = fresh_url
                except Exception as e:
                    logger.warning(f"Failed to generate signed URL when adding reference: {str(e)}")

            if image_data.get('thumbnail_gcs_path'):
                try:
                    fresh_thumb_url = await self.gcs_service.generate_signed_url(
                        image_data['thumbnail_gcs_path'],
                        expiration_hours=24
                    )
                    if fresh_thumb_url:
                        image_data['thumbnail_signed_url'] = fresh_thumb_url
                except Exception as e:
                    logger.warning(f"Failed to generate thumbnail signed URL when adding reference: {str(e)}")

            # Create reference image link
            reference_data = {
                'character_id': character_id,
                'generated_image_id': generated_image_id,
                'angle_description': angle_description,
                'is_primary': is_primary,
                'display_order': display_order
            }

            response = supabase.table('character_reference_images')\
                .insert(reference_data)\
                .execute()

            if not response.data:
                raise Exception("Failed to add reference image")

            reference = response.data[0]

            # Mark the generated image as a character reference
            supabase.table('generated_images')\
                .update({'is_character_reference': True, 'character_id': character_id})\
                .eq('id', generated_image_id)\
                .execute()

            # If this is primary, update character thumbnail and unset other primaries
            if is_primary:
                await self.set_primary_reference(access_token, user_id, character_id, generated_image_id)

            logger.info(f"Added reference image {generated_image_id} to character {character_id}")

            # Enrich with image data (using refreshed URLs)
            reference['image_url'] = image_data.get('gcs_signed_url')
            reference['thumbnail_url'] = image_data.get('thumbnail_signed_url')
            reference['width'] = image_data.get('width')
            reference['height'] = image_data.get('height')

            return reference

        except Exception as e:
            logger.error(f"Error adding reference image: {str(e)}")
            raise

    async def get_character_references(
        self,
        access_token: str,
        character_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all reference images for a character

        Args:
            access_token: User's JWT access token
            character_id: ID of the character

        Returns:
            List of reference image records with image data
        """
        if not self.is_available():
            raise Exception("Character service not available")

        try:
            supabase = self._get_authenticated_client(access_token)

            # Get reference image links
            response = supabase.table('character_reference_images')\
                .select('*')\
                .eq('character_id', character_id)\
                .order('display_order')\
                .order('created_at')\
                .execute()

            references = response.data or []

            # Enrich with image data and generate fresh signed URLs for response
            # Note: We generate fresh URLs on-demand but don't update the database
            # to avoid unnecessary PATCH requests on every page load
            for ref in references:
                image_response = supabase.table('generated_images')\
                    .select('id, gcs_path, thumbnail_gcs_path, gcs_signed_url, thumbnail_signed_url, width, height')\
                    .eq('id', ref['generated_image_id'])\
                    .single()\
                    .execute()

                if image_response.data:
                    image_data = image_response.data

                    # Generate fresh main image signed URL if we have gcs_path
                    if image_data.get('gcs_path'):
                        try:
                            fresh_url = await self.gcs_service.generate_signed_url(
                                image_data['gcs_path'],
                                expiration_hours=24
                            )
                            if fresh_url:
                                ref['image_url'] = fresh_url
                            else:
                                ref['image_url'] = image_data.get('gcs_signed_url')
                        except Exception as e:
                            logger.warning(f"Failed to generate signed URL for {image_data['id']}: {str(e)}")
                            ref['image_url'] = image_data.get('gcs_signed_url')
                    else:
                        ref['image_url'] = image_data.get('gcs_signed_url')

                    # Generate fresh thumbnail signed URL if we have thumbnail_gcs_path
                    if image_data.get('thumbnail_gcs_path'):
                        try:
                            fresh_thumb_url = await self.gcs_service.generate_signed_url(
                                image_data['thumbnail_gcs_path'],
                                expiration_hours=24
                            )
                            if fresh_thumb_url:
                                ref['thumbnail_url'] = fresh_thumb_url
                            else:
                                ref['thumbnail_url'] = image_data.get('thumbnail_signed_url')
                        except Exception as e:
                            logger.warning(f"Failed to generate thumbnail signed URL for {image_data['id']}: {str(e)}")
                            ref['thumbnail_url'] = image_data.get('thumbnail_signed_url')
                    else:
                        ref['thumbnail_url'] = image_data.get('thumbnail_signed_url')

                    ref['width'] = image_data.get('width')
                    ref['height'] = image_data.get('height')

            return references

        except Exception as e:
            logger.error(f"Error getting character references: {str(e)}")
            raise

    async def remove_reference_image(
        self,
        access_token: str,
        user_id: str,
        character_id: str,
        reference_id: str
    ) -> bool:
        """
        Remove a reference image from a character

        Args:
            access_token: User's JWT access token
            user_id: ID of the user
            character_id: ID of the character
            reference_id: ID of the reference image link

        Returns:
            True if removed successfully
        """
        if not self.is_available():
            raise Exception("Character service not available")

        try:
            supabase = self._get_authenticated_client(access_token)

            # Verify character ownership
            character = await self.get_character(access_token, user_id, character_id, include_references=False)
            if not character:
                return False

            # Get the reference to get the generated_image_id
            ref_response = supabase.table('character_reference_images')\
                .select('*')\
                .eq('id', reference_id)\
                .eq('character_id', character_id)\
                .single()\
                .execute()

            if not ref_response.data:
                return False

            generated_image_id = ref_response.data['generated_image_id']

            # Delete reference link
            supabase.table('character_reference_images')\
                .delete()\
                .eq('id', reference_id)\
                .execute()

            # Unmark the generated image as character reference
            # (only if it's not referenced by other characters)
            other_refs = supabase.table('character_reference_images')\
                .select('id')\
                .eq('generated_image_id', generated_image_id)\
                .execute()

            if not other_refs.data:
                supabase.table('generated_images')\
                    .update({'is_character_reference': False, 'character_id': None})\
                    .eq('id', generated_image_id)\
                    .execute()

            logger.info(f"Removed reference image {reference_id} from character {character_id}")

            return True

        except Exception as e:
            logger.error(f"Error removing reference image: {str(e)}")
            raise

    async def set_primary_reference(
        self,
        access_token: str,
        user_id: str,
        character_id: str,
        generated_image_id: str
    ) -> bool:
        """
        Set a reference image as the primary thumbnail

        Args:
            access_token: User's JWT access token
            user_id: ID of the user
            character_id: ID of the character
            generated_image_id: ID of the image to set as primary

        Returns:
            True if set successfully
        """
        if not self.is_available():
            raise Exception("Character service not available")

        try:
            supabase = self._get_authenticated_client(access_token)

            # Verify character ownership
            character = await self.get_character(access_token, user_id, character_id, include_references=False)
            if not character:
                return False

            # Unset all other primaries for this character
            supabase.table('character_reference_images')\
                .update({'is_primary': False})\
                .eq('character_id', character_id)\
                .execute()

            # Set the new primary
            supabase.table('character_reference_images')\
                .update({'is_primary': True})\
                .eq('character_id', character_id)\
                .eq('generated_image_id', generated_image_id)\
                .execute()

            # Update character thumbnail_image_id
            supabase.table('character_designs')\
                .update({'thumbnail_image_id': generated_image_id})\
                .eq('id', character_id)\
                .execute()

            logger.info(f"Set primary reference for character {character_id} to image {generated_image_id}")

            return True

        except Exception as e:
            logger.error(f"Error setting primary reference: {str(e)}")
            raise

    async def reorder_references(
        self,
        access_token: str,
        user_id: str,
        character_id: str,
        image_orders: List[Dict[str, Any]]
    ) -> bool:
        """
        Reorder reference images

        Args:
            access_token: User's JWT access token
            user_id: ID of the user
            character_id: ID of the character
            image_orders: List of {id: str, display_order: int}

        Returns:
            True if reordered successfully
        """
        if not self.is_available():
            raise Exception("Character service not available")

        try:
            supabase = self._get_authenticated_client(access_token)

            # Verify character ownership
            character = await self.get_character(access_token, user_id, character_id, include_references=False)
            if not character:
                return False

            # Update display orders
            for item in image_orders:
                supabase.table('character_reference_images')\
                    .update({'display_order': item['display_order']})\
                    .eq('id', item['id'])\
                    .eq('character_id', character_id)\
                    .execute()

            logger.info(f"Reordered references for character {character_id}")

            return True

        except Exception as e:
            logger.error(f"Error reordering references: {str(e)}")
            raise

    # =============================================
    # Collection Operations
    # =============================================

    async def create_collection(
        self,
        access_token: str,
        user_id: str,
        name: str,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a character collection"""
        if not self.is_available():
            raise Exception("Character service not available")

        try:
            supabase = self._get_authenticated_client(access_token)

            collection_data = {
                'user_id': user_id,
                'name': name.strip(),
                'description': description
            }

            response = supabase.table('character_collections')\
                .insert(collection_data)\
                .execute()

            if not response.data:
                raise Exception("Failed to create collection")

            collection = response.data[0]
            logger.info(f"Created collection {collection['id']} for user {user_id}")

            return collection

        except Exception as e:
            logger.error(f"Error creating collection: {str(e)}")
            raise

    async def list_collections(
        self,
        access_token: str,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """List all collections for a user with character counts"""
        if not self.is_available():
            raise Exception("Character service not available")

        try:
            supabase = self._get_authenticated_client(access_token)

            response = supabase.table('character_collections')\
                .select('*')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .execute()

            collections = response.data or []

            # Add character counts
            for collection in collections:
                count_response = supabase.table('character_designs')\
                    .select('id', count='exact')\
                    .eq('collection_id', collection['id'])\
                    .execute()
                collection['character_count'] = count_response.count or 0

            return collections

        except Exception as e:
            logger.error(f"Error listing collections: {str(e)}")
            raise

    async def delete_collection(
        self,
        access_token: str,
        user_id: str,
        collection_id: str
    ) -> bool:
        """Delete a collection (characters will be uncategorized)"""
        if not self.is_available():
            raise Exception("Character service not available")

        try:
            supabase = self._get_authenticated_client(access_token)

            # Delete collection (characters will have collection_id set to NULL via ON DELETE SET NULL)
            response = supabase.table('character_collections')\
                .delete()\
                .eq('id', collection_id)\
                .eq('user_id', user_id)\
                .execute()

            logger.info(f"Deleted collection {collection_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting collection: {str(e)}")
            raise

    # =============================================
    # Scene Integration Operations
    # =============================================

    async def generate_scene_prompt(
        self,
        access_token: str,
        user_id: str,
        scene_prompt: str,
        character_ids: List[str],
        include_visual_notes: bool = True
    ) -> Dict[str, Any]:
        """
        Generate a combined prompt for scene generation with characters

        Args:
            access_token: User's JWT access token
            user_id: ID of the user
            scene_prompt: Base scene description
            character_ids: List of character IDs to include
            include_visual_notes: Whether to include visual style notes

        Returns:
            Dict with combined_prompt, character_names, and reference_image_urls
        """
        if not self.is_available():
            raise Exception("Character service not available")

        try:
            character_descriptions = []
            character_names = []
            reference_image_urls = []

            for char_id in character_ids:
                character = await self.get_character(access_token, user_id, char_id, include_references=True)
                if not character:
                    continue

                character_names.append(character['name'])

                # Build character description
                desc_parts = [f"{character['name']}"]

                if character.get('description'):
                    desc_parts.append(character['description'])

                if include_visual_notes and character.get('visual_style_notes'):
                    desc_parts.append(f"({character['visual_style_notes']})")

                character_descriptions.append(', '.join(desc_parts))

                # Collect reference image URLs
                for ref in character.get('reference_images', []):
                    if ref.get('image_url'):
                        reference_image_urls.append(ref['image_url'])

            # Combine prompts
            if character_descriptions:
                combined_prompt = f"{scene_prompt}. Characters: {'; '.join(character_descriptions)}"
            else:
                combined_prompt = scene_prompt

            return {
                'combined_prompt': combined_prompt,
                'character_names': character_names,
                'reference_image_urls': reference_image_urls
            }

        except Exception as e:
            logger.error(f"Error generating scene prompt: {str(e)}")
            raise
