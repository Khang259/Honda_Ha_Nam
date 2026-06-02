# core/camera_manager.py
import threading
import queue
from shared.setup_log import setup_logger
from inference_engine.camera_processor import CameraProcessor

logger = setup_logger("camera_manager", "logs/camera_manager/log")


class CameraManager:

    def __init__(self, cameras_config, state_manager, inference_engine, snapshot_manager=None, camera_zones=None):
        self.cameras_config = cameras_config
        self.state_manager = state_manager
        self.inference_engine = inference_engine
        self.snapshot_manager = snapshot_manager
        self.camera_zones = camera_zones or []
        if not self.camera_zones and cameras_config:
            self.camera_zones = ["AE5"] * len(cameras_config)

        self.threads = []
        self.enabled = [False] * len(cameras_config)
        self._enabled_lock = threading.Lock()
        self.latest_frames = {}
        self._node_id_to_cam = {}
        self._build_node_id_to_cam()

    def _get_cam_url(self, cam: dict) -> str:
        return cam.get("url")

    def _get_internal_rois(self, cam: dict):
        """
        Convert CAMERAS['rois'] to internal format:
        - list[{"node_id": str, "roi": [x,y,w,h]}]
        Supports both:
        - old: rois is list of {"node_id":..., "roi":[...]}
        - new: rois is dict { "<numeric_id>": {"roi":[...], "start":bool, "end":bool} }
        """
        rois = cam.get("rois", [])
        if isinstance(rois, dict):
            internal = []
            for roi_key, roi_val in rois.items():
                # roi_val can be {"roi":[...], "start":..., "end":...} or directly [x,y,w,h]
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
                        # If no start/end role exists, we can't map to state timers.
                        continue

                internal.append({"node_id": node_id, "roi": coords})
            return internal

        # Old schema: already in internal format.
        return rois or []

    def _build_node_id_to_cam(self):
        for i, cam in enumerate(self.cameras_config):
            # Use cameraId from MongoDB if available, fallback to index
            camera_id = cam.get("cameraId", i)
            cam_id = f"cam_{i}_{camera_id}"
            for roi_dict in self._get_internal_rois(cam):
                node_id = roi_dict.get("node_id")
                if node_id and node_id not in self._node_id_to_cam:
                    self._node_id_to_cam[node_id] = (cam_id, i)

    def start(self):
        for i, cam in enumerate(self.cameras_config):
            cam_url = self._get_cam_url(cam)
            # Use cameraId from MongoDB if available, fallback to index
            camera_id = cam.get("cameraId", i)
            cam_id = f"cam_{i}_{camera_id}"

            result_queue = queue.Queue(maxsize=10)
            self.inference_engine.register_camera(cam_id, result_queue)

            rois_internal = self._get_internal_rois(cam)
            thread = CameraProcessor(
                cam_url,
                rois_internal,
                self.state_manager,
                self.inference_engine,
                result_queue,
                cam_id,
                snapshot_manager=self.snapshot_manager, #This can be deleted cause dont need to snapshot
                enabled_ref=self.enabled,
                camera_index=i,
                latest_frames_ref=self.latest_frames,
            )
            self.threads.append(thread)
            thread.start()

        logger.info(f"All {len(self.threads)} camera threads started")

    def stop(self):
        """Stop camera threads gracefully."""
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
        with self._enabled_lock:
            if 0 <= index < len(self.enabled):
                self.enabled[index] = on

    def set_zone_enabled(self, zone: str, on: bool):
        with self._enabled_lock:
            for i, z in enumerate(self.camera_zones):
                if i < len(self.enabled) and z == zone:
                    self.enabled[i] = on

    def start_all_cameras(self):
        with self._enabled_lock:
            for i in range(len(self.enabled)):
                self.enabled[i] = True
        logger.info("All cameras enabled")

    def stop_all_cameras(self):
        with self._enabled_lock:
            for i in range(len(self.enabled)):
                self.enabled[i] = False
        logger.info("All cameras disabled")

    def get_cam_id_for_node(self, node_id: str):
        info = self._node_id_to_cam.get(node_id)
        return info[0] if info else None

    def get_status(self):
        with self._enabled_lock:
            enabled_count = sum(1 for e in self.enabled if e)
        return {
            "total": len(self.threads),
            "alive": sum(1 for t in self.threads if t.is_alive()),
            "enabled": enabled_count,
        }
    
    def get_camera_detections(self, cam_id: str):
        """
        Lấy latest detections cho camera.
        
        Args:
            cam_id: ID của camera (format: cam_0_101)
        
        Returns:
            torch.Tensor hoặc None - shape (N, 6) [x1, y1, x2, y2, conf, class]
        """
        for thread in self.threads:
            if hasattr(thread, 'cam_id') and thread.cam_id == cam_id:
                if hasattr(thread, '_detections_lock'):
                    with thread._detections_lock:
                        return thread.latest_detections
        return None
    
    def get_camera_rois(self, cam_id: str):
        """
        Lấy ROIs config cho camera từ internal threads.
        NOTE: Đây là ROIs từ config lúc khởi tạo, không phải từ MongoDB.
        
        Args:
            cam_id: ID của camera (format: cam_0_101)
        
        Returns:
            list[dict] - [{"node_id": str, "roi": [x, y, w, h]}, ...]
        """
        for thread in self.threads:
            if hasattr(thread, 'cam_id') and thread.cam_id == cam_id:
                if hasattr(thread, 'rois'):
                    return thread.rois
        return []
    
    def get_all_camera_ids(self):
        """
        Lấy tất cả cam_ids đang active.
        
        Returns:
            list[str] - list of cam_ids
        """
        return list(self.latest_frames.keys())

    def get_cameras_enable_snapshot(self) -> list[dict]:
        """Snapshot bật/tắt từng camera (index + cameraId + zone)."""
        with self._enabled_lock:
            items: list[dict] = []
            for i, cam in enumerate(self.cameras_config or []):
                camera_id = cam.get("cameraId", i)
                zone = self.camera_zones[i] if i < len(self.camera_zones) else None
                enabled = bool(self.enabled[i]) if i < len(self.enabled) else False
                items.append(
                    {
                        "index": i,
                        "cameraId": camera_id,
                        "enabled": enabled,
                        "zone": zone,
                    }
                )
            return items
