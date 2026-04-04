from typing import Any, Dict

from fastapi import APIRouter

import api.state as api_state

router = APIRouter()


@router.get("/state/points")
async def get_state_points() -> Dict[str, Any]:
    """Get all node points state."""
    if not api_state.state_manager:
        return {"error": "State manager not initialized", "success": False}

    points_dict: Dict[str, Any] = {}
    for node_id, data in api_state.state_manager.points.items():
        points_dict[node_id] = {
            "state": data["state"],
            "time": data["time"],
            "flag": data["flag"],
        }

    return {"success": True, "points": points_dict}


@router.get("/state/ready-lists")
async def get_ready_lists() -> Dict[str, Any]:
    """Get ready_start_list and ready_end_list."""
    if not api_state.state_manager:
        return {"error": "State manager not initialized", "success": False}

    return {
        "success": True,
        "ready_start_list": list(api_state.state_manager.ready_start_list),
        "ready_end_list": list(api_state.state_manager.ready_end_list),
    }

