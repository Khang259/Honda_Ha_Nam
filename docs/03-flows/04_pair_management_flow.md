# Pair Management Flow (Start/End Pairing + ICS Webhook)

## 1. Mô tả usecase

Theo dõi state của các điểm start/end (ROI), phát hiện khi có cặp start-end ready (đủ điều kiện), ghép cặp theo logic nghiệp vụ (bao gồm lệnh đơn/đôi/xe trống), và gọi webhook ICS để tạo task order.

## 2. Actors

- **PairManager (Thread)**: thread quản lý nghiệp vụ pairing
- **StateManager**: lưu trữ state/timer của các node (start_*/end_*)
- **CameraProcessor threads**: update state theo ROI detections
- **ICS Server**: hệ thống backend nhận webhook để tạo task
- **SnapshotManager** (optional): lưu snapshot khi tạo lệnh

## 3. Flow

### 3.1. Initialization

```
RuntimeService.start()
    └─> validate_pairs = ValidatePairsService().get_validate_pairs_all()
        └─> query MongoDB collection "validate_pairs"
            └─> return: [
                    ("start_1", "end_1"),    # normal pair
                    ("start_2", "end_2"),    # normal pair
                    ("start_empty_3",),      # empty car (len=1)
                    ...
                ]
    
    └─> state_manager = StateManager(validate_pairs)
        └─> points = defaultdict(lambda: {
                "state": False,
                "time": time.time(),
                "flag": False,
                "frame": None
            })
        └─> ready_start_list = set()
        └─> ready_end_list = set()
        └─> pair_mapping = {}  # end → start
        └─> order_mapping = {}  # order_id → [(start, end, empty_car)]
    
    └─> pair_manager = PairManager(
            ICS_URL,
            state_manager,
            validate_pairs,
            snapshot_manager
        )
    └─> pair_manager.start()
        └─> thread = Thread(target=_run, daemon=True, name="PairManager")
        └─> thread.start()
```

### 3.2. State Update Flow (from CameraProcessor)

```
CameraProcessor.run()
    └─> FOR roi_dict in rois:
        ├─> has_obj, coverage = has_object_in_roi(detections, roi)
        │
        └─> state_manager.get_state_nodes(node_id, has_obj)
            └─> current = points[node_id]
            └─> old_state = current["state"]
            └─> current["state"] = has_obj
            │
            └─> IF old_state != has_obj:  # state changed
                ├─> IF node_id.startswith("start_"):
                │   ├─> IF has_obj:  # object xuất hiện
                │   │   └─> current["time"] = time.time()  # start timer
                │   └─> ELSE:  # object biến mất
                │       ├─> current["time"] = time.time()  # reset timer
                │       └─> ready_start_list.discard(node_id)  # remove từ ready
                │
                └─> IF node_id.startswith("end_"):
                    ├─> IF not has_obj:  # object biến mất (điểm end trống)
                    │   └─> current["time"] = time.time()  # start timer
                    └─> ELSE:  # object xuất hiện
                        ├─> current["time"] = time.time()  # reset timer
                        └─> ready_end_list.discard(node_id)  # remove từ ready
```

### 3.3. Pair Processing Loop

