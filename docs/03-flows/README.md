# Flows - Luồng hoạt động hệ thống

> **Đọc phần này nếu**: Bạn cần hiểu hệ thống chạy như thế nào trong từng use-case cụ thể.

## Nội dung

Mỗi flow document bao gồm 7 phần:
1. Mô tả usecase
2. Actors tham gia
3. Flow chi tiết (step-by-step)
4. Data flow (ASCII diagram)
5. Communication protocols
6. Error points và xử lý
7. Notes + cải tiến đề xuất

---

### 🔄 [01. Worker Registration & Heartbeat Flow](./01_worker_registration_heartbeat_flow.md)
Worker tự đăng ký, nhận camera assignment, heartbeat để báo hiệu "còn sống", và auto-rebalance khi topology thay đổi.

**Key concepts**: Worker registry, fencing tokens, rebalance logic

---

### 📹 [02. Camera Processing Flow](./02_camera_processing_flow.md)
Thread per camera: decode RTSP (FFmpeg GPU) → push frames → nhận detections → update state theo ROI.

**Key concepts**: GPU decode, shared inference queue, ROI detection

---

### 🧠 [03. Inference Engine Flow](./03_inference_engine_flow.md)
Tập trung inference: gom batch frames → CUDA streams async → distribute results về cameras.

**Key concepts**: Batching, CUDA streams pipeline, result queues

---

### 🔗 [04. Pair Management Flow](./04_pair_management_flow.md)
Theo dõi state start/end → ghép cặp theo logic nghiệp vụ → POST webhook ICS.

**Key concepts**: State timer, ready lists, FIFO pairing, double tasks

---

### 📺 [05. Streaming API Flow](./05_streaming_api_flow.md)
HTTP endpoint stream video MJPEG với overlay detections + ROIs.

**Key concepts**: MJPEG protocol, frame overlay, MongoDB ROI query

---

### 🎛️ [06. Camera Control Flow](./06_camera_control_flow.md)
Bật/tắt camera qua API → đồng bộ inference pause/resume.

**Key concepts**: Toggle API, shared state lock, camera thread response

---

## Flow Dependencies (Phụ thuộc)

```
Startup Flow:
  RuntimeService.start()
    ├─> [01] WorkerManager (async task)
    ├─> [04] PairManager (thread)
    ├─> [03] InferenceEngine (thread)
    └─> [02] CameraManager (N threads)

Runtime Flow:
  [01] Worker heartbeat → rebalance
  [02] Cameras → frames → [03] Inference
  [03] Detections → [02] Camera → [04] State
  [04] State → pairing → ICS webhook

API Flow:
  [05] Streaming ← latest_frames + detections
  [06] Control → toggle cameras → pause/resume
```

## Concurrency Summary

| Component | Type | Count | Lifespan |
|-----------|------|-------|----------|
| WorkerManager heartbeat | Async Task | 1 | Toàn app |
| CameraProcessor | Thread | N | Per camera |
| GPUVideoDecoder | Thread | N | Per camera |
| InferenceEngine | Thread | 1 | Toàn app |
| PairManager | Thread | 1 | Toàn app |

**Total threads**: 2N + 3 (N = số cameras)

---

[⬅️ Về trang chủ](../README.md) | [➡️ Tiếp: Features](../04-features/)
