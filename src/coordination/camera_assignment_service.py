"""
Camera Assignment Service - Quản lý phân bổ cameras cho workers với fencing token
"""

from typing import List, Dict, Tuple, Any, Optional
from datetime import datetime, timedelta
from persistence.database import get_collection
from shared.setup_log import setup_logger

logger = setup_logger("camera_assignment_service", "logs/camera_assignment_service/log")


class CameraAssignmentService:
    """Service quản lý camera assignment với fencing token để tránh tranh chấp"""
    
    def __init__(self, collection_name: str = "node_id"):
        self._collection_name = collection_name

    @staticmethod
    def calculate_assignment_for_camera_ids(
        camera_ids: List[int],
        active_workers: List[str],
    ) -> Dict[str, List[int]]:
        """
        Chia đều theo danh sách cameraId thực tế (đã sort).

        - Không giả định cameraId liên tục.
        - Nếu chia dư, workers đầu (theo sort worker_id) nhận thêm 1 camera.
        """
        if not active_workers:
            logger.warning("No active workers to assign cameras")
            return {}

        camera_ids_sorted = sorted([int(x) for x in camera_ids])
        worker_ids_sorted = sorted(active_workers)

        num_workers = len(worker_ids_sorted)
        total_cameras = len(camera_ids_sorted)

        base_count = total_cameras // num_workers
        remainder = total_cameras % num_workers

        assignment: Dict[str, List[int]] = {}
        offset = 0

        for i, worker_id in enumerate(worker_ids_sorted):
            count = base_count + (1 if i < remainder else 0)
            assignment[worker_id] = camera_ids_sorted[offset : offset + count]
            offset += count

        logger.info(
            f"Calculated assignment: {num_workers} workers, "
            f"{total_cameras} cameras, distribution: {[len(v) for v in assignment.values()]}"
        )

        return assignment
    
    def calculate_assignment(
        self, 
        total_cameras: int, 
        active_workers: List[str]
    ) -> Dict[str, List[int]]:
        """
        Tính toán phân bổ cameras đều cho các workers.
        Nếu phép chia có dư, phân phối dư cho các workers đầu tiên.
        
        Args:
            total_cameras: Tổng số cameras cần phân bổ
            active_workers: Danh sách worker_ids active
            
        Returns:
            Dict[str, List[int]]: Mapping worker_id -> list camera_ids
            
        Example:
            100 cameras, 4 workers -> mỗi worker 25 cameras
            100 cameras, 3 workers -> 34, 33, 33 cameras
        """
        # Backward-compatible: vẫn giữ hành vi cũ theo range(0..N-1)
        # (không dùng cho production nếu cameraId không liên tục).
        return self.calculate_assignment_for_camera_ids(
            camera_ids=list(range(int(total_cameras))),
            active_workers=active_workers,
        )

    async def get_all_camera_ids(self) -> List[int]:
        """Lấy danh sách cameraId thực tế từ collection (sorted)."""
        try:
            col = get_collection(self._collection_name)
            cursor = col.find({}, {"cameraId": 1, "_id": 0}).sort("cameraId", 1)
            docs = await cursor.to_list(length=None)
            camera_ids: List[int] = []
            for d in docs:
                if isinstance(d, dict) and "cameraId" in d:
                    try:
                        camera_ids.append(int(d["cameraId"]))
                    except Exception:
                        continue
            return camera_ids
        except Exception as e:
            logger.error(f"Failed to fetch camera ids: {e}")
            return []
    
    async def claim_camera(
        self, 
        camera_id: int, 
        worker_id: str
    ) -> Tuple[bool, int]:
        """
        Claim một camera với atomic fencing token increment.
        
        Args:
            camera_id: ID của camera cần claim
            worker_id: ID của worker claim camera
            
        Returns:
            Tuple[bool, int]: (success, new_fencing_token)
        """
        try:
            col = get_collection(self._collection_name)
            now = datetime.utcnow()
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
                    f"Camera {camera_id} claimed by worker {worker_id}, "
                    f"fencing_token={new_token}"
                )
                return True, new_token
            else:
                logger.warning(f"Camera {camera_id} not found for claim")
                return False, 0
                
        except Exception as e:
            logger.error(f"Failed to claim camera {camera_id}: {e}")
            return False, 0
    
    async def release_camera(self, camera_id: int) -> bool:
        """
        Release một camera (set current_worker = None).
        
        Args:
            camera_id: ID của camera cần release
            
        Returns:
            bool: True nếu thành công
        """
        try:
            col = get_collection(self._collection_name)
            
            result = await col.update_one(
                {"cameraId": camera_id},
                {
                    "$set": {
                        "current_worker": None
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.debug(f"Camera {camera_id} released")
                return True
            else:
                logger.warning(f"Camera {camera_id} not found for release")
                return False
                
        except Exception as e:
            logger.error(f"Failed to release camera {camera_id}: {e}")
            return False
    
    async def release_cameras(self, worker_id: str) -> int:
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
                {
                    "$set": {
                        "current_worker": None
                    }
                }
            )
            
            count = result.modified_count
            logger.info(f"Released {count} cameras from worker {worker_id}")
            return count
            
        except Exception as e:
            logger.error(f"Failed to release cameras for worker {worker_id}: {e}")
            return 0
    
    async def get_assigned_cameras(self, worker_id: str) -> List[Dict[str, Any]]:
        """
        Lấy danh sách cameras được assign cho một worker.
        
        Args:
            worker_id: ID của worker
            
        Returns:
            List[Dict]: Danh sách camera configs
        """
        try:
            col = get_collection(self._collection_name)
            
            cursor = col.find(
                {"current_worker": worker_id},
                {"_id": 0}
            ).sort("cameraId", 1)
            
            cameras = await cursor.to_list(length=None)
            
            logger.debug(f"Found {len(cameras)} cameras assigned to worker {worker_id}")
            return cameras
            
        except Exception as e:
            logger.error(f"Failed to get assigned cameras for {worker_id}: {e}")
            return []
    
    async def validate_token(
        self, 
        camera_id: int, 
        current_token: int
    ) -> bool:
        """
        Validate xem fencing token của worker có khớp với DB không.
        
        Args:
            camera_id: ID của camera
            current_token: Token hiện tại worker đang giữ
            
        Returns:
            bool: True nếu token khớp (worker vẫn own camera)
        """
        try:
            col = get_collection(self._collection_name)
            
            camera = await col.find_one(
                {"cameraId": camera_id},
                {"fencing_token": 1}
            )
            
            if not camera:
                logger.warning(f"Camera {camera_id} not found for token validation")
                return False
            
            db_token = camera.get("fencing_token", 0)
            is_valid = (current_token == db_token)
            
            if not is_valid:
                logger.warning(
                    f"Token mismatch for camera {camera_id}: "
                    f"current={current_token}, db={db_token}"
                )
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Failed to validate token for camera {camera_id}: {e}")
            return False
    
    async def get_all_cameras_count(self) -> int:
        """
        Đếm tổng số cameras trong collection.
        
        Returns:
            int: Tổng số cameras
        """
        try:
            col = get_collection(self._collection_name)
            count = await col.count_documents({})
            return count
            
        except Exception as e:
            logger.error(f"Failed to count cameras: {e}")
            return 0
    
    async def get_unassigned_cameras(self) -> List[Dict[str, Any]]:
        """
        Lấy danh sách cameras chưa được assign worker nào.
        
        Returns:
            List[Dict]: Danh sách cameras chưa assign
        """
        try:
            col = get_collection(self._collection_name)
            
            cursor = col.find(
                {
                    "$or": [
                        {"current_worker": None},
                        {"current_worker": {"$exists": False}}
                    ]
                },
                {"_id": 0}
            ).sort("cameraId", 1)
            
            cameras = await cursor.to_list(length=None)
            
            logger.debug(f"Found {len(cameras)} unassigned cameras")
            return cameras
            
        except Exception as e:
            logger.error(f"Failed to get unassigned cameras: {e}")
            return []
