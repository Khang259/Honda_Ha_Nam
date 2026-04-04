# AI System - 3 Service Architecture

Hệ thống AI đã được tách thành 3 service độc lập:

## Kiến trúc

```
┌─────────────────────────────────────────┐
│         Docker Compose Network          │
│                                         │
│  ┌──────────────┐    ┌──────────────┐  │
│  │  API Server  │◄───│  AI Worker   │  │
│  │  (FastAPI)   │    │  (GPU/NVDEC) │  │
│  │  Port: 5000  │    │              │  │
│  └──────┬───────┘    └──────────────┘  │
│         │                               │
│         │            ┌──────────────┐   │
│         └────────────┤    Redis     │   │
│                      └──────────────┘   │
└─────────────────────────────────────────┘
                  │
                  │ HTTP API
                  ▼
         ┌─────────────────┐
         │   UI Monitor    │
         │  (Local Tkinter)│
         └─────────────────┘
```

## Services

### 1. API Server (`api_server`)
- **Vai trò**: Trung tâm quản lý state và điều phối
- **Port**: 5000
- **Chức năng**:
  - Quản lý StateManager (points, ready lists)
  - Nhận detection results từ AI Worker
  - Xử lý webhook từ ICS
  - Chạy PairManager để tạo tasks
  - Cung cấp API cho UI

### 2. AI Worker (`ai_worker`)
- **Vai trò**: GPU inference và video processing
- **Requirements**: NVIDIA GPU với CUDA support
- **Chức năng**:
  - Decode RTSP streams bằng NVDEC
  - Chạy inference với TensorRT model
  - Gửi detection results về API Server
  - Quản lý snapshot (nếu enabled)

### 3. UI Monitor (Local)
- **Vai trò**: Monitoring và điều khiển
- **Chạy**: Local machine (không trong Docker)
- **Chức năng**:
  - Hiển thị realtime state từ API
  - Điều khiển camera zones
  - Xem camera preview
  - Toggle flags

## Cách chạy

### Bước 1: Build và start Docker services

```bash
# Từ thư mục root project
cd d:/Honda/ai_project

# Build và start services
docker compose up --build -d api_server ai_worker

# Xem logs
docker compose logs -f api_server
docker compose logs -f ai_worker
```

### Bước 2: Chạy UI Monitor local

```bash
# Từ thư mục ai-nvdec-snapshot-2task-processor-docker
cd ai-nvdec-snapshot-2task-processor-docker

# Đảm bảo có dependencies
pip install -r requirements_api.txt
pip install tkinter pillow

# Chạy UI
python ui/main_ui.py
```

## Environment Variables

### API Server
- `API_SERVER_HOST`: Default `0.0.0.0`
- `API_SERVER_PORT`: Default `5000`
- `API_LOG_LEVEL`: Default `info`

### AI Worker
- `API_URL`: Default `http://api_server:5000`
- Các biến khác trong `config.py`

### UI Monitor
- `API_URL`: Default `http://localhost:5000`

## API Endpoints

### Health Check
```bash
GET http://localhost:5000/health
```

### Get Points State
```bash
GET http://localhost:5000/state/points
```

### Get Ready Lists
```bash
GET http://localhost:5000/state/ready-lists
```

### Post Detection (từ AI Worker)
```bash
POST http://localhost:5000/detections
{
  "cam_id": "cam_0_123",
  "node_id": "start_10000037",
  "detected": true,
  "coverage": 0.85
}
```

### Delete Flag (webhook từ ICS)
```bash
POST http://localhost:5000/delete-flag
{
  "orderId": "ORDER123",
  "status": 3
}
```

## Troubleshooting

### API Server không start
```bash
# Check logs
docker compose logs api_server

# Check port conflict
netstat -an | grep 5000
```

### AI Worker không kết nối được API
```bash
# Test API từ worker container
docker compose exec ai_worker curl http://api_server:5000/health

# Check network
docker compose exec ai_worker ping api_server
```

### UI không kết nối được API
```bash
# Test API từ host
curl http://localhost:5000/health

# Check API_URL trong ui/main_ui.py
```

### GPU không available trong worker
```bash
# Check nvidia-docker
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi

# Check compose deploy config
docker compose config | grep -A5 deploy
```

## File Structure

```
ai-nvdec-snapshot-2task-processor-docker/
├── api/
│   ├── api_server.py          # FastAPI app với endpoints
│   └── main_api.py            # Entry point cho API service
├── worker/
│   ├── api_client.py          # HTTP client để gọi API
│   └── main_worker.py         # Entry point cho AI worker
├── ui/
│   ├── main_ui.py             # Entry point cho UI local
│   ├── state_proxy.py         # Proxy để poll API
│   └── gui_monitor.py         # Tkinter GUI (đã sửa)
├── core/
│   ├── camera_manager.py      # Quản lý cameras (đã sửa)
│   ├── camera_processor.py    # Process từng camera (đã sửa)
│   ├── inference_engine.py    # GPU inference
│   ├── pair_manager.py        # Tạo pairs và gửi ICS
│   └── state_manager.py       # State management
├── Dockerfile.api             # Dockerfile cho API service
├── Dockerfile.worker          # Dockerfile cho AI worker
├── requirements_api.txt       # Dependencies cho API
├── requirements_worker.txt    # Dependencies cho Worker
└── .dockerignore             # Files bỏ qua khi build
```

## Migration từ hệ thống cũ

Hệ thống cũ (`main_ai.py`) đã được thay thế bằng 3 entry points:
- `api/main_api.py` - thay thế phần API + StateManager + PairManager
- `worker/main_worker.py` - thay thế phần inference + cameras
- `ui/main_ui.py` - thay thế phần UI

Để chạy hệ thống cũ (nếu cần), copy code từ `ai-nvdec-snapshot-2task-processor` (không có `-docker` suffix).
