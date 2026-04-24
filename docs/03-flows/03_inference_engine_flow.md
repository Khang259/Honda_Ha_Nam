# Inference Engine Flow (Batch + CUDA Streams)

## 1. Mô tả usecase

Tập trung tất cả inference từ N camera vào 1 engine duy nhất, gom batch frames để tăng throughput GPU, và sử dụng CUDA streams để chạy inference async (overlap transfer + compute).

## 2. Actors

- **InferenceEngine (Thread)**: thread chính quản lý inference pipeline
- **CameraProcessor threads**: producer - đẩy frames vào shared_queue
- **YOLO model**: Ultralytics YOLO (TensorRT engine)
- **CUDA streams**: PyTorch CUDA streams cho async execution
- **Result queues**: per-camera queues để trả detections về đúng camera

## 3. Flow

### 3.1. Initialization

```
InferenceEngine.__init__(
    model_path,
    max_queue_size=500,
    max_batch_size=24,
    batch_timeout=1.0,
    num_streams=3,
    initial_paused=True
)
    ├─> shared_queue = Queue(maxsize=max_queue_size)
    ├─> result_queues = {}  # {cam_id: Queue}
    ├─> streams = []  # CUDA streams
    ├─> pending_batches = deque(maxlen=num_streams*2)
    └─> _paused = Event()
        └─> IF initial_paused: _paused.set()

RuntimeService.start()
    └─> inference_engine = InferenceEngine(...)
    └─> inference_engine.start()
        └─> Thread.start() → run()
            └─> _load_model()
                ├─> model = YOLO(model_path, verbose=False)
                └─> streams = [torch.cuda.Stream() for _ in range(num_streams)]
```

### 3.2. Main Inference Loop

```
InferenceEngine.run() [Thread]
    └─> WHILE running:
        ├─> IF _paused.is_set():
        │   └─> sleep(0.05) → CONTINUE
        │
        ├─> batch_frames, cam_ids = _collect_batch()
        │   └─> WHILE len(batch) < max_batch_size:
        │       ├─> timeout = batch_timeout - elapsed
        │       ├─> IF timeout <= 0: BREAK
        │       │
        │       └─> TRY:
        │           └─> frame, cam_id = shared_queue.get(timeout)
        │           └─> batch.append(frame)
        │           └─> cam_ids.append(cam_id)
        │
        ├─> IF len(batch_frames) > 0:
        │   ├─> stream = streams[stream_idx]
        │   ├─> results, event = _async_inference(batch_frames, stream)
        │   │   └─> with torch.cuda.stream(stream):
        │   │       ├─> results = model(batch_frames, conf=0.3, max_det=15, ...)
        │   │       ├─> output = [result.boxes.data for result in results]
        │   │       └─> event = stream.record_event()
        │   │
        │   ├─> pending_batches.append({
        │   │       'results': results,
        │   │       'cam_ids': cam_ids,
        │   │       'event': event,
        │   │       'timestamp': time.time()
        │   │   })
        │   │
        │   └─> stream_idx = (stream_idx + 1) % num_streams
        │
        ├─> FOR i, batch_info in enumerate(pending_batches):
        │   └─> IF batch_info['event'].query():  # check if CUDA event done
        │       ├─> _distribute_results(batch_info['results'], batch_info['cam_ids'])
        │       │   └─> FOR detection, cam_id in zip(results, cam_ids):
        │       │       └─> result_queues[cam_id].put_nowait(detection)
        │       │           └─> IF queue full: drop oldest
        │       │
        │       └─> mark completed → remove from pending_batches
        │
        └─> IF no frames and no pending:
            └─> sleep(0.5)
```

### 3.3. Frame Submission (from CameraProcessor)

```
CameraProcessor.run()
    └─> inference_engine.put_frame_with_drop(frame, cam_id)
        └─> TRY:
            └─> shared_queue.put_nowait((frame, cam_id))
        └─> EXCEPT queue.Full:
            ├─> dropped_frame, _ = shared_queue.get_nowait()
            └─> shared_queue.put_nowait((frame, cam_id))
                └─> (drop oldest frame)
```

### 3.4. Pause/Resume (linked with camera enable/disable)

