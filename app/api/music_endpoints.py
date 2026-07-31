"""
Music API endpoints for preset background music selection

Provides endpoints for:
- Getting available preset music tracks
- Searching music by category/mood
- Getting music track details
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from config.preset_music import (
    PRESET_MUSIC_LIBRARY,
    get_music_by_category,
    get_music_by_mood,
    get_music_by_id,
    get_all_categories,
    get_all_moods,
    search_music,
    MusicCategory,
    MusicMood
)
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/music", tags=["music"])

class MusicTrack(BaseModel):
    id: str
    name: str
    description: str
    url: str
    duration: float
    category: str
    mood: str
    bpm: int
    tags: List[str]

class MusicLibraryResponse(BaseModel):
    tracks: List[MusicTrack]
    categories: List[str]
    moods: List[str]
    total_count: int

class MusicSearchResponse(BaseModel):
    tracks: List[MusicTrack]
    query: Optional[str]
    category: Optional[str]
    mood: Optional[str]
    total_count: int

@router.get("/library", response_model=MusicLibraryResponse)
async def get_music_library():
    """
    Get the complete preset music library
    
    Returns:
        Complete music library with tracks, categories, and moods
    """
    try:
        tracks = [MusicTrack(**track) for track in PRESET_MUSIC_LIBRARY]
        
        return MusicLibraryResponse(
            tracks=tracks,
            categories=get_all_categories(),
            moods=get_all_moods(),
            total_count=len(tracks)
        )
        
    except Exception as e:
        logger.error("Error fetching music library", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error fetching music library: {str(e)}")

@router.get("/search", response_model=MusicSearchResponse)
async def search_music_tracks(
    q: Optional[str] = Query(None, description="Search query (searches name, description, tags)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    mood: Optional[str] = Query(None, description="Filter by mood"),
    limit: Optional[int] = Query(50, description="Maximum number of results")
):
    """
    Search music tracks with filters
    
    Args:
        q: Search query string
        category: Filter by music category
        mood: Filter by music mood
        limit: Maximum number of results to return
        
    Returns:
        Filtered list of music tracks
    """
    try:
        # Validate category and mood if provided
        if category and category not in get_all_categories():
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
        
        if mood and mood not in get_all_moods():
            raise HTTPException(status_code=400, detail=f"Invalid mood: {mood}")
        
        # Search tracks
        results = search_music(query=q, category=category, mood=mood)
        
        # Apply limit
        if limit and len(results) > limit:
            results = results[:limit]
        
        tracks = [MusicTrack(**track) for track in results]
        
        return MusicSearchResponse(
            tracks=tracks,
            query=q,
            category=category,
            mood=mood,
            total_count=len(tracks)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error searching music tracks", error=str(e), query=q, category=category, mood=mood)
        raise HTTPException(status_code=500, detail=f"Error searching music: {str(e)}")

@router.get("/categories")
async def get_music_categories():
    """
    Get all available music categories
    
    Returns:
        List of category names with descriptions
    """
    try:
        categories = []
        for category in MusicCategory:
            # Get track count for this category
            tracks_in_category = get_music_by_category(category)
            
            categories.append({
                "value": category.value,
                "name": category.value.title(),
                "track_count": len(tracks_in_category)
            })
        
        return {"categories": categories}
        
    except Exception as e:
        logger.error("Error fetching music categories", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error fetching categories: {str(e)}")

@router.get("/moods")
async def get_music_moods():
    """
    Get all available music moods
    
    Returns:
        List of mood names with descriptions
    """
    try:
        moods = []
        for mood in MusicMood:
            # Get track count for this mood
            tracks_in_mood = get_music_by_mood(mood)
            
            moods.append({
                "value": mood.value,
                "name": mood.value.title(),
                "track_count": len(tracks_in_mood)
            })
        
        return {"moods": moods}
        
    except Exception as e:
        logger.error("Error fetching music moods", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error fetching moods: {str(e)}")

@router.get("/track/{track_id}", response_model=MusicTrack)
async def get_music_track(track_id: str):
    """
    Get details for a specific music track
    
    Args:
        track_id: ID of the music track
        
    Returns:
        Music track details
    """
    try:
        track_data = get_music_by_id(track_id)
        
        if not track_data:
            raise HTTPException(status_code=404, detail=f"Music track not found: {track_id}")
        
        return MusicTrack(**track_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching music track", error=str(e), track_id=track_id)
        raise HTTPException(status_code=500, detail=f"Error fetching track: {str(e)}")

@router.get("/featured")
async def get_featured_music(limit: int = Query(6, description="Number of featured tracks")):
    """
    Get featured/recommended music tracks
    
    Args:
        limit: Number of tracks to return
        
    Returns:
        List of featured music tracks
    """
    try:
        # For now, return a mix of different categories
        featured = []
        
        # Get one track from each category
        for category in MusicCategory:
            tracks_in_category = get_music_by_category(category)
            if tracks_in_category:
                featured.append(tracks_in_category[0])  # Take first track
                
                if len(featured) >= limit:
                    break
        
        tracks = [MusicTrack(**track) for track in featured[:limit]]
        
        return {
            "tracks": tracks,
            "total_count": len(tracks)
        }
        
    except Exception as e:
        logger.error("Error fetching featured music", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error fetching featured music: {str(e)}")

@router.get("/similar/{track_id}")
async def get_similar_music(track_id: str, limit: int = Query(4, description="Number of similar tracks")):
    """
    Get music tracks similar to the specified track
    
    Args:
        track_id: ID of the reference track
        limit: Number of similar tracks to return
        
    Returns:
        List of similar music tracks
    """
    try:
        reference_track = get_music_by_id(track_id)
        
        if not reference_track:
            raise HTTPException(status_code=404, detail=f"Reference track not found: {track_id}")
        
        # Find similar tracks by category and mood
        similar_tracks = []
        
        # First, try to find tracks in the same category
        category_tracks = get_music_by_category(reference_track["category"])
        for track in category_tracks:
            if track["id"] != track_id:
                similar_tracks.append(track)
        
        # If we need more, add tracks with the same mood
        if len(similar_tracks) < limit:
            mood_tracks = get_music_by_mood(reference_track["mood"])
            for track in mood_tracks:
                if track["id"] != track_id and track not in similar_tracks:
                    similar_tracks.append(track)
        
        # Limit results
        similar_tracks = similar_tracks[:limit]
        tracks = [MusicTrack(**track) for track in similar_tracks]
        
        return {
            "reference_track": MusicTrack(**reference_track),
            "similar_tracks": tracks,
            "total_count": len(tracks)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching similar music", error=str(e), track_id=track_id)
        raise HTTPException(status_code=500, detail=f"Error fetching similar music: {str(e)}")