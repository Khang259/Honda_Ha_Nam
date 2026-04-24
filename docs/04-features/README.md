# Features - Chức năng hệ thống

> **Đọc phần này nếu**: Bạn cần hiểu từng chức năng cụ thể làm gì, input/output là gì, và cách sử dụng.

## Core Features

### 🎥 [Camera Management](./camera-management.md)
Quản lý nhiều cameras: enable/disable, health check, reconnect logic.

**Capabilities**:
- Add/remove cameras động
- Toggle enable/disable per camera
- Monitor FPS, drop rate, reconnect count
- Zone-based control

---

### 🧠 [AI Inference](./ai-inference.md)
Chạy YOLO inference tập trung với batching + GPU optimization.

**Capabilities**:
- Batch processing (adaptive timeout)
- CUDA streams async
- Model hot-reload
- Pause/resume (tiết kiệm GPU)

---

### 📍 [ROI Detection](./roi-detection.md)
Detect objects trong ROI và trigger state changes.

**Capabilities**:
- Multiple ROIs per camera
- IoU calculation (GPU-accelerated)
- State timer (30s threshold)
- Visual debug (streaming overlay)

---

### 🔗 [Pair Management](./pair-management.md)
Ghép cặp start/end points theo business logic.

**Capabilities**:
- FIFO pairing
- Double task (normal + empty)
- Validate pairs từ DB
- Retry failed webhooks

---

### 📺 [Video Streaming](./video-streaming.md)
Stream video realtime với detection overlays.

**Capabilities**:
- MJPEG protocol
- Detections + ROI overlay
- Multiple concurrent clients
- Quality/FPS tuning

---

### 🌐 [Distributed Workers](./distributed-workers.md)
Nhiều workers chia sẻ cameras, auto-rebalance.

**Capabilities**:
- Worker registration/heartbeat
- Camera assignment (round-robin)
- Fencing tokens (split-brain prevention)
- Graceful failover

---

### 📊 [Monitoring & Health](./monitoring-health.md)
Theo dõi health của từng component.

**Capabilities**:
- Runtime status API
- Per-camera metrics
- Inference throughput
- Worker topology

---

## Feature Matrix

| Feature | API Endpoint | Config | Dependencies |
|---------|-------------|--------|--------------|
| Camera Management | `/engine-control/*` | MongoDB node_id | CameraManager |
| AI Inference | Internal | config.py | InferenceEngine, GPU |
| ROI Detection | Internal | MongoDB rois | StateManager |
| Pair Management | Internal | MongoDB validate_pairs | PairManager, ICS |
| Video Streaming | `/streaming/*` | - | CameraManager |
| Distributed Workers | Internal | MongoDB worker_registry | WorkerManager |
| Monitoring | `/runtime/*`, `/health` | - | All components |

---

[⬅️ Về trang chủ](../README.md) | [➡️ Tiếp: API](../05-api/)
