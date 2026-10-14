"""
Camera Assignment Service - Quản lý phân bổ cameras cho workers với fencing token
"""

from typing import List, Dict, Tuple, Any, Optional
from datetime import datetime
from persistence.database import get_collection
from shared.setup_log import setup_logger

logger = setup_logger("camera_assignment_service", "logs/camera_assignment_service/log")


class CameraAssignmentService:
    """Service quản lý camera assignment với fencing token để tránh tranh chấp"""
    
    def __init__(self, collection_name: str = "node_id"):
        self._collection_name = collection_name

    @staticmethod
    def calculate_minimize_move_assignment(
        camera_ids: List[int],
        active_workers: List[str],
        current_owners: Optional[Dict[int, Optional[str]]] = None,
    ) -> Dict[str, List[int]]:
        """
        Chia camera với mục tiêu minimize move:
        - Giữ camera đang thuộc worker còn active.
        - Camera mồ côi (None / worker chết) → gán cho máy ít tải nhất.
        - Nếu lệch tải (máy mới join): lấy bớt từ máy tải cao nhất.

        Args:
            camera_ids: danh sách cameraId
            active_workers: worker còn sống
            current_owners: cameraId -> current_worker (None nếu chưa gán)
        """
        if not active_workers:
            logger.warning("No active workers to assign cameras")
            return {}

        camera_ids_sorted = sorted(int(x) for x in camera_ids)
        worker_ids_sorted = sorted(str(w) for w in active_workers)
        active_set = set(worker_ids_sorted)
        owners = current_owners or {}

        assignment: Dict[str, List[int]] = {w: [] for w in worker_ids_sorted}
        orphans: List[int] = []

        for cam_id in camera_ids_sorted:
            owner = owners.get(cam_id)
            if owner is not None:
                owner = str(owner)
            if owner in active_set:
                assignment[owner].append(cam_id)
            else:
                orphans.append(cam_id)

        # Phase 2: orphans → least loaded (tie-break worker_id)
        for cam_id in orphans:
            target = min(worker_ids_sorted, key=lambda w: (len(assignment[w]), w))
            assignment[target].append(cam_id)

        # Phase 3: rebalance by stealing from most loaded until max-min <= 1
        # Deterministic: move highest cameraId from richest worker.
        guard = 0
        max_guard = max(len(camera_ids_sorted) * 2, 1)
        while guard < max_guard:
            guard += 1
            richest = max(worker_ids_sorted, key=lambda w: (len(assignment[w]), w))
            poorest = min(worker_ids_sorted, key=lambda w: (len(assignment[w]), w))
            if len(assignment[richest]) - len(assignment[poorest]) <= 1:
                break
            if not assignment[richest]:
                break
            cam_id = max(assignment[richest])
            assignment[richest].remove(cam_id)
            assignment[poorest].append(cam_id)

        for w in worker_ids_sorted:
            assignment[w] = sorted(assignment[w])

        logger.info(
            "Minimize-move assignment: %s workers, %s cameras, "
            "orphans_initial=%s, distribution=%s",
            len(worker_ids_sorted),
            len(camera_ids_sorted),
            len(orphans),
            [len(assignment[w]) for w in worker_ids_sorted],
        )
        return assignment

    @staticmethod
    def calculate_contiguous_assignment_for_camera_ids(
        camera_ids: List[int],
        active_workers: List[str],
    ) -> Dict[str, List[int]]:
        """
        Thuật toán cũ: cắt khối liên tiếp (để so sánh / rollback nếu cần).
        Không dùng cho production rebalance.
        """
        if not active_workers:
            return {}

        camera_ids_sorted = sorted(int(x) for x in camera_ids)
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
        return assignment

    @staticmethod
    def calculate_assignment_for_camera_ids(
        camera_ids: List[int],
        active_workers: List[str],
        current_owners: Optional[Dict[int, Optional[str]]] = None,
    ) -> Dict[str, List[int]]:
        """
        Production: minimize-move assignment.
        current_owners=None → mọi camera coi như mồ côi (chia đều lần đầu).
        """
        return CameraAssignmentService.calculate_minimize_move_assignment(
            camera_ids=camera_ids,
            active_workers=active_workers,
            current_owners=current_owners,
        )

    def calculate_assignment(
        self,
        total_cameras: int,
        active_workers: List[str],
        current_owners: Optional[Dict[int, Optional[str]]] = None,
    ) -> Dict[str, List[int]]:
        """
        Tính phân bổ cho range(0..N-1). Production nên dùng cameraId thật + owners.
        """
        return self.calculate_assignment_for_camera_ids(
            camera_ids=list(range(int(total_cameras))),
            active_workers=active_workers,
            current_owners=current_owners,
        )

    async def get_all_camera_ids(self) -> Optional[List[int]]:
        """
        Lấy danh sách cameraId thực tế từ collection (sorted).
        None = lỗi Mongo (unknown); [] = thành công nhưng không có camera.
        """
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
            logger.error(f"Failed to fetch camera ids (unknown): {e}")
            return None

    async def get_current_ownership(self) -> Optional[Dict[int, Optional[str]]]:
        """
        Lấy map cameraId -> current_worker từ DB.
        None = lỗi Mongo (unknown) — không được coi như mọi camera mồ côi.
        """
        try:
            col = get_collection(self._collection_name)
            cursor = col.find({}, {"cameraId": 1, "current_worker": 1, "_id": 0})
            docs = await cursor.to_list(length=None)
            ownership: Dict[int, Optional[str]] = {}
            for d in docs:
                if not isinstance(d, dict) or "cameraId" not in d:
                    continue
                try:
                    cam_id = int(d["cameraId"])
                except Exception:
                    continue
                owner = d.get("current_worker")
                ownership[cam_id] = str(owner) if owner is not None else None
            return ownership
        except Exception as e:
            logger.error(f"Failed to fetch camera ownership (unknown): {e}")
            return None
    
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
        current_token: int,
    ) -> Optional[bool]:
        """
        Validate fencing token.

        Returns:
            True: khớp; False: lệch / không tìm thấy camera;
            None: lỗi Mongo (unknown) — không được coi như mất quyền sở hữu.
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
            is_valid = current_token == db_token

            if not is_valid:
                logger.warning(
                    f"Token mismatch for camera {camera_id}: "
                    f"current={current_token}, db={db_token}"
                )

            return is_valid

        except Exception as e:
            logger.error(
                f"Failed to validate token for camera {camera_id} (unknown): {e}"
            )
            return None
    
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
