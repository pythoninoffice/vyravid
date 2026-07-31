"""
API endpoints for scene generation using AI to create text-to-image prompts
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel, Field
import logging
import json
import re
import uuid
import asyncio
import time
import os
from google.genai import types

from models.auth_models import UserProfile
from auth import get_current_user
from services.scene_generation_service import SceneGenerationService
from services.gcs_service import get_gcs_service
from services.translation_service import TranslationService
from services.background_task_service import get_background_task_service, TaskStatus
from services.google_genai_client import create_google_genai_api_client

router = APIRouter(prefix="/api/scene-generation", tags=["scene-generation"])
logger = logging.getLogger(__name__)
TALKING_SCENE_PROMPT_MODEL = "gemini-3.1-flash-lite"
TALKING_SCENE_PROMPT_FALLBACK_MODEL = "gemini-3-flash-preview"
ANIMAL_HAIRCUT_PROMPT_MODEL = (
    os.getenv("ANIMAL_HAIRCUT_PROMPT_MODEL")
    or os.getenv("GEMINI_TEXT_MODEL")
    or "gemini-3.1-flash-lite"
).strip()
ANIMAL_HAIRCUT_PROMPT_FALLBACK_MODEL = (
    os.getenv("ANIMAL_HAIRCUT_PROMPT_FALLBACK_MODEL")
    or os.getenv("GEMINI_FALLBACK_MODEL")
    or "gemini-3-flash-preview"
).strip()


def _is_gemini_overload_error(error: Exception) -> bool:
    """Detect transient Gemini capacity/rate-limit errors worth falling back on."""
    msg = str(error).lower()
    tokens = [
        "503",
        "service unavailable",
        "unavailable",
        "overloaded",
        "high demand",
        "resource_exhausted",
        "rate limit",
        "quota",
    ]
    return any(token in msg for token in tokens)

# Helper function to extract first valid JSON object or array from text
def extract_first_json_object(text: str):
    """Extract the first valid JSON object or array from text, handling nested braces/brackets and markdown blocks"""
    # Remove markdown code blocks if present
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)

    # Strip whitespace
    text = text.strip()

    # Try to find opening bracket for array first
    bracket_idx = text.find('[')
    brace_idx = text.find('{')

    # Determine which comes first
    if bracket_idx != -1 and (brace_idx == -1 or bracket_idx < brace_idx):
        # Try to extract array
        return _extract_json_structure(text, bracket_idx, '[', ']')
    elif brace_idx != -1:
        # Try to extract object
        return _extract_json_structure(text, brace_idx, '{', '}')
    else:
        raise ValueError("No JSON object or array found in response")

def _extract_json_structure(text: str, start_idx: int, open_char: str, close_char: str):
    """Extract a JSON structure (object or array) from text starting at start_idx"""
    depth = 0
    in_string = False
    escape_next = False

    for i in range(start_idx, len(text)):
        char = text[i]

        # Handle string escaping
        if escape_next:
            escape_next = False
            continue

        if char == '\\':
            escape_next = True
            continue

        # Track if we're inside a string
        if char == '"':
            in_string = not in_string
            continue

        # Only count braces/brackets outside of strings
        if not in_string:
            if char == open_char:
                depth += 1
            elif char == close_char:
                depth -= 1

                # Found the matching closing character
                if depth == 0:
                    json_str = text[start_idx:i+1]
                    return json.loads(json_str)

    # If we get here, structure wasn't balanced
    raise ValueError(f"Unbalanced {open_char}{close_char} in JSON response")

def fix_common_json_errors(json_str: str) -> str:
    """
    Fix common JSON errors that occur in AI-generated responses.

    Common issues:
    - Missing commas between array elements or object properties
    - Trailing commas before closing brackets/braces
    - Unescaped quotes in strings
    - Malformed strings with line breaks
    """
    # Remove trailing commas before closing brackets/braces
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)

    # Fix missing commas between objects in arrays (common issue)
    # Pattern: }\n{  or }\n  { should be },\n{
    json_str = re.sub(r'\}(\s*)\{', r'},\1{', json_str)

    # Fix missing commas between quoted strings
    # Pattern: "value"\n" should be "value",\n"
    json_str = re.sub(r'\"(\s*)\n(\s*)\"', r'",\1\n\2"', json_str)

    # Fix unescaped quotes in strings (basic attempt)
    # This is tricky without a full parser, so we'll be conservative

    return json_str

async def retry_gemini_with_json_parsing(
    gemini_call_func,
    json_parse_func,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    exponential_base: float = 2.0
):
    """
    Retry a Gemini API call with JSON parsing, handling both API errors and JSON parse errors.

    Args:
        gemini_call_func: Function that calls Gemini API and returns the response
        json_parse_func: Function that parses the JSON response
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff calculation

    Returns:
        The parsed JSON result

    Raises:
        The last exception if all retries fail
    """
    last_exception = None
    delay = initial_delay

    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                logger.info(f"🔄 Retry attempt {attempt}/{max_retries} after {delay:.2f}s delay...")

            # Call Gemini API
            response_text = gemini_call_func()

            # Try to parse JSON
            try:
                result = json_parse_func(response_text)

                if attempt > 0:
                    logger.info(f"✅ Retry successful on attempt {attempt}")

                return result

            except (ValueError, json.JSONDecodeError) as parse_error:
                logger.warning(f"⚠️ JSON parsing failed on attempt {attempt + 1}: {str(parse_error)}")
                logger.debug(f"Response preview: {response_text[:500]}...")

                # Try to fix common JSON errors
                if attempt < max_retries:
                    try:
                        logger.info("🔧 Attempting to fix common JSON errors...")
                        fixed_json = fix_common_json_errors(response_text)
                        result = json_parse_func(fixed_json)
                        logger.info("✅ Successfully fixed and parsed JSON!")
                        return result
                    except Exception as fix_error:
                        logger.debug(f"JSON fix attempt failed: {str(fix_error)}")

                # If this is the last attempt or fix failed, raise the error
                if attempt >= max_retries:
                    logger.error(f"❌ All {max_retries + 1} attempts failed. Last JSON error: {str(parse_error)}")
                    raise

                last_exception = parse_error

        except Exception as e:
            last_exception = e

            # Check if this is a retryable API error (503, rate limit, etc.)
            error_str = str(e)
            is_retryable_api_error = (
                "503" in error_str or
                "UNAVAILABLE" in error_str or
                "overloaded" in error_str or
                "rate limit" in error_str.lower()
            )

            if is_retryable_api_error:
                logger.warning(f"⚠️ Gemini API error on attempt {attempt + 1}/{max_retries + 1}: {error_str}")

            # If not retryable or last attempt, raise the exception
            if not is_retryable_api_error and attempt < max_retries:
                # Non-retryable error, don't retry
                logger.error(f"❌ Non-retryable error: {error_str}")
                raise

            if attempt >= max_retries:
                logger.error(f"❌ All {max_retries + 1} attempts failed. Last error: {error_str}")
                raise

        # Wait before retry with exponential backoff
        await asyncio.sleep(delay)
        delay = min(delay * exponential_base, max_delay)

    # This should never be reached, but just in case
    if last_exception:
        raise last_exception

# Helper function to aggregate sentences
def aggregate_sentences(
    sentences: List[dict],
    agg_first_half: int,
    agg_second_half: int,
    cut_off: float = 0.5
) -> List[dict]:
    """
    Aggregate sentences by combining multiple sentences into one.

    The function processes sentences in two phases:
    1. First half: Aggregates sentences using agg_first_half until reaching/exceeding the cutoff point
    2. Second half: Aggregates remaining sentences using agg_second_half

    This ensures even distribution by allowing first half chunks to complete even if they
    slightly exceed the cutoff point.

    Args:
        sentences: List of sentence objects with 'text', 'start_time', and 'end_time'
        agg_first_half: Number of sentences to combine in the first half
        agg_second_half: Number of sentences to combine in the second half
        cut_off: The point to split first/second half (e.g., 0.5 = 50%, 0.3 = 30%)

    Returns:
        List of aggregated sentence objects
    """
    if not sentences:
        return []

    aggregated = []

    # Calculate the approximate cutoff index
    cutoff_index = int(len(sentences) * cut_off)

    # Process first half - continue until we reach or exceed cutoff_index
    i = 0
    while i < len(sentences):
        # If we've reached or exceeded the cutoff, switch to second half processing
        if i >= cutoff_index:
            break

        # Take up to agg_first_half sentences
        chunk = sentences[i:i + agg_first_half]

        if chunk:
            # Combine text with spaces (and preserve punctuation)
            combined_text = " ".join(s.get('text', '').strip() for s in chunk)

            # Use first sentence's start_time and last sentence's end_time
            aggregated_sentence = {
                'text': combined_text,
                'start_time': chunk[0].get('start_time', 0),
                'end_time': chunk[-1].get('end_time', 0)
            }
            aggregated.append(aggregated_sentence)

        i += agg_first_half

    # Process second half - process remaining sentences
    while i < len(sentences):
        # Take up to agg_second_half sentences
        chunk = sentences[i:i + agg_second_half]

        if chunk:
            # Combine text with spaces (and preserve punctuation)
            combined_text = " ".join(s.get('text', '').strip() for s in chunk)

            # Use first sentence's start_time and last sentence's end_time
            aggregated_sentence = {
                'text': combined_text,
                'start_time': chunk[0].get('start_time', 0),
                'end_time': chunk[-1].get('end_time', 0)
            }
            aggregated.append(aggregated_sentence)

        i += agg_second_half

    return aggregated

def make_scenes_continuous(scenes: List[dict]) -> List[dict]:
    """
    Ensure scenes are continuous with no gaps between them.
    Adjusts each scene's start_time to match the previous scene's end_time.

    Args:
        scenes: List of scene objects with 'start_time' and 'end_time'

    Returns:
        List of scenes with adjusted continuous timing
    """
    if not scenes:
        return []

    # Keep first scene's start_time as-is
    continuous_scenes = []

    for i, scene in enumerate(scenes):
        if i == 0:
            # First scene keeps its original timing
            continuous_scenes.append(scene)
        else:
            # Subsequent scenes: start_time = previous scene's end_time
            prev_end = continuous_scenes[i - 1].get('end_time', 0)
            scene_copy = scene.copy()
            scene_copy['start_time'] = prev_end
            # Keep original end_time
            continuous_scenes.append(scene_copy)

    return continuous_scenes

# Request/Response Models
class SceneGenerationRequest(BaseModel):
    text: str = Field(..., description="The story text to analyze and create scenes from")
    scene_count: int = Field(default=3, ge=1, le=50, description="Number of scenes to generate (1-10)")

class SceneData(BaseModel):
    description: str = Field(..., description="Brief description of the scene")
    prompt: str = Field(..., description="Text-to-image prompt for this scene")

class SceneGenerationResponse(BaseModel):
    scenes: List[SceneData] = Field(..., description="List of generated scenes with prompts")
    total_scenes: int = Field(..., description="Total number of scenes generated")


class TalkingScenePromptInput(BaseModel):
    scene_id: str = Field(..., description="Client-generated scene identifier")
    scene_index: int = Field(..., description="0-based scene order")
    scene_type: Optional[str] = Field(default="dialogue", description="dialogue, monologue, broll, mixed")
    scene_script: str = Field(..., description="Full scene script block")
    description: Optional[str] = Field(default=None, description="Short scene summary")
    layout_type: Optional[str] = Field(default="single", description="single, two_shot, group, speaker_focus")
    character_names: List[str] = Field(default_factory=list, description="Characters visible in the scene")
    dialogue_turns: List[dict] = Field(default_factory=list, description="Dialogue turns with speaker labels and text")


class TalkingScenePromptRequest(BaseModel):
    scenes: List[TalkingScenePromptInput] = Field(..., min_length=1, max_length=50)
    language_code: Optional[str] = Field(default="en", description="Language code for the script")


class TalkingScenePromptResult(BaseModel):
    scene_id: str
    prompt: str


class TalkingScenePromptResponse(BaseModel):
    scenes: List[TalkingScenePromptResult]
    total_scenes: int


class AnimalHaircutPromptRequest(BaseModel):
    animal: str = Field(..., min_length=1, max_length=80, description="Animal name, e.g. tiger, lion, dog")
    haircut_style: str = Field(..., min_length=1, max_length=80, description="Haircut style, e.g. mohawk, undercut")


class AnimalHaircutPromptResponse(BaseModel):
    animal_name: str
    haircut_style: str
    haircut_description: str
    animal_appearance_details: str
    first_image_prompt: str
    second_image_prompt: str
    video_prompt: str

# New models for transcript-based scene generation
class TranscriptSceneGenerationRequest(BaseModel):
    project_id: str = Field(..., description="Project ID to find the transcript file")
    agg_first_half: Optional[int] = Field(default=1, description="Number of sentences to combine in first half")
    agg_second_half: Optional[int] = Field(default=1, description="Number of sentences to combine in second half")
    cut_off: Optional[float] = Field(default=0.5, ge=0.0, le=1.0, description="Point to split first/second half (0.0-1.0)")
    language_code: Optional[str] = Field(default=None, description="Language code for multi-language support")
    custom_prompt_instructions: Optional[str] = Field(default=None, description="Custom instructions for image prompt generation")

class SceneDataWithTiming(BaseModel):
    description: str = Field(..., description="Brief description of the scene")
    prompt: str = Field(..., description="Text-to-image prompt for this scene")
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    animation_prompt: Optional[str] = Field(None, description="Animation/camera movement prompt for text-to-video")

class TranscriptSceneGenerationResponse(BaseModel):
    scenes: List[SceneDataWithTiming] = Field(..., description="List of generated scenes with prompts and timing")
    total_scenes: int = Field(..., description="Total number of scenes generated")

# Async task response models
class TaskInitiatedResponse(BaseModel):
    task_id: str = Field(..., description="Unique task identifier")
    status: str = Field(..., description="Task status")
    message: str = Field(..., description="Task status message")

class TaskStatusResponse(BaseModel):
    task_id: str = Field(..., description="Unique task identifier")
    task_type: str = Field(..., description="Type of task")
    status: str = Field(..., description="Task status (pending, processing, completed, failed)")
    progress: int = Field(..., description="Progress percentage (0-100)")
    message: str = Field(..., description="Status message")
    result: Optional[TranscriptSceneGenerationResponse] = Field(None, description="Task result when completed")
    error: Optional[str] = Field(None, description="Error message if failed")
    created_at: str = Field(..., description="Task creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")


def _build_talking_scene_prompt_system_instruction() -> str:
    return """You write high-quality image-generation prompts for AI video storyboards.

