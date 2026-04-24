# Worker Registration & Heartbeat Flow

## 1. Mô tả usecase

Worker tự đăng ký vào hệ thống phân tán, nhận camera được gán, và duy trì heartbeat để báo hiệu "còn sống". Khi topology worker thay đổi (worker mới join hoặc worker cũ die), hệ thống tự động rebalance camera assignment.

## 2. Actors

- **WorkerManager**: quản lý lifecycle của worker (register/heartbeat/claim/release)
- **WorkerRegistryService**: service giao tiếp với MongoDB collection `worker_registry`
- **CameraAssignmentService**: service tính toán và quản lý camera assignment (fencing tokens)
- **MongoDB**: lưu trữ worker registry và camera assignments

## 3. Flow

### 3.1. Initialization Flow

```
RuntimeService.start()
    └─> WorkerManager.__init__(worker_id, worker_ip)
    └─> WorkerManager.initialize()
        ├─> _register_self() → WorkerRegistryService.register()
        │   └─> INSERT worker vào `worker_registry` collection
        │
        └─> detect_and_rebalance()
            ├─> get_active_workers(timeout) → query workers với last_heartbeat gần
            ├─> get_all_cameras_count() → đếm cameras trong DB
            ├─> calculate_assignment() → chia cameras theo round-robin
            │   └─> assignment = {worker_id: [cam_ids]}
            │
            ├─> to_claim = my_cameras - assigned_cameras
            ├─> to_release = assigned_cameras - my_cameras
            │
            ├─> FOR camera in to_release:
            │   └─> release_camera(camera_id) → UNSET assigned_worker
            │
            └─> FOR camera in to_claim:
                └─> claim_camera(camera_id, worker_id)
                    └─> UPDATE với $inc fencing_token → trả về new_token
                    └─> lưu fencing_tokens[camera_id] = new_token
```

### 3.2. Heartbeat Loop

```
asyncio.create_task(WorkerManager.start_heartbeat_loop())
    └─> WHILE running:
        ├─> update_heartbeat(worker_id, current_cameras)
        │   └─> UPDATE last_heartbeat = now, camera_count
        │
        ├─> _validate_current_cameras()
        │   └─> FOR camera_id, current_token in fencing_tokens:
        │       └─> validate_token(camera_id, current_token)
        │           └─> CHECK DB: fencing_token == current_token?
        │           └─> IF mismatch: remove từ assigned_camera_ids
        │
        └─> detect_and_rebalance()
            └─> (tương tự như init, nhưng chỉ chạy khi worker_count thay đổi)
        
        └─> sleep(heartbeat_interval)  # default: 10s
```

### 3.3. Shutdown Flow

```
RuntimeService.stop()
    └─> WorkerManager.shutdown()
        ├─> release_cameras(worker_id) → UNSET assigned_worker cho tất cả cameras
        └─> remove_worker(worker_id) → DELETE khỏi worker_registry
```

## 4. Data flow

```
┌─────────────────────────────────────────────────────────────┐
│                         MongoDB                             │
│  ┌──────────────────┐        ┌─────────────────────────┐   │
│  │ worker_registry  │        │  node_id (cameras)      │   │
│  │ - worker_id      │        │  - cameraId             │   │
│  │ - worker_ip      │        │  - assigned_worker      │   │
│  │ - last_heartbeat │        │  - fencing_token        │   │
│  │ - camera_count   │        │  - rois, url, ...       │   │
│  └──────────────────┘        └─────────────────────────┘   │
└────────────┬────────────────────────────┬───────────────────┘
             │                            │
        (1) register                 (2) claim/release
        (3) update_heartbeat         (4) validate_token
             │                            │
             └────────────┬───────────────┘
                          │
                ┌─────────▼──────────┐
                │   WorkerManager    │
                │ - worker_id        │
                │ - assigned_cameras │
                │ - fencing_tokens   │
                └─────────┬──────────┘
                          │
                          │ (5) get_assigned_camera_configs()
                          │     → trả về list[camera_config]
                          ▼
                  RuntimeService.start()
                          │
                          └──> spawn CameraManager threads
```

## 5. Communication

### 5.1. Protocols

- **MongoDB Wire Protocol** qua Motor (async MongoDB driver)
- **Asyncio Task** cho heartbeat loop (không block main thread)

### 5.2. Key API Calls

