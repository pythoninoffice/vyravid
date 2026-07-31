"""
Translation service using Google Gemini API
"""

import logging
from typing import Optional
from google.genai import types
from config import get_settings
from services.google_genai_client import create_google_genai_api_client

logger = logging.getLogger(__name__)

class TranslationService:
    def __init__(self):
        self.settings = get_settings()

        # Use the same API key as the scene generation service
        self.google_api_key = self.settings.google_api_key
        if not self.google_api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")

        self.model = "gemini-flash-latest"
        self.client = create_google_genai_api_client(self.google_api_key)

        logger.info("TranslationService initialized successfully")

    async def translate_text(self, text: str, target_language: str) -> str:
        """
        Translate text to the target language using Gemini AI

        Args:
            text: The text to translate
            target_language: The target language (e.g., "Chinese", "Spanish", "French")

        Returns:
            Translated text
        """
        try:
            logger.info(f"Translating {len(text)} characters to {target_language}")

            # Create the system prompt for translation
            system_prompt = self._build_system_prompt(target_language)

            # Create the user prompt with the text to translate
            user_prompt = f"Please translate the following text:\n\n{text}"

            logger.debug(f"System prompt: {system_prompt}")
            logger.debug(f"User prompt: {user_prompt[:200]}...")

            # Call Gemini API
            response = self.client.models.generate_content(
                model=self.model,
                config=types.GenerateContentConfig(system_instruction=system_prompt),
                contents=user_prompt
            )

            logger.info("Received response from Gemini API")

            # Return the translated text
            translated_text = response.text.strip()

            logger.info(f"Successfully translated text to {target_language}")

            return translated_text

        except Exception as e:
            logger.error(f"Error translating text: {str(e)}")
            raise Exception(f"Failed to translate text: {str(e)}")

    async def translate_video_script(
        self,
        text: str,
        source_language: str,
        target_language: str
    ) -> dict:
        """
        Translate video script with awareness of timing and voiceover requirements

        Args:
            text: The video script to translate
            source_language: Source language name (e.g., "English")
            target_language: Target language name (e.g., "Chinese")

        Returns:
            dict with:
                - translated_text: The translated script
                - original_length: Character count of original
                - translated_length: Character count of translation
                - estimated_duration_ratio: Ratio of translated/original duration
        """
        try:
            logger.info(f"Translating video script from {source_language} to {target_language}")

            system_prompt = f"""You are an expert translator specializing in video scripts and voiceover content.
Your task is to translate video scripts from {source_language} to {target_language}.

CRITICAL REQUIREMENTS for video script translation:
1. Maintain natural speech patterns suitable for voiceover narration
2. Keep similar sentence length when possible to help with timing synchronization
3. Use conversational, spoken language (not formal written language)
4. Preserve the pacing and rhythm of the original script
5. Ensure cultural appropriateness and natural flow for {target_language} audiences
6. Maintain any formatting (line breaks, punctuation)
7. Optimize for how it will SOUND when spoken, not just how it reads

DO NOT:
- Add explanations, comments, or notes
- Change the meaning or tone
- Make the translation overly formal if the original is casual
- Add or remove sentences

Return ONLY the translated text, nothing else."""

            user_prompt = f"Translate this video script:\n\n{text}"

            response = self.client.models.generate_content(
                model=self.model,
                config=types.GenerateContentConfig(system_instruction=system_prompt),
                contents=user_prompt
            )

            translated_text = response.text.strip()

            # Calculate metrics
            original_words = len(text.split())
            translated_words = len(translated_text.split())
            duration_ratio = translated_words / original_words if original_words > 0 else 1.0

            logger.info(f"Video script translation complete. Duration ratio: {duration_ratio:.2f}")

            return {
                "translated_text": translated_text,
                "original_length": len(text),
                "translated_length": len(translated_text),
                "original_word_count": original_words,
                "translated_word_count": translated_words,
                "estimated_duration_ratio": duration_ratio
            }

        except Exception as e:
            logger.error(f"Error translating video script: {str(e)}")
            raise Exception(f"Failed to translate video script: {str(e)}")

    def _build_system_prompt(self, target_language: str) -> str:
        """Build the system prompt for translation"""
        return f"""You are an expert translator. Your task is to translate the provided text into {target_language}.

Instructions:
- Provide accurate, natural-sounding translations
- Preserve the original meaning and tone
- Maintain formatting (line breaks, punctuation, etc.)
- For creative content like stories, ensure the translation flows naturally in {target_language}
- If the text is already in {target_language}, return it unchanged
- Do not add explanations, comments, or any additional text
- Return only the translated text

Target language: {target_language}"""