Your job is to convert talking-scene context into visually rich, varied image prompts.

Requirements:
- Derive the prompt from the scene context, not from a generic template.
- Do NOT copy raw dialogue lines or narration into the prompt.
- Focus on what should be visible: environment, background, props, wardrobe, blocking, gesture, body language, facial expression, camera framing, composition, mood, lighting, and action.
- If multiple characters are on screen, explicitly keep them in the same frame and stage their positions and reactions naturally.
- Vary the framing across scenes when appropriate based on the conversation context.
- Keep prompts grounded and realistic.
- Do not mention text overlays, subtitles, or captions.
- Do not include bullet points, markdown, or explanations.

Return ONLY valid JSON in this exact shape:
{
  "scenes": [
    {
      "scene_id": "string",
      "prompt": "string"
    }
  ]
}"""


def _build_talking_scene_prompt_user_prompt(request: TalkingScenePromptRequest) -> str:
    scene_payload = []
    for scene in request.scenes:
        scene_payload.append({
            "scene_id": scene.scene_id,
            "scene_index": scene.scene_index,
            "scene_type": scene.scene_type,
            "layout_type": scene.layout_type,
            "description": scene.description,
            "scene_script": scene.scene_script,
            "character_names": scene.character_names,
            "dialogue_turns": scene.dialogue_turns,
        })

    return (
        f"Language code: {request.language_code or 'en'}\n"
        "Generate one distinct image prompt for each talking scene below.\n"
        "Use the full scene context to infer setting, gesture, environment, and composition.\n"
        "Keep prompts varied across scenes. For multi-character scenes, allow multiple characters in the same shot when the context supports it.\n\n"
        f"Scenes JSON:\n{json.dumps(scene_payload, ensure_ascii=False, indent=2)}"
    )


def _build_animal_haircut_prompt_system_instruction() -> str:
    return """You create production-ready prompt packages for comedic animal grooming videos.

