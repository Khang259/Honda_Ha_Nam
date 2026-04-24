# System Overview - Tổng quan hệ thống

> **Đọc file này nếu**: Bạn mới tham gia team hoặc cần hiểu nhanh hệ thống này là gì, dùng để làm gì.

## Sản phẩm này là gì?

**Honda AI Monitoring** là một **backend service** chạy realtime (gần thời gian thực) cho bài toán:
- Ingest video từ nhiều camera (RTSP)
- Chạy AI inference (object detection) theo cơ chế batch/GPU
- Quản lý state machine theo ROI (Region of Interest)
- Cung cấp API cho hệ sinh thái (UI/worker/monitoring)

## Giải quyết vấn đề gì?

### Vấn đề 1: Scale nhiều camera mà không tốn nhiều GPU
**Challenge**: Load 1 model YOLO per camera → 10 cameras = 10 models trên GPU → out of memory

**Giải pháp**: 
- 1 `InferenceEngine` dùng chung model
- Gom batch frames từ nhiều cameras
- Chạy inference 1 lần cho batch → phân phối kết quả về từng camera

→ **Kết quả**: 10 cameras chỉ cần 1 model instance, tăng throughput GPU

### Vấn đề 2: Latency/overhead khi inference per frame
**Challenge**: Mỗi camera 24 FPS → 24 lần inference/s → overhead CUDA kernel launch

**Giải pháp**:
- Batching + CUDA streams
- Overlap data transfer + compute
- Adaptive timeout để gom batch optimal

→ **Kết quả**: Giảm latency, tăng throughput (FPS tổng)

### Vấn đề 3: Chuẩn hoá nghiệp vụ theo điểm (node/ROI)
**Challenge**: Mỗi camera có logic khác nhau để detect "sự kiện" → khó maintain

**Giải pháp**:
- State manager theo "start point" / "end point"
- Timer 30s để xác định "ready"
- Pairing logic tập trung trong `PairManager`

→ **Kết quả**: Logic nghiệp vụ tách khỏi camera processing, dễ config/test

## Dùng trong context nào?

### Context 1: Distributed worker system
- Nhiều workers (servers) chạy song song
- Mỗi worker đăng ký vào registry (MongoDB)
- Central coordinator gán cameras cho workers
- Worker heartbeat để báo hiệu "còn sống"
- Auto-rebalance khi worker join/die

### Context 2: Manufacturing/Logistics monitoring
- Cameras đặt tại các điểm quan trọng (cổng vào/ra, kho, ...)
- Detect objects (xe, người, ...) vào/ra ROI
- Trigger actions theo logic nghiệp vụ (gọi ICS/webhook)
- Snapshot/log sự kiện để audit

### Context 3: Realtime monitoring/control
- UI/dashboard theo dõi status cameras
- Bật/tắt cameras theo khu vực/ca làm việc
- Xem stream video với overlay detections + ROI
- Alert khi có anomaly (camera offline, inference lag, ...)

## Use-cases cụ thể

### UC1: Giám sát realtime
**Actor**: Operator (vận hành)

**Flow**:
1. Mở dashboard, chọn camera
2. Xem MJPEG stream với overlay detections + ROI
3. Verify ROI config đúng (visual check)
4. Adjust confidence threshold nếu cần

**Lợi ích**: Debug nhanh, không cần SSH vào server

### UC2: Bật/tắt camera theo khu vực
**Actor**: Supervisor (quản lý)

**Flow**:
1. POST `/engine-control/toggle` với `cameraId`
2. Camera thread tự động stop/start decoder
3. Inference engine pause nếu không còn camera nào

**Lợi ích**: Tiết kiệm GPU, giảm network bandwidth

### UC3: Distributed assignment
**Actor**: System (auto)

**Flow**:
1. Worker 1 start → claim 10 cameras
2. Worker 2 join → rebalance → mỗi worker 5 cameras
3. Worker 1 die → Worker 2 claim thêm 5 cameras

**Lợi ích**: High availability, no manual intervention

### UC4: Tối ưu throughput GPU
**Actor**: DevOps (optimize)

**Flow**:
1. Monitor batch size average (mục tiêu: gần `max_batch_size`)
2. Tune `batch_timeout` để balance latency/throughput
3. Monitor GPU utilization (mục tiêu: >80%)

**Lợi ích**: Maximize ROI trên GPU hardware

## Mô tả ngắn gọn (Elevator Pitch)

> "Nhận frame từ N cameras → batch inference trên GPU → cập nhật state/logic start-end → cung cấp API điều khiển & streaming"

