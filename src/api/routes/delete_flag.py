from typing import Any, Dict
from fastapi import APIRouter
from api.schemas.payloads import WebhookPayload
from datetime import datetime
import asyncio
import time
import api.state as api_state
from persistence.mongo.mongo_start_event_client import MongoStartEventClient
from api.settings import settings

router = APIRouter()
_start_event_client = MongoStartEventClient()

#This services used to reset flag from webhook from external server
@router.post("/delete-flag")
async def delete_flag(payload: WebhookPayload) -> Dict[str, Any]:
    """Receive webhook from external server to reset flags."""
    if not api_state.state_manager:
        return {"error": "State manager not initialized", "success": False}

    order_id = payload.orderId
    status = payload.status

    # Query MongoDB để lấy tất cả start_ nodes của order_id
    start_nodes = await _start_event_client.get_starts_by_order_id(order_id)
    
    # Reset RAM state (nếu có trong order_mapping)
    pairs = api_state.state_manager.order_mapping.get(order_id)
    if pairs:
        for start_point, end_point, _empty_car in pairs:
            api_state.state_manager.points[start_point]["flag"] = False
            api_state.state_manager.points[end_point]["flag"] = False
            api_state.state_manager.points[start_point]["time"] = time.time()
            api_state.state_manager.points[end_point]["time"] = time.time()
            
            api_state.state_manager.ready_start_list.discard(start_point)
            api_state.state_manager.ready_end_list.discard(end_point)
        
        del api_state.state_manager.order_mapping[order_id]
        for _start_point, end_point, _empty_car in pairs:
            api_state.state_manager.pair_mapping.pop(end_point, None)
    
    # Schedule delayed reset cho tất cả start_ nodes từ MongoDB
    for node_doc in start_nodes:
        node_id = node_doc.get("node_id")
        if node_id and node_id.startswith("start_"):
            asyncio.create_task(
                _start_event_client.reset_to_pending_after_delay(
                    node_id=node_id,
                    worker_id=settings.WORKER_ID,
                    delay_seconds=30,
                )
            )
    
    if status == 3:
        return {
            "code": "1000",
            "message": f"Flags reset for orderId {order_id}, {len(start_nodes)} start_ nodes scheduled",
        }
    
    if status == 23:
        return {
            "code": "1000",
            "message": f"Partial reset for orderId {order_id}, {len(start_nodes)} start_ nodes scheduled",
        }

    return {
        "code": "1001",
        "message": f"OrderId {order_id} not found",
        "status": status,
    }
