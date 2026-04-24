# Streaming API Flow (MJPEG Video + Overlay)

## 1. Mô tả usecase

Cung cấp HTTP endpoint để stream video realtime từ camera với overlay detections (bounding boxes) và ROIs, phục vụ monitoring/debugging. Stream dạng MJPEG (Motion JPEG) - simple protocol, không cần WebRTC/HLS.

## 2. Actors

- **StreamingService**: service xử lý logic streaming
- **FastAPI route** (`/streaming/video/{cam_id_param}`): HTTP endpoint
- **CameraManager**: cung cấp `latest_frames` và detections cache
- **MongoNodeIdClient**: lấy ROI config từ MongoDB
- **Browser/Client**: consumer của MJPEG stream

## 3. Flow

### 3.1. Endpoint Setup

```
api/app_factory.py
    └─> app.include_router(streaming_router, prefix="/streaming", tags=["streaming"])

api/routes/streaming.py
    └─> @router.get("/video/{cam_id_param}")
        └─> StreamingService.get_video_feed(cam_id_param)
```

### 3.2. Stream Request Flow

```
Client (Browser)
    └─> GET /streaming/video/{cam_id_param}
        └─> cam_id_param có thể là:
            ├─> "101" (cameraId số)
            └─> "cam_0_101" (full cam_id)

StreamingService.get_video_feed(cam_id_param)
    └─> return StreamingResponse(
            generate_mjpeg_stream(cam_id_param),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )
```

### 3.3. MJPEG Stream Generation Loop

```
StreamingService.generate_mjpeg_stream(cam_id_param) [async generator]
    ├─> cam_id = await _resolve_cam_id(cam_id_param)
    │   └─> IF cam_id_param in latest_frames:
    │       └─> return cam_id_param (đã là full cam_id)
    │   └─> ELSE:
    │       └─> TRY parse as cameraId (int)
    │       └─> FOR key in latest_frames.keys():
    │           └─> IF key.endswith(f"_{cameraId}"):
    │               └─> return key
    │
    └─> WHILE True:
        ├─> IF not api_state.camera_manager:
        │   └─> log error → sleep(1) → CONTINUE
        │
        ├─> latest_frames = api_state.camera_manager.latest_frames
        ├─> IF cam_id not in latest_frames:
        │   └─> log warning → sleep(0.5) → CONTINUE
        │
        ├─> frame = latest_frames[cam_id].copy()
        │   └─> (get snapshot từ CameraProcessor)
        │
        ├─> detections = camera_manager.get_camera_detections(cam_id)
        │   └─> FOR thread in camera_manager.threads:
        │       └─> IF thread.cam_id == cam_id:
        │           └─> with thread._detections_lock:
        │               └─> return thread.latest_detections
        │
        ├─> rois = await _get_rois_from_mongo(cam_id)
        │   └─> parse cameraId từ cam_id string (format: cam_0_101)
        │   └─> all_cameras = await mongo_client.get_all()
        │   └─> FOR cam_doc in all_cameras:
        │       └─> IF cam_doc["cameraId"] == cameraId:
        │           └─> return cam_doc.get("rois", {})
        │
        ├─> annotated_frame = draw_detections_and_rois(frame, detections, rois)
        │   └─> (vẽ bounding boxes + ROI rectangles lên frame)
        │
        ├─> success, buffer = cv2.imencode(
        │       '.jpg',
        │       annotated_frame,
        │       [cv2.IMWRITE_JPEG_QUALITY, 85]
        │   )
        │
        ├─> IF not success:
        │   └─> log error → sleep(0.1) → CONTINUE
        │
        └─> yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                buffer.tobytes() +
                b'\r\n'
            )
        
        └─> await asyncio.sleep(1.0 / target_fps)  # default: 10 FPS
```

### 3.4. Frame Overlay (draw_detections_and_rois)

```
utils/draw_detections.py
    └─> draw_detections_and_rois(frame, detections, rois)
        ├─> frame_copy = frame.copy()
        │
        ├─> IF detections is not None:
        │   └─> FOR detection in detections:  # shape (N, 6)
        │       ├─> x1, y1, x2, y2, conf, cls = detection
        │       ├─> cv2.rectangle(frame_copy, (x1, y1), (x2, y2), (0, 255, 0), 2)
        │       └─> cv2.putText(frame_copy, f"{conf:.2f}", ...)
        │
        ├─> IF rois is not None:
        │   └─> FOR roi_id, roi_data in rois.items():
        │       ├─> x, y, w, h = roi_data["roi"]
        │       ├─> cv2.rectangle(frame_copy, (x, y), (x+w, y+h), (255, 0, 0), 2)
        │       └─> cv2.putText(frame_copy, roi_id, ...)
        │
        └─> return frame_copy
```

