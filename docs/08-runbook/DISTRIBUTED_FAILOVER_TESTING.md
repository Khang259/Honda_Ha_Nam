# Distributed Camera Failover System - Testing Guide

## Giới thiệu

Hệ thống phân tán camera với khả năng failover tự động, hỗ trợ 1-4 workers xử lý tối đa 100 cameras.

## Cấu trúc Hệ thống

### Components Mới

1. **WorkerRegistryService** (`api/services/worker_registry_service.py`)
   - Quản lý đăng ký và heartbeat của workers
   - CRUD operations cho collection `register_worker`

2. **CameraAssignmentService** (`api/services/camera_assignment_service.py`)
   - Tính toán phân bổ cameras cho workers
   - Claim/release cameras với fencing token atomic

3. **WorkerManager** (`core/worker_manager.py`)
   - Quản lý worker lifecycle
   - Heartbeat loop và rebalancing
   - Lưu fencing tokens trong RAM

4. **Updates**
   - `api/schemas/node_id.py`: Thêm `current_worker`, `fencing_token`, `last_assigned`
   - `api/settings.py`: Thêm `WORKER_ID`, `WORKER_IP`, `HEARTBEAT_*`
   - `api/services/runtime_service.py`: Tích hợp WorkerManager

## MongoDB Schema

### Collection: `register_worker` (MỚI)

```javascript
{
  "worker_id": "w1",                    // Unique
  "worker_ip": "192.168.1.30",
  "start_time": ISODate("..."),
  "last_time": ISODate("..."),          // Heartbeat timestamp
  "capacity": {
    "current_cameras": 25
  }
}
```

**Index**: `worker_id` (unique)

### Collection: `node_id` (CẬP NHẬT)

Thêm các trường mới:
```javascript
{
  // ... existing fields ...
  "current_worker": "w1",               // Worker đang xử lý camera này
  "fencing_token": 5,                   // Token để tránh tranh chấp
  "last_assigned": ISODate("...")       // Thời gian assign
}
```

**Index mới**: `current_worker`

## Setup và Cấu hình

### 1. Database Setup

Tạo indexes trong MongoDB:

```javascript
// MongoDB shell
use HONDA_HN

// Index cho register_worker
db.register_worker.createIndex({ "worker_id": 1 }, { unique: true })

// Index cho node_id
db.node_id.createIndex({ "current_worker": 1 })
db.node_id.createIndex({ "cameraId": 1 }, { unique: true })  // Existing

// Initialize fencing_token cho cameras hiện có
db.node_id.updateMany(
  { fencing_token: { $exists: false } },
  { $set: { fencing_token: 0, current_worker: null } }
)
```

### 2. Cấu hình Workers

Copy `.env.example` thành `.env` và chỉnh sửa cho mỗi máy:

**Máy 1:**
```bash
WORKER_ID=w1
WORKER_IP=192.168.1.30
HEARTBEAT_INTERVAL=10
HEARTBEAT_TIMEOUT=30
MongoDB_URL=mongodb://192.168.1.100:27017/
MongoDB_DB=HONDA_HN
AI_SERVER_PORT=5000
```

**Máy 2:**
```bash
WORKER_ID=w2
WORKER_IP=192.168.1.31
# ... same other settings
AI_SERVER_PORT=5001  # Khác port nếu test trên cùng máy
```

**Máy 3:**
```bash
WORKER_ID=w3
WORKER_IP=192.168.1.32
AI_SERVER_PORT=5002
```

**Máy 4:**
```bash
WORKER_ID=w4
WORKER_IP=192.168.1.33
AI_SERVER_PORT=5003
```

## Test Scenarios

### Test 1: Single Worker

**Mục đích**: Verify worker có thể claim và xử lý tất cả cameras.

**Steps**:
1. Start worker 1:
   ```bash
   python api/main_ai.py
   ```

2. Check logs:
   ```
   [worker_manager] Worker w1 initialized successfully
   [worker_manager] Claiming 100 cameras: [0, 1, 2, ..., 99]
   [camera_manager] All 100 camera threads started
   ```