Hoặc:

> "Một runtime service để scale AI inference cho nhiều cameras, với distributed worker support và business logic theo ROI"

## Tech stack chi tiết

### Backend
- **FastAPI** (0.115.0): REST API framework
- **Uvicorn** (0.30.6): ASGI server
- **Pydantic** (2.9.2): validation/settings

### Database
- **MongoDB** (via Motor 3.6.0): camera configs, worker registry, validate pairs
- **PyMongo** (4.9.2): sync operations

### AI/Inference
- **Ultralytics YOLO** (8.4.7): object detection model
- **PyTorch** (2.5.1+cu121): deep learning framework
- **TensorRT** (10.15.1.29): GPU inference optimization
- **ONNX/ONNXRuntime-GPU** (1.23.2): model interchange

### Video Processing
- **OpenCV** (4.11.0): frame manipulation, encoding
- **PyAV** (16.1.0): video container handling
- **FFmpeg** (via subprocess): RTSP decode với NVDEC (GPU)

### Scheduling/Utils
- **APScheduler** (3.10.4): scheduled tasks
- **Loguru** (0.7.2): logging framework
- **Redis** (7.1.0): (optional) caching/pub-sub

### Testing
- **pytest** (8.3.3): unit/integration tests
- **pytest-asyncio** (0.24.0): async test support

## Kiến trúc tổng quan (high-level)

```
┌────────────────────────────────────────────────────────┐
│                    MongoDB                             │
│  - worker_registry (workers + heartbeat)               │
│  - node_id (cameras + ROI configs)                     │
│  - validate_pairs (nghiệp vụ pairing)                  │
└────────────────────┬───────────────────────────────────┘
                     │
                     │ connect + load configs
                     ▼
┌────────────────────────────────────────────────────────┐
│              FastAPI (Uvicorn) - Main Process          │
│  - Routes: health, runtime, cameras, streaming, ...    │
│  - Lifecycle: connect DB, start runtime                │
└────────────────────┬───────────────────────────────────┘
                     │
                     │ start components
                     ▼
        ┌────────────┴───────────────┐
        │                            │
        ▼                            ▼
┌───────────────┐          ┌──────────────────┐
│ WorkerManager │          │  Core Runtime    │
│ (async task)  │          │  (threads)       │
│ - heartbeat   │          │  - CameraManager │
│ - rebalance   │          │  - InferenceEngine│
└───────────────┘          │  - PairManager   │
                           │  - StateManager  │
                           └──────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌──────────┐    ┌──────────┐   ┌──────────┐
            │ Camera 1 │    │ Camera 2 │   │ Camera N │
            │ (thread) │    │ (thread) │   │ (thread) │
            └──────────┘    └──────────┘   └──────────┘
                    │               │               │
                    └───────────────┼───────────────┘
                                    │
                            shared inference queue
                                    ▼
                            ┌──────────────┐
                            │ YOLO Model   │
                            │ (GPU batch)  │
                            └──────────────┘
```

## Luồng dữ liệu tổng quan

1. **Startup**: FastAPI lifespan connect MongoDB → load configs → start runtime
2. **Worker**: heartbeat loop (async) → update registry → detect rebalance
3. **Camera**: N threads đọc RTSP → decode (GPU) → push frames vào shared queue
4. **Inference**: 1 thread gom batch → YOLO inference (GPU) → distribute detections
5. **State**: camera threads nhận detections → check ROI → update state manager
6. **Pair**: 1 thread poll state → ghép cặp start/end → POST webhook ICS
7. **API**: routes serve requests (streaming, control, status, ...)

## Các con số quan trọng

- **Cameras**: 10-50 cameras per worker (tuỳ GPU)
- **Inference batch**: 24 frames (RTX 3090), 16 frames (RTX 3060)
- **Latency**: ~50-100ms (từ frame capture → detection result)
- **Throughput**: ~200-400 FPS tổng (10 cameras @ 20-40 FPS)
- **GPU utilization**: 80-95% (optimal)
- **Memory**: ~1GB per model + ~1MB per camera frame buffer

## Next steps

- **Hiểu kiến trúc**: [Architecture docs](../02-architecture/)
- **Hiểu từng flow**: [Flows docs](../03-flows/)
- **Setup hệ thống**: [Quick Start](./quick-start.md)
- **Vận hành**: [Runbook](../08-runbook/)

---

[⬅️ Về Overview](./README.md) | [🏠 Trang chính](../README.md)
