"""
Repository for project scenes in Supabase
Handles CRUD operations for AI-generated scene data
Now uses video_project_backgrounds table for consolidated storage
"""

from typing import List, Dict
from uuid import UUID
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

class ProjectScenesRepository:
    """Repository for managing project scenes in Supabase (uses video_project_backgrounds)"""

    def __init__(self, supabase_client):
        self.supabase = supabase_client.supabase
        self.table_name = "video_project_backgrounds"

    async def save_scenes(self, project_id: UUID, scenes: List[Dict]) -> bool:
        """
        Save scenes for a project using upsert to preserve scene IDs.
        Scenes with IDs are updated, scenes without IDs are inserted with new IDs.
        Scenes that exist in DB but not in the new list are deleted.

        Args:
            project_id: UUID of the project
            scenes: List of scene dictionaries

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get existing scene IDs for this project
            existing_result = self.supabase.table(self.table_name).select("id").eq(
                "project_id", str(project_id)
            ).eq("background_type", "image_timeline").execute()
            existing_ids = {row["id"] for row in (existing_result.data or [])}

            # Track which IDs we're keeping
            new_ids = set()

            # Prepare scenes for upsert
            scenes_to_upsert = []
            for idx, scene in enumerate(scenes):
                # Map to video_project_backgrounds schema
                scene_data = {
                    "project_id": str(project_id),
                    "background_type": "image_timeline",  # Scenes form a timeline
                    "sort_order": scene.get("scene_index", idx),  # Use scene_index or fallback to idx
                    "description": scene.get("description", ""),
                    "prompt": scene.get("prompt", ""),
                }
                effects = {}

                # Use provided scene ID if it's a valid UUID, otherwise let DB generate one
                scene_id = scene.get("id")
                if scene_id:
                    try:
                        # Validate it's a proper UUID
                        from uuid import UUID as UUIDType
                        UUIDType(scene_id)
                        scene_data["id"] = scene_id
                        new_ids.add(scene_id)
                    except (ValueError, TypeError):
                        # Invalid UUID, let database generate one
                        logger.warning(f"Invalid scene ID '{scene_id}', will generate new one")

                # Add optional fields only if they exist
                if scene.get("start_time") is not None:
                    scene_data["start_time"] = scene.get("start_time")
                if scene.get("end_time") is not None:
                    scene_data["end_time"] = scene.get("end_time")
                if scene.get("character_ids") is not None:
                    scene_data["character_ids"] = scene.get("character_ids")
                if scene.get("scene_type") is not None:
                    effects["scene_type"] = scene.get("scene_type")
                if scene.get("scene_script") is not None:
                    effects["scene_script"] = scene.get("scene_script")
                if scene.get("layout_type") is not None:
                    effects["layout_type"] = scene.get("layout_type")
                if scene.get("target_duration") is not None:
                    effects["target_duration"] = scene.get("target_duration")
                if scene.get("dialogue_turns") is not None:
                    effects["dialogue_turns"] = scene.get("dialogue_turns")
                if scene.get("character_layout") is not None:
                    effects["character_layout"] = scene.get("character_layout")
                if scene.get("scene_audio") is not None:
                    effects["scene_audio"] = scene.get("scene_audio")

                # Handle generated_image - extract relevant fields
                if scene.get("generated_image") is not None:
                    gen_img = scene.get("generated_image")
                    if isinstance(gen_img, dict):
                        if gen_img.get("id"):
                            scene_data["image_id"] = gen_img.get("id")
                        # Note: image_url column removed - URLs fetched from generated_images table
                        if gen_img.get("width"):
                            scene_data["image_width"] = gen_img.get("width")
                        if gen_img.get("height"):
                            scene_data["image_height"] = gen_img.get("height")

                if scene.get("animation_prompt") is not None:
                    scene_data["animation_prompt"] = scene.get("animation_prompt")

                # Handle animated_video - extract relevant fields
                if scene.get("animated_video") is not None:
                    anim_vid = scene.get("animated_video")
                    if isinstance(anim_vid, dict):
                        if anim_vid.get("url"):
                            scene_data["video_url"] = anim_vid.get("url")
                        if anim_vid.get("duration"):
                            scene_data["video_duration_seconds"] = anim_vid.get("duration")

                if scene.get("camera_movement") is not None:
                    scene_data["camera_movement"] = scene.get("camera_movement")
                if scene.get("transition_type") is not None:
                    scene_data["transition_type"] = scene.get("transition_type")
                if scene.get("transition_duration") is not None:
                    scene_data["transition_duration"] = scene.get("transition_duration")
                if scene.get("greenscreen_effect") is not None:
                    scene_data["greenscreen_effect"] = scene.get("greenscreen_effect")
                if effects:
                    scene_data["effects"] = effects

                scenes_to_upsert.append(scene_data)

            # Delete scenes that are no longer in the list
            ids_to_delete = existing_ids - new_ids
            if ids_to_delete:
                for id_to_delete in ids_to_delete:
                    self.supabase.table(self.table_name).delete().eq("id", id_to_delete).execute()
                logger.info(f"Deleted {len(ids_to_delete)} removed scenes for project {project_id}")

            # Upsert all scenes (insert or update based on ID)
            if scenes_to_upsert:
                result = self.supabase.table(self.table_name).upsert(
                    scenes_to_upsert,
                    on_conflict="id"  # Use ID as the conflict column
                ).execute()

                if not result.data:
                    logger.error(f"Failed to upsert scenes for project {project_id}")
                    return False

            logger.info(f"Successfully saved {len(scenes)} scenes for project {project_id}")
            return True

        except Exception as e:
            logger.error(f"Error saving scenes for project {project_id}: {str(e)}")
            return False

    async def get_scenes_by_project(self, project_id: UUID) -> List[Dict]:
        """
        Get all scenes for a project, ordered by sort_order
        Maps video_project_backgrounds data back to scene format
        Automatically refreshes expired signed URLs

        Args:
            project_id: UUID of the project

        Returns:
            List[Dict]: List of scene dictionaries
        """
        try:
            result = self.supabase.table(self.table_name).select("*").eq(
                "project_id", str(project_id)
            ).eq("background_type", "image_timeline").order("sort_order").execute()

            backgrounds = result.data or []

            # Initialize GCS service for URL refresh
            from services.gcs_service import GCSService
            gcs_service = GCSService()

            # Map video_project_backgrounds fields back to scene format
            scenes = []
            for bg in backgrounds:
                scene = {
                    "id": bg.get("id"),  # Return scene UUID for stable references
                    "scene_index": bg.get("sort_order", 0),
                    "description": bg.get("description", ""),
                    "prompt": bg.get("prompt", ""),
                    "start_time": bg.get("start_time"),
                    "end_time": bg.get("end_time"),
                    "character_ids": bg.get("character_ids"),
                    "animation_prompt": bg.get("animation_prompt"),
                    "camera_movement": bg.get("camera_movement"),
                    "transition_type": bg.get("transition_type"),
                    "transition_duration": bg.get("transition_duration"),
                    "greenscreen_effect": bg.get("greenscreen_effect"),
                }
                effects = bg.get("effects") or {}
                if effects:
                    scene["scene_type"] = effects.get("scene_type")
                    scene["scene_script"] = effects.get("scene_script")
                    scene["layout_type"] = effects.get("layout_type")
                    scene["target_duration"] = effects.get("target_duration")
                    scene["dialogue_turns"] = effects.get("dialogue_turns") or []
                    scene["character_layout"] = effects.get("character_layout") or []
                    scene["scene_audio"] = effects.get("scene_audio")

                if not bg.get("image_id") and bg.get("prompt"):
                    try:
                        match_query = self.supabase.table("generated_images").select(
                            "id,gcs_path,gcs_signed_url,width,height"
                        ).like("prompt", f"{bg['prompt']}%")

                        match_result = match_query.order("created_at").limit(1).execute()
                        if match_result.data:
                            recovered_image = match_result.data[0]
                            recovered_image_id = recovered_image.get("id")
                            if recovered_image_id:
                                bg["image_id"] = recovered_image_id
                                bg["image_width"] = bg.get("image_width") or recovered_image.get("width")
                                bg["image_height"] = bg.get("image_height") or recovered_image.get("height")
                                self.supabase.table(self.table_name).update({
                                    "image_id": recovered_image_id,
                                    "image_width": bg.get("image_width"),
                                    "image_height": bg.get("image_height"),
                                }).eq("id", bg["id"]).execute()
                                logger.info(
                                    "Recovered image link for scene %s -> %s",
                                    bg.get("id"),
                                    recovered_image_id,
                                )
                    except Exception as recovery_error:
                        logger.warning(
                            "Could not recover image link for scene %s: %s",
                            bg.get("id"),
                            recovery_error,
                        )

                # Map image fields back to generated_image object
                if bg.get("image_id") or bg.get("image_url"):
                    image_url = bg.get("image_url")
                    scene_id = bg.get("id")
                    image_id = bg.get("image_id")

                    logger.info(f"📸 Checking scene {bg.get('sort_order')} (ID: {scene_id}) - Image ID: {image_id}")

                    # Check if URL is missing or expired
                    needs_refresh = False
                    if not image_url:
                        logger.info(f"   ⚠️ No image_url found, will fetch from generated_images table")
                        needs_refresh = True
                    else:
                        logger.info(f"   Checking URL expiration...")
                        is_expired = gcs_service.is_signed_url_expired(image_url, buffer_minutes=60)
                        if is_expired:
                            logger.info(f"   🔄 URL is expired/expiring, attempting refresh...")
                            needs_refresh = True
                        else:
                            logger.info(f"   ✅ URL is still valid, no refresh needed")

                    # Fetch/refresh URL if needed
                    if needs_refresh and image_id:
                        try:
                            img_result = self.supabase.table('generated_images').select('gcs_path').eq(
                                'id', image_id
                            ).execute()

                            if img_result.data and len(img_result.data) > 0:
                                gcs_path = img_result.data[0].get('gcs_path')
                                logger.info(f"   Found GCS path: {gcs_path}")

                                if gcs_path:
                                    # Generate fresh signed URL
                                    logger.info(f"   Generating fresh signed URL (24h expiration)...")
                                    fresh_url = await gcs_service.generate_signed_url(gcs_path, expiration_hours=24)

                                    if fresh_url:
                                        image_url = fresh_url
                                        # Note: image_url column removed from table - URL only used in response
                                        logger.info(f"   ✅ Successfully fetched/refreshed URL for scene {scene_id}")
                                    else:
                                        logger.error(f"   ❌ Failed to generate fresh URL for {gcs_path}")
                                else:
                                    logger.warning(f"   ⚠️ No GCS path found in generated_images for image {image_id}")
                            else:
                                logger.warning(f"   ⚠️ No image record found in generated_images for ID {image_id}")
                        except Exception as refresh_error:
                            logger.error(f"   ❌ Error fetching/refreshing URL: {refresh_error}")

                    scene["generated_image"] = {
                        "id": bg.get("image_id"),
                        "url": image_url,
                        "width": bg.get("image_width"),
                        "height": bg.get("image_height"),
                        "aspect_ratio": f"{bg.get('image_width', 16)}:{bg.get('image_height', 9)}" if bg.get("image_width") and bg.get("image_height") else "16:9"
                    }

                # Map video fields back to animated_video object
                if bg.get("video_url"):
                    scene["animated_video"] = {
                        "id": bg.get("id") or bg.get("segment_id"),
                        "url": bg.get("video_url"),
                        "duration": bg.get("video_duration_seconds")
                    }

                scenes.append(scene)

            logger.info(f"Retrieved {len(scenes)} scenes for project {project_id}")
            return scenes

        except Exception as e:
            logger.error(f"Error retrieving scenes for project {project_id}: {str(e)}")
            return []

    async def save_text_layers(self, project_id: UUID, text_layers: List[Dict]) -> bool:
        """
        Save text layers for a project using upsert.
        Stored in video_project_backgrounds with background_type='text_layer'.
        Style properties are stored in the effects JSONB column.
        """
        try:
            # Get existing text layer IDs for this project
            existing_result = self.supabase.table(self.table_name).select("id").eq(
                "project_id", str(project_id)
            ).eq("background_type", "text_layer").execute()
            existing_ids = {row["id"] for row in (existing_result.data or [])}

            new_ids = set()
            rows_to_upsert = []

            for idx, tl in enumerate(text_layers):
                row = {
                    "project_id": str(project_id),
                    "background_type": "text_layer",
                    "sort_order": idx,
                    "description": tl.get("text", ""),
                    "start_time": tl.get("startTime", 0),
                    "end_time": tl.get("endTime", 5),
                    "effects": {
                        "x": tl.get("x", 50),
                        "y": tl.get("y", 50),
                        "fontSize": tl.get("fontSize", 48),
                        "fontColor": tl.get("fontColor", "#ffffff"),
                        "fontWeight": tl.get("fontWeight", "bold"),
                        "fontFamily": tl.get("fontFamily", "Arial"),
                        "backgroundColor": tl.get("backgroundColor", "transparent"),
                        "animation": tl.get("animation", "none"),
                    },
                }

                layer_id = tl.get("id")
                if layer_id:
                    try:
                        from uuid import UUID as UUIDType
                        UUIDType(layer_id)
                        row["id"] = layer_id
                        new_ids.add(layer_id)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid text layer ID '{layer_id}', generating new one")

                rows_to_upsert.append(row)

            # Delete layers that are no longer present
            ids_to_delete = existing_ids - new_ids
            if ids_to_delete:
                for id_to_delete in ids_to_delete:
                    self.supabase.table(self.table_name).delete().eq("id", id_to_delete).execute()
                logger.info(f"Deleted {len(ids_to_delete)} removed text layers for project {project_id}")

            if rows_to_upsert:
                result = self.supabase.table(self.table_name).upsert(
                    rows_to_upsert, on_conflict="id"
                ).execute()
                if not result.data:
                    logger.error(f"Failed to upsert text layers for project {project_id}")
                    return False

            logger.info(f"Successfully saved {len(text_layers)} text layers for project {project_id}")
            return True

        except Exception as e:
            logger.error(f"Error saving text layers for project {project_id}: {str(e)}")
            return False

    async def get_text_layers_by_project(self, project_id: UUID) -> List[Dict]:
        """
        Get all text layers for a project, ordered by sort_order.
        Maps video_project_backgrounds fields back to TextLayer format.
        """
        try:
            result = self.supabase.table(self.table_name).select("*").eq(
                "project_id", str(project_id)
            ).eq("background_type", "text_layer").order("sort_order").execute()

            rows = result.data or []
            text_layers = []
            for row in rows:
                effects = row.get("effects") or {}
                tl = {
                    "id": row.get("id"),
                    "text": row.get("description", ""),
                    "startTime": row.get("start_time", 0),
                    "endTime": row.get("end_time", 5),
                    "x": effects.get("x", 50),
                    "y": effects.get("y", 50),
                    "fontSize": effects.get("fontSize", 48),
                    "fontColor": effects.get("fontColor", "#ffffff"),
                    "fontWeight": effects.get("fontWeight", "bold"),
                    "fontFamily": effects.get("fontFamily", "Arial"),
                    "backgroundColor": effects.get("backgroundColor", "transparent"),
                    "animation": effects.get("animation", "none"),
                }
                text_layers.append(tl)

            logger.info(f"Retrieved {len(text_layers)} text layers for project {project_id}")
            return text_layers

        except Exception as e:
            logger.error(f"Error retrieving text layers for project {project_id}: {str(e)}")
            return []

    async def delete_scenes_by_project(self, project_id: UUID) -> bool:
        """
        Delete all scenes for a project (only image backgrounds)

        Args:
            project_id: UUID of the project

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.supabase.table(self.table_name).delete().eq(
                "project_id", str(project_id)
            ).eq("background_type", "image_timeline").execute()

            logger.info(f"Deleted scenes for project {project_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting scenes for project {project_id}: {str(e)}")
            return False

# Singleton instance
_project_scenes_repository = None

def get_project_scenes_repository():
    """Get or create repository instance"""
    global _project_scenes_repository
    if _project_scenes_repository is None:
        from db.supabase_client import SupabaseClient
        _project_scenes_repository = ProjectScenesRepository(SupabaseClient())
    return _project_scenes_repository
