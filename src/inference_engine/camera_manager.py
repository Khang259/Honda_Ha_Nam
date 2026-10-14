# core/camera_manager.py
import threading
import queue
from typing import Any, Dict, List, Optional, Set

from shared.setup_log import setup_logger
from inference_engine.camera_processor import CameraProcessor

logger = setup_logger("camera_manager", "logs/camera_manager/log")


class CameraManager:

    def __init__(
        self,
        cameras_config,
        state_manager,
        inference_engine,
        snapshot_manager=None,
        camera_zones=None,
    ):
        self.cameras_config: List[dict] = list(cameras_config or [])
        self.state_manager = state_manager
        self.inference_engine = inference_engine
        self.snapshot_manager = snapshot_manager

        # cameraId (Mongo) -> zone / enabled
        self.camera_zones: Dict[int, str] = {}
        self.enabled: Dict[int, bool] = {}
        self._enabled_lock = threading.Lock()

        self.threads: List[CameraProcessor] = []
        self.threads_by_camera_id: Dict[int, CameraProcessor] = {}
        self.latest_frames = {}
        self._node_id_to_cam = {}
        self._next_slot = 0
        self._started = False

        if camera_zones and isinstance(camera_zones, dict):
            self.camera_zones = {int(k): v for k, v in camera_zones.items()}
        else:
            zone_list = list(camera_zones or [])
            for i, cam in enumerate(self.cameras_config):
                cid = int(cam.get("cameraId", i))
                if zone_list and i < len(zone_list) and zone_list[i]:
                    self.camera_zones[cid] = zone_list[i]
                else:
                    self.camera_zones[cid] = cam.get("area_name") or cam.get("zone") or "AE5"

        for i, cam in enumerate(self.cameras_config):
            cid = int(cam.get("cameraId", i))
            self.enabled[cid] = False

        self._rebuild_node_id_to_cam()

    def _mongo_camera_id(self, cam: dict, fallback_index: int) -> int:
        return int(cam.get("cameraId", fallback_index))

    def _get_inference_engine_for_camera_index(self, camera_index: int):
        engine = self.inference_engine
        getter = getattr(engine, "get_engine_for_camera_index", None)
        if callable(getter):
            selected = getter(camera_index)
            if selected is not None:
                return selected
        return engine

    def _get_cam_url(self, cam: dict) -> str:
        return cam.get("url")

    def _get_internal_rois(self, cam: dict):
        rois = cam.get("rois", [])
        if isinstance(rois, dict):
            internal = []
            for roi_key, roi_val in rois.items():
                if isinstance(roi_val, dict):
                    coords = roi_val.get("roi")
                    is_start = bool(roi_val.get("start"))
                    is_end = bool(roi_val.get("end"))
                else:
                    coords = roi_val
                    is_start = False
                    is_end = False

                if not coords or len(coords) < 4:
                    continue

                roi_key_str = str(roi_key)
                if roi_key_str.startswith("start_") or roi_key_str.startswith("end_"):
                    node_id = roi_key_str
                else:
                    if is_start:
                        node_id = f"start_{roi_key_str}"
                    elif is_end:
                        node_id = f"end_{roi_key_str}"
                    else:
                        continue

                internal.append({"node_id": node_id, "roi": coords})
            return internal

        return rois or []

    def _rebuild_node_id_to_cam(self):
        self._node_id_to_cam = {}
        for i, cam in enumerate(self.cameras_config):
            camera_id = self._mongo_camera_id(cam, i)
            cam_id = f"cam_{i}_{camera_id}"
            for roi_dict in self._get_internal_rois(cam):
                node_id = roi_dict.get("node_id")
                if node_id and node_id not in self._node_id_to_cam:
                    self._node_id_to_cam[node_id] = (cam_id, i)

    def _spawn_thread(self, cam: dict, slot_index: int, initially_enabled: bool) -> CameraProcessor:
        camera_id = self._mongo_camera_id(cam, slot_index)
        cam_id = f"cam_{slot_index}_{camera_id}"
        cam_url = self._get_cam_url(cam)

        result_queue = queue.Queue(maxsize=10)
        engine = self._get_inference_engine_for_camera_index(slot_index)
        engine.register_camera(cam_id, result_queue)

        rois_internal = self._get_internal_rois(cam)
        thread = CameraProcessor(
            cam_url,
            rois_internal,
            self.state_manager,
            engine,
            result_queue,
            cam_id,
            snapshot_manager=self.snapshot_manager,
            enabled_ref=self.enabled,
            camera_index=slot_index,
            mongo_camera_id=camera_id,
            latest_frames_ref=self.latest_frames,
        )
        with self._enabled_lock:
            self.enabled[camera_id] = bool(initially_enabled)
            if camera_id not in self.camera_zones:
                self.camera_zones[camera_id] = (
                    cam.get("area_name") or cam.get("zone") or "AE5"
                )

        self.threads.append(thread)
        self.threads_by_camera_id[camera_id] = thread
        thread.start()
        return thread

    def start(self):
        # Stagger nhẹ giữa các thread lúc tạo (jitter chính nằm ở CameraProcessor khi mở ffmpeg)
        for i, cam in enumerate(self.cameras_config):
            self._spawn_thread(cam, i, initially_enabled=False)
            self._next_slot = i + 1
        self._started = True
        self._rebuild_node_id_to_cam()
        logger.info(f"All {len(self.threads)} camera threads started")

    def add_camera(self, cam_config: dict, initially_enabled: bool = False) -> bool:
        """Hot-add một camera đang chạy. Trả False nếu đã có."""
        if not cam_config:
            return False
        camera_id = self._mongo_camera_id(cam_config, self._next_slot)
        if camera_id in self.threads_by_camera_id:
            logger.info("add_camera skip: cameraId=%s already present", camera_id)
            return False

        slot = self._next_slot
        self._next_slot += 1
        self.cameras_config.append(cam_config)
        self._spawn_thread(cam_config, slot, initially_enabled=initially_enabled)
        self._rebuild_node_id_to_cam()
        logger.info(
            "Hot-added cameraId=%s enabled=%s (threads=%s)",
            camera_id,
            initially_enabled,
            len(self.threads),
        )
        return True

    def remove_camera(self, camera_id: int) -> bool:
        """Hot-remove camera: stop thread, bỏ khỏi config/enabled."""
        camera_id = int(camera_id)
        thread = self.threads_by_camera_id.get(camera_id)
        if thread is None:
            logger.warning("remove_camera: cameraId=%s not found", camera_id)
            return False

        thread.running = False
        if thread.is_alive():
            thread.join(timeout=2.0)

        engine = self._get_inference_engine_for_camera_index(getattr(thread, "camera_index", 0))
        unregister = getattr(engine, "unregister_camera", None)
        if callable(unregister):
            try:
                unregister(thread.cam_id)
            except Exception as e:
                logger.warning("unregister_camera failed for %s: %s", thread.cam_id, e)

        self.threads = [t for t in self.threads if t is not thread]
        self.threads_by_camera_id.pop(camera_id, None)
        self.cameras_config = [
            c
            for i, c in enumerate(self.cameras_config)
            if self._mongo_camera_id(c, i) != camera_id
        ]
        with self._enabled_lock:
            self.enabled.pop(camera_id, None)
            self.camera_zones.pop(camera_id, None)

        self.latest_frames.pop(thread.cam_id, None)
        self._rebuild_node_id_to_cam()
        logger.info("Hot-removed cameraId=%s (threads=%s)", camera_id, len(self.threads))
        return True

    def get_managed_camera_ids(self) -> Set[int]:
        return set(self.threads_by_camera_id.keys())

    def stop(self):
        logger.info("Stopping all camera threads...")
        for thread in self.threads:
            if thread.is_alive():
                thread.running = False
        for thread in self.threads:
            if thread.is_alive():
                thread.join(timeout=2.0)
        alive_count = sum(1 for t in self.threads if t.is_alive())
        if alive_count > 0:
            logger.warning(f"{alive_count} camera threads still alive after shutdown")
        else:
            logger.info("All camera threads stopped successfully")

    def set_camera_enabled(self, index: int, on: bool):
        """Backward-compatible: index trong cameras_config."""
        if 0 <= index < len(self.cameras_config):
            cid = self._mongo_camera_id(self.cameras_config[index], index)
            self.set_camera_enabled_by_id(cid, on)

    def set_camera_enabled_by_id(self, camera_id: int, on: bool):
        with self._enabled_lock:
            if int(camera_id) in self.enabled or int(camera_id) in self.threads_by_camera_id:
                self.enabled[int(camera_id)] = bool(on)

    def set_zone_enabled(self, zone: str, on: bool):
        with self._enabled_lock:
            for cid, z in self.camera_zones.items():
                if z == zone:
                    self.enabled[cid] = bool(on)

    def start_all_cameras(self):
        with self._enabled_lock:
            for cid in list(self.enabled.keys()):
                self.enabled[cid] = True
            for cid in self.threads_by_camera_id:
                self.enabled[cid] = True
        logger.info("All cameras enabled")

    def stop_all_cameras(self):
        with self._enabled_lock:
            for cid in list(self.enabled.keys()):
                self.enabled[cid] = False
        logger.info("All cameras disabled")

    def get_cam_id_for_node(self, node_id: str):
        info = self._node_id_to_cam.get(node_id)
        return info[0] if info else None

    def get_status(self):
        with self._enabled_lock:
            enabled_count = sum(1 for e in self.enabled.values() if e)
        return {
            "total": len(self.threads),
            "alive": sum(1 for t in self.threads if t.is_alive()),
            "enabled": enabled_count,
        }

    def get_camera_detections(self, cam_id: str):
        for thread in self.threads:
            if hasattr(thread, "cam_id") and thread.cam_id == cam_id:
                if hasattr(thread, "_detections_lock"):
                    with thread._detections_lock:
                        return thread.latest_detections
        return None

    def get_camera_rois(self, cam_id: str):
        for thread in self.threads:
            if hasattr(thread, "cam_id") and thread.cam_id == cam_id:
                if hasattr(thread, "rois"):
                    return thread.rois
        return []

    def get_all_camera_ids(self):
        return list(self.latest_frames.keys())

    def get_cameras_enable_snapshot(self) -> list[dict]:
        with self._enabled_lock:
            items: list[dict] = []
            for i, cam in enumerate(self.cameras_config or []):
                camera_id = self._mongo_camera_id(cam, i)
                zone = self.camera_zones.get(camera_id)
                enabled = bool(self.enabled.get(camera_id, False))
                items.append(
                    {
                        "index": i,
                        "cameraId": camera_id,
                        "enabled": enabled,
                        "zone": zone,
                    }
                )
            return items

    def get_nodes_by_zone(self, zone: str) -> Set[str]:
        nodes: Set[str] = set()
        for cid, z in self.camera_zones.items():
            if z != zone:
                continue
            thread = self.threads_by_camera_id.get(cid)
            if not thread:
                continue
            for roi in thread.rois or []:
                nid = roi.get("node_id")
                if nid:
                    nodes.add(nid)
        return nodes

    def get_nodes_by_camera_id(self, camera_id: int) -> Set[str]:
        nodes: Set[str] = set()
        thread = self.threads_by_camera_id.get(int(camera_id))
        if not thread:
            return nodes
        for roi in thread.rois or []:
            nid = roi.get("node_id")
            if nid:
                nodes.add(nid)
        return nodes