Your job:
- Take an animal and a haircut style.
- Infer species-accurate fur, markings, skin visibility, and hairstyle shaping details.
- Return concise descriptors and the finished Image 2 prompt.
- Image 1 and the video prompt are assembled separately by the application from fixed templates.

Hard requirements:
- Return ONLY valid JSON.
- Use the exact JSON shape shown below with all string fields filled.
- Keep the animal the same across all prompts.
- Keep the haircut style exactly aligned with the user's request.
- Make descriptors photorealistic, grounded, and usable directly in image/video generation templates.
- Generate:
  - haircut_description: a concise phrase describing the exact visual shape, length, texture, and styling of the requested haircut on top of the animal's head.
  - animal_appearance_details: a concise phrase describing the animal's species-specific fur color, markings, facial/ruff features, and lighter/darker areas. This descriptor must work for both overgrown and trimmed states.
  - skin_color_and_markings: a concise phrase describing the sleek visible short coat or skin tone after close trimming, including any species-specific markings or patterns that remain visible.
- No markdown fences. No commentary. No extra keys.

Return JSON exactly in this shape:
{
  "animal_name": "string",
  "haircut_style": "string",
  "haircut_description": "string",
  "animal_appearance_details": "string",
  "skin_color_and_markings": "string"
}"""


def _build_animal_haircut_prompt_user_prompt(request: AnimalHaircutPromptRequest) -> str:
    animal = request.animal.strip()
    haircut_style = request.haircut_style.strip()
    return f"""Create the animal haircut prompt package for:

Animal: {animal}
Haircut style: {haircut_style}

Build the three finished prompts so they are ready to paste into the storyboard UI.
Keep the tone understated and photorealistic, with a subtly comedic grooming reveal.
"""


def _build_animal_haircut_first_image_prompt(animal: str, animal_appearance_details: str) -> str:
    return f"""
A photorealistic extreme close-up portrait of a {animal} inside an upscale pet grooming studio, before grooming.
IMPORTANT: crop tightly — head and face fill the frame completely, nothing below the chin visible.
Every single part of the head is covered in heavily overgrown, tangled fur — the face, cheeks, forehead,
muzzle, chin, jaw, ears, neck and thick striped ruff typical of a {animal} are all wild, unkempt and voluminous with uneven
clumps and stray hairs jutting out in all directions. Dense orange fur with bold black stripes ({animal_appearance_details}) appears overgrown and chaotic,
with lighter white fur around the muzzle and cheeks blending messily ({animal_appearance_details}). Fur spills over the eyes naturally.
The {animal} looks directly at the camera. Black grooming cape visible at the very bottom of frame.
Warm ring light reflected in both eyes. Background blurred: clean salon interior. Shot on iPhone 15 Pro Max,
shallow depth of field, hyper-detailed fur, cinematic realism, 4K."""


def _build_animal_haircut_second_image_prompt(
    animal: str,
    haircut_style: str,
    haircut_description: str,
    skin_color_and_markings: str,
) -> str:
    return f"""
