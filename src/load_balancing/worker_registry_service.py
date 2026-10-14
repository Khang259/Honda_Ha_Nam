"""
Worker Registry Service - Quản lý CRUD operations cho collection register_worker
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from persistence.database import get_collection
from shared.setup_log import setup_logger

logger = setup_logger("worker_registry_service", "logs/worker_registry_service/log")


class WorkerRegistryService:
    """Service quản lý worker registration và heartbeat"""

    def __init__(self, collection_name: str = "register_worker"):
        self._collection_name = collection_name

    @staticmethod
    def _vietnam_display_now() -> str:
        """Chỉ để hiển thị; authoritative clock là last_time = $$NOW trên Mongo."""
        now = datetime.utcnow() + timedelta(hours=7)
        return now.strftime("%Y-%m-%d %H:%M:%S")

    async def register(self, worker_id: str, worker_ip: str) -> bool:
        """
        Đăng ký worker mới hoặc update nếu đã tồn tại.
        last_time dùng $$NOW (giờ server Mongo) — cần MongoDB >= 4.2.
        """
        try:
            col = get_collection(self._collection_name)
            formatted_time = self._vietnam_display_now()

            result = await col.update_one(
                {"worker_id": worker_id},
                [
                    {
                        "$set": {
                            "worker_id": {"$ifNull": ["$worker_id", worker_id]},
                            "worker_ip": worker_ip,
                            "last_time": "$$NOW",
                            "last_time_vietnam": formatted_time,
                            "start_time": {"$ifNull": ["$start_time", "$$NOW"]},
                            "capacity": {
                                "$ifNull": ["$capacity", {"current_cameras": 0}]
                            },
                        }
                    }
                ],
                upsert=True,
            )
            if result.upserted_id is not None or result.modified_count > 0 or result.matched_count > 0:
                logger.info(f"Worker registered: {worker_id} @ {worker_ip}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to register worker {worker_id}: {e}")
            return False

    async def update_heartbeat(
        self,
        worker_id: str,
        current_cameras: int,
    ) -> bool:
        """Cập nhật heartbeat bằng $$NOW (giờ server Mongo)."""
        try:
            col = get_collection(self._collection_name)
            formatted_time = self._vietnam_display_now()

            result = await col.update_one(
                {"worker_id": worker_id},
                [
                    {
                        "$set": {
                            "last_time": "$$NOW",
                            "last_time_vietnam": formatted_time,
                            "capacity.current_cameras": int(current_cameras),
                        }
                    }
                ],
            )

            if result.modified_count > 0 or result.matched_count > 0:
                logger.debug(
                    f"Heartbeat updated for worker {worker_id}, cameras: {current_cameras}"
                )
                return True

            logger.warning(f"Worker {worker_id} not found in registry")
            return False

        except Exception as e:
            logger.error(f"Failed to update heartbeat for {worker_id}: {e}")
            return False

    async def get_active_workers(
        self, timeout_seconds: int = 30
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Workers active theo cutoff = $$NOW - timeout (giờ server).

        Returns:
            List[Dict] nếu OK; None nếu lỗi Mongo (unknown).
        """
        try:
            col = get_collection(self._collection_name)
            timeout_ms = int(timeout_seconds) * 1000

            cursor = col.find(
                {
                    "$expr": {
                        "$gte": [
                            "$last_time",
                            {"$subtract": ["$$NOW", timeout_ms]},
                        ]
                    }
                },
                {"_id": 0},
            ).sort("worker_id", 1)

            workers = await cursor.to_list(length=None)

            logger.debug(
                f"Found {len(workers)} active workers (timeout={timeout_seconds}s, server $$NOW)"
            )
            return workers

        except Exception as e:
            logger.error(f"Failed to get active workers (unknown): {e}")
            return None

    async def remove_worker(self, worker_id: str) -> bool:
        try:
            col = get_collection(self._collection_name)
            result = await col.delete_one({"worker_id": worker_id})

            if result.deleted_count > 0:
                logger.info(f"Worker {worker_id} removed from registry")
                return True

            logger.warning(f"Worker {worker_id} not found for removal")
            return False

        except Exception as e:
            logger.error(f"Failed to remove worker {worker_id}: {e}")
            return False