```
PairManager._run() [Thread]
    └─> WHILE running:
        ├─> state_manager.process_starts()
        │   └─> FOR node_id in points (chỉ start_*):
        │       └─> IF state == True AND flag == False:
        │           └─> existed_time = now - time
        │           └─> IF existed_time > 30s:
        │               └─> ready_start_list.add(node_id)
        │
        ├─> state_manager.process_ends()
        │   └─> FOR node_id in points (chỉ end_*):
        │       └─> IF state == False AND flag == False:
        │           └─> existed_time = now - time
        │           └─> IF existed_time > 30s:
        │               └─> ready_end_list.add(node_id)
        │
        ├─> pairs, payloads = make_pairs()
        │   └─> (1) process empty pairs (len=1):
        │       └─> IF start_empty in ready_start_list:
        │           └─> pending_empty_queue.append((start_empty, deadline=now+15s))
        │   
        │   └─> (2) process normal pairs (len=2) - FIFO order:
        │       └─> start_queue = deque(ready_start_list)
        │       └─> WHILE start_queue:
        │           ├─> start_point = start_queue.popleft()
        │           ├─> FIND end_point in validate_pairs WHERE:
        │           │   └─> (start_point, end_point) in validate_pairs
        │           │   └─> end_point in ready_end_list
        │           │   └─> end_point not used
        │           │
        │           └─> IF found:
        │               ├─> payload = payload_sent_ICS(start, end)
        │               ├─> pairs.append((start, end))
        │               └─> mark start/end as used
        │
        ├─> (3) ghép double tasks (normal + empty):
        │   └─> normal_idx = 0
        │   └─> WHILE normal_idx < len(pairs) AND pending_empty_queue:
        │       ├─> start_empty, deadline = pending_empty_queue[0]
        │       │
        │       ├─> IF now > deadline:  # empty timeout
        │       │   ├─> payload_empty = payload_sent_ICS_empty(start_empty, end_empty)
        │       │   ├─> post_to_ics(payload_empty)
        │       │   ├─> IF success:
        │       │   │   └─> state_manager.set_pair_used(start_empty, end_empty, order_id)
        │       │   └─> pending_empty_queue.pop(0)
        │       │
        │       └─> ELSE:  # ghép với normal pair
        │           ├─> start_point, end_point = pairs[normal_idx]
        │           ├─> payload_double = payload_sent_ICS_double(
        │           │       start_point, end_point,
        │           │       start_empty, end_empty
        │           │   )
        │           ├─> post_to_ics(payload_double)
        │           ├─> IF success:
        │           │   ├─> set_pair_used(start_point, end_point, order_id, empty_car=True)
        │           │   └─> set_pair_used(start_empty, end_empty, order_id, empty_car=False)
        │           │
        │           ├─> pending_empty_queue.pop(0)
        │           └─> normal_idx += 1
        │
        ├─> (4) gửi normal pairs còn lại (single):
        │   └─> FOR pair, payload in remaining_pairs:
        │       ├─> post_to_ics(payload)
        │       └─> IF success:
        │           └─> set_pair_used(start, end, order_id, empty_car=False)
        │
        ├─> (5) flush empty timeout:
        │   └─> WHILE pending_empty_queue AND now > deadline:
        │       └─> (tương tự step 3 timeout)
        │
        └─> sleep(1s)
```

### 3.4. Set Pair Used

```
StateManager.set_pair_used(start_point, end_point, order_id, empty_car)
    ├─> points[start_point]["flag"] = True
    ├─> points[end_point]["flag"] = True
    │
    ├─> ready_start_list.discard(start_point)
    ├─> ready_end_list.discard(end_point)
    │
    ├─> pair_mapping[end_point] = start_point
    │
    └─> order_mapping[order_id].append((start_point, end_point, empty_car))
        └─> (lưu để track lệnh đơn/đôi)
```

## 4. Data flow

```
┌──────────────────────────────────────────────────────────────┐
│              Multiple CameraProcessor Threads                │
│  Thread 1        Thread 2        ...       Thread N          │
└───────┬──────────────┬────────────────────────┬──────────────┘
        │              │                        │
        │ has_object_in_roi(detections, roi)   │
        │              │                        │
        └──────────────┼────────────────────────┘
                       ▼
        ┌──────────────────────────────────────┐
        │       StateManager                   │
        │  ┌────────────────────────────────┐  │
        │  │ points = {                     │  │
        │  │   "start_1": {                 │  │
        │  │     state: True,               │  │
        │  │     time: 1234567890.5,        │  │
        │  │     flag: False                │  │
        │  │   },                           │  │
        │  │   "end_1": {...}               │  │
        │  │ }                              │  │
        │  └────────────────────────────────┘  │
        │                                      │
        │  ready_start_list = {"start_1", ...} │
        │  ready_end_list = {"end_1", ...}     │
        └───────────────┬──────────────────────┘
                        │
                        │ process_starts() / process_ends()
                        │ └─> check timer > 30s
                        ▼
        ┌───────────────────────────────────────┐
        │     PairManager Thread                │
        │                                       │
        │  (1) make_pairs()                     │
        │      ├─> empty pairs → pending_queue  │
        │      └─> normal pairs → pairs list    │
        │                                       │
        │  (2) ghép double (normal + empty)     │
        │      └─> payload_sent_ICS_double()    │
        │                                       │
        │  (3) gửi single normal pairs          │
        │      └─> payload_sent_ICS()           │
        │                                       │
        │  (4) gửi empty timeout                │
        │      └─> payload_sent_ICS_empty()     │
        └───────────────┬───────────────────────┘
                        │
                        │ post_to_ics(payload)
                        ▼
        ┌───────────────────────────────────────┐
        │      requests.post(ICS_URL, json)     │
        │      └─> HTTP POST                    │
        └───────────────┬───────────────────────┘
                        │
                        ▼
        ┌───────────────────────────────────────┐
        │           ICS Server                  │
        │  {                                    │
        │    "orderId": "...",                  │
        │    "taskType": "SINGLE|DOUBLE",       │
        │    "startPoint": "start_1",           │
        │    "endPoint": "end_1",               │
        │    ...                                │
        │  }                                    │
        └───────────────────────────────────────┘
```

