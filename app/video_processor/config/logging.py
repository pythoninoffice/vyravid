"""
Logging configuration for Cloud Video Processor
"""

import structlog
import logging
import os
import sys
from typing import Any, Dict
from video_processor.config.persistent_error_logging import install_persistent_error_logging

def configure_logging(debug: bool = False) -> None:
    """
    Configure structured logging for the application
    
    Args:
        debug: Enable debug logging level
    """
    # Set logging level
    log_level = logging.DEBUG if debug else logging.INFO
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    
    # Configure structlog
    structlog.configure(
        processors=[
            # Add timestamp
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            # Add context
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # JSON output for Cloud Logging
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    install_persistent_error_logging(
        service_name="cloud-video-processor",
        environment=os.getenv("ENV", os.getenv("ENVIRONMENT", "production")),
    )

def get_logger(name: str = None) -> structlog.BoundLogger:
    """
    Get a structured logger instance
    
    Args:
        name: Logger name (optional)
        
    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)

class LoggingMiddleware:
    """
    FastAPI middleware for request/response logging
    """
    
    def __init__(self, app):
        self.app = app
        self.logger = get_logger("middleware")
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Log incoming request
            self.logger.info(
                "request_started",
                method=scope["method"],
                path=scope["path"],
                query_string=scope.get("query_string", b"").decode(),
                client=scope.get("client", ["unknown", 0])[0]
            )
        
        await self.app(scope, receive, send)
