from typing import Any, Dict

from fastapi import APIRouter

import api.state as api_state
from api.schemas.payloads import DetectionPayload

router = APIRouter()


# @router.post("/detections")
# async def post_detection(payload: DetectionPayload) -> Dict[str, Any]:
#     """AI worker sends detection results."""
#     if not api_state.state_manager:
#         return {"error": "State manager not initialized", "success": False}

#     api_state.state_manager.get_state_nodes(payload.node_id, payload.detected)
#     return {"success": True, "message": "Detection updated"}

