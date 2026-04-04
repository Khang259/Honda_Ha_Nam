# core/gpu_video_decoder.py - GPUVideoDecoder (Stage 1)

`GPUVideoDecoder` chịu trách nhiệm decode RTSP bằng FFmpeg với `-hwaccel cuda` (NVDEC). Nó chạy theo thread riêng, đọc frame raw BGR từ `stdout` FFmpeg và đẩy frame vào `queue` để consumer (ở đây là `CameraProcessor`/`InferenceEngine`) lấy tiếp.

## Class: `GPUVideoDecoder`

### `__init__(rtsp_url, width=..., height=...)`

```python
def __init__(self, rtsp_url, width=640, height=480):
    self.rtsp_url = rtsp_url
    self.width = width
    self.height = height
    self.frame_size = width * height * 3

    self.queue = queue.Queue(maxsize=3)
    self.process = None
    self.thread = None
    self.running = False
    self._opened = False
    self._ready = threading.Event()

    self._start_decode()
```

Điểm chính:
- `self.queue` là buffer nhỏ (max 3 frame) để giảm latency.
- `self._ready` là `threading.Event` dùng để đợi frame đầu tiên decode xong.

### `_start_decode()`: khởi tạo FFmpeg + thread decode loop

```python
def _start_decode(self):
    cmd = [
        "ffmpeg",
        "-hwaccel", "cuda",
        "-rtsp_transport", "tcp",
        "-fflags", "nobuffer",
        "-flags", "low_delay",
        "-i", self.rtsp_url,
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-s", f"{self.width}x{self.height}",
        "-"
    ]

    self.process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=GPU_DECODE_BUFFER_SIZE
    )

    self.running = True
    self._opened = True
    self.thread = threading.Thread(target=self._decode_loop, daemon=True)
    self.thread.start()
```

### `_decode_loop()`: đọc raw frame và push vào queue

```python
def _decode_loop(self):
    first_frame = True
    while self.running:
        raw = self.process.stdout.read(self.frame_size)
        if len(raw) != self.frame_size:
            continue

        frame = np.frombuffer(raw, np.uint8).reshape((self.height, self.width, 3))

        if first_frame:
            self._ready.set()
            first_frame = False

        if self.queue.full():
            try:
                self.queue.get_nowait()
            except queue.Empty:
                pass

        self.queue.put(frame)
```

Lưu ý:
- Khi queue đầy, frame cũ bị drop để ưu tiên frame mới (giảm trễ).
- `self._ready.set()` chỉ diễn ra ở frame đầu tiên.

### `wait_ready(timeout=10.0)`: chờ frame đầu

```python
def wait_ready(self, timeout=10.0):
    is_ready = self._ready.wait(timeout)
    if is_ready:
        logger.info(f"Decoder ready for {self.rtsp_url}")
    else:
        logger.warning(f"Decoder timeout waiting for first frame from {self.rtsp_url}")
    return is_ready
```

### `read()`: lấy frame từ queue (non-blocking)

```python
def read(self):
    if not self.isOpened():
        return False, None

    if not self.queue.empty():
        frame = self.queue.get()
        return True, frame
    return False, None
```

### `release()`: dừng thread + kill FFmpeg process

```python
def release(self):
    self.running = False
    self._opened = False

    if self.process:
        try:
            self.process.kill()
            self.process.wait(timeout=2)
        except:
            pass
        self.process = None
```

## Data flow Stage 1 (tóm tắt)
- `GPUVideoDecoder._decode_loop()` -> `queue` frame BGR
- `CameraProcessor.run()` -> `cap.read()` -> `InferenceEngine.put_frame_with_drop()`

