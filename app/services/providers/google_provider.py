"""
Google Gemini API provider for image generation
"""

import asyncio
import base64
import logging
import mimetypes
import re
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from google import genai
from google.genai import types
from PIL import Image
from io import BytesIO
import os
import requests

logger = logging.getLogger(__name__)

GEMINI_OMNI_FLASH_MODEL = "gemini-omni-flash-preview"


class GoogleProvider:
    """Provider for Google Gemini API image generation services"""

    def __init__(self):
        """Initialize Google provider"""
        self.google_api_key = os.getenv("GOOGLE_GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.client = None
        self._initialize_client()
        self.supported_models = [
            'gemini-2.5-flash-image',
            'gemini-3.1-flash-image-preview',
            'gemini-imagen-3.0-generate-001',
            GEMINI_OMNI_FLASH_MODEL,
        ]

    @staticmethod
    def _with_google_genai_api(callable_obj):
        """
        Force the Google GenAI SDK onto the API-key backend for image generation.
        This prevents process-level Vertex toggles from affecting PPT image requests.
        """
        prev_use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")
        try:
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"
            return callable_obj()
        finally:
            if prev_use_vertex is None:
                os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
            else:
                os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = prev_use_vertex

    def _initialize_client(self):
        """Initialize Google Gemini client"""
        try:
            if not self.google_api_key:
                logger.warning("GOOGLE_GEMINI_API_KEY/GOOGLE_API_KEY not found. Google provider will not be available.")
                return

            self.client = self._with_google_genai_api(
                lambda: genai.Client(api_key=self.google_api_key)
            )
            logger.info("✅ Google Gemini client initialized successfully")

        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Gemini: {str(e)}")
            self.client = None

    def is_available(self) -> bool:
        """Check if Google provider is available"""
        return self.client is not None

    @staticmethod
    def _normalize_veo_resolution(resolution: str) -> str:
        if resolution == "1080p":
            return "1080p"
        if resolution == "4k":
            return "4k"
        return "720p"

    @staticmethod
    def _normalize_veo_duration(duration: Optional[int], resolution: str, has_last_frame: bool = False) -> int:
        if resolution in {"1080p", "4k"} or has_last_frame:
            return 8
        if duration in {4, 6, 8}:
            return int(duration)
        return 4

    @staticmethod
    def _download_image_for_veo(image_url: str) -> types.Image:
        response = requests.get(image_url, timeout=60)
        response.raise_for_status()
        content_type = response.headers.get("content-type") or mimetypes.guess_type(image_url.split("?")[0])[0]
        if not content_type or not content_type.startswith("image/"):
            content_type = "image/png"
        return types.Image(image_bytes=response.content, mime_type=content_type)

    @staticmethod
    def _normalize_omni_aspect_ratio(aspect_ratio: str) -> str:
        return "9:16" if aspect_ratio == "9:16" else "16:9"

    @staticmethod
    def _download_image_for_omni(image_url: str) -> Dict[str, str]:
        response = requests.get(image_url, timeout=60)
        response.raise_for_status()
        content_type = response.headers.get("content-type") or mimetypes.guess_type(image_url.split("?")[0])[0]
        if not content_type or not content_type.startswith("image/"):
            content_type = "image/png"
        return {
            "type": "image",
            "data": base64.b64encode(response.content).decode("utf-8"),
            "mime_type": content_type,
        }

    @staticmethod
    def _decode_omni_video_data(video_data: Any) -> bytes:
        if isinstance(video_data, bytes):
            return video_data
        if isinstance(video_data, str):
            return base64.b64decode(video_data)
        raise ValueError("Gemini Omni returned video data in an unsupported format")

    @staticmethod
    def _omni_state_name(state: Any) -> str:
        if isinstance(state, dict):
            return str(state.get("name") or state.get("state") or "").upper()
        return str(state or "").upper()

    @staticmethod
    def _omni_file_id_from_uri(uri: str) -> Optional[str]:
        match = re.search(r"/files/([^/:?]+)", uri) or re.search(r"^files/([^/:?]+)", uri)
        return match.group(1) if match else None

    @classmethod
    def _iter_omni_video_parts(cls, interaction: Any):
        if isinstance(interaction, dict):
            output_video = interaction.get("output_video") or interaction.get("outputVideo")
            if isinstance(output_video, dict):
                yield output_video
            for step in interaction.get("steps", []) or []:
                for part in step.get("content", []) or []:
                    if part.get("type") == "video":
                        yield part
            return

        output_video = getattr(interaction, "output_video", None)
        if output_video is not None:
            yield output_video

        steps = getattr(interaction, "steps", None) or []
        for step in steps:
            content = getattr(step, "content", None)
            if content is None and isinstance(step, dict):
                content = step.get("content")
            for part in content or []:
                part_type = getattr(part, "type", None)
                if isinstance(part, dict):
                    part_type = part.get("type")
                if part_type == "video":
                    yield part

    @classmethod
    def _extract_omni_video_bytes(cls, interaction: Any) -> bytes:
        """Extract inline base64 video bytes from SDK convenience fields or raw steps."""
        for part in cls._iter_omni_video_parts(interaction):
            data = part.get("data") if isinstance(part, dict) else getattr(part, "data", None)
            if data:
                return cls._decode_omni_video_data(data)
        raise Exception("Gemini Omni video generation completed without inline video data")

    @classmethod
    def _extract_omni_video_uri(cls, interaction: Any) -> Optional[str]:
        for part in cls._iter_omni_video_parts(interaction):
            uri = part.get("uri") if isinstance(part, dict) else getattr(part, "uri", None)
            if uri:
                return str(uri)
        return None

    def _download_omni_video_uri(self, uri: str, max_poll_attempts: int = 120) -> bytes:
        file_id = self._omni_file_id_from_uri(uri)
        headers = {"x-goog-api-key": self.google_api_key or ""}

        if file_id:
            for _ in range(max_poll_attempts):
                status_response = requests.get(
                    f"https://generativelanguage.googleapis.com/v1beta/files/{file_id}",
                    headers=headers,
                    timeout=60,
                )
                if status_response.status_code >= 400:
                    raise Exception(
                        f"Gemini Omni file status request failed ({status_response.status_code}): "
                        f"{status_response.text[:500]}"
                    )
                status_json = status_response.json()
                state = self._omni_state_name(status_json.get("state"))
                if state == "ACTIVE":
                    break
                if state == "FAILED":
                    raise Exception("Gemini Omni generated file processing failed")
                time.sleep(5)
            else:
                raise TimeoutError("Gemini Omni generated file did not become ACTIVE in time")

        download_url = uri
        if not download_url.startswith("http"):
            if not file_id:
                raise Exception(f"Unsupported Gemini Omni video URI: {uri}")
            download_url = f"https://generativelanguage.googleapis.com/v1beta/files/{file_id}:download?alt=media"

        response = requests.get(download_url, headers=headers, timeout=600)
        if response.status_code >= 400:
            raise Exception(f"Gemini Omni video download failed ({response.status_code}): {response.text[:500]}")
        return response.content

    def _create_omni_interaction_rest(
        self,
        *,
        model: str,
        interaction_input: Any,
        aspect_ratio: str,
        task: str,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "input": interaction_input,
            "response_format": {
                "type": "video",
                "aspect_ratio": aspect_ratio,
                "delivery": "uri",
            },
        }
        if task != "text_to_video":
            payload["generation_config"] = {
                "video_config": {
                    "task": task,
                }
            }

        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={
                "x-goog-api-key": self.google_api_key or "",
                "Content-Type": "application/json",
                "Api-Revision": "2026-05-20",
            },
            json=payload,
            timeout=600,
        )
        if response.status_code >= 400:
            raise Exception(f"Gemini Omni REST request failed ({response.status_code}): {response.text[:500]}")
        return response.json()

    async def generate_omni_video(
        self,
        prompt: str,
        model: str = GEMINI_OMNI_FLASH_MODEL,
        aspect_ratio: str = "16:9",
        image_url: Optional[str] = None,
        task: str = "text_to_video",
    ) -> Dict[str, Any]:
        """Generate a video with Gemini Omni Flash using the Interactions API."""
        if not self.is_available():
            raise Exception("Google provider not available")

        start_time = datetime.now()
        normalized_aspect_ratio = self._normalize_omni_aspect_ratio(aspect_ratio)
        normalized_task = task if task in {"text_to_video", "image_to_video", "reference_to_video", "edit"} else "text_to_video"

        try:
            logger.info(
                "Starting Gemini Omni video generation: model=%s task=%s aspect_ratio=%s",
                model,
                normalized_task,
                normalized_aspect_ratio,
            )

            loop = asyncio.get_event_loop()

            if image_url:
                image_part = await loop.run_in_executor(None, lambda: self._download_image_for_omni(image_url))
                interaction_input: Any = [
                    image_part,
                    {"type": "text", "text": prompt},
                ]
                normalized_task = "image_to_video"
            else:
                interaction_input = prompt
                normalized_task = "text_to_video"

            # Keep Omni isolated on REST with the new schema. This avoids changing
            # existing Gemini image/Veo/content paths while remaining compatible with
            # deployments that have not restarted onto google-genai >= 2.0.0 yet.
            interaction = await loop.run_in_executor(
                None,
                lambda: self._create_omni_interaction_rest(
                    model=model,
                    interaction_input=interaction_input,
                    aspect_ratio=normalized_aspect_ratio,
                    task=normalized_task,
                )
            )

            try:
                video_bytes = self._extract_omni_video_bytes(interaction)
            except Exception:
                video_uri = self._extract_omni_video_uri(interaction)
                if not video_uri:
                    raise
                video_bytes = await loop.run_in_executor(None, lambda: self._download_omni_video_uri(video_uri))

            generation_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            return {
                "status": "completed",
                "video_bytes": video_bytes,
                "generation_time_ms": generation_time_ms,
                "model": model,
                "duration": None,
                "input_params": {
                    "prompt": prompt,
                    "aspect_ratio": normalized_aspect_ratio,
                    "task": normalized_task,
                    "has_reference_image": bool(image_url),
                }
            }
        except Exception as e:
            logger.error(f"❌ Gemini Omni video generation failed: {str(e)}")
            raise Exception(f"Gemini Omni video generation failed: {str(e)}")

    async def animate_image(
        self,
        image_url: str,
        prompt: str,
        model: str = "veo-3.1-fast-generate-preview",
        resolution: str = "720p",
        aspect_ratio: str = "16:9",
        last_image: Optional[str] = None,
        duration: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate an image-to-video animation using Google Veo or Gemini Omni."""
        if not self.is_available():
            raise Exception("Google provider not available")

        if model == GEMINI_OMNI_FLASH_MODEL:
            return await self.generate_omni_video(
                prompt=prompt,
                model=model,
                aspect_ratio=aspect_ratio,
                image_url=image_url,
                task="image_to_video",
            )

        start_time = datetime.now()
        normalized_resolution = self._normalize_veo_resolution(resolution)
        normalized_aspect_ratio = "9:16" if aspect_ratio == "9:16" else "16:9"
        normalized_duration = self._normalize_veo_duration(duration, normalized_resolution, bool(last_image))

        try:
            logger.info(f"Starting Veo video generation with model: {model}")
            logger.info(f"Prompt: {prompt[:100]}...")
            logger.info(
                "Veo config: resolution=%s, aspect_ratio=%s, duration=%s",
                normalized_resolution,
                normalized_aspect_ratio,
                normalized_duration,
            )

            loop = asyncio.get_event_loop()
            first_frame = await loop.run_in_executor(None, lambda: self._download_image_for_veo(image_url))
            last_frame = None
            if last_image:
                last_frame = await loop.run_in_executor(None, lambda: self._download_image_for_veo(last_image))

            config_kwargs = {
                "number_of_videos": 1,
                "duration_seconds": normalized_duration,
                "aspect_ratio": normalized_aspect_ratio,
                "resolution": normalized_resolution,
                "person_generation": kwargs.get("person_generation", "allow_adult"),
            }
            if kwargs.get("negative_prompt"):
                config_kwargs["negative_prompt"] = kwargs["negative_prompt"]
            if last_frame is not None:
                config_kwargs["last_frame"] = last_frame

            config = types.GenerateVideosConfig(**config_kwargs)

            operation = await loop.run_in_executor(
                None,
                lambda: self._with_google_genai_api(
                    lambda: self.client.models.generate_videos(
                        model=model,
                        prompt=prompt,
                        image=first_frame,
                        config=config,
                    )
                )
            )

            max_attempts = kwargs.get("max_poll_attempts", 45)
            attempts = 0
            while not operation.done and attempts < max_attempts:
                attempts += 1
                await asyncio.sleep(10)
                operation = await loop.run_in_executor(
                    None,
                    lambda: self._with_google_genai_api(lambda: self.client.operations.get(operation))
                )

            if not operation.done:
                raise TimeoutError("Veo video generation timed out")
            if operation.error:
                raise Exception(f"Veo video generation failed: {operation.error}")

            video_response = operation.response or operation.result
            generated_videos = getattr(video_response, "generated_videos", None) or []
            if not generated_videos:
                raise Exception("Veo video generation completed without a video")

            generated_video = generated_videos[0]
            video = generated_video.video
            video_bytes = await loop.run_in_executor(
                None,
                lambda: self._with_google_genai_api(lambda: self.client.files.download(file=video))
            )

            if not video_bytes and getattr(video, "video_bytes", None):
                video_bytes = video.video_bytes
            if not video_bytes:
                raise Exception("Failed to download generated Veo video bytes")

            generation_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            return {
                "status": "completed",
                "video_bytes": video_bytes,
                "generation_time_ms": generation_time_ms,
                "model": model,
                "duration": normalized_duration,
                "input_params": {
                    "prompt": prompt,
                    "resolution": normalized_resolution,
                    "aspect_ratio": normalized_aspect_ratio,
                    "duration_seconds": normalized_duration,
                    "has_last_frame": bool(last_frame),
                }
            }
        except Exception as e:
            logger.error(f"❌ Veo video generation failed: {str(e)}")
            raise Exception(f"Veo video generation failed: {str(e)}")

    def _make_prompt_safer(self, prompt: str, retry_count: int) -> str:
        """
        Modify prompt to be more likely to pass safety filters

        Args:
            prompt: Original prompt
            retry_count: Current retry attempt (0-indexed)

        Returns:
            Modified safer prompt
        """
        # Strategy based on retry attempt
        if retry_count == 0:
            # First retry: Add artistic style descriptors
            return f"A professional, artistic illustration of {prompt}. Digital art style, suitable for general audiences."
        elif retry_count == 1:
            # Second retry: Make it more abstract/stylized
            return f"An abstract, stylized representation of {prompt}. Safe for work, professional quality."
        else:
            # Final retry: Very generic and safe
            return f"A simple, clean illustration showing {prompt}. Family-friendly, professional digital art."

    async def generate_image(
        self,
        prompt: str,
        model: str = "gemini-3.1-flash-image-preview",
        width: int = 1024,
        height: int = 1024,
        num_outputs: int = 1,
        aspect_ratio: str = "1:1",
        max_retries: int = 3,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate image using Google Gemini API with retry logic for safety filters

        Args:
            prompt: Text prompt for image generation
            model: Model to use for generation (default: gemini-3.1-flash-image-preview)
            width: Image width (used to determine aspect ratio)
            height: Image height (used to determine aspect ratio)
            num_outputs: Number of images to generate (Google API generates 1 at a time)
            aspect_ratio: Aspect ratio string (e.g., "1:1", "16:9", "9:16", "4:3", "3:4")
            max_retries: Maximum number of retry attempts for safety filter failures (default: 3)
            **kwargs: Additional model-specific parameters (including reference_images)

        Returns:
            Dict with generation result including image_data and status
        """
        if not self.is_available():
            raise Exception("Google provider not available")

        try:
            start_time = datetime.now()
            logger.info(f"Starting image generation with Google model: {model}")
            logger.info(f"Prompt: {prompt[:100]}...")

            # Extract reference images from kwargs
            reference_images = kwargs.get('reference_images', [])
            if reference_images:
                logger.info(f"📸 Using {len(reference_images)} reference image(s)")
            
            image_size = None
            if model == "gemini-3-pro-preview":
                #check image_size only for nb pro
                image_size = kwargs.get('image_size')

            # Determine aspect ratio from width/height if aspect_ratio not explicitly provided
            if aspect_ratio == "1:1" and width != height:
                if width > height:
                    ratio = width / height
                    if ratio >= 1.7:
                        aspect_ratio = "16:9"
                    elif ratio >= 1.2:
                        aspect_ratio = "4:3"
                else:
                    ratio = height / width
                    if ratio >= 1.7:
                        aspect_ratio = "9:16"
                    elif ratio >= 1.2:
                        aspect_ratio = "3:4"

            logger.info(f"Using aspect ratio: {aspect_ratio}")

            # Google Gemini generates one image at a time
            # We'll generate multiple if requested
            generated_images = []

            for i in range(num_outputs):
                logger.info(f"Generating image {i+1}/{num_outputs}")

                # Retry loop for each image
                retry_count = 0
                image_generated = False
                current_prompt = prompt
                last_error = None

                while retry_count <= max_retries and not image_generated:
                    try:
                        if retry_count > 0:
                            # Modify prompt for retry
                            current_prompt = self._make_prompt_safer(prompt, retry_count - 1)
                            logger.warning(f"🔄 Retry {retry_count}/{max_retries} with modified prompt: {current_prompt[:100]}...")
                            # Exponential backoff
                            backoff_time = 2 ** (retry_count - 1)  # 1s, 2s, 4s
                            logger.info(f"⏳ Waiting {backoff_time}s before retry...")
                            await asyncio.sleep(backoff_time)

                        # Configure generation with response modalities and aspect ratio
                        # Aspect ratio is specified in image_config
                        if image_size:
                            logger.info('...........................................')
                            config = types.GenerateContentConfig(
                            response_modalities=['IMAGE', 'TEXT'],
                            image_config=types.ImageConfig(
                                aspect_ratio=aspect_ratio,
                                image_size = image_size
                            )
                        )


                        else:
                            config = types.GenerateContentConfig(
                                response_modalities=['Image'],
                                image_config=types.ImageConfig(
                                    aspect_ratio=aspect_ratio
                                )
                            )

                        logger.info(f"Config - response_modalities: ['Image'], aspect_ratio: {aspect_ratio}")

                        # Prepare contents array with prompt and reference images
                        contents = [current_prompt]

                        # Add reference images to contents if provided
                        if reference_images:
                            for idx, ref_image_base64 in enumerate(reference_images):
                                try:
                                    # Convert URL or base64 reference image into a PIL image.
                                    if ref_image_base64.startswith('http://') or ref_image_base64.startswith('https://'):
                                        response = requests.get(ref_image_base64, timeout=30)
                                        response.raise_for_status()
                                        image_bytes = response.content
                                    elif 'base64,' in ref_image_base64:
                                        base64_data = ref_image_base64.split('base64,')[1]
                                        image_bytes = base64.b64decode(base64_data)
                                    else:
                                        base64_data = ref_image_base64
                                        image_bytes = base64.b64decode(base64_data)

                                    pil_image = Image.open(BytesIO(image_bytes))

                                    contents.append(pil_image)
                                    logger.info(f"✅ Added reference image {idx+1} to contents")
                                except Exception as e:
                                    logger.error(f"❌ Failed to process reference image {idx+1}: {str(e)}")
                                    # Continue with generation even if one reference image fails

                        # Generate image using Gemini
                        logger.info(f"....................{config}")
                        response = self._with_google_genai_api(
                            lambda: self.client.models.generate_content(
                                model=model,
                                contents=contents,
                                config=config
                            )
                        )

                        # Check if response has the expected structure
                        if not response.candidates or len(response.candidates) == 0:
                            logger.error(f"❌ No candidates in response: {response}")
                            raise Exception("No candidates returned from Google API - request may have been blocked")

                        # Check for safety filter blocking
                        if not response.candidates[0].content:
                            finish_reason = response.candidates[0].finish_reason if hasattr(response.candidates[0], 'finish_reason') else None

                            # Log the full response for debugging
                            logger.error(f"❌ No content in candidate. Response: {response}")
                            logger.error(f"❌ Candidate finish_reason: {finish_reason}")
                            logger.error(f"❌ Safety ratings: {response.candidates[0].safety_ratings if hasattr(response.candidates[0], 'safety_ratings') else 'N/A'}")

                            # Check if it's a safety filter issue that we can retry
                            if finish_reason and 'SAFETY' in str(finish_reason):
                                retry_count += 1
                                if retry_count <= max_retries:
                                    logger.warning(f"⚠️ Content blocked by safety filters. Will retry with modified prompt...")
                                    continue
                                else:
                                    raise Exception(f"Content blocked by safety filters after {max_retries} retries")
                            else:
                                raise Exception("Invalid response from Google API")

                        # Extract image data from response
                        image_data = None
                        for part in response.candidates[0].content.parts:
                            if part.inline_data is not None:
                                # Convert the image data to PIL Image
                                pil_image = Image.open(BytesIO(part.inline_data.data))

                                # Convert PIL Image to bytes
                                img_byte_arr = BytesIO()
                                pil_image.save(img_byte_arr, format='PNG')
                                img_byte_arr.seek(0)

                                image_data = img_byte_arr.read()

                                # Get actual dimensions from generated image
                                actual_width, actual_height = pil_image.size

                                generated_images.append({
                                    'image_data': image_data,
                                    'width': actual_width,
                                    'height': actual_height,
                                    'format': 'PNG'
                                })

                                logger.info(f"✅ Image {i+1} generated successfully: {actual_width}x{actual_height}")
                                image_generated = True
                                break

                        if not image_data and not image_generated:
                            raise Exception(f"No image data received from Google API for image {i+1}")

                    except Exception as e:
                        last_error = e
                        # Check if this is a retryable error
                        if 'safety filter' in str(e).lower() and retry_count < max_retries:
                            retry_count += 1
                            logger.warning(f"⚠️ Safety filter error on attempt {retry_count}. Retrying...")
                            continue
                        else:
                            # Non-retryable error or max retries exceeded
                            if retry_count >= max_retries:
                                logger.error(f"❌ Max retries ({max_retries}) exceeded for image {i+1}")
                            raise

                # If we exhausted retries without success, raise the last error
                if not image_generated and last_error:
                    raise last_error

            end_time = datetime.now()
            generation_time_ms = int((end_time - start_time).total_seconds() * 1000)

            logger.info(f"✅ Generated {len(generated_images)} image(s) in {generation_time_ms}ms")

            return {
                'status': 'completed',
                'images': generated_images,
                'generation_time_ms': generation_time_ms,
                'model': model,
                'prompt': prompt
            }

        except Exception as e:
            logger.error(f"❌ Image generation failed: {str(e)}")
            return {
                'status': 'failed',
                'error': str(e),
                'generation_time_ms': 0,
                'images': []
            }