A photorealistic extreme close-up portrait of the same {animal} in the same upscale pet grooming studio,
now fully groomed. IMPORTANT: this is the exact same animal as Image 1 — the face shape, eye colour, facial features,
skin tone and markings must be identical. Only the fur has changed. crop tightly — head and face fill the frame completely,
nothing below the chin visible. Every single part of the head except the {haircut_style} {haircut_description}, natural animal
coat — the face, cheeks, forehead, muzzle, chin, jaw, ears,
neck and thick striped ruff are all cut flat and close, revealing sleek {skin_color_and_markings} and
clean white muzzle areas, with no bulk, no volume and no stray hairs. No species-specific fur volume whatsoever.
The {haircut_style} on top is the only fur with any length or volume — longer striped fur sits sharply styled on the crown like
a human {haircut_style}, contrasting against the closely shaved sides. The {animal} looks directly at the camera with a calm,
quietly proud expression. Black grooming cape visible at the very bottom of frame. Warm ring light reflected in both eyes.
Background blurred: clean salon interior. Shot on iPhone 15 Pro Max, shallow depth of field, ultra-detailed,
cinematic realism, 4K."""


def _build_animal_haircut_video_prompt(animal: str, haircut_style: str) -> str:
    return f"""Animal: {animal} | Haircut: {haircut_style}
Setting: upscale pet grooming studio

Opening: tight close-up of {animal}, black cape, overgrown messy fur on head and face, ring light in eyes.

[shot 1 — side] Wide brush strokes through the head and facial fur only — fur separates naturally. Soft brushing sounds.
[shot 2 — front] Electric clippers run firmly down the sides of the face, cheeks, jaw and thick striped ruff — fur drops away cleanly, revealing short natural skin underneath. Loud satisfying buzz.
[shot 3 — top-down] Water mist spritzed directly onto the top of the head — fur clumps and flattens ready for styling. Crisp spray sound.
[shot 4 — side] Scissors shape the top of the head — fur falls, {haircut_style} emerges. Snipping sounds.
[shot 5 — front] Hairdryer aimed at the head — head fur lifts and settles into final style. Warm dryer hum.
[shot 6 — top-down] Fine-tooth comb through head fur only, locks in clean edges.
[final — front centre] {animal}, finished {haircut_style} on top, all facial fur trimmed close and neat, cape on, calm and quietly proud. Slow blink, subtle ear flick.

