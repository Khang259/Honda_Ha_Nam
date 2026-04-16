from typing import Any, Dict

from fastapi import APIRouter

import api.state as api_state
from api.schemas.payloads import WebhookPayload

router = APIRouter()

#This services used to reset flag from webhook from external server
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
            "code": "1000",
            "message": f"Flags reset for all points of orderId {order_id}",
        }

    if status == 23:
    # Kiểm tra có phải lệnh đôi không
        is_double_task = order_id.startswith("D-")
        
        if is_double_task:
            # Lệnh đôi: reset theo thứ tự ưu tiên
            remaining = []
            reset_pairs = []
            
            # Kiểm tra xem còn normal pair (empty_car=True) không
            has_normal = any(empty_car for _, _, empty_car in pairs)
            
            for start_point, end_point, empty_car in pairs:
                if has_normal:
                    # Lần 1: reset normal pair (empty_car=True), giữ empty pair
                    if empty_car:
                        api_state.state_manager.points[start_point]["flag"] = False
                        api_state.state_manager.points[end_point]["flag"] = False
                        
                        api_state.state_manager.ready_start_list.discard(start_point)
                        api_state.state_manager.ready_end_list.discard(end_point)
                        
                        api_state.state_manager.pair_mapping.pop(end_point, None)
                    else:
                        # Giữ lại empty pair cho lần 2
                        remaining.append((start_point, end_point, empty_car))
                else:
                    # Lần 2: reset empty pair (empty_car=False)
                    api_state.state_manager.points[start_point]["flag"] = False
                    api_state.state_manager.points[end_point]["flag"] = False
                    
                    api_state.state_manager.ready_start_list.discard(start_point)
                    api_state.state_manager.ready_end_list.discard(end_point)
                    
                    api_state.state_manager.pair_mapping.pop(end_point, None)
            
            # Cập nhật order_mapping
            if remaining:
                api_state.state_manager.order_mapping[order_id] = remaining
                message = f"Normal pair reset for orderId {order_id}, empty pair kept"
            else:
                del api_state.state_manager.order_mapping[order_id]
                message = f"Empty pair reset for orderId {order_id}, all pairs completed"
        
        else:
            # Lệnh đơn hoặc empty: reset tất cả
            for start_point, end_point, _empty_car in pairs:
                api_state.state_manager.points[start_point]["flag"] = False
                api_state.state_manager.points[end_point]["flag"] = False
                
                api_state.state_manager.ready_start_list.discard(start_point)
                api_state.state_manager.ready_end_list.discard(end_point)
                
                api_state.state_manager.pair_mapping.pop(end_point, None)
            
            del api_state.state_manager.order_mapping[order_id]
            message = f"Flags reset for orderId {order_id}"
        
        return {
            "code": "1000",
            "message": message,
        }

    return {
        "code": "1001",
        "message": f"OrderId {order_id} not found",
        "status": status,
    }