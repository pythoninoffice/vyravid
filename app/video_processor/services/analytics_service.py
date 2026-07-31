"""
Analytics and reporting service for Cloud Video Processor

Provides usage analytics, cost analysis, and performance insights
"""

import structlog
from typing import Dict, Optional, Any, List
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from enum import Enum

from video_processor.services.usage_logger import usage_logger, UsageEventType
from video_processor.services.performance_tracker import performance_tracker, OperationType
# from services.cost_calculator import cost_calculator, TranscriptionService  # Removed

logger = structlog.get_logger()

class ReportType(str, Enum):
    """Types of analytics reports"""
    USAGE_SUMMARY = "usage_summary"
    COST_ANALYSIS = "cost_analysis"
    PERFORMANCE_METRICS = "performance_metrics"
    USER_ANALYTICS = "user_analytics"
    SYSTEM_HEALTH = "system_health"
    BILLING_REPORT = "billing_report"

@dataclass
class UsageMetrics:
    """Usage metrics for a specific period"""
    total_jobs: int = 0
    successful_jobs: int = 0
    failed_jobs: int = 0
    total_processing_time_hours: float = 0.0
    total_audio_hours: float = 0.0
    total_video_hours: float = 0.0
    total_cost: float = 0.0
    avg_job_duration_minutes: float = 0.0
    peak_concurrent_jobs: int = 0
    unique_users: int = 0
    error_rate: float = 0.0

@dataclass
class CostBreakdown:
    """Cost breakdown analysis"""
    transcription_costs: Dict[str, float]
    video_processing_costs: Dict[str, float]
    storage_costs: float
    compute_costs: float
    total_cost: float
    cost_by_service: Dict[str, float]
    cost_per_minute: float

