# Camera Processing Flow (RTSP → Inference)

## 1. Mô tả usecase

Mỗi camera chạy trong 1 thread riêng, decode RTSP stream bằng FFmpeg GPU (NVDEC), đẩy frame vào inference queue chung, nhận detection results, và cập nhật state theo ROI.

## 2. Actors

- **CameraManager**: khởi tạo và quản lý N camera threads
- **CameraProcessor (Thread)**: thread per camera, đọc frame và xử lý ROI
- **GPUVideoDecoder**: wrapper FFmpeg NVDEC, decode RTSP → raw BGR frames
- **InferenceEngine**: shared inference service (nhận frames từ tất cả cameras)
- **StateManager**: lưu trữ state của các node (start_*/end_*)
- **SnapshotManager** (optional): lưu snapshot khi có event

## 3. Flow

### 3.1. Camera Initialization

```
CameraManager.start()
    └─> FOR each camera in cameras_config:
        ├─> parse camera config (url, rois, cameraId)
        ├─> cam_id = f"cam_{index}_{cameraId}"
        │
        ├─> result_queue = Queue(maxsize=10)
        ├─> inference_engine.register_camera(cam_id, result_queue)
        │
        ├─> rois_internal = _get_internal_rois(cam)
        │   └─> convert rois dict → [{"node_id": str, "roi": [x,y,w,h]}]
        │
        └─> thread = CameraProcessor(
                rtsp=cam_url,
                rois=rois_internal,
                state_manager=state_manager,
                inference_engine=inference_engine,
                result_queue=result_queue,
                cam_id=cam_id,
                enabled_ref=self.enabled,
                camera_index=i,
                latest_frames_ref=self.latest_frames
            )
            └─> thread.start()
```

### 3.2. Camera Processing Loop

```
CameraProcessor.run() [Thread]
    └─> WHILE running:
        ├─> IF not _is_enabled():
        │   ├─> cap.release() if cap
        │   └─> sleep(1) → CONTINUE
        │
        ├─> IF cap is None or not cap.isOpened():
        │   ├─> cap = GPUVideoDecoder(self.rtsp)
        │   ├─> IF not cap.isOpened():
        │   │   └─> log error → sleep(2) → CONTINUE
        │   │
        │   └─> cap.wait_ready(timeout=10.0)
        │       └─> IF timeout:
        │           └─> cap.release() → sleep(2) → CONTINUE
        │
        ├─> ret, frame = cap.read()
        ├─> IF not ret:
        │   └─> log warning → cap.release() → sleep(1) → CONTINUE
        │
        ├─> latest_frames_ref[cam_id] = frame.copy()
        │   └─> (phục vụ streaming API)
        │
        ├─> inference_engine.put_frame_with_drop(frame, cam_id)
        │   └─> đẩy (frame, cam_id) vào shared_queue
        │       └─> IF queue full: drop oldest frame
        │
        ├─> detections = result_queue.get(timeout=0.1)
        │   └─> IF timeout: log warning → sleep(0.01) → CONTINUE
        │
        ├─> with _detections_lock:
        │   └─> latest_detections = detections (cache cho streaming)
        │
        └─> FOR roi_dict in rois:
            ├─> node_id = roi_dict["node_id"]
            ├─> roi = roi_dict["roi"]
            │
            ├─> has_obj, coverage = has_object_in_roi(
            │       detections, roi, node_id, use_gpu=True
            │   )
            │
            ├─> state_manager.get_state_nodes(node_id, has_obj)
            │   └─> update state và timer cho node_id
            │
            └─> IF snapshot_manager:
                └─> snapshot_manager.update_frame(node_id, frame)
        
        └─> sleep(0.01)  # throttle
```

### 3.3. GPU Decoder Internal Flow

```
GPUVideoDecoder.__init__(rtsp_url)
    └─> _start_decode()
        ├─> spawn FFmpeg subprocess:
        │   ffmpeg -hwaccel cuda -rtsp_transport tcp \
        │          -i {rtsp_url} -f rawvideo -pix_fmt bgr24 \
        │          -s 640x480 -
        │   └─> stdout → pipe raw BGR data
        │
        └─> thread = Thread(target=_decode_loop, daemon=True)
            └─> _decode_loop():
                └─> WHILE running:
                    ├─> raw = process.stdout.read(frame_size)
                    ├─> frame = np.frombuffer(raw).reshape(H,W,3)
                    │
                    ├─> IF first_frame:
                    │   └─> _ready.set()  # signal ready event
                    │
                    ├─> IF queue.full():
                    │   └─> queue.get_nowait()  # drop oldest
                    │
                    └─> queue.put(frame)
```

### 3.4. Enable/Disable Flow

```
CameraControlService.toggle_camera(camera_id)
    └─> index = find_camera_index(camera_manager, camera_id)
    └─> with camera_manager._enabled_lock:
        └─> camera_manager.enabled[index] = not enabled[index]
    
    └─> IF enabled_count > 0:
        └─> inference_engine.resume()
    └─> ELSE:
        └─> inference_engine.pause()
```

