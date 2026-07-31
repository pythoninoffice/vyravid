"""
Database initialization script for Story Generator.
Creates all tables and sets up the database schema.
"""

from sqlalchemy import text
from .database import engine, Base
from .story_models import (
    StoryDB, CommentDB, ProcessedStoryDB, AudioFileDB, 
    CaptionDB, VideoFileDB, VideoProcessingJobDB
)

def create_database_schema():
    """Create all database tables."""
    print("Creating database schema...")
    
    # Import all models to ensure they're registered with Base
    from . import story_models
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    print("Database schema created successfully!")

def create_indexes():
    """Create additional indexes for better performance."""
    print("Creating additional indexes...")
    
    with engine.connect() as conn:
        # Create indexes for better query performance
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_reddit_posts_subreddit_created ON reddit_posts(subreddit, created_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_reddit_posts_upvotes ON reddit_posts(upvotes DESC);",
            "CREATE INDEX IF NOT EXISTS idx_comments_story_upvotes ON comments(story_id, upvotes DESC);",
            "CREATE INDEX IF NOT EXISTS idx_processed_stories_status ON processed_stories(processing_status);",
            "CREATE INDEX IF NOT EXISTS idx_audio_files_status ON audio_files(status);",
            "CREATE INDEX IF NOT EXISTS idx_captions_audio_time ON captions(audio_file_id, start_time);",
            "CREATE INDEX IF NOT EXISTS idx_video_jobs_status ON video_processing_jobs(status, created_at);",
        ]
        
        for index_sql in indexes:
            try:
                conn.execute(text(index_sql))
                print(f"Created index: {index_sql.split('idx_')[1].split(' ')[0] if 'idx_' in index_sql else 'custom'}")
            except Exception as e:
                print(f"Warning: Could not create index - {e}")
        
        conn.commit()
    
    print("Indexes created successfully!")

def init_database():
    """Initialize the complete database schema."""
    try:
        create_database_schema()
        create_indexes()
        print("Database initialization completed successfully!")
        return True
    except Exception as e:
        print(f"Error initializing database: {e}")
        return False

if __name__ == "__main__":
    init_database()