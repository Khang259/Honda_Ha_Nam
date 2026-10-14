"""
Service xử lý bật/tắt camera theo cameraId.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from shared.setup_log import setup_logger

logger = setup_logger("camera_control_service", "logs/camera_control_service/log")


class CameraControlService:
    """Service điều khiển camera (enable/disable) theo cameraId."""

    def find_camera_index(self, camera_manager: Any, camera_id: int) -> Optional[int]:
        cameras_config = getattr(camera_manager, "cameras_config", None) or []
        for i, cam in enumerate(cameras_config):
            cid = cam.get("cameraId", i)
            if int(cid) == int(camera_id):
                return i
        return None

    def toggle_camera(
        self,
        camera_manager: Any,
        inference_engine: Any,
        camera_id: int,
    ) -> Dict[str, Any]:
        camera_id = int(camera_id)
        enabled_map = getattr(camera_manager, "enabled", None)

        # Dict theo cameraId (hot-apply)
        if isinstance(enabled_map, dict):
            with camera_manager._enabled_lock:
                if camera_id not in enabled_map and camera_id not in getattr(
                    camera_manager, "threads_by_camera_id", {}
                ):
                    logger.warning(f"Camera cameraId={camera_id} not found")
                    return {
                        "code": 1002,
                        "message": f"Không tìm thấy camera với cameraId {camera_id}",
                    }
                new_value = not bool(enabled_map.get(camera_id, False))
                enabled_map[camera_id] = new_value
                enabled_count = sum(1 for e in enabled_map.values() if e)
        else:
            index = self.find_camera_index(camera_manager, camera_id)
            if index is None:
                logger.warning(f"Camera cameraId={camera_id} not found")
                return {
                    "code": 1002,
                    "message": f"Không tìm thấy camera với cameraId {camera_id}",
                }
            with camera_manager._enabled_lock:
                if not (0 <= index < len(camera_manager.enabled)):
                    logger.error(
                        f"Invalid camera index={index} for cameraId={camera_id}"
                    )
                    return {"code": 1003, "message": "Invalid camera index"}
                new_value = not camera_manager.enabled[index]
                camera_manager.enabled[index] = new_value
                enabled_count = sum(1 for e in camera_manager.enabled if e)

        if enabled_count > 0:
            inference_engine.resume()
        else:
            inference_engine.pause()

        logger.info(f"Toggled camera cameraId={camera_id}: enabled={new_value}")
        return {"id": camera_id, "enabled": new_value}


camera_control_service = CameraControlService()
