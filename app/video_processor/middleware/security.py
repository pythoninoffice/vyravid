"""
Security middleware for Cloud Video Processor API
"""

import time
import structlog
import json
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from typing import Dict, Optional, Callable, Awaitable
from collections import defaultdict, deque
import asyncio
import os

from video_processor.services.auth_service import validate_api_key

logger = structlog.get_logger()

# Rate limiting storage (in-memory for simplicity, use Redis for production)
rate_limit_storage: Dict[str, deque] = defaultdict(deque)
request_sizes: Dict[str, deque] = defaultdict(deque)

class SecurityMiddleware:
    """Security middleware for authentication, rate limiting, and request validation"""
    
    def __init__(
        self,
        app,
        max_requests_per_minute: int = 60,
        max_request_size_mb: float = 100.0,
        enable_api_key_validation: bool = True
    ):
        self.app = app
        self.max_requests_per_minute = max_requests_per_minute
        self.max_request_size_bytes = int(max_request_size_mb * 1024 * 1024)
        self.enable_api_key_validation = enable_api_key_validation
    
    async def __call__(self, scope, receive, send):
        """ASGI application interface"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Create request object from scope
        from fastapi import Request
        request = Request(scope, receive)
        
        try:
            # Skip middleware for health check and service info endpoints
            if request.url.path in ["/health", "/"]:
                await self.app(scope, receive, send)
                return
            
            # 1. Request size validation
            await self._validate_request_size(request)
            
            # 2. Rate limiting
            await self._check_rate_limit(request)
            
            # 3. API key validation (if enabled)
            if self.enable_api_key_validation:
                await self._validate_api_key(request)
            
            # 4. Security headers validation
            await self._validate_security_headers(request)
            
            # Custom send wrapper to add security headers
            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    headers = dict(message.get("headers", []))
                    
                    # Add security headers
                    security_headers = {
                        b"x-content-type-options": b"nosniff",
                        b"x-frame-options": b"DENY",
                        b"x-xss-protection": b"1; mode=block"
                    }
                    
                    # Add HSTS only for HTTPS
                    if request.url.scheme == "https":
                        security_headers[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"
                    
                    # Update headers
                    for key, value in security_headers.items():
                        headers[key] = value
                    
                    message["headers"] = list(headers.items())
                
                await send(message)
            
            # Process the request with the wrapped send
            await self.app(scope, receive, send_wrapper)
            
        except HTTPException as e:
            # Convert HTTPException to ASGI response
            response_content = {"detail": e.detail}
            response_body = json.dumps(response_content).encode()
            
            await send({
                "type": "http.response.start",
                "status": e.status_code,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(response_body)).encode()]
                ]
            })
            await send({
                "type": "http.response.body",
                "body": response_body
            })
            
        except Exception as e:
            logger.error(
                "security_middleware_error",
                error=str(e),
                path=request.url.path if hasattr(request, 'url') else "unknown",
                method=scope.get("method", "unknown")
            )
            
            # Send 500 error response
            error_content = {"detail": "Security validation failed"}
            error_body = json.dumps(error_content).encode()
            
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(error_body)).encode()]
                ]
            })
            await send({
                "type": "http.response.body",
                "body": error_body
            })
    
    async def _validate_request_size(self, request: Request) -> None:
        """Validate request size limits"""
        # Check Content-Length header
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > self.max_request_size_bytes:
                    logger.warning(
                        "request_size_exceeded",
                        size=size,
                        max_size=self.max_request_size_bytes,
                        path=request.url.path,
                        client_ip=self._get_client_ip(request)
                    )
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Request size {size} bytes exceeds limit of {self.max_request_size_bytes} bytes"
                    )
            except ValueError:
                # Invalid Content-Length header
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid Content-Length header"
                )
    
    async def _check_rate_limit(self, request: Request) -> None:
        """Check rate limiting per client IP"""
        client_ip = self._get_client_ip(request)
        current_time = time.time()
        
        # Clean old requests (older than 1 minute)
        client_requests = rate_limit_storage[client_ip]
        while client_requests and current_time - client_requests[0] > 60:
            client_requests.popleft()
        
        # Check if limit exceeded
        if len(client_requests) >= self.max_requests_per_minute:
            logger.warning(
                "rate_limit_exceeded",
                client_ip=client_ip,
                requests_count=len(client_requests),
                max_requests=self.max_requests_per_minute,
                path=request.url.path
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {self.max_requests_per_minute} requests per minute",
                headers={"Retry-After": "60"}
            )
        
        # Add current request
        client_requests.append(current_time)
    
    async def _validate_api_key(self, request: Request) -> None:
        """Validate API key if provided"""
        api_key = request.headers.get("X-API-Key")
        
        # If API key is provided, validate it
        if api_key:
            if not validate_api_key(api_key):
                logger.warning(
                    "invalid_api_key",
                    client_ip=self._get_client_ip(request),
                    path=request.url.path,
                    api_key_prefix=api_key[:10] if api_key else "None"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid API key"
                )
        # Note: API key is optional, main auth is via Bearer token
        # This provides an additional security layer if configured
    
    async def _validate_security_headers(self, request: Request) -> None:
        """Validate security-related headers"""
        # Check for suspicious User-Agent strings
        user_agent = request.headers.get("user-agent", "").lower()
        suspicious_agents = ["bot", "crawler", "spider", "scraper", "scanner"]
        
        if any(agent in user_agent for agent in suspicious_agents):
            logger.info(
                "suspicious_user_agent",
                user_agent=user_agent,
                client_ip=self._get_client_ip(request),
                path=request.url.path
            )
            # Don't block, just log for monitoring
        
        # Validate Content-Type for POST requests
        if request.method in ["POST", "PUT", "PATCH"]:
            content_type = request.headers.get("content-type", "")
            if content_type and not content_type.startswith("application/json"):
                if request.url.path not in ["/health", "/"]:  # Skip for non-API endpoints
                    logger.warning(
                        "invalid_content_type",
                        content_type=content_type,
                        path=request.url.path,
                        client_ip=self._get_client_ip(request)
                    )
                    raise HTTPException(
                        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail="Content-Type must be application/json"
                    )
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address considering proxy headers"""
        # Check for common proxy headers
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Take the first IP (client IP)
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fallback to direct connection IP
        if hasattr(request, "client") and request.client:
            return request.client.host
        
        return "unknown"

async def api_key_header_validation(request: Request) -> Optional[str]:
    """
    Optional API key validation dependency
    
    Can be used with Depends() for specific endpoints that require API key
    """
    api_key = request.headers.get("X-API-Key")
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "X-API-Key"}
        )
    
    if not validate_api_key(api_key):
        logger.warning(
            "api_key_validation_failed",
            api_key_prefix=api_key[:10] if api_key else "None"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    return api_key

# Rate limiting configuration based on environment
def get_rate_limit_config():
    """Get rate limiting configuration from environment variables"""
    return {
        "max_requests_per_minute": int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "60")),
        "max_request_size_mb": float(os.getenv("MAX_REQUEST_SIZE_MB", "100.0")),
        "enable_api_key_validation": os.getenv("ENABLE_API_KEY_VALIDATION", "true").lower() == "true"
    }