```
CameraControlService.toggle_camera(camera_id)
    └─> camera_manager.enabled[index] = new_value
    └─> enabled_count = sum(enabled)
    └─> IF enabled_count > 0:
        └─> inference_engine.resume()
            └─> _paused.clear()
    └─> ELSE:
        └─> inference_engine.pause()
            └─> _paused.set()
```

## 4. Data flow

```
┌────────────────────────────────────────────────────────────┐
│           Multiple CameraProcessor Threads                 │
│  Thread 1         Thread 2         ...        Thread N     │
│  (cam_0_101)      (cam_1_102)                 (cam_N_...)  │
└───────┬──────────────┬──────────────────────────┬──────────┘
        │              │                          │
        │ put_frame_with_drop(frame, cam_id)     │
        │              │                          │
        └──────────────┼──────────────────────────┘
                       ▼
        ┌──────────────────────────────┐
        │  InferenceEngine.shared_queue│
        │  Queue(maxsize=500)          │
        │  [(frame, cam_id), ...]      │
        └──────────────┬───────────────┘
                       │
                       │ _collect_batch()
                       │ └─> gom max_batch_size frames
                       │     hoặc timeout sau batch_timeout
                       ▼
        ┌──────────────────────────────┐
        │  Batch: [frame1, frame2, ...] │
        │  Cam IDs: [cam_0, cam_1, ...]│
        └──────────────┬───────────────┘
                       │
                       │ _async_inference(batch, stream)
                       ▼
        ┌──────────────────────────────────────────────┐
        │        CUDA Stream Pipeline                  │
        │                                              │
        │  Stream 0: ┌────────┐  ┌──────────┐        │
        │            │ Batch A│->│ Inference│-> Event│
        │            └────────┘  └──────────┘        │
        │                                              │
        │  Stream 1:     ┌────────┐  ┌──────────┐    │
        │                │ Batch B│->│ Inference│->E │
        │                └────────┘  └──────────┘    │
        │                                              │
        │  Stream 2:         ┌────────┐  ┌────────┐  │
        │                    │ Batch C│->│ Infer  │->E│
        │                    └────────┘  └────────┘  │
        └──────────────────────────┬───────────────────┘
                                   │
                                   │ event.query() → check done
                                   │ _distribute_results()
                                   ▼
        ┌────────────────────────────────────────────┐
        │  Result Queues (per camera)                │
        │  result_queues[cam_0] → Queue(maxsize=10)  │
        │  result_queues[cam_1] → Queue(maxsize=10)  │
        │  ...                                       │
        └────────────────────────────────────────────┘
                       │
                       │ CameraProcessor.result_queue.get()
                       ▼
        ┌──────────────────────────────┐
        │  CameraProcessor receives     │
        │  detections (torch.Tensor)    │
        │  shape: (N, 6)                │
        │  [x1, y1, x2, y2, conf, cls]  │
        └───────────────────────────────┘
```

## 5. Communication

### 5.1. Queue-based Communication

**shared_queue** (producer-consumer):
- **Producer**: N CameraProcessor threads
- **Consumer**: 1 InferenceEngine thread
- **Data**: `(frame: np.ndarray, cam_id: str)`
- **Behavior**: drop oldest frame if full (FIFO with eviction)

**result_queues** (fan-out):
- **Producer**: InferenceEngine thread
- **Consumer**: CameraProcessor thread (per camera)
- **Data**: `detections: torch.Tensor` shape (N, 6)
- **Behavior**: drop oldest detection if full

### 5.2. CUDA Synchronization

**torch.cuda.Stream()**:
- Async execution context cho CUDA operations
- Mỗi stream có queue riêng trên GPU
- Streams chạy parallel nếu GPU có tài nguyên

**stream.record_event()**:
- Ghi marker vào stream để track completion
- `event.query()` return True khi operations complete

**Overlap strategy**:
```
Time  →
Stream 0: ████████████████  (Batch A inference)
Stream 1:     ████████████████  (Batch B inference)
Stream 2:         ████████████████  (Batch C inference)
CPU:      ▲   ▲   ▲   ▲   (collect batches + distribute)
```

