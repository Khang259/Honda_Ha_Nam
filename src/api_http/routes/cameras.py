# File: api/routes/cameras.py
"""
Camera control routes.
`CameraManager` and controlling `InferenceEngine` pause/resume.
"""
from typing import Dict, Any, Set
from fastapi import APIRouter

from api_http.schemas.node_flag import NodeFlagRequest
from api_http.schemas.camera_flag import CameraFlagRequest
import api_http.state as api_state
from api_http.services.camera_health_service import camera_health_service
from api_http.services.camera_control_service import camera_control_service
from shared.setup_log import setup_logger

logger = setup_logger("engine_control_routes", "logs/engine_control_routes/log")

router = APIRouter()


def _get_nodes_by_zone(zone: str) -> Set[str]:
    """Lấy tất cả node_ids thuộc zone."""
    nodes = set()
    if not api_state.camera_manager:
        return nodes
    
    for i, cam_zone in enumerate(api_state.camera_manager.camera_zones):
        if cam_zone == zone:
            # Lấy nodes từ camera index i
            for thread in api_state.camera_manager.threads:
                if hasattr(thread, 'camera_index') and thread.camera_index == i:
                    for roi in thread.rois:
                        nodes.add(roi["node_id"])
    return nodes


def _get_nodes_by_camera(camera_id: int) -> Set[str]:
    """Lấy tất cả node_ids thuộc camera."""
    nodes = set()
    if not api_state.camera_manager:
        return nodes
    
    index = camera_control_service.find_camera_index(api_state.camera_manager, camera_id)
    if index is not None:
        for thread in api_state.camera_manager.threads:
            if hasattr(thread, 'camera_index') and thread.camera_index == index:
                for roi in thread.rois:
                    nodes.add(roi["node_id"])
    return nodes

@router.post("/start-all")
async def start_all_cameras() -> Dict[str, Any]:
    """Enable all cameras and resume inference."""
    if not api_state.camera_manager or not api_state.inference_engine:
        return {"error": "camera_manager/inference_engine not initialized", "success": False}
    
    api_state.camera_manager.start_all_cameras()
    api_state.inference_engine.resume()
    
    if api_state.pairing_orchestrator:
        api_state.pairing_orchestrator.resume()
    
    return {"code": 1000, "message": "Success enable (camera + inference + pairing)"}


@router.post("/stop-all")
async def stop_all_cameras() -> Dict[str, Any]:
    """Disable all cameras and pause inference."""
    if not api_state.camera_manager or not api_state.inference_engine:
        return {"error": "camera_manager/inference_engine not initialized", "success": False}
    
    api_state.camera_manager.stop_all_cameras()
    api_state.inference_engine.pause()
    
    if api_state.pairing_orchestrator:
        api_state.pairing_orchestrator.pause()
    
    return {"code": 1000, "message": "Success disable (camera + inference + pairing)"}


@router.post("/{zone}/start-all")
async def start_zone_cameras(zone: str) -> Dict[str, Any]:
    """Enable all cameras in specified zone and resume inference if needed."""
    if not api_state.camera_manager or not api_state.inference_engine:
        return {"error": "camera_manager/inference_engine not initialized", "success": False}
    
    z = zone.upper()
    
    # Enable pairing cho nodes của zone
    zone_nodes = _get_nodes_by_zone(z)
    if api_state.pairing_orchestrator:
        api_state.pairing_orchestrator.enable_nodes(zone_nodes)
    
    # Start camera
    api_state.camera_manager.set_zone_enabled(z, True)
    enabled_count = api_state.camera_manager.get_status().get("enabled", 0)
    
    if enabled_count > 0:
        api_state.inference_engine.resume()
        if api_state.pairing_orchestrator and api_state.pairing_orchestrator._paused:
            api_state.pairing_orchestrator.resume()
    
    return {
        "code": 1000,
        "message": f"Zone {z} enabled (pairing resumed for {len(zone_nodes)} nodes)",
        "enabled": enabled_count
    }