Trong `CameraProcessor.run()`:
```
IF not _is_enabled():
    → release decoder → sleep(1)
```

## 4. Data flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Camera Thread (per cam)                  │
│                                                             │
│  ┌──────────────┐    raw BGR    ┌────────────────────┐    │
│  │ RTSP camera  ├──────────────>│ GPUVideoDecoder    │    │
│  │ (H264/RTSP)  │                │ (FFmpeg NVDEC)     │    │
│  └──────────────┘                │ - subprocess       │    │
│                                   │ - decode thread    │    │
│                                   │ - queue(size=3)    │    │
│                                   └─────────┬──────────┘    │
│                                             │ read()         │
│                                   ┌─────────▼──────────┐    │
│                                   │ CameraProcessor    │    │
│                                   │ .run() loop        │    │
│                                   └─────────┬──────────┘    │
│                                             │                │
│  ┌──────────────────────────────────────────┼──────────┐   │
│  │                                          │           │   │
│  │  (1) latest_frames_ref[cam_id] ←─ frame.copy()     │   │
│  │      └─> phục vụ streaming API                      │   │
│  │                                                      │   │
│  │  (2) inference_engine.put_frame_with_drop(frame)    │   │
│  │      └─> shared_queue ─────────────────────────┐    │   │
│  │                                                 │    │   │
│  │  (3) detections ← result_queue.get(timeout)    │    │   │
│  │      └─> từ InferenceEngine                    │    │   │
│  │                                                 │    │   │
│  │  (4) FOR roi in rois:                          │    │   │
│  │      ├─> has_obj = has_object_in_roi(...)      │    │   │
│  │      └─> state_manager.get_state_nodes(...)    │    │   │
│  │          └─> update timers/ready_lists         │    │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ (2) frames to inference
                         ▼
         ┌───────────────────────────┐
         │   InferenceEngine Thread  │
         │   - shared_queue          │
         │   - batch + CUDA streams  │
         └───────────┬───────────────┘
                     │ (3) distribute detections
                     └──> result_queue per camera
```

## 5. Communication

### 5.1. Inter-thread Communication

**Queues**:
- `InferenceEngine.shared_queue`: `(frame, cam_id)` từ tất cả camera threads
- `CameraProcessor.result_queue`: detections từ `InferenceEngine` cho từng camera riêng

**Shared State** (với lock):
- `CameraManager.enabled`: list[bool] - enable/disable per camera
- `CameraManager.latest_frames`: dict[cam_id, frame] - frame cache cho streaming
- `CameraProcessor.latest_detections`: cached detections cho streaming API

**Synchronization**:
- `CameraManager._enabled_lock`: protect enabled list
- `CameraProcessor._detections_lock`: protect latest_detections
- `GPUVideoDecoder._ready`: Event signal khi frame đầu tiên decode xong

### 5.2. FFmpeg Process Communication

- **stdin**: không dùng (FFmpeg tự kết nối RTSP)
- **stdout**: pipe raw BGR data (640x480x3 bytes per frame)
- **stderr**: DEVNULL (bỏ qua log)

## 6. Error points

### 6.1. RTSP connection failed

**Triệu chứng**: `cap.isOpened() = False`

**Nguyên nhân**:
- Camera offline/network unreachable
- RTSP credentials sai
- URL format sai

**Xử lý hiện tại**:
- Log error
- Sleep 2s và retry trong loop
- Camera thread không die, chờ camera sống lại

**Cải tiến**:
- Exponential backoff cho retry (2s → 4s → 8s → max 60s)
- Alert nếu camera offline quá N phút

### 6.2. Decoder timeout (first frame)

**Triệu chứng**: `wait_ready(timeout=10)` return False

**Nguyên nhân**:
- RTSP stream chậm (buffering)
- Network congestion
- FFmpeg không nhận được keyframe

**Xử lý hiện tại**:
- Release decoder và retry

**Cải tiến**:
- Tăng timeout cho camera xa/slow network
- Thêm metrics: time to first frame

### 6.3. Frame loss / inference timeout

**Triệu chứng**: `result_queue.get(timeout=0.1)` throw Empty

**Nguyên nhân**:
- InferenceEngine quá tải (batch chậm)
- Camera push frame nhanh hơn inference
- Shared queue drop frame của camera này

**Xử lý hiện tại**:
- Log warning
- Skip frame và continue (không block thread)

**Cải tiến**:
- Adaptive frame rate (giảm FPS nếu inference lag)
- Priority queue (camera quan trọng ưu tiên)

### 6.4. FFmpeg process crash

**Triệu chứng**: `cap.read()` return `ret=False`

**Nguyên nhân**:
- FFmpeg segfault (driver issue)
- RTSP stream bị disconnect
- Out of memory

**Xử lý hiện tại**:
- `cap.release()` → kill FFmpeg process
- Retry trong loop

**Cải tiến**:
- Monitor FFmpeg stderr để phát hiện error pattern
- Restart FFmpeg với tham số khác nếu fail liên tục

### 6.5. Memory leak (frame accumulation)

**Triệu chứng**: RAM tăng dần

**Nguyên nhân**:
- `latest_frames_ref` giữ frame copy (640x480x3 ~ 1MB per cam)
- Không có GC nếu camera thread die nhưng entry vẫn trong dict

**Cải tiến**:
- Cleanup `latest_frames[cam_id]` khi camera thread stop
- Sử dụng weak reference hoặc LRU cache

### 6.6. ROI detection false positive/negative

**Triệu chứng**: state manager update sai

**Nguyên nhân**:
- ROI config sai (tọa độ ngoài frame)
- Detection confidence thấp
- Object nhỏ bị model miss

**Debug**:
- Check `has_object_in_roi()` logic
- Visualize ROI + detections bằng streaming API
- Tune threshold trong `config.py`

## 7. Notes + cải tiến

### 7.1. Hiện trạng

- **Fixed resolution**: 640x480 hardcode trong `GPUVideoDecoder`
- **No adaptive FPS**: camera luôn đẩy frame với FPS max của RTSP stream
- **CPU decode fallback**: không có fallback khi GPU không available
- **Single ROI check per frame**: mỗi frame chỉ check ROI 1 lần (không track object across frames)

### 7.2. Cải tiến đề xuất

#### a) Dynamic resolution

```python
# Trong CameraManager config
camera_config = {
    "url": "rtsp://...",
    "resolution": "1280x720",  # cho camera quan trọng
    ...
}

