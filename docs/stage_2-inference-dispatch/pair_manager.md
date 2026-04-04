# core/pair_manager.py - PairManager (Stage 2: make_pairs + dispatch to ICS)

`PairManager` lấy danh sách start/end “ready” từ `StateManager`, ghép thành các pair hợp lệ theo `validate_pairs`, sau đó POST payload sang ICS. Có cơ chế đặc biệt cho “empty car” (pair có length==1) thông qua `pending_empty_queue` để ghép theo FIFO trong một khoảng deadline.

## Class: `PairManager`

### `make_pairs()`: ghép ready pairs (normal + empty)

Đoạn quan trọng về empty vs normal:

```python
def make_pairs(self):
    payloads = []
    pairs = []
    now = time.time()

    # 1) Empty (len == 1) -> đưa vào pending queue (không gửi payload ngay)
    for pair in self.validate_pairs:
        if len(pair) == 1:
            start_empty = pair[0]
            if start_empty in self.state_manager.ready_start_list:
                if not any(start_empty == item[0] for item in self.pending_empty_queue):
                    deadline = now + 15
                    self.pending_empty_queue.append((start_empty, deadline))

    # 2) Normal pairs (len == 2) -> ghép FIFO theo ready_start_list
    used_starts = set()
    used_ends = set()
    start_queue = deque(self.state_manager.ready_start_list)

    while start_queue:
        start_point = start_queue.popleft()
        if start_point in used_starts:
            continue

        candidate_end = None
        for pair in self.validate_pairs:
            if len(pair) != 2:
                continue
            s, e = pair
            if s != start_point:
                continue
            if e in self.state_manager.ready_end_list and e not in used_ends:
                candidate_end = e
                break

        if candidate_end is None:
            continue

        payload = payload_sent_ICS(start_point, candidate_end)
        payloads.append(payload)
        pairs.append((start_point, candidate_end))
        used_starts.add(start_point)
        used_ends.add(candidate_end)

    return pairs, payloads
```

### `post_to_ics(payload)`: POST request tới ICS

```python
def post_to_ics(self, payload):
    response = requests.post(
        self.ics_url,
        json=payload
    )

    if response.status_code != 200:
        logger.error(f"POST failed - status: {response.status_code}")
        return False

    response_data = response.json()
    if response_data.get("code") == 1000:
        return True
    else:
        logger.error(f"ICS error response: {response_data}")
        return False
```

### `_run()`: vòng lặp ghép double/empty/single và dispatch

Một luồng dispatch rút gọn (đúng logic chính):

```python
def _run(self):
    while self.running:
        self.state_manager.process_starts()
        self.state_manager.process_ends()

        pairs, payloads = self.make_pairs()
        now = time.time()

        normal_idx = 0
        while normal_idx < len(pairs) and self.pending_empty_queue:
            start_empty, deadline = self.pending_empty_queue[0]

            if now > deadline:
                end_empty = END_POINT_EMPTY
                payload_empty = payload_sent_ICS_empty(start_empty, end_empty)
                success = self.post_to_ics(payload_empty)
                if success:
                    self.state_manager.set_pair_used(start_empty, end_empty, order_id, empty_car=True)
                self.pending_empty_queue.pop(0)
                continue

            start_point, end_point = pairs[normal_idx]
            end_empty = END_POINT_EMPTY
            payload_double = payload_sent_ICS_double(
                start_point, end_point,
                start_empty, end_empty
            )
            success = self.post_to_ics(payload_double)
            if success:
                self.state_manager.set_pair_used(start_point, end_point, order_id, empty_car=False)
                self.state_manager.set_pair_used(start_empty, end_empty, order_id, empty_car=True)
            self.pending_empty_queue.pop(0)
            normal_idx += 1

        # flush phần còn lại dưới dạng single pairs
        for pair, payload in zip(pairs[normal_idx:], payloads[normal_idx:]):
            start_point, end_point = pair
            success = self.post_to_ics(payload)
            if success:
                self.state_manager.set_pair_used(start_point, end_point, order_id, empty_car=False)

        time.sleep(1)
```

### `start()` / `stop()`

```python
def start(self):
    self.running = True
    self.thread = threading.Thread(
        target=self._run,
        daemon=True,
        name="PairManager"
    )
    self.thread.start()
```

## Data flow Stage 2 (tóm tắt)
- `PairManager._run()` -> `StateManager.process_*()` -> `make_pairs()`
- ghép -> tạo payload (`payload_sent_ICS/_empty/_double`)
- `post_to_ics()` -> nếu thành công -> `StateManager.set_pair_used()` để đánh dấu flags + lưu mapping theo `order_id`

