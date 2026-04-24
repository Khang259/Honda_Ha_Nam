# API Documentation

> **Đọc phần này nếu**: Bạn đang tích hợp service khác hoặc frontend với hệ thống này.

## Quick Start

### Base URL
```
http://<AI_SERVER_HOST>:<AI_SERVER_PORT>
```

### Swagger UI
```
http://<AI_SERVER_HOST>:<AI_SERVER_PORT>/docs
```

### ReDoc
```
http://<AI_SERVER_HOST>:<AI_SERVER_PORT>/redoc
```

---

## API Groups

### 🏥 [Health & Status](./health-status.md)
Check service health và runtime status.

**Endpoints**:
- `GET /health` - Health check
- `GET /runtime/status` - Runtime status chi tiết

---

### 🎛️ [Camera Control](./camera-control.md)
Điều khiển cameras (enable/disable, snapshot).

**Endpoints**:
- `POST /engine-control/toggle` - Toggle camera
- `GET /engine-control/cameras` - Lấy danh sách cameras
- `POST /engine-control/enable-zone` - Enable theo zone

---

### 📺 [Streaming](./streaming.md)
Stream video với detection overlays.

**Endpoints**:
- `GET /streaming/video/{cam_id}` - MJPEG stream
- `GET /streaming/snapshot/{cam_id}` - Single frame snapshot

---

### 📊 [State & Detections](./state-detections.md)
Lấy state và detection results.

**Endpoints**:
- `GET /state/points` - State của tất cả nodes
- `GET /state/ready` - Ready lists (start/end)
- `GET /detections/{cam_id}` - Latest detections

---

### 🔗 [Pairs](./pairs.md)
Xem pairs history và failed pairs.

**Endpoints**:
- `GET /pairs/history` - Pair history
- `GET /pairs/failed` - Failed pairs cần retry
- `POST /pairs/failed/{order_id}/retry` - Retry failed pair

---

### 👷 [Worker Management](./worker-management.md)
Quản lý workers (chỉ dùng internal/admin).

**Endpoints**:
- `GET /workers` - Danh sách workers
- `GET /workers/{worker_id}` - Worker detail
- `POST /workers/{worker_id}/rebalance` - Force rebalance

---

## Authentication

**Hiện tại**: Không có authentication (development mode)

**Production**: Sẽ thêm JWT authentication
```
Authorization: Bearer <token>
```

---

## Error Responses

### Standard Error Format
```json
{
  "code": 1001,
  "message": "Camera manager not initialized",
  "detail": "Runtime not started yet"
}
```

### Common Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| 1001 | Runtime not started | Wait hoặc check logs |
| 1002 | Camera not found | Verify cameraId |
| 1003 | Invalid index | Bug - report |
| 2001 | Camera unreachable | Check network/camera |
| 5000 | Internal error | Check logs |

---

## Rate Limiting

**Hiện tại**: Không có rate limiting

**Khuyến nghị production**:
- Camera control: 10 req/min per IP
- Streaming: 5 concurrent streams per IP
- State queries: 100 req/min per IP

---

## Client Examples

### Python
```python
import requests

# Health check
resp = requests.get("http://localhost:8000/health")
print(resp.json())  # {"status": "ok"}

# Toggle camera
resp = requests.post(
    "http://localhost:8000/engine-control/toggle",
    json={"cameraId": 101}
)
print(resp.json())  # {"id": 101, "enabled": true}
```

### JavaScript
```javascript
// Health check
const resp = await fetch('http://localhost:8000/health');
const data = await resp.json();
console.log(data);  // {status: "ok"}

// Toggle camera
const resp = await fetch('http://localhost:8000/engine-control/toggle', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({cameraId: 101})
});
const data = await resp.json();
console.log(data);  // {id: 101, enabled: true}
```

### cURL
```bash
# Health check
curl http://localhost:8000/health

# Toggle camera
curl -X POST http://localhost:8000/engine-control/toggle \
  -H 'Content-Type: application/json' \
  -d '{"cameraId": 101}'
```

---

## WebSocket (Future)

**Planned**: Real-time notifications
```javascript
const ws = new WebSocket('ws://localhost:8000/ws');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'camera_state_changed') {
    console.log(`Camera ${data.camera_id} is now ${data.enabled}`);
  }
};
```

---

[⬅️ Về trang chủ](../README.md) | [➡️ Tiếp: Technical](../06-technical/)
