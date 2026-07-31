"""
Performance and timing tracking service for Cloud Video Processor

Tracks processing times, resource usage, and performance metrics
"""

import time
import structlog
import asyncio
from typing import Dict, Optional, Any, List
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager
import os
from enum import Enum

logger = structlog.get_logger()

try:
    import psutil
except ImportError:
    psutil = None

class OperationType(str, Enum):
    """Types of operations being tracked"""
    TRANSCRIPTION = "transcription"
    VIDEO_COMBINATION = "video_combination"
    AUDIO_SYNC = "audio_sync"
    VIDEO_SPLIT = "video_split"
    SUBTITLE_BURN = "subtitle_burn"
    FULL_PIPELINE = "full_pipeline"
    API_REQUEST = "api_request"

@dataclass
class PerformanceMetrics:
    """Performance metrics for an operation"""
    job_id: str
    operation_type: OperationType
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    
    # Resource usage
    peak_cpu_percent: Optional[float] = None
    peak_memory_mb: Optional[float] = None
    avg_cpu_percent: Optional[float] = None
    avg_memory_mb: Optional[float] = None
    
    # Operation-specific metrics
    input_file_size_mb: Optional[float] = None
    output_file_size_mb: Optional[float] = None
    audio_duration_minutes: Optional[float] = None
    video_duration_minutes: Optional[float] = None
    
    # Processing details
    transcription_service: Optional[str] = None
    model_used: Optional[str] = None
    features_enabled: Optional[List[str]] = None
    
    # Error information
    error_occurred: bool = False
    error_message: Optional[str] = None
    
    # Quality metrics
    throughput_ratio: Optional[float] = None  # processing_time / media_duration
    files_processed: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage"""
        data = asdict(self)
        # Convert datetime objects to ISO strings
        if self.start_time:
            data['start_time'] = self.start_time.isoformat()
        if self.end_time:
            data['end_time'] = self.end_time.isoformat()
        return data

class PerformanceTracker:
    """Track performance metrics for operations"""
    
    def __init__(self):
        self.active_operations: Dict[str, PerformanceMetrics] = {}
        self.completed_operations: List[PerformanceMetrics] = []
        self.max_completed_history = 1000  # Keep last 1000 operations in memory
        
        # System monitoring
        self.system_monitoring_enabled = (
            os.getenv('ENABLE_SYSTEM_MONITORING', 'true').lower() == 'true'
            and psutil is not None
        )
        if psutil is None:
            logger.warning(
                "system_monitoring_unavailable",
                message="psutil is not installed; system metrics disabled"
            )
        
        logger.info("performance_tracker_initialized", system_monitoring=self.system_monitoring_enabled)
    
    def start_operation(
        self,
        job_id: str,
        operation_type: OperationType,
        **kwargs
    ) -> PerformanceMetrics:
        """
        Start tracking an operation
        
        Args:
            job_id: Unique job identifier
            operation_type: Type of operation being performed
            **kwargs: Additional metrics to track
            
        Returns:
            PerformanceMetrics object for this operation
        """
        metrics = PerformanceMetrics(
            job_id=job_id,
            operation_type=operation_type,
            start_time=datetime.now(timezone.utc),
            **kwargs
        )
        
        self.active_operations[job_id] = metrics
        
        logger.info(
            "operation_started",
            job_id=job_id,
            operation_type=operation_type,
            start_time=metrics.start_time.isoformat()
        )
        
        return metrics
    
    def end_operation(
        self,
        job_id: str,
        error_occurred: bool = False,
        error_message: Optional[str] = None,
        **kwargs
    ) -> Optional[PerformanceMetrics]:
        """
        End tracking an operation
        
        Args:
            job_id: Job identifier
            error_occurred: Whether an error occurred
            error_message: Error details if any
            **kwargs: Additional metrics to update
            
        Returns:
            Completed PerformanceMetrics object
        """
        if job_id not in self.active_operations:
            logger.warning("operation_not_found_for_end", job_id=job_id)
            return None
        
        metrics = self.active_operations[job_id]
        metrics.end_time = datetime.now(timezone.utc)
        metrics.duration_seconds = (metrics.end_time - metrics.start_time).total_seconds()
        metrics.error_occurred = error_occurred
        metrics.error_message = error_message
        
        # Update additional metrics
        for key, value in kwargs.items():
            if hasattr(metrics, key):
                setattr(metrics, key, value)
        
        # Calculate throughput ratio if we have media duration
        if metrics.duration_seconds and metrics.audio_duration_minutes:
            audio_duration_seconds = metrics.audio_duration_minutes * 60
            metrics.throughput_ratio = metrics.duration_seconds / audio_duration_seconds
        elif metrics.duration_seconds and metrics.video_duration_minutes:
            video_duration_seconds = metrics.video_duration_minutes * 60
            metrics.throughput_ratio = metrics.duration_seconds / video_duration_seconds
        
        # Move to completed operations
        del self.active_operations[job_id]
        self.completed_operations.append(metrics)
        
        # Trim completed operations if needed
        if len(self.completed_operations) > self.max_completed_history:
            self.completed_operations = self.completed_operations[-self.max_completed_history:]
        
        logger.info(
            "operation_completed",
            job_id=job_id,
            operation_type=metrics.operation_type,
            duration_seconds=metrics.duration_seconds,
            error_occurred=error_occurred,
            throughput_ratio=metrics.throughput_ratio
        )
        
        return metrics
    
    def update_operation_metrics(
        self,
        job_id: str,
        **kwargs
    ) -> bool:
        """
        Update metrics for an active operation
        
        Args:
            job_id: Job identifier
            **kwargs: Metrics to update
            
        Returns:
            True if operation was found and updated
        """
        if job_id not in self.active_operations:
            logger.warning("operation_not_found_for_update", job_id=job_id)
            return False
        
        metrics = self.active_operations[job_id]
        
        for key, value in kwargs.items():
            if hasattr(metrics, key):
                setattr(metrics, key, value)
                logger.debug("metric_updated", job_id=job_id, metric=key, value=value)
        
        return True
    
    def get_operation_metrics(self, job_id: str) -> Optional[PerformanceMetrics]:
        """Get current metrics for an operation"""
        # Check active operations first
        if job_id in self.active_operations:
            return self.active_operations[job_id]
        
        # Check completed operations
        for metrics in reversed(self.completed_operations):
            if metrics.job_id == job_id:
                return metrics
        
        return None
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """Get current system performance metrics"""
        if not self.system_monitoring_enabled:
            return {}
        
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_mb": memory.available / 1024 / 1024,
                "memory_used_mb": memory.used / 1024 / 1024,
                "disk_percent": disk.percent,
                "disk_free_gb": disk.free / 1024 / 1024 / 1024,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error("system_metrics_collection_failed", error=str(e))
            return {}
    
    def get_performance_summary(
        self,
        operation_type: Optional[OperationType] = None,
        hours_back: int = 24
    ) -> Dict[str, Any]:
        """
        Get performance summary for operations
        
        Args:
            operation_type: Filter by operation type
            hours_back: How many hours back to analyze
            
        Returns:
            Performance summary statistics
        """
        cutoff_time = datetime.now(timezone.utc).timestamp() - (hours_back * 3600)
        
        # Filter operations
        filtered_ops = []
        for metrics in self.completed_operations:
            if metrics.start_time.timestamp() >= cutoff_time:
                if not operation_type or metrics.operation_type == operation_type:
                    filtered_ops.append(metrics)
        
        if not filtered_ops:
            return {
                "operation_type": operation_type,
                "hours_analyzed": hours_back,
                "total_operations": 0
            }
        
        # Calculate statistics
        durations = [op.duration_seconds for op in filtered_ops if op.duration_seconds]
        throughput_ratios = [op.throughput_ratio for op in filtered_ops if op.throughput_ratio]
        error_count = sum(1 for op in filtered_ops if op.error_occurred)
        
        summary = {
            "operation_type": operation_type,
            "hours_analyzed": hours_back,
            "total_operations": len(filtered_ops),
            "error_count": error_count,
            "error_rate": error_count / len(filtered_ops) if filtered_ops else 0,
            "avg_duration_seconds": sum(durations) / len(durations) if durations else 0,
            "min_duration_seconds": min(durations) if durations else 0,
            "max_duration_seconds": max(durations) if durations else 0,
            "avg_throughput_ratio": sum(throughput_ratios) / len(throughput_ratios) if throughput_ratios else 0,
            "total_processing_time": sum(durations) if durations else 0
        }
        
        return summary
    
    @asynccontextmanager
    async def track_operation(
        self,
        job_id: str,
        operation_type: OperationType,
        **initial_metrics
    ):
        """
        Context manager for tracking an operation
        
        Usage:
            async with tracker.track_operation("job123", OperationType.TRANSCRIPTION):
                # do work
                tracker.update_operation_metrics("job123", audio_duration_minutes=5.2)
        """
        metrics = self.start_operation(job_id, operation_type, **initial_metrics)
        
        try:
            yield metrics
        except Exception as e:
            self.end_operation(
                job_id,
                error_occurred=True,
                error_message=str(e)
            )
            raise
        else:
            self.end_operation(job_id)

class TimingDecorator:
    """Decorator for automatically timing functions"""
    
    def __init__(self, tracker: PerformanceTracker, operation_type: OperationType):
        self.tracker = tracker
        self.operation_type = operation_type
    
    def __call__(self, func):
        """Decorator function"""
        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                # Try to extract job_id from arguments
                job_id = kwargs.get('job_id') or self._extract_job_id(args, kwargs)
                
                if job_id:
                    async with self.tracker.track_operation(job_id, self.operation_type):
                        return await func(*args, **kwargs)
                else:
                    return await func(*args, **kwargs)
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs):
                job_id = kwargs.get('job_id') or self._extract_job_id(args, kwargs)
                
                if job_id:
                    start_time = time.time()
                    try:
                        result = func(*args, **kwargs)
                        duration = time.time() - start_time
                        logger.info(
                            "function_timing",
                            function=func.__name__,
                            job_id=job_id,
                            duration_seconds=duration
                        )
                        return result
                    except Exception as e:
                        duration = time.time() - start_time
                        logger.error(
                            "function_timing_error",
                            function=func.__name__,
                            job_id=job_id,
                            duration_seconds=duration,
                            error=str(e)
                        )
                        raise
                else:
                    return func(*args, **kwargs)
            return sync_wrapper
    
    def _extract_job_id(self, args, kwargs):
        """Try to extract job_id from function arguments"""
        # Look for job_id in kwargs
        if 'job_id' in kwargs:
            return kwargs['job_id']
        
        # Look for request object with job_id attribute
        for arg in args:
            if hasattr(arg, 'job_id'):
                return arg.job_id
        
        return None

# Global performance tracker instance
performance_tracker = PerformanceTracker()

# Decorator factory functions
def track_transcription(func):
    """Decorator for transcription operations"""
    return TimingDecorator(performance_tracker, OperationType.TRANSCRIPTION)(func)

def track_video_processing(func):
    """Decorator for video processing operations"""
    return TimingDecorator(performance_tracker, OperationType.VIDEO_COMBINATION)(func)

def track_api_request(func):
    """Decorator for API request timing"""
    return TimingDecorator(performance_tracker, OperationType.API_REQUEST)(func)
