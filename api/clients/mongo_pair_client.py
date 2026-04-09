"""
MongoDB client for validate pairs
Thiết kế mới: 1 document = 1 pair với unique index (start, end)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pymongo.errors import BulkWriteError

from api.core.database import get_collection
from utils.setup_log import setup_logger

logger = setup_logger("mongo_pair_client", "logs/mongo_pair_client/log")


class MongoPairClient:
    """Client đọc/ghi validate pairs từ MongoDB collection validate_pairs."""

    def __init__(self, collection_name: str = "validate_pairs"):
        self._collection_name = collection_name

    async def get_all_pairs(self) -> List[Dict[str, Any]]:
        """Lấy tất cả validate pairs từ Mongo."""
        col = get_collection(self._collection_name)
        cursor = col.find({}, {"_id": 0}).sort([("area_name", 1), ("start", 1)])
        docs = await cursor.to_list(length=None)
        logger.info(f"Fetched {len(docs)} pairs (all areas)")
        return [doc for doc in docs if isinstance(doc, dict)]

    async def get_pairs_by_area(self, area_name: str) -> List[Dict[str, Any]]:
        """Lấy validate pairs theo area từ Mongo."""
        col = get_collection(self._collection_name)
        cursor = col.find(
            {"area_name": area_name.upper()}, {"_id": 0}
        ).sort("start", 1)
        docs = await cursor.to_list(length=None)
        logger.info(f"Fetched {len(docs)} pairs for area {area_name}")
        return [doc for doc in docs if isinstance(doc, dict)]

    async def add_pairs(
        self, area_name: str, pairs: List[Dict[str, Optional[str]]]
    ) -> Tuple[int, List[Dict[str, Optional[str]]]]:
        """
        Thêm 1 hoặc nhiều pairs vào Mongo.
        Trả về (số lượng inserted, list pairs bị duplicate).
        Sử dụng ordered=False để insert phần hợp lệ khi có lỗi.
        """
        col = get_collection(self._collection_name)
        now = datetime.now(timezone.utc)

        # Transform thành documents với area_name và created_at
        docs_to_insert = [
            {
                "start": p["start"],
                "end": p.get("end"),
                "area_name": area_name.upper(),
                "created_at": now,
            }
            for p in pairs
        ]

        inserted_count = 0
        duplicate_pairs = []

        try:
            result = await col.insert_many(docs_to_insert, ordered=False)
            inserted_count = len(result.inserted_ids)
            logger.info(f"Inserted {inserted_count} pairs into area {area_name}")
        except BulkWriteError as e:
            inserted_count = e.details.get("nInserted", 0)

            # Lấy danh sách pairs bị duplicate (E11000)
            for error in e.details.get("writeErrors", []):
                if error.get("code") == 11000:  # Duplicate key error
                    idx = error.get("index", -1)
                    if 0 <= idx < len(docs_to_insert):
                        dup_doc = docs_to_insert[idx]
                        duplicate_pairs.append(
                            {"start": dup_doc["start"], "end": dup_doc.get("end")}
                        )

            logger.warning(
                f"BulkWrite partial success: inserted={inserted_count}, "
                f"duplicates={len(duplicate_pairs)}"
            )

        return inserted_count, duplicate_pairs

    async def delete_pairs(
        self, pairs_to_delete: List[Dict[str, Optional[str]]]
    ) -> int:
        """
        Xóa 1 hoặc nhiều pairs cụ thể (theo start và end).
        Trả về số lượng pairs đã xóa.
        """
        col = get_collection(self._collection_name)

        # Build query $or để match từng pair
        or_conditions = []
        for p in pairs_to_delete:
            condition = {"start": p["start"]}
            if p.get("end") is not None:
                condition["end"] = p["end"]
            else:
                condition["end"] = None
            or_conditions.append(condition)

        if not or_conditions:
            return 0

        result = await col.delete_many({"$or": or_conditions})
        logger.info(f"Deleted {result.deleted_count} pairs")
        return result.deleted_count