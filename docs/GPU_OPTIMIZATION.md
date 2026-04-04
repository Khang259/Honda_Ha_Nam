# GPU Optimization Implementation

## Tổng quan

Implementation này chuyển đổi hệ thống từ CPU-based sang GPU-accelerated:
1. **NVDEC hardware decode** thay vì cv2.VideoCapture
2. **PyTorch GPU tensors** cho ROI overlap calculation

## Thay đổi chính

### 1. GPU Video Decoder (`core/gpu_video_decoder.py`)

**Trước:**
- Dùng `cv2.VideoCapture` (CPU decode)
- Không tận dụng NVDEC hardware

**Sau:**
```python
cap = GPUVideoDecoder(rtsp_url, width=640, height=480)
ret, frame = cap.read()  # Interface tương thích VideoCapture
```

**Đặc điểm:**
- FFmpeg với `-hwaccel nvdec`
- Background thread + queue buffer
- Tự động reconnect khi mất kết nối

### 2. GPU ROI Calculation (`utils/overlap_utils.py`)

**Trước:**
```python
for det in detections:  # Loop qua từng detection
    coverage = calculate_coverage(det_box, roi_box)
```

**Sau:**
```python
coverage = calculate_coverage_batch(detections_tensor, roi_box, device='cuda')
# Vectorized: tính tất cả detections cùng lúc
```

**Lợi ích:**
- Không cần loop Python
- Tận dụng parallel processing trên GPU
- Data không rời GPU (giảm CPU-GPU transfer)

### 3. YOLO Visualizer (`utils/yolo_visualizer.py`)

**Thay đổi:**
```python
detections, frame = predict_and_visualize(model, frame, return_tensor=True)
# detections giờ là torch.Tensor trên GPU, không convert sang numpy
```

### 4. Detection Logic (`core/detection.py`)

**Cải tiến:**
```python
has_object_in_roi(detections, roi, node_id, use_gpu=True)
# Tự động detect tensor/numpy và dùng GPU ops nếu có thể
```

## Data Flow mới

```
RTSP Stream 
  → FFmpeg hwaccel nvdec (GPU decode) 
  → Raw frames → NumPy (CPU)
  → YOLO inference (GPU) 
  → Detections tensor (GPU) ✅ Giữ trên GPU
  → ROI overlap (GPU vectorized) ✅
  → State update (CPU)
```

## Cách sử dụng

### Test GPU decoder đơn:
```bash
cd ai-nvdec/unit_test
python test_model.py
```

### Test full pipeline với GPU monitoring:
```bash
cd ai-nvdec/unit_test
python test_gpu_usage.py
```

### Chạy production:
```bash
cd ai-nvdec
python main_ai.py
```

## Kiểm tra GPU usage

### Verify NVDEC support:
```bash
ffmpeg -codecs | grep cuvid
```

### Monitor GPU trong khi chạy:
```bash
# Terminal 1
python main_ai.py

# Terminal 2
nvidia-smi -l 1  # Refresh mỗi giây
```

**Metrics cần check:**
- VRAM usage (~100-200MB per camera decode)
- GPU utilization
- Decoder usage (Video Engine)

## Backward compatibility

System vẫn hoạt động nếu GPU không có:
```python
has_object_in_roi(detections, roi, use_gpu=False)  # Fallback CPU
```

## Performance expectations

### Single camera (RTX 3060):
- Decode latency: ~5-10ms (vs 20-30ms CPU)
- ROI calculation: <1ms (vs 2-5ms CPU loop)
- Total pipeline: ~30-40ms (decode + inference + ROI)

### Multi-camera (10-20 cameras):
- NVDEC có 2-3 engines → parallel decode
- VRAM usage: ~50-100MB per stream
- Bottleneck: YOLO inference batch size

## Troubleshooting

### Lỗi: "Unknown decoder h264_cuvid"
→ Không áp dụng nữa, đang dùng `-hwaccel nvdec`
→ Nếu lỗi hwaccel: FFmpeg không compile với NVDEC support

### GPU out of memory
→ Giảm số camera hoặc batch size
→ Check memory leak với `nvidia-smi`

### Latency cao
→ Kiểm tra network (RTSP lag)
→ Monitor CPU usage (decode thread bottleneck)
→ Verify GPU không bị shared với process khác
