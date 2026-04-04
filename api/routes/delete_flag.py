from typing import Any, Dict

from fastapi import APIRouter

import api.state as api_state
from api.schemas.payloads import WebhookPayload

router = APIRouter()


@router.post("/delete-flag")
async def delete_flag(payload: WebhookPayload) -> Dict[str, Any]:
    """Receive webhook from external server to reset flags."""
    if not api_state.state_manager:
        return {"error": "State manager not initialized", "success": False}

    order_id = payload.orderId
    status = payload.status

    pairs = api_state.state_manager.order_mapping.get(order_id)
    if not pairs:
        # keep original response shape
        return {"error": f"orderId {order_id} not found", "status": False}

    if status == 3:
        # Reset ALL points (normal + empty) for this orderId
        for start_point, end_point, _empty_car in pairs:
            api_state.state_manager.points[start_point]["flag"] = False
            api_state.state_manager.points[end_point]["flag"] = False

            api_state.state_manager.ready_start_list.discard(start_point)
            api_state.state_manager.ready_end_list.discard(end_point)

        # Clean mappings
        del api_state.state_manager.order_mapping[order_id]
        for _start_point, end_point, _empty_car in pairs:
            api_state.state_manager.pair_mapping.pop(end_point, None)

        return {
            "success": True,
            "message": f"Flags reset for all points of orderId {order_id}",
            "orderId": order_id,
        }

    if status == 23:
        # Reset only empty points for this orderId (keep normal if exists)
        remaining = []
        reset_pairs = []

        for start_point, end_point, empty_car in pairs:
            if empty_car:
                api_state.state_manager.points[start_point]["flag"] = False
                api_state.state_manager.points[end_point]["flag"] = False

                api_state.state_manager.ready_start_list.discard(start_point)
                api_state.state_manager.ready_end_list.discard(end_point)

                api_state.state_manager.pair_mapping.pop(end_point, None)
                reset_pairs.append([start_point, end_point])
            else:
                remaining.append((start_point, end_point, empty_car))

        if remaining:
            api_state.state_manager.order_mapping[order_id] = remaining
        else:
            del api_state.state_manager.order_mapping[order_id]

        return {
            "success": True,
            "message": f"Empty pairs reset for orderId {order_id}",
            "orderId": order_id,
            "reset_pairs": reset_pairs,
        }

    return {
        "message": f"OrderId {order_id} not found",
        "status": status,
    }

