# core/camera_manager.py - CameraManager (Stage 1)

`CameraManager` tạo và quản lý các thread `CameraProcessor` theo cấu hình camera. Đồng thời nó ánh xạ `node_id` (từ ROI) sang `cam_id` để UI có thể mở đúng camera khi người dùng chọn node.

## Class: `CameraManager`

### `__init__(...)`: khởi tạo enabled/state và map node_id -> cam

```python
def __init__(self, cameras_config, state_manager, inference_engine,
             snapshot_manager=None, camera_zones=None, api_client=None):
    self.cameras_config = cameras_config
    self.state_manager = state_manager
    self.inference_engine = inference_engine
    self.snapshot_manager = snapshot_manager
    self.camera_zones = camera_zones or []
    self.api_client = api_client

    self.threads = []
    self.enabled = [False] * len(cameras_config)
    self._enabled_lock = threading.Lock()
    self.latest_frames = {}
    self._node_id_to_cam = {}
    self._build_node_id_to_cam()
```

### `_build_node_id_to_cam()`

```python
def _build_node_id_to_cam(self):
    for i, cam in enumerate(self.cameras_config):
        cam_id = f"cam_{i}_{cam['rtsp'].split('.')[-2]}"
        for roi_dict in cam.get("rois", []):
            node_id = roi_dict.get("node_id")
            if node_id and node_id not in self._node_id_to_cam:
                self._node_id_to_cam[node_id] = (cam_id, i)
```

### `start()`: tạo result_queue + đăng ký vào `InferenceEngine` + start `CameraProcessor`

```python
def start(self):
    for i, cam in enumerate(self.cameras_config):
        cam_id = f"cam_{i}_{cam['rtsp'].split('.')[-2]}"

        result_queue = queue.Queue(maxsize=10)
        self.inference_engine.register_camera(cam_id, result_queue)

        thread = CameraProcessor(
            cam["rtsp"],
            cam["rois"],
            self.state_manager,
            self.inference_engine,
            result_queue,
            cam_id,
            snapshot_manager=self.snapshot_manager,
            enabled_ref=self.enabled,
            camera_index=i,
            latest_frames_ref=self.latest_frames,
            api_client=self.api_client,
        )
        self.threads.append(thread)
        thread.start()
```

### `stop()`: dừng thread camera

```python
def stop(self):
    logger.info("Stopping all camera threads...")
    for thread in self.threads:
        if thread.is_alive():
            thread.running = False
    for thread in self.threads:
        if thread.is_alive():
            thread.join(timeout=2.0)
```

### `set_camera_enabled(index, on)` và `set_zone_enabled(zone, on)`

```python
def set_camera_enabled(self, index: int, on: bool):
    with self._enabled_lock:
        if 0 <= index < len(self.enabled):
            self.enabled[index] = on

def set_zone_enabled(self, zone: str, on: bool):
    with self._enabled_lock:
        for i, z in enumerate(self.camera_zones):
            if i < len(self.enabled) and z == zone:
                self.enabled[i] = on
```

### `start_all_cameras()` / `stop_all_cameras()`

```python
def start_all_cameras(self):
    with self._enabled_lock:
        for i in range(len(self.enabled)):
            self.enabled[i] = True

def stop_all_cameras(self):
    with self._enabled_lock:
        for i in range(len(self.enabled)):
            self.enabled[i] = False
```

### `get_cam_id_for_node(node_id)`

```python
def get_cam_id_for_node(self, node_id: str):
    info = self._node_id_to_cam.get(node_id)
    return info[0] if info else None
```

## Data flow Stage 1 (tóm tắt)
- `CameraManager.start()` tạo `result_queue` theo camera và gọi `InferenceEngine.register_camera()`
- `CameraProcessor.run()` đọc frame và đẩy vào `InferenceEngine`

