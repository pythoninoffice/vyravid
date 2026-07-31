"""
Replicate API provider for image generation
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import os
import replicate
from config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_REPLICATE_POLL_INTERVAL_SECONDS = 2.0
SENSITIVE_CONTENT_RETRY_ATTEMPTS = 2


class SensitiveContentError(Exception):
    """Raised when Replicate flags image generation input/output as sensitive."""

    code = "content_blocked"

    def __init__(self, message: str, attempts: int = 1):
        self.attempts = attempts
        super().__init__(message)


def is_sensitive_content_error(error: Exception | str) -> bool:
    """Detect Replicate/OpenAI sensitive-content failures from provider text."""
    text = str(error).lower()
    return (
        "flagged as sensitive" in text
        or "(e005)" in text
        or "please try again with different inputs" in text
    )


def _normalize_openai_image_aspect_ratio(aspect_ratio: str) -> str:
    if aspect_ratio == "16:9":
        return "3:2"
    if aspect_ratio == "9:16":
        return "2:3"
    return aspect_ratio


def _is_seedance_2_model(model: str) -> bool:
    normalized_model = (model or "").lower()
    return normalized_model.startswith("bytedance/seedance-2")


def _is_kling_v2_1_model(model: str) -> bool:
    return (model or "").lower() == "kwaivgi/kling-v2.1"


def _is_kling_v2_6_model(model: str) -> bool:
    return (model or "").lower() == "kwaivgi/kling-v2.6"


def _is_kling_v3_video_model(model: str) -> bool:
    return (model or "").lower() == "kwaivgi/kling-v3-video"


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


def _seedance_prompt_with_reference_media(
    prompt: str,
    *,
    include_image_reference: bool,
    include_audio_reference: bool,
) -> str:
    instructions = []
    if include_image_reference and "[Image1]" not in prompt:
        instructions.append("Use [Image1] as the first-frame and primary visual reference.")
    if include_audio_reference and "[Audio1]" not in prompt:
        instructions.append("Use [Audio1] as the reference audio for the spoken timing and delivery.")
    if not instructions:
        return prompt
    return f"{prompt}\n" + " ".join(instructions)


def _seedance_resolution(model: str, requested_resolution: Optional[str]) -> str:
    if _is_seedance_2_model(model):
        return "480p"
    return requested_resolution or "480p"

class ReplicateProvider:
    """Provider for Replicate API image generation services"""
    
    def __init__(self):
        """Initialize Replicate provider"""
        self.settings = get_settings()
        self.client = None
        self._initialize_client()
        self.models_supports_aspect_ratio = ['bytedance/seedream-4','bytedance/seedream-4.5',
                                                'minimax/image-01','prunaai/wan-2.2-image','qwen/qwen-image',
                                                "nvidia/sana-sprint-1.6b:038aee6907b53a5c148780983e39a50ce7cd0747b4e2642e78387f48cf36039a",
                                                'aisha-ai-official/anillustrious-v4:80441e2c32a55f2fcf9b77fa0a74c6c86ad7deac51eed722b9faedb253265cb4',
                                                'cjwbw/animagine-xl-3.1:6afe2e6b27dad2d6f480b59195c221884b6acc589ff4d05ff0e5fc058690fbb9'

                                            ]
    
    def _initialize_client(self):
        """Initialize Replicate client"""
        try:
            # Check if API key is available
            replicate_api_key = getattr(self.settings, 'replicate_api_key', None)
            if not replicate_api_key:
                logger.warning("REPLICATE_API_KEY not found in settings. Provider will not be available.")
                return
            
            # Set API token for replicate module
            os.environ['REPLICATE_API_TOKEN'] = replicate_api_key
            poll_interval = float(
                getattr(
                    self.settings,
                    'replicate_poll_interval_seconds',
                    DEFAULT_REPLICATE_POLL_INTERVAL_SECONDS,
                )
            )
            os.environ['REPLICATE_POLL_INTERVAL'] = str(poll_interval)
            if hasattr(replicate, 'default_client'):
                replicate.default_client.poll_interval = poll_interval
            self.client = True  # Just a flag to indicate we're ready
            logger.info("✅ Replicate API token set successfully (poll interval: %.1fs)", poll_interval)
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Replicate: {str(e)}")
            self.client = None
    
    def is_available(self) -> bool:
        """Check if Replicate provider is available"""
        return self.client is not None
    
    async def generate_image(
        self,
        prompt: str,
        model: str = "prunaai/z-image-turbo:7ea16386290ff5977c7812e66e462d7ec3954d8e007a8cd18ded3e7d41f5d7cf",
        width: int = 1024,
        height: int = 1024,
        num_outputs: int = 1,
        aspect_ratio: str = "1:1",
        negative_prompt: str = "",
        reference_images: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate image using Replicate API
        
        Args:
            prompt: Text prompt for image generation
            model: Model to use for generation
            width: Image width
            height: Image height
            num_outputs: Number of images to generate
            negative_prompt: Negative prompt to avoid certain elements
            **kwargs: Additional model-specific parameters
            
        Returns:
            Dict with generation result including prediction_id and status
        """

        logger.info('........image size:  %s x %s', width, height)
        if reference_images:
            logger.info(f'📸 Reference images received: {len(reference_images)} images')

        if not self.is_available():
            raise Exception("Replicate provider not available")
        
        try:
            logger.info(f"Starting image generation with model: {model}")
            
            
            # Prepare input parameters for models that accept aspect_ratio
            if model in self.models_supports_aspect_ratio:
                # Convert width/height to aspect ratio
                aspect_ratio = "1:1"  # default
                if width == height:
                    aspect_ratio = "1:1"
                elif width > height:
                    ratio = width / height
                    if ratio >= 1.7:
                        aspect_ratio = "16:9"
                    elif ratio >= 1.2:
                        aspect_ratio = "4:3"
                    else:
                        aspect_ratio = "1:1"
                else:  # height > width
                    ratio = height / width
                    if ratio >= 1.7:
                        aspect_ratio = "9:16"
                    elif ratio >= 1.2:
                        aspect_ratio = "3:4"
                    else:
                        aspect_ratio = "1:1"
                
                # Enhance the prompt if it's too simple (sometimes causes blank images)
                enhanced_prompt = prompt
                if len(prompt.split()) < 5:
                    enhanced_prompt = f"{prompt}, detailed, high quality, photorealistic"
                    logger.info(f"Enhanced short prompt: '{prompt}' -> '{enhanced_prompt}'")
                
                # Incorporate negative prompt into the main prompt for models without a separate negative prompt field
                if negative_prompt and negative_prompt.strip():
                    enhanced_prompt = f"{enhanced_prompt}, avoid: {negative_prompt.strip()}"
                    logger.info(f"Added negative prompt guidance: avoid {negative_prompt.strip()}")
                
                logger.info(f"Prompt: {enhanced_prompt}")

                # Use minimal parameters that match your working example exactly
                input_params = {
                    "prompt": enhanced_prompt,
                    "go_fast": True,
                    "megapixels": "1",
                    "num_outputs": num_outputs,
                    "aspect_ratio": aspect_ratio,  # Use the calculated aspect ratio
                    "width": width,
                    "height": height,
                    "output_format": "webp",
                    "output_quality": 80,
                    "num_inference_steps": 4
                }
                
                # Handle reference images for Seedream-4
                if model in ['bytedance/seedream-4','bytedance/seedream-4.5'] and reference_images:
                    # Process reference images - can be URLs, data URIs, or base64
                    image_uris = []
                    for img_data in reference_images[:10]:  # Max 10 images
                        # If it's a URL (starts with http/https), pass it directly
                        # Replicate can handle URLs
                        if img_data.startswith('http://') or img_data.startswith('https://'):
                            image_uris.append(img_data)
                            logger.info(f"Added reference image URL: {img_data[:100]}...")
                        # If it's already a data URI, use it
                        elif img_data.startswith('data:'):
                            image_uris.append(img_data)
                            logger.info(f"Added reference image data URI")
                        else:
                            # Assume it's base64 and pass as-is
                            image_uris.append(img_data)
                            logger.info(f"Added reference image base64")

                    input_params['image_input'] = image_uris
                    logger.info(f"✅ Added {len(image_uris)} reference images for Seedream-4")

                logger.info(f"Replicate image input parameters: {input_params}")
                logger.info(f"Calculated aspect ratio: {aspect_ratio} (from {width}x{height})")
            else:
                # Generic parameters for other models
                input_params = {
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "num_outputs": num_outputs,
                    **kwargs
                }

                # Handle reference images for generic models
                if reference_images:
                    image_uris = []
                    for img_data in reference_images[:10]:
                        if img_data.startswith('data:'):
                            image_uris.append(img_data)
                        else:
                            image_uris.append(img_data)
                    input_params['image_input'] = image_uris
                    logger.info(f"Added {len(image_uris)} reference images")

                # Add model-specific parameters
                if model == "aisha-ai-official/anillustrious-v4:80441e2c32a55f2fcf9b77fa0a74c6c86ad7deac51eed722b9faedb253265cb4":
                    input_params["steps"] = 30

                if model == "cjwbw/animagine-xl-3.1:6afe2e6b27dad2d6f480b59195c221884b6acc589ff4d05ff0e5fc058690fbb9":
                    input_params["num_inference_steps"] = 30
                    input_params["quality_selector"]="Standard v3.1"

            if model == 'prunaai/wan-2.2-image':
                input_params['megapixels'] = 2

            # Handle openai/gpt-image-2 model with custom input parameters
            if model == 'openai/gpt-image-2':
                # Check if input params were passed from frontend
                if 'input' in kwargs and kwargs['input']:
                    input_params = kwargs['input']
                    if 'aspect_ratio' in input_params:
                        input_params['aspect_ratio'] = _normalize_openai_image_aspect_ratio(str(input_params['aspect_ratio']))
                    logger.info(f"Using custom input params for openai/gpt-image-2: {input_params}")
                else:
                    # Build default input params for this model
                    input_params = {
                        "prompt": prompt,
                        "quality": "low",
                        "background": "auto",
                        "moderation": "auto",
                        "aspect_ratio": _normalize_openai_image_aspect_ratio(str(kwargs.get('aspect_ratio', '1:1'))),
                        "output_format": "webp",
                        "input_fidelity": "low",
                        "number_of_images": 1,
                        "output_compression": 90
                    }
                    logger.info(f"Using default input params for openai/gpt-image-2: {input_params}")

            # Generate image using replicate.run(). Replicate/OpenAI can sometimes
            # return E005 sensitive-content failures for either the input or output;
            # retry that exact provider error twice before surfacing a prompt-update
            # message to the UI.
            start_time = datetime.now()
            max_attempts = SENSITIVE_CONTENT_RETRY_ATTEMPTS + 1
            output = None
            for attempt in range(1, max_attempts + 1):
                try:
                    output = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: replicate.run(model, input=input_params)
                    )
                    break
                except Exception as run_error:
                    if not is_sensitive_content_error(run_error):
                        raise

                    if attempt < max_attempts:
                        logger.warning(
                            "Replicate sensitive-content failure; retrying image generation "
                            "(attempt %s/%s): %s",
                            attempt,
                            max_attempts,
                            str(run_error),
                        )
                        await asyncio.sleep(1.5 * attempt)
                        continue

                    logger.error(
                        "Replicate sensitive-content failure persisted after %s attempts: %s",
                        max_attempts,
                        str(run_error),
                    )
                    raise SensitiveContentError(
                        "The image prompt or generated output was flagged as sensitive after multiple attempts. Please update the prompt and try again.",
                        attempts=max_attempts,
                    ) from run_error

            if output is None:
                raise Exception("Replicate returned no output")
            
            generation_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"Image generation completed in {generation_time:.0f}ms")
            
            # Extract image URLs from output
            image_urls = []
            if isinstance(output, list):
                # Output is a list of file objects
                for item in output:
                    if hasattr(item, 'url') and callable(getattr(item, 'url')):
                        # Call the url() method
                        image_urls.append(item.url())
                    elif hasattr(item, 'url'):
                        # Access url property
                        image_urls.append(item.url)
                    else:
                        # Fallback to string conversion
                        image_urls.append(str(item))
            elif hasattr(output, 'url') and callable(getattr(output, 'url')):
                # Single file object with url() method
                image_urls = [output.url()]
            elif hasattr(output, 'url'):
                # Single file object with url property
                image_urls = [output.url]
            else:
                # Fallback for string URLs
                image_urls = [str(output)]
            
            return {
                'status': 'completed',
                'prediction_id': None,  # replicate.run() doesn't return prediction ID
                'image_urls': image_urls,
                'generation_time_ms': int(generation_time),
                'model': model,
                'input_params': input_params,
                'raw_output': output
            }
                
        except SensitiveContentError:
            raise
        except Exception as e:
            logger.error(f"Error generating image with Replicate: {str(e)}")
            raise Exception(f"Image generation failed: {str(e)}")
    
    async def get_generation_status(self, prediction_id: str) -> Dict[str, Any]:
        """
        Check status of image generation
        
        Note: replicate.run() is synchronous, so this method is not applicable
        
        Args:
            prediction_id: Not used with replicate.run()
            
        Returns:
            Dict indicating that status checking is not supported
        """
        return {
            'prediction_id': prediction_id,
            'status': 'not_supported',
            'message': 'Status checking not supported with replicate.run() - generations are synchronous'
        }
    
    def get_available_models(self) -> List[Dict[str, Any]]:
        """
        Get list of available image generation models
        
        Returns:
            List of model information dictionaries
        """
        # Standard image model
        models = [
            {
                'id': 'prunaai/z-image-turbo:7ea16386290ff5977c7812e66e462d7ec3954d8e007a8cd18ded3e7d41f5d7cf',
                'name': 'Standard',
                'description': 'Fast, high-quality image generation',
                'max_width': 2048,
                'max_height': 2048,
                'supports_batch': False
            }
        ]
        
        return models
    
    def _get_model_version(self, model_id: str) -> str:
        """
        Get the model identifier (no version hash needed for replicate.run())
        
        Args:
            model_id: Model identifier
            
        Returns:
            Model identifier for Replicate API
        """
        # For replicate.run(), we use the model ID directly
        return model_id
    
    async def cancel_generation(self, prediction_id: str) -> bool:
        """
        Cancel an ongoing image generation

        Note: replicate.run() is synchronous, so cancellation is not supported

        Args:
            prediction_id: Not used with replicate.run()

        Returns:
            False - cancellation not supported with synchronous generation
        """
        logger.warning("Cancellation not supported with replicate.run() - generations are synchronous")
        return False

    async def animate_image(
        self,
        image_url: str,
        prompt: str = "A dynamic scene",
        model: str = "wan-video/wan-2.2-i2v-fast",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Animate an image into a video using Replicate's i2v model

        Args:
            image_url: URL of the image to animate
            prompt: Text prompt describing the desired animation
            model: Model to use for video generation (default: wan-2.2-i2v-fast)
            **kwargs: Additional model-specific parameters

        Returns:
            Dict with generation result including video_url and metadata
        """
        if not self.is_available():
            raise Exception("Replicate provider not available")

        try:
            logger.info(f"Starting image-to-video generation with model: {model}")
            logger.info(f"Image URL: {image_url}")
            logger.info(f"Animation prompt: {prompt}")

            # Map frontend model names to Replicate model identifiers
            model_mapping = {
                "wan-video/wan-2.2-i2v-fast": "wan-video/wan-2.2-i2v-fast",
                "hailuo-video/hailuo2-fast": "minimax/hailuo-2-fast",
                "hailuo-video/hailuo2.3": "minimax/hailuo-2.3",
                "kling-video/kling2.1": "kwaivgi/kling-v2.1",
                "kling-video/kling2.3": "kwaivgi/kling-v2.3",
                "kwaivgi/kling-avatar-v2": "kwaivgi/kling-avatar-v2",
                "kwaivgi/kling-v2.6": "kwaivgi/kling-v2.6",
                "kwaivgi/kling-v3-video": "kwaivgi/kling-v3-video",
                "bytedance/seedance-1-pro-fast": "bytedance/seedance-1-pro-fast",
                "bytedance/seedance-2.0": "bytedance/seedance-2.0",
                "bytedance/seedance-2.0-fast": "bytedance/seedance-2.0-fast",
            }

            replicate_model = model_mapping.get(model, model)
            logger.info(f"Using Replicate model: {replicate_model}")

            # Prepare input parameters based on the model
            if replicate_model.startswith("wan-video/"):
                # Wan Video parameters
                input_params = {
                    "image": image_url,
                    "prompt": prompt,
                    "duration": kwargs.get("duration", 5),  # Default 5 seconds
                    # "fps": kwargs.get("fps", 16),  # Default 16 fps
                    # "guidance_scale": kwargs.get("guidance_scale", 7.5),
                    # "num_inference_steps": kwargs.get("num_inference_steps", 50)
                    "resolution": kwargs.get("resolution", "480p"),
                }
                # Add end frame if provided
                if kwargs.get("last_image"):
                    input_params["last_image"] = kwargs.get("last_image")
                    logger.info(f"Using last_image for WAN model")

            elif replicate_model.startswith("minimax/hailuo"):
                # Hailuo parameters
                input_params = {
                    "prompt": prompt,
                    "duration": kwargs.get("duration", 6),  # Default 6 seconds
                    "resolution": kwargs.get("resolution", "768p"),  # 540p, 768p, or 1080p
                    "prompt_optimizer": kwargs.get("prompt_optimizer", True),
                    "first_frame_image": image_url  # Image input for Hailuo
                }

            elif replicate_model == "kwaivgi/kling-avatar-v2":
                # Kling Avatar v2 — audio-driven avatar animation
                audio_url = kwargs.get("audio_url")
                if not audio_url:
                    raise ValueError("audio_url is required for kwaivgi/kling-avatar-v2")
                input_params = {
                    "image": image_url,
                    "audio": audio_url,
                    "mode": kwargs.get("mode", "std"),  # "std" or "pro"
                }
                if prompt:
                    input_params["prompt"] = prompt

            elif _is_kling_v2_1_model(replicate_model):
                # Kling v2.1 requires start_image. Standard mode generates 720p.
                # Do not send end_image here because the model requires pro mode
                # when end_image is set.
                input_params = {
                    "mode": "standard",
                    "prompt": prompt,
                    "duration": kwargs.get("duration", 5),
                    "start_image": image_url,
                    "negative_prompt": kwargs.get("negative_prompt", "")
                }

            elif _is_kling_v2_6_model(replicate_model):
                # Kling v2.6 supports native audio by default; keep it disabled
                # for this app flow. The API endpoint passes the source image's
                # aspect ratio; do not hardcode a fallback here.
                input_params = {
                    "prompt": prompt,
                    "duration": kwargs.get("duration", 5),
                    "start_image": image_url,
                    "generate_audio": False,
                    "negative_prompt": kwargs.get("negative_prompt", "")
                }
                aspect_ratio = _canonical_video_aspect_ratio(kwargs.get("aspect_ratio"))
                if aspect_ratio:
                    input_params["aspect_ratio"] = aspect_ratio

            elif _is_kling_v3_video_model(replicate_model):
                # Kling v3 video parameters. Standard mode generates 720p and
                # native audio must remain disabled for this app flow. The API
                # endpoint passes the source image's aspect ratio; do not
                # hardcode a fallback here.
                input_params = {
                    "mode": "standard",
                    "prompt": prompt,
                    "duration": kwargs.get("duration", 3),
                    "start_image": image_url,
                    "generate_audio": False,
                    "negative_prompt": kwargs.get("negative_prompt", "")
                }
                aspect_ratio = _canonical_video_aspect_ratio(kwargs.get("aspect_ratio"))
                if aspect_ratio:
                    input_params["aspect_ratio"] = aspect_ratio
                if kwargs.get("last_image"):
                    input_params["end_image"] = kwargs.get("last_image")
                    logger.info("Using end_image for Kling v3 video model")

            elif replicate_model.startswith("kwaivgi/kling"):
                # Kling i2v parameters
                input_params = {
                    "mode": kwargs.get("mode", "std"),  # "standard" or "pro"
                    "prompt": prompt,
                    "duration": kwargs.get("duration", 5),  # Default 5 seconds
                    "start_image": image_url,
                    "negative_prompt": kwargs.get("negative_prompt", "")
                }
            
            elif replicate_model.startswith("bytedance/seedance"):
                # SeeDance parameters
                input_params = {
                    "image": image_url,
                    "fps": kwargs.get("fps", 24),
                    "prompt": prompt,
                    "duration": kwargs.get("duration", 5),  # Default 5 seconds
                    "resolution": _seedance_resolution(replicate_model, kwargs.get("resolution")),
                    "camera_fixed": kwargs.get("camera_fixed", False),
                }
                if kwargs.get("aspect_ratio"):
                    input_params["aspect_ratio"] = kwargs["aspect_ratio"]
                if _is_seedance_2_model(replicate_model):
                    input_params["model_variant"] = "video_in"
                    if kwargs.get("last_image"):
                        input_params["last_frame_image"] = kwargs["last_image"]
                        logger.info("Using last_frame_image for Seedance 2 model")
                audio_url = kwargs.get("audio_url")
                if audio_url and _is_seedance_2_model(replicate_model):
                    # Seedance 2.0's multimodal reference mode cannot mix first-frame
                    # content with reference media, so switch the source image into
                    # the reference input set when audio is present.
                    input_params.pop("image", None)
                    input_params["reference_images"] = [image_url]
                    input_params["reference_audios"] = [audio_url]
                    input_params["generate_audio"] = True
                    input_params["prompt"] = _seedance_prompt_with_reference_media(
                        prompt,
                        include_image_reference=True,
                        include_audio_reference=True,
                    )

            else:
                # Fallback for unknown models
                input_params = {
                    "image": image_url,
                    "prompt": prompt,
                    "duration": kwargs.get("duration", 5)
                }

            logger.info(f"i2v input parameters: {input_params}")

            # Generate video using replicate.run()
            start_time = datetime.now()
            output = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: replicate.run(replicate_model, input=input_params)
            )

            generation_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"Video generation completed in {generation_time:.0f}ms")

            # Extract video URL from output
            video_url = None
            if isinstance(output, list) and len(output) > 0:
                # Output is a list - take first item
                item = output[0]
                if hasattr(item, 'url') and callable(getattr(item, 'url')):
                    video_url = item.url()
                elif hasattr(item, 'url'):
                    video_url = item.url
                else:
                    video_url = str(item)
            elif hasattr(output, 'url') and callable(getattr(output, 'url')):
                # Single file object with url() method
                video_url = output.url()
            elif hasattr(output, 'url'):
                # Single file object with url property
                video_url = output.url
            else:
                # Fallback for string URL
                video_url = str(output)

            logger.info(f"Generated video URL: {video_url}")

            return {
                'status': 'completed',
                'video_url': video_url,
                'generation_time_ms': int(generation_time),
                'model': model,
                'input_params': input_params,
                'duration': input_params.get('duration', 0),
                'raw_output': output
            }

        except Exception as e:
            logger.error(f"Error generating video with Replicate: {str(e)}")
            raise Exception(f"Video generation failed: {str(e)}")
