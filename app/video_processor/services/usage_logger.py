"""
Usage logging service for Cloud Video Processor

Logs structured usage data for monitoring, analytics, and billing
"""

import structlog
import json
import os
from typing import Dict, Optional, Any, List
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum

# from services.cost_calculator import cost_calculator, TranscriptionService  # Removed
from video_processor.services.performance_tracker import PerformanceMetrics, OperationType

logger = structlog.get_logger()

class UsageEventType(str, Enum):
    """Types of usage events to log"""
    JOB_STARTED = "job_started"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    TRANSCRIPTION_STARTED = "transcription_started"
    TRANSCRIPTION_COMPLETED = "transcription_completed"
    VIDEO_PROCESSING_STARTED = "video_processing_started"
    VIDEO_PROCESSING_COMPLETED = "video_processing_completed"
    API_REQUEST = "api_request"
    COST_CALCULATED = "cost_calculated"
    USAGE_SUMMARY = "usage_summary"

@dataclass
class UsageEvent:
    """Structured usage event data"""
    event_id: str
    event_type: UsageEventType
    timestamp: datetime
    job_id: str
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    
    # Operation details
    operation_type: Optional[str] = None
    transcription_service: Optional[str] = None
    model_used: Optional[str] = None
    
    # File information
    input_files: Optional[List[Dict[str, Any]]] = None
    output_files: Optional[List[Dict[str, Any]]] = None
    
    # Processing metrics
    processing_time_seconds: Optional[float] = None
    audio_duration_minutes: Optional[float] = None
    video_duration_minutes: Optional[float] = None
    
    # Cost information
    transcription_cost: Optional[float] = None
    video_processing_cost: Optional[float] = None
    storage_cost: Optional[float] = None
    total_cost: Optional[float] = None
    
    # Performance metrics
    cpu_usage_percent: Optional[float] = None
    memory_usage_mb: Optional[float] = None
    throughput_ratio: Optional[float] = None
    
    # Request context
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_size_bytes: Optional[int] = None
    response_size_bytes: Optional[int] = None
    
    # Error information
    error_occurred: bool = False
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    
    # Billing context
    billing_tier: Optional[str] = None
    rate_limit_remaining: Optional[int] = None
    
    # Additional metadata
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage"""
        data = asdict(self)
        # Convert datetime to ISO string
        data['timestamp'] = self.timestamp.isoformat()
        return data

class UsageLogger:
    """Log and track usage events with structured data"""
    
    def __init__(self):
        self.enable_detailed_logging = os.getenv('ENABLE_DETAILED_USAGE_LOGGING', 'true').lower() == 'true'
        self.log_to_file = os.getenv('USAGE_LOG_TO_FILE', 'false').lower() == 'true'
        self.usage_log_file = os.getenv('USAGE_LOG_FILE', '/var/log/cloud-video-processor-usage.jsonl')
        
        # Usage aggregation (in-memory for now, should be database in production)
        self.daily_usage: Dict[str, Dict[str, Any]] = {}
        self.user_usage: Dict[str, Dict[str, Any]] = {}
        
        logger.info(
            "usage_logger_initialized",
            detailed_logging=self.enable_detailed_logging,
            log_to_file=self.log_to_file
        )
    
    def log_usage_event(self, event: UsageEvent) -> None:
        """
        Log a usage event with structured data
        
        Args:
            event: UsageEvent to log
        """
        try:
            event_data = event.to_dict()
            
            # Log to structured logger
            # Remove duplicated fields from event_data to avoid conflicts
            # Convert complex objects to JSON strings for structured logging
            log_data = {}
            for k, v in event_data.items():
                if k not in ['event_type', 'job_id', 'user_id']:
                    if isinstance(v, (list, dict)):
                        log_data[k] = json.dumps(v) if v is not None else None
                    else:
                        log_data[k] = v
            
            logger.info(
                "usage_event",
                event_type=event.event_type,
                job_id=event.job_id,
                user_id=event.user_id,
                **log_data
            )
            
            # Log to file if enabled
            if self.log_to_file:
                self._write_to_file(event_data)
            
            # Update aggregations
            self._update_aggregations(event)
            
        except Exception as e:
            logger.error(
                "usage_event_logging_failed",
                event_type=event.event_type,
                job_id=event.job_id,
                error=str(e)
            )
    
    def log_job_started(
        self,
        job_id: str,
        operation_type: str,
        user_id: Optional[str] = None,
        **kwargs
    ) -> None:
        """Log job start event"""
        event = UsageEvent(
            event_id=f"{job_id}_started",
            event_type=UsageEventType.JOB_STARTED,
            timestamp=datetime.now(timezone.utc),
            job_id=job_id,
            user_id=user_id,
            operation_type=operation_type,
            **kwargs
        )
        self.log_usage_event(event)
    
    def log_job_completed(
        self,
        job_id: str,
        performance_metrics: PerformanceMetrics,
        cost_breakdown: Dict[str, Any],
        user_id: Optional[str] = None,
        **kwargs
    ) -> None:
        """Log job completion with full metrics"""
        event = UsageEvent(
            event_id=f"{job_id}_completed",
            event_type=UsageEventType.JOB_COMPLETED,
            timestamp=datetime.now(timezone.utc),
            job_id=job_id,
            user_id=user_id,
            operation_type=performance_metrics.operation_type,
            transcription_service=performance_metrics.transcription_service,
            model_used=performance_metrics.model_used,
            processing_time_seconds=performance_metrics.duration_seconds,
            audio_duration_minutes=performance_metrics.audio_duration_minutes,
            video_duration_minutes=performance_metrics.video_duration_minutes,
            transcription_cost=cost_breakdown.get('transcription_cost', 0.0),
            video_processing_cost=cost_breakdown.get('video_processing_cost', 0.0),
            storage_cost=cost_breakdown.get('storage_cost', 0.0),
            total_cost=cost_breakdown.get('total_cost', 0.0),
            cpu_usage_percent=performance_metrics.avg_cpu_percent,
            memory_usage_mb=performance_metrics.avg_memory_mb,
            throughput_ratio=performance_metrics.throughput_ratio,
            error_occurred=performance_metrics.error_occurred,
            error_message=performance_metrics.error_message,
            **kwargs
        )
        self.log_usage_event(event)
    
    def log_job_failed(
        self,
        job_id: str,
        error_code: str,
        error_message: str,
        performance_metrics: Optional[PerformanceMetrics] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> None:
        """Log job failure"""
        event = UsageEvent(
            event_id=f"{job_id}_failed",
            event_type=UsageEventType.JOB_FAILED,
            timestamp=datetime.now(timezone.utc),
            job_id=job_id,
            user_id=user_id,
            operation_type=performance_metrics.operation_type if performance_metrics else None,
            processing_time_seconds=performance_metrics.duration_seconds if performance_metrics else None,
            error_occurred=True,
            error_code=error_code,
            error_message=error_message,
            **kwargs
        )
        self.log_usage_event(event)
    
    def log_api_request(
        self,
        job_id: str,
        endpoint: str,
        method: str,
        status_code: int,
        processing_time_seconds: float,
        user_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_size_bytes: Optional[int] = None,
        response_size_bytes: Optional[int] = None,
        **kwargs
    ) -> None:
        """Log API request"""
        event = UsageEvent(
            event_id=f"{job_id}_api_request",
            event_type=UsageEventType.API_REQUEST,
            timestamp=datetime.now(timezone.utc),
            job_id=job_id,
            user_id=user_id,
            operation_type=f"{method} {endpoint}",
            processing_time_seconds=processing_time_seconds,
            client_ip=client_ip,
            user_agent=user_agent,
            request_size_bytes=request_size_bytes,
            response_size_bytes=response_size_bytes,
            error_occurred=status_code >= 400,
            error_code=str(status_code) if status_code >= 400 else None,
            metadata={"status_code": status_code, "endpoint": endpoint, "method": method},
            **kwargs
        )
        self.log_usage_event(event)
    
    def log_transcription_event(
        self,
        job_id: str,
        event_type: UsageEventType,
        service_name: str,
        audio_duration_minutes: float,
        cost: float,
        model: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> None:
        """Log transcription-specific event"""
        event = UsageEvent(
            event_id=f"{job_id}_transcription_{event_type}",
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            job_id=job_id,
            user_id=user_id,
            operation_type="transcription",
            transcription_service=service_name,
            model_used=model,
            audio_duration_minutes=audio_duration_minutes,
            transcription_cost=cost,
            total_cost=cost,
            **kwargs
        )
        self.log_usage_event(event)
    
    def log_video_processing_event(
        self,
        job_id: str,
        event_type: UsageEventType,
        operation: str,
        video_duration_minutes: float,
        cost: float,
        user_id: Optional[str] = None,
        **kwargs
    ) -> None:
        """Log video processing event"""
        event = UsageEvent(
            event_id=f"{job_id}_video_{operation}_{event_type}",
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            job_id=job_id,
            user_id=user_id,
            operation_type=f"video_{operation}",
            video_duration_minutes=video_duration_minutes,
            video_processing_cost=cost,
            total_cost=cost,
            **kwargs
        )
        self.log_usage_event(event)
    
    def get_user_usage_summary(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get usage summary for a user
        
        Args:
            user_id: User identifier
            start_date: Start of period to analyze
            end_date: End of period to analyze
            
        Returns:
            Usage summary statistics
        """
        # In a real implementation, this would query a database
        # For now, return aggregated data from memory
        
        user_data = self.user_usage.get(user_id, {})
        
        return {
            "user_id": user_id,
            "period_start": start_date.isoformat() if start_date else None,
            "period_end": end_date.isoformat() if end_date else None,
            "total_jobs": user_data.get("total_jobs", 0),
            "successful_jobs": user_data.get("successful_jobs", 0),
            "failed_jobs": user_data.get("failed_jobs", 0),
            "total_processing_time_seconds": user_data.get("total_processing_time", 0.0),
            "total_audio_minutes": user_data.get("total_audio_minutes", 0.0),
            "total_video_minutes": user_data.get("total_video_minutes", 0.0),
            "total_cost": user_data.get("total_cost", 0.0),
            "transcription_cost": user_data.get("transcription_cost", 0.0),
            "video_processing_cost": user_data.get("video_processing_cost", 0.0),
            "storage_cost": user_data.get("storage_cost", 0.0),
            "avg_job_duration_seconds": user_data.get("avg_job_duration", 0.0),
            "most_used_transcription_service": user_data.get("primary_transcription_service"),
            "total_api_requests": user_data.get("total_api_requests", 0)
        }
    
    def get_daily_usage_summary(self, date: datetime) -> Dict[str, Any]:
        """Get usage summary for a specific day"""
        date_key = date.strftime('%Y-%m-%d')
        daily_data = self.daily_usage.get(date_key, {})
        
        return {
            "date": date_key,
            "total_jobs": daily_data.get("total_jobs", 0),
            "successful_jobs": daily_data.get("successful_jobs", 0),
            "failed_jobs": daily_data.get("failed_jobs", 0),
            "total_cost": daily_data.get("total_cost", 0.0),
            "total_processing_time_seconds": daily_data.get("total_processing_time", 0.0),
            "unique_users": daily_data.get("unique_users", 0),
            "total_api_requests": daily_data.get("total_api_requests", 0),
            "peak_concurrent_jobs": daily_data.get("peak_concurrent", 0)
        }
    
    def _write_to_file(self, event_data: Dict[str, Any]) -> None:
        """Write usage event to file in JSONL format"""
        try:
            os.makedirs(os.path.dirname(self.usage_log_file), exist_ok=True)
            
            with open(self.usage_log_file, 'a') as f:
                f.write(json.dumps(event_data) + '\n')
                
        except Exception as e:
            logger.error(
                "usage_log_file_write_failed",
                file=self.usage_log_file,
                error=str(e)
            )
    
    def _update_aggregations(self, event: UsageEvent) -> None:
        """Update in-memory usage aggregations"""
        try:
            # Update daily aggregation
            date_key = event.timestamp.strftime('%Y-%m-%d')
            if date_key not in self.daily_usage:
                self.daily_usage[date_key] = {
                    "total_jobs": 0,
                    "successful_jobs": 0,
                    "failed_jobs": 0,
                    "total_cost": 0.0,
                    "total_processing_time": 0.0,
                    "unique_users": set(),
                    "total_api_requests": 0,
                    "peak_concurrent": 0
                }
            
            daily = self.daily_usage[date_key]
            
            if event.event_type == UsageEventType.JOB_STARTED:
                daily["total_jobs"] += 1
            elif event.event_type == UsageEventType.JOB_COMPLETED:
                daily["successful_jobs"] += 1
                if event.total_cost:
                    daily["total_cost"] += event.total_cost
                if event.processing_time_seconds:
                    daily["total_processing_time"] += event.processing_time_seconds
            elif event.event_type == UsageEventType.JOB_FAILED:
                daily["failed_jobs"] += 1
            elif event.event_type == UsageEventType.API_REQUEST:
                daily["total_api_requests"] += 1
            
            if event.user_id:
                daily["unique_users"].add(event.user_id)
            
            # Update user aggregation
            if event.user_id:
                if event.user_id not in self.user_usage:
                    self.user_usage[event.user_id] = {
                        "total_jobs": 0,
                        "successful_jobs": 0,
                        "failed_jobs": 0,
                        "total_cost": 0.0,
                        "transcription_cost": 0.0,
                        "video_processing_cost": 0.0,
                        "storage_cost": 0.0,
                        "total_processing_time": 0.0,
                        "total_audio_minutes": 0.0,
                        "total_video_minutes": 0.0,
                        "total_api_requests": 0,
                        "transcription_services": {},
                        "job_durations": []
                    }
                
                user = self.user_usage[event.user_id]
                
                if event.event_type == UsageEventType.JOB_STARTED:
                    user["total_jobs"] += 1
                elif event.event_type == UsageEventType.JOB_COMPLETED:
                    user["successful_jobs"] += 1
                    if event.total_cost:
                        user["total_cost"] += event.total_cost
                    if event.transcription_cost:
                        user["transcription_cost"] += event.transcription_cost
                    if event.video_processing_cost:
                        user["video_processing_cost"] += event.video_processing_cost
                    if event.storage_cost:
                        user["storage_cost"] += event.storage_cost
                    if event.processing_time_seconds:
                        user["total_processing_time"] += event.processing_time_seconds
                        user["job_durations"].append(event.processing_time_seconds)
                    if event.audio_duration_minutes:
                        user["total_audio_minutes"] += event.audio_duration_minutes
                    if event.video_duration_minutes:
                        user["total_video_minutes"] += event.video_duration_minutes
                    if event.transcription_service:
                        service = event.transcription_service
                        user["transcription_services"][service] = user["transcription_services"].get(service, 0) + 1
                        
                        # Update primary service
                        primary = max(user["transcription_services"], key=user["transcription_services"].get)
                        user["primary_transcription_service"] = primary
                        
                        # Update average duration
                        if user["job_durations"]:
                            user["avg_job_duration"] = sum(user["job_durations"]) / len(user["job_durations"])
                            
                elif event.event_type == UsageEventType.JOB_FAILED:
                    user["failed_jobs"] += 1
                elif event.event_type == UsageEventType.API_REQUEST:
                    user["total_api_requests"] += 1
                    
        except Exception as e:
            logger.error(
                "usage_aggregation_update_failed",
                event_type=event.event_type,
                error=str(e)
            )

# Global usage logger instance
usage_logger = UsageLogger()