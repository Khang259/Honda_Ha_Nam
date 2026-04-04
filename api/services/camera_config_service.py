"""
This service is used to get the camera config from the BE server.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from api.clients.be_node_id_client import BENodeIdClient
from api.mappers.camera_config_mapper import map_be_node_response_to_cameras
from api.settings import settings


@dataclass
class CameraConfigCache:
    area: str
    fetched_at: float
    cameras: List[Dict[str, Any]]
    source: str  # "be" | "cache"


class CameraConfigService:
    def __init__(self, client: Optional[BENodeIdClient] = None):
        self._client = client or BENodeIdClient(settings.BE_BASE_URL, timeout_s=settings.BE_TIMEOUT_S)
        self._cache: Dict[str, CameraConfigCache] = {}

    # This method is used to get the cached camera config of the area.
    def get_cached(self, area: str) -> Optional[CameraConfigCache]:
        return self._cache.get(area.upper())

    # This method is used to check if the cache of the area is valid.
    def is_cache_valid(self, area: str) -> bool:
        cached = self.get_cached(area)
        if not cached:
            return False
        return (time.time() - cached.fetched_at) < settings.CONFIG_CACHE_TTL_S

    # This method is used to get the camera config of the area.
    async def get(self, area: str) -> CameraConfigCache:
        area_u = area.upper()
        if self.is_cache_valid(area_u):
            cached = self._cache[area_u]
            return CameraConfigCache(area=area_u, fetched_at=cached.fetched_at, cameras=cached.cameras, source="cache")
        return await self.refresh(area_u)

    async def refresh(self, area: str) -> CameraConfigCache:
        area_u = area.upper()
        try:
            be_payload = await self._client.get_by_area(area_u)
            cameras = map_be_node_response_to_cameras(be_payload)
            cache = CameraConfigCache(area=area_u, fetched_at=time.time(), cameras=cameras, source="be")
            self._cache[area_u] = cache
            return cache
        except Exception:
            # Fallback to stale cache if exists
            cached = self._cache.get(area_u)
            if cached:
                return CameraConfigCache(area=area_u, fetched_at=cached.fetched_at, cameras=cached.cameras, source="cache")
            raise


camera_config_service = CameraConfigService()

