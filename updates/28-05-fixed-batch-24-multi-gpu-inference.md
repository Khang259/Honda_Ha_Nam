# 28-05 — Fixed batch=24 (hold) + chia đều inference theo GPU

## Mục tiêu

- Cố định **batch size = 24** theo cơ chế **hold-until-full**: chỉ chạy inference khi gom đủ 24 frames.
- Chia đều inference theo **các GPU hiện có** (round-robin theo `camera_index`).

## Thay đổi chính (source)

- `src/inference_core/inference_engine.py`
  - Thêm `device_id` để chạy đúng `cuda:{id}`.
  - Thêm `hold_full_batch` (mặc định True) để chuyển `_collect_batch()` sang **hold full batch**.
  - Tạo CUDA streams trong context `torch.cuda.device(device_id)`.
- `src/inference_core/inference_engine_pool.py`
  - Wrapper quản lý nhiều `InferenceEngine` và giữ interface `pause/resume/stop` tương thích API routes.
  - Cung cấp `get_engine_for_camera_index()` để `CameraManager` chọn engine theo camera index.
- `src/inference_core/camera_manager.py`
  - Khi start camera: chọn engine theo `camera_index`, đăng ký result queue vào engine đó và truyền đúng engine cho `CameraProcessor`.
- `src/runtime/runtime_service.py`
  - Khởi tạo số engine theo `torch.cuda.device_count()` (fallback 1 nếu không detect được).
  - Set `api_state.inference_engine = InferenceEnginePool(...)` để API `/start-all`, `/stop-all`, `/flag-camera-id` vẫn gọi `pause/resume` bình thường.

## Quyết định ngoài spec / giả định

- **Detect số GPU bằng `torch.cuda.device_count()`** (không thêm config mới).
  - Nếu detect lỗi hoặc `cuda` không available thì **fallback 1** để tránh crash start runtime.
- **Chia đều camera theo `camera_index % gpu_count`**.
  - Không dựa vào metadata camera (zone/area/fps) vì chưa có tín hiệu ổn định để “weighted scheduling”.

## Trade-off

### Hold batch=24

- **Ưu**: batch size ổn định → thường giảm dao động VRAM do cấp phát theo batch.
- **Nhược**:
  - **Tăng latency**: nếu tổng FPS thấp hoặc ít camera, có thể chờ lâu mới đủ 24 frames.
  - Khi một số camera disable → tốc độ gom batch giảm → inference có thể “đứng” lâu hơn.

### Multi-GPU round-robin theo camera_index

- **Ưu**: triển khai đơn giản, chia đều theo số camera, dễ vận hành.
- **Nhược**:
  - Không đảm bảo “cân theo tải thực” (camera FPS/độ phức tạp scene khác nhau).
  - Decode vẫn là pipeline riêng; thay đổi này tập trung vào **inference**.

## Khác với thực tế trước đó

- Trước đây runtime tạo **1** `InferenceEngine` và `shared_queue` gom từ mọi camera → batch size biến thiên theo timeout.
- Bây giờ:
  - Mỗi GPU có **1** `InferenceEngine` riêng (queue riêng theo nhóm camera).
  - Batch inference được **hold đủ 24** (không còn gom theo timeout khi `hold_full_batch=True`).

## Rủi ro / lưu ý vận hành

- Nếu môi trường thực không có CUDA/driver, code vẫn fallback `gpu_count=1` nhưng model gọi `cuda:{id}` có thể fail. Khi đó cần chạy CPU (ngoài phạm vi thay đổi lần này).
- Với hold-until-full, cần đảm bảo tổng throughput đủ để không gây “đứng inference” trong giờ thấp điểm.

