from typing import Generic, TypeVar, Type, List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, or_, desc, asc
from uuid import UUID
from datetime import datetime

from .database import Base
from .story_models import (
    StoryDB, CommentDB, ProcessedStoryDB, AudioFileDB, 
    CaptionDB, VideoFileDB, VideoProcessingJobDB,
    ProcessingStatus, GenerationStatus
)
from models.story_models import (
    Story, Comment, ProcessedStory, AudioFile, 
    Caption, VideoFile, VideoProcessingJob
)

# Utility functions to convert between DB models and Pydantic models
def db_to_pydantic_story(db_story: StoryDB) -> Story:
    """Convert SQLAlchemy Story model to Pydantic model."""
    return Story.from_orm(db_story)

def db_to_pydantic_comment(db_comment: CommentDB) -> Comment:
    """Convert SQLAlchemy Comment model to Pydantic model."""
    return Comment.from_orm(db_comment)

def db_to_pydantic_processed_story(db_processed_story: ProcessedStoryDB) -> ProcessedStory:
    """Convert SQLAlchemy ProcessedStory model to Pydantic model."""
    return ProcessedStory.from_orm(db_processed_story)

def db_to_pydantic_audio_file(db_audio_file: AudioFileDB) -> AudioFile:
    """Convert SQLAlchemy AudioFile model to Pydantic model."""
    return AudioFile.from_orm(db_audio_file)

def db_to_pydantic_caption(db_caption: CaptionDB) -> Caption:
    """Convert SQLAlchemy Caption model to Pydantic model."""
    return Caption.from_orm(db_caption)

def db_to_pydantic_video_file(db_video_file: VideoFileDB) -> VideoFile:
    """Convert SQLAlchemy VideoFile model to Pydantic model."""
    return VideoFile.from_orm(db_video_file)

def db_to_pydantic_video_job(db_video_job: VideoProcessingJobDB) -> VideoProcessingJob:
    """Convert SQLAlchemy VideoProcessingJob model to Pydantic model."""
    # Handle the many-to-many relationship for background_video_ids
    background_video_ids = [video.id for video in db_video_job.background_videos]
    
    job_dict = {
        "id": db_video_job.id,
        "audio_file_id": db_video_job.audio_file_id,
        "background_video_ids": background_video_ids,
        "caption_file_path": db_video_job.caption_file_path,
        "output_file_path": db_video_job.output_file_path,
        "status": db_video_job.status,
        "progress": db_video_job.progress,
        "error_message": db_video_job.error_message,
        "processing_options": db_video_job.processing_options,
        "created_at": db_video_job.created_at,
        "started_at": db_video_job.started_at,
        "completed_at": db_video_job.completed_at,
    }
    
    return VideoProcessingJob(**job_dict)

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")

class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get(self, db: Session, id: UUID) -> Optional[ModelType]:
        return db.query(self.model).filter(self.model.id == id).first()

    def get_multi(
        self, 
        db: Session, 
        *, 
        skip: int = 0, 
        limit: int = 100,
        order_by: str = "created_at",
        order_desc: bool = True
    ) -> List[ModelType]:
        query = db.query(self.model)
        
        # Apply ordering
        if hasattr(self.model, order_by):
            order_column = getattr(self.model, order_by)
            if order_desc:
                query = query.order_by(desc(order_column))
            else:
                query = query.order_by(asc(order_column))
        
        return query.offset(skip).limit(limit).all()

    def create(self, db: Session, *, obj_in: CreateSchemaType) -> ModelType:
        obj_data = obj_in.dict() if hasattr(obj_in, 'dict') else obj_in
        db_obj = self.model(**obj_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self, 
        db: Session, 
        *, 
        db_obj: ModelType, 
        obj_in: UpdateSchemaType
    ) -> ModelType:
        obj_data = obj_in.dict(exclude_unset=True) if hasattr(obj_in, 'dict') else obj_in
        for field, value in obj_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, *, id: UUID) -> ModelType:
        obj = db.query(self.model).get(id)
        db.delete(obj)
        db.commit()
        return obj

