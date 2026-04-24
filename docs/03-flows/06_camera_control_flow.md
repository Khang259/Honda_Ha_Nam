# Camera Control Flow (Enable/Disable)

## 1. Mô tả usecase

Cho phép bật/tắt camera theo `cameraId` qua API, đồng bộ với inference engine (pause/resume) để tiết kiệm GPU, và cung cấp snapshot trạng thái enable của tất cả cameras.

## 2. Actors

- **FastAPI route** (`/engine-control/toggle`): HTTP endpoint
- **CameraControlService**: service xử lý logic toggle
- **CameraManager**: quản lý `enabled` list (shared state)
- **InferenceEngine**: pause/resume inference pipeline
- **Client** (UI/automation): consumer của API

## 3. Flow

### 3.1. Endpoint Setup

```
api/app_factory.py
    └─> app.include_router(
            cameras_router,
            prefix="/engine-control",
            tags=["engine-control"]
        )

api/routes/cameras.py
    └─> @router.post("/toggle")
        └─> CameraControlService.toggle_camera(...)
```

### 3.2. Toggle Camera Flow

```
Client
    └─> POST /engine-control/toggle
        Body: {"cameraId": 101}

api/routes/cameras.py
    └─> toggle_camera(camera_id: int)
        ├─> camera_manager = api_state.camera_manager
        ├─> inference_engine = api_state.inference_engine
        │
        ├─> IF camera_manager is None:
        │   └─> return {"code": 1001, "message": "Runtime not started"}
        │
        └─> result = camera_control_service.toggle_camera(
                camera_manager,
                inference_engine,
                camera_id
            )
            └─> (chi tiết bên dưới)
```

### 3.3. CameraControlService.toggle_camera()

```
CameraControlService.toggle_camera(camera_manager, inference_engine, camera_id)
    ├─> index = find_camera_index(camera_manager, camera_id)
    │   └─> FOR i, cam in enumerate(cameras_config):
    │       └─> IF cam.get("cameraId", i) == camera_id:
    │           └─> return i
    │   └─> IF not found: return None
    │
    ├─> IF index is None:
    │   └─> return {"code": 1002, "message": "Camera not found"}
    │
    ├─> with camera_manager._enabled_lock:
    │   ├─> IF index out of bounds:
    │   │   └─> return {"code": 1003, "message": "Invalid index"}
    │   │
    │   └─> new_value = not camera_manager.enabled[index]
    │   └─> camera_manager.enabled[index] = new_value
    │
    ├─> enabled_count = sum(1 for e in camera_manager.enabled if e)
    │
    ├─> IF enabled_count > 0:
    │   └─> inference_engine.resume()
    │       └─> _paused.clear()
    │       └─> log "InferenceEngine resumed"
    │
    └─> ELSE:  # no camera enabled
        └─> inference_engine.pause()
            └─> _paused.set()
            └─> log "InferenceEngine paused"
    
    └─> return {
            "id": camera_id,
            "enabled": new_value
        }
```

### 3.4. Camera Thread Response

```
CameraProcessor.run() [Thread]
    └─> WHILE running:
        ├─> IF not _is_enabled():
        │   ├─> IF cap is not None:
        │   │   └─> cap.release()  # stop FFmpeg decoder
        │   │   └─> cap = None
        │   │
        │   └─> sleep(1) → CONTINUE
        │
        └─> ... (normal processing khi enabled)
```

→ Camera thread tự động stop/start decoder khi detect `enabled[index] = False/True`

### 3.5. InferenceEngine Response

```
InferenceEngine.run() [Thread]
    └─> WHILE running:
        ├─> IF _paused.is_set():
        │   └─> sleep(0.05) → CONTINUE  # skip inference
        │
        └─> ... (normal batching/inference)
```

→ Inference engine skip processing khi paused

### 3.6. Get Camera Status (Snapshot)

```
Client
    └─> GET /engine-control/cameras

api/routes/cameras.py
    └─> get_cameras_enable()
        └─> camera_manager.get_cameras_enable_snapshot()
            └─> with camera_manager._enabled_lock:
                └─> FOR i, cam in enumerate(cameras_config):
                    ├─> camera_id = cam.get("cameraId", i)
                    ├─> zone = camera_zones[i]
                    ├─> enabled = enabled[i]
                    │
                    └─> items.append({
                            "index": i,
                            "cameraId": camera_id,
                            "enabled": enabled,
                            "zone": zone
                        })
            
            └─> return items

Response:
[
  {
    "index": 0,
    "cameraId": 101,
    "enabled": true,
    "zone": "AE5"
  },
  {
    "index": 1,
    "cameraId": 102,
    "enabled": false,
    "zone": "AE5"
  }
]
```

