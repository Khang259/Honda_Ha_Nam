"""
MongoDB client for camera config CRUD operations.
"""

from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from pymongo.errors import BulkWriteError
from persistence.database import get_collection
from shared.setup_log import setup_logger

logger = setup_logger("mongo_node_id_client", "logs/mongo_node_id_client/log")

class MongoNodeIdClient:
    """Client đọc camera config từ MongoDB collection node_id."""
    
    def __init__(self, collection_name: str = "node_id"):
        self._collection_name = collection_name
        self._end_points_collection_name = "end_points"

    async def check_exist(self, camera_id: int) -> bool:
        """Check if cameraId exists in MongoDB."""
        col = get_collection(self._collection_name)
        result = await col.find_one({"cameraId": camera_id})
        return result is not None

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
                if error.get('code') == 1002:  # Duplicate key error
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

    async def get_empty_car_points(self) -> List[Dict[str, Any]]:
        """Lấy tất cả điểm trống từ Mongo."""
        col = get_collection("end_points")
        cursor = col.find({}, {"_id": 0})
        docs = await cursor.to_list(length=None)
        return [doc for doc in docs if isinstance(doc, dict)]

    async def update_empty_car_points(self, end_points: str) -> Dict[str, Any]:
        col = get_collection(self._end_points_collection_name)
        result = await col.update_one(
            {"end_points": end_points},
            {"$set": {"empty_car": True}}
        )
        return {
            "code": 1000,
            "message": "Success"
        }
    
    async def get_by_worker(self, worker_id: str) -> List[Dict[str, Any]]:
        """
        Lấy tất cả cameras được assign cho một worker.
        
        Args:
            worker_id: ID của worker
            
        Returns:
            List[Dict]: Danh sách camera configs
        """
        col = get_collection(self._collection_name)
        cursor = col.find(
            {"current_worker": worker_id},
            {"_id": 0}
        ).sort("cameraId", 1)
        docs = await cursor.to_list(length=None)
        logger.debug(f"Found {len(docs)} cameras for worker {worker_id}")
        return [doc for doc in docs if isinstance(doc, dict)]
    #TODO: kiểm tra hàm claim_camera_atomic có cần thiết không?
    async def claim_camera_atomic(
        self, 
        camera_id: int, 
        worker_id: str
    ) -> Tuple[bool, int]:
        """
        Claim một camera với atomic fencing token increment.
        
        Args:
            camera_id: ID của camera
            worker_id: ID của worker
            
        Returns:
            Tuple[bool, int]: (success, new_fencing_token)
        """
        try:
            col = get_collection(self._collection_name)
            now = datetime.utcnow()
            # now_vietnam = now + timedelta(hours=7)
            # formatted_time =  now_vietnam.strftime("%Y-%m-%d %H:%M:%S")
            
            result = await col.find_one_and_update(
                {"cameraId": camera_id},
                {
                    "$inc": {"fencing_token": 1},
                    "$set": {
                        "current_worker": worker_id,
                        "last_assigned": now
                    }
                },
                return_document=True
            )
            
            if result:
                new_token = result.get("fencing_token", 0)
                logger.debug(
                    f"Camera {camera_id} claimed by {worker_id}, token={new_token}"
                )
                return True, new_token
            else:
                logger.warning(f"Camera {camera_id} not found for claim")
                return False, 0
                
        except Exception as e:
            logger.error(f"Failed to claim camera {camera_id}: {e}")
            return False, 0
    
    async def release_by_worker(self, worker_id: str) -> int:
        """
        Release tất cả cameras của một worker.
        
        Args:
            worker_id: ID của worker
            
        Returns:
            int: Số lượng cameras đã release
        """
        try:
            col = get_collection(self._collection_name)
            result = await col.update_many(
                {"current_worker": worker_id},
                {"$set": {"current_worker": None}}
            )
            count = result.modified_count
            logger.info(f"Released {count} cameras from worker {worker_id}")
            return count
        except Exception as e:
            logger.error(f"Failed to release cameras for {worker_id}: {e}")
            return 0