## 5. Communication

### 5.1. Internal (in-process)

**Thread-safe shared state**:
- `StateManager.points`: dict với defaultdict (thread-safe reads, nhưng updates không có lock)
- `StateManager.ready_start_list / ready_end_list`: set operations (not thread-safe)

**Note**: Hiện tại `StateManager` không có lock protection, nhưng:
- Chỉ `CameraProcessor` threads write `points[node_id]["state"]`
- Chỉ `PairManager` thread read `ready_*_list`
- Race condition có thể xảy ra nếu 2 cameras cùng update 1 node_id

### 5.2. External (HTTP)

**ICS Webhook API**:
```
POST {ICS_URL}
Content-Type: application/json

# Single task
{
  "orderId": "20260423_123456_start1_end1",
  "taskType": "SINGLE",
  "startPoint": "start_1",
  "endPoint": "end_1",
  "timestamp": 1234567890,
  ...
}

# Double task
{
  "orderId": "20260423_123457_double",
  "taskType": "DOUBLE",
  "normalTask": {
    "startPoint": "start_1",
    "endPoint": "end_1"
  },
  "emptyTask": {
    "startPoint": "start_empty_3",
    "endPoint": "end_empty"
  },
  ...
}

# Response
{
  "code": 1000,  # success
  "message": "OK"
}
```

**Timeout**: không có timeout config (dùng default requests timeout)

## 6. Error points

### 6.1. StateManager race condition

**Triệu chứng**: cặp start-end không được ghép dù visual check thấy ready

**Nguyên nhân**:
- 2 camera threads cùng update 1 node_id
- `ready_*_list.add()` và `ready_*_list.discard()` không atomic

**Cải tiến**:
```python
class StateManager:
    def __init__(self):
        self._lock = threading.Lock()
    
    def get_state_nodes(self, node_id, state):
        with self._lock:
            # existing logic
```

### 6.2. Timer không chính xác (30s threshold)

**Triệu chứng**: cặp ready sau 35s thay vì 30s

**Nguyên nhân**:
- `process_starts()` chỉ chạy mỗi 1s
- Nếu state change lúc 0.9s, phải chờ đến 1.0s mới check

**Tác động**: không nghiêm trọng, chỉ delay ~1s

**Cải tiến**: nếu cần chính xác hơn, dùng heap/priority queue theo deadline

### 6.3. ICS webhook timeout/failed

**Triệu chứng**: `post_to_ics()` return False

**Nguyên nhân**:
- ICS server down/slow
- Network issue
- Payload format sai

**Xử lý hiện tại**:
- Log error
- **Không retry** → pair lost (flag=False vẫn, nhưng không thêm vào order_mapping)

**Cải tiến**:
- Thêm retry logic (exponential backoff)
- Dead letter queue cho failed pairs
- Alert nếu fail rate cao

### 6.4. Empty car logic phức tạp (pending queue)

**Triệu chứng**: lệnh empty không gửi hoặc gửi sai

**Nguyên nhân**:
- Logic ghép double rối (nhiều nhánh if/else)
- Deadline tracking không rõ ràng

**Risk**: bug logic dễ xảy ra khi refactor

**Cải tiến**: tách logic thành state machine rõ ràng

### 6.5. Duplicate order_id

**Triệu chứng**: ICS reject vì orderId đã tồn tại

**Nguyên nhân**:
- `payload_sent_ICS()` generate orderId từ timestamp + node_id
- Nếu 2 pairs tạo cùng lúc có thể trùng

**Cải tiến**:
- Thêm UUID vào orderId
- Check orderId unique trước khi gửi

### 6.6. Validate pairs không sync với DB

**Triệu chứng**: pair ready nhưng không trong validate_pairs → không gửi

**Nguyên nhân**:
- `validate_pairs` load 1 lần lúc startup
- Nếu DB update sau khi runtime start → không sync

**Cải tiến**:
- Reload validate_pairs định kỳ (mỗi 5 phút)
- Hoặc dùng MongoDB Change Streams

## 7. Notes + cải tiến

### 7.1. Hiện trạng

- **30s fixed threshold**: không configurable per node
- **No retry for failed webhooks**: pair lost nếu ICS down
- **No state persistence**: restart → mất tất cả state/timers
- **Complex double task logic**: khó maintain

### 7.2. Cải tiến đề xuất

#### a) Configurable timer threshold

```python
# Trong MongoDB node_id collection:
{
  "node_id": "start_1",
  "timer_threshold": 30,  # seconds (default)
  ...
}

# Hoặc per node type:
{
  "start_*": 30,
  "end_*": 25,
  "start_vip_*": 10  # VIP area nhanh hơn
}
```

