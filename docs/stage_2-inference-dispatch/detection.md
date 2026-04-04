# core/detection.py - has_object_in_roi (Stage 2)

`has_object_in_roi()` nhận detections từ model và kiểm tra xem trong một ROI có object (vehicle) hay không. Hàm hỗ trợ tính toán trên GPU (`torch.Tensor`) hoặc fallback CPU (lặp từng detection).

## Function: `has_object_in_roi(detections, roi, node_id=None, use_gpu=True)`

### Nhánh GPU (`torch.Tensor`)

```python
def has_object_in_roi(detections, roi, node_id=None, use_gpu=True):
    threshold_coverage = THRESHOLD_COVERAGE
    threshold_detect = THRESHOLD_DETECT
    roi_box = roi

    if use_gpu and isinstance(detections, torch.Tensor):
        if len(detections) == 0:
            return False, 0.0

        vehicle_mask = (detections[:, 5] == 0.0) & (detections[:, 4] > threshold_detect)
        vehicle_detections = detections[vehicle_mask]

        if len(vehicle_detections) == 0:
            return False, 0.0

        coverage_values = calculate_coverage_batch(vehicle_detections, roi_box, device='cuda')
        max_coverage, max_idx = torch.max(coverage_values, dim=0)

        if max_coverage >= threshold_coverage:
            has_object = True
            coverage_value = max_coverage.item()
```

### Nhánh CPU (fallback)

```python
else:  # Fallback to CPU
    for det in detections:
        det_x, det_y, det_x1, det_y1, conf, cls = det
        if cls == 0.0 and conf > threshold_detect:
            det_box = [det_x, det_y, det_x1, det_y1]
            if is_roi_covered_enough(det_box, roi_box, threshold_coverage):
                coverage_value = calculate_coverage(det_box, roi_box)
                has_object = True
                break
```

## Data flow Stage 2 (tóm tắt)
- `CameraProcessor.run()` -> gọi `has_object_in_roi(detections, roi, node_id, use_gpu=True)`
- Kết quả `(has_obj, coverage)` -> gửi về API (`POST /detections`) hoặc cập nhật trực tiếp `StateManager` (tuỳ mode).

