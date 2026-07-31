from sqlalchemy import Column, Integer, String, DateTime, func, ForeignKey, BigInteger, Boolean, Text
from sqlalchemy.orm import relationship
from db.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    external_id = Column(String, unique=True, index=True, nullable=True)  # For Supabase user ID
    stripe_customer_id = Column(String, unique=True, index=True, nullable=True)  # Stripe customer ID
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    notes = relationship("Note", back_populates="user", cascade="all, delete-orphan")
    files = relationship("FileAttachment", back_populates="user", cascade="all, delete-orphan")
    downloads = relationship("FileDownloadAnalytics", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")

class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    content = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="notes")
    files = relationship("FileAttachment", back_populates="note", cascade="all, delete-orphan")

class FileAttachment(Base):
    __tablename__ = "file_attachments"
    id = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False, unique=True)  # Full path in storage
    file_type = Column(String, nullable=False)  # MIME type
    size = Column(BigInteger, nullable=False)  # Size in bytes
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=True)  # Nullable to support orphaned files
    bucket_name = Column(String, nullable=False)  # Storage bucket name
    is_processed = Column(Boolean, nullable=False, default=False)  # Flag for background processing
    processing_status = Column(String, nullable=True)  # Status of background processing
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_accessed = Column(DateTime(timezone=True), nullable=True)  # Track last access time
    download_count = Column(Integer, nullable=False, default=0)  # Track number of downloads
    
    # Relationships
    user = relationship("User", back_populates="files")
    note = relationship("Note", back_populates="files")
    downloads = relationship("FileDownloadAnalytics", back_populates="file", cascade="all, delete-orphan")

class FileDownloadAnalytics(Base):
    __tablename__ = "file_download_analytics"
    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("file_attachments.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Who downloaded it
    downloaded_at = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String, nullable=True)  # Anonymized IP (optional)
    user_agent = Column(String, nullable=True)  # Browser/device info (optional)
    status = Column(String, nullable=False, default="success")  # success, failed, etc.
    download_type = Column(String, nullable=True)  # direct, time-limited, shared link, etc.
    
    # Relationships
    file = relationship("FileAttachment", back_populates="downloads")
    user = relationship("User", back_populates="downloads")


class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    stripe_subscription_id = Column(String, unique=True, index=True, nullable=False)
    stripe_customer_id = Column(String, nullable=False)
    status = Column(String, nullable=False)  # active, canceled, past_due, etc.
    current_period_start = Column(DateTime(timezone=True), nullable=False)
    current_period_end = Column(DateTime(timezone=True), nullable=False)
    plan_id = Column(String, nullable=False)  # Stripe price ID
    plan_name = Column(String, nullable=True)  # Human readable plan name
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="subscriptions")


class StripeEvent(Base):
    __tablename__ = "stripe_events"
    id = Column(Integer, primary_key=True, index=True)
    stripe_event_id = Column(String, unique=True, index=True, nullable=False)
    event_type = Column(String, nullable=False)
    processed = Column(Boolean, default=False, nullable=False)
    data = Column(Text, nullable=True)  # JSON data from Stripe
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)