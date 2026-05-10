from __future__ import annotations
from fastapi import APIRouter, HTTPException, Path

from api_http.services.streaming_service import streaming_service

router = APIRouter()


@router.get("/video-feed/{cam_id}")
async def get_video_feed(
    cam_id: str = Path(..., description="Camera ID (cameraId hoặc cam_0_0)")
):
    try:
        return await streaming_service.get_video_feed(cam_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Streaming error: {str(e)}"
        )