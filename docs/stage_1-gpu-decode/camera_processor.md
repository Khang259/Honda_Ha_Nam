# core/camera_processor.py - CameraProcessor (Stage 1)

`CameraProcessor` là thread xử lý theo từng camera: đọc frame từ `GPUVideoDecoder`, đẩy frame vào `InferenceEngine` qua `put_frame_with_drop()`, rồi chờ `InferenceEngine` trả kết quả detections thông qua `result_queue`.

## Class: `CameraProcessor`

### `__init__(...)`: wiring dependencies

```python
def __init__(
    self,
    rtsp,
    rois,
    state_manager,
    inference_engine,
    result_queue,
    cam_id,
    snapshot_manager=None,
    enabled_ref=None,
    camera_index=0,
    latest_frames_ref=None,
    api_client=None,
):
    super().__init__()
    self.rtsp = rtsp
    self.rois = rois
    self.state_manager = state_manager
    self.inference_engine = inference_engine
    self.result_queue = result_queue
    self.cam_id = cam_id
    self.snapshot_manager = snapshot_manager
    self.enabled_ref = enabled_ref if enabled_ref is not None else []
    self.camera_index = camera_index
    self.latest_frames_ref = latest_frames_ref if latest_frames_ref is not None else {}
    self.api_client = api_client
    self.running = True
```

### `_is_enabled()`: bật/tắt camera theo UI/manager

```python
def _is_enabled(self):
    if self.camera_index < len(self.enabled_ref):
        return self.enabled_ref[self.camera_index]
    return True
```

### `run()`: vòng lặp đọc frame -> infer -> lấy detections

Các đoạn “xương sống”:

1) Chờ decode sẵn sàng:
```python
cap = GPUVideoDecoder(self.rtsp)
if not cap.isOpened():
    ...
if not cap.wait_ready(timeout=10.0):
    ...
```

2) Đọc frame và đẩy vào `InferenceEngine`:
```python
ret, frame = cap.read()
if not ret:
    ...
self.inference_engine.put_frame_with_drop(frame, self.cam_id)
```

3) Nhận detections từ `result_queue`:
```python
try:
    detections = self.result_queue.get(timeout=0.1)
except queue.Empty:
    logger.warning(f"Inference timeout for {self.cam_id}, skipping frame")
    time.sleep(0.01)
    continue
```

4) (Stage 1/2 ranh giới) Duyệt ROI và cập nhật state/UI theo mode:
```python
for roi_dict in self.rois:
    node_id = roi_dict["node_id"]
    roi = roi_dict["roi"]
    has_obj, coverage = has_object_in_roi(detections, roi, node_id, use_gpu=True)

    if self.api_client:
        self.api_client.post_detection(self.cam_id, node_id, has_obj, coverage)
    elif self.state_manager:
        self.state_manager.get_state_nodes(node_id, has_obj)

    if self.snapshot_manager is not None:
        self.snapshot_manager.update_frame(node_id, frame)
```

### Kết thúc thread

Khi `self.running = False`, thread sẽ giải phóng `cap` nếu tồn tại:
```python
if cap is not None:
    try:
        cap.release()
    except Exception:
        pass
```

## Data flow Stage 1 (tóm tắt)
- `CameraProcessor.run()` đọc frame từ `GPUVideoDecoder` -> push sang `InferenceEngine.shared_queue`
- `InferenceEngine` trả detections về `result_queue` cho đúng `cam_id`

