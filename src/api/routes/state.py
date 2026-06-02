from typing import Any, Dict, List

from fastapi import APIRouter

import api.state as api_state

router = APIRouter()


@router.get("/state/points")
async def get_state_points() -> Dict[str, Any]:
    """Get all node points state."""
    if not api_state.state_manager:
        return {"error": "State manager not initialized", "success": False}

    points_list: List[Dict[str, Any]] = []
    for node_id, data in api_state.state_manager.points.items():
        points_list.append({
            "node_id": node_id,
            "state": data["state"],
            "enabled": data["flag"]
        })

    return {"code": 1000, "message": "Success", "data": points_list}
