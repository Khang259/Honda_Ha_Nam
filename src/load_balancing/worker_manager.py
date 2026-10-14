"""
Worker Manager - Quản lý worker lifecycle, heartbeat và camera rebalancing
"""
#TODO: Refactor this file ensure this file has only 4 steps function
import asyncio
from typing import Awaitable, Callable, Dict, List, Set, Optional, FrozenSet, Any
from load_balancing.worker_registry_service import WorkerRegistryService
from load_balancing.camera_assignment_service import CameraAssignmentService
from shared.setup_log import setup_logger

logger = setup_logger("worker_manager", "logs/worker_manager/log")

# Số lần liên tiếp không thấy heartbeat mới coi worker chết (debounce)
DEFAULT_DEAD_MISS_THRESHOLD = 2

# Callback: (to_claim_ids, to_release_ids, my_camera_ids) after DB claim/release
AssignmentApplyCallback = Callable[
    [List[int], List[int], Set[int]],
    Awaitable[None],
]


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
        heartbeat_interval: int = 10,
        heartbeat_timeout: int = 30,
        dead_miss_threshold: int = DEFAULT_DEAD_MISS_THRESHOLD,
    ):
        self.worker_id = worker_id
        self.worker_ip = worker_ip
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.dead_miss_threshold = max(1, int(dead_miss_threshold))

        self.registry_service = WorkerRegistryService()
        self.assignment_service = CameraAssignmentService()

        self.fencing_tokens: Dict[int, int] = {}
        self.assigned_camera_ids: Set[int] = set()
        self.last_active_worker_ids: FrozenSet[str] = frozenset()
        self.last_camera_ids: FrozenSet[int] = frozenset()
        # worker_id -> số chu kỳ liên tiếp không có trong heartbeat query
        self._miss_streak: Dict[str, int] = {}
        self.running: bool = False
        self._on_assignment_applied: Optional[AssignmentApplyCallback] = None

    def set_assignment_apply_callback(self, callback: Optional[AssignmentApplyCallback]) -> None:
        """Runtime gắn callback hot-apply CameraManager sau rebalance DB."""
        self._on_assignment_applied = callback
        logger.info(
            "Assignment apply callback %s for worker_id=%s",
            "set" if callback else "cleared",
            self.worker_id,
        )

    async def initialize(self) -> None:
        """Đăng ký worker và assignment ban đầu."""
        logger.info(f"Initializing worker {self.worker_id}...")

        success = await self._register_self()
        if not success:
            raise RuntimeError(f"Failed to register worker {self.worker_id}")

        await self.detect_and_rebalance()

        self.running = True
        logger.info(f"Worker {self.worker_id} initialized successfully")

    async def _register_self(self) -> bool:
        return await self.registry_service.register(
            worker_id=self.worker_id,
            worker_ip=self.worker_ip,
        )

    def _effective_active_workers(self, heartbeat_worker_ids: List[str]) -> Set[str]:
        """
        Debounce: worker chỉ chết sau N lần liên tiếp không thấy heartbeat.
        Trong thời gian grace vẫn giữ trong tập active hiệu lực.
        """
        heartbeat_set = {str(w) for w in heartbeat_worker_ids}
        tracked = set(self._miss_streak.keys()) | heartbeat_set | set(self.last_active_worker_ids)
        tracked.add(self.worker_id)

        for wid in tracked:
            if wid in heartbeat_set:
                self._miss_streak[wid] = 0
            else:
                self._miss_streak[wid] = self._miss_streak.get(wid, 0) + 1

        effective = {
            wid
            for wid in tracked
            if self._miss_streak.get(wid, 0) < self.dead_miss_threshold
        }
        effective.add(self.worker_id)

        # Dọn streak quá cũ để không phình dict
        for wid in list(self._miss_streak.keys()):
            if (
                wid not in effective
                and wid not in heartbeat_set
                and self._miss_streak[wid] > self.dead_miss_threshold + 5
            ):
                del self._miss_streak[wid]

        return effective

    async def detect_and_rebalance(self) -> None:
        """
        Detect co-workers + camera assignment.
        Lỗi Mongo (unknown) → bỏ qua lần này, không release/claim.
        """
        active_workers = await self.registry_service.get_active_workers(
            timeout_seconds=self.heartbeat_timeout
        )
        if active_workers is None:
            logger.warning(
                "Active workers unknown (Mongo error); skipping rebalance this cycle"
            )
            return

        heartbeat_ids = [str(w["worker_id"]) for w in active_workers if w.get("worker_id")]
        effective_ids = self._effective_active_workers(heartbeat_ids)
        effective_sorted = sorted(effective_ids)

        camera_ids = await self.assignment_service.get_all_camera_ids()
        if camera_ids is None:
            logger.warning(
                "Camera ids unknown (Mongo error); skipping rebalance this cycle"
            )
            return

        current_owners = await self.assignment_service.get_current_ownership()
        if current_owners is None:
            logger.warning(
                "Camera ownership unknown (Mongo error); skipping rebalance this cycle"
            )
            return

        worker_set = frozenset(effective_sorted)
        camera_set = frozenset(int(c) for c in camera_ids)

        if (
            worker_set == self.last_active_worker_ids
            and camera_set == self.last_camera_ids
            and self.assigned_camera_ids
        ):
            logger.debug(
                "No worker/camera set change (%s workers, %s cameras); "
                "reconcile CameraManager only",
                len(worker_set),
                len(camera_set),
            )
            await self._notify_assignment_applied(
                [], [], set(self.assigned_camera_ids)
            )
            return

        logger.info(
            "Rebalancing: workers %s -> %s (heartbeat=%s), cameras %s -> %s",
            sorted(self.last_active_worker_ids),
            effective_sorted,
            sorted(heartbeat_ids),
            len(self.last_camera_ids),
            len(camera_set),
        )

        if not camera_ids:
            logger.warning("No cameras found in database")
            self.last_active_worker_ids = worker_set
            self.last_camera_ids = camera_set
            self.assigned_camera_ids = set()
            await self._notify_assignment_applied([], [], set())
            return

        assignment = self.assignment_service.calculate_assignment_for_camera_ids(
            camera_ids=camera_ids,
            active_workers=effective_sorted,
            current_owners=current_owners,
        )

        my_camera_ids = set(assignment.get(self.worker_id, []))

        to_claim = my_camera_ids - self.assigned_camera_ids
        to_release = self.assigned_camera_ids - my_camera_ids

        if to_release:
            logger.info(f"Releasing {len(to_release)} cameras: {sorted(to_release)}")
            for camera_id in to_release:
                # Chỉ clear DB nếu vẫn là chủ — tránh đụng ownership worker mới (fencing)
                owner = current_owners.get(int(camera_id))
                if owner is None or str(owner) == self.worker_id:
                    await self.assignment_service.release_camera(camera_id)
                self.fencing_tokens.pop(camera_id, None)

        if to_claim:
            logger.info(f"Claiming {len(to_claim)} cameras: {sorted(to_claim)}")
            claimed_tokens = await self._claim_cameras(list(to_claim))
            self.fencing_tokens.update(claimed_tokens)

        self.assigned_camera_ids = my_camera_ids
        self.last_active_worker_ids = worker_set
        self.last_camera_ids = camera_set

        await self._notify_assignment_applied(
            sorted(to_claim), sorted(to_release), set(my_camera_ids)
        )

        logger.info(
            f"Rebalance completed: {len(self.assigned_camera_ids)} cameras assigned "
            f"to worker {self.worker_id}"
        )

    async def _notify_assignment_applied(
        self,
        to_claim: List[int],
        to_release: List[int],
        my_camera_ids: Set[int],
    ) -> None:
        """Luôn gọi callback để CameraManager đối soát managed vs assigned."""
        if not self._on_assignment_applied:
            return
        try:
            await self._on_assignment_applied(
                list(to_claim),
                list(to_release),
                set(my_camera_ids),
            )
        except Exception as e:
            logger.error(
                "Assignment apply callback failed: %s", e, exc_info=True
            )

    async def _claim_cameras(self, camera_ids: List[int]) -> Dict[int, int]:
        tokens = {}
        for camera_id in camera_ids:
            success, new_token = await self.assignment_service.claim_camera(
                camera_id=camera_id,
                worker_id=self.worker_id,
            )
            if success:
                tokens[camera_id] = new_token
                logger.debug(f"Claimed camera {camera_id}, token={new_token}")
            else:
                logger.error(f"Failed to claim camera {camera_id}")
        return tokens

    async def _validate_current_cameras(self) -> List[int]:
        """
        Validate fencing tokens. Lỗi Mongo (None) → bỏ qua, không discard ownership.
        """
        invalid_cameras = []

        for camera_id, current_token in list(self.fencing_tokens.items()):
            is_valid = await self.assignment_service.validate_token(
                camera_id=camera_id,
                current_token=current_token,
            )

            if is_valid is None:
                logger.warning(
                    "Token validation unknown for camera %s; keeping ownership",
                    camera_id,
                )
                continue

            if not is_valid:
                logger.warning(
                    f"Camera {camera_id} token mismatch, "
                    f"no longer owned by worker {self.worker_id}"
                )
                invalid_cameras.append(camera_id)
                # Giữ assigned đến rebalance → to_release có camera → remove_camera chạy
                self.fencing_tokens.pop(camera_id, None)

        return invalid_cameras

    async def start_heartbeat_loop(self) -> None:
        logger.info(f"Starting heartbeat loop (interval={self.heartbeat_interval}s)")

        while self.running:
            try:
                await self.registry_service.update_heartbeat(
                    worker_id=self.worker_id,
                    current_cameras=len(self.assigned_camera_ids),
                )

                invalid_cameras = await self._validate_current_cameras()
                if invalid_cameras:
                    logger.warning(
                        f"Found {len(invalid_cameras)} invalid tokens, "
                        f"triggering rebalance"
                    )
                    # Force rebalance: clear last sets so next detect không skip
                    self.last_active_worker_ids = frozenset()

                await self.detect_and_rebalance()

            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}", exc_info=True)

            await asyncio.sleep(self.heartbeat_interval)

    async def shutdown(self) -> None:
        logger.info(f"Shutting down worker {self.worker_id}...")

        self.running = False

        if self.assigned_camera_ids:
            logger.info(
                f"Releasing {len(self.assigned_camera_ids)} cameras "
                f"on shutdown"
            )
            released = await self.assignment_service.release_cameras(
                worker_id=self.worker_id
            )
            logger.info(f"Released {released} cameras")

        await self.registry_service.remove_worker(self.worker_id)

        logger.info(f"Worker {self.worker_id} shutdown completed")

    def get_assigned_cameras(self) -> List[int]:
        return sorted(list(self.assigned_camera_ids))

    def get_fencing_token(self, camera_id: int) -> Optional[int]:
        return self.fencing_tokens.get(camera_id)

    async def get_assigned_camera_configs(self) -> List[Dict]:
        return await self.assignment_service.get_assigned_cameras(self.worker_id)