Camera: Handheld, close-ups, slight tilt. Shot on iPhone 15 Pro Max. High-key studio lighting.
Audio: ASMR grooming sounds, no music. Comedic through understatement."""

# Background task processing function
async def process_transcript_scene_generation(
    task_id: str,
    request: TranscriptSceneGenerationRequest,
    user_id: str,
    user_email: str
) -> TranscriptSceneGenerationResponse:
    """
    Background processing function for transcript-based scene generation.
    This contains all the heavy processing logic that can take 30+ seconds.
    """
    task_service = get_background_task_service()

    try:
        # Step 1: Verify the project exists in Supabase
        task_service.update_task(task_id, progress=3, message="Verifying project...")
        from db.supabase_client import supabase_client

        # Query the video_projects table to verify project exists
        result = supabase_client.supabase.table("video_projects") \
            .select("id") \
            .eq("id", request.project_id) \
            .execute()

        if not result.data or len(result.data) == 0:
            raise HTTPException(status_code=404, detail="Project not found")

        logger.info(f"📁 Verified project exists: {request.project_id}")

        # Step 2: Read transcript data from GCS
        task_service.update_task(task_id, progress=5, message="Reading transcript data...")
        gcs_service = get_gcs_service()
        transcript_filename = f"raw_transcript_data_{request.language_code}.txt" if request.language_code else "raw_transcript_data.txt"
        # Transcript is saved under output/{user_id}/{project_id}/
        transcript_path = f"output/{user_id}/{request.project_id}/{transcript_filename}"
        logger.info(f"🔍 Looking for transcript at: {transcript_path}")

        # Local-first: read transcript from filesystem storage
        transcript_content = None
        try:
            if hasattr(gcs_service, "read_text"):
                transcript_content = gcs_service.read_text(transcript_path)
                logger.info(f"📖 Read transcript from local storage: {transcript_path}")
        except FileNotFoundError:
            logger.warning(f"Transcript not on disk at {transcript_path}, trying signed URL")
        except Exception as e:
            logger.warning(f"Local transcript read failed: {e}")

        if transcript_content is None:
            signed_url = await gcs_service.generate_signed_url(transcript_path, expiration_hours=1)
            if not signed_url:
                raise HTTPException(
                    status_code=404,
                    detail="Transcript file not found. Please generate audio with transcription first.",
                )
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(signed_url) as response:
                    if response.status != 200:
                        raise HTTPException(status_code=404, detail="Failed to download transcript file")
                    transcript_content = await response.text()

        # Step 3: Parse transcript JSON and extract text and words
        task_service.update_task(task_id, progress=10, message="Parsing transcript...")
        transcript_data = json.loads(transcript_content)
        user_input_text = transcript_data.get('user_input_text')
        if user_input_text and user_input_text.strip():
            full_text = user_input_text
        else:
            full_text = transcript_data.get('text', '')
        words_data = transcript_data.get('words', [])

        logger.info(f"📝 Parsed transcript - full_text length: {len(full_text) if full_text else 0}, words count: {len(words_data)}")

        if not full_text or not words_data:
            raise ValueError("Invalid transcript data. Missing text or words information.")

        # Step 4: Generate or load sentences with timing
        task_service.update_task(task_id, progress=20, message="Processing sentences with timing...")
        translation_service = TranslationService()
        from google.genai import types

        sentences_filename = f"transcript_sentences_{request.language_code}.json" if request.language_code else "transcript_sentences.json"
        # Use project_id for consistency with transcript location
        sentences_gcs_path = f"output/{user_id}/{request.project_id}/{sentences_filename}"
        sentences = None

        # Try to load existing sentences (currently disabled to force regeneration)
        # In production, you might want to enable this for faster re-processing

        # Generate sentences with first Gemini call
        task_service.update_task(task_id, progress=30, message="Organizing transcript into sentences...")
        first_prompt_data = {"text": full_text, "words": words_data}
        first_system_prompt = (
            "Below is a speech to text API call result. The 'text' contains the full text content. "
            "The 'words' contains each text or scripts and their start/end time. the times are in milliseconds. Do not convert them to seconds."
            "DO NOT modify start_time or end_time of the 'words' array, keep them as they are."
            "If the given context has punctuations, use them to split senetnces. One sentence should end with a period."
            "If the given context doesn't have punctuations, use the given context to re-organize 'text' into complete sentences, with corresponding start/end time, in JSON format. "
            "Each sentence should end with a period not a comma."
            "Return a JSON object with 'sentences' array, where each sentence has 'text', 'start_time', and 'end_time' fields. DO NOT modify start_time or end_time of the 'words' array."
        )

        logger.info("Making first Gemini call to reorganize transcript into sentences")

        def call_first_gemini_api():
            """Call Gemini API for sentence organization and return response text."""
            client = create_google_genai_api_client(translation_service.google_api_key)
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash-lite",
                    config=types.GenerateContentConfig(system_instruction=first_system_prompt),
                    contents=f"Transcript data: {json.dumps(first_prompt_data, ensure_ascii=False)}"
                )
                response_text = response.text.strip()
                logger.info(f"First Gemini response length: {len(response_text)}")
                return response_text
            finally:
                # Properly close the client to avoid asyncio warnings
                client.close()

        def parse_sentences_json(response_text: str):
            """Parse JSON from Gemini sentence-organization response."""
            return extract_first_json_object(response_text)

        try:
            sentences_data = await retry_gemini_with_json_parsing(
                gemini_call_func=call_first_gemini_api,
                json_parse_func=parse_sentences_json,
                max_retries=3,
                initial_delay=2.0,
                max_delay=10.0
            )
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Failed to parse JSON from first Gemini response after retries: {str(e)}")
            raise ValueError(f"Failed to parse sentence response after retries: {str(e)}")

        sentences = sentences_data.get('sentences', [])
        if not sentences:
            raise ValueError("No sentences found in response")

        logger.info(f"Successfully parsed {len(sentences)} sentences from first API response")

        # Upload sentences response to GCS
        try:
            sentences_json = json.dumps(sentences_data, ensure_ascii=False, indent=2)
            await gcs_service.upload_content(
                content=sentences_json,
                user_id=user_id,
                job_id=request.project_id,
                filename=sentences_filename,
                file_type="output",
                content_type="application/json"
            )
            logger.info(f"✅ Successfully uploaded sentences to GCS")
        except Exception as upload_error:
            logger.warning(f"⚠️ Failed to upload sentences to GCS: {str(upload_error)}")

        # Step 3.5: Aggregate sentences if requested
        task_service.update_task(task_id, progress=50, message="Aggregating sentences...")
        if request.agg_first_half > 1 or request.agg_second_half > 1:
            logger.info(f"Aggregating sentences - first_half: {request.agg_first_half}, second_half: {request.agg_second_half}")
            aggregated_sentences = aggregate_sentences(
                sentences=sentences,
                agg_first_half=request.agg_first_half,
                agg_second_half=request.agg_second_half,
                cut_off=request.cut_off
            )
            logger.info(f"Aggregated from {len(sentences)} to {len(aggregated_sentences)} sentences")
            sentences_for_prompts = aggregated_sentences
        else:
            sentences_for_prompts = sentences

        # Step 3.6: Ensure scenes are continuous (no timing gaps)
        task_service.update_task(task_id, progress=55, message="Ensuring continuous scene timing...")
        sentences_for_prompts = make_scenes_continuous(sentences_for_prompts)
        logger.info(f"Applied continuous timing to {len(sentences_for_prompts)} sentences")

        # Step 4: Second Gemini call to generate image prompts (THE SLOW PART)
        task_service.update_task(task_id, progress=60, message=f"Generating image prompts for {len(sentences_for_prompts)} scenes...")

        # Step 4.5: Fetch user's available characters from Supabase
        available_characters = []
        try:
            from db.supabase_client import SupabaseClient
            supabase_client = SupabaseClient()

            # Query character_designs table for all characters belonging to this user
            characters_result = supabase_client.supabase.table('character_designs')\
                .select('name')\
                .eq('user_id', user_id)\
                .execute()

            if characters_result.data:
                available_characters = [char['name'] for char in characters_result.data]
                logger.info(f"Found {len(available_characters)} available characters for user {user_id}: {available_characters}")
            else:
                logger.info(f"No characters found for user {user_id}")
        except Exception as char_error:
            logger.warning(f"Failed to fetch characters for user {user_id}: {str(char_error)}")
            # Don't fail the whole process if character fetching fails

        # Build the base system prompt
        base_system_prompt = (
            "We are making YouTube videos using the given text as script. "
            "For EACH PROVIDED TEXT SEGMENT (do not split them), create ONE image generation prompt that captures the overall context of that segment. "
            "Each text segment represents one scene in the video. "
            "Be as creative as possible with detailed visual descriptions. "
        )

        # Add custom instructions if provided (first occurrence - early emphasis)
        if request.custom_prompt_instructions and request.custom_prompt_instructions.strip():
            base_system_prompt += f"\n\nCRITICAL STYLE REQUIREMENT - APPLY TO EVERY SINGLE SCENE: {request.custom_prompt_instructions.strip()}\n\n"

        # Add available characters list if any exist
        if available_characters:
            characters_formatted = ", ".join([f"@{name.replace(' ', '').lower()}" for name in available_characters])
            base_system_prompt += f"\n\nAVAILABLE CHARACTERS: This user has the following characters already created: {characters_formatted}. "
            base_system_prompt += "When you detect character names in the script that match these available characters, use the exact format shown above (starting with @). "
            base_system_prompt += "Try your best to match names from the script to these available character names. If no character names are found, use names from the script. do not add @ sign to the names.\n\n"

        

        # Add the rest of the standard instructions
        second_system_prompt = base_system_prompt + (
            "If there are persons/characters in a scene, write their names in this format: @<firstname><lastname> all together no space. For example, 'Elon Musk' will be written as @elonmusk. "
            "Try your best to match their names into our format. A generic name like 'a man' or 'a woman' or 'you', etc. should not be written in this format."
            "Return a JSON object with 'scenes' array, where each scene has: "
            "'text' (the exact original text provided), 'prompt' (detailed image generation prompt), 'start_time', and 'end_time'. "
            "IMPORTANT: Create exactly ONE scene per input text segment. Do NOT split the text segments into multiple scenes. "
            "Keep the original 'text', 'start_time', and 'end_time' values unchanged from the input."
        )

        # Reinforce custom instructions at the end (second occurrence - final emphasis)
        # if request.custom_prompt_instructions and request.custom_prompt_instructions.strip():
        #     second_system_prompt += f"\n\nCRITICAL STYLE REQUIREMENT - APPLY TO EVERY SINGLE SCENE: {request.custom_prompt_instructions.strip()}\n\nRemember: ALL scenes must follow this style requirement consistently."

        logger.info(f"Making second Gemini call to generate image prompts for {len(sentences_for_prompts)} sentences")
        logger.info(f"System prompt: {second_system_prompt}")
        logger.info(f"System prompt includes {len(available_characters)} available characters")
        logger.debug(f"Full system prompt: {second_system_prompt[:500]}...")  # Log first 500 chars for debugging

        # Parse the scenes response
        task_service.update_task(task_id, progress=90, message="Processing generated prompts...")

        # Use retry mechanism for Gemini API call and JSON parsing
        def call_gemini_api():
            """Call Gemini API and return response text"""
            client = create_google_genai_api_client(translation_service.google_api_key)
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash-lite",
                    config=types.GenerateContentConfig(system_instruction=second_system_prompt),
                    contents=f"Sentences with timing: {json.dumps(sentences_for_prompts, ensure_ascii=False)}"
                )
                response_text = response.text.strip()
                logger.info(f"Second Gemini response length: {len(response_text)}")
                return response_text
            finally:
                # Properly close the client to avoid asyncio warnings
                client.close()

        def parse_scenes_json(response_text: str):
            """Parse JSON from Gemini response"""
            return extract_first_json_object(response_text)

        # Call with retry mechanism
        try:
            scenes_data = await retry_gemini_with_json_parsing(
                gemini_call_func=call_gemini_api,
                json_parse_func=parse_scenes_json,
                max_retries=3,
                initial_delay=2.0,
                max_delay=10.0
            )
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Failed to parse JSON after all retries: {str(e)}")
            raise ValueError(f"Failed to parse scene generation response after retries: {str(e)}")

        # Handle different response formats from Gemini
        scenes = []
        if isinstance(scenes_data, list):
            # Gemini returned an array directly: [{...}, {...}]
            logger.info(f"Parsed scenes_data as array with {len(scenes_data)} scenes")
            scenes = scenes_data
        elif isinstance(scenes_data, dict):
            # Check if it's the expected format: {"scenes": [...]}
            if 'scenes' in scenes_data:
                logger.info(f"Parsed scenes_data as object with 'scenes' key")
                scenes = scenes_data.get('scenes', [])
            # Check if it's a single scene object: {"text": "...", "prompt": "...", ...}
            elif 'text' in scenes_data and 'prompt' in scenes_data:
                logger.info(f"Parsed scenes_data as single scene object, wrapping in array")
                scenes = [scenes_data]
            else:
                logger.info(f"Parsed scenes_data keys: {list(scenes_data.keys())}")

        logger.info(f"Parsed scenes_data preview: {json.dumps(scenes_data if isinstance(scenes_data, dict) else {'scenes': scenes_data}, ensure_ascii=False)[:1000]}...")

        if not scenes:
            raise ValueError("No scenes found in response")

        logger.info(f"Successfully parsed {len(scenes)} scenes from second API response")

        # Step 4.5: Third Gemini call to generate animation prompts
        task_service.update_task(task_id, progress=93, message="Generating animation prompts...")

        animation_scenes = []
        try:
            animation_prompt_input = []
            for scene in scenes:
                animation_prompt_input.append({
                    "text": scene.get("text", scene.get("description", "")),
                    "image_prompt": scene.get("prompt", ""),
                    "start_time": scene.get("start_time", 0),
                    "end_time": scene.get("end_time", 0),
                })

            third_system_prompt = (
                "You are generating high-quality image-to-video animation prompts for text-to-video AI models.\n\n"
                "For each scene, you will receive:\n"
                "- the original source text for the scene\n"
                "- the image prompt that was used to design the scene visually\n"
                "- timing data\n\n"
                "Your job is to create an animation prompt that ANIMATES THE EXACT SCENE ALREADY DESCRIBED by the image prompt.\n"
                "Do not ignore the image prompt. Use it as the visual source of truth.\n"
                "Also use the source text to infer what actions, reactions, and story beats should happen in the shot.\n\n"
                "For each scene, write a cinematic animation prompt that includes, when relevant:\n"
                "- primary subject action\n"
                "- body movement or pose changes\n"
                "- facial expression or eye movement\n"
                "- secondary environmental motion (wind, smoke, water, crowd motion, flickering lights, particles, fabric, hair, etc.)\n"
                "- object motion and interaction\n"
                "- camera movement that supports the action rather than replacing it\n\n"
                "Important requirements:\n"
                "- Keep the same characters, setting, objects, and overall composition implied by the image prompt\n"
                "- Bring the scene to life with specific motion, not generic camera-only instructions\n"
                "- Avoid vague prompts like 'camera slowly pans' unless you also describe what is happening in the scene\n"
                "- If the source text implies emotion, make the motion reflect that emotion\n"
                "- If the scene is naturally subtle, use subtle motion, but still animate the world\n"
                "- Prefer concrete verbs such as turns, reaches, glances, steps, exhales, sways, flickers, ripples, drifts, pulses, leans, opens, closes\n"
                "- Keep each prompt concise but meaningful, around 2-4 sentences\n\n"
                "Good example:\n"
                "\"The scientist looks up from the glowing console, blinks in alarm, and quickly reaches toward the controls as holographic particles pulse around the room. Her lab coat and loose papers flutter from the machine's energy while the camera slowly pushes in to heighten the tension.\"\n\n"
                "Bad example:\n"
                "\"Camera slowly zooms in with a slight pan.\"\n\n"
                "Return JSON with 'scenes' array, where each scene has:\n"
                "- 'text' (original text - unchanged)\n"
                "- 'animation_prompt' (the animation/camera movement prompt)\n"
                "- 'start_time' (unchanged)\n"
                "- 'end_time' (unchanged)"
            )

            logger.info(f"Making third Gemini call to generate animation prompts for {len(sentences_for_prompts)} sentences")

            def call_animation_gemini_api():
                """Call Gemini API for animation prompts and return response text"""
                client = create_google_genai_api_client(translation_service.google_api_key)
                try:
                    response = client.models.generate_content(
                        model="gemini-2.5-flash-lite",
                        config=types.GenerateContentConfig(system_instruction=third_system_prompt),
                        contents=f"Scenes with source text, image prompts, and timing: {json.dumps(animation_prompt_input, ensure_ascii=False)}"
                    )
                    response_text = response.text.strip()
                    logger.info(f"Third Gemini response length: {len(response_text)}")
                    return response_text
                finally:
                    client.close()

            def parse_animation_json(response_text: str):
                """Parse JSON from Gemini animation response"""
                return extract_first_json_object(response_text)

            # Call with retry mechanism (max 3 retries)
            animation_data = await retry_gemini_with_json_parsing(
                gemini_call_func=call_animation_gemini_api,
                json_parse_func=parse_animation_json,
                max_retries=3,
                initial_delay=2.0,
                max_delay=10.0
            )

            # Handle different response formats
            if isinstance(animation_data, list):
                animation_scenes = animation_data
            elif isinstance(animation_data, dict):
                if 'scenes' in animation_data:
                    animation_scenes = animation_data.get('scenes', [])
                elif 'text' in animation_data and 'animation_prompt' in animation_data:
                    animation_scenes = [animation_data]

            logger.info(f"Successfully parsed {len(animation_scenes)} animation prompts from third API response")

        except Exception as animation_error:
            # Graceful degradation - continue without animation prompts if generation fails
            logger.error(f"Failed to generate animation prompts after all retries: {str(animation_error)}")
            logger.warning("Continuing with empty animation prompts (user can add them manually later)")
            animation_scenes = []

        # Step 5: Format response
        task_service.update_task(task_id, progress=95, message="Finalizing results...")
        formatted_scenes = []
        for i, scene in enumerate(scenes):
            # Get matching animation prompt by index
            animation_prompt = None
            if i < len(animation_scenes):
                animation_prompt = animation_scenes[i].get('animation_prompt', '')

            formatted_scenes.append(SceneDataWithTiming(
                description=scene.get('text', scene.get('description', '')),
                prompt=scene.get('prompt', ''),
                start_time=float(scene.get('start_time', 0))/1000,
                end_time=float(scene.get('end_time', 0))/1000,
                animation_prompt=animation_prompt
            ))

        logger.info(f"Successfully generated {len(formatted_scenes)} scenes from transcript for user {user_email}")

        return TranscriptSceneGenerationResponse(
            scenes=formatted_scenes,
            total_scenes=len(formatted_scenes)
        )

    except Exception as e:
        logger.error(f"Background task {task_id} failed: {str(e)}", exc_info=True)
        raise
    # Note: Google Genai Client doesn't require explicit cleanup

# Scene generation endpoint
@router.post("/generate-prompts", response_model=SceneGenerationResponse)
async def generate_scene_prompts(
    request: SceneGenerationRequest,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Generate text-to-image prompts from story content using AI
    """
    try:
        user_email = getattr(current_user, 'email', None) or current_user.get('email', 'unknown') if isinstance(current_user, dict) else current_user.email
        logger.info(f"User {user_email} requesting {request.scene_count} scene prompts")
        logger.info(f"Text content length: {len(request.text)} characters")

        # Validate text content
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="Text content cannot be empty")

        if len(request.text.strip()) < 50:
            raise HTTPException(status_code=400, detail="Text content must be at least 50 characters long")

        # Initialize scene generation service
        scene_service = SceneGenerationService()

        # Generate scenes using AI
        scenes = await scene_service.generate_scene_prompts(
            text=request.text,
            scene_count=request.scene_count
        )

        logger.info(f"Successfully generated {len(scenes)} scenes for user {user_email}")

        return SceneGenerationResponse(
            scenes=scenes,
            total_scenes=len(scenes)
        )

    except Exception as e:
        logger.error(f"Scene generation failed for user {user_email}: {str(e)}")

        if isinstance(e, HTTPException):
            raise e

        # Generic error for unexpected issues
        raise HTTPException(
            status_code=500,
            detail="Failed to generate scene prompts. Please try again."
        )