3. Check MongoDB:
   ```javascript
   db.register_worker.find()
   // Should see 1 worker with current_cameras: 100
   
   db.node_id.find({ current_worker: "w1" }).count()
   // Should return 100
   
   db.node_id.find().limit(5)
   // Check fencing_token > 0 and current_worker = "w1"
   ```

4. Check API status:
   ```bash
   curl http://localhost:5000/api/runtime/status
   ```
   Response should include:
   ```json
   {
     "worker": {
       "worker_id": "w1",
       "assigned_cameras": 100
     }
   }
   ```

**Expected**: Worker 1 xử lý tất cả 100 cameras, fencing_token = 1.

### Test 2: 4 Workers Startup

**Mục đích**: Verify 4 workers chia đều cameras (25 cameras/worker).

**Steps**:
1. Start 4 workers trong 4 terminals:
   ```bash
   # Terminal 1
   WORKER_ID=w1 AI_SERVER_PORT=5000 python api/main_ai.py
   
   # Terminal 2
   WORKER_ID=w2 AI_SERVER_PORT=5001 python api/main_ai.py
   
   # Terminal 3
   WORKER_ID=w3 AI_SERVER_PORT=5002 python api/main_ai.py
   
   # Terminal 4
   WORKER_ID=w4 AI_SERVER_PORT=5003 python api/main_ai.py
   ```

2. Wait 10-15 seconds cho workers rebalance.

3. Check MongoDB:
   ```javascript
   db.register_worker.find()
   // Should see 4 workers, each with current_cameras: 25
   
   db.node_id.aggregate([
     { $group: { _id: "$current_worker", count: { $sum: 1 } } }
   ])
   // Should show: w1: 25, w2: 25, w3: 25, w4: 25
   ```

4. Check camera distribution:
   ```javascript
   db.node_id.find({ current_worker: "w1" }).count()  // 25
   db.node_id.find({ current_worker: "w2" }).count()  // 25
   db.node_id.find({ current_worker: "w3" }).count()  // 25
   db.node_id.find({ current_worker: "w4" }).count()  // 25
   ```

**Expected**: Mỗi worker có 25 cameras, fencing_token đã tăng.

### Test 3: Failover (Kill Worker 2)

**Mục đích**: Verify rebalancing khi 1 worker chết.

**Steps**:
1. Với 4 workers đang chạy, kill worker 2 (Ctrl+C hoặc kill process).

2. Wait 30-40 seconds (heartbeat_timeout + processing time).

3. Observe logs của workers còn lại:
   ```
   [worker_manager] Worker count changed: 4 -> 3, rebalancing cameras...
   [worker_manager] Claiming XX cameras: [...]
   ```

4. Check MongoDB:
   ```javascript
   db.register_worker.find()
   // Should see 3 workers
   
   db.node_id.aggregate([
     { $group: { _id: "$current_worker", count: { $sum: 1 } } }
   ])
   // Should show distribution like: w1: 34, w3: 33, w4: 33
   // (100 cameras / 3 workers = 33.33)
   ```

**Expected**: 
- Workers 1, 3, 4 rebalance cameras
- Total: ~34 + 33 + 33 = 100 cameras
- Fencing tokens tăng cho cameras mới được claim

### Test 4: Recovery (Worker 2 sống lại)

**Mục đích**: Verify worker recovery và rebalancing.

**Steps**:
1. Start lại worker 2:
   ```bash
   WORKER_ID=w2 AI_SERVER_PORT=5001 python api/main_ai.py
   ```

2. Wait 10-15 seconds.

3. Observe logs:
   ```
   [worker_manager] Worker w2 initialized successfully
   [worker_manager] Worker count changed: 3 -> 4, rebalancing cameras...
   [worker_manager] Claiming 25 cameras: [25, 26, ..., 49]
   ```

