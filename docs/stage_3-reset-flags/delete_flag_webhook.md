# api/api_server.py - POST /delete-flag (Stage 3: reset flags)

Endpoint `POST /delete-flag` nhận webhook từ external server (ICS) để reset `flag` của các `node_id` đã được PairManager dispatch theo `orderId`.

## Endpoint: `delete_flag(payload: WebhookPayload)`

### Wiring & lấy mapping theo `orderId`

```python
@app.post("/delete-flag")
async def delete_flag(payload: WebhookPayload) -> Dict[str, Any]:
    if not state_manager:
        return {"error": "State manager not initialized", "success": False}

    order_id = payload.orderId
    status = payload.status

    pairs = state_manager.order_mapping.get(order_id)
    if not pairs:
        logger.warning(f"orderId {order_id} not found in order_mapping")
        return {"error": f"orderId {order_id} not found", "status": False}
```

### `status == 3`: reset ALL points (normal + empty) và clean mappings

```python
if status == 3:
    for start_point, end_point, _empty_car in pairs:
        state_manager.points[start_point]["flag"] = False
        state_manager.points[end_point]["flag"] = False

        state_manager.ready_start_list.discard(start_point)
        state_manager.ready_end_list.discard(end_point)

    del state_manager.order_mapping[order_id]
    for _start_point, end_point, _empty_car in pairs:
        state_manager.pair_mapping.pop(end_point, None)

    return {
        "success": True,
        "message": f"Flags reset for all points of orderId {order_id}",
        "orderId": order_id,
    }
```

### `status == 23`: reset only empty pairs

```python
elif status == 23:
    remaining = []
    reset_pairs = []

    for start_point, end_point, empty_car in pairs:
        if empty_car:
            state_manager.points[start_point]["flag"] = False
            state_manager.points[end_point]["flag"] = False

            state_manager.ready_start_list.discard(start_point)
            state_manager.ready_end_list.discard(end_point)

            state_manager.pair_mapping.pop(end_point, None)
            reset_pairs.append([start_point, end_point])
        else:
            remaining.append((start_point, end_point, empty_car))

    if remaining:
        state_manager.order_mapping[order_id] = remaining
    else:
        del state_manager.order_mapping[order_id]

    return {
        "success": True,
        "message": f"Empty pairs reset for orderId {order_id}",
        "orderId": order_id,
        "reset_pairs": reset_pairs,
    }
```

### Data flow Stage 3 (tóm tắt)
- External server -> `POST /delete-flag` -> API Server
- API Server -> cập nhật `StateManager.points[*]["flag"]`
- cập nhật `ready_*` và `order_mapping/pair_mapping` để tránh dispatch lặp

