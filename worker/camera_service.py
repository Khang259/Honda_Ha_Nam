# File: worker/camera_service.py
"""
Internal HTTP service for camera control.
Runs inside worker process to expose camera_manager controls via HTTP.
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from utils.setup_log import setup_logger

logger = setup_logger("camera_service", "logs/camera_service/log")

app = FastAPI(title="Camera Control Service", version="1.0.0")

# Global ref to camera_manager (set from main_worker.py)
camera_manager_ref = None


class CameraControlRequest(BaseModel):
    zone: Optional[str] = None
    camera_index: Optional[int] = None
    enabled: Optional[bool] = None


@app.post("/internal/cameras/start-all")
async def start_all():
    """Start all cameras."""
    if camera_manager_ref:
        camera_manager_ref.start_all_cameras()
        logger.info("All cameras started via API")
        return {"success": True, "message": "All cameras started"}
    return {"error": "Camera manager not initialized", "success": False}


@app.post("/internal/cameras/stop-all")
async def stop_all():
    """Stop all cameras."""
    if camera_manager_ref:
        camera_manager_ref.stop_all_cameras()
        logger.info("All cameras stopped via API")
        return {"success": True, "message": "All cameras stopped"}
    return {"error": "Camera manager not initialized", "success": False}


@app.post("/internal/cameras/zone")
async def set_zone(req: CameraControlRequest):
    """Enable/disable cameras by zone."""
    if not camera_manager_ref:
        return {"error": "Camera manager not initialized", "success": False}
    
    if not req.zone or req.enabled is None:
        return {"error": "Invalid request - zone and enabled required", "success": False}
    
    camera_manager_ref.set_zone_enabled(req.zone, req.enabled)
    action = "enabled" if req.enabled else "disabled"
    logger.info(f"Zone {req.zone} cameras {action} via API")
    return {"success": True, "message": f"Zone {req.zone} {action}"}


@app.post("/internal/cameras/camera")
async def set_camera(req: CameraControlRequest):
    """Enable/disable specific camera by index."""
    if not camera_manager_ref:
        return {"error": "Camera manager not initialized", "success": False}
    
    if req.camera_index is None or req.enabled is None:
        return {"error": "Invalid request - camera_index and enabled required", "success": False}
    
    camera_manager_ref.set_camera_enabled(req.camera_index, req.enabled)
    action = "enabled" if req.enabled else "disabled"
    logger.info(f"Camera {req.camera_index} {action} via API")
    return {"success": True, "message": f"Camera {req.camera_index} {action}"}


@app.get("/internal/cameras/status")
async def get_status():
    """Get camera manager status."""
    if camera_manager_ref:
        status = camera_manager_ref.get_status()
        return {"success": True, "status": status}
    return {"error": "Camera manager not initialized", "success": False}


@app.get("/internal/health")
async def health_check():
    """Health check for camera service."""
    return {
        "status": "ok",
        "service": "Camera Control Service",
        "camera_manager_initialized": camera_manager_ref is not None
    }