**WorkerRegistryService**:
- `register(worker_id, worker_ip)` → INSERT worker
- `update_heartbeat(worker_id, camera_count)` → UPDATE last_heartbeat
- `get_active_workers(timeout_seconds)` → FIND workers với `last_heartbeat > now - timeout`
- `remove_worker(worker_id)` → DELETE worker

**CameraAssignmentService**:
- `get_all_cameras_count()` → COUNT documents trong `node_id` collection
- `claim_camera(camera_id, worker_id)` → UPDATE + $inc fencing_token
- `release_camera(camera_id)` → UNSET assigned_worker
- `validate_token(camera_id, current_token)` → FIND_ONE và so sánh token

### 5.3. Fencing Token Mechanism

Dùng **monotonic counter** trong MongoDB để ngăn "split-brain":
- Mỗi lần claim → `$inc fencing_token`
- Worker lưu token trong RAM
- Mỗi heartbeat validate token với DB
- Nếu token không khớp → camera đã bị worker khác claim → tự release

## 6. Error points

### 6.1. Worker không connect được MongoDB

**Triệu chứng**: `RuntimeService.start()` throw exception

**Nguyên nhân**:
- MongoDB_URL sai/network không reach
- Auth failed

**Giải pháp**:
- Check `.env` và MongoDB connection string
- Verify network/firewall

### 6.2. Heartbeat timeout → worker bị coi là "dead"

**Triệu chứng**: camera bị reassign cho worker khác

**Nguyên nhân**:
- Worker bị pause quá lâu (GC/CPU starve)
- Network partition

**Giải pháp**:
- Tăng `HEARTBEAT_TIMEOUT` nếu môi trường không ổn định
- Monitor worker load

### 6.3. Race condition khi nhiều worker cùng claim camera

**Triệu chứng**: 2 worker cùng nghĩ mình own camera

**Cơ chế bảo vệ**:
- Fencing token + validate mỗi heartbeat
- Worker phát hiện token mismatch sẽ tự release

### 6.4. Rebalance quá thường xuyên (thrashing)

**Triệu chứng**: camera bị start/stop liên tục

**Nguyên nhân**:
- Worker flapping (die/rejoin liên tục)
- Heartbeat interval quá ngắn

**Giải pháp**:
- Tăng `HEARTBEAT_INTERVAL`
- Thêm cooldown/hysteresis cho rebalance logic

### 6.5. MongoDB write conflict

**Triệu chứng**: `claim_camera` failed

**Nguyên nhân**:
- 2 worker cùng claim 1 camera đồng thời

**Xử lý hiện tại**:
- MongoDB atomic update → chỉ 1 worker thành công
- Worker thất bại sẽ skip camera đó trong vòng rebalance

## 7. Notes + cải tiến

### 7.1. Hiện trạng

- Worker assignment theo **round-robin** đơn giản (không tính GPU load/network)
- Heartbeat interval cố định (không adaptive)
- Không có "graceful handoff" khi rebalance (camera bị disconnect ngắn)

### 7.2. Cải tiến đề xuất

#### a) Load-aware assignment

Thay vì round-robin, tính assignment dựa trên:
- GPU utilization của worker
- Network latency tới camera
- Camera resolution/complexity

#### b) Graceful handoff

Khi reassign camera từ worker A → B:
1. Worker B claim camera (token++)
2. Worker A validate → phát hiện token mismatch
3. Worker A gửi "handoff ready" signal
4. Worker B chờ signal rồi mới start camera
→ Giảm frame loss

#### c) Health check nâng cao

Thêm metrics vào heartbeat:
- FPS thực tế của từng camera
- Inference queue depth
- GPU memory usage

→ Central coordinator có thể trigger rebalance chủ động khi worker quá tải

#### d) Snapshot/restore state

Khi worker restart:
- Lưu `fencing_tokens` vào persistent storage (Redis/file)
- Restore tokens và skip rebalance nếu topology không đổi
→ Giảm downtime

#### e) Multi-region support

Hiện tại assume workers trong 1 region:
- Thêm `region` field vào worker registry
- Assignment ưu tiên camera cùng region
- Cross-region chỉ khi không đủ worker local

### 7.3. Monitoring checklist

- [ ] Worker count hiện tại (`get_active_workers()`)
- [ ] Camera distribution histogram (mỗi worker bao nhiêu cam)
- [ ] Heartbeat miss rate (worker miss heartbeat trước khi die)
- [ ] Rebalance frequency (bao nhiêu lần/phút)
- [ ] Fencing token mismatch rate (conflict rate)
