"""
This service is used to get the camera config from MongoDB directly.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from api.clients.mongo_node_id_client import MongoNodeIdClient
from utils.setup_log import setup_logger

logger = setup_logger("node_id_config_service", "logs/node_id_config_service/log")

class NodeIdConfigService:
    """Service lấy node_id config từ MongoDB (không cache, không mapper)."""
    
    def __init__(self, client: Optional[MongoNodeIdClient] = None):
        self._client = client or MongoNodeIdClient()
    
    async def get(self, area: str) -> List[Dict[str, Any]]:
        """
        Lấy node_id config theo area từ Mongo.
        Không cache, luôn fetch mới.
        """
        node_ids = await self._client.get_by_area(area.upper())
        logger.info(f"Loaded {len(node_ids)} node_ids for area {area}")
        return node_ids
    
    async def refresh(self, area: str) -> List[Dict[str, Any]]:
        """Alias cho get() để backward-compatible với runtime_service."""
        return await self.get(area)

node_id_config_service = NodeIdConfigService()

