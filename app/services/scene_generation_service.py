"""
Service for generating text-to-image scene prompts using AI
"""

import os
import json
import logging
from typing import List, Dict, Any
from google.genai import types
from dotenv import load_dotenv
from services.google_genai_client import create_google_genai_api_client

load_dotenv()

logger = logging.getLogger(__name__)

class SceneData:
    def __init__(self, description: str, prompt: str):
        self.description = description
        self.prompt = prompt

    def to_dict(self) -> Dict[str, str]:
        return {
            "description": self.description,
            "prompt": self.prompt
        }

class SceneGenerationService:
    def __init__(self):
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        if not self.google_api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")

        self.model = "gemini-2.5-flash"
        self.client = create_google_genai_api_client(self.google_api_key)

        logger.info("SceneGenerationService initialized successfully")

    async def generate_scene_prompts(self, text: str, scene_count: int) -> List[Dict[str, str]]:
        """
        Generate text-to-image prompts from story content using Gemini AI

        Args:
            text: The story text to analyze
            scene_count: Number of scenes to generate (1-10)

        Returns:
            List of scene dictionaries with description and prompt
        """
        try:
            logger.info(f"Generating {scene_count} scene prompts from {len(text)} character text")

            # Create the system prompt for scene generation
            system_prompt = self._build_system_prompt()

            # Create the user prompt with the story text
            user_prompt = self._build_user_prompt(text, scene_count)

            logger.debug(f"System prompt: {system_prompt[:200]}...")
            logger.debug(f"User prompt: {user_prompt[:200]}...")

            # Call Gemini API
            response = self.client.models.generate_content(
                model=self.model,
                config=types.GenerateContentConfig(system_instruction=system_prompt),
                contents=user_prompt
            )

            logger.info("Received response from Gemini API")

            # Parse the response
            scenes = self._parse_gemini_response(response.text, scene_count)

            logger.info(f"Successfully parsed {len(scenes)} scenes from AI response")

            return [scene.to_dict() for scene in scenes]

        except Exception as e:
            logger.error(f"Error generating scene prompts: {str(e)}")
            raise Exception(f"Failed to generate scene prompts: {str(e)}")

    def _build_system_prompt(self) -> str:
        """Build the system prompt for scene generation"""
        return """You are an expert at analyzing stories and creating detailed text-to-image prompts. Your task is to:

1. Analyze the provided story text
2. Identify key visual scenes that would make compelling images
3. Create detailed text-to-image prompts for each scene

Your prompts should be:
- Visually descriptive and detailed
- Suitable for text-to-image AI models (like google Gemini, Flux, Seadream, Minimax-image)
- Focused on the most visually interesting and important moments
- Include details about setting, characters, mood, lighting
- Only generate images that reflect reality, do not generate images that are not possible in real life
- Avoid including style
- Each prompt should be 2-3 sentences long

CRITICAL: Respond ONLY with valid JSON. Do not include any text before or after the JSON. Do not include any comments, explanations, or markdown formatting.

Use this exact structure:
{
  "scenes": [
    {
      "description": "Brief description of what happens in this scene",
      "prompt": "Detailed text-to-image prompt for generating this scene"
    }
  ]
}"""

    def _build_user_prompt(self, text: str, scene_count: int) -> str:
        """Build the user prompt with story text and scene count"""
        return f"""Please analyze this story and create {scene_count} distinct visual scenes with text-to-image prompts:

Story text:
{text}

Generate {scene_count} scenes that capture the most visually interesting and important moments from this story. Each scene should have a brief description and a detailed text-to-image prompt that would generate a compelling image representing that moment.

IMPORTANT: Respond with valid JSON only. No additional text, comments, or explanations."""

    def _parse_gemini_response(self, response_text: str, expected_count: int) -> List[SceneData]:
        """Parse the Gemini API response and extract scene data"""
        try:
            logger.debug(f"Parsing response: {response_text[:500]}...")

            # Clean up the response text - remove markdown code blocks if present
            cleaned_text = response_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()

            # Parse JSON
            try:
                parsed_data = json.loads(cleaned_text)
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
                logger.error(f"Response text: {cleaned_text}")
                # Try to fix common JSON issues
                cleaned_text = self._fix_common_json_issues(cleaned_text)
                parsed_data = json.loads(cleaned_text)

            # Extract scenes
            if "scenes" not in parsed_data:
                raise ValueError("Response does not contain 'scenes' field")

            scenes_data = parsed_data["scenes"]
            if not isinstance(scenes_data, list):
                raise ValueError("'scenes' field is not a list")

            scenes = []
            for i, scene_data in enumerate(scenes_data):
                if not isinstance(scene_data, dict):
                    logger.warning(f"Scene {i} is not a dictionary, skipping")
                    continue

                description = scene_data.get("description", "").strip()
                prompt = scene_data.get("prompt", "").strip()

                if not description or not prompt:
                    logger.warning(f"Scene {i} missing description or prompt, skipping")
                    continue

                scenes.append(SceneData(description=description, prompt=prompt))

            if len(scenes) == 0:
                raise ValueError("No valid scenes found in response")

            logger.info(f"Successfully parsed {len(scenes)} scenes")
            return scenes

        except Exception as e:
            logger.error(f"Error parsing Gemini response: {str(e)}")
            # Fallback: create default scenes if parsing fails
            return self._create_fallback_scenes(expected_count)

    def _fix_common_json_issues(self, text: str) -> str:
        """Fix common JSON formatting issues"""
        import re

        # Remove any trailing commas before closing brackets/braces
        text = re.sub(r',(\s*[}\]])', r'\1', text)

        # Try to extract valid JSON if there's corrupted content
        # Look for the main JSON structure starting with { and ending with }
        start_match = re.search(r'^\s*{', text)
        if start_match:
            # Find the last } that closes the main object
            brace_count = 0
            last_valid_pos = len(text)

            for i, char in enumerate(text[start_match.start():], start_match.start()):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        last_valid_pos = i + 1
                        break

            # Extract only the valid JSON portion
            text = text[start_match.start():last_valid_pos]

        # Remove any line breaks within quoted strings that might break JSON
        # This is a simple fix - in practice, more sophisticated parsing might be needed
        text = re.sub(r'"\s*\n\s*([^"]*?)"\s*}', r'"\1"}', text, flags=re.DOTALL)

        # Fix malformed strings that end abruptly
        # Look for patterns like: "text" extra_text."
        text = re.sub(r'"([^"]*?)"\s+[^,}\]]+\.?"', r'"\1"', text)

        # Clean up any obvious text injections in JSON strings
        # Pattern: text that appears after a closing quote but before comma/brace
        text = re.sub(r'"\s*([^"]*?)\s*"\s+[^,}\]]*?"', r'"\1"', text)

        return text

    def _create_fallback_scenes(self, scene_count: int) -> List[SceneData]:
        """Create fallback scenes if AI response parsing fails"""
        logger.warning("Creating fallback scenes due to parsing failure")

        fallback_scenes = []
        for i in range(min(scene_count, 3)):  # Maximum 3 fallback scenes
            fallback_scenes.append(SceneData(
                description=f"Scene {i+1} from the story",
                prompt=f"A cinematic scene depicting an important moment from a story, dramatic lighting, detailed environment, high quality digital art"
            ))

        return fallback_scenes