# GPUVideoDecoder parse resolution từ config
```

#### b) Adaptive frame rate

```python
class CameraProcessor:
    def __init__(self, ..., target_fps=10):
        self.target_fps = target_fps
        self.frame_interval = 1.0 / target_fps
    
    def run(self):
        last_frame_time = 0
        while running:
            ret, frame = cap.read()
            now = time.time()
            if now - last_frame_time < self.frame_interval:
                continue  # skip frame
            last_frame_time = now
            ...
```

→ Giảm load inference nếu không cần FPS cao

#### c) CPU decode fallback

```python
class VideoDecoder:
    def __init__(self, rtsp_url, use_gpu=True):
        if use_gpu and has_cuda():
            self.decoder = GPUVideoDecoder(...)
        else:
            self.decoder = cv2.VideoCapture(rtsp_url)
```

→ Hệ thống vẫn chạy khi GPU bị lỗi

#### d) Object tracking across frames

Thay vì chỉ check "có object trong ROI không", track object ID:
- Dùng DeepSORT/ByteTrack
- Mapping object_id → node_id
- Detect "object enter/exit ROI" chính xác hơn

→ Giảm false positive do object nháy nháy

#### e) ROI validation on startup

```python
def _validate_rois(self, cam_config):
    frame_width = 640
    frame_height = 480
    for roi in cam_config["rois"]:
        x, y, w, h = roi["roi"]
        if x + w > frame_width or y + h > frame_height:
            logger.error(f"ROI out of bounds: {roi}")
```

→ Catch config error sớm

#### f) Reconnect strategy tuning

```python
class ReconnectStrategy:
    def __init__(self):
        self.retry_count = 0
        self.backoff = [2, 4, 8, 16, 30, 60]  # seconds
    
    def get_delay(self):
        idx = min(self.retry_count, len(self.backoff) - 1)
        return self.backoff[idx]
    
    def on_retry(self):
        self.retry_count += 1
    
    def on_success(self):
        self.retry_count = 0
```

#### g) Health metrics per camera

```python
class CameraMetrics:
    def __init__(self):
        self.frames_received = 0
        self.frames_dropped = 0
        self.inference_timeouts = 0
        self.reconnect_count = 0
        self.last_frame_timestamp = None
    
    def get_fps(self):
        # calculate actual FPS
        ...
    
    def get_health_score(self):
        # 0-100 score based on metrics
        ...
```

Expose qua API:
```
GET /cameras/{cam_id}/metrics
{
  "fps": 24.5,
  "drop_rate": 0.02,
  "health_score": 95
}
```

### 7.3. Performance tuning checklist

- [ ] FFmpeg buffer size (`GPU_DECODE_BUFFER_SIZE`)
- [ ] Queue size (GPUVideoDecoder=3, result_queue=10)
- [ ] Frame resolution vs GPU memory
- [ ] Target FPS vs inference latency
- [ ] ROI complexity (số lượng ROI per camera)
- [ ] Snapshot enable/disable (overhead)

### 7.4. Monitoring/Debug tools

- [ ] Log FPS thực tế per camera
- [ ] Log inference timeout rate
- [ ] Log reconnect frequency
- [ ] Streaming endpoint để visualize ROI + detections
- [ ] Endpoint toggle enable/disable camera realtime