@router.post("/generate-talking-scene-prompts", response_model=TalkingScenePromptResponse)
async def generate_talking_scene_prompts(
    request: TalkingScenePromptRequest,
    current_user: UserProfile = Depends(get_current_user)
):
    """Generate image prompts for talking scenes using Gemini."""
    try:
        user_email = getattr(current_user, 'email', None) or current_user.get('email', 'unknown') if isinstance(current_user, dict) else current_user.email
        logger.info(f"User {user_email} requesting Gemini talking-scene prompts for {len(request.scenes)} scenes")

        google_api_key = os.getenv("GOOGLE_API_KEY")
        if not google_api_key:
            raise HTTPException(status_code=500, detail="GOOGLE_API_KEY is not configured")

        client = create_google_genai_api_client(google_api_key)
        system_instruction = _build_talking_scene_prompt_system_instruction()
        user_prompt = _build_talking_scene_prompt_user_prompt(request)

        model_chain = list(dict.fromkeys([
            TALKING_SCENE_PROMPT_MODEL,
            TALKING_SCENE_PROMPT_FALLBACK_MODEL,
        ]))
        response = None
        last_error: Optional[Exception] = None

        for model_index, model_name in enumerate(model_chain):
            try:
                logger.info(
                    "[Gemini][talking-scene-prompts] user=%s calling model=%s",
                    user_email,
                    model_name,
                )
                response = client.models.generate_content(
                    model=model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.6,
                    ),
                    contents=user_prompt,
                )
                break
            except Exception as model_error:
                last_error = model_error
                has_next_model = model_index < len(model_chain) - 1
                if _is_gemini_overload_error(model_error) and has_next_model:
                    logger.warning(
                        "[Gemini][talking-scene-prompts] user=%s model=%s overloaded, falling back to %s",
                        user_email,
                        model_name,
                        model_chain[model_index + 1],
                    )
                    continue
                raise

        if response is None and last_error is not None:
            raise last_error

        parsed = extract_first_json_object((response.text or "").strip())
        scene_results = parsed.get("scenes") if isinstance(parsed, dict) else None
        if not isinstance(scene_results, list):
            raise ValueError("Gemini response missing scenes array")

        prompts_by_scene_id = {}
        for item in scene_results:
            if not isinstance(item, dict):
                continue
            scene_id = str(item.get("scene_id") or "").strip()
            prompt = str(item.get("prompt") or "").strip()
            if scene_id and prompt:
                prompts_by_scene_id[scene_id] = prompt

        results: List[TalkingScenePromptResult] = []
        missing_scene_ids: List[str] = []
        for scene in request.scenes:
            prompt = prompts_by_scene_id.get(scene.scene_id)
            if prompt:
                results.append(TalkingScenePromptResult(scene_id=scene.scene_id, prompt=prompt))
            else:
                missing_scene_ids.append(scene.scene_id)

        if missing_scene_ids:
            raise ValueError(f"Gemini did not return prompts for scenes: {', '.join(missing_scene_ids)}")

        return TalkingScenePromptResponse(
            scenes=results,
            total_scenes=len(results),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Talking-scene prompt generation failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to generate talking-scene prompts. Please try again."
        )


