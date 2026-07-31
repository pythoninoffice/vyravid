"""
Service for managing video project assets and enabling project editing
"""

from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime
import logging
import json
from db.supabase_client import SupabaseClient
from services.video_resolution import get_pixel_dimensions
import os

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()
# Configuration
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')

class ProjectAssetsService:
    """Service for managing all video project assets"""

    def __init__(self):
        self.supabase_client = SupabaseClient()
        self.supabase = self.supabase_client.supabase

    def _extract_greenscreen_effect_name(self, greenscreen_effect: str | None) -> str | None:
        """Extract effect name from full GCS URL or return as-is if already a name"""
        if not greenscreen_effect:
            return None

        # If it's a full URL, extract the filename without extension
        if greenscreen_effect.startswith('http'):
            try:
                # Extract filename from URL: https://storage.googleapis.com/bucket/greenscreen/fire2_v.mp4 -> fire2_v
                url_parts = greenscreen_effect.split('/')
                filename = url_parts[-1]  # Get last part (fire2_v.mp4)
                name_without_ext = filename.rsplit('.', 1)[0]  # Remove extension (fire2_v)
                return name_without_ext
            except Exception as e:
                logger.warning(f"Failed to extract effect name from URL: {greenscreen_effect}, error: {e}")
                return greenscreen_effect

        # Already just a name, return as-is
        return greenscreen_effect

    async def store_project_assets(
        self,
        project_id: UUID,
        generation_request: Dict[str, Any],
        audio_file_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Store all assets used to create a video project

        Args:
            project_id: The video project ID
            generation_request: Original request data from /generate-complete endpoint
            audio_file_data: Audio file metadata

        Returns:
            True if storage was successful
        """
        try:
            # Extract data from the generation request
            text_content = generation_request.get('text', '')
            background_type = generation_request.get('background_type', 'video')
            background_video_url = generation_request.get('background_video_url', '')
            background_image_url = generation_request.get('background_image_url', '')
            background_image_timeline = generation_request.get('image_timeline', [])
            voice_id = generation_request.get('voice_id', '')
            project_title = generation_request.get('project_title', '')
            caption_settings = generation_request.get('caption_settings', {})
            video_settings = generation_request.get('video_settings', {})

            # Music settings
            background_music_id = generation_request.get('background_music_id')
            music_volume = generation_request.get('music_volume', 0.25)
            music_fade_in = generation_request.get('music_fade_in', 2.0)
            music_fade_out = generation_request.get('music_fade_out', 3.0)

            # Store main project assets
            assets_data = {
                "original_text_content": text_content,
                "processed_text_content": text_content,  # For now, same as original
                "text_source": "custom",  # Could be 'reddit', 'custom', 'upload'
                "custom_instructions": generation_request.get('custom_instructions'),
                "output_language": "English",

                # Audio settings
                "audio_file_id": str(audio_file_data.get('id')) if audio_file_data else None,
                "audio_gcs_path": audio_file_data.get('gcs_path') if audio_file_data else None,
                "audio_signed_url": audio_file_data.get('url') if audio_file_data else None,
                "audio_duration_seconds": audio_file_data.get('duration') if audio_file_data else None,
                "voice_settings": {
                    "voice_id": voice_id,
                    "speed": 1.0,
                    "volume": 1.0,
                    "pitch": 0.0
                },
                "audio_settings": {
                    "sample_rate": 32000,
                    "bitrate": 128000,
                    "format": "mp3",
                    "channel": 1
                },

                # Caption settings
                "caption_settings": caption_settings,

                # Music settings
                "background_music_id": background_music_id,
                "music_settings": {
                    "volume": music_volume,
                    "fade_in": music_fade_in,
                    "fade_out": music_fade_out
                }
            }

            # Store assets in database
            if self.supabase:
                result = self.supabase.table("video_project_assets").upsert({
                    "project_id": str(project_id),
                    **assets_data
                }).execute()

                if not result.data:
                    logger.error(f"Failed to store assets for project {project_id}")
                    return False


            logger.info('🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀')
            logger.info(generation_request)
            # Store background assets
            await self._store_background_assets(project_id, background_type, generation_request)

            # Store processing settings
            await self._store_processing_settings(project_id, caption_settings, video_settings)

            logger.info(f"Successfully stored assets for project {project_id}")
            return True

        except Exception as e:
            logger.error(f"Error storing project assets: {str(e)}")
            return False

    async def _store_background_assets(
        self,
        project_id: UUID,
        background_type: str,
        request_data: Dict[str, Any]
    ):
        """Store background assets (videos, images, timelines) using upsert pattern"""
        try:
            backgrounds = []

            if background_type == 'video':
                backgrounds.append({
                    "background_type": "video",
                    "video_url": request_data.get('background_video_url'),
                    "sort_order": 0
                })

            elif background_type == 'image':
                backgrounds.append({
                    "background_type": "image",
                    "image_url": request_data.get('background_image_url'),
                    "sort_order": 0
                })

            elif background_type == 'image_timeline':
                image_timeline = request_data.get('image_timeline', [])
                logger.info('🚀 Processing image_timeline backgrounds')
                logger.info(image_timeline)

                # Fetch existing backgrounds to preserve IDs and data
                existing_bgs_by_sort = {}
                existing_ids = set()
                if self.supabase:
                    try:
                        existing_result = self.supabase.table("video_project_backgrounds").select(
                            "id, sort_order, description, prompt"
                        ).eq("project_id", str(project_id)).eq(
                            "background_type", "image_timeline"
                        ).execute()

                        # Map by sort_order for matching
                        if existing_result.data:
                            for bg in existing_result.data:
                                sort_order = bg['sort_order']
                                existing_bgs_by_sort[sort_order] = {
                                    'id': bg['id'],
                                    'description': bg.get('description'),
                                    'prompt': bg.get('prompt')
                                }
                                existing_ids.add(bg['id'])
                            logger.info(f"📝 Found {len(existing_bgs_by_sort)} existing backgrounds to preserve")
                    except Exception as e:
                        logger.warning(f"Failed to fetch existing backgrounds: {e}")

                # Track which sort_orders we're keeping
                new_sort_orders = set()

                for i, segment in enumerate(image_timeline):
                    start_time = segment.get('start_time', 0)
                    end_time = segment.get('end_time', 0)

                    # Skip segments with invalid time ranges (violates DB constraint: end_time > start_time)
                    if end_time <= start_time:
                        logger.warning(f"⚠️ Skipping segment {i} with invalid time range: start={start_time}, end={end_time}")
                        continue

                    new_sort_orders.add(i)

                    bg_data = {
                        "project_id": str(project_id),
                        "background_type": "image_timeline",
                        "image_id": segment.get('image_id'),
                        "start_time": start_time,
                        "end_time": end_time,
                        "transition_type": segment.get('transition_type', 'cut'),
                        "transition_duration": segment.get('transition_duration', 0),
                        "camera_movement": segment.get('camera_movement', 'static'),
                        "greenscreen_effect": self._extract_greenscreen_effect_name(segment.get('greenscreen_effect')),
                        "sort_order": i
                    }

                    # Preserve ID if this sort_order existed before (enables upsert)
                    if i in existing_bgs_by_sort:
                        bg_data["id"] = existing_bgs_by_sort[i]['id']
                        logger.info(f"🔄 Reusing existing ID for segment {i}: {bg_data['id']}")

                    # Handle description: use provided value or preserve existing
                    if 'description' in segment and segment['description']:
                        bg_data["description"] = segment['description']
                    elif i in existing_bgs_by_sort and existing_bgs_by_sort[i].get('description'):
                        bg_data["description"] = existing_bgs_by_sort[i]['description']
                        logger.info(f"✅ Preserved description for segment {i}")
                    else:
                        bg_data["description"] = ''

                    # Handle prompt: use provided value or preserve existing
                    if 'prompt' in segment and segment['prompt']:
                        bg_data["prompt"] = segment['prompt']
                    elif i in existing_bgs_by_sort and existing_bgs_by_sort[i].get('prompt'):
                        bg_data["prompt"] = existing_bgs_by_sort[i]['prompt']
                        logger.info(f"✅ Preserved prompt for segment {i}")
                    else:
                        bg_data["prompt"] = ''

                    backgrounds.append(bg_data)

                # Delete backgrounds that are no longer in the timeline
                sort_orders_to_delete = set(existing_bgs_by_sort.keys()) - new_sort_orders
                if sort_orders_to_delete and self.supabase:
                    ids_to_delete = [existing_bgs_by_sort[sort_order]['id'] for sort_order in sort_orders_to_delete]
                    for id_to_delete in ids_to_delete:
                        self.supabase.table("video_project_backgrounds").delete().eq("id", id_to_delete).execute()
                    logger.info(f"🗑️ Deleted {len(ids_to_delete)} removed backgrounds")

            # Upsert backgrounds (update if ID exists, insert if new)
            if self.supabase and backgrounds:
                # Add project_id to non-timeline backgrounds
                if background_type != 'image_timeline':
                    for bg in backgrounds:
                        bg["project_id"] = str(project_id)

                logger.info(f"💾 Upserting {len(backgrounds)} backgrounds for project {project_id}")

                # Use upsert to update existing records or insert new ones
                result = self.supabase.table("video_project_backgrounds").upsert(
                    backgrounds,
                    on_conflict="id"  # Use ID as conflict column (updates if exists, inserts if not)
                ).execute()

                if result.data:
                    logger.info(f"✅ Successfully upserted {len(result.data)} backgrounds")
                else:
                    logger.warning("⚠️ Upsert completed but no data returned")

        except Exception as e:
            logger.error(f"Error storing background assets: {str(e)}")

    async def _store_processing_settings(
        self,
        project_id: UUID,
        caption_settings: Dict[str, Any],
        video_settings: Dict[str, Any]
    ):
        """Store processing settings"""
        try:
            settings_data = {
                "project_id": str(project_id),

                # Video settings
                "resolution": video_settings.get('resolution', '1080x1920'),
                "aspect_ratio": video_settings.get('aspect_ratio', '9:16'),
                "fps": 30,
                "video_codec": "libx264",
                "audio_codec": "aac",
                "quality_level": "medium",
                "processing_method": "cloud",

                # Caption settings
                "caption_position": caption_settings.get('position', 'middle'),
                "font_family": caption_settings.get('font_family', 'Luckiest Guy'),
                "font_size": caption_settings.get('font_size', 72),
                "font_file_path": caption_settings.get('font_file_path'),
                "highlight_color": caption_settings.get('highlight_color', '&H00FFFF&'),
                "default_color": caption_settings.get('default_color', '&HFFFFFF&'),
                "subtitle_style": caption_settings.get('subtitle_style', 'karaoke'),

                # Additional options
                "additional_options": {
                    "original_caption_settings": caption_settings,
                    "original_video_settings": video_settings
                }
            }

            if self.supabase:
                result = self.supabase.table("video_project_processing_settings").upsert(settings_data).execute()

        except Exception as e:
            logger.error(f"Error storing processing settings: {str(e)}")

    async def get_project_details(self, project_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get complete project details including all assets and settings

        Args:
            project_id: The video project ID

        Returns:
            Complete project data or None if not found
        """
        try:
            if not self.supabase:
                logger.warning("Supabase client not available")
                return None

            # Get main project
            project_result = self.supabase.table("video_projects").select("*").eq("id", str(project_id)).execute()
            
            if not project_result.data or len(project_result.data) == 0:
                logger.warning(f"No project found with id {project_id}")
                return None

            project = project_result.data[0]
            logger.info(f"Found project: {project.get('title', 'No title')}")

            # Get assets - handle case where table doesn't exist
            assets = {}
            try:
                assets_result = self.supabase.table("video_project_assets").select("*").eq("project_id", str(project_id)).execute()
                assets = assets_result.data[0] if assets_result.data else {}
                logger.info(f"Found assets: {bool(assets)}")
            except Exception as e:
                logger.warning(f"Could not get assets (table might not exist): {str(e)}")

            # Get backgrounds - handle case where table doesn't exist
            backgrounds = []
            try:
                backgrounds_result = self.supabase.table("video_project_backgrounds").select("*").eq("project_id", str(project_id)).order("sort_order").execute()
                backgrounds = backgrounds_result.data or []
                logger.info(f"Found {len(backgrounds)} backgrounds")
            except Exception as e:
                logger.warning(f"Could not get backgrounds (table might not exist): {str(e)}")

            # Get processing settings - handle case where table doesn't exist
            settings = {}
            try:
                settings_result = self.supabase.table("video_project_processing_settings").select("*").eq("project_id", str(project_id)).execute()
                settings = settings_result.data[0] if settings_result.data else {}
                logger.info(f"Found settings: {bool(settings)}")
            except Exception as e:
                logger.warning(f"Could not get processing settings (table might not exist): {str(e)}")

            # Get edit history - handle case where table doesn't exist
            history = []
            try:
                history_result = self.supabase.table("video_project_edit_history").select("*").eq("project_id", str(project_id)).order("edited_at", desc=True).limit(10).execute()
                history = history_result.data or []
                logger.info(f"Found {len(history)} history entries")
            except Exception as e:
                logger.warning(f"Could not get edit history (table might not exist): {str(e)}")

            # Get timeline segments with proper formatting
            timeline_segments = []
            try:
                timeline_result = self.supabase.table("video_project_backgrounds").select("*").eq("project_id", str(project_id)).eq("background_type", "image_timeline").order("sort_order").execute()

                raw_segments = timeline_result.data or []
                logger.info(f"🎬 DEBUG: Found {len(raw_segments)} raw timeline segments")
                if raw_segments:
                    logger.info(f"🎬 DEBUG: First segment raw data: {raw_segments[0]}")

                from services.gcs_service import GCSService
                gcs_service = GCSService()

                # Recover legacy/broken local rows where the scene kept its prompt
                # but lost the generated_images foreign key.
                for segment in raw_segments:
                    if segment.get('image_id') or not segment.get('prompt'):
                        continue

                    try:
                        match_query = self.supabase.table("generated_images").select("""
                            id,
                            gcs_signed_url,
                            gcs_path,
                            width,
                            height
                        """).like("prompt", f"{segment['prompt']}%")

                        if project.get("user_id"):
                            match_query = match_query.eq("user_id", project["user_id"])

                        match_result = match_query.order("created_at").limit(1).execute()
                        if not match_result.data:
                            continue

                        recovered_image = match_result.data[0]
                        recovered_image_id = recovered_image.get("id")
                        if not recovered_image_id:
                            continue

                        segment["image_id"] = recovered_image_id
                        segment["image_width"] = segment.get("image_width") or recovered_image.get("width")
                        segment["image_height"] = segment.get("image_height") or recovered_image.get("height")

                        self.supabase.table("video_project_backgrounds").update({
                            "image_id": recovered_image_id,
                            "image_width": segment.get("image_width"),
                            "image_height": segment.get("image_height"),
                        }).eq("id", segment["id"]).execute()

                        logger.info(
                            "Recovered image link for timeline segment %s -> %s",
                            segment.get("id"),
                            recovered_image_id,
                        )
                    except Exception as recovery_error:
                        logger.warning(
                            "Could not recover image link for segment %s: %s",
                            segment.get("id"),
                            recovery_error,
                        )

                # OPTIMIZATION: Batch fetch all images at once instead of N+1 queries
                # Step 1: Collect all unique image_ids
                image_ids = [seg.get('image_id') for seg in raw_segments if seg.get('image_id')]
                unique_image_ids = list(set(image_ids))

                # Step 2: Batch fetch from generated_images
                generated_images_map = {}

                if unique_image_ids:
                    logger.info(f"🚀 Batch fetching {len(unique_image_ids)} images from generated_images")

                    # Batch query generated_images
                    generated_images_result = self.supabase.table("generated_images").select("""
                        id,
                        gcs_signed_url,
                        gcs_path,
                        width,
                        height
                    """).in_("id", unique_image_ids).execute()

                    if generated_images_result.data:
                        generated_images_map = {img['id']: img for img in generated_images_result.data}
                        logger.info(f"✅ Found {len(generated_images_map)} generated images")

                # Format segments for frontend consumption
                for segment_data in raw_segments:
                    # Extract transition settings from JSONB
                    transition_settings = segment_data.get('transition_settings', {})
                    if isinstance(transition_settings, str):
                        import json
                        try:
                            transition_settings = json.loads(transition_settings)
                        except:
                            transition_settings = {}
                    elif not isinstance(transition_settings, dict):
                        transition_settings = {}

                    # Get image info from pre-fetched maps (no queries!)
                    image_info = {}
                    image_id = segment_data.get('image_id')
                    if image_id:
                        try:
                            # Check generated_images map
                            if image_id in generated_images_map:
                                img = generated_images_map[image_id]
                                image_url = img.get('gcs_signed_url')

                                # Check if URL is expired or missing by parsing the URL
                                needs_refresh = False
                                if not image_url:
                                    needs_refresh = True
                                    logger.info(f"Image {image_id} has no signed URL, generating new one")
                                elif gcs_service.is_signed_url_expired(image_url, buffer_minutes=60):
                                    needs_refresh = True
                                    logger.info(f"Image {image_id} URL expired/expiring, refreshing...")

                                # Generate new URL if needed
                                if needs_refresh and img.get('gcs_path'):
                                    try:
                                        image_url = await gcs_service.generate_signed_url(img['gcs_path'], 24)
                                        if image_url:
                                            # Update database with new URL
                                            self.supabase.table("generated_images").update({
                                                "gcs_signed_url": image_url
                                            }).eq("id", image_id).execute()
                                            logger.info(f"✅ Refreshed URL for image {image_id}")
                                    except Exception as gcs_error:
                                        logger.warning(f"Failed to generate signed URL: {gcs_error}")
                                        image_url = None

                                if image_url:
                                    image_info = {
                                        "signed_url": image_url,
                                        "width": img.get('width'),
                                        "height": img.get('height')
                                    }
                            else:
                                logger.warning(f"Image {image_id} not found in generated_images")
                        except Exception as img_error:
                            logger.warning(f"Error fetching image data for segment: {img_error}")

                    # Get transition type - prefer direct column over settings
                    transition_type = segment_data.get('transition_type') or transition_settings.get('type', 'crossfade')
                    transition_duration = segment_data.get('transition_duration') or transition_settings.get('duration', 0.5)

                    #logger.info(f"🎬 DEBUG: Segment {segment_data.get('sort_order', 0)} - transition_type from DB: '{segment_data.get('transition_type')}', from settings: '{transition_settings.get('type')}', final: '{transition_type}'")

                    # Build formatted segment object
                    formatted_segment = {
                        "id": segment_data.get('id') or segment_data.get('segment_id'),
                        "image_id": segment_data.get('image_id'),
                        "start_time": segment_data.get('start_time', 0),
                        "end_time": segment_data.get('end_time', 0),
                        "transition_type": transition_type,
                        "transition_duration": transition_duration,
                        "sort_order": segment_data.get('sort_order', 0),
                        "camera_movement": segment_data.get('camera_movement', 'static'),
                        "greenscreen_effect": segment_data.get('greenscreen_effect'),
                        "scene_description": segment_data.get("description"),
                        "prompt": segment_data.get("prompt"),
                        "animation_prompt": segment_data.get("animation_prompt"),
                        "effects": segment_data.get("effects"),
                        "image_info": image_info
                    }

                    timeline_segments.append(formatted_segment)

                # logger.info(f"🎬 DEBUG: Formatted {len(timeline_segments)} timeline segments")
                # if timeline_segments:
                #     logger.info(f"🎬 DEBUG: Timeline segments being returned to frontend:")
                #     for i, segment in enumerate(timeline_segments[:3]):  # Log first 3 segments
                #         logger.info(f"🎬 DEBUG: Segment {i}: transition_type='{segment.get('transition_type')}', duration={segment.get('transition_duration')}")
            except Exception as e:
                logger.warning(f"Could not get timeline segments: {str(e)}")
                import traceback
                logger.warning(f"Timeline segments error traceback: {traceback.format_exc()}")

            # Get text layers
            text_layers = []
            try:
                from repositories.project_scenes_repository import get_project_scenes_repository
                scenes_repo = get_project_scenes_repository()
                text_layers = await scenes_repo.get_text_layers_by_project(project_id)
                logger.info(f"Found {len(text_layers)} text layers")
            except Exception as e:
                logger.warning(f"Could not get text layers: {str(e)}")

            return {
                "project": project,
                "assets": assets,
                "backgrounds": backgrounds,
                "processing_settings": settings,
                "edit_history": history,
                "timeline_segments": timeline_segments,
                "text_layers": text_layers,
            }

        except Exception as e:
            logger.error(f"Error getting project details: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return None

    async def get_project_timeline_segments(self, project_id: UUID) -> List[Dict[str, Any]]:
        """
        Get timeline segments for a project from the timeline_segments view

        Args:
            project_id: The video project ID

        Returns:
            List of timeline segments ordered by start_time
        """
        try:
            if not self.supabase:
                logger.warning("Supabase client not available")
                return []

            timeline_result = self.supabase.table("video_project_backgrounds").select("*").eq("project_id", str(project_id)).eq("background_type", "image_timeline").order("start_time").execute()
            timeline_segments = timeline_result.data or []
            logger.info(f"Retrieved {len(timeline_segments)} timeline segments for project {project_id}")
            return timeline_segments

        except Exception as e:
            logger.error(f"Error getting timeline segments: {str(e)}")
            return []

    async def log_project_edit(
        self,
        project_id: UUID,
        user_id: UUID,
        edit_type: str,
        field_changed: str,
        old_value: Any = None,
        new_value: Any = None,
        description: str = None
    ):
        """Log an edit to the project history"""
        try:
            if not self.supabase:
                return

            edit_data = {
                "project_id": str(project_id),
                "user_id": str(user_id),
                "edit_type": edit_type,
                "field_changed": field_changed,
                "old_value": old_value,
                "new_value": new_value,
                "edit_description": description or f"Updated {field_changed}"
            }

            self.supabase.table("video_project_edit_history").insert(edit_data).execute()

            # Also update the project's last_edited_at timestamp and increment edit count
            # Get current edit count first
            current_project = self.supabase.table("video_projects").select("edit_count").eq("id", str(project_id)).execute()
            current_edit_count = 0
            if current_project.data and len(current_project.data) > 0:
                current_edit_count = current_project.data[0].get("edit_count", 0) or 0

            self.supabase.table("video_projects").update({
                "last_edited_at": datetime.now().isoformat(),
                "edit_count": current_edit_count + 1
            }).eq("id", str(project_id)).execute()

        except Exception as e:
            logger.error(f"Error logging project edit: {str(e)}")

    async def update_project_text(
        self,
        project_id: UUID,
        user_id: UUID,
        new_text: str
    ) -> bool:
        """Update the text content of a project"""
        try:
            if not self.supabase:
                return False

            # Get current text for history
            current_assets = self.supabase.table("video_project_assets").select("original_text_content").eq("project_id", str(project_id)).execute()
            old_text = current_assets.data[0].get('original_text_content', '') if current_assets.data else ''

            # Update the text
            result = self.supabase.table("video_project_assets").update({
                "original_text_content": new_text,
                "processed_text_content": new_text
            }).eq("project_id", str(project_id)).execute()

            if result.data:
                # Log the edit
                await self.log_project_edit(
                    project_id=project_id,
                    user_id=user_id,
                    edit_type="text_edit",
                    field_changed="text_content",
                    old_value=old_text,
                    new_value=new_text,
                    description="Updated text content"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Error updating project text: {str(e)}")
            return False

    async def update_project_settings(
        self,
        project_id: UUID,
        user_id: UUID,
        settings_type: str,  # 'caption' or 'video'
        new_settings: Dict[str, Any]
    ) -> bool:
        """Update processing settings for a project"""
        try:
            if not self.supabase:
                return False

            if settings_type == 'caption':
                update_data = {
                    "caption_position": new_settings.get('position'),
                    "font_family": new_settings.get('font_family'),
                    "font_size": new_settings.get('font_size'),
                    "highlight_color": new_settings.get('highlight_color'),
                    "default_color": new_settings.get('default_color'),
                    "subtitle_style": new_settings.get('subtitle_style')
                }
                # Remove None values
                update_data = {k: v for k, v in update_data.items() if v is not None}

                # Also update the caption_settings in assets
                self.supabase.table("video_project_assets").update({
                    "caption_settings": new_settings
                }).eq("project_id", str(project_id)).execute()

            elif settings_type == 'video':
                update_data = {
                    "resolution": new_settings.get('resolution'),
                    "aspect_ratio": new_settings.get('aspect_ratio'),
                    "fps": new_settings.get('fps'),
                    "quality_level": new_settings.get('quality_level')
                }
                # Remove None values
                update_data = {k: v for k, v in update_data.items() if v is not None}

            else:
                logger.error(f"Unknown settings type: {settings_type}")
                return False

            result = self.supabase.table("video_project_processing_settings").update(update_data).eq("project_id", str(project_id)).select().execute()

            if result.data:
                await self.log_project_edit(
                    project_id=project_id,
                    user_id=user_id,
                    edit_type="settings_change",
                    field_changed=f"{settings_type}_settings",
                    new_value=new_settings,
                    description=f"Updated {settings_type} settings"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Error updating project settings: {str(e)}")
            return False

    async def update_project_backgrounds(
        self,
        project_id: UUID,
        user_id: UUID,
        backgrounds: List[Dict[str, Any]]
    ) -> bool:
        """Update background assets for a project"""
        try:
            if not self.supabase:
                return False

            # Delete existing backgrounds of the same types being replaced
            # IMPORTANT: Only delete backgrounds that match the types in the new backgrounds list
            # This prevents accidentally deleting scene data (image_timeline) when updating videos
            logger("update_project_backgrounds() deleting existing backgrounds")
            background_types = set(bg.get('background_type') for bg in backgrounds if bg.get('background_type'))

            for bg_type in background_types:
                self.supabase.table("video_project_backgrounds").delete().eq(
                    "project_id", str(project_id)
                ).eq("background_type", bg_type).execute()

            # Insert new backgrounds
            for i, bg in enumerate(backgrounds):
                bg_data = {
                    "project_id": str(project_id),
                    "sort_order": i,
                    **bg
                }
                logger(f"inserting backgrounds {bg_data}")
                self.supabase.table("video_project_backgrounds").insert(bg_data).execute()

            # Log the edit
            await self.log_project_edit(
                project_id=project_id,
                user_id=user_id,
                edit_type="asset_update",
                field_changed="backgrounds",
                new_value=backgrounds,
                description=f"Updated {len(backgrounds)} background assets"
            )

            return True

        except Exception as e:
            logger.error(f"Error updating project backgrounds: {str(e)}")
            return False

    async def prepare_regeneration_request(self, project_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Prepare a request for video regeneration based on stored project assets

        Args:
            project_id: The project ID

        Returns:
            Dictionary formatted for the /generate-complete endpoint
        """
        try:
            project_details = await self.get_project_details(project_id)
            if not project_details:
                return None

            assets = project_details.get('assets', {})
            backgrounds = project_details.get('backgrounds', [])
            settings = project_details.get('processing_settings', {})

            # Get audio_file_id directly from video_projects table
            project_result = self.supabase.table("video_projects").select("audio_file_id").eq("id", str(project_id)).execute()
            audio_file_id = None
            if project_result.data and len(project_result.data) > 0:
                audio_file_id = project_result.data[0].get('audio_file_id')
                logger.info(f"Found audio_file_id from video_projects table: {audio_file_id}")
            else:
                logger.warning(f"No audio_file_id found in video_projects table for project {project_id}")

            # Reconstruct the generation request
            request_data = {
                "text": assets.get('original_text_content', ''),
                "voice_id": assets.get('voice_settings', {}).get('voice_id', ''),
                "project_title": project_details.get('project', {}).get('title', ''),
                "project_id": str(project_id),
                "existing_audio_id": audio_file_id,  # Get audio_file_id directly from video_projects table

                # Caption settings
                "caption_settings": assets.get('caption_settings', {}),

                # Video settings - convert resolution format if needed
                "video_settings": self._normalize_video_settings(settings),

                # Music settings
                "background_music_id": assets.get('background_music_id'),
                "music_volume": assets.get('music_settings', {}).get('volume', 0.25),
                "music_fade_in": assets.get('music_settings', {}).get('fade_in', 2.0),
                "music_fade_out": assets.get('music_settings', {}).get('fade_out', 3.0),
            }

            # Handle different background types
            if backgrounds:
                first_bg = backgrounds[0]
                bg_type = first_bg.get('background_type', 'video')

                if bg_type == 'video':
                    request_data.update({
                        "background_type": "video",
                        "background_video_url": first_bg.get('video_url', '')
                    })
                elif bg_type == 'image':
                    request_data.update({
                        "background_type": "image",
                        "background_image_url": first_bg.get('image_url', '')
                    })
                elif bg_type == 'image_timeline':
                    # Reconstruct image timeline - convert image_id to image_url
                    timeline = []
                    for bg in backgrounds:
                        if bg.get('background_type') == 'image_timeline':
                            image_id = bg.get('image_id')
                            image_url = None

                            if image_id:
                                # Generate signed URL for the image_id
                                try:
                                    from services.gcs_service import GCSService
                                    gcs_service = GCSService()
                                    # Image path format: images/{image_id}.{ext}
                                    image_gcs_path = f"images/{image_id}"

                                    # Find the actual image file with extension in local storage.
                                    image_blobs = list(gcs_service.bucket.list_blobs(prefix=f"images/{image_id}"))
                                    for blob in image_blobs:
                                        if blob.name.startswith(f"images/{image_id}.") or blob.name == f"images/{image_id}":
                                            image_url = await gcs_service.generate_signed_url(blob.name)
                                            logger.info(f"Generated signed URL for image {image_id}: {blob.name}")
                                            break

                                    if not image_url:
                                        logger.warning(f"No image file found for image_id: {image_id}")

                                except Exception as e:
                                    logger.error(f"Error generating signed URL for image_id {image_id}: {str(e)}")

                            timeline.append({
                                "image_url": image_url,
                                "start_time": bg.get('start_time', 0),
                                "end_time": bg.get('end_time', 0),
                                "transition_type": bg.get('transition_type', 'cut'),
                                "transition_duration": bg.get('transition_duration', 0)
                            })
                    request_data.update({
                        "background_type": "image_timeline",
                        "image_timeline": timeline
                    })

            return request_data

        except Exception as e:
            logger.error(f"Error preparing regeneration request: {str(e)}")
            return None

    def _normalize_video_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize video settings to ensure proper resolution format"""
        try:
            aspect_ratio = settings.get('aspect_ratio', '9:16')
            resolution = settings.get('resolution', '1080p')

            # If resolution is already in pixel format (e.g., '1080x1920'), keep it
            if 'x' in str(resolution):
                return {
                    "resolution": resolution,
                    "aspect_ratio": aspect_ratio
                }

            # Convert resolution from '1080p' format to pixel dimensions
            pixel_resolution = self._get_pixel_dimensions(aspect_ratio, resolution)

            return {
                "resolution": pixel_resolution,
                "aspect_ratio": aspect_ratio
            }
        except Exception as e:
            logger.error(f"Error normalizing video settings: {str(e)}")
            # Return safe defaults
            return {
                "resolution": "1080x1920",
                "aspect_ratio": "9:16"
            }

    def _get_pixel_dimensions(self, aspect_ratio: str, resolution: str) -> str:
        """Convert aspect ratio and resolution to frontend-matched pixel dimensions."""
        return get_pixel_dimensions(aspect_ratio, resolution, default_resolution="1080x1920")

    async def merge_regeneration_settings(self, base_request: Dict[str, Any], new_settings: Dict[str, Any],
                                        project_id: UUID, user_id: UUID) -> Dict[str, Any]:
        """
        Merge new settings from frontend with existing project data for regeneration

        Args:
            base_request: Base regeneration request from existing project data
            new_settings: New settings from frontend request
            project_id: Project ID
            user_id: User ID

        Returns:
            Merged regeneration request
        """
        try:
            logger.info(f"🔄 Merging regeneration settings for project {project_id}")
            logger.info(f"📋 New settings received: {new_settings}")

            # Start with base request
            merged_request = base_request.copy()

            # Update text content if provided
            if 'text' in new_settings:
                merged_request['text'] = new_settings['text']
                logger.info(f"📝 Updated text content: {len(new_settings['text'])} characters")

            # Update voice settings if provided
            if 'voice_id' in new_settings:
                merged_request['voice_id'] = new_settings['voice_id']
                logger.info(f"🎤 Updated voice ID: {new_settings['voice_id']}")

            # Update project title if provided
            if 'project_title' in new_settings:
                merged_request['project_title'] = new_settings['project_title']

            # Update video settings if provided
            if 'video_settings' in new_settings:
                # Merge with existing video settings
                existing_video_settings = merged_request.get('video_settings', {})
                new_video_settings = new_settings['video_settings']

                # Update individual fields
                if 'aspect_ratio' in new_video_settings:
                    existing_video_settings['aspect_ratio'] = new_video_settings['aspect_ratio']
                if 'resolution' in new_video_settings:
                    existing_video_settings['resolution'] = new_video_settings['resolution']

                # Normalize the video settings (convert 1080p to pixel dimensions)
                merged_request['video_settings'] = self._normalize_video_settings(existing_video_settings)
                logger.info(f"🎬 Updated video settings: {merged_request['video_settings']}")

            # Update caption settings if provided
            if 'caption_settings' in new_settings:
                existing_caption_settings = merged_request.get('caption_settings', {})
                existing_caption_settings.update(new_settings['caption_settings'])
                merged_request['caption_settings'] = existing_caption_settings
                logger.info(f"📝 Updated caption settings: {existing_caption_settings}")

            # Update background settings if provided
            if 'background_type' in new_settings:
                merged_request['background_type'] = new_settings['background_type']

                # Update background URLs based on type
                if new_settings['background_type'] == 'video' and 'background_video_url' in new_settings:
                    merged_request['background_video_url'] = new_settings['background_video_url']
                    merged_request.pop('background_image_url', None)
                    merged_request.pop('image_timeline', None)
                elif new_settings['background_type'] == 'image' and 'background_image_url' in new_settings:
                    merged_request['background_image_url'] = new_settings['background_image_url']
                    merged_request.pop('background_video_url', None)
                    merged_request.pop('image_timeline', None)
                elif new_settings['background_type'] == 'image_timeline':
                    # Handle both 'image_timeline' and 'background_image_timeline' parameter names
                    timeline_data = None
                    if 'image_timeline' in new_settings:
                        timeline_data = new_settings['image_timeline']
                    elif 'background_image_timeline' in new_settings:
                        timeline_data = new_settings['background_image_timeline']

                    # Convert image_id to image_url if needed
                    if timeline_data:
                        converted_timeline = []
                        for segment in timeline_data:
                            if 'image_id' in segment and 'image_url' not in segment:
                                # Generate signed URL for image_id
                                image_id = segment.get('image_id')
                                image_url = None

                                if image_id:
                                    try:
                                        from services.gcs_service import GCSService
                                        gcs_service = GCSService()

                                        # First, look up the gcs_path from the generated_images table
                                        from services.supabase import get_supabase_client
                                        supabase = get_supabase_client()

                                        if supabase:
                                            response = supabase.table('generated_images').select('gcs_path').eq('id', image_id).execute()

                                            if response.data and len(response.data) > 0:
                                                gcs_path = response.data[0].get('gcs_path')
                                                if gcs_path:
                                                    image_url = await gcs_service.generate_signed_url(gcs_path)
                                                    logger.info(f"Generated signed URL for image {image_id} using gcs_path: {image_url}")
                                                else:
                                                    logger.warning(f"No gcs_path found for image_id: {image_id}")
                                            else:
                                                logger.warning(f"No record found in generated_images for image_id: {image_id}")
                                        
                                        if not image_url:
                                            logger.warning(f"No image file found for image_id in merge: {image_id}")
                                    except Exception as e:
                                        logger.error(f"Error generating signed URL for image_id in merge {image_id}: {str(e)}")

                                # Create new segment with image_url
                                new_segment = segment.copy()
                                new_segment['image_url'] = image_url
                                converted_timeline.append(new_segment)
                            else:
                                # Already has image_url or no image_id
                                converted_timeline.append(segment)

                        merged_request['image_timeline'] = converted_timeline
                    else:
                        merged_request['image_timeline'] = timeline_data
                    merged_request.pop('background_video_url', None)
                    merged_request.pop('background_image_url', None)

                logger.info(f"🖼️ Updated background type: {new_settings['background_type']}")

            # Update music settings if provided
            if 'background_music_id' in new_settings:
                merged_request['background_music_id'] = new_settings['background_music_id']
            if 'music_volume' in new_settings:
                merged_request['music_volume'] = new_settings['music_volume']
            if 'music_fade_in' in new_settings:
                merged_request['music_fade_in'] = new_settings['music_fade_in']
            if 'music_fade_out' in new_settings:
                merged_request['music_fade_out'] = new_settings['music_fade_out']

            # Log the changes that will be applied
            await self.log_project_edit(
                project_id=project_id,
                user_id=user_id,
                edit_type="regeneration_with_updates",
                field_changed="multiple_settings",
                description=f"Regenerating with updated settings: {', '.join(new_settings.keys())}"
            )

            logger.info(f"✅ Successfully merged regeneration settings")
            return merged_request

        except Exception as e:
            logger.error(f"❌ Error merging regeneration settings: {str(e)}")
            # Return base request as fallback
            return base_request


# Global instance
_project_assets_service = None

def get_project_assets_service() -> ProjectAssetsService:
    """Get or create project assets service instance"""
    global _project_assets_service
    if _project_assets_service is None:
        _project_assets_service = ProjectAssetsService()
    return _project_assets_service
