"""
Worker Registry Service - Quản lý CRUD operations cho collection register_worker
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from api.core.database import get_collection
from utils.setup_log import setup_logger

logger = setup_logger("worker_registry_service", "logs/worker_registry_service/log")


class WorkerRegistryService:
    """Service quản lý worker registration và heartbeat"""
    
    def __init__(self, collection_name: str = "register_worker"):
        self._collection_name = collection_name
    
    async def register(self, worker_id: str, worker_ip: str) -> bool:
        """
        Đăng ký worker mới hoặc update nếu đã tồn tại.
        
        Args:
            worker_id: ID unique của worker
            worker_ip: IP address của worker
            
        Returns:
            bool: True nếu thành công
        """
        try:
            col = get_collection(self._collection_name)
            now = datetime.utcnow()
            now_vietnam = now + timedelta(hours=7)
            formatted_time =  now_vietnam.strftime("%Y-%m-%d %H:%M:%S")
            
            result = await col.update_one(
                {"worker_id": worker_id},
                {
                    "$set": {
                        "worker_ip": worker_ip,
                        "last_time": now,
                        "last_time_vietnam": formatted_time,
                    },
                    "$setOnInsert": {
                        "start_time": now,
                        "capacity": {"current_cameras": 0}
                    }
                },
                upsert=True
            )
            
            if result.upserted_id or result.modified_count > 0:
                logger.info(f"Worker registered: {worker_id} @ {worker_ip}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to register worker {worker_id}: {e}")
            return False
    
    async def update_heartbeat(
        self, 
        worker_id: str, 
        current_cameras: int
    ) -> bool:
        """
        Cập nhật heartbeat và capacity của worker.
        
        Args:
            worker_id: ID của worker
            current_cameras: Số lượng cameras hiện tại worker đang xử lý
            
        Returns:
            bool: True nếu thành công
        """
        try:
            col = get_collection(self._collection_name)
            now = datetime.utcnow()
            now_vietnam = now + timedelta(hours=7)
            formatted_time =  now_vietnam.strftime("%Y-%m-%d %H:%M:%S")
            
            result = await col.update_one(
                {"worker_id": worker_id},
                {
                    "$set": {
                        "last_time": now,
                        "last_time_vietnam": formatted_time,
                        "capacity.current_cameras": current_cameras
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.debug(f"Heartbeat updated for worker {worker_id}, cameras: {current_cameras}")
                return True
            else:
                logger.warning(f"Worker {worker_id} not found in registry")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update heartbeat for {worker_id}: {e}")
            return False
    
    async def get_active_workers(self, timeout_seconds: int = 30) -> List[Dict[str, Any]]:
        """
        Lấy danh sách workers active (có heartbeat trong timeout).
        
        Args:
            timeout_seconds: Thời gian timeout để xác định worker còn active
            
        Returns:
            List[Dict]: Danh sách workers active
        """
        try:
            col = get_collection(self._collection_name)
            cutoff_time = datetime.utcnow() - timedelta(seconds=timeout_seconds)
            
            cursor = col.find(
                {"last_time": {"$gte": cutoff_time}},
                {"_id": 0}
            ).sort("worker_id", 1)
            
            workers = await cursor.to_list(length=None)
            
            logger.debug(f"Found {len(workers)} active workers (timeout={timeout_seconds}s)")
            return workers
            
        except Exception as e:
            logger.error(f"Failed to get active workers: {e}")
            return []
    
    async def get_all_workers(self) -> List[Dict[str, Any]]:
        """
        Lấy tất cả workers (bao gồm cả inactive).
        
        Returns:
            List[Dict]: Danh sách tất cả workers
        """
        try:
            col = get_collection(self._collection_name)
            cursor = col.find({}, {"_id": 0}).sort("worker_id", 1)
            workers = await cursor.to_list(length=None)
            return workers
            
        except Exception as e:
            logger.error(f"Failed to get all workers: {e}")
            return []
    
    async def remove_worker(self, worker_id: str) -> bool:
        """
        Xóa worker khỏi registry.
        
        Args:
            worker_id: ID của worker cần xóa
            
        Returns:
            bool: True nếu xóa thành công
        """
        try:
            col = get_collection(self._collection_name)
            result = await col.delete_one({"worker_id": worker_id})
            
            if result.deleted_count > 0:
                logger.info(f"Worker {worker_id} removed from registry")
                return True
            else:
                logger.warning(f"Worker {worker_id} not found for removal")
                return False
                
        except Exception as e:
            logger.error(f"Failed to remove worker {worker_id}: {e}")
            return False
    
    async def get_worker(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """
        Lấy thông tin của một worker cụ thể.
        
        Args:
            worker_id: ID của worker
            
        Returns:
            Optional[Dict]: Thông tin worker hoặc None nếu không tìm thấy
        """
        try:
            col = get_collection(self._collection_name)
            worker = await col.find_one({"worker_id": worker_id}, {"_id": 0})
            return worker
            
        except Exception as e:
            logger.error(f"Failed to get worker {worker_id}: {e}")
            return None
