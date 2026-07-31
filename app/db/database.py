from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
import os
from config import get_settings

settings = get_settings()

# Use Supabase PostgreSQL URL if available, fallback to SQLite for development
DATABASE_URL = settings.database_url

# Configure engine based on database type
if DATABASE_URL.startswith("postgresql"):
    # PostgreSQL/Supabase configuration
    engine = create_engine(
        DATABASE_URL,
        poolclass=NullPool,  # Supabase handles connection pooling
        echo=False
    )
else:
    # SQLite configuration for development
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False},
        echo=False
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database dependency for FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 