4. Check MongoDB:
   ```javascript
   db.register_worker.find().count()  // 4 workers
   
   db.node_id.aggregate([
     { $group: { _id: "$current_worker", count: { $sum: 1 } } }
   ])
   // Should show: w1: 25, w2: 25, w3: 25, w4: 25
   ```

**Expected**: Cameras được rebalance về 25/worker, tokens tăng.

### Test 5: Extreme - 1 Worker Handles All

**Mục đích**: Verify 1 worker có thể handle tối đa 100 cameras.

**Steps**:
1. Start 4 workers.
2. Kill workers 2, 3, 4 (chỉ giữ worker 1).
3. Wait 30-40 seconds.
4. Check worker 1 logs và MongoDB.

**Expected**: Worker 1 claim và xử lý tất cả 100 cameras.

### Test 6: Split-brain Prevention

**Mục đích**: Verify fencing token ngăn tranh chấp.

**Steps**:
1. Start worker 1, wait cho nó claim cameras.
2. Note down fencing_token của camera 0:
   ```javascript
   db.node_id.findOne({ cameraId: 0 })
   // { ..., fencing_token: 5, current_worker: "w1" }
   ```
3. Simulate worker 1 crash (kill -9).
4. Start worker 2, nó sẽ claim camera 0.
5. Check token tăng:
   ```javascript
   db.node_id.findOne({ cameraId: 0 })
   // { ..., fencing_token: 6, current_worker: "w2" }
   ```
6. Start lại worker 1.
7. Check logs của worker 1:
   ```
   [worker_manager] Token mismatch for camera 0: current=5, db=6
   [worker_manager] Camera 0 no longer owned by worker w1
   ```

**Expected**: Worker 1 phát hiện token không khớp và không claim camera 0.

## Monitoring

### Logs to Watch

```bash
# Worker lifecycle
tail -f logs/worker_manager/log_*.log

# Camera assignment
tail -f logs/camera_assignment_service/log_*.log

# Worker registry
tail -f logs/worker_registry_service/log_*.log

# Camera processing
tail -f logs/camera_manager/log_*.log
```

### MongoDB Queries

```javascript
// Active workers
db.register_worker.find({ 
  last_time: { $gte: new Date(Date.now() - 30000) } 
})

// Camera distribution
db.node_id.aggregate([
  { $group: { 
    _id: "$current_worker", 
    count: { $sum: 1 },
    cameras: { $push: "$cameraId" }
  }}
])

// Fencing token status
db.node_id.find({}, { 
  cameraId: 1, 
  current_worker: 1, 
  fencing_token: 1 
}).limit(10)

// Unassigned cameras
db.node_id.find({ 
  $or: [
    { current_worker: null },
    { current_worker: { $exists: false }}
  ]
}).count()
```

## Troubleshooting

### Issue: Workers không rebalance

**Nguyên nhân**: Heartbeat timeout quá ngắn.

**Giải pháp**: Tăng `HEARTBEAT_TIMEOUT` trong `.env`:
```bash
HEARTBEAT_TIMEOUT=60  # Tăng lên 60 giây
```

### Issue: Fencing token conflicts

**Nguyên nhân**: Multiple workers cùng claim camera.

**Giải pháp**: Kiểm tra logs và MongoDB để xác định worker nào có token mới nhất.

### Issue: Worker không release cameras khi shutdown

**Nguyên nhân**: Graceful shutdown không hoạt động.

**Giải pháp**: Dùng Ctrl+C thay vì kill -9, và check logs.

## Performance Notes

- **Heartbeat interval**: 10s là optimal cho balance giữa responsiveness và overhead
- **Heartbeat timeout**: 30s cho phép 2-3 missed heartbeats trước khi coi worker là dead
- **Camera processing**: Mỗi camera là 1 thread, 100 cameras = 100 threads
- **Rebalance time**: ~5-10 seconds cho 100 cameras

## Next Steps

1. Monitor system performance với 100 cameras thực
2. Tune heartbeat parameters nếu cần
3. Add metrics/monitoring (Prometheus, Grafana)
4. Consider adding coordinator service nếu cần orchestration phức tạp hơn