@router.post("/generate-animal-haircut-prompts", response_model=AnimalHaircutPromptResponse)
async def generate_animal_haircut_prompts(
    request: AnimalHaircutPromptRequest,
    current_user: UserProfile = Depends(get_current_user)
):
    """Generate the before/after/video prompt package for the animal haircut storyboard flow."""
    try:
        animal = request.animal.strip()
        haircut_style = request.haircut_style.strip()
        if not animal or not haircut_style:
            raise HTTPException(status_code=400, detail="Animal and haircut style are required")

        user_email = (
            getattr(current_user, 'email', None)
            or current_user.get('email', 'unknown') if isinstance(current_user, dict)
            else current_user.email
        )
        logger.info(
            "[Gemini][animal-haircut-prompts] user=%s animal=%s haircut=%s",
            user_email,
            animal,
            haircut_style,
        )

        google_api_key = os.getenv("GOOGLE_GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not google_api_key:
            raise HTTPException(status_code=500, detail="Google Gemini API key is not configured")

        client = create_google_genai_api_client(google_api_key)
        system_instruction = _build_animal_haircut_prompt_system_instruction()
        user_prompt = _build_animal_haircut_prompt_user_prompt(request)

        model_chain = list(dict.fromkeys([
            ANIMAL_HAIRCUT_PROMPT_MODEL,
            ANIMAL_HAIRCUT_PROMPT_FALLBACK_MODEL,
        ]))
        response = None
        last_error: Optional[Exception] = None

        for model_index, model_name in enumerate(model_chain):
            try:
                logger.info(
                    "[Gemini][animal-haircut-prompts] user=%s calling model=%s",
                    user_email,
                    model_name,
                )
                response = client.models.generate_content(
                    model=model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.7,
                        response_mime_type="application/json",
                    ),
                    contents=user_prompt,
                )
                break
            except Exception as model_error:
                last_error = model_error
                has_next_model = model_index < len(model_chain) - 1
                if _is_gemini_overload_error(model_error) and has_next_model:
                    logger.warning(
                        "[Gemini][animal-haircut-prompts] user=%s model=%s overloaded, falling back to %s",
                        user_email,
                        model_name,
                        model_chain[model_index + 1],
                    )
                    continue
                raise

        if response is None and last_error is not None:
            raise last_error

        raw_text = (response.text or "").strip()
        parsed = json.loads(raw_text) if raw_text.startswith("{") else extract_first_json_object(raw_text)
        if not isinstance(parsed, dict):
            raise ValueError("Gemini response was not a JSON object")

        required_fields = [
            "animal_name",
            "haircut_style",
            "haircut_description",
            "animal_appearance_details",
            "skin_color_and_markings",
        ]
        missing_fields = [field for field in required_fields if not str(parsed.get(field) or "").strip()]
        if missing_fields:
            raise ValueError(f"Gemini response missing required fields: {', '.join(missing_fields)}")

        return AnimalHaircutPromptResponse(
            animal_name=str(parsed["animal_name"]).strip(),
            haircut_style=str(parsed["haircut_style"]).strip(),
            haircut_description=str(parsed["haircut_description"]).strip(),
            animal_appearance_details=str(parsed["animal_appearance_details"]).strip(),
            first_image_prompt=_build_animal_haircut_first_image_prompt(
                animal,
                str(parsed["animal_appearance_details"]).strip(),
            ),
            second_image_prompt=_build_animal_haircut_second_image_prompt(
                animal,
                haircut_style,
                str(parsed["haircut_description"]).strip(),
                str(parsed["skin_color_and_markings"]).strip(),
            ),
            video_prompt=_build_animal_haircut_video_prompt(animal, haircut_style),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Animal haircut prompt generation failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to generate animal haircut prompts. Please try again."
        )