#### b) Webhook retry với exponential backoff

```python
class WebhookClient:
    def __init__(self, url, max_retries=3):
        self.url = url
        self.max_retries = max_retries
    
    def post_with_retry(self, payload):
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.url,
                    json=payload,
                    timeout=5.0
                )
                if response.status_code == 200:
                    return True, None
            except Exception as e:
                if attempt == self.max_retries - 1:
                    return False, str(e)
                time.sleep(2 ** attempt)  # 1s, 2s, 4s
        
        return False, "Max retries exceeded"
```

#### c) Dead letter queue cho failed pairs

```python
class PairManager:
    def __init__(self, ...):
        self.failed_pairs = deque(maxlen=100)
    
    def _run(self):
        ...
        success = self.post_to_ics(payload)
        if not success:
            self.failed_pairs.append({
                "payload": payload,
                "timestamp": time.time(),
                "retry_count": 0
            })
        
        # Periodic retry
        self._retry_failed_pairs()
```

Expose qua API:
```
GET /pairs/failed
[
  {
    "order_id": "...",
    "start": "start_1",
    "end": "end_1",
    "failed_at": 1234567890,
    "retry_count": 3
  }
]

POST /pairs/failed/{order_id}/retry
```

#### d) State persistence (Redis/SQLite)

```python
class StateManager:
    def __init__(self, validate_pairs, redis_client=None):
        self.redis = redis_client
        if self.redis:
            self._restore_state()
    
    def _restore_state(self):
        # Load from Redis
        for node_id in self.redis.scan_iter("state:*"):
            data = self.redis.hgetall(node_id)
            self.points[node_id] = data
    
    def get_state_nodes(self, node_id, state):
        # Update logic
        ...
        # Persist to Redis
        if self.redis:
            self.redis.hmset(f"state:{node_id}", self.points[node_id])
```

→ Restart không mất state

#### e) Simplify double task logic với state machine

```python
class EmptyCarStateMachine:
    states = ["WAITING", "PENDING", "PAIRED", "TIMEOUT"]
    
    def __init__(self, start_empty):
        self.start = start_empty
        self.state = "WAITING"
        self.deadline = None
    
    def on_ready(self):
        self.state = "PENDING"
        self.deadline = time.time() + 15
    
    def can_pair_with(self, normal_pair):
        return self.state == "PENDING" and time.time() < self.deadline
    
    def on_paired(self, normal_pair):
        self.state = "PAIRED"
    
    def on_timeout(self):
        self.state = "TIMEOUT"
```

#### f) Monitoring/alerting

```python
class PairMetrics:
    def __init__(self):
        self.pairs_sent = 0
        self.pairs_failed = 0
        self.double_tasks = 0
        self.empty_timeouts = 0
        self.avg_wait_time = deque(maxlen=100)
    
    def get_health(self):
        fail_rate = self.pairs_failed / (self.pairs_sent + 1)
        return {
            "total_pairs": self.pairs_sent,
            "fail_rate": fail_rate,
            "double_rate": self.double_tasks / (self.pairs_sent + 1),
            "avg_wait_time": np.mean(self.avg_wait_time),
            "health": "OK" if fail_rate < 0.05 else "DEGRADED"
        }
```

Expose qua API:
```
GET /pairs/metrics
{
  "total_pairs": 1234,
  "fail_rate": 0.02,
  "double_rate": 0.15,
  "avg_wait_time": 32.5,
  "health": "OK"
}
```

#### g) Validate pairs hot reload

```python
class PairManager:
    def __init__(self, ...):
        self._validate_pairs_refresh_interval = 300  # 5 phút
        self._last_refresh = time.time()
    
    async def _refresh_validate_pairs(self):
        new_pairs = await ValidatePairsService().get_validate_pairs_all()
        if new_pairs != self.validate_pairs:
            logger.info(f"Validate pairs updated: {len(new_pairs)} pairs")
            self.validate_pairs = new_pairs
            self.state_manager.validate_pairs = new_pairs
```

### 7.3. Testing checklist

- [ ] Test timer 30s threshold (mock time.time)
- [ ] Test race condition (multiple cameras update same node)
- [ ] Test ICS webhook retry
- [ ] Test double task logic (empty + normal)
- [ ] Test empty timeout (15s)
- [ ] Test payload format (single/double/empty)
- [ ] Test state persistence (restart)

### 7.4. Business logic validation

- [ ] Verify validate_pairs format trong DB
- [ ] Check ICS_URL config
- [ ] Confirm end_point_empty mapping
- [ ] Test snapshot logic (nếu enable)
- [ ] Verify orderId format acceptable by ICS
