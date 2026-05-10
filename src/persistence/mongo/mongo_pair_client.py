"""
MongoDB client for validate pairs
Thiết kế mới: 1 document = 1 pair với unique index (start, end)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pymongo.errors import BulkWriteError

from persistence.database import get_collection
from shared.setup_log import setup_logger

logger = setup_logger("mongo_pair_client", "logs/mongo_pair_client/log")


class MongoPairClient:
    """Client đọc/ghi validate pairs từ MongoDB collection validate_pairs."""

    def __init__(self, collection_name: str = "validate_pairs_test"):
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
                "updated_at": now,
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

    def _pair_filter(self, p: Dict[str, Optional[str]]) -> Dict[str, Any]:
        """Filter Mongo cho 1 pair (start, end) — end None được lưu rõ ràng."""
        cond: Dict[str, Any] = {"start": p["start"]}
        if p.get("end") is not None:
            cond["end"] = p["end"]
        else:
            cond["end"] = None
        return cond

    async def update_pairs(
        self, updates: List[Dict[str, Any]]
    ) -> Tuple[int, List[Dict[str, Optional[str]]]]:
        """
        Cập nhật 1 hoặc nhiều pairs theo `match`, optional new_start/new_end/area_name.
        Luôn set `updated_at`. Nếu document thiếu `created_at` thì set lúc update.
        Trả về (số bản ghi modified, danh sách match không tìm thấy).
        """
        col = get_collection(self._collection_name)
        now = datetime.now(timezone.utc)
        modified_total = 0
        not_found: List[Dict[str, Optional[str]]] = []

        for item in updates:
            match = item.get("pairs") or {}
            filt = self._pair_filter(match)

            doc = await col.find_one(filt)
            if not doc:
                not_found.append(
                    {"start": match.get("start", ""), "end": match.get("end")}
                )
                continue

            set_doc: Dict[str, Any] = {"updated_at": now}
            if doc.get("created_at") is None:
                set_doc["created_at"] = now

            if item.get("new_start") is not None:
                set_doc["start"] = item["new_start"]
            if "new_end" in item:
                # Cho phép set end thành None rõ ràng
                set_doc["end"] = item["new_end"]
            if item.get("area_name") is not None:
                set_doc["area_name"] = str(item["area_name"]).upper()

            result = await col.update_one(filt, {"$set": set_doc})
            modified_total += result.modified_count

        logger.info(
            f"update_pairs: modified={modified_total}, not_found={len(not_found)}"
        )
        return modified_total, not_found

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