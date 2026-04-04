# api/api_server.py - API endpoints (Stage 2: detections + state read)

Trong kiến trúc hiện tại, API Server (FastAPI) là điểm nhận detection từ AI Worker và là nguồn để UI poll state.

## Endpoints và function chính

### `set_state_manager(manager)` (wiring)

```python
def set_state_manager(manager):
    global state_manager
    state_manager = manager
    logger.info("State manager attached to API server")
```

### `post_detection(payload: DetectionPayload)` -> `StateManager.get_state_nodes(...)`

```python
@app.post("/detections")
async def post_detection(payload: DetectionPayload) -> Dict[str, Any]:
    if not state_manager:
        return {"error": "State manager not initialized", "success": False}

    state_manager.get_state_nodes(payload.node_id, payload.detected)
    return {"success": True, "message": "Detection updated"}
```

### `get_state_points()` -> UI lấy state theo từng `node_id`

```python
@app.get("/state/points")
async def get_state_points() -> Dict[str, Any]:
    if not state_manager:
        return {"error": "State manager not initialized", "success": False}

    points_dict = {}
    for node_id, data in state_manager.points.items():
        points_dict[node_id] = {
            "state": data["state"],
            "time": data["time"],
            "flag": data["flag"]
        }

    return {"success": True, "points": points_dict}
```

### `get_ready_lists()` -> UI đọc `ready_start_list`/`ready_end_list`

```python
@app.get("/state/ready-lists")
async def get_ready_lists() -> Dict[str, Any]:
    if not state_manager:
        return {"error": "State manager not initialized", "success": False}

    return {
        "success": True,
        "ready_start_list": list(state_manager.ready_start_list),
        "ready_end_list": list(state_manager.ready_end_list)
    }
```

## Data flow Stage 2 (tóm tắt)
- `worker/APIClient.post_detection()` -> POST `/detections`
- API Server gọi `StateManager.get_state_nodes()`
- `PairManager._run()` đọc `ready_*` từ `StateManager` để ghép pair và dispatch sang ICS
- UI poll `/state/points` và `/state/ready-lists` qua `StateProxy`

## Xem thêm
- `POST /delete-flag` nằm ở Stage 3 (reset flags).