class StoryRepository(BaseRepository[StoryDB, Dict[str, Any], Dict[str, Any]]):
    def get_by_reddit_id(self, db: Session, reddit_id: str) -> Optional[StoryDB]:
        return db.query(StoryDB).filter(StoryDB.reddit_id == reddit_id).first()
    
    def get_by_subreddit(
        self, 
        db: Session, 
        subreddit: str, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[StoryDB]:
        return (
            db.query(StoryDB)
            .filter(StoryDB.subreddit == subreddit)
            .order_by(desc(StoryDB.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def search_stories(
        self, 
        db: Session, 
        query: str, 
        subreddits: Optional[List[str]] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[StoryDB]:
        db_query = db.query(StoryDB)
        
        # Add text search
        search_filter = or_(
            StoryDB.title.ilike(f"%{query}%"),
            StoryDB.content.ilike(f"%{query}%")
        )
        db_query = db_query.filter(search_filter)
        
        # Add subreddit filter if provided
        if subreddits:
            db_query = db_query.filter(StoryDB.subreddit.in_(subreddits))
        
        return (
            db_query
            .order_by(desc(StoryDB.upvotes))
            .offset(skip)
            .limit(limit)
            .all()
        )

class CommentRepository(BaseRepository[CommentDB, Dict[str, Any], Dict[str, Any]]):
    def get_by_story_id(
        self, 
        db: Session, 
        story_id: UUID, 
        limit: int = 10
    ) -> List[CommentDB]:
        return (
            db.query(CommentDB)
            .filter(CommentDB.story_id == story_id)
            .order_by(desc(CommentDB.upvotes))
            .limit(limit)
            .all()
        )
    
    def get_by_reddit_id(self, db: Session, reddit_id: str) -> Optional[CommentDB]:
        return db.query(CommentDB).filter(CommentDB.reddit_id == reddit_id).first()

class ProcessedStoryRepository(BaseRepository[ProcessedStoryDB, Dict[str, Any], Dict[str, Any]]):
    def get_by_original_story_id(
        self, 
        db: Session, 
        original_story_id: UUID
    ) -> List[ProcessedStoryDB]:
        return (
            db.query(ProcessedStoryDB)
            .filter(ProcessedStoryDB.original_story_id == original_story_id)
            .order_by(desc(ProcessedStoryDB.created_at))
            .all()
        )
    
    def get_by_status(
        self, 
        db: Session, 
        status: ProcessingStatus,
        skip: int = 0,
        limit: int = 100
    ) -> List[ProcessedStoryDB]:
        return (
            db.query(ProcessedStoryDB)
            .filter(ProcessedStoryDB.processing_status == status)
            .order_by(desc(ProcessedStoryDB.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )

class AudioFileRepository(BaseRepository[AudioFileDB, Dict[str, Any], Dict[str, Any]]):
    def get_by_processed_story_id(
        self, 
        db: Session, 
        processed_story_id: UUID
    ) -> List[AudioFileDB]:
        return (
            db.query(AudioFileDB)
            .filter(AudioFileDB.processed_story_id == processed_story_id)
            .order_by(desc(AudioFileDB.created_at))
            .all()
        )
    
    def get_by_status(
        self, 
        db: Session, 
        status: GenerationStatus,
        skip: int = 0,
        limit: int = 100
    ) -> List[AudioFileDB]:
        return (
            db.query(AudioFileDB)
            .filter(AudioFileDB.status == status)
            .order_by(desc(AudioFileDB.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_by_task_id(self, db: Session, task_id: str) -> Optional[AudioFileDB]:
        return db.query(AudioFileDB).filter(AudioFileDB.task_id == task_id).first()

class CaptionRepository(BaseRepository[CaptionDB, Dict[str, Any], Dict[str, Any]]):
    def get_by_audio_file_id(
        self, 
        db: Session, 
        audio_file_id: UUID
    ) -> List[CaptionDB]:
        return (
            db.query(CaptionDB)
            .filter(CaptionDB.audio_file_id == audio_file_id)
            .order_by(asc(CaptionDB.start_time))
            .all()
        )
    
    def get_by_time_range(
        self, 
        db: Session, 
        audio_file_id: UUID,
        start_time: float,
        end_time: float
    ) -> List[CaptionDB]:
        return (
            db.query(CaptionDB)
            .filter(
                and_(
                    CaptionDB.audio_file_id == audio_file_id,
                    CaptionDB.start_time >= start_time,
                    CaptionDB.end_time <= end_time
                )
            )
            .order_by(asc(CaptionDB.start_time))
            .all()
        )

class VideoFileRepository(BaseRepository[VideoFileDB, Dict[str, Any], Dict[str, Any]]):
    def get_by_resolution(
        self, 
        db: Session, 
        resolution: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[VideoFileDB]:
        return (
            db.query(VideoFileDB)
            .filter(VideoFileDB.resolution == resolution)
            .order_by(desc(VideoFileDB.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )

class VideoProcessingJobRepository(BaseRepository[VideoProcessingJobDB, Dict[str, Any], Dict[str, Any]]):
    def get_by_audio_file_id(
        self, 
        db: Session, 
        audio_file_id: UUID
    ) -> List[VideoProcessingJobDB]:
        return (
            db.query(VideoProcessingJobDB)
            .filter(VideoProcessingJobDB.audio_file_id == audio_file_id)
            .order_by(desc(VideoProcessingJobDB.created_at))
            .all()
        )
    
    def get_by_status(
        self, 
        db: Session, 
        status: GenerationStatus,
        skip: int = 0,
        limit: int = 100
    ) -> List[VideoProcessingJobDB]:
        return (
            db.query(VideoProcessingJobDB)
            .filter(VideoProcessingJobDB.status == status)
            .order_by(desc(VideoProcessingJobDB.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_pending_jobs(self, db: Session, limit: int = 10) -> List[VideoProcessingJobDB]:
        return (
            db.query(VideoProcessingJobDB)
            .filter(VideoProcessingJobDB.status == GenerationStatus.QUEUED)
            .order_by(asc(VideoProcessingJobDB.created_at))
            .limit(limit)
            .all()
        )

# Repository instances
story_repository = StoryRepository(StoryDB)
comment_repository = CommentRepository(CommentDB)
processed_story_repository = ProcessedStoryRepository(ProcessedStoryDB)
audio_file_repository = AudioFileRepository(AudioFileDB)
caption_repository = CaptionRepository(CaptionDB)
video_file_repository = VideoFileRepository(VideoFileDB)
video_processing_job_repository = VideoProcessingJobRepository(VideoProcessingJobDB)