## 4. Data flow

```
┌───────────────────────────────────────────────────────────┐
│                   Client (Browser/VLC)                    │
│  <img src="http://host:port/streaming/video/101">        │
└───────────────────────┬───────────────────────────────────┘
                        │
                        │ HTTP GET /streaming/video/101
                        ▼
        ┌───────────────────────────────────┐
        │    FastAPI Route                  │
        │    /streaming/video/{cam_id}      │
        └───────────────┬───────────────────┘
                        │
                        │ call StreamingService
                        ▼
        ┌───────────────────────────────────┐
        │   StreamingService                │
        │   .generate_mjpeg_stream()        │
        └───────────────┬───────────────────┘
                        │
        ┌───────────────┼───────────────────┐
        │               │                   │
        │   (1) resolve cam_id              │
        │       └─> "101" → "cam_0_101"     │
        │               │                   │
        │   (2) get frame                   │
        │       └─> camera_manager          │
        │           .latest_frames[cam_id]  │
        │               │                   │
        │   (3) get detections              │
        │       └─> camera_manager          │
        │           .get_camera_detections()│
        │               │                   │
        │   (4) get ROIs from MongoDB       │
        │       └─> mongo_client.get_all()  │
        │               │                   │
        └───────────────┼───────────────────┘
                        │
                        │ draw_detections_and_rois()
                        ▼
        ┌───────────────────────────────────┐
        │  Annotated Frame (numpy array)    │
        │  - bounding boxes (green)         │
        │  - ROI rectangles (blue)          │
        │  - labels + confidence            │
        └───────────────┬───────────────────┘
                        │
                        │ cv2.imencode('.jpg', quality=85)
                        ▼
        ┌───────────────────────────────────┐
        │  JPEG buffer                      │
        └───────────────┬───────────────────┘
                        │
                        │ yield MJPEG frame với boundary
                        ▼
        ┌───────────────────────────────────┐
        │  HTTP Response Stream             │
        │  Content-Type: multipart/x-mixed- │
        │                replace;           │
        │                boundary=frame     │
        │                                   │
        │  --frame\r\n                      │
        │  Content-Type: image/jpeg\r\n\r\n │
        │  <JPEG data>\r\n                  │
        │  --frame\r\n                      │
        │  ...                              │
        └───────────────────────────────────┘
```

## 5. Communication

### 5.1. HTTP Protocol

**MJPEG (Motion JPEG over HTTP)**:
- Content-Type: `multipart/x-mixed-replace; boundary=frame`
- Mỗi frame là 1 part trong multipart response
- Browser tự động parse và hiển thị liên tục

**Frame format**:
```
--frame\r\n
Content-Type: image/jpeg\r\n\r\n
<binary JPEG data>
\r\n
--frame\r\n
...
```

### 5.2. Internal Communication

**Shared memory access** (no lock):
- `CameraManager.latest_frames[cam_id]`: frame được copy từ `CameraProcessor`
- `CameraProcessor.latest_detections`: cached detections (có lock)

**MongoDB query**:
- Async query qua Motor driver
- Query mỗi frame → có thể cache để giảm load

## 6. Error points

### 6.1. cam_id không tồn tại

**Triệu chứng**: stream không có frame, log warning liên tục

**Nguyên nhân**:
- Camera chưa start
- cam_id_param sai format
- Camera bị disable

**Xử lý hiện tại**:
- Log warning và sleep 0.5s
- Retry trong vòng lặp (không throw exception)

**Client thấy**: blank/no stream

### 6.2. Frame encoding failed

**Triệu chứng**: `cv2.imencode()` return success=False

**Nguyên nhân**:
- Frame corrupt (numpy array sai shape)
- OpenCV lỗi

**Xử lý hiện tại**:
- Log error và skip frame
- Continue vòng lặp

**Client thấy**: frame freeze (vài giây)

### 6.3. MongoDB query slow/timeout

**Triệu chứng**: stream lag, FPS drop

