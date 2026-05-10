"""
Test batching with real RTSP streams from config.py.

Goal:
- Open RTSP streams using GPUVideoDecoder (ffmpeg + hwaccel cuda).
- Push frames into an InferenceEngine-like batching loop (NO YOLO load).
- Measure:
  - batch size distribution (1..INFERENCE_MAX_BATCH_SIZE)
  - time spent collecting a batch (how long to "fill" / timeout)

Usage (PowerShell):
  cd d:\Honda\ai_project\ai-nvdec-snapshot
  py .\test_rtsp_batching.py --seconds 30 --max-cams 24

Notes:
- Requires ffmpeg available in PATH.
- This does NOT run YOLO inference; it only tests decode -> batching behavior.
"""

from __future__ import annotations

import argparse
import queue
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from config import (
    CAMERAS,
    INFERENCE_MAX_BATCH_SIZE,
    INFERENCE_BATCH_TIMEOUT,
)
from inference_core.gpu_video_decoder import GPUVideoDecoder


@dataclass
class BatchStat:
    batch_size: int
    collect_s: float


class BatchCollector:
    """Minimal batch-collector compatible with current InferenceEngine behavior."""

    def __init__(self, max_batch_size: int, batch_timeout_s: float, max_queue_size: int = 500):
        self.max_batch_size = int(max_batch_size)
        self.batch_timeout_s = float(batch_timeout_s)
        self.shared_queue: "queue.Queue[Tuple[np.ndarray, str]]" = queue.Queue(maxsize=max_queue_size)
        self.running = threading.Event()
        self.running.set()

    def put_frame_with_drop(self, frame: np.ndarray, cam_id: str) -> None:
        try:
            self.shared_queue.put_nowait((frame, cam_id))
        except queue.Full:
            try:
                self.shared_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.shared_queue.put_nowait((frame, cam_id))
            except queue.Full:
                # If still full, drop.
                pass

    def collect_batch(self) -> Tuple[List[np.ndarray], List[str], float]:
        batch: List[np.ndarray] = []
        cam_ids: List[str] = []
        start = time.time()

        while len(batch) < self.max_batch_size:
            timeout = self.batch_timeout_s - (time.time() - start)
            if timeout <= 0:
                break
            try:
                frame, cam_id = self.shared_queue.get(timeout=timeout)
            except queue.Empty:
                break
            batch.append(frame)
            cam_ids.append(cam_id)

        return batch, cam_ids, (time.time() - start)


def _build_cam_id(index: int, rtsp: str) -> str:
    # Keep it simple and stable; no dependency on CameraManager naming.
    tail = rtsp.split("/")[-1].replace(":", "_")
    return f"cam{index}_{tail}"


def camera_decode_worker(
    index: int,
    rtsp: str,
    collector: BatchCollector,
    stop_evt: threading.Event,
    fps_stats: Dict[int, float],
    fps_lock: threading.Lock,
    width: int = 640,
    height: int = 480,
) -> None:
    cam_id = _build_cam_id(index, rtsp)
    dec: Optional[GPUVideoDecoder] = None

    frames = 0
    t0 = time.time()

    try:
        dec = GPUVideoDecoder(rtsp, width=width, height=height)
        if not dec.isOpened():
            print(f"[cam {index}] ERROR: cannot open RTSP")
            return
        if not dec.wait_ready(timeout=10.0):
            print(f"[cam {index}] ERROR: timeout waiting first frame")
            return

        while not stop_evt.is_set():
            ok, frame = dec.read()
            if not ok or frame is None:
                time.sleep(0.01)
                continue

            # Push a copy to isolate from reuse.
            collector.put_frame_with_drop(frame, cam_id)

            frames += 1
            now = time.time()
            if now - t0 >= 1.0:
                fps = frames / (now - t0)
                with fps_lock:
                    fps_stats[index] = fps
                frames = 0
                t0 = now
    finally:
        if dec is not None:
            try:
                dec.release()
            except Exception:
                pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=30, help="How long to run the test")
    ap.add_argument("--max-cams", type=int, default=24, help="Max RTSP streams to open from config.CAMERAS")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--batch-size", type=int, default=INFERENCE_MAX_BATCH_SIZE)
    ap.add_argument("--batch-timeout", type=float, default=INFERENCE_BATCH_TIMEOUT)
    args = ap.parse_args()

    cams = [c for c in CAMERAS if c.get("url")]
    cams = cams[: max(0, args.max_cams)]
    if not cams:
        print("No RTSP cameras found in config.CAMERAS")
        return 2

    collector = BatchCollector(max_batch_size=args.batch_size, batch_timeout_s=args.batch_timeout)
    stop_evt = threading.Event()

    fps_stats: Dict[int, float] = {}
    fps_lock = threading.Lock()

    threads: List[threading.Thread] = []
    for i, cam in enumerate(cams):
        rtsp = cam["url"]
        t = threading.Thread(
            target=camera_decode_worker,
            args=(i, rtsp, collector, stop_evt, fps_stats, fps_lock, args.width, args.height),
            daemon=True,
            name=f"RTSPCam{i}",
        )
        t.start()
        threads.append(t)

    stats: List[BatchStat] = []
    t_end = time.time() + max(1, args.seconds)
    last_print = 0.0

    print(f"Running {len(cams)} RTSP streams for {args.seconds}s")
    print(f"batch_size={args.batch_size}, batch_timeout={args.batch_timeout}s")

    try:
        while time.time() < t_end:
            batch, cam_ids, collect_s = collector.collect_batch()
            if batch:
                stats.append(BatchStat(batch_size=len(batch), collect_s=collect_s))

            now = time.time()
            if now - last_print >= 2.0:
                last_print = now
                with fps_lock:
                    fps_snapshot = dict(fps_stats)
                if fps_snapshot:
                    avg_fps = sum(fps_snapshot.values()) / len(fps_snapshot)
                    print(
                        f"[status] cams_ready={len(fps_snapshot)}/{len(cams)} "
                        f"avg_cam_fps={avg_fps:.1f} "
                        f"queue={collector.shared_queue.qsize()} "
                        f"last_batch={len(batch)} collect={collect_s:.3f}s"
                    )
                else:
                    print(f"[status] cams_ready=0/{len(cams)} queue={collector.shared_queue.qsize()}")
    finally:
        stop_evt.set()
        # Give decoders time to exit.
        time.sleep(0.2)

    if not stats:
        print("No batches collected (no frames arrived).")
        return 1

    sizes = [s.batch_size for s in stats]
    times = [s.collect_s for s in stats]

    def pct(vals: List[float], p: float) -> float:
        if not vals:
            return 0.0
        x = sorted(vals)
        k = int(round((len(x) - 1) * p))
        return float(x[max(0, min(k, len(x) - 1))])

    print("\n=== SUMMARY ===")
    print(f"batches: {len(stats)}")
    print(f"batch_size: min={min(sizes)} max={max(sizes)} avg={sum(sizes)/len(sizes):.2f}")
    print(
        "collect_time(s): "
        f"min={min(times):.4f} p50={pct(times, 0.50):.4f} p90={pct(times, 0.90):.4f} "
        f"max={max(times):.4f} avg={sum(times)/len(times):.4f}"
    )
    full = sum(1 for s in sizes if s >= args.batch_size)
    print(f"full_batches: {full}/{len(sizes)} ({(full/len(sizes))*100:.1f}%)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

