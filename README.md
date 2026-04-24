# Honda AI Monitoring

## Overview

**Mô tả ngắn gọn**: 
- Hệ thống AI xử lý nhiều luồng camera (RTSP) sử dụng YOLOv8 cho bài toán object detection để kiểm tra hoạt động kéo xe hàng từ công nhân và gửi lệnh/thông báo đến External_server

**Giải quyết vấn đề gì**

- **Scale nhiều camera** mà không phải load model per camera (tập trung inference và batching).
- **Giảm latency/overhead GPU** nhờ gom batch và CUDA streams.
- **Chuẩn hoá nghiệp vụ theo điểm (start/end node)** để kích hoạt hành vi hệ thống (pairing, gọi ICS/webhook, v.v.).

**Bối cảnh sử dụng**

- Nhà máy/kho bãi/line sản xuất cần **giám sát theo zone/ROI**, theo dõi “điểm bắt đầu/kết thúc”, và điều khiển camera theo worker node.
- Mô hình **distributed**: nhiều worker chạy ở nhiều máy, mỗi worker nhận camera được gán từ MongoDB và gửi/nhận trạng thái qua API.

## Features

- **Runtime orchestration**: khởi tạo `WorkerManager`, `StateManager`, `PairManager`, `InferenceEngine`, `CameraManager`.
- **Distributed worker**: worker heartbeat và nhận danh sách camera được gán từ MongoDB.
- **Centralized inference**: 1 `InferenceEngine` dùng chung model, gom batch theo timeout/kích thước, chạy async với CUDA streams.
- **Camera control**: bật/tắt camera theo `cameraId`, đồng bộ pause/resume inference khi không còn camera chạy.
- **Streaming MJPEG**: stream frame có overlay detections + ROI; ROI được lấy từ MongoDB.
- **Health/State/Runtime APIs**: cung cấp endpoint quan sát trạng thái hệ thống.

## Architecture

Kiến trúc theo kiểu **modular monolith + layered** (tách lớp API và core runtime):

- **API layer** (`api/`)
  - `api/app_factory.py`: tạo `FastAPI` app, đăng ký routes + lifecycle
  - `api/routes/*`: các endpoint (health/runtime/state/cameras/pairs/streaming/...)
  - `api/services/*`: service cho từng use-case (runtime, camera control, streaming, validate pairs, ...)
  - `api/state.py`: giữ reference global tới `state_manager`, `camera_manager`, `inference_engine`
- **Core runtime** (`core/`)
  - `core/worker_manager.py`: đăng ký worker/check heartbeat worker theo lifespan + lấy camera configs theo worker để rebalance theo worker registy
  - `core/camera_manager.py` + `core/camera_processor.py`: thread per camera, đọc frame, cập nhật `latest_frames`
  - `core/inference_engine.py`: shared queue, batching, inference GPU, phân phối kết quả về từng camera
  - `core/state_manager.py`: state theo `start_*`**điểm lấy hàng** / `end_*` **điểm cấp hàng** và logic “ready” theo thời gian vật xuất hiện trong vùng ROI
  - `core/pair_manager.py`: xử lý nghiệp vụ start/end (gọi ICS/webhook theo cấu hình) theo business logic (**phần này tùy theo BA**)
- **Test/benchmark nội bộ** (`unit_test/`)
  - Dùng để kiểm tra kết nối DB, latency/timing, GPU/decoder/CUDA stream, và kịch bản end-to-end.

## Data flow (ASCII)

```text
          +-----------------------+
          |       MongoDB         |
          |  cameras/rois/pairs   |
          +-----------+-----------+
                      |
                      | (lifespan connect + runtime start)
                      v
  +-------------------+-------------------+
  |            FastAPI (Uvicorn)          |
  |  routes -> services -> runtime_service|
  +-------------------+-------------------+
                      |
                      | create core components
                      v
      +---------------+----------------+
      |        Core Runtime            |
      | WorkerManager (heartbeat/assign|
      | StateManager (node timers)     |
      | PairManager (start/end pairs)  |
      +---------------+----------------+
                      |
                      | start camera threads
                      v
  +-------------------+-------------------+
  |        CameraManager / CameraProcessor|
  |  RTSP -> frame -> shared inference q  |
  |  update latest_frames + state by ROI  |
  +-------------------+-------------------+
                      |
                      | batch + CUDA streams
                      v
            +---------+----------+
            |   InferenceEngine  |
            | YOLO on GPU (batch)|
            +---------+----------+
                      |
                      | detections per cam
                      v
  +-------------------+-------------------+
  | API /streaming (MJPEG) + overlays     |
  | API /engine-control (toggle cameras)  |
  +---------------------------------------+
```

