# core/inference_engine.py - InferenceEngine (Stage 1)

`InferenceEngine` là “trung tâm” inference: nhận frame từ nhiều camera (qua `shared_queue`), gom batch theo `batch_timeout`/`max_batch_size`, chạy YOLO trên nhiều `CUDA streams` theo cơ chế async, rồi phân phối detections trở lại cho từng camera qua `result_queues`.

## Class: `InferenceEngine`

### `__init__(...)`: shared queue + CUDA streams

```python
def __init__(self, model_path, max_queue_size, max_batch_size,
             batch_timeout, num_streams):
    self.model_path = model_path
    self.max_queue_size = max_queue_size
    self.max_batch_size = max_batch_size
    self.batch_timeout = batch_timeout
    self.num_streams = num_streams
    self.shared_queue = queue.Queue(maxsize=max_queue_size)
    self.result_queues = {}
    self.streams = []
    self.pending_batches = deque(maxlen=num_streams * 2)
    self.running = False
    self.model = None
```

### `register_camera(cam_id, result_queue)`

```python
def register_camera(self, cam_id, result_queue):
    self.result_queues[cam_id] = result_queue
```

### `put_frame_with_drop(frame, cam_id)`: drop-oldest khi full

```python
def put_frame_with_drop(self, frame, cam_id):
    try:
        self.shared_queue.put_nowait((frame, cam_id))
    except queue.Full:
        try:
            dropped_frame, dropped_cam_id = self.shared_queue.get_nowait()
        except queue.Empty:
            pass
```

### `_collect_batch()`: gom frame thành batch

```python
def _collect_batch(self):
    batch = []
    cam_ids = []
    start_time = time.time()

    while len(batch) < self.max_batch_size:
        timeout = self.batch_timeout - (time.time() - start_time)
        if timeout <= 0:
            break

        try:
            frame, cam_id = self.shared_queue.get(timeout=timeout)
            batch.append(frame)
            cam_ids.append(cam_id)
        except queue.Empty:
            break

    return batch, cam_ids
```

### `_load_model()`: load YOLO + tạo CUDA streams

```python
def _load_model(self):
    self.model = YOLO(self.model_path, verbose=False)
    self.streams = [torch.cuda.Stream() for _ in range(self.num_streams)]
```

### `_async_inference(frames_batch, stream)`: inference trong 1 stream

```python
def _async_inference(self, frames_batch, stream):
    with torch.cuda.stream(stream):
        results = self.model(frames_batch,
                              conf=0.3,
                              max_det=15,
                              device='cuda',
                              verbose=False,
                              stream=True)

        output = []
        for result in results:
            detections = result.boxes.data
            output.append(detections)

        event = stream.record_event()

    return output, event
```

### `_distribute_results(results, cam_ids)`: put detections về camera

```python
def _distribute_results(self, results, cam_ids):
    for detection, cam_id in zip(results, cam_ids):
        if cam_id not in self.result_queues:
            logger.warning(f"Camera {cam_id} not registered")
            continue

        try:
            self.result_queues[cam_id].put_nowait(detection)
        except queue.Full:
            try:
                self.result_queues[cam_id].get_nowait()
                self.result_queues[cam_id].put_nowait(detection)
            except (queue.Empty, queue.Full):
                logger.warning(f"Failed to deliver result to {cam_id}")
```

### `run()`: pipeline async CUDA streams + event completion

```python
def run(self):
    self.running = True
    self._load_model()
    stream_idx = 0

    while self.running:
        batch_frames, cam_ids = self._collect_batch()

        if len(batch_frames) > 0:
            stream = self.streams[stream_idx]
            results, event = self._async_inference(batch_frames, stream)
            self.pending_batches.append({
                'results': results,
                'cam_ids': cam_ids,
                'event': event,
                'timestamp': time.time()
            })
            stream_idx = (stream_idx + 1) % self.num_streams

        completed_indices = []
        for i, batch_info in enumerate(self.pending_batches):
            if batch_info['event'].query():
                self._distribute_results(batch_info['results'], batch_info['cam_ids'])
                completed_indices.append(i)

        for i in reversed(completed_indices):
            del self.pending_batches[i]
```

### `stop()`

```python
def stop(self):
    self.running = False
    logger.info("Stopping InferenceEngine...")
```

## Data flow Stage 1 (tóm tắt)
- `CameraProcessor.put_frame_with_drop()` -> `InferenceEngine.shared_queue`
- `InferenceEngine.run()` -> `_async_inference()` (multi CUDA streams) -> `_distribute_results()` -> `CameraProcessor.result_queue`