## 4. Data flow

```
┌─────────────────────────────────────────────────────────┐
│                Client (UI/Automation)                   │
│  POST /engine-control/toggle {"cameraId": 101}         │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ HTTP POST
                     ▼
        ┌────────────────────────────┐
        │  FastAPI Route             │
        │  /engine-control/toggle    │
        └────────────┬───────────────┘
                     │
                     │ call CameraControlService
                     ▼
        ┌────────────────────────────────────────┐
        │  CameraControlService                  │
        │  .toggle_camera()                      │
        │                                        │
        │  (1) find_camera_index(camera_id)     │
        │      └─> search in cameras_config     │
        │                                        │
        │  (2) with _enabled_lock:              │
        │      └─> enabled[index] = !enabled    │
        │                                        │
        │  (3) enabled_count = sum(enabled)     │
        │                                        │
        │  (4) IF count > 0:                    │
        │      └─> inference_engine.resume()    │
        │      ELSE:                            │
        │      └─> inference_engine.pause()     │
        └────────────┬───────────────────────────┘
                     │
        ┌────────────┼────────────────────────┐
        │            │                        │
        ▼            ▼                        ▼
┌──────────────┐ ┌────────────┐  ┌──────────────────┐
│CameraProcessor│ │ Inference  │  │  Response        │
│  Thread       │ │ Engine     │  │  {"id": 101,     │
│               │ │            │  │   "enabled": true}│
│ _is_enabled() │ │ IF paused: │  └──────────────────┘
│ ├─> enabled[i]│ │   sleep()  │
│ │             │ │ ELSE:      │
│ └─> IF False: │ │   inference│
│     cap.release()│            │
│     sleep(1)  │ │            │
└───────────────┘ └────────────┘
```

## 5. Communication

### 5.1. HTTP API

**Toggle endpoint**:
```
POST /engine-control/toggle
Content-Type: application/json

{
  "cameraId": 101
}

Response:
{
  "id": 101,
  "enabled": true
}

Error responses:
{
  "code": 1001,
  "message": "Camera manager not initialized"
}
{
  "code": 1002,
  "message": "Không tìm thấy camera với cameraId 101"
}
```

**Snapshot endpoint**:
```
GET /engine-control/cameras

Response:
[
  {
    "index": 0,
    "cameraId": 101,
    "enabled": true,
    "zone": "AE5"
  },
  ...
]
```

### 5.2. Internal Communication

**Shared state**:
- `CameraManager.enabled`: `list[bool]` - per camera enable flag
- Protected by `CameraManager._enabled_lock` (threading.Lock)

**Thread signaling**:
- Không có explicit signal (event/condition)
- Camera threads poll `enabled[index]` mỗi vòng lặp
- InferenceEngine poll `_paused.is_set()` mỗi vòng lặp

**Race condition protection**:
- Lock `_enabled_lock` khi read/write `enabled` list
- Atomic toggle: read old → write new trong 1 lock scope

## 6. Error points

### 6.1. Camera not found (cameraId không tồn tại)

**Triệu chứng**: API return code 1002

**Nguyên nhân**:
- `cameraId` không match với cameras trong config
- Config không sync với DB

**Debug**:
- GET `/engine-control/cameras` để xem list cameras
- Check MongoDB `node_id` collection

### 6.2. Index out of bounds

**Triệu chứng**: API return code 1003

**Nguyên nhân**:
- `index` tính được nhưng vượt quá `len(enabled)`
- Lỗi logic trong `find_camera_index()`

**Không nên xảy ra**: nếu cameras_config và enabled sync

### 6.3. Runtime not started

**Triệu chứng**: API return code 1001

**Nguyên nhân**:
- `api_state.camera_manager` is None
- Gọi API trước khi `RuntimeService.start()` complete

**Xử lý**:
- Check `/runtime/status` trước khi toggle
- Retry với backoff

### 6.4. Toggle không có hiệu ứng (camera vẫn chạy)

**Triệu chứng**: toggle API success nhưng camera vẫn stream

**Nguyên nhân**:
- Camera thread đọc sai index (`self.camera_index`)
- Race condition trong `_is_enabled()`

