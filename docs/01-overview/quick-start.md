# Quick Start Guide

> Hướng dẫn nhanh để setup và chạy **Honda AI Monitoring** lần đầu.

## Prerequisites

### 1. Hardware Requirements
- **GPU**: NVIDIA GPU với CUDA support (recommended: RTX 3060 trở lên)
  - VRAM: ≥6GB
  - Driver: 535.x trở lên
- **CPU**: 8 cores trở lên
- **RAM**: 16GB trở lên
- **Storage**: 50GB free space

### 2. Software Requirements
- **OS**: Ubuntu 20.04+ hoặc Windows 10/11
- **Python**: 3.10
- **CUDA**: 12.1
- **MongoDB**: 4.4+
- **FFmpeg**: với NVDEC support

### 3. Network
- Camera RTSP URLs accessible
- MongoDB accessible
- Port 8000 available (API server)

---

## Installation Steps

### Step 1: Clone Repository
```bash
git clone <repository_url>
cd <folder>
```

### Step 2: Create Virtual Environment
```bash
python -m venv .venv

# Linux/Mac
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

**Note**: TensorRT wheels cần install thủ công (xem `requirements.txt` line 87-89).

### Step 4: Setup Environment Variables

Tạo file `.env` trong project root:

```bash
# MongoDB
MongoDB_URL=mongodb://localhost:27017
MongoDB_DB=honda_ai_monitoring

# API Server
AI_SERVER_HOST=0.0.0.0
AI_SERVER_PORT=8000
AI_LOG_LEVEL=info

# Worker Config
WORKER_ID=worker_01
WORKER_IP=192.168.1.100
HEARTBEAT_INTERVAL=10
HEARTBEAT_TIMEOUT=30
```

### Step 5: Setup MongoDB

#### Install MongoDB
```bash
# Ubuntu
sudo apt-get install -y mongodb

# hoặc dùng Docker
docker run -d -p 27017:27017 --name mongodb mongo:4.4
```

#### Import Initial Data

Cần 3 collections:
1. **node_id**: Camera configs + ROI
2. **worker_registry**: Workers
3. **validate_pairs**: Valid start/end pairs

Example seed data:
```javascript
// Collection: node_id
{
  "cameraId": 101,
  "url": "rtsp://camera_ip/stream",
  "area_name": "AE5",
  "rois": {
    "1": {
      "roi": [100, 200, 300, 400],
      "start": true,
      "end": false
    },
    "2": {
      "roi": [500, 200, 300, 400],
      "start": false,
      "end": true
    }
  }
}

// Collection: validate_pairs
{
  "pairs": [
    ["start_1", "end_2"]
  ]
}
```

### Step 6: Prepare Model

Đặt YOLO TensorRT engine vào `models/`:
```bash
mkdir -p models
# Copy hoặc export model
cp /path/to/ModelHN_160326_02.engine models/
```

Hoặc export từ ONNX:
```bash
python utils/export_engine.py
```

### Step 7: Update Config

Edit `config.py`:
```python
# Model
MODEL_PATH = "models/ModelHN_160326_02.engine"

# Inference
INFERENCE_MAX_BATCH_SIZE = 24  # Tune theo GPU
INFERENCE_BATCH_TIMEOUT = 1.0

# ICS
ICS_URL = "http://your-ics-server/api/tasks"

# Snapshot (optional)
ENABLE_SNAPSHOTS = False
```

---

## Start Service

### Development Mode
```bash
python -m api.main_ai
```

Output should show:
```
INFO: Starting AI server on 0.0.0.0:8000
INFO: Worker worker_01 initialized successfully
INFO: All 10 camera threads started
INFO: InferenceEngine async pipeline started
INFO: PairManager processing loop started
```

### Access Swagger UI
```
http://localhost:8000/docs
```

---

## Verify Installation

### 1. Check Health
```bash
curl http://localhost:8000/health

# Expected: {"status": "ok"}
```

### 2. Check Runtime Status
```bash
curl http://localhost:8000/runtime/status

# Expected:
{
  "running": true,
  "cameras": {
    "total": 10,
    "enabled": 0,
    "alive": 0
  },
  "inference": {
    "paused": true
  }
}
```

### 3. Enable Cameras
```bash
# Enable một camera
curl -X POST http://localhost:8000/engine-control/toggle \
  -H 'Content-Type: application/json' \
  -d '{"cameraId": 101}'

# Check lại status
curl http://localhost:8000/runtime/status
# cameras.enabled should be 1
```

### 4. View Stream
Mở browser: `http://localhost:8000/streaming/video/101`

Bạn sẽ thấy MJPEG stream với bounding boxes (nếu có detections) và ROI rectangles.

---

## Troubleshooting

### MongoDB Connection Failed
```
Error: MongoDB connection refused
```

**Fix**:
- Check MongoDB_URL trong `.env`
- Test connection: `mongosh <MongoDB_URL>`

---

### CUDA Out of Memory
```
RuntimeError: CUDA out of memory
```

**Fix**:
- Giảm `INFERENCE_MAX_BATCH_SIZE` trong `config.py`
- Check GPU processes: `nvidia-smi`
- Kill other GPU processes nếu cần

---

### Camera Cannot Open
```
ERROR: Cannot open RTSP: rtsp://...
```

**Fix**:
- Check camera online: `ping <camera_ip>`
- Test RTSP URL: `ffplay rtsp://...`
- Verify camera credentials

---

### Model Not Found
```
FileNotFoundError: models/ModelHN_160326_02.engine
```

**Fix**:
- Check model path: `ls models/`
- Update `MODEL_PATH` trong `config.py`
- Export model: `python utils/export_engine.py`

---

## Next Steps

### Setup Multiple Cameras
1. Add cameras to MongoDB `node_id` collection
2. Restart service
3. Cameras sẽ tự động được pickup

### Setup Distributed Workers
1. Start service trên server khác với WORKER_ID khác
2. Workers tự động rebalance cameras
3. Monitor qua `/workers` API (coming soon)

### Production Deployment
- Setup reverse proxy (Nginx)
- Enable authentication
- Setup monitoring (Prometheus + Grafana)
- Configure log rotation

---

## Common Commands

```bash
# Start service
python -m api.main_ai

# Check logs
tail -f logs/ai_main/log_$(date +%Y%m%d).log

# Monitor GPU
nvidia-smi dmon

# Test camera
ffplay rtsp://camera_ip/stream

# MongoDB shell
mongosh <MongoDB_URL>/<MongoDB_DB>
```

---

## Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Environment variables (MongoDB, server, worker) |
| `config.py` | Runtime parameters (batch size, model path, ICS URL) |
| `requirements.txt` | Python dependencies |

---

## Directory Structure (After Setup)

```
ai-n-s-2-p-docker-db/
├── .env                    # Your env vars
├── .venv/                  # Python virtual env
├── api/                    # FastAPI app
├── core/                   # Runtime core
├── utils/                  # Utilities
├── models/                 # YOLO models
│   └── ModelHN_160326_02.engine
├── logs/                   # Runtime logs
├── docs/                   # Documentation
└── unit_test/              # Tests
```

---

## Further Reading

- [System Overview](./system-overview.md) - Hiểu tổng quan hệ thống
- [Architecture](../02-architecture/) - Hiểu kiến trúc
- [Flows](../03-flows/) - Hiểu từng luồng hoạt động
- [API Reference](../05-api/) - API documentation

---

[⬅️ Về Overview](./README.md) | [🏠 Trang chính](../README.md)
