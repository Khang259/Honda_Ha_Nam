# Overview - Tổng quan hệ thống

Phần này cung cấp cái nhìn tổng quan về hệ thống **Honda AI Monitoring** - mục đích, bối cảnh sử dụng, và các khái niệm cốt lõi.

## Nội dung

### 📄 [System Overview](./system-overview.md)
Tổng quan về hệ thống: sản phẩm là gì, giải quyết vấn đề gì, use-cases cụ thể.

### 📄 [Quick Start](./quick-start.md)
Hướng dẫn nhanh để setup và chạy hệ thống lần đầu.

### 📄 [Glossary](./glossary.md)
Thuật ngữ và khái niệm quan trọng trong hệ thống.

---

## Tóm tắt nhanh

**Honda AI Monitoring** là service AI runtime xử lý nhiều luồng camera (RTSP), chạy suy luận (YOLO) theo cơ chế batch + GPU, quản lý trạng thái theo node/ROI, và cung cấp FastAPI để điều khiển/quan sát runtime.

### Mục đích chính
- **Tập trung hoá inference**: 1 engine xử lý nhiều cameras → giảm overhead
- **Realtime processing**: gom batch + CUDA streams → tối ưu GPU
- **Distributed workers**: nhiều workers chia sẻ cameras, auto-rebalance
- **Business logic**: state machine theo ROI → trigger actions/webhooks

### Use-cases
- Giám sát realtime nhiều camera với AI detection
- Bật/tắt camera theo khu vực/ca làm việc
- Tự động phát hiện sự kiện theo ROI (start/end points)
- Streaming video với overlay detections + ROI

### Tech stack chính
- **Backend**: Python 3.10, FastAPI, Uvicorn
- **Database**: MongoDB (Motor/PyMongo)
- **AI**: Ultralytics YOLO, PyTorch (CUDA), TensorRT
- **Video**: FFmpeg (GPU decode), OpenCV, PyAV

---

[🏠 Về trang chính](../README.md) | [➡️ Tiếp: Architecture](../02-architecture/)
