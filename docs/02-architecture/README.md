# Architecture - Kiến trúc hệ thống

> **Đọc phần này nếu**: Bạn cần hiểu hệ thống được thiết kế như thế nào - các components, luồng dữ liệu, và design decisions.

## Nội dung

### 📄 [System Architecture](./system-architecture.md)
Kiến trúc tổng thể: layers, components, dependencies.

### 📄 [Concurrency Model](./concurrency-model.md)
Mô hình đồng thời: threads, async tasks, queues, synchronization.

### 📄 [Data Model](./data-model.md)
Schema MongoDB collections: worker_registry, node_id, validate_pairs.

### 📄 [Design Decisions](./design-decisions.md)
Các quyết định thiết kế quan trọng và trade-offs.

---

## Tóm tắt kiến trúc

### Layered Architecture

```
┌─────────────────────────────────────────────┐
│         API Layer (FastAPI)                 │
│  - routes/, services/, schemas/             │
│  - HTTP endpoints + lifecycle management    │
└───────────────┬─────────────────────────────┘
                │
┌───────────────┴─────────────────────────────┐
│         Core Runtime Layer                  │
│  - camera_manager, inference_engine         │
│  - pair_manager, state_manager              │
│  - worker_manager (distributed)             │
└───────────────┬─────────────────────────────┘
                │
┌───────────────┴─────────────────────────────┐
│         Infrastructure Layer                │
│  - MongoDB (configs, state)                 │
│  - RTSP cameras (video source)              │
│  - GPU (CUDA/TensorRT)                      │
└─────────────────────────────────────────────┘
```

### Key Components

1. **WorkerManager** (async): Distributed coordination
2. **CameraManager** (threads): Per-camera processing
3. **InferenceEngine** (thread): Centralized AI inference
4. **PairManager** (thread): Business logic execution
5. **StateManager** (in-memory): State machine
6. **Streaming/Control APIs**: External interfaces

### Design Principles

- **Separation of Concerns**: API ↔ Core ↔ Infrastructure
- **Single Responsibility**: Mỗi component 1 nhiệm vụ rõ ràng
- **Thread-per-Task**: Camera/Inference/Pair riêng biệt
- **Shared-Nothing**: Minimize shared mutable state
- **Fail-Safe**: Component fail không crash toàn hệ thống

---

[⬅️ Về trang chủ](../README.md) | [➡️ Tiếp: Flows](../03-flows/)