## 6. Error points

### 6.1. Model load failed

**Triệu chứng**: `_load_model()` throw exception

**Nguyên nhân**:
- Model path sai (`MODEL_PATH` trong `config.py`)
- TensorRT engine không compatible với GPU
- CUDA out of memory khi load model

**Xử lý**:
- Check model file exists
- Rebuild TensorRT engine nếu GPU thay đổi
- Giảm model size hoặc tăng GPU memory

### 6.2. Shared queue overflow (frame drop)

**Triệu chứng**: log "dropped frame" nhiều lần

**Nguyên nhân**:
- Camera push frame nhanh hơn inference
- `max_queue_size` quá nhỏ
- Inference chậm (model complex/GPU yếu)

**Tác động**:
- Frame bị skip → có thể miss detection

**Cải tiến**:
- Tăng `max_queue_size` (trade-off: memory)
- Giảm camera FPS
- Upgrade GPU

### 6.3. Batch timeout không optimal

**Triệu chứng**: batch size thường < `max_batch_size`

**Nguyên nhân**:
- `batch_timeout` quá ngắn (1.0s)
- Ít camera active

**Tác động**:
- GPU underutilized (small batch = low throughput)

**Tuning**:
- Tăng `batch_timeout` nếu có nhiều camera
- Giảm `batch_timeout` nếu cần low latency

### 6.4. CUDA stream starvation

**Triệu chứng**: `pending_batches` luôn đầy

**Nguyên nhân**:
- `num_streams` quá nhiều so với GPU
- Inference chậm, stream không kịp complete

**Xử lý**:
- Giảm `num_streams` (default: 3)
- Check GPU utilization (nvidia-smi)

### 6.5. Result queue overflow (detection drop)

**Triệu chứng**: camera thread log "Failed to deliver result"

**Nguyên nhân**:
- Camera thread xử lý chậm (ROI check phức tạp)
- Result queue size quá nhỏ (maxsize=10)

**Tác động**:
- Detection bị drop → state manager update sai

**Cải tiến**:
- Tăng result queue size
- Optimize ROI check logic

### 6.6. Memory leak (pending_batches)

**Triệu chứng**: GPU memory tăng dần

**Nguyên nhân**:
- `pending_batches` không cleanup (bug trong remove logic)
- Event không query (GPU hang)

**Debug**:
- Monitor `len(pending_batches)`
- Check event.query() luôn được gọi

### 6.7. Pause/resume race condition

**Triệu chứng**: inference không pause khi tất cả camera disabled

**Nguyên nhân**:
- Race giữa `_paused.set()` và inference loop

**Xử lý hiện tại**:
- Check `_paused.is_set()` đầu mỗi loop
- Paused state không block model load

## 7. Notes + cải tiến

### 7.1. Hiện trạng

- **Fixed batch params**: batch_size/timeout hardcode trong config
- **No priority**: tất cả camera có priority bằng nhau trong queue
- **Single model**: chỉ hỗ trợ 1 model cho tất cả cameras
- **No warmup**: model chạy ngay khi start (first batch chậm)

### 7.2. Cải tiến đề xuất

#### a) Dynamic batching

Thay vì fixed timeout, adaptive:
```python
def _adaptive_batch_timeout(self):
    queue_depth = self.shared_queue.qsize()
    if queue_depth > 0.8 * self.max_queue_size:
        return 0.1  # nhanh lấy frame tránh overflow
    elif queue_depth < 0.2 * self.max_queue_size:
        return 2.0  # chờ lâu để gom batch lớn
    else:
        return self.batch_timeout  # default
```

#### b) Priority queue

Camera quan trọng (vị trí cổng ra vào) ưu tiên:
```python
shared_queue = PriorityQueue()

# Camera thread push
priority = 1 if camera.is_critical else 5
shared_queue.put((priority, (frame, cam_id)))
```

#### c) Multi-model support

```python
class InferenceEngine:
    def __init__(self, model_configs):
        self.engines = {
            "default": YOLOEngine("model_v1.engine"),
            "highres": YOLOEngine("model_v2.engine")
        }
    
    def register_camera(self, cam_id, result_queue, model_name="default"):
        self.camera_model_map[cam_id] = model_name
```

