"""
Cluster Control Listener - watches MongoDB for cluster-wide start/stop commands.
Poll là nguồn sự thật; change stream chỉ giảm độ trễ.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from persistence.database import get_collection
from load_balancing.persistence.mongo_cluster_control_client import MongoClusterControlClient
import api.state as api_state
from shared.setup_log import setup_logger

logger = setup_logger("cluster_control_listener", "logs/cluster_control_listener/log")

# Poll đối soát định kỳ (nguồn sự thật)
POLL_INTERVAL_SECONDS = 5.0
# Chờ trước khi reconnect change stream
STREAM_RETRY_SECONDS = 2.0


class ClusterControlListener:
    """
    Listens to MongoDB engine_control_status collection for cluster commands.
    Applies RUN/STOP commands to local camera_manager, inference_engine, and pairing_orchestrator.
    """

    def __init__(
        self,
        worker_id: str,
        poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
        stream_retry_seconds: float = STREAM_RETRY_SECONDS,
    ):
        self.worker_id = worker_id
        self.client = MongoClusterControlClient()
        self.last_applied_token: int = -1
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._poll_interval_seconds = float(poll_interval_seconds)
        self._stream_retry_seconds = float(stream_retry_seconds)
        self._apply_lock = asyncio.Lock()

    def _token_needs_apply(self, token: int, source: str) -> bool:
        """
        Áp dụng khi token khác last_applied (kể cả token nhỏ hơn sau khi DB bị reset).
        """
        if token == self.last_applied_token:
            return False
        if token < self.last_applied_token:
            logger.warning(
                "Token went backwards via %s: token=%s < last_applied=%s; will re-apply",
                source,
                token,
                self.last_applied_token,
            )
        return True

    async def _try_apply(self, desired_state: str, token: int, source: str) -> None:
        """Apply có lock — tránh poll và stream cùng apply một token."""
        async with self._apply_lock:
            if not self._token_needs_apply(token, source):
                return
            logger.info(
                "Applying via %s: state=%s, token=%s, last_applied=%s",
                source,
                desired_state,
                token,
                self.last_applied_token,
            )
            await self._apply_command(desired_state, token)

    async def bootstrap(self) -> None:
        """Load initial state from MongoDB on startup."""
        try:
            await self.client.ensure_indexes()
            status = await self.client.get_current_status()
            if status is None:
                logger.warning(
                    "Bootstrap: Mongo status unknown (read error); skip apply"
                )
                return

            token = int(status.get("token", 0) or 0)
            desired_state = status.get("desired_state", "STOP")

            logger.info(
                "Bootstrap: current cluster state=%s, token=%s, last_applied=%s",
                desired_state,
                token,
                self.last_applied_token,
            )

            if self._token_needs_apply(token, "bootstrap"):
                await self._try_apply(desired_state, token, "bootstrap")
            else:
                logger.info("Bootstrap: no new commands to apply")

        except Exception as e:
            logger.error(f"Bootstrap error: {e}")

    async def _apply_command(self, desired_state: str, token: int) -> None:
        """Apply cluster command locally."""
        if not api_state.camera_manager or not api_state.inference_engine:
            logger.warning(
                f"Cannot apply {desired_state}: camera_manager or inference_engine not initialized"
            )
            return

        try:
            if desired_state == "RUN":
                logger.info(f"Applying RUN command (token={token})")

                api_state.camera_manager.start_all_cameras()
                api_state.inference_engine.resume()

                if api_state.pairing_orchestrator:
                    api_state.pairing_orchestrator.resume()

                logger.info(f"RUN command applied successfully (token={token})")

            elif desired_state == "STOP":
                logger.info(f"Applying STOP command (token={token})")

                api_state.camera_manager.stop_all_cameras()
                api_state.inference_engine.pause()

                if api_state.pairing_orchestrator:
                    api_state.pairing_orchestrator.pause()

                logger.info(f"STOP command applied successfully (token={token})")

            else:
                logger.warning(f"Unknown desired_state: {desired_state}")
                return

            self.last_applied_token = token

            await self.client.write_ack(
                worker_id=self.worker_id,
                token=token,
                applied_state=desired_state,
            )

        except Exception as e:
            logger.error(f"Error applying {desired_state} command (token={token}): {e}")

    async def _handle_change(self, change: Dict[str, Any]) -> None:
        """Handle a change stream event (low latency)."""
        try:
            full_doc = change.get("fullDocument")
            if not full_doc:
                return

            token = int(full_doc.get("token", 0) or 0)
            desired_state = full_doc.get("desired_state")

            if not desired_state:
                return

            if token == self.last_applied_token:
                logger.debug(
                    "Ignoring change with token=%s (already applied %s)",
                    token,
                    self.last_applied_token,
                )
                return

            await self._try_apply(desired_state, token, "change_stream")

        except Exception as e:
            logger.error(f"Error handling change: {e}")

    async def _poll_status(self) -> None:
        """Đối soát định kỳ với Mongo (nguồn sự thật)."""
        try:
            status = await self.client.get_current_status()
            if status is None:
                logger.warning(
                    "Poll: Mongo status unknown (read error); skip apply"
                )
                return

            token = int(status.get("token", 0) or 0)
            desired_state = status.get("desired_state", "STOP")
            await self._try_apply(desired_state, token, "poll")

        except Exception as e:
            logger.error(f"Poll error: {e}")

    async def _reconcile_loop(self) -> None:
        """Vòng poll luôn chạy khi listener còn sống."""
        logger.info(
            "Starting reconcile poll loop (interval=%.1fs)",
            self._poll_interval_seconds,
        )
        while self._running:
            try:
                await self._poll_status()
            except Exception as e:
                logger.error(f"Reconcile loop error: {e}", exc_info=True)
            await asyncio.sleep(self._poll_interval_seconds)

    async def _stream_loop(self) -> None:
        """
        Change stream giảm độ trễ. Kết thúc bình thường hoặc lỗi → return;
        caller sẽ reconnect. Không được làm chết cả listener.
        """
        collection_name = self.client._status_collection
        col = get_collection(collection_name)
        pipeline = [
            {
                "$match": {
                    "operationType": {"$in": ["insert", "update", "replace"]},
                    "fullDocument._id": "inference_status",
                }
            }
        ]

        logger.info("Starting change stream watch on engine_control_status")
        async with col.watch(pipeline, full_document="updateLookup") as stream:
            async for change in stream:
                if not self._running:
                    return
                await self._handle_change(change)

        if self._running:
            logger.warning("Change stream ended without exception; will reconnect")

    async def _watch_loop(self) -> None:
        """
        Supervisor: bootstrap → poll song song stream;
        stream chết thì retry vô hạn khi còn _running.
        """
        await self.bootstrap()

        poll_task = asyncio.create_task(
            self._reconcile_loop(),
            name="cluster_control_poll",
        )
        try:
            while self._running:
                try:
                    await self._stream_loop()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(
                        "Change stream unavailable (%s); poll continues, retry stream in %.1fs",
                        e,
                        self._stream_retry_seconds,
                    )
                if self._running:
                    await asyncio.sleep(self._stream_retry_seconds)
        finally:
            if not poll_task.done():
                poll_task.cancel()
                try:
                    await poll_task
                except asyncio.CancelledError:
                    pass

    async def start(self) -> None:
        """Start the listener (blocks until stop)."""
        if self._running:
            logger.warning("Listener already running")
            return

        self._running = True
        logger.info(f"Starting cluster control listener for worker {self.worker_id}")

        while self._running:
            try:
                await self._watch_loop()
                # _watch_loop chỉ return khi _running=False hoặc poll/stream cùng thoát bất thường
                if self._running:
                    logger.warning(
                        "Watch loop exited unexpectedly; restarting in %.1fs",
                        self._stream_retry_seconds,
                    )
                    await asyncio.sleep(self._stream_retry_seconds)
            except asyncio.CancelledError:
                self._running = False
                raise
            except Exception as e:
                logger.error(
                    "Cluster control supervisor error: %s; restarting in %.1fs",
                    e,
                    self._stream_retry_seconds,
                    exc_info=True,
                )
                if self._running:
                    await asyncio.sleep(self._stream_retry_seconds)

    async def stop(self) -> None:
        """Stop the listener."""
        if not self._running:
            return

        logger.info("Stopping cluster control listener")
        self._running = False
        await asyncio.sleep(0.5)