# Transcript-based scene generation endpoint (ASYNC VERSION)
@router.post("/generate-from-transcript", response_model=TaskInitiatedResponse)
async def generate_scenes_from_transcript(
    request: TranscriptSceneGenerationRequest,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Generate text-to-image prompts from transcript data with timing information.
    Returns immediately with a task_id. Poll /task-status/{task_id} for progress.
    """
    try:
        user_id = getattr(current_user, 'id', None) or current_user.get('id', None) if isinstance(current_user, dict) else current_user.id
        user_email = getattr(current_user, 'email', None) or current_user.get('email', 'unknown') if isinstance(current_user, dict) else current_user.email

        logger.info(f"User {user_email} requesting async transcript-based scene generation for project {request.project_id}")

        # Create a background task
        task_service = get_background_task_service()
        task_id = task_service.create_task(
            task_type="transcript_scene_generation",
            user_id=user_id,
            metadata={
                "project_id": request.project_id,
                "language_code": request.language_code,
                "agg_first_half": request.agg_first_half,
                "agg_second_half": request.agg_second_half,
                "cut_off": request.cut_off,
                "custom_prompt_instructions": request.custom_prompt_instructions
            }
        )

        # Start the background processing task
        task_service.start_background_task(
            task_id,
            process_transcript_scene_generation,
            task_id,
            request,
            user_id,
            user_email
        )

        logger.info(f"Started background task {task_id} for user {user_email}")

        # Return immediately with task_id
        return TaskInitiatedResponse(
            task_id=task_id,
            status=TaskStatus.PENDING,
            message="Scene generation started. Poll /api/scene-generation/task-status/{task_id} for progress."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initiate transcript-based scene generation for user {user_email}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to start scene generation task. Please try again."
        )

# Task status polling endpoint
@router.get("/task-status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Get the status of a background task.
    Poll this endpoint to check progress and get results when complete.
    """
    task_service = get_background_task_service()
    task_data = task_service.get_task(task_id)

    if not task_data:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found"
        )

    # Verify the task belongs to the current user
    user_id = getattr(current_user, 'id', None) or current_user.get('id', None) if isinstance(current_user, dict) else current_user.id
    if task_data.get("user_id") != user_id:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to access this task"
        )

    # Build the response
    response = TaskStatusResponse(
        task_id=task_data["task_id"],
        task_type=task_data["task_type"],
        status=task_data["status"],
        progress=task_data["progress"],
        message=task_data["message"],
        result=task_data.get("result"),
        error=task_data.get("error"),
        created_at=task_data["created_at"],
        updated_at=task_data["updated_at"]
    )

    return response

# Test endpoint to verify the router is working
@router.get("/test")
async def test_scene_generation():
    """Test endpoint to verify scene generation router is working"""
    return {
        "message": "Scene generation router is working",
        "status": "healthy"
    }
