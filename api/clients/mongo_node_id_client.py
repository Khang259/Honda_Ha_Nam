"""
MongoDB client for camera config CRUD operations.
"""

from typing import Any, Dict, List, Tuple
from pymongo.errors import BulkWriteError
from api.core.database import get_collection
from utils.setup_log import setup_logger

logger = setup_logger("mongo_node_id_client", "logs/mongo_node_id_client/log")

class MongoNodeIdClient:
    """Client đọc camera config từ MongoDB collection node_id."""
    
    def __init__(self, collection_name: str = "node_id"):
        self._collection_name = collection_name
    #TODO: kiểm tra 2 hàm get_by_area và get_all có cần thiết không?
    async def get_by_area(self, area_name: str) -> List[Dict[str, Any]]:
        """
        Lấy tất cả camera trong area từ Mongo.
        Trả về list[dict] đã bỏ _id, giả định schema đã chuẩn.
        """
        col = get_collection(self._collection_name)
        cursor = col.find({"area_name": area_name.upper()},{"_id": 0}).sort("cameraId", 1)
        docs = await cursor.to_list(length=None)
        return [doc for doc in docs if isinstance(doc, dict)]
    
    async def get_all(self) -> List[Dict[str, Any]]:
        """Lấy tất cả camera (không filter area)."""
        col = get_collection(self._collection_name)
        cursor = col.find({}, {"_id": 0}).sort("cameraId", 1)
        docs = await cursor.to_list(length=None)
        return [doc for doc in docs if isinstance(doc, dict)]
    
    async def create_many(self, camera_docs: List[Dict[str, Any]]) -> Tuple[int, List[int]]:
        """
        Thêm nhiều camera vào Mongo.
        Trả về (số lượng inserted, list cameraId bị trùng/lỗi).
        Sử dụng ordered=False để insert phần hợp lệ khi có lỗi.
        """
        col = get_collection(self._collection_name)
        inserted_count = 0
        duplicate_camera_ids = []
        
        try:
            result = await col.insert_many(camera_docs, ordered=False)
            inserted_count = len(result.inserted_ids)
            logger.info(f"Inserted {inserted_count} node_id documents")
        except BulkWriteError as e:
            inserted_count = e.details.get('nInserted', 0)
            
            # Lấy danh sách cameraId bị duplicate (E11000)
            for error in e.details.get('writeErrors', []):
                if error.get('code') == 11000:  # Duplicate key error
                    # Extract cameraId từ error message hoặc từ document gốc
                    idx = error.get('index', -1)
                    if 0 <= idx < len(camera_docs):
                        dup_camera_id = camera_docs[idx].get('cameraId')
                        if dup_camera_id:
                            duplicate_camera_ids.append(dup_camera_id)
            
            logger.warning(
                f"BulkWrite partial success: inserted={inserted_count}, "
                f"duplicates={len(duplicate_camera_ids)}"
            )
        
        return inserted_count, duplicate_camera_ids
    
    async def update_by_camera_id(self, camera_id: int, update_data: Dict[str, Any]) -> bool:
        """Update node_id theo cameraId. Trả về True nếu modified."""
        col = get_collection(self._collection_name)
        result = await col.update_many(
            {"cameraId": camera_id},
            {"$set": update_data}
        )
        return result.modified_count > 0
    
    async def delete_by_camera_id(self, camera_id: int) -> bool:
        """Xoá node_id theo cameraId. Trả về True nếu deleted."""
        col = get_collection(self._collection_name)
        result = await col.delete_many({"cameraId": camera_id})
        logger.info(f"Deleted node_id cameraId={camera_id}, deleted={result.deleted_count}")
        return result.deleted_count > 0
