# worker/api_client.py - APIClient (Stage 2: gọi API server)

`APIClient` là wrapper HTTP client để:
- AI Worker POST detection lên API Server (`/detections`)
- UI poll state (`/state/points`, `/state/ready-lists`)
- kiểm tra health / retry connect

## Class: `APIClient`

### `post_detection(...)`

```python
def post_detection(self, cam_id: str, node_id: str, detected: bool, coverage: Optional[float] = None) -> bool:
    response = self.client.post(
        f"{self.api_url}/detections",
        json={
            "cam_id": cam_id,
            "node_id": node_id,
            "detected": detected,
            "coverage": coverage
        }
    )

    if response.status_code == 200:
        return True
    else:
        logger.error(f"POST detection failed: {response.status_code}")
        return False
```

### `get_points_state()`

```python
def get_points_state(self) -> Optional[Dict[str, Any]]:
    response = self.client.get(f"{self.api_url}/state/points")

    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            return data.get("points", {})
    return None
```

### `get_ready_lists()`

```python
def get_ready_lists(self) -> Optional[Dict[str, List[str]]]:
    response = self.client.get(f"{self.api_url}/state/ready-lists")

    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            return {
                "ready_start_list": set(data.get("ready_start_list", [])),
                "ready_end_list": set(data.get("ready_end_list", []))
            }
    return None
```

### `wait_for_api(...)` + `health_check()`

```python
def wait_for_api(self, max_retries: int = 30, retry_delay: float = 2.0) -> bool:
    for i in range(max_retries):
        if self.health_check():
            logger.info("API server is ready")
            return True
        time.sleep(retry_delay)
    return False

def health_check(self) -> bool:
    response = self.client.get(f"{self.api_url}/health")
    return response.status_code == 200
```

### `close()`

```python
def close(self):
    self.client.close()
```

## Data flow Stage 2 (tóm tắt)
- AI Worker: `post_detection()` -> API `/detections` -> `StateManager.get_state_nodes()`
- UI: `get_points_state()`/`get_ready_lists()` -> `StateProxy.refresh()` -> `GUIMonitor.update_display()`