**Nguyên nhân**:
- Query ROIs mỗi frame (10 FPS = 10 queries/s per client)
- MongoDB connection slow

**Cải tiến**:
- Cache ROIs trong StreamingService (TTL 60s)
- Hoặc lấy ROIs từ camera config trong memory

### 6.4. Multiple clients → high CPU

**Triệu chứng**: CPU spike khi nhiều browser mở stream

**Nguyên nhân**:
- Mỗi client = 1 generator instance
- Mỗi generator gọi `draw_detections_and_rois()` độc lập
- `cv2.imencode()` CPU-intensive

**Cải tiến**:
- Pre-encode annotated frame 1 lần
- Broadcast tới tất cả clients
- Hoặc giới hạn concurrent streams

### 6.5. Memory leak (frame copy)

**Triệu chứng**: RAM tăng dần khi có nhiều clients

**Nguyên nhân**:
- `frame.copy()` mỗi vòng lặp
- Generator không cleanup khi client disconnect

**Xử lý**:
- FastAPI tự cleanup generator khi client disconnect
- Nhưng nếu exception trong generator → có thể leak

### 6.6. Browser compatibility

**Triệu chứng**: stream không hiển thị trên một số browser

**Nguyên nhân**:
- Safari không hỗ trợ MJPEG tốt
- Mobile browser giới hạn

**Giải pháp**:
- Document browser support (Chrome/Firefox recommended)
- Fallback sang HLS/WebRTC cho production

## 7. Notes + cải tiến

### 7.1. Hiện trạng

- **MJPEG only**: không có HLS/WebRTC (modern protocols)
- **No authentication**: bất kỳ ai cũng có thể xem stream
- **No rate limiting**: client có thể spam requests
- **Fixed FPS**: 10 FPS hardcode, không adaptive
- **ROI query mỗi frame**: không cache

### 7.2. Cải tiến đề xuất

#### a) ROI caching

```python
class StreamingService:
    def __init__(self):
        self._roi_cache = {}  # {cam_id: (rois, expire_time)}
        self._roi_cache_ttl = 60  # seconds
    
    async def _get_rois_cached(self, cam_id):
        if cam_id in self._roi_cache:
            rois, expire = self._roi_cache[cam_id]
            if time.time() < expire:
                return rois
        
        # Fetch from MongoDB
        rois = await self._get_rois_from_mongo(cam_id)
        self._roi_cache[cam_id] = (rois, time.time() + self._roi_cache_ttl)
        return rois
```

#### b) Pre-encode optimization (broadcast)

```python
class StreamingService:
    def __init__(self):
        self._encoded_frames = {}  # {cam_id: (jpeg_buffer, timestamp)}
        self._encoder_tasks = {}   # {cam_id: asyncio.Task}
    
    async def _encode_loop(self, cam_id):
        """Background task encode frame 1 lần cho tất cả clients"""
        while True:
            frame = camera_manager.latest_frames.get(cam_id)
            detections = camera_manager.get_camera_detections(cam_id)
            rois = await self._get_rois_cached(cam_id)
            
            annotated = draw_detections_and_rois(frame, detections, rois)
            success, buffer = cv2.imencode('.jpg', annotated, ...)
            
            if success:
                self._encoded_frames[cam_id] = (buffer, time.time())
            
            await asyncio.sleep(0.1)  # 10 FPS
    
    async def generate_mjpeg_stream(self, cam_id_param):
        cam_id = await self._resolve_cam_id(cam_id_param)
        
        # Start encoder task nếu chưa có
        if cam_id not in self._encoder_tasks:
            self._encoder_tasks[cam_id] = asyncio.create_task(
                self._encode_loop(cam_id)
            )
        
        while True:
            if cam_id in self._encoded_frames:
                buffer, _ = self._encoded_frames[cam_id]
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' +
                    buffer.tobytes() +
                    b'\r\n'
                )
            
            await asyncio.sleep(0.1)
```

→ Nhiều clients chỉ encode 1 lần

#### c) Authentication

```python
@router.get("/video/{cam_id_param}")
async def stream_video(
    cam_id_param: str,
    token: str = Depends(verify_token)
):
    # Verify JWT token
    ...
    return streaming_service.get_video_feed(cam_id_param)
```

#### d) Rate limiting

