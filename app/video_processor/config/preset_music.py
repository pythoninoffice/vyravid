"""
Preset Music Configuration for Cloud Video Processor

This module defines the available background music tracks that can be selected by ID.
All music files are stored in local media storage under data/storage/music.
"""

from typing import List, Dict, Any, Optional
from enum import Enum
import os
from pathlib import Path
from urllib.parse import urlparse

from local.constants import STORAGE_ROOT

MEDIA_BASE_URL = os.getenv("VYRAVID_PUBLIC_BASE", "http://localhost:8000").rstrip("/") + "/media/"

class MusicCategory(str, Enum):
    UPBEAT = "upbeat"
    AMBIENT = "ambient" 
    CINEMATIC = "cinematic"
    ELECTRONIC = "electronic"
    ACOUSTIC = "acoustic"
    CORPORATE = "corporate"
    GAMING = "gaming"
    YOUTUBE="youtube"

class MusicMood(str, Enum):
    ENERGETIC = "energetic"
    CALM = "calm"
    INSPIRING = "inspiring"
    MYSTERIOUS = "mysterious"
    HAPPY = "happy"
    SERIOUS = "serious"
    EPIC = "epic"

# Preset music library - Replace with your actual local music files
# Preset music library - Update these URLs with your actual local music files
PRESET_MUSIC_LIBRARY = [
    {
        "id": "boogie_down",
        "name": "Boogie Down",
        "description": "High energy track perfect for tech and gaming content",
        "url": f"{MEDIA_BASE_URL}music/boogie-down.mp3",
        "duration": 180.0,  # 3 minutes
        "category": MusicCategory.UPBEAT.value,
        "mood": MusicMood.ENERGETIC.value,
        "bpm": 128,
        "tags": ["tech", "gaming", "motivation", "workout"]
    },
    {
        "id": "ambient_calm_01", 
        "name": "Peaceful Thoughts",
        "description": "Calm ambient background for storytelling and meditation",
        "url": f"{MEDIA_BASE_URL}music/futile-room.mp3",
        "duration": 240.0,  # 4 minutes
        "category": MusicCategory.AMBIENT.value,
        "mood": MusicMood.CALM.value,
        "bpm": 70,
        "tags": ["meditation", "relaxation", "background", "soft"]
    },
    {
        "id": "cinematic_epic_01",
        "name": "Epic Journey",
        "description": "Cinematic orchestral piece for dramatic storytelling",
        "url": f"{MEDIA_BASE_URL}music/ruff-money.mp3", 
        "duration": 200.0,  # 3:20
        "category": MusicCategory.CINEMATIC.value,
        "mood": MusicMood.EPIC.value,
        "bpm": 90,
        "tags": ["orchestral", "dramatic", "adventure", "movie"]
    },
    {
        "id": "suspense_tension_building",
        "name": "Suspense 1",
        "description": "Suspense 1",
        "url": f"{MEDIA_BASE_URL}music/suspense-tension-building-401925.mp3",
        "duration": 195.0,  # 3:15
        "category": MusicCategory.ELECTRONIC.value,
        "mood": MusicMood.INSPIRING.value,
        "bpm": 120,
        "tags": ["technology", "innovation", "futuristic", "synth"]
    },
    {
        "id": "suspense_tension_building_2",
        "name": "Suspense 2",
        "description": "Suspense 2",
        "url": f"{MEDIA_BASE_URL}music/suspense-tension-trailer-398329.mp3",
        "duration": 165.0,  # 2:45
        "category": MusicCategory.ACOUSTIC.value,
        "mood": MusicMood.HAPPY.value,
        "bpm": 110,
        "tags": ["guitar", "lifestyle", "positive", "organic"]
    },
    {
        "id": "beethoven_moonlight_sonata",
        "name": "Beethoven Moonlight Sonata",
        "description": "Beethoven Moonlight Sonata",
        "url": f"{MEDIA_BASE_URL}music/beethoven-moonlight-sonata-op-27-nr-2-concert-grand-version-227468.mp3",
        "duration": 165.0,  # 2:45
        "category": MusicCategory.ACOUSTIC.value,
        "mood": MusicMood.CALM.value,
        "bpm": 110,
        "tags": ["classical", "lifestyle", "positive", "organic"]
    },


    {
        "id": "brain_implant_cyberpunk_sci_fi_trailer_action_intro",
        "name": "Cyberpunk Sci-Fi",
        "description": "Cyberpunk Sci-Fi",
        "url": f"{MEDIA_BASE_URL}music/brain-implant-cyberpunk-sci-fi-trailer-action-intro-330416.mp3",
        "duration": 165.0,  # 2:45
        "category": MusicCategory.ACOUSTIC.value,
        "mood": MusicMood.EPIC.value,
        "bpm": 110,
        "tags": ["sci-fi", "cyberpunk", "trailer", "action"]
    },

    {
        "id": "happy_day",
        "name": "Happy Day",
        "description": "Happy Day",
        "url": f"{MEDIA_BASE_URL}music/happy-day-148320.mp3",
        "duration": 165.0,  # 2:45
        "category": MusicCategory.ACOUSTIC.value,
        "mood": MusicMood.HAPPY.value,
        "bpm": 110,
        "tags": ["happy", "day", "positive", "organic"]
    },

    {
        "id": "unlimited_motivation",
        "name": "Unlimited Motivation",
        "description": "Unlimited Motivation",
        "url": f"{MEDIA_BASE_URL}music/unlimited-motivation-158250.mp3",
        "duration": 165.0,  # 2:45
        "category": MusicCategory.ACOUSTIC.value,
        "mood": MusicMood.INSPIRING.value,
        "bpm": 110,
        "tags": ["motivation", "positive", "organic"]
    },

    {
        "id": "Bethoven-legacy",
        "name": "Beethoven Legacy",
        "description": "Beethoven Legacy",
        "url": f"{MEDIA_BASE_URL}music/legacy-of-beethoven-background-music-for-video-stories-short-1-401052.mp3",
        "duration": 165.0,  # 2:45
        "category": MusicCategory.ACOUSTIC.value,
        "mood": MusicMood.EPIC.value,
        "bpm": 110,
        "tags": ["classical", "lifestyle", "positive", "organic", "epic"]
    },

    {
        "id": "mozart-legacy",
        "name": "Mozart Legacy",
        "description": "Mozart Legacy",
        "url": f"{MEDIA_BASE_URL}music/legacy-of-mozart-turkish-march-background-house-music-for-video-401046.mp3",
        "duration": 165.0,  # 2:45
        "category": MusicCategory.ACOUSTIC.value,
        "mood": MusicMood.EPIC.value,
        "bpm": 110,
        "tags": ["classical", "lifestyle", "positive", "organic", "epic"]
    },

    {
        "id": "paganini-legacy",
        "name": "Paganini Legacy",
        "description": "Paganini Legacy",
        "url": f"{MEDIA_BASE_URL}music/legendary-paganini-caprice-background-house-music-for-video-short-401050.mp3",
        "duration": 165.0,  # 2:45
        "category": MusicCategory.ACOUSTIC.value,
        "mood": MusicMood.EPIC.value,
        "bpm": 110,
        "tags": ["classical", "lifestyle", "positive", "organic", "epic"]
    },
    {
        "id": "chaos-full",
        "name": "Chaos Full",
        "description": "Chaos Full",
        "url": f"{MEDIA_BASE_URL}music/chaos-full.mp3",
        "duration": 165.0,  # 2:45
        "category": MusicCategory.ACOUSTIC.value,
        "mood": MusicMood.EPIC.value,
        "bpm": 110,
        "tags": ["dark"]
    },
    {
        "id": "road-to-peach",
        "name": "Road to Peace",
        "description": "Road to Peace",
        "url": f"{MEDIA_BASE_URL}music/road-to-peace.mp3",
        "duration": 165.0,  # 2:45
        "category": MusicCategory.ACOUSTIC.value,
        "mood": MusicMood.EPIC.value,
        "bpm": 110,
        "tags": ["dark"]
    },
        {
        "id": "epic-piano-music-for-short",
        "name": "Epic Piano Music For Shorts",
        "description": "Epic Piano Music For Shorts",
        "url": f"{MEDIA_BASE_URL}music/background-epic-piano-music-for-short-video.mp3",
        "duration": 165.0,  # 2:45
        "category": MusicCategory.ACOUSTIC.value,
        "mood": MusicMood.EPIC.value,
        "bpm": 110,
        "tags": ["dark"]
    },
    {
        "id": "soft-piano-music",
        "name": "Soft Piano Music",
        "description": "Soft Piano Music",
        "url": f"{MEDIA_BASE_URL}music/soft-piano-music.mp3",
        "duration": 165.0,  # 2:45
        "category": MusicCategory.ACOUSTIC.value,
        "mood": MusicMood.EPIC.value,
        "bpm": 110,
        "tags": ["dark"]
    },
    {
    "id": "a-stroll",
    "name": "A Stroll",
    "description": "A Stroll",
    "url": f"{MEDIA_BASE_URL}music/a-stroll.mp3",
    "duration": 0.0,
    "category": MusicCategory.YOUTUBE.value,
    "mood": MusicMood.CALM.value,
    "bpm": 0,
    "tags": []
    },
    {
        "id": "aurora-on-the-boulevard",
        "name": "Aurora On The Boulevard",
        "description": "Aurora On The Boulevard",
        "url": f"{MEDIA_BASE_URL}music/aurora-on-the-boulevard.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "beast-mode",
        "name": "Beast Mode",
        "description": "Beast Mode",
        "url": f"{MEDIA_BASE_URL}music/beast-mode.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "dead-wrong",
        "name": "Dead Wrong",
        "description": "Dead Wrong",
        "url": f"{MEDIA_BASE_URL}music/dead-wrong.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "deep-space-sector-9",
        "name": "Deep Space Sector 9",
        "description": "Deep Space Sector 9",
        "url": f"{MEDIA_BASE_URL}music/deep-space-sector-9.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "deified",
        "name": "Deified",
        "description": "Deified",
        "url": f"{MEDIA_BASE_URL}music/deified.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "epic-battle-speech",
        "name": "Epic Battle Speech",
        "description": "Epic Battle Speech",
        "url": f"{MEDIA_BASE_URL}music/epic-battle-speech.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "everything-has-a-beginning",
        "name": "Everything Has A Beginning",
        "description": "Everything Has A Beginning",
        "url": f"{MEDIA_BASE_URL}music/everything-has-a-beginning.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "frodos-quest",
        "name": "Frodos Quest",
        "description": "Frodos Quest",
        "url": f"{MEDIA_BASE_URL}music/frodos-quest.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "future",
        "name": "Future",
        "description": "Future",
        "url": f"{MEDIA_BASE_URL}music/future.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "heaven-and-hell",
        "name": "Heaven And Hell",
        "description": "Heaven And Hell",
        "url": f"{MEDIA_BASE_URL}music/heaven-and-hell.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "level",
        "name": "Level",
        "description": "Level",
        "url": f"{MEDIA_BASE_URL}music/level.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "light-years-away",
        "name": "Light Years Away",
        "description": "Light Years Away",
        "url": f"{MEDIA_BASE_URL}music/light-years-away.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "midnight-trace",
        "name": "Midnight Trace",
        "description": "Midnight Trace",
        "url": f"{MEDIA_BASE_URL}music/midnight-trace.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "mission-to-mars",
        "name": "Mission To Mars",
        "description": "Mission To Mars",
        "url": f"{MEDIA_BASE_URL}music/mission-to-mars.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "mysterious-strange-things",
        "name": "Mysterious Strange Things",
        "description": "Mysterious Strange Things",
        "url": f"{MEDIA_BASE_URL}music/mysterious-strange-things.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "nebula",
        "name": "Nebula",
        "description": "Nebula",
        "url": f"{MEDIA_BASE_URL}music/nebula.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "pawn",
        "name": "Pawn",
        "description": "Pawn",
        "url": f"{MEDIA_BASE_URL}music/pawn.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "racecar",
        "name": "Racecar",
        "description": "Racecar",
        "url": f"{MEDIA_BASE_URL}music/racecar.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "reviver",
        "name": "Reviver",
        "description": "Reviver",
        "url": f"{MEDIA_BASE_URL}music/reviver.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "space-trooper",
        "name": "Space Trooper",
        "description": "Space Trooper",
        "url": f"{MEDIA_BASE_URL}music/space-trooper.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "spookster",
        "name": "Spookster",
        "description": "Spookster",
        "url": f"{MEDIA_BASE_URL}music/spookster.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "steps",
        "name": "Steps",
        "description": "Steps",
        "url": f"{MEDIA_BASE_URL}music/steps.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "video-game-soldiers",
        "name": "Video Game Soldiers",
        "description": "Video Game Soldiers",
        "url": f"{MEDIA_BASE_URL}music/video-game-soldiers.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "violin-huasteco",
        "name": "Violin Huasteco",
        "description": "Violin Huasteco",
        "url": f"{MEDIA_BASE_URL}music/violin-huasteco.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },
    {
        "id": "way-back-when",
        "name": "Way Back When",
        "description": "Way Back When",
        "url": f"{MEDIA_BASE_URL}music/way-back-when.mp3",
        "duration": 0.0,
        "category": MusicCategory.YOUTUBE.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": []
    },



    
    {
        "id": "no_music",
        "name": "No Background Music",
        "description": "Generate video without background music",
        "url": "",  # Empty URL = no music
        "duration": 0.0,
        "category": MusicCategory.AMBIENT.value,
        "mood": MusicMood.CALM.value,
        "bpm": 0,
        "tags": ["silent", "no-music"]
    }
]

def _local_music_exists(track: Dict[str, Any]) -> bool:
    url = track.get("url") or ""
    if not url:
        return True
    filename = Path(urlparse(url).path).name
    return bool(filename) and (STORAGE_ROOT / "music" / filename).is_file()

PRESET_MUSIC_LIBRARY = [track for track in PRESET_MUSIC_LIBRARY if _local_music_exists(track)]

def get_music_by_id(music_id: str) -> Optional[Dict[str, Any]]:
    """Get music track by ID"""
    for track in PRESET_MUSIC_LIBRARY:
        if track["id"] == music_id:
            return track
    return None

def get_music_url_by_id(music_id: str) -> Optional[str]:
    """Get music URL by ID"""
    track = get_music_by_id(music_id)
    return track["url"] if track else None

# Default music options for video processing
DEFAULT_MUSIC_OPTIONS = {
    "volume": 0.25,           # 25% volume for background music
    "fade_in_duration": 2.0,  # 2 second fade in
    "fade_out_duration": 3.0, # 3 second fade out
    "loop_music": True,       # Loop if music is shorter than video
    "duck_during_speech": False, # Don't duck music during speech (simple mixing)
    "mix_mode": "background"  # Mix as background, not overlay
}
