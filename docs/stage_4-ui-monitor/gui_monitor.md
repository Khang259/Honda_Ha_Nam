# ui/gui_monitor.py - GUIMonitor (Stage 4: display + manual toggle)

`GUIMonitor` là UI Tkinter. Nó:
- đọc state từ API qua `StateProxy` (khi chạy mode api_client)
- hiển thị bảng start/end/flag/time theo các ROI node
- hỗ trợ toggle camera enable (qua `CameraManager.set_camera_enabled`)
- có cơ chế preview camera theo ROI (mở popup, lấy frame từ `CameraManager.latest_frames`)

## Class: `GUIMonitor`

### `__init__(...)`: chế độ proxy vs direct state_manager

```python
def __init__(..., api_client=None, state_manager=None, ...):
    # Support both direct state_manager (old mode) and api_client (new mode)
    if api_client and not state_manager:
        from ui.state_proxy import StateProxy
        self.state_manager = StateProxy(api_client)
        self.use_proxy = True
    else:
        self.state_manager = state_manager
        self.use_proxy = False
```

### `toggle_flag(point_id, flag_type)`

```python
def toggle_flag(self, point_id, flag_type):
    if point_id not in self.state_manager.points:
        return
    point_data = self.state_manager.points[point_id]
    current_flag = point_data["flag"]
    point_data["flag"] = not current_flag
    self.update_display()
```

### `update_display()`: refresh từ API + render UI

```python
def update_display(self):
    # Refresh state from API if using proxy
    if self.use_proxy and self.state_manager:
        self.state_manager.refresh()

    current_time = time.time()
    for row in self.labels:
        start_point = row["start_point"]
        end_point = row["end_point"]
        labels = row["labels"]
        for pt, prefix in [(start_point, "start"), (end_point, "end")]:
            if pt in self.state_manager.points:
                data = self.state_manager.points[pt]
                st = data["state"]
                fl = data["flag"]
                t = data["time"]
                labels[f"{prefix}_state"].config(text="T" if st else "F", bg="#00ff00" if st else "#ff0000")
                labels[f"{prefix}_flag"].config(text="T" if fl else "F", bg="#ffff00" if fl else "#808080")
                if t > 0:
                    elapsed = current_time - t
                    labels[f"{prefix}_time"].config(text=f"{elapsed:.1f}s", bg="#e8f5e9" if elapsed < 10 else "#ffebee")
                else:
                    labels[f"{prefix}_time"].config(text="-", bg="white")
            self._set_pair_cam_button_color(labels, prefix, pt)

    self.window.after(500, self.update_display)
```

### Preview camera theo `node_id`

Popup preview được tạo bởi `_start_preview_in_thread()`:

```python
def _start_preview_in_thread(self, node_id):
    if not self.camera_manager:
        return
    cam_id = self.camera_manager.get_cam_id_for_node(node_id)
    if cam_id is None:
        return

    top = tk.Toplevel(self.window)
    top.title(f"Camera: {node_id}")
    label = tk.Label(top, text="Waiting for frame...")
    label.pack(fill=tk.BOTH, expand=1)

    photo_ref = []
    frame_queue = queue.Queue(maxsize=1)
    running = {"running": True}
    ...
    thread = threading.Thread(
        target=self._preview_worker,
        args=(cam_id, node_id, frame_queue, running),
        daemon=True,
        name="PreviewWorker",
    )
    thread.start()
```

Và worker vẽ ROI + đẩy frame ra queue:

```python
def _preview_worker(self, cam_id, node_id, frame_queue, running, min_interval=0.1):
    roi = self._get_roi_for_node(node_id)
    last_push = 0.0
    while running.get("running"):
        frames = getattr(self.camera_manager, "latest_frames", {})
        frame = frames.get(cam_id)
        now = time.time()

        if frame is not None and (now - last_push) >= min_interval:
            frame = frame.copy()
            if roi is not None and len(roi) >= 4:
                x, y, w, h = int(roi[0]), int(roi[1]), int(roi[2]), int(roi[3])
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            ...
            frame_queue.put_nowait(rgb_copy)
            last_push = now
        time.sleep(0.01)
```

### `on_closing()` và `run()`

```python
def on_closing(self):
    for w in self._preview_windows[:]:
        try:
            w.destroy()
        except Exception:
            pass
    self._preview_windows.clear()
    if self.shutdown_callback:
        self.window.destroy()
        self.shutdown_callback()
    else:
        self.window.destroy()

def run(self):
    self.update_display()
    self.window.mainloop()
    logger.info("GUI mainloop ended")
```

## Data flow Stage 4 (tóm tắt)
- `GUIMonitor.update_display()` -> `StateProxy.refresh()` -> `APIClient.get_points_state()`/`get_ready_lists()`
- render bảng -> user thao tác toggle/preview (UI-level)

