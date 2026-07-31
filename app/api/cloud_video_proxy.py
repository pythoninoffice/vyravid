"""
Cloud Video Processor Proxy Endpoint

Proxies requests from /api/cloud-video/* to the cloud-video-processor service
running on Google Cloud Run or locally.
"""

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
import aiohttp
import logging
import os
from typing import Any, Dict

from auth import get_current_user

router = APIRouter(prefix="/api/cloud-video", tags=["cloud-video-proxy"])
logger = logging.getLogger(__name__)

# Get cloud video processor URL from environment
CLOUD_VIDEO_PROCESSOR_URL = os.getenv('CLOUD_VIDEO_PROCESSOR_URL') or (os.getenv('VYRAVID_PUBLIC_BASE', 'http://localhost:8000').rstrip('/') + '/vp')

# Service account for authentication
from services.cloud_video_service import CloudVideoService
cloud_video_service = CloudVideoService()


@router.post("/timeline/render")
async def proxy_timeline_render(
    request: Request,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Proxy timeline render requests to cloud-video-processor

    This endpoint forwards timeline rendering requests to the cloud-video-processor
    service and returns the response.
    """
    try:
        # Get request body
        body = await request.json()

        logger.info(f"📤 Proxying timeline render request to {CLOUD_VIDEO_PROCESSOR_URL}")
        logger.info(f"Request body: {body}")

        # Get authentication token
        token = await cloud_video_service._get_access_token()

        # Forward request to cloud-video-processor
        async with aiohttp.ClientSession() as session:
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            async with session.post(
                f"{CLOUD_VIDEO_PROCESSOR_URL}/timeline/render",
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=600)  # 10 minute timeout for rendering
            ) as response:
                response_data = await response.json()

                if response.status != 200:
                    logger.error(f"Cloud video processor error: {response_data}")
                    raise HTTPException(
                        status_code=response.status,
                        detail=response_data
                    )

                logger.info(f"✅ Timeline render response: {response_data}")
                return response_data

    except aiohttp.ClientError as e:
        logger.error(f"Failed to connect to cloud-video-processor: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail=f"Cloud video processor unavailable: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error proxying timeline render request: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to proxy request: {str(e)}"
        )
