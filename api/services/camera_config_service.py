"""
This service is used to get the camera config from MongoDB directly.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from api.clients.mongo_camera_client import MongoCameraClient
from utils.setup_log import setup_logger

logger = setup_logger("camera_config_service", "logs/camera_config_service/log")

class CameraConfigService:
    """Service lấy camera config từ MongoDB (không cache, không mapper)."""
    
    def __init__(self, client: Optional[MongoCameraClient] = None):
        self._client = client or MongoCameraClient()
    
    async def get(self, area: str) -> List[Dict[str, Any]]:
        """
        Lấy camera config theo area từ Mongo.
        Không cache, luôn fetch mới.
        """
        cameras = await self._client.get_by_area(area.upper())
        logger.info(f"Loaded {len(cameras)} cameras for area {area}")
        return cameras
    
    async def refresh(self, area: str) -> List[Dict[str, Any]]:
        """Alias cho get() để backward-compatible với runtime_service."""
        return await self.get(area)

camera_config_service = CameraConfigService()