```python
from slowapi import Limiter

limiter = Limiter(key_func=get_remote_address)

@router.get("/video/{cam_id_param}")
@limiter.limit("5/minute")  # max 5 streams per IP
async def stream_video(...):
    ...
```

#### e) Adaptive FPS based on client bandwidth

```python
async def generate_mjpeg_stream(self, cam_id_param, target_fps=10):
    while True:
        start = time.time()
        
        # Generate frame
        yield frame_data
        
        # Measure send time
        elapsed = time.time() - start
        
        # Adaptive delay
        if elapsed > 0.2:  # slow client
            target_fps = max(5, target_fps - 1)
        
        delay = max(0, 1.0/target_fps - elapsed)
        await asyncio.sleep(delay)
```

#### f) Fallback sang HLS/WebRTC

**HLS (HTTP Live Streaming)**:
- Segment frames thành .ts files
- Generate .m3u8 playlist
- Better browser support, adaptive bitrate

**WebRTC**:
- Low latency (<500ms vs MJPEG ~1-2s)
- Native browser support
- Requires signaling server

**Trade-off**: complexity tăng nhiều

#### g) Stream health monitoring

```python
class StreamMetrics:
    def __init__(self):
        self.active_streams = {}  # {cam_id: [client_ips]}
        self.frame_sent = Counter()
        self.encode_errors = Counter()
    
    def get_stats(self):
        return {
            "total_streams": len(self.active_streams),
            "streams_per_camera": {
                cam_id: len(clients)
                for cam_id, clients in self.active_streams.items()
            },
            "frames_sent": dict(self.frame_sent),
            "error_rate": sum(self.encode_errors.values()) / sum(self.frame_sent.values())
        }
```

Expose qua API:
```
GET /streaming/stats
{
  "total_streams": 3,
  "streams_per_camera": {
    "cam_0_101": 2,
    "cam_1_102": 1
  },
  "frames_sent": {
    "cam_0_101": 12345
  },
  "error_rate": 0.001
}
```

#### h) Quality selector

```
GET /streaming/video/{cam_id}?quality=low|medium|high

low: 480p, JPEG quality=50
medium: 640p, JPEG quality=70
high: 720p, JPEG quality=85
```

#### i) Snapshot API (single frame)

```python
@router.get("/snapshot/{cam_id}")
async def get_snapshot(cam_id: str):
    frame = camera_manager.latest_frames.get(cam_id)
    detections = camera_manager.get_camera_detections(cam_id)
    rois = await streaming_service._get_rois_cached(cam_id)
    
    annotated = draw_detections_and_rois(frame, detections, rois)
    success, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 95])
    
    return Response(content=buffer.tobytes(), media_type="image/jpeg")
```

→ Dùng để embed static image thay vì stream

### 7.3. Performance tuning checklist

**JPEG encoding**:
- [ ] Quality: 85 (balance size/quality)
- [ ] Resolution: match camera resolution (640x480)
- [ ] Encoding time: <30ms per frame (check với cProfile)

**FPS**:
- [ ] Target FPS: 10 (balance smoothness/bandwidth)
- [ ] Actual FPS: measure client-side với JavaScript

**Bandwidth**:
- [ ] Per stream: ~500 KB/s (640x480 @ 85 quality @ 10 FPS)
- [ ] Monitor network interface saturation

**Concurrent streams**:
- [ ] Max clients: giới hạn theo CPU/bandwidth
- [ ] Test với ab/wrk: `ab -n 1000 -c 10 http://host/streaming/video/101`

### 7.4. Browser integration example

```html
<!-- Simple MJPEG -->
<img src="http://localhost:8000/streaming/video/101" alt="Camera 101">

<!-- With error handling -->
<img id="stream" src="http://localhost:8000/streaming/video/101"
     onerror="this.src='placeholder.jpg'; setTimeout(() => location.reload(), 5000)">

<!-- With FPS counter -->
<script>
let lastFrameTime = Date.now();
let fps = 0;

const img = document.getElementById('stream');
img.onload = function() {
    const now = Date.now();
    fps = 1000 / (now - lastFrameTime);
    lastFrameTime = now;
    console.log('FPS:', fps.toFixed(1));
};
</script>
```

### 7.5. Security checklist

- [ ] Thêm authentication (JWT/API key)
- [ ] Rate limiting per IP
- [ ] CORS config (chỉ allow trusted origins)
- [ ] HTTPS để encrypt stream
- [ ] Log access (audit trail)
