from sqlalchemy import Column, String, Text, Integer, Float, DateTime, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from enum import Enum

from .database import Base

class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class GenerationStatus(str, Enum):
    QUEUED = "queued"
    GENERATING_AUDIO = "generating_audio"
    GENERATING_CAPTIONS = "generating_captions"
    COMBINING_MEDIA = "combining_media"
    COMPLETED = "completed"
    FAILED = "failed"

class SubtitleStyle(str, Enum):
    KARAOKE = "karaoke"
    WORD_BY_WORD = "word_by_word"
    SENTENCE = "sentence"

class StoryDB(Base):
    __tablename__ = "reddit_posts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    reddit_id = Column(String, unique=True, nullable=False, index=True)
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    author = Column(String, nullable=False)
    subreddit = Column(String, nullable=False, index=True)
    upvotes = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    url = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    comments = relationship("CommentDB", back_populates="story", cascade="all, delete-orphan")
    processed_stories = relationship("ProcessedStoryDB", back_populates="original_story", cascade="all, delete-orphan")

class CommentDB(Base):
    __tablename__ = "comments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    story_id = Column(UUID(as_uuid=True), ForeignKey("reddit_posts.id"), nullable=False)
    reddit_id = Column(String, unique=True, nullable=False, index=True)
    content = Column(Text, nullable=False)
    author = Column(String, nullable=False)
    upvotes = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    story = relationship("StoryDB", back_populates="comments")

class ProcessedStoryDB(Base):
    __tablename__ = "processed_stories"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    original_story_id = Column(UUID(as_uuid=True), ForeignKey("reddit_posts.id"), nullable=False)
    processed_content = Column(Text, nullable=False)
    user_edits = Column(Text)
    processing_status = Column(SQLEnum(ProcessingStatus), default=ProcessingStatus.PENDING)
    user_id = Column(UUID(as_uuid=True))  # For future auth integration
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    original_story = relationship("StoryDB", back_populates="processed_stories")
    audio_files = relationship("AudioFileDB", back_populates="processed_story", cascade="all, delete-orphan")

class AudioFileDB(Base):
    __tablename__ = "audio_files"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    processed_story_id = Column(UUID(as_uuid=True), ForeignKey("processed_stories.id"), nullable=False)
    file_path = Column(Text, nullable=False)
    duration = Column(Float)
    format = Column(String, default="mp3")
    voice_settings = Column(JSON)
    audio_settings = Column(JSON)
    status = Column(SQLEnum(GenerationStatus), default=GenerationStatus.QUEUED)
    task_id = Column(String)  # For async processing
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    processed_story = relationship("ProcessedStoryDB", back_populates="audio_files")
    captions = relationship("CaptionDB", back_populates="audio_file", cascade="all, delete-orphan")
    video_jobs = relationship("VideoProcessingJobDB", back_populates="audio_file", cascade="all, delete-orphan")

class CaptionDB(Base):
    __tablename__ = "captions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    audio_file_id = Column(UUID(as_uuid=True), ForeignKey("audio_files.id"), nullable=False)
    text = Column(Text, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    audio_file = relationship("AudioFileDB", back_populates="captions")

class VideoFileDB(Base):
    __tablename__ = "video_files"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    file_path = Column(Text, nullable=False)
    duration = Column(Float)
    resolution = Column(String)  # e.g., "1920x1080"
    format = Column(String, default="mp4")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    video_jobs = relationship("VideoProcessingJobDB", back_populates="background_videos", secondary="video_job_backgrounds")

class VideoProcessingJobDB(Base):
    __tablename__ = "video_processing_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    audio_file_id = Column(UUID(as_uuid=True), ForeignKey("audio_files.id"), nullable=False)
    caption_file_path = Column(Text)
    output_file_path = Column(Text, nullable=False)
    status = Column(SQLEnum(GenerationStatus), default=GenerationStatus.QUEUED)
    progress = Column(Float, default=0.0)
    error_message = Column(Text)
    processing_options = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    
    # Relationships
    audio_file = relationship("AudioFileDB", back_populates="video_jobs")

# Association table for many-to-many relationship between video jobs and background videos
from sqlalchemy import Table
video_job_backgrounds = Table(
    'video_job_backgrounds',
    Base.metadata,
    Column('video_job_id', UUID(as_uuid=True), ForeignKey('video_processing_jobs.id'), primary_key=True),
    Column('video_file_id', UUID(as_uuid=True), ForeignKey('video_files.id'), primary_key=True)
)

# Update the relationship in VideoProcessingJobDB
VideoProcessingJobDB.background_videos = relationship(
    "VideoFileDB", 
    secondary=video_job_backgrounds, 
    back_populates="video_jobs"
)