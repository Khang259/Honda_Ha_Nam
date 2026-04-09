"""
MongoDB client for validate pairs
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from api.core.database import get_collection
from utils.setup_log import setup_logger

logger = setup_logger("mongo_pair_client", "logs/mongo_pair_client/log")


class MongoPairClient:
    """Client đọc/ghi validate pairs từ MongoDB collection validate_pairs."""

    def __init__(self, collection_name: str = "validate_pairs"):
        self._collection_name = collection_name

    async def get_all_pairs(self) -> List[Dict[str, Any]]:
        """Lấy tất cả validate pairs (tất cả area) từ Mongo."""
        col = get_collection(self._collection_name)
        cursor = col.find({}, {"_id": 0}).sort("area_name", 1)
        docs = await cursor.to_list(length=None)
        return [doc for doc in docs if isinstance(doc, dict)]

    async def get_pairs_by_area(self, area_name: str) -> Optional[Dict[str, Any]]:
        """Lấy validate pairs theo area từ Mongo. Trả về 1 document hoặc None."""
        col = get_collection(self._collection_name)
        doc = await col.find_one({"area_name": area_name.upper()}, {"_id": 0})
        if doc:
            logger.info(f"Fetched pairs for area {area_name}: {len(doc.get('pairs', []))} pairs")
        else:
            logger.warning(f"No pairs found for area {area_name}")
        return doc

    async def create_area(
        self, area_name: str, pairs: List[Dict[str, Optional[str]]]
    ) -> str:
        """
        Tạo mới area với pairs. Raise error nếu area đã tồn tại.
        pairs: list[{start: str, end: str|None}]
        """
        col = get_collection(self._collection_name)
        now = datetime.now(timezone.utc)
        
        existing = await col.find_one({"area_name": area_name.upper()})
        if existing:
            raise ValueError(f"Area {area_name} already exists")
        
        doc = {
            "area_name": area_name.upper(),
            "pairs": pairs,
            "created_at": now,
            "updated_at": now,
        }
        result = await col.insert_one(doc)
        logger.info(f"Created area {area_name} with {len(pairs)} pairs")
        return str(result.inserted_id)

    async def update_area(
        self, area_name: str, pairs: List[Dict[str, Optional[str]]]
    ) -> bool:
        """
        Cập nhật toàn bộ pairs cho area đã tồn tại.
        pairs: list[{start: str, end: str|None}]
        """
        col = get_collection(self._collection_name)
        now = datetime.now(timezone.utc)
        
        result = await col.update_one(
            {"area_name": area_name.upper()},
            {
                "$set": {
                    "pairs": pairs,
                    "updated_at": now,
                }
            },
        )
        logger.info(
            f"Updated area {area_name}: matched={result.matched_count}, modified={result.modified_count}"
        )
        return result.modified_count > 0

    async def delete_pairs(
        self, area_name: str, pairs_to_delete: List[Dict[str, Optional[str]]]
    ) -> bool:
        """
        Xóa 1 hoặc nhiều pairs cụ thể trong area.
        pairs_to_delete: list[{start: str, end: str|None}] - các pair cần xóa
        """
        col = get_collection(self._collection_name)
        now = datetime.now(timezone.utc)
        
        result = await col.update_one(
            {"area_name": area_name.upper()},
            {
                "$pull": {"pairs": {"$in": pairs_to_delete}},
                "$set": {"updated_at": now},
            },
        )
        logger.info(
            f"Deleted {len(pairs_to_delete)} pairs from area {area_name}: modified={result.modified_count}"
        )
        return result.modified_count > 0

    async def delete_area(self, area_name: str) -> bool:
        """Xóa toàn bộ document của 1 area."""
        col = get_collection(self._collection_name)
        result = await col.delete_one({"area_name": area_name.upper()})
        logger.info(f"Deleted area {area_name}: deleted={result.deleted_count}")
        return result.deleted_count > 0