@router.post("/{zone}/stop-all")
async def stop_zone_cameras(zone: str) -> Dict[str, Any]:
    """Disable all cameras in specified zone and pause inference if no camera is enabled."""
    if not api_state.camera_manager or not api_state.inference_engine:
        return {"error": "camera_manager/inference_engine not initialized", "success": False}
    
    z = zone.upper()
    
    # Tìm tất cả node_ids thuộc zone này
    zone_nodes = _get_nodes_by_zone(z)
    
    # Disable pairing cho nodes của zone
    if api_state.pairing_orchestrator:
        api_state.pairing_orchestrator.disable_nodes(zone_nodes)
    
    # Stop camera
    api_state.camera_manager.set_zone_enabled(z, False)
    enabled_count = api_state.camera_manager.get_status().get("enabled", 0)
    
    if enabled_count == 0:
        api_state.inference_engine.pause()
        if api_state.pairing_orchestrator:
            api_state.pairing_orchestrator.pause()
    
    return {
        "code": 1000,
        "message": f"Zone {z} disabled (pairing stopped for {len(zone_nodes)} nodes)",
        "enabled": enabled_count,
        "disabled_nodes": len(zone_nodes)
    }

# Gán flag theo body { "id", "enable" }; flag trong StateManager = enable
@router.post("/flag-node-id")
async def set_node_flag(payload: NodeFlagRequest) -> Dict[str, Any]:
    """Đặt flag của node_id (payload.id) trong StateManager bằng payload.enable."""
    if not api_state.state_manager:
        return {"error": "State manager not initialized", "success": False}

    node_id = payload.id
    if node_id in api_state.state_manager.points:
        api_state.state_manager.points[node_id]["flag"] = payload.enable
        logger.info(f"Set flag for {node_id}: flag={payload.enable}")
        return {
            "success": True,
            "id": node_id,
            "enable": payload.enable,
        }

    logger.warning(f"Node {node_id} not found in state manager")
    return {"error": "Node not found", "success": False}


@router.post("/flag-camera-id")
async def set_camera_flag(payload: CameraFlagRequest) -> Dict[str, Any]:
    """Toggle bật/tắt một camera theo cameraId từ MongoDB."""
    if not api_state.camera_manager or not api_state.inference_engine:
        return {"code": 1001, "message": "camera_manager/inference_engine not initialized"}
    
    # Tìm nodes thuộc camera này
    camera_nodes = _get_nodes_by_camera(payload.id)
    
    # Toggle camera
    result = camera_control_service.toggle_camera(
        api_state.camera_manager,
        api_state.inference_engine,
        payload.id
    )
    
    # Cập nhật pairing
    if api_state.pairing_orchestrator:
        if result.get("enabled"):
            api_state.pairing_orchestrator.enable_nodes(camera_nodes)
        else:
            api_state.pairing_orchestrator.disable_nodes(camera_nodes)
    
    result["disabled_nodes_count"] = len(camera_nodes)
    return result

@router.get("/health-check-cameras")
async def health_check_cameras() -> Dict[str, Any]:
    if not api_state.camera_manager:
        return {"code": 1001, "message": "camera_manager not initialized", "data": []}
    data = await camera_health_service.check_area_all()
    return {"code": 1000, "message": "Success", "data": data}

@router.get("/cameras-enable-state")
async def get_cameras_enable_state() -> Dict[str, Any]:
    if not api_state.camera_manager:
        return {"code": 1001, "message": "camera_manager not initialized", "data": []}
    data = api_state.camera_manager.get_cameras_enable_snapshot()
    return {"code": 1000, "message": "Success", "data": data}

@router.get("/{zone}")
async def get_zone(zone: str) -> Dict[str, Any]:
    """Trả về snapshot state + flags của các node_id trong zone."""
    if not api_state.state_manager:
        return {"error": "State manager not initialized", "success": False}
    
    # Lấy tất cả node_ids từ validate_pairs của StateManager
    zone_node_ids = set()
    for pair in api_state.state_manager.validate_pairs:
        for node_id in pair:
            zone_node_ids.add(node_id)
    
    if not zone_node_ids:
        return {"error": "No pairs loaded in state manager", "success": False}
    
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