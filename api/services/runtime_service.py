from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from config import (
    ICS_URL,
    ENABLE_SNAPSHOTS,
    SNAPSHOT_DIR,
    SNAPSHOT_QUALITY,
    INFERENCE_MAX_QUEUE_SIZE,
    INFERENCE_MAX_BATCH_SIZE,
    INFERENCE_BATCH_TIMEOUT,
    INFERENCE_NUM_STREAMS,
    MODEL_PATH,
)
from core.state_manager import StateManager
from core.snapshot_manager import SnapshotManager
from core.camera_manager import CameraManager
from core.inference_engine import InferenceEngine
from core.worker_manager import WorkerManager
import config as _ai_config
import api.state as api_state
from api.services.validate_pairs_service import ValidatePairsService
from api.services.start_event_pairing_service import StartEventPairingOrchestrator
from api.clients.mongo_node_id_client import MongoNodeIdClient
from api.settings import settings


@dataclass
#TODO: check this still available?
class RuntimeStatus:
    running: bool
    config_source: Optional[str]
    config_fetched_at: Optional[float]
    cameras_total: int
    cameras_enabled: int
    cameras_alive: int
    inference_paused: Optional[bool]
    started_at: Optional[float]


class RuntimeService:
    def __init__(self):
        self._components: Dict[str, Any] = {}
        self._running: bool = False
        self._started_at: Optional[float] = None
        self._config_meta: Dict[str, Any] = {}
        self._worker_manager: Optional[WorkerManager] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._pairing_orchestrator: Optional[StartEventPairingOrchestrator] = None

    async def start(self) -> RuntimeStatus:
        if self._running:
            return None #self.status()

        # Initialize WorkerManager
        self._worker_manager = WorkerManager(
            worker_id=settings.WORKER_ID,
            worker_ip=settings.WORKER_IP,
            heartbeat_interval=settings.HEARTBEAT_INTERVAL,
            heartbeat_timeout=settings.HEARTBEAT_TIMEOUT
        )
        await self._worker_manager.initialize()
        
        # Start heartbeat loop in background
        self._heartbeat_task = asyncio.create_task(
            self._worker_manager.start_heartbeat_loop()
        )
        
        # Get assigned cameras for this worker
        cameras = await self._worker_manager.get_assigned_camera_configs()

        docs = await MongoNodeIdClient().get_empty_car_points()
        end_point_empty = docs[0].get("end_points")
        api_state.set_end_point_empty(end_point_empty)

        # Keep config.CAMERAS in sync for scripts/tests that read the global list.
        _ai_config.CAMERAS = list(cameras)

        # Load validate pairs from MongoDB
        validate_pairs = await ValidatePairsService().get_validate_pairs_all()
        state_manager = StateManager(validate_pairs)

        snapshot_manager = None
        if ENABLE_SNAPSHOTS:
            snapshot_manager = SnapshotManager(
                snapshot_dir=SNAPSHOT_DIR,
                quality=SNAPSHOT_QUALITY,
            )

        inference_engine = InferenceEngine(
            model_path=MODEL_PATH,
            max_queue_size=INFERENCE_MAX_QUEUE_SIZE,
            max_batch_size=INFERENCE_MAX_BATCH_SIZE,
            batch_timeout=INFERENCE_BATCH_TIMEOUT,
            num_streams=INFERENCE_NUM_STREAMS,
            initial_paused=True,
        )
        inference_engine.start()

        camera_zones = [c.get("area_name", c.get("zone")) for c in cameras]
        camera_manager = CameraManager(
            cameras,
            state_manager,
            inference_engine,
            snapshot_manager=snapshot_manager,
            camera_zones=camera_zones,
        )
        camera_manager.start()

        self._pairing_orchestrator = StartEventPairingOrchestrator(
            worker_id=settings.WORKER_ID,
            state_manager=state_manager,
            validate_pairs=validate_pairs,
            ics_url=ICS_URL,
            snapshot_manager=snapshot_manager,
        )
        await self._pairing_orchestrator.start()

        api_state.set_state_manager(state_manager)
        api_state.set_camera_manager(camera_manager)
        api_state.set_inference_engine(inference_engine)

        self._components = {
            "state_manager": state_manager,
            "pairing_orchestrator": self._pairing_orchestrator,
            "snapshot_manager": snapshot_manager,
            "inference_engine": inference_engine,
            "camera_manager": camera_manager,
            "worker_manager": self._worker_manager,
        }
        self._running = True
        self._started_at = time.time()
        self._config_meta = {
            "cameras_count": len(cameras),
            "worker_id": settings.WORKER_ID,
        }
        return self.status()

    async def stop(self) -> RuntimeStatus:
        if not self._running:
            return self.status()

        self._running = False

        if self._pairing_orchestrator:
            try:
                await self._pairing_orchestrator.stop()
            except Exception:
                pass
            self._pairing_orchestrator = None
        
        # Stop heartbeat task
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        
        # Shutdown worker manager
        if self._worker_manager:
            try:
                await self._worker_manager.shutdown()
            except Exception as e:
                print(f"Error shutting down worker manager: {e}")

        camera_manager = self._components.get("camera_manager")
        if camera_manager:
            try:
                camera_manager.stop()
            except Exception:
                pass

        inference_engine = self._components.get("inference_engine")
        if inference_engine:
            try:
                inference_engine.stop()
            except Exception:
                pass

        self._components = {}
        self._worker_manager = None
        self._heartbeat_task = None
        api_state.set_state_manager(None)
        api_state.set_camera_manager(None)
        api_state.set_inference_engine(None)

        return self.status()

    async def reload(self, area: str) -> Dict[str, Any]:
        prev = self.status()
        await self.stop()
        current = await self.start()
        return {"success": True, "previous": prev, "current": current}

    def status(self) -> Dict[str, Any]:
        camera_manager = self._components.get("camera_manager")
        inference_engine = self._components.get("inference_engine")

        cameras_total = 0
        cameras_enabled = 0
        cameras_alive = 0
        if camera_manager:
            try:
                st = camera_manager.get_status()
                cameras_total = int(st.get("total", 0))
                cameras_enabled = int(st.get("enabled", 0))
                cameras_alive = int(st.get("alive", 0))
            except Exception:
                pass

        inference_paused = None
        if inference_engine is not None:
            try:
                inference_paused = bool(getattr(inference_engine, "_paused").is_set())
            except Exception:
                inference_paused = None
        
        worker_info = {}
        if self._worker_manager:
            worker_info = {
                "worker_id": self._worker_manager.worker_id,
                "assigned_cameras": len(self._worker_manager.assigned_camera_ids),
            }

        status = RuntimeStatus(
            running=self._running,
            config_source="mongo",
            config_fetched_at=None,
            cameras_total=cameras_total,
            cameras_enabled=cameras_enabled,
            cameras_alive=cameras_alive,
            inference_paused=inference_paused,
            started_at=self._started_at,
        )
        return {
            "running": status.running,
            "config": {
                "source": status.config_source,
                "cameras_count": self._config_meta.get("cameras_count", 0),
                "worker_id": self._config_meta.get("worker_id"),
            },
            "cameras": {
                "total": status.cameras_total,
                "enabled": status.cameras_enabled,
                "alive": status.cameras_alive,
            },
            "inference": {
                "paused": status.inference_paused,
            },
            "worker": worker_info,
            "started_at": status.started_at,
        }


runtime_service = RuntimeService()

