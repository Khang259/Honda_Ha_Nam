# core/state_manager.py - StateManager (Stage 2: state + ready lists + set_pair_used)

`StateManager` lưu trạng thái theo từng `node_id` (start/end points) và duy trì 2 tập `ready_start_list`/`ready_end_list`. Khi đủ điều kiện, `set_pair_used()` sẽ “chuyển” pair từ ready sang used bằng cách set `flag` và cập nhật mapping để phục vụ logic reset.

## Class: `StateManager`

### `__init__(validate_pairs)`

```python
def __init__(self, validate_pairs):
    self.points = defaultdict(lambda: {
        "state": False, "time": time.time(), "flag": False, "frame": None
    })
    self.ready_start_list = set()
    self.ready_end_list = set()
    self.pair_mapping = {}
    self.order_mapping = {}
    self.validate_pairs = validate_pairs
```

### `get_state_nodes(node_id, state, frame=None)`

```python
def get_state_nodes(self, node_id, state, frame=None):
    current = self.points[node_id]
    old_state = current["state"]
    current["state"] = state

    if old_state != state:
        if node_id.startswith("start_"):
            if state:
                current["time"] = time.time()
            else:
                current["time"] = time.time()
                self.ready_start_list.discard(node_id)

        elif node_id.startswith("end_"):
            if not state:
                current["time"] = time.time()
            else:
                current["time"] = time.time()
                self.ready_end_list.discard(node_id)
```

### `process_starts()`: đưa start vào ready sau thời gian tồn tại

```python
def process_starts(self):
    current_time = time.time()
    for node_id, data in list(self.points.items()):
        if not node_id.startswith("start_"):
            continue

        if data["state"]:
            if not data["flag"]:
                existed_time = current_time - data["time"]
                if existed_time > 30:
                    if node_id not in self.ready_start_list:
                        self.ready_start_list.add(node_id)
```

### `process_ends()`: đưa end vào ready sau thời gian “không state”

```python
def process_ends(self):
    current_time = time.time()
    for node_id, data in list(self.points.items()):
        if not node_id.startswith("end_"):
            continue

        if not data["state"]:
            if not data["flag"]:
                existed_time = current_time - data["time"]
                if existed_time > 60:
                    if node_id not in self.ready_end_list:
                        self.ready_end_list.add(node_id)
```

### `set_pair_used(start_point, end_point, order_id, empty_car=False)`

```python
def set_pair_used(self, start_point, end_point, order_id, empty_car=False):
    self.points[start_point]["flag"] = True
    self.points[end_point]["flag"] = True

    self.ready_start_list.discard(start_point)
    self.ready_end_list.discard(end_point)

    self.pair_mapping[end_point] = start_point
    pairs = self.order_mapping.setdefault(order_id, [])
    pairs.append((start_point, end_point, empty_car))
```

## Data flow Stage 2 (tóm tắt)
- `/detections` -> `StateManager.get_state_nodes()`
- vòng lặp `PairManager._run()` -> `StateManager.process_starts()`/`process_ends()` -> quyết định pair -> `set_pair_used()` -> dispatch sang ICS