**Debug**:
- Log `camera_index` và `len(enabled_ref)` trong CameraProcessor
- Verify index mapping

### 6.5. Inference không pause khi tất cả cameras disabled

**Triệu chứng**: GPU vẫn busy dù không có camera

**Nguyên nhân**:
- `enabled_count` tính sai
- `inference_engine.pause()` không được gọi

**Debug**:
- Log `enabled_count` sau mỗi toggle
- Check `inference_engine._paused.is_set()` status

### 6.6. Camera không tự động resume sau toggle ON

**Triệu chứng**: toggle ON nhưng không có frame

**Nguyên nhân**:
- Camera thread sleep(1) → delay 1s trước khi check lại
- FFmpeg decoder mất thời gian reconnect (2-10s)

**Không phải bug**: expected behavior, chờ camera reconnect

### 6.7. Concurrent toggle requests race

**Triệu chứng**: 2 requests cùng toggle → state không đúng

**Nguyên nhân**:
- Không có request-level lock
- 2 requests đọc cùng 1 `enabled[index]` rồi cùng toggle

**Xử lý hiện tại**:
- `_enabled_lock` protect read/write
- Race có thể xảy ra ở logic layer (find_camera_index → toggle)

**Cải tiến**: thêm service-level lock hoặc dùng atomic compare-and-swap

## 7. Notes + cải tiến

### 7.1. Hiện trạng

- **Toggle only**: không có enable/disable explicit (phải check state trước)
- **No batch toggle**: toggle từng camera một (không toggle theo zone/group)
- **No schedule**: không thể schedule enable/disable theo giờ
- **No audit log**: không track ai toggle camera nào lúc nào

### 7.2. Cải tiến đề xuất

#### a) Explicit enable/disable endpoints

```python
@router.post("/enable")
def enable_camera(camera_id: int):
    # Force enable (idempotent)
    ...

@router.post("/disable")
def disable_camera(camera_id: int):
    # Force disable (idempotent)
    ...

@router.post("/toggle")
def toggle_camera(camera_id: int):
    # Toggle current state
    ...
```

→ Client không cần check state trước

#### b) Batch operations

```python
@router.post("/enable-zone")
def enable_zone(zone: str):
    camera_manager.set_zone_enabled(zone, on=True)
    # Enable tất cả cameras trong zone
    return {"zone": zone, "cameras_enabled": [...]}

@router.post("/enable-all")
def enable_all():
    camera_manager.start_all_cameras()
    return {"total_enabled": len(camera_manager.enabled)}

@router.post("/disable-all")
def disable_all():
    camera_manager.stop_all_cameras()
    inference_engine.pause()
    return {"total_disabled": len(camera_manager.enabled)}
```

#### c) Schedule enable/disable

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@router.post("/schedule")
def schedule_toggle(
    camera_id: int,
    action: str,  # "enable" | "disable"
    cron: str     # "0 8 * * *" (8 AM daily)
):
    def job():
        if action == "enable":
            enable_camera(camera_id)
        else:
            disable_camera(camera_id)
    
    scheduler.add_job(job, CronTrigger.from_crontab(cron))
    return {"scheduled": True, "cron": cron}
```

#### d) Audit log

```python
class CameraControlAudit:
    def __init__(self, db_client):
        self.db = db_client
        self.collection = db["camera_control_audit"]
    
    async def log_action(
        self,
        camera_id: int,
        action: str,
        user: str,
        result: dict
    ):
        await self.collection.insert_one({
            "camera_id": camera_id,
            "action": action,
            "user": user,
            "timestamp": datetime.now(),
            "result": result
        })

# In route
@router.post("/toggle")
async def toggle_camera(
    camera_id: int,
    user: str = Depends(get_current_user)
):
    result = camera_control_service.toggle_camera(...)
    await audit.log_action(camera_id, "toggle", user, result)
    return result
```

Query audit:
```
GET /engine-control/audit?camera_id=101
[
  {
    "camera_id": 101,
    "action": "toggle",
    "user": "admin",
    "timestamp": "2026-04-23T10:30:00Z",
    "result": {"enabled": true}
  }
]
```

#### e) Camera health check trước khi enable

```python
def enable_camera_safe(camera_id: int):
    # Pre-check camera URL reachable
    camera = find_camera_config(camera_id)
    rtsp_url = camera["url"]
    
    if not check_rtsp_reachable(rtsp_url, timeout=5):
        return {
            "code": 2001,
            "message": "Camera URL không reach được"
        }
    
    # Proceed enable
    return enable_camera(camera_id)
