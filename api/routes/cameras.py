# File: api/routes/cameras.py
"""
Camera control routes.

In mode "API+Worker merged", commands are executed in-process by calling
`CameraManager` and controlling `InferenceEngine` pause/resume.
"""
from typing import Dict, Any
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import asyncio
import json
import time

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


# ============ SSE Streaming ============

@router.get("/{zone}/stream")
async def stream_zone_state(zone: str):
    """
    SSE stream trả về state/flag của các node_id trong zone.
    Gửi event khi có thay đổi hoặc heartbeat mỗi 5s.
    """
    
    async def event_generator():
        from config import VALIDATE_PAIRS_BY_ZONE
        
        # Lấy danh sách node_id trong zone này
        zone_pairs = VALIDATE_PAIRS_BY_ZONE.get(zone.upper(), [])
        zone_node_ids = set()
        for pair in zone_pairs:
            for node_id in pair:
                zone_node_ids.add(node_id)
        
        if not zone_node_ids:
            logger.warning(f"No nodes found for zone {zone}")
            yield f"data: {json.dumps({'error': 'Zone not found'})}\n\n"
            return
        
        logger.info(f"SSE stream started for zone {zone} with {len(zone_node_ids)} nodes")
        
        last_states = {}
        last_heartbeat = time.time()
        
        try:
            while True:
                if not api_state.state_manager:
                    await asyncio.sleep(1)
                    continue
                
                current_time = time.time()
                
                # Collect current states
                current_states = {}
                for node_id in zone_node_ids:
                    if node_id in api_state.state_manager.points:
                        data = api_state.state_manager.points[node_id]
                        current_states[node_id] = {
                            "state": data["state"],
                            "flag": data["flag"]
                        }
                
                # Send event if changed or heartbeat (every 5s)
                send_event = False
                if current_states != last_states:
                    send_event = True
                    logger.debug(f"State changed for zone {zone}")
                elif (current_time - last_heartbeat) >= 5.0:
                    send_event = True
                    last_heartbeat = current_time
                
                if send_event:
                    event_data = {
                        "zone": zone.upper(),
                        "nodes": current_states,
                        "timestamp": current_time
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"
                    last_states = current_states.copy()
                
                await asyncio.sleep(0.5)
        
        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled for zone {zone}")
        except Exception as e:
            logger.error(f"SSE stream error for zone {zone}: {e}")
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.get("/{zone}/status")
async def get_zone_status(zone: str) -> Dict[str, Any]:
    """HTTP GET fallback - trả về snapshot state của zone."""
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
    
    result = {}
    for node_id in zone_node_ids:
        if node_id in api_state.state_manager.points:
            data = api_state.state_manager.points[node_id]
            result[node_id] = {
                "state": data["state"],
                "flag": data["flag"]
            }
    
    return {"success": True, "zone": zone.upper(), "nodes": result}


@router.get("/{zone}/flag")
async def get_zone_flags(zone: str) -> Dict[str, Any]:
    """Get only flags of nodes in zone (alias for status with flag filter)."""
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
    
    result = {}
    for node_id in zone_node_ids:
        if node_id in api_state.state_manager.points:
            result[node_id] = api_state.state_manager.points[node_id]["flag"]
    
    return {"success": True, "zone": zone.upper(), "flags": result}
