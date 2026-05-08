"""
Worker Manager - Quản lý worker lifecycle, heartbeat và camera rebalancing
"""
#TODO: Refactor this file ensure this file has only 4 steps function
import asyncio
from typing import Dict, List, Set, Optional
from datetime import datetime
from api.services.worker_registry_service import WorkerRegistryService
from api.services.camera_assignment_service import CameraAssignmentService
from utils.setup_log import setup_logger

logger = setup_logger("worker_manager", "logs/worker_manager/log")


class WorkerManager:
    """
    Quản lý worker lifecycle với các bước:
    1. Worker Registration
    2. Detect Co-workers
    3. Camera Assignment
    4. Heartbeat Loop
    """
    
    def __init__(
        self,
        worker_id: str,
        worker_ip: str,
        heartbeat_interval: int = 10, #Thời gian định kỳ register và update heartbeat
        heartbeat_timeout: int = 30 #Thời gian timeout để detect worker die
    ):
        self.worker_id = worker_id
        self.worker_ip = worker_ip
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        
        # Services
        self.registry_service = WorkerRegistryService()
        self.assignment_service = CameraAssignmentService()
        
        # Worker state
        self.fencing_tokens: Dict[int, int] = {}  # camera_id -> current_token (in RAM)
        self.assigned_camera_ids: Set[int] = set()
        self.last_worker_count: int = 0
        self.running: bool = False
        
        logger.info(
            f"WorkerManager initialized: worker_id={worker_id}, "
            f"heartbeat_interval={heartbeat_interval}s, timeout={heartbeat_timeout}s"
        )
    
    async def initialize(self) -> None:
        """
        Bước: Worker Registration
        Đăng ký worker vào registry và thực hiện assignment ban đầu.
        """
        logger.info(f"Initializing worker {self.worker_id}...")
        
        # Register worker
        success = await self._register_self()
        if not success:
            raise RuntimeError(f"Failed to register worker {self.worker_id}")
        
        # Detect co-workers và assign cameras
        await self.detect_and_rebalance()
        
        self.running = True
        logger.info(f"Worker {self.worker_id} initialized successfully")
    
    async def _register_self(self) -> bool:
        """Đăng ký worker vào registry."""
        return await self.registry_service.register(
            worker_id=self.worker_id,
            worker_ip=self.worker_ip
        )
    
    async def detect_and_rebalance(self) -> None:
        """
        Bước 2: Detect Co-workers
        Bước 3: Camera Assignment
        
        Phát hiện workers active và rebalance cameras nếu cần.
        """
        # Get active workers
        active_workers = await self.registry_service.get_active_workers(
            timeout_seconds=self.heartbeat_timeout
        )
        
        active_worker_ids = [w["worker_id"] for w in active_workers]
        current_worker_count = len(active_worker_ids)
        
        # Check if rebalance needed
        if current_worker_count == self.last_worker_count and self.assigned_camera_ids:
            logger.debug(
                f"No worker count change ({current_worker_count} workers), "
                f"skipping rebalance"
            )
            return
        
        logger.info(
            f"Worker count changed: {self.last_worker_count} -> {current_worker_count}, "
            f"rebalancing cameras..."
        )
        
        camera_ids = await self.assignment_service.get_all_camera_ids()
        if not camera_ids:
            logger.warning("No cameras found in database")
            return
        
        # Calculate assignment
        assignment = self.assignment_service.calculate_assignment_for_camera_ids(
            camera_ids=camera_ids, #Danh sách camera_id từ database
            active_workers=active_worker_ids,
        )
        
        my_camera_ids = set(assignment.get(self.worker_id, []))
        
        # Determine which cameras to claim and release
        to_claim = my_camera_ids - self.assigned_camera_ids
        to_release = self.assigned_camera_ids - my_camera_ids
        
        # Release cameras no longer assigned to us
        if to_release:
            logger.info(f"Releasing {len(to_release)} cameras: {sorted(to_release)}")
            for camera_id in to_release:
                await self.assignment_service.release_camera(camera_id)
                self.fencing_tokens.pop(camera_id, None)
        
        # Claim new cameras
        if to_claim:
            logger.info(f"Claiming {len(to_claim)} cameras: {sorted(to_claim)}")
            claimed_tokens = await self._claim_cameras(list(to_claim))
            self.fencing_tokens.update(claimed_tokens)
        
        # Update internal state
        self.assigned_camera_ids = my_camera_ids
        self.last_worker_count = current_worker_count
        
        logger.info(
            f"Rebalance completed: {len(self.assigned_camera_ids)} cameras assigned "
            f"to worker {self.worker_id}"
        )
    
    async def _claim_cameras(self, camera_ids: List[int]) -> Dict[int, int]:
        """
        Claim danh sách cameras và lưu fencing tokens.
        
        Returns:
            Dict[int, int]: camera_id -> fencing_token
        """
        tokens = {}
        
        for camera_id in camera_ids:
            success, new_token = await self.assignment_service.claim_camera(
                camera_id=camera_id,
                worker_id=self.worker_id
            )
            
            if success:
                tokens[camera_id] = new_token
                logger.debug(f"Claimed camera {camera_id}, token={new_token}")
            else:
                logger.error(f"Failed to claim camera {camera_id}")
        
        return tokens
    
    async def _validate_current_cameras(self) -> List[int]:
        """
        Validate fencing tokens cho cameras hiện tại.
        Trả về list camera_ids có token không khớp (không còn own).
        """
        invalid_cameras = []
        
        for camera_id, current_token in list(self.fencing_tokens.items()):
            is_valid = await self.assignment_service.validate_token(
                camera_id=camera_id,
                current_token=current_token
            )
            
            if not is_valid:
                logger.warning(
                    f"Camera {camera_id} token mismatch, "
                    f"no longer owned by worker {self.worker_id}"
                )
                invalid_cameras.append(camera_id)
                self.fencing_tokens.pop(camera_id, None)
                self.assigned_camera_ids.discard(camera_id)
        
        return invalid_cameras
    
    async def start_heartbeat_loop(self) -> None:
        """
        Bước 4: Heartbeat Loop
        
        Gửi heartbeat định kỳ và thực hiện rebalance nếu có thay đổi.
        """
        logger.info(f"Starting heartbeat loop (interval={self.heartbeat_interval}s)")
        
        while self.running:
            try:
                # Update time heartbeat
                await self.registry_service.update_heartbeat(
                    worker_id=self.worker_id,
                    current_cameras=len(self.assigned_camera_ids)
                )
                
                # Validate tokens
                invalid_cameras = await self._validate_current_cameras()
                if invalid_cameras:
                    logger.warning(
                        f"Found {len(invalid_cameras)} invalid tokens, "
                        f"triggering rebalance"
                    )
                
                # Detect and rebalance if needed
                await self.detect_and_rebalance()
                
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}", exc_info=True)
            
            # Wait for next heartbeat
            await asyncio.sleep(self.heartbeat_interval)
    
    async def shutdown(self) -> None:
        """Graceful shutdown: release cameras và remove worker khỏi registry."""
        logger.info(f"Shutting down worker {self.worker_id}...")
        
        self.running = False
        
        # Release all cameras
        if self.assigned_camera_ids:
            logger.info(
                f"Releasing {len(self.assigned_camera_ids)} cameras "
                f"on shutdown"
            )
            released = await self.assignment_service.release_cameras(
                worker_id=self.worker_id
            )
            logger.info(f"Released {released} cameras")
        
        # Remove worker from registry
        await self.registry_service.remove_worker(self.worker_id)
        
        logger.info(f"Worker {self.worker_id} shutdown completed")
    
    def get_assigned_cameras(self) -> List[int]:
        """Lấy danh sách camera IDs được assign."""
        return sorted(list(self.assigned_camera_ids))
    
    def get_fencing_token(self, camera_id: int) -> Optional[int]:
        """Lấy fencing token cho một camera."""
        return self.fencing_tokens.get(camera_id)
    
    async def get_assigned_camera_configs(self) -> List[Dict]:
        """Lấy danh sách camera configs từ database."""
        return await self.assignment_service.get_assigned_cameras(self.worker_id)