```

#### f) Graceful disable (flush pending detections)

```python
def disable_camera_graceful(camera_id: int):
    # Mark camera as "disabling"
    camera_manager.set_camera_disabling(camera_id)
    
    # Wait for inference result queue empty
    timeout = 5.0
    start = time.time()
    while time.time() - start < timeout:
        if camera_manager.is_result_queue_empty(camera_id):
            break
        time.sleep(0.1)
    
    # Actually disable
    return disable_camera(camera_id)
```

#### g) Camera group management

```python
# Config
camera_groups = {
    "entrance": [101, 102],
    "exit": [103, 104],
    "parking": [105, 106, 107]
}

@router.post("/enable-group")
def enable_group(group_name: str):
    camera_ids = camera_groups.get(group_name, [])
    results = []
    for cam_id in camera_ids:
        result = enable_camera(cam_id)
        results.append(result)
    
    return {
        "group": group_name,
        "results": results
    }
```

#### h) WebSocket notifications

```python
from fastapi import WebSocket

active_connections = []

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        active_connections.remove(websocket)

# In toggle_camera()
async def notify_camera_state_change(camera_id, enabled):
    message = {
        "type": "camera_state_changed",
        "camera_id": camera_id,
        "enabled": enabled,
        "timestamp": time.time()
    }
    
    for ws in active_connections:
        await ws.send_json(message)
```

Client:
```javascript
const ws = new WebSocket('ws://host/engine-control/ws');
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'camera_state_changed') {
        updateUI(data.camera_id, data.enabled);
    }
};
```

#### i) Dry-run mode

```python
@router.post("/toggle")
def toggle_camera(camera_id: int, dry_run: bool = False):
    if dry_run:
        # Simulate toggle, return what would happen
        index = find_camera_index(camera_id)
        current_state = camera_manager.enabled[index]
        new_state = not current_state
        
        return {
            "dry_run": True,
            "camera_id": camera_id,
            "current_enabled": current_state,
            "would_enable": new_state,
            "inference_would_pause": new_state == False and sum(enabled) == 1
        }
    
    # Actually toggle
    return toggle_camera_impl(camera_id)
```

### 7.3. Performance considerations

**Lock contention**:
- `_enabled_lock` held briefly (< 1ms)
- No contention observed với < 100 cameras

**Toggle latency**:
- API response: < 10ms
- Camera thread detect: 0-1s (poll interval)
- FFmpeg reconnect: 2-10s (RTSP handshake)

**Inference pause/resume**:
- Pause: immediate (set event)
- Resume: immediate (clear event)
- No warm-up needed

### 7.4. Testing checklist

- [ ] Toggle single camera (enable → disable → enable)
- [ ] Toggle tất cả cameras (verify inference pause)
- [ ] Toggle concurrent requests (2 clients cùng toggle)
- [ ] Toggle camera không tồn tại (error handling)
- [ ] Toggle khi runtime chưa start (error handling)
- [ ] Get cameras snapshot (verify state sync)
- [ ] Camera auto-reconnect sau enable
- [ ] Inference resume khi có ít nhất 1 camera enabled

### 7.5. Monitoring metrics

Key metrics cần track:
- [ ] Camera enable/disable events (count, timestamp)
- [ ] Toggle request rate (req/s)
- [ ] Toggle latency (API → camera actual stop)
- [ ] Failed toggle rate (error 1002/1003)
- [ ] Camera uptime per enable session
- [ ] Inference pause/resume events

Expose qua API:
```
GET /engine-control/metrics
{
  "total_toggles": 123,
  "cameras_enabled": 8,
  "cameras_disabled": 2,
  "inference_paused": false,
  "avg_toggle_latency_ms": 5.2
}
```

### 7.6. UI integration example

```javascript
// React component
function CameraControl({ cameraId }) {
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(false);

  const toggle = async () => {
    setLoading(true);
    try {
      const resp = await fetch('/engine-control/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cameraId })
      });
      const data = await resp.json();
      setEnabled(data.enabled);
    } catch (error) {
      console.error('Toggle failed:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button onClick={toggle} disabled={loading}>
      {enabled ? 'Disable' : 'Enable'} Camera {cameraId}
    </button>
  );
}
```
