# ui/main_ui.py - UI entrypoint (Stage 4)

`UIManager` là điểm bắt đầu cho UI monitor chạy local. Nó tạo `APIClient`, chờ API server sẵn sàng, rồi khởi tạo `UIT` (wrapper thread) để chạy `GUIMonitor`.

## Class: `UIManager`

### `initialize()`

```python
def initialize(self):
    logger.info("Initializing UI monitor...")
    self.api_client = APIClient(API_URL)
    if not self.api_client.wait_for_api(max_retries=10, retry_delay=2.0):
        logger.error("Cannot connect to API server, exiting...")
        sys.exit(1)

    validate_pairs = get_validate_pairs(VALIDATE_PAIRS)
    camera_zones = [c.get("zone") for c in CAMERAS]

    self.ui = UIT(
        api_client=self.api_client,
        validate_pairs=validate_pairs,
        shutdown_callback=self.shutdown,
        pairs_by_zone=VALIDATE_PAIRS_BY_ZONE,
        cameras_config=CAMERAS,
        camera_zones=camera_zones,
    )
```

### `start()` / `shutdown()`

```python
def start(self):
    if self.ui:
        self.ui.start()

def shutdown(self):
    logger.info("UI MONITOR SHUTDOWN")
    if self.api_client:
        self.api_client.close()
    sys.exit(0)
```

## Cách chạy (theo docs project)
- Chạy Docker compose cho `api_server` (đã có ở `docs/README_SERVICES.md`)
- Chạy UI local:
  - `python ui/main_ui.py`

