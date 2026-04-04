# ui/state_proxy.py - StateProxy (Stage 4: poll state)

`StateProxy` mô phỏng interface kiểu `StateManager` cho UI. UI không đọc state trực tiếp từ worker/API process, mà sẽ `poll` API server định kỳ và cache vào `self.points`, `ready_start_list`, `ready_end_list`.

## Class: `StateProxy`

### `refresh()`: poll và cache từ API server

```python
def refresh(self):
    now = time.time()
    if now - self.last_update < self.update_interval:
        return

    try:
        points_data = self.api_client.get_points_state()
        if points_data:
            for node_id, data in points_data.items():
                self.points[node_id].update(data)

        ready_lists = self.api_client.get_ready_lists()
        if ready_lists:
            self.ready_start_list = ready_lists.get("ready_start_list", set())
            self.ready_end_list = ready_lists.get("ready_end_list", set())

        self.last_update = now
    except Exception as e:
        logger.error(f"Error refreshing state from API: {e}")
```

### Các field cache chính (khởi tạo)

```python
self.points = defaultdict(lambda: {"state": False, "time": time.time(), "flag": False, "frame": None})
self.ready_start_list = set()
self.ready_end_list = set()
self.last_update = 0
self.update_interval = 0.5  # Poll mỗi 500ms
```

## Data flow Stage 4 (tóm tắt)
- `GUIMonitor.update_display()` gọi `StateProxy.refresh()`
- `StateProxy.refresh()` -> `APIClient.get_points_state()` + `APIClient.get_ready_lists()`
- UI cập nhật bảng theo cache

