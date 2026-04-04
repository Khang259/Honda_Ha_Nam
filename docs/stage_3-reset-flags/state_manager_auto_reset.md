# core/state_manager.py - Auto reset / lifecycle (Stage 3)

Trong code hiện tại, “reset/điều kiện sẵn sàng” diễn ra theo 2 hướng:
- Reset chủ động qua webhook: `POST /delete-flag` (Stage 3 API docs)
- Auto lifecycle dựa trên thời gian tồn tại / biến đổi state: `process_starts()` và `process_ends()`

## Auto reset/lifecycle functions

### `process_starts()`: đưa `start_*` vào `ready_start_list` sau 30s

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

### `process_ends()`: đưa `end_*` vào `ready_end_list` sau 60s (khi `state == False`)

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

## Ý nghĩa trong pipeline reset tránh lặp
- `PairManager._run()` gọi `process_starts/process_ends` để tạo “ready” cho dispatch.
- Khi webhook reset diễn ra, `points[*]["flag"]` được set về `False` và các entry tương ứng bị loại khỏi `ready_*`, nên lần dispatch kế tiếp không bị lặp sai vòng.

