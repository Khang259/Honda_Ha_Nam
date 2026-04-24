# Glossary - Thuật ngữ và khái niệm

> Danh sách các thuật ngữ quan trọng trong hệ thống Honda AI Monitoring.

## A

### API
Application Programming Interface - giao diện lập trình ứng dụng. Hệ thống expose FastAPI endpoints cho client.

### Async/Await
Python async/await syntax cho asynchronous programming. Dùng cho I/O operations (MongoDB, HTTP).

## B

### Batch / Batching
Gom nhiều frames thành 1 batch để inference cùng lúc → tăng throughput GPU.

### Bounding Box
Hình chữ nhật bao quanh object được detect (format: x, y, w, h).

## C

### Camera Assignment
Gán cameras cho workers trong distributed system. Sử dụng fencing tokens để tránh conflict.

### CUDA
Compute Unified Device Architecture - platform của NVIDIA cho GPU computing.

### CUDA Stream
Mechanism cho async GPU operations. Cho phép overlap data transfer + compute.

## D

### Detection
Kết quả inference từ YOLO model - list các objects với bounding box + confidence + class.

### Distributed System
Hệ thống nhiều workers chạy song song, chia sẻ workload (cameras).

## E

### Empty Car
Xe không chở hàng. Logic đặc biệt trong pairing (pending queue + timeout 15s).

### End Point
Điểm kết thúc trong ROI. State = False khi xe rời khỏi (ready sau 30s).

## F

### Fencing Token
Monotonic counter để ngăn split-brain trong distributed assignment. Token tăng mỗi lần claim camera.

### FPS (Frames Per Second)
Số frame xử lý mỗi giây. Target FPS camera: 10-30, throughput inference: 200-400 (tổng).

## G

### GPU Decode
Decode video bằng GPU (FFmpeg NVDEC) thay vì CPU → giảm CPU load.

## H

### Heartbeat
Signal định kỳ từ worker để báo "còn sống". Default: 10s interval, 30s timeout.

## I

### ICS
Integrated Control System - hệ thống backend nhận webhook khi có pair ready.

### Inference
Quá trình chạy model AI để predict/detect objects từ frame.

### Inference Engine
Component tập trung xử lý inference cho tất cả cameras (shared queue + batching).

## M

### MJPEG
Motion JPEG - format streaming video đơn giản (multipart HTTP response).

### MongoDB
NoSQL database lưu configs (cameras, ROI, validate_pairs, worker_registry).

## N

### Node / Node ID
Điểm trong hệ thống (start_* hoặc end_*). Mapping với ROI của camera.

### NVDEC
NVIDIA Video Decoder - hardware decoder trên GPU cho video (H264/H265).

## O

### Order ID
Unique identifier cho task order gửi lên ICS. Format: `{timestamp}_{start}_{end}`.

## P

### Pair / Pairing
Ghép cặp start point + end point để tạo task order. Logic: FIFO + validate_pairs.

### Paused
Trạng thái inference engine khi không có camera nào enabled → skip processing.

## Q

### Queue
FIFO data structure. Hệ thống dùng nhiều queues:
- `shared_queue`: frames từ cameras → inference
- `result_queue`: detections từ inference → camera (per camera)

## R

### Ready List
Set các nodes đã đủ điều kiện (timer > 30s) để pairing:
- `ready_start_list`: start points ready
- `ready_end_list`: end points ready

### Rebalance
Tính toán lại camera assignment khi worker count thay đổi (join/die).

### ROI (Region of Interest)
Vùng quan tâm trong frame. Format: [x, y, width, height]. Dùng để check object có trong vùng không.

### RTSP
Real Time Streaming Protocol - protocol stream video từ camera IP.

## S

### Shared Queue
Queue chung nhận frames từ tất cả camera threads. InferenceEngine consume từ queue này.

### Snapshot
Ảnh chụp frame tại thời điểm có event (optional, config via `ENABLE_SNAPSHOTS`).

### Start Point
Điểm bắt đầu trong ROI. State = True khi xe vào (ready sau 30s).

### State Manager
Component quản lý state/timer của các nodes và ready lists.

### Streaming
Phát video realtime qua HTTP (MJPEG). Có overlay detections + ROI.

## T

### TensorRT
NVIDIA inference optimizer. Convert YOLO model → TensorRT engine → faster inference.

### Thread
Luồng thực thi độc lập. Hệ thống có nhiều threads:
- N camera threads (per camera)
- 1 inference thread
- 1 pair manager thread
- N decoder threads (internal FFmpeg)

### Throughput
Lượng data xử lý per unit time. Ví dụ: 400 FPS (tổng frames inference per second).

### Toggle
Bật/tắt camera. API: POST `/engine-control/toggle`.

## V

### Validate Pairs
List các cặp (start, end) hợp lệ từ DB. Dùng để filter pairing logic.

## W

### Worker
Instance của service chạy trên 1 server. Nhiều workers cùng chạy (distributed).

### Worker Manager
Component quản lý lifecycle worker: register, heartbeat, assignment, rebalance.

### Worker Registry
MongoDB collection lưu danh sách workers + last_heartbeat + camera_count.

## Y

### YOLO
You Only Look Once - family các model object detection. Hệ thống dùng Ultralytics YOLO v8.

---

## Acronyms (Viết tắt)

| Acronym | Full Name | Nghĩa |
|---------|-----------|-------|
| API | Application Programming Interface | Giao diện lập trình |
| CRUD | Create, Read, Update, Delete | Các thao tác cơ bản DB |
| CUDA | Compute Unified Device Architecture | Platform GPU NVIDIA |
| DRY | Don't Repeat Yourself | Nguyên tắc không lặp code |
| FFmpeg | Fast Forward MPEG | Tool xử lý video/audio |
| FPS | Frames Per Second | Số frame/giây |
| GPU | Graphics Processing Unit | Bộ xử lý đồ hoạ |
| HTTP | Hypertext Transfer Protocol | Giao thức web |
| ICS | Integrated Control System | Hệ thống điều khiển |
| MJPEG | Motion JPEG | Format streaming |
| NVDEC | NVIDIA Video Decoder | Decoder GPU |
| ONNX | Open Neural Network Exchange | Format model AI |
| REST | Representational State Transfer | Kiến trúc API |
| ROI | Region of Interest | Vùng quan tâm |
| RTSP | Real Time Streaming Protocol | Protocol camera |
| TensorRT | NVIDIA TensorRT | Optimizer inference |
| YOLO | You Only Look Once | Model detection |

---

## Thuật ngữ nghiệp vụ (Business Terms)

### Double Task
Lệnh đôi: 1 task normal + 1 task empty car dùng chung orderId.

### Empty Car
Xe không chở hàng (chạy rỗng).

### Single Task
Lệnh đơn: chỉ có 1 pair (start, end).

### Task Order
Lệnh được gửi lên ICS khi có pair ready. Gồm orderId + start/end points + metadata.

### Timer Threshold
Ngưỡng thời gian (default: 30s) để node chuyển từ "detected" → "ready".

---

[⬅️ Về Overview](./README.md) | [🏠 Trang chính](../README.md)
