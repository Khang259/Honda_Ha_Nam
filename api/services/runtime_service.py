from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from config import (
    VALIDATE_PAIRS,
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
from core.pair_manager import PairManager, get_validate_pairs
from core.snapshot_manager import SnapshotManager
from core.camera_manager import CameraManager
from core.inference_engine import InferenceEngine

import api.state as api_state
from api.services.camera_config_service import camera_config_service


@dataclass
class RuntimeStatus:
    running: bool
    area: Optional[str]
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
        self._area: Optional[str] = None
        self._config_meta: Dict[str, Any] = {}

    async def start(self, area: str) -> RuntimeStatus:
        if self._running:
            return self.status()

        cameras = await camera_config_service.refresh(area)

        # Keep config.CAMERAS in sync for scripts/tests that read the global list.
        import config as _ai_config

        _ai_config.CAMERAS = list(cameras)

        state_manager = StateManager(VALIDATE_PAIRS)
        validate_pairs = get_validate_pairs(VALIDATE_PAIRS)

        snapshot_manager = None
        if ENABLE_SNAPSHOTS:
            snapshot_manager = SnapshotManager(
                snapshot_dir=SNAPSHOT_DIR,
                quality=SNAPSHOT_QUALITY,
            )

        pair_manager = PairManager(
            ICS_URL,
            state_manager,
            validate_pairs,
            snapshot_manager=snapshot_manager,
        )
        pair_manager.start()

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

        api_state.set_state_manager(state_manager)
        api_state.set_camera_manager(camera_manager)
        api_state.set_inference_engine(inference_engine)

        self._components = {
            "state_manager": state_manager,
            "pair_manager": pair_manager,
            "snapshot_manager": snapshot_manager,
            "inference_engine": inference_engine,
            "camera_manager": camera_manager,
        }
        self._running = True
        self._started_at = time.time()
        self._area = area.upper()
        self._config_meta = {
            "cameras_count": len(cameras),
        }
        return self.status()

    def stop(self) -> RuntimeStatus:
        if not self._running:
            return self.status()

        self._running = False

        pair_manager = self._components.get("pair_manager")
        if pair_manager:
            try:
                pair_manager.stop()
            except Exception:
                pass

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
        api_state.set_state_manager(None)
        api_state.set_camera_manager(None)
        api_state.set_inference_engine(None)

        return self.status()

    async def reload(self, area: str) -> Dict[str, Any]:
        prev = self.status()
        self.stop()
        current = await self.start(area)
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

        status = RuntimeStatus(
            running=self._running,
            area=self._area,
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
            "area": status.area,
            "config": {
                "source": status.config_source,
                "cameras_count": self._config_meta.get("cameras_count", 0),
            },
            "cameras": {
                "total": status.cameras_total,
                "enabled": status.cameras_enabled,
                "alive": status.cameras_alive,
            },
            "inference": {
                "paused": status.inference_paused,
            },
            "started_at": status.started_at,
        }


runtime_service = RuntimeService()

