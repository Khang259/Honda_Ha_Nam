"""
MongoDB client for camera config CRUD operations.
"""

from typing import Any, Dict, List
from api.core.database import get_collection
from utils.setup_log import setup_logger

logger = setup_logger("mongo_camera_client", "logs/mongo_camera_client/log")

class MongoCameraClient:
    """Client đọc camera config từ MongoDB collection node_id."""
    
    def __init__(self, collection_name: str = "node_id"):
        self._collection_name = collection_name
    
    async def get_by_area(self, area_name: str) -> List[Dict[str, Any]]:
        """
        Lấy tất cả camera trong area từ Mongo.
        Trả về list[dict] đã bỏ _id, giả định schema đã chuẩn.
        """
        col = get_collection(self._collection_name)
        cursor = col.find(
            {"area_name": area_name.upper()},
            {"_id": 0}
        ).sort("cameraId", 1)
        docs = await cursor.to_list(length=None)
        logger.info(f"Fetched {len(docs)} cameras for area {area_name}")
        return [doc for doc in docs if isinstance(doc, dict)]
    
    async def get_all(self) -> List[Dict[str, Any]]:
        """Lấy tất cả camera (không filter area)."""
        col = get_collection(self._collection_name)
        cursor = col.find({}, {"_id": 0}).sort("cameraId", 1)
        docs = await cursor.to_list(length=None)
        print(f"Number docs : {len(docs)}")
        logger.info(f"Fetched {len(docs)} cameras (all areas)")
        return [doc for doc in docs if isinstance(doc, dict)]
    
    async def create(self, camera_doc: Dict[str, Any]) -> str:
        """Thêm camera mới vào Mongo. Trả về inserted_id."""
        col = get_collection(self._collection_name)
        result = await col.insert_one(camera_doc)
        logger.info(f"Created camera cameraId={camera_doc.get('cameraId')}")
        return str(result.inserted_id)
    
    async def update_by_camera_id(self, camera_id: int, update_data: Dict[str, Any]) -> bool:
        """Update camera theo cameraId. Trả về True nếu modified."""
        col = get_collection(self._collection_name)
        result = await col.update_one(
            {"cameraId": camera_id},
            {"$set": update_data}
        )
        logger.info(f"Updated camera cameraId={camera_id}, modified={result.modified_count}")
        return result.modified_count > 0
    
    async def delete_by_camera_id(self, camera_id: int) -> bool:
        """Xoá camera theo cameraId. Trả về True nếu deleted."""
        col = get_collection(self._collection_name)
        result = await col.delete_one({"cameraId": camera_id})
        logger.info(f"Deleted camera cameraId={camera_id}, deleted={result.deleted_count}")
        return result.deleted_count > 0