## Tech Stack
- **Backend**
  - FastAPI, Uvicorn, Starlette
  - MongoDB (Motor/PyMongo)
  - Redis (có dependency trong `requirements.txt`, tuỳ môi trường triển khai/use-case)
- **AI/Video**
  - Ultralytics YOLO, Torch (CUDA), CUDA Streams
  - TensorRT (wheel local), ONNX / ONNXRuntime-GPU
  - OpenCV, PyAV
- **Frontend**

## Setup

### Backend

1) Tạo môi trường Python 3.10 và cài dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2) Tạo file `.env` theo mục “Environment Variables”.

3) Chạy service:

```bash
python -m api.main_ai
```

### Frontend

## Environment Variables

Các biến môi trường được load từ `.env` (xem `api/settings.py`):

- **MongoDB_URL**: MongoDB connection string
- **MongoDB_DB**: tên database
- **AI_SERVER_HOST**: host bind của Uvicorn
- **AI_SERVER_PORT**: port bind của Uvicorn
- **AI_LOG_LEVEL**: log level (ví dụ: `info`)
- **WORKER_ID**: định danh worker
- **WORKER_IP**: IP worker
- **HEARTBEAT_INTERVAL**: chu kỳ heartbeat (seconds)
- **HEARTBEAT_TIMEOUT**: timeout heartbeat (seconds)

## API Docs

Khi service chạy, mở Swagger UI tại:

- `http://<AI_SERVER_HOST>:<AI_SERVER_PORT>/docs`

## AI Model

- Model runtime mặc định được cấu hình trong `config.py` qua `MODEL_PATH` (ví dụ: `models/ModelHN_160326_02.engine`).
- Pipeline inference nằm ở `core/inference_engine.py` (batching + CUDA streams).
- Khi triển khai và chạy bằng `engine` cần cài thêm thư viện `TensorRT` từ bên ngoài không thông qua `pip install <package> `. Có thể install thông qua `Zip file installation` theo khuyến nghị từ `NVIDIA`

## Deployment

- Do mang tính bảo mật nên phần này, phần mềm sẽ được triển khai trên dạng windows services nên có thể bỏ qua.

## Troubleshooting
- **Không có frame/stream trống**: 
  + Kiểm tra camera RTSP URL trong config lấy từ MongoDB (worker assignment).
  + Kiểm tra xem phần mềm có hỗ trợ deocde video (ffmpeg, pyav, ... ).
  + Kiểm tra xem input/ouput resolution của cameras có tương thích với đầu vào phần mềm
- **Không kết nối được MongoDB**: kiểm tra `MongoDB_URL`, network, user/password, và firewall.
- **GPU inference không chạy**: 
  + File model.engine không tương thích kiểm tra cài các thư viện cần thiết `torch, TensorRT, ultralytics`
  + Kiểm tra input model format
  + Kiểm tra thiết bị có GPU
- **Không thấy stream**: endpoint streaming dùng MJPEG; kiểm tra route `/streaming/*` và camera có `latest_frames`.
- **Không thấy gửi lệnh**:
  + Kiểm tra đường dẫn đến external-server trong file `config.py`
  + Nếu đường dẫn đúng kiểm tra respone từ external-server và kiểm tra mã lỗi theo tài liệu ICS từ hãng sản xuất để debug
- **Gửi lệnh liên tục theo dạng spam**: kiểm tra xem biến `flag` đã được set và reset hợp lý chưa

## Contribution

- Giữ cấu trúc theo module (`api/`, `core/`, `utils/`) và tránh lặp logic.
- Với thay đổi nghiệp vụ, ưu tiên đặt ở `core/*` hoặc `api/services/*` thay vì nhét vào routes.

## Tiêu chí maintainability

- **Phân lớp rõ ràng**: HTTP/controller ở `api/routes/*`, use-case ở `api/services/*`, runtime core ở `core/*`.
- **Giảm coupling**: routes không tự “new core object”; khởi tạo tập trung ở `runtime_service`.
- **Cấu hình hoá**: tham số runtime qua `.env` (`api/settings.py`) và `config.py` (batching/model/snapshot).
- **Quan sát được**: log theo module (`utils/setup_log.py`) và endpoint health/runtime để triage nhanh.
- **Testability**: `unit_test/` tập trung benchmark/integration cho các điểm rủi ro realtime (DB, latency, GPU/decoder).
