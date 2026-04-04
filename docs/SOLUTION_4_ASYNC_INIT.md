# Solution 4: Async Initialization Implementation

## Vấn đề đã giải quyết

**Trước:**
- `GPUVideoDecoder` khởi tạo nhưng FFmpeg chưa sẵn sàng
- Test/code bắt đầu đọc frames ngay lập tức
- Kết quả: 0 frames hoặc inconsistent (cold start issue)

**Sau:**
- Có method `wait_ready()` để đợi frame đầu tiên
- Blocking cho đến khi decoder thực sự sẵn sàng
- Kết quả: consistent, predictable behavior

## Thay đổi trong code

### 1. `gpu_video_decoder.py`

#### Thêm Event synchronization:
```python
class GPUVideoDecoder:
    def __init__(self, ...):
        self._ready = threading.Event()  # ← Thêm
```

#### Signal khi frame đầu tiên decoded:
```python
def _decode_loop(self):
    first_frame = True
    while self.running:
        # ... decode logic ...
        
        if first_frame:
            self._ready.set()  # ← Signal: ready!
            first_frame = False
            logger.info(f"First frame decoded from {self.rtsp_url}")
```

#### Public method để wait:
```python
def wait_ready(self, timeout=10.0):
    """
    Block until first frame is decoded.
    
    Args:
        timeout: Maximum seconds to wait (default 10.0)
    
    Returns:
        True if ready within timeout, False otherwise
    """
    is_ready = self._ready.wait(timeout)
    if is_ready:
        logger.info(f"Decoder ready for {self.rtsp_url}")
    else:
        logger.warning(f"Timeout waiting for {self.rtsp_url}")
    return is_ready
```

### 2. `test_single_camera.py`

**Before:**
```python
cap = GPUVideoDecoder(rtsp_url)
if cap.isOpened():
    # Bắt đầu test ngay ← BAD!
    for i in range(100):
        ret, frame = cap.read()
```

**After:**
```python
cap = GPUVideoDecoder(rtsp_url)
if cap.isOpened():
    print("Waiting for first frame...")
    if cap.wait_ready(timeout=10.0):  # ← Đợi sẵn sàng
        # Bây giờ mới test
        for i in range(100):
            ret, frame = cap.read()
```

### 3. `camera_processor.py`

**Before:**
```python
cap = GPUVideoDecoder(self.rtsp)
if not cap.isOpened():
    return
# Bắt đầu process ngay ← Có thể chưa có frame
while self.running:
    ret, frame = cap.read()
```

**After:**
```python
cap = GPUVideoDecoder(self.rtsp)
if not cap.isOpened():
    return

# Đợi decoder sẵn sàng
if not cap.wait_ready(timeout=10.0):
    logger.error(f"Timeout waiting for {self.rtsp}")
    return

# Giờ mới bắt đầu process loop
while self.running:
    ret, frame = cap.read()
```

## Cách sử dụng

### Basic usage:
```python
from core.gpu_video_decoder import GPUVideoDecoder

cap = GPUVideoDecoder(rtsp_url)

# Method 1: Wait with default timeout (10s)
if cap.wait_ready():
    print("Ready to decode!")
    ret, frame = cap.read()

# Method 2: Custom timeout
if cap.wait_ready(timeout=5.0):
    print("Ready in 5s or less")
```

### Advanced usage với error handling:
```python
cap = GPUVideoDecoder(rtsp_url)

if not cap.isOpened():
    print("Failed to start FFmpeg process")
    exit(1)

print("FFmpeg started, waiting for first frame...")

if cap.wait_ready(timeout=15.0):
    print("Decoder ready!")
    
    # Your processing loop
    while True:
        ret, frame = cap.read()
        if ret and frame is not None:
            # Process frame
            pass
        time.sleep(0.033)
else:
    print("Timeout - possible causes:")
    print("  - Network issue")
    print("  - Camera offline")
    print("  - Wrong credentials")
    print("  - FFmpeg crash")
    cap.release()
```

### Multi-camera với sequential start:
```python
cameras = []
rtsp_urls = [f"rtsp://...{i}" for i in range(101, 114)]

for url in rtsp_urls:
    cap = GPUVideoDecoder(url)
    
    if cap.wait_ready(timeout=10.0):
        print(f"✅ {url} ready")
        cameras.append(cap)
    else:
        print(f"❌ {url} failed")
        cap.release()

print(f"Started {len(cameras)}/13 cameras")
```

## Lợi ích

### 1. **Consistent behavior**
- Không còn run đầu 0 frames, run sau 38 frames
- Mỗi lần chạy đều predictable

### 2. **Better error detection**
- Timeout rõ ràng nếu camera offline
- Không phải đợi mãi trong main loop

### 3. **Cleaner logs**
- Không còn hàng nghìn "Lost frame" false alarm
- Chỉ log khi thật sự có vấn đề

### 4. **Thread-safe**
- `threading.Event` is thread-safe primitive
- Không cần thêm locks

### 5. **Graceful degradation**
- Nếu 1 camera timeout → skip, tiếp tục các camera khác
- System không crash toàn bộ

## Testing

### Test startup time:
```bash
cd ai-nvdec
python test_startup_time.py
```

Expected output:
```
Run 1/5:
  Process started: 15ms
  ✅ First frame ready: 850ms
  Frames in 1s: 6/10

Run 2/5:
  Process started: 12ms
  ✅ First frame ready: 780ms
  Frames in 1s: 6/10
```

### Test single camera:
```bash
python test_single_camera.py
```

Expected output:
```
Testing rtsp://...
✅ Decoder process started
Waiting for first frame...
✅ Decoder ready!
Decoded 20/100 frames in 3.30s (6.1 FPS)
```

## Troubleshooting

### Timeout consistently?
```python
# Check FFmpeg errors (bật stderr)
stderr=subprocess.PIPE  # Thay DEVNULL
```

### Ready nhưng vẫn ít frames?
- Camera thật sự chỉ 6 FPS → expected
- Adjust polling rate match camera FPS

### Multiple cameras timeout?
- Network bandwidth insufficient
- GPU decoder overload
- Start cameras sequentially với delay
