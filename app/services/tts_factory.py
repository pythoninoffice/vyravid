from typing import Union, Dict, List, Any
from enum import Enum

from services.tts_service import TTSService
from services.google_tts_service import GoogleTTSService


class TTSProvider(str, Enum):
    MINIMAX = "minimax"
    GOOGLE = "google"


class TTSServiceFactory:
    """Factory for creating TTS service instances based on provider"""

    @staticmethod
    def create_service(provider: TTSProvider) -> Union[TTSService, GoogleTTSService]:
        """
        Create a TTS service instance for the specified provider

        Args:
            provider: The TTS provider to use

        Returns:
            TTS service instance

        Raises:
            ValueError: If provider is not supported
        """
        if provider == TTSProvider.MINIMAX:
            return TTSService()
        elif provider == TTSProvider.GOOGLE:
            return GoogleTTSService()
        else:
            raise ValueError(f"Unsupported TTS provider: {provider}")

    @staticmethod
    def get_available_voices(provider: TTSProvider = None) -> List[Dict[str, Any]]:
        """
        Get available voices for a specific provider or all providers

        Args:
            provider: Specific provider to get voices for, or None for all

        Returns:
            List of voice dictionaries with provider information
        """
        voices = []

        if provider is None or provider == TTSProvider.MINIMAX:
            # Get Minimax voices (comprehensive list based on API documentation and usage)
            minimax_voices = [
                # Female Voices
                {
                    "voice_id": "English_MatureBoss",
                    "name": "Charlotte",
                    "language": "English",
                    "gender": "Female",
                    "description": "Professional Female",
                    "provider": "minimax"
                },
                {
                    "voice_id": "English_Upbeat_Woman",
                    "name": "Emma",
                    "language": "English",
                    "gender": "Female",
                    "description": "Upbeat Female",
                    "provider": "minimax"
                },
                {
                    "voice_id": "Wise_Woman",
                    "name": "Sophia",
                    "language": "English",
                    "gender": "Female",
                    "description": "Wise Woman",
                    "provider": "minimax"
                },
                {
                    "voice_id": "English_AnimeCharacter",
                    "name": "Aria",
                    "language": "English",
                    "gender": "Female",
                    "description": "Anime Character Voice",
                    "provider": "minimax"
                },
                {
                    "voice_id": "English_Lyrical_Voice",
                    "name": "Melody",
                    "language": "English",
                    "gender": "Female",
                    "description": "Lyrical Voice",
                    "provider": "minimax"
                },
                {
                    "voice_id": "English_Gentle_Woman",
                    "name": "Grace",
                    "language": "English",
                    "gender": "Female",
                    "description": "Gentle Woman",
                    "provider": "minimax"
                },
                {
                    "voice_id": "English_Confident_Woman",
                    "name": "Victoria",
                    "language": "English",
                    "gender": "Female",
                    "description": "Confident Woman",
                    "provider": "minimax"
                },
                # Male Voices
                {
                    "voice_id": "English_Debator",
                    "name": "David",
                    "language": "English",
                    "gender": "Male",
                    "description": "Tough Male",
                    "provider": "minimax"
                },
                {
                    "voice_id": "English_magnetic_voiced_man",
                    "name": "Charlie",
                    "language": "English",
                    "gender": "Male",
                    "description": "Magnetic Voice Male",
                    "provider": "minimax"
                },
                {
                    "voice_id": "English_ManWithDeepVoice",
                    "name": "Marcus",
                    "language": "English",
                    "gender": "Male",
                    "description": "Deep Voice Male",
                    "provider": "minimax"
                },
                {
                    "voice_id": "English_Insightful_Speaker",
                    "name": "Alexander",
                    "language": "English",
                    "gender": "Male",
                    "description": "Insightful Speaker",
                    "provider": "minimax"
                },
                {
                    "voice_id": "English_expressive_narrator",
                    "name": "Samuel",
                    "language": "English",
                    "gender": "Male",
                    "description": "Expressive Narrator",
                    "provider": "minimax"
                },
                {
                    "voice_id": "audiobook_male_1",
                    "name": "Nathan",
                    "language": "English",
                    "gender": "Male",
                    "description": "Audiobook Male Voice",
                    "provider": "minimax"
                },
                {
                    "voice_id": "English_Calm_Man",
                    "name": "Oliver",
                    "language": "English",
                    "gender": "Male",
                    "description": "Calm Man",
                    "provider": "minimax"
                },
                {
                    "voice_id": "English_Energetic_Man",
                    "name": "Ryan",
                    "language": "English",
                    "gender": "Male",
                    "description": "Energetic Man",
                    "provider": "minimax"
                },
                {
                    "voice_id": "English_Professional_Man",
                    "name": "James",
                    "language": "English",
                    "gender": "Male",
                    "description": "Professional Man",
                    "provider": "minimax"
                },
                {
                    "voice_id": "English_Storyteller",
                    "name": "Benjamin",
                    "language": "English",
                    "gender": "Male",
                    "description": "Storyteller Voice",
                    "provider": "minimax"
                },
                # Chinese Voices (for multilingual support)
                {
                    "voice_id": "Chinese (Mandarin)_Warm_Girl",
                    "name": "Mei",
                    "language": "Chinese (Mandarin)",
                    "gender": "Female",
                    "description": "Warm Girl Voice",
                    "provider": "minimax"
                },
                {
                    "voice_id": "Chinese (Mandarin)_Stubborn_Friend",
                    "name": "Wei",
                    "language": "Chinese (Mandarin)",
                    "gender": "Male",
                    "description": "Stubborn Friend Voice",
                    "provider": "minimax"
                },
                {
                    "voice_id": "Chinese (Mandarin)_Humorous_Elder",
                    "name": "Lao",
                    "language": "Chinese (Mandarin)",
                    "gender": "Male",
                    "description": "Humorous Elder Voice",
                    "provider": "minimax"
                }
            ]
            voices.extend(minimax_voices)

        if provider is None or provider == TTSProvider.GOOGLE:
            # Get Google voices
            google_voices = GoogleTTSService.get_available_voices()
            voices.extend(google_voices)

        return voices

    @staticmethod
    def get_default_provider() -> TTSProvider:
        """Get the default TTS provider"""
        return TTSProvider.MINIMAX


def get_tts_service(provider: str = None) -> Union[TTSService, GoogleTTSService]:
    """
    Convenience function to get a TTS service instance

    Args:
        provider: Provider string ('minimax' or 'google'), defaults to minimax

    Returns:
        TTS service instance
    """
    if provider is None:
        provider = TTSProvider.MINIMAX.value

    try:
        tts_provider = TTSProvider(provider.lower())
        return TTSServiceFactory.create_service(tts_provider)
    except ValueError:
        raise ValueError(f"Unsupported TTS provider: {provider}. Use 'minimax' or 'google'.")