class AnalyticsService:
    """Analytics and reporting service"""
    
    def __init__(self):
        self.cache_ttl_minutes = 15  # Cache reports for 15 minutes
        self.report_cache: Dict[str, Dict[str, Any]] = {}
        
        logger.info("analytics_service_initialized")
    
    def generate_usage_report(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive usage report
        
        Args:
            start_date: Start of reporting period
            end_date: End of reporting period
            user_id: Filter by specific user
            organization_id: Filter by organization
            
        Returns:
            Usage report with metrics and insights
        """
        try:
            cache_key = f"usage_{start_date.isoformat()}_{end_date.isoformat()}_{user_id}_{organization_id}"
            
            # Check cache first
            cached_report = self._get_cached_report(cache_key)
            if cached_report:
                return cached_report
            
            # Generate new report
            report = {
                "report_type": ReportType.USAGE_SUMMARY,
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "duration_days": (end_date - start_date).days
                },
                "filters": {
                    "user_id": user_id,
                    "organization_id": organization_id
                },
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Get usage metrics
            usage_metrics = self._calculate_usage_metrics(start_date, end_date, user_id, organization_id)
            report["usage_metrics"] = usage_metrics.__dict__
            
            # Get operation breakdown
            report["operation_breakdown"] = self._get_operation_breakdown(start_date, end_date, user_id)
            
            # Get service usage
            report["service_usage"] = self._get_service_usage_breakdown(start_date, end_date, user_id)
            
            # Get daily trends
            report["daily_trends"] = self._get_daily_usage_trends(start_date, end_date, user_id)
            
            # Get performance insights
            report["performance_insights"] = self._get_performance_insights(start_date, end_date)
            
            # Cache the report
            self._cache_report(cache_key, report)
            
            logger.info(
                "usage_report_generated",
                period_days=(end_date - start_date).days,
                total_jobs=usage_metrics.total_jobs,
                user_id=user_id
            )
            
            return report
            
        except Exception as e:
            logger.error("usage_report_generation_failed", error=str(e))
            raise
    
    def generate_cost_analysis(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate detailed cost analysis report"""
        try:
            cache_key = f"cost_{start_date.isoformat()}_{end_date.isoformat()}_{user_id}"
            
            cached_report = self._get_cached_report(cache_key)
            if cached_report:
                return cached_report
            
            report = {
                "report_type": ReportType.COST_ANALYSIS,
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Calculate cost breakdown
            cost_breakdown = self._calculate_cost_breakdown(start_date, end_date, user_id)
            report["cost_breakdown"] = cost_breakdown.__dict__
            
            # Cost trends
            report["cost_trends"] = self._get_cost_trends(start_date, end_date, user_id)
            
            # Service efficiency analysis
            report["service_efficiency"] = self._analyze_service_efficiency(start_date, end_date)
            
            # Cost optimization recommendations
            report["optimization_recommendations"] = self._generate_cost_recommendations(cost_breakdown)
            
            # Projected costs
            report["projections"] = self._project_future_costs(cost_breakdown, start_date, end_date)
            
            self._cache_report(cache_key, report)
            
            logger.info(
                "cost_analysis_generated",
                total_cost=cost_breakdown.total_cost,
                period_days=(end_date - start_date).days
            )
            
            return report
            
        except Exception as e:
            logger.error("cost_analysis_generation_failed", error=str(e))
            raise
    
    def generate_performance_report(
        self,
        start_date: datetime,
        end_date: datetime,
        operation_type: Optional[OperationType] = None
    ) -> Dict[str, Any]:
        """Generate performance metrics report"""
        try:
            cache_key = f"performance_{start_date.isoformat()}_{end_date.isoformat()}_{operation_type}"
            
            cached_report = self._get_cached_report(cache_key)
            if cached_report:
                return cached_report
            
            # Get performance summary from tracker
            hours_back = int((datetime.now(timezone.utc) - start_date).total_seconds() / 3600)
            performance_summary = performance_tracker.get_performance_summary(operation_type, hours_back)
            
            report = {
                "report_type": ReportType.PERFORMANCE_METRICS,
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "operation_type": operation_type,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "performance_summary": performance_summary
            }
            
            # Add detailed performance metrics
            report["throughput_analysis"] = self._analyze_throughput_performance()
            report["resource_utilization"] = self._analyze_resource_utilization()
            report["error_analysis"] = self._analyze_error_patterns(start_date, end_date)
            report["system_health"] = performance_tracker.get_system_metrics()
            
            self._cache_report(cache_key, report)
            
            return report
            
        except Exception as e:
            logger.error("performance_report_generation_failed", error=str(e))
            raise
    
    def generate_billing_report(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate billing report for invoicing"""
        try:
            # Get usage and cost data
            usage_report = self.generate_usage_report(start_date, end_date, user_id, organization_id)
            cost_analysis = self.generate_cost_analysis(start_date, end_date, user_id)
            
            billing_report = {
                "report_type": ReportType.BILLING_REPORT,
                "billing_period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "billing_cycle": "monthly"  # Could be configurable
                },
                "customer": {
                    "user_id": user_id,
                    "organization_id": organization_id
                },
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Extract billing-relevant data
            billing_report["usage_summary"] = {
                "total_jobs": usage_report["usage_metrics"]["total_jobs"],
                "successful_jobs": usage_report["usage_metrics"]["successful_jobs"],
                "total_processing_hours": usage_report["usage_metrics"]["total_processing_time_hours"],
                "total_media_hours": usage_report["usage_metrics"]["total_audio_hours"] + usage_report["usage_metrics"]["total_video_hours"]
            }
            
            billing_report["cost_summary"] = {
                "subtotal": cost_analysis["cost_breakdown"]["total_cost"],
                "tax_rate": 0.0,  # Would be calculated based on location
                "tax_amount": 0.0,
                "total_amount": cost_analysis["cost_breakdown"]["total_cost"],
                "currency": "USD"
            }
            
            billing_report["line_items"] = self._generate_billing_line_items(
                usage_report, cost_analysis
            )
            
            # Payment and billing info
            billing_report["billing_details"] = {
                "billing_tier": "standard",
                "payment_method": "automatic",
                "next_billing_date": (end_date + timedelta(days=30)).isoformat()
            }
            
            logger.info(
                "billing_report_generated",
                user_id=user_id,
                total_amount=billing_report["cost_summary"]["total_amount"],
                period_days=(end_date - start_date).days
            )
            
            return billing_report
            
        except Exception as e:
            logger.error("billing_report_generation_failed", error=str(e))
            raise
    
    def get_real_time_metrics(self) -> Dict[str, Any]:
        """Get real-time system metrics"""
        try:
            now = datetime.now(timezone.utc)
            last_hour = now - timedelta(hours=1)
            
            # Get current system metrics
            system_metrics = performance_tracker.get_system_metrics()
            
            # Get recent performance summary
            performance_summary = performance_tracker.get_performance_summary(hours_back=1)
            
            # Get current usage from logger
            daily_summary = usage_logger.get_daily_usage_summary(now)
            
            metrics = {
                "timestamp": now.isoformat(),
                "system": system_metrics,
                "performance": performance_summary,
                "usage": daily_summary,
                "active_jobs": len(performance_tracker.active_operations),
                "health_status": "healthy" if system_metrics.get("cpu_percent", 0) < 80 else "warning"
            }
            
            return metrics
            
        except Exception as e:
            logger.error("real_time_metrics_failed", error=str(e))
            return {"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}
    
    def _calculate_usage_metrics(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[str],
        organization_id: Optional[str]
    ) -> UsageMetrics:
        """Calculate usage metrics for the period"""
        # In a real implementation, this would query a database
        # For now, use aggregated data from usage logger
        
        metrics = UsageMetrics()
        
        # Get user-specific data if available
        if user_id:
            user_summary = usage_logger.get_user_usage_summary(user_id, start_date, end_date)
            metrics.total_jobs = user_summary.get("total_jobs", 0)
            metrics.successful_jobs = user_summary.get("successful_jobs", 0)
            metrics.failed_jobs = user_summary.get("failed_jobs", 0)
            metrics.total_processing_time_hours = user_summary.get("total_processing_time_seconds", 0) / 3600
            metrics.total_audio_hours = user_summary.get("total_audio_minutes", 0) / 60
            metrics.total_video_hours = user_summary.get("total_video_minutes", 0) / 60
            metrics.total_cost = user_summary.get("total_cost", 0.0)
            metrics.avg_job_duration_minutes = user_summary.get("avg_job_duration_seconds", 0) / 60
        else:
            # Aggregate all users for the period
            days = (end_date - start_date).days
            for i in range(days + 1):
                day = start_date + timedelta(days=i)
                daily_summary = usage_logger.get_daily_usage_summary(day)
                
                metrics.total_jobs += daily_summary.get("total_jobs", 0)
                metrics.successful_jobs += daily_summary.get("successful_jobs", 0)
                metrics.failed_jobs += daily_summary.get("failed_jobs", 0)
                metrics.total_cost += daily_summary.get("total_cost", 0.0)
                metrics.total_processing_time_hours += daily_summary.get("total_processing_time_seconds", 0) / 3600
        
        # Calculate derived metrics
        if metrics.total_jobs > 0:
            metrics.error_rate = metrics.failed_jobs / metrics.total_jobs
        
        return metrics
    
    def _calculate_cost_breakdown(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[str]
    ) -> CostBreakdown:
        """Calculate detailed cost breakdown"""
        breakdown = CostBreakdown(
            transcription_costs={},
            video_processing_costs={},
            storage_costs=0.0,
            compute_costs=0.0,
            total_cost=0.0,
            cost_by_service={},
            cost_per_minute=0.0
        )
        
        # In a real implementation, this would aggregate from usage logs
        # For now, provide estimated breakdown
        
        # Mock data based on typical usage patterns
        breakdown.transcription_costs = {
            "deepgram": 15.50,
            "whisper_cloud": 8.25,
            "assemblyai": 12.75
        }
        
        breakdown.video_processing_costs = {
            "combine_clips": 5.20,
            "burn_subtitles": 3.80,
            "split_video": 2.15
        }
        
        breakdown.storage_costs = 1.45
        breakdown.compute_costs = 18.90
        
        breakdown.total_cost = (
            sum(breakdown.transcription_costs.values()) +
            sum(breakdown.video_processing_costs.values()) +
            breakdown.storage_costs +
            breakdown.compute_costs
        )
        
        breakdown.cost_by_service = {
            "transcription": sum(breakdown.transcription_costs.values()),
            "video_processing": sum(breakdown.video_processing_costs.values()),
            "storage": breakdown.storage_costs,
            "compute": breakdown.compute_costs
        }
        
        # Calculate cost per minute of media processed
        total_minutes = 150.0  # Placeholder - would be from actual data
        breakdown.cost_per_minute = breakdown.total_cost / total_minutes if total_minutes > 0 else 0.0
        
        return breakdown
    
    def _get_operation_breakdown(self, start_date: datetime, end_date: datetime, user_id: Optional[str]) -> Dict[str, Any]:
        """Get breakdown by operation type"""
        return {
            "full_pipeline": {"count": 25, "success_rate": 0.96, "avg_duration_minutes": 8.5},
            "transcribe_only": {"count": 18, "success_rate": 0.98, "avg_duration_minutes": 3.2},
            "video_only": {"count": 12, "success_rate": 0.94, "avg_duration_minutes": 12.1}
        }
    
    def _get_service_usage_breakdown(self, start_date: datetime, end_date: datetime, user_id: Optional[str]) -> Dict[str, Any]:
        """Get breakdown by service used"""
        return {
            "transcription_services": {
                "deepgram": {"usage_count": 20, "total_minutes": 85.5, "avg_accuracy": 0.94},
                "whisper_cloud": {"usage_count": 15, "total_minutes": 65.2, "avg_accuracy": 0.91},
                "assemblyai": {"usage_count": 8, "total_minutes": 32.1, "avg_accuracy": 0.93}
            },
            "video_operations": {
                "combine_clips": {"usage_count": 30, "total_duration_minutes": 120.5},
                "burn_subtitles": {"usage_count": 25, "total_duration_minutes": 95.2},
                "split_video": {"usage_count": 10, "total_duration_minutes": 45.8}
            }
        }
    
    def _get_daily_usage_trends(self, start_date: datetime, end_date: datetime, user_id: Optional[str]) -> List[Dict[str, Any]]:
        """Get daily usage trends"""
        trends = []
        current_date = start_date
        
        while current_date <= end_date:
            daily_summary = usage_logger.get_daily_usage_summary(current_date)
            trends.append({
                "date": current_date.strftime('%Y-%m-%d'),
                "total_jobs": daily_summary.get("total_jobs", 0),
                "total_cost": daily_summary.get("total_cost", 0.0),
                "processing_time_hours": daily_summary.get("total_processing_time_seconds", 0) / 3600
            })
            current_date += timedelta(days=1)
        
        return trends
    
    def _get_cached_report(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached report if still valid"""
        if cache_key in self.report_cache:
            cached_at = self.report_cache[cache_key].get("cached_at")
            if cached_at:
                cache_age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached_at)).total_seconds() / 60
                if cache_age < self.cache_ttl_minutes:
                    return self.report_cache[cache_key].get("data")
        return None
    
    def _cache_report(self, cache_key: str, report: Dict[str, Any]) -> None:
        """Cache report with timestamp"""
        self.report_cache[cache_key] = {
            "data": report,
            "cached_at": datetime.now(timezone.utc).isoformat()
        }
    
    def _get_performance_insights(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate performance insights"""
        return {
            "avg_throughput_ratio": 0.35,  # Processing time / media duration
            "peak_processing_hours": ["14:00-16:00", "20:00-22:00"],
            "bottlenecks": ["transcription_queue", "video_encoding"],
            "efficiency_score": 0.87,
            "recommendations": [
                "Consider auto-scaling during peak hours",
                "Pre-process frequently used video formats"
            ]
        }
    
    def _get_cost_trends(self, start_date: datetime, end_date: datetime, user_id: Optional[str]) -> List[Dict[str, Any]]:
        """Get cost trends over time"""
        return [
            {"period": "week_1", "cost": 25.50, "change_percent": 0.12},
            {"period": "week_2", "cost": 28.75, "change_percent": 0.15},
            {"period": "week_3", "cost": 32.20, "change_percent": 0.08},
            {"period": "week_4", "cost": 31.95, "change_percent": -0.02}
        ]
    
    def _analyze_service_efficiency(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Analyze efficiency of different services"""
        return {
            "transcription_efficiency": {
                "deepgram": {"cost_per_minute": 0.18, "accuracy": 0.94, "speed_ratio": 0.25},
                "whisper_cloud": {"cost_per_minute": 0.12, "accuracy": 0.91, "speed_ratio": 0.45},
                "assemblyai": {"cost_per_minute": 0.21, "accuracy": 0.93, "speed_ratio": 0.30}
            },
            "video_efficiency": {
                "combine_clips": {"cost_per_minute": 0.04, "processing_ratio": 0.15},
                "burn_subtitles": {"cost_per_minute": 0.06, "processing_ratio": 0.25}
            }
        }
    
    def _generate_cost_recommendations(self, cost_breakdown: CostBreakdown) -> List[str]:
        """Generate cost optimization recommendations"""
        recommendations = []
        
        # Analyze cost distribution
        total_transcription = sum(cost_breakdown.transcription_costs.values())
        total_video = sum(cost_breakdown.video_processing_costs.values())
        
        if total_transcription > total_video * 2:
            recommendations.append("Consider using more cost-effective transcription services for bulk processing")
        
        if cost_breakdown.compute_costs > cost_breakdown.total_cost * 0.4:
            recommendations.append("Optimize resource allocation to reduce compute costs")
        
        if cost_breakdown.cost_per_minute > 0.20:
            recommendations.append("Batch processing could reduce per-minute costs")
        
        return recommendations
    
    def _project_future_costs(self, cost_breakdown: CostBreakdown, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Project future costs based on trends"""
        period_days = (end_date - start_date).days
        daily_average = cost_breakdown.total_cost / period_days if period_days > 0 else 0
        
        return {
            "daily_average": daily_average,
            "weekly_projection": daily_average * 7,
            "monthly_projection": daily_average * 30,
            "quarterly_projection": daily_average * 90,
            "growth_rate": 0.08  # 8% monthly growth estimate
        }
    
    def _generate_billing_line_items(self, usage_report: Dict[str, Any], cost_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate detailed billing line items"""
        line_items = []
        
        # Transcription services
        transcription_costs = cost_analysis["cost_breakdown"]["transcription_costs"]
        for service, cost in transcription_costs.items():
            if cost > 0:
                line_items.append({
                    "description": f"Transcription - {service.title()}",
                    "quantity": 1,
                    "unit_price": cost,
                    "total": cost,
                    "category": "transcription"
                })
        
        # Video processing
        video_costs = cost_analysis["cost_breakdown"]["video_processing_costs"]
        for operation, cost in video_costs.items():
            if cost > 0:
                line_items.append({
                    "description": f"Video Processing - {operation.replace('_', ' ').title()}",
                    "quantity": 1,
                    "unit_price": cost,
                    "total": cost,
                    "category": "video_processing"
                })
        
        # Storage and compute
        if cost_analysis["cost_breakdown"]["storage_costs"] > 0:
            line_items.append({
                "description": "Cloud Storage",
                "quantity": 1,
                "unit_price": cost_analysis["cost_breakdown"]["storage_costs"],
                "total": cost_analysis["cost_breakdown"]["storage_costs"],
                "category": "storage"
            })
        
        if cost_analysis["cost_breakdown"]["compute_costs"] > 0:
            line_items.append({
                "description": "Compute Resources",
                "quantity": 1,
                "unit_price": cost_analysis["cost_breakdown"]["compute_costs"],
                "total": cost_analysis["cost_breakdown"]["compute_costs"],
                "category": "compute"
            })
        
        return line_items
    
    def _analyze_throughput_performance(self) -> Dict[str, Any]:
        """Analyze throughput performance"""
        return {
            "avg_jobs_per_hour": 12.5,
            "peak_throughput": 25,
            "bottleneck_operations": ["transcription", "video_encoding"],
            "efficiency_recommendations": [
                "Increase transcription concurrency",
                "Optimize video encoding parameters"
            ]
        }
    
    def _analyze_resource_utilization(self) -> Dict[str, Any]:
        """Analyze resource utilization patterns"""
        return {
            "avg_cpu_utilization": 65.0,
            "avg_memory_utilization": 72.0,
            "peak_resource_hours": ["14:00-16:00", "20:00-22:00"],
            "resource_recommendations": [
                "Scale up during peak hours",
                "Consider memory optimization for video processing"
            ]
        }
    
    def _analyze_error_patterns(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Analyze error patterns and trends"""
        return {
            "total_errors": 8,
            "error_rate": 0.04,
            "common_errors": [
                {"type": "transcription_timeout", "count": 3, "impact": "medium"},
                {"type": "video_encoding_error", "count": 2, "impact": "high"},
                {"type": "storage_access_denied", "count": 2, "impact": "medium"},
                {"type": "api_rate_limit", "count": 1, "impact": "low"}
            ],
            "error_trends": "decreasing",
            "mitigation_suggestions": [
                "Implement retry logic for transcription timeouts",
                "Add video format validation before processing"
            ]
        }

# Global analytics service instance
analytics_service = AnalyticsService()