#### d) Model warmup

```python
def _warmup_model(self):
    logger.info("Warming up model...")
    dummy_batch = [np.zeros((480, 640, 3), dtype=np.uint8)] * self.max_batch_size
    for _ in range(5):
        _ = self.model(dummy_batch, verbose=False)
    logger.info("Model warmed up")
```

#### e) Inference metrics

```python
class InferenceMetrics:
    def __init__(self):
        self.batch_sizes = deque(maxlen=100)
        self.inference_times = deque(maxlen=100)
        self.queue_depths = deque(maxlen=100)
    
    def log_batch(self, batch_size, inference_time, queue_depth):
        self.batch_sizes.append(batch_size)
        self.inference_times.append(inference_time)
        self.queue_depths.append(queue_depth)
    
    def get_stats(self):
        return {
            "avg_batch_size": np.mean(self.batch_sizes),
            "avg_inference_time": np.mean(self.inference_times),
            "avg_queue_depth": np.mean(self.queue_depths),
            "throughput_fps": sum(self.batch_sizes) / sum(self.inference_times)
        }
```

Expose qua API:
```
GET /inference/metrics
{
  "avg_batch_size": 18.5,
  "avg_inference_time": 0.045,
  "throughput_fps": 410.0,
  "gpu_utilization": 0.85
}
```

#### f) Backpressure mechanism

Khi inference quá tải, thông báo camera threads giảm FPS:
```python
# InferenceEngine
def _check_backpressure(self):
    queue_depth = self.shared_queue.qsize()
    if queue_depth > 0.9 * self.max_queue_size:
        return "HIGH"  # camera cần giảm FPS
    elif queue_depth > 0.7 * self.max_queue_size:
        return "MEDIUM"
    else:
        return "LOW"

# CameraProcessor check
backpressure = inference_engine.get_backpressure()
if backpressure == "HIGH":
    time.sleep(0.1)  # throttle
```

#### g) Multi-GPU support

Distribute cameras across GPUs:
```python
class MultiGPUInferenceEngine:
    def __init__(self, model_path, gpu_ids=[0, 1]):
        self.engines = [
            InferenceEngine(model_path, device=f"cuda:{gpu_id}")
            for gpu_id in gpu_ids
        ]
        self.camera_to_engine = {}  # round-robin assignment
    
    def register_camera(self, cam_id, result_queue):
        engine_idx = len(self.camera_to_engine) % len(self.engines)
        self.engines[engine_idx].register_camera(cam_id, result_queue)
        self.camera_to_engine[cam_id] = engine_idx
```

### 7.3. Performance tuning checklist

**Batch parameters**:
- [ ] `INFERENCE_MAX_BATCH_SIZE`: 24 (tốt cho RTX 3090), 16 (RTX 3060)
- [ ] `INFERENCE_BATCH_TIMEOUT`: 1.0s (balance latency/throughput)
- [ ] `INFERENCE_MAX_QUEUE_SIZE`: 500 (buffer ~20s với 24fps)

**CUDA streams**:
- [ ] `INFERENCE_NUM_STREAMS`: 3 (overlap 3 batches)
- [ ] Tăng nếu GPU có nhiều SMs (Streaming Multiprocessors)

**Model optimization**:
- [ ] TensorRT FP16 (2x faster vs FP32)
- [ ] Batch size phải chia hết cho 8 (Tensor Core optimization)
- [ ] Input size 640x640 (YOLO optimal)

**Memory**:
- [ ] Monitor GPU memory: `nvidia-smi -l 1`
- [ ] Estimate: batch_size * (640*640*3) + model_weights + activations

### 7.4. Monitoring dashboard

Key metrics cần track:
- [ ] Throughput (FPS tổng của tất cả cameras)
- [ ] Average batch size (mục tiêu: gần `max_batch_size`)
- [ ] Queue depth (mục tiêu: 20-50% để có buffer)
- [ ] GPU utilization (mục tiêu: >80%)
- [ ] Inference latency per batch (mục tiêu: <50ms)
- [ ] Frame drop rate (mục tiêu: <1%)
