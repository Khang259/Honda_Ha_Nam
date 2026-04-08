# File: api/routes/cameras.py
"""
Camera control routes.

In mode "API+Worker merged", commands are executed in-process by calling
`CameraManager` and controlling `InferenceEngine` pause/resume.
"""
from typing import Dict, Any
from fastapi import APIRouter

import api.state as api_state
from utils.setup_log import setup_logger

logger = setup_logger("cameras_routes", "logs/cameras_routes/log")

router = APIRouter(prefix="/cameras", tags=["cameras"])


# ============ Camera Control ============

@router.post("/start-all")
async def start_all_cameras() -> Dict[str, Any]:
    """Enable all cameras and resume inference."""
    if not api_state.camera_manager or not api_state.inference_engine:
        return {"error": "camera_manager/inference_engine not initialized", "success": False}
    api_state.camera_manager.start_all_cameras()
    api_state.inference_engine.resume()
    return {"success": True, "message": "All cameras enabled"}


@router.post("/stop-all")
async def stop_all_cameras() -> Dict[str, Any]:
    """Disable all cameras and pause inference."""
    if not api_state.camera_manager or not api_state.inference_engine:
        return {"error": "camera_manager/inference_engine not initialized", "success": False}
    api_state.camera_manager.stop_all_cameras()
    api_state.inference_engine.pause()
    return {"success": True, "message": "All cameras disabled"}


@router.post("/{zone}/start-all")
async def start_zone_cameras(zone: str) -> Dict[str, Any]:
    """Enable all cameras in specified zone and resume inference if needed."""
    if not api_state.camera_manager or not api_state.inference_engine:
        return {"error": "camera_manager/inference_engine not initialized", "success": False}
    z = zone.upper()
    api_state.camera_manager.set_zone_enabled(z, True)
    enabled_count = api_state.camera_manager.get_status().get("enabled", 0)
    if enabled_count > 0:
        api_state.inference_engine.resume()
    return {"success": True, "message": f"Zone {z} enabled", "enabled": enabled_count}


@router.post("/{zone}/stop-all")
async def stop_zone_cameras(zone: str) -> Dict[str, Any]:
    """Disable all cameras in specified zone and pause inference if no camera is enabled."""
    if not api_state.camera_manager or not api_state.inference_engine:
        return {"error": "camera_manager/inference_engine not initialized", "success": False}
    z = zone.upper()
    api_state.camera_manager.set_zone_enabled(z, False)
    enabled_count = api_state.camera_manager.get_status().get("enabled", 0)
    if enabled_count == 0:
        api_state.inference_engine.pause()
    return {"success": True, "message": f"Zone {z} disabled", "enabled": enabled_count}


@router.post("/flag/{node_id}")
async def toggle_node_flag(node_id: str) -> Dict[str, Any]:
    """Toggle flag của node_id trong StateManager."""
    if not api_state.state_manager:
        return {"error": "State manager not initialized", "success": False}
    
    if node_id in api_state.state_manager.points:
        current = api_state.state_manager.points[node_id]["flag"]
        api_state.state_manager.points[node_id]["flag"] = not current
        logger.info(f"Toggled flag for {node_id}: {current} -> {not current}")
        return {"success": True, "node_id": node_id, "flag": not current}
    
    logger.warning(f"Node {node_id} not found in state manager")
    return {"error": "Node not found", "success": False}


@router.get("/{zone}")
async def get_zone(zone: str) -> Dict[str, Any]:
    """Trả về snapshot state + flags của các node_id trong zone."""
    from config import VALIDATE_PAIRS_BY_ZONE
    
    if not api_state.state_manager:
        return {"error": "State manager not initialized", "success": False}
    
    zone_pairs = VALIDATE_PAIRS_BY_ZONE.get(zone.upper(), [])
    zone_node_ids = set()
    for pair in zone_pairs:
        for node_id in pair:
            zone_node_ids.add(node_id)
    
    if not zone_node_ids:
        return {"error": "Zone not found", "success": False}
    
    nodes = {}
    flags = {}
    for node_id in zone_node_ids:
        if node_id in api_state.state_manager.points:
            data = api_state.state_manager.points[node_id]
            nodes[node_id] = {
                "state": data["state"],
                "flag": data["flag"]
            }
            flags[node_id] = data["flag"]
    
    return {"success": True, "zone": zone.upper(), "nodes": nodes, "flags": flags}
