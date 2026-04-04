# ui/ui_thread.py - UIT thread wrapper (Stage 4)

`UIT` là wrapper tạo thread riêng để chạy `GUIMonitor`. Điều này giúp tách UI main loop khỏi logic entrypoint.

## Class: `UIT`

### `start()`

```python
def start(self):
    self.thread = threading.Thread(target=self.run, daemon=False, name="UIT")
    self.thread.start()
    logger.info("UIT thread started")
```

### `run()`: tạo `GUIMonitor` và `mainloop`

```python
def run(self):
    self.gui = GUIMonitor(
        api_client=self.api_client,
        state_manager=self.state_manager,
        validate_pairs=self.validate_pairs,
        shutdown_callback=self.shutdown_callback,
        camera_manager=self.camera_manager,
        pairs_by_zone=self.pairs_by_zone,
        cameras_config=self.cameras_config,
        camera_zones=self.camera_zones,
        rtsp_ae5=self.rtsp_ae5,
        rtsp_ae6=self.rtsp_ae6,
        rtsp_5l=self.rtsp_5l,
        rtsp_6l=self.rtsp_6l,
        rtsp_af=self.rtsp_af,
    )
    self.gui.run()
```

### `stop()`

```python
def stop(self):
    if self.gui and self.gui.window:
        try:
            self.gui.window.quit()
            self.gui.window.destroy()
            logger.info("GUI stopped")
        except Exception as e:
            logger.error(f"Error stopping GUI: {e}")
```

