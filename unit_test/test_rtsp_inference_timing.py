"""
Test real RTSP -> batching -> YOLO inference timing.

What it measures:
- batch_size each inference (1..INFERENCE_MAX_BATCH_SIZE)
- collect_time: time spent waiting to gather a batch (<= INFERENCE_BATCH_TIMEOUT)
- inference_gpu_ms: CUDA event timing on the selected stream (approx GPU execution time)
- inference_wall_s: wall-clock time spent in _async_inference wrapper

Usage (PowerShell):
  cd d:\Honda\ai_project\ai-nvdec-snapshot
  py .\test_rtsp_inference_timing.py --seconds 30 --max-cams 12

Notes:
- Requires CUDA + torch + ultralytics working.
- Uses GPUVideoDecoder (ffmpeg -hwaccel cuda) to read RTSP.
"""

from __future__ import annotations

import argparse
import queue
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch

from config import (
    CAMERAS,
    INFERENCE_MAX_BATCH_SIZE,
    INFERENCE_BATCH_TIMEOUT,
    INFERENCE_MAX_QUEUE_SIZE,
    INFERENCE_NUM_STREAMS,
    MODEL_PATH,
)
from inference_core.gpu_video_decoder import GPUVideoDecoder
from inference_core.inference_engine import InferenceEngine


@dataclass
class InferStat:
    batch_size: int
    collect_s: float
    inference_wall_s: float
    inference_gpu_ms: float


def _build_cam_id(index: int, rtsp: str) -> str:
    tail = rtsp.split("/")[-1].replace(":", "_")
    return f"cam{index}_{tail}"


class TimedInferenceEngine(InferenceEngine):
    """InferenceEngine with timing instrumentation (no codebase changes)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stats: List[InferStat] = []
        self._stats_lock = threading.Lock()

    def _async_inference(self, frames_batch, stream):
        # GPU timing using CUDA events on the same stream.
        start_evt = torch.cuda.Event(enable_timing=True)
        end_evt = torch.cuda.Event(enable_timing=True)

        t0 = time.time()
        with torch.cuda.stream(stream):
            start_evt.record(stream)
            results = self.model(
                frames_batch,
                conf=0.3,
                max_det=15,
                device="cuda",
                half= True,
                verbose=False,
                stream=True,
            )

            output = []
            for result in results:
                detections = result.boxes.data
                output.append(detections)

            end_evt.record(stream)
            event = stream.record_event()

        # NOTE: We do not synchronize here; the run-loop will query completion via `event`.
        wall_s = time.time() - t0

        # We cannot safely call end_evt.elapsed_time(start_evt) until GPU work is done.
        # Store events on the batch_info in run() by returning them.
        return output, event, start_evt, end_evt, wall_s

    def run(self):
        self.running = True
        self._load_model()
        stream_idx = 0

        # pending item holds events for GPU timing
        pending: List[dict] = []

        while self.running:
            try:
                t_collect0 = time.time()
                batch_frames, cam_ids = self._collect_batch()
                collect_s = time.time() - t_collect0

                if batch_frames:
                    stream = self.streams[stream_idx]
                    out, event, start_evt, end_evt, wall_s = self._async_inference(batch_frames, stream)
                    pending.append(
                        {
                            "results": out,
                            "cam_ids": cam_ids,
                            "event": event,
                            "start_evt": start_evt,
                            "end_evt": end_evt,
                            "collect_s": collect_s,
                            "wall_s": wall_s,
                            "batch_size": len(batch_frames),
                        }
                    )
                    stream_idx = (stream_idx + 1) % self.num_streams

                done_idx = []
                for i, info in enumerate(pending):
                    if info["event"].query():
                        # GPU time available now
                        try:
                            gpu_ms = info["start_evt"].elapsed_time(info["end_evt"])
                        except Exception:
                            gpu_ms = float("nan")

                        with self._stats_lock:
                            self.stats.append(
                                InferStat(
                                    batch_size=info["batch_size"],
                                    collect_s=info["collect_s"],
                                    inference_wall_s=info["wall_s"],
                                    inference_gpu_ms=gpu_ms,
                                )
                            )

                        self._distribute_results(info["results"], info["cam_ids"])
                        done_idx.append(i)

                for i in reversed(done_idx):
                    del pending[i]

                if not batch_frames and not pending:
                    time.sleep(0.001)
            except Exception:
                time.sleep(0.05)


def camera_decode_worker(
    index: int,
    rtsp: str,
    engine: TimedInferenceEngine,
    stop_evt: threading.Event,
    fps_stats: Dict[int, float],
    fps_lock: threading.Lock,
    width: int,
    height: int,
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
                time.sleep(0.005)
                continue
            engine.put_frame_with_drop(frame, cam_id)

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


def _pct(vals: List[float], p: float) -> float:
    if not vals:
        return 0.0
    x = sorted(vals)
    k = int(round((len(x) - 1) * p))
    return float(x[max(0, min(k, len(x) - 1))])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--max-cams", type=int, default=12)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--model-path", type=str, default=MODEL_PATH)
    ap.add_argument("--batch-size", type=int, default=INFERENCE_MAX_BATCH_SIZE)
    ap.add_argument("--batch-timeout", type=float, default=INFERENCE_BATCH_TIMEOUT)
    ap.add_argument("--num-streams", type=int, default=INFERENCE_NUM_STREAMS)
    args = ap.parse_args()

    if not torch.cuda.is_available():
        print("ERROR: CUDA is not available (torch.cuda.is_available() == False)")
        return 2

    cams = [c for c in CAMERAS if c.get("url")]
    cams = cams[: max(0, args.max_cams)]
    if not cams:
        print("No RTSP cameras found in config.CAMERAS")
        return 2

    engine = TimedInferenceEngine(
        model_path=args.model_path,
        max_queue_size=INFERENCE_MAX_QUEUE_SIZE,
        max_batch_size=args.batch_size,
        batch_timeout=args.batch_timeout,
        num_streams=args.num_streams,
    )

    # Register cameras so distribute_results won't warn; also drain results.
    result_queues: Dict[str, "queue.Queue"] = {}
    for i, cam in enumerate(cams):
        cam_id = _build_cam_id(i, cam["url"])
        q = queue.Queue(maxsize=3)
        result_queues[cam_id] = q
        engine.register_camera(cam_id, q)

    def drain_worker(q: "queue.Queue", stop_evt: threading.Event):
        while not stop_evt.is_set():
            try:
                q.get(timeout=0.2)
            except queue.Empty:
                pass

    stop_evt = threading.Event()
    drain_threads: List[threading.Thread] = []
    for q in result_queues.values():
        t = threading.Thread(target=drain_worker, args=(q, stop_evt), daemon=True)
        t.start()
        drain_threads.append(t)

    engine.start()

    fps_stats: Dict[int, float] = {}
    fps_lock = threading.Lock()
    cam_threads: List[threading.Thread] = []
    for i, cam in enumerate(cams):
        t = threading.Thread(
            target=camera_decode_worker,
            args=(i, cam["url"], engine, stop_evt, fps_stats, fps_lock, args.width, args.height),
            daemon=True,
            name=f"RTSPCam{i}",
        )
        t.start()
        cam_threads.append(t)

    print(f"Running YOLO inference for {args.seconds}s on {len(cams)} RTSP streams")
    print(f"model={args.model_path}")
    print(f"batch_size={args.batch_size}, batch_timeout={args.batch_timeout}s, num_streams={args.num_streams}")

    t_end = time.time() + max(1, args.seconds)
    last_print = 0.0

    try:
        while time.time() < t_end:
            now = time.time()
            if now - last_print >= 2.0:
                last_print = now
                with engine._stats_lock:
                    n = len(engine.stats)
                    last = engine.stats[-1] if engine.stats else None
                with fps_lock:
                    fps_snapshot = dict(fps_stats)
                if fps_snapshot:
                    avg_fps = sum(fps_snapshot.values()) / len(fps_snapshot)
                    if last:
                        print(
                            f"[status] batches={n} last_batch={last.batch_size} "
                            f"collect={last.collect_s:.3f}s gpu={last.inference_gpu_ms:.2f}ms wall={last.inference_wall_s:.3f}s "
                            f"cams_ready={len(fps_snapshot)}/{len(cams)} avg_cam_fps={avg_fps:.1f}"
                        )
                    else:
                        print(
                            f"[status] batches=0 cams_ready={len(fps_snapshot)}/{len(cams)} avg_cam_fps={avg_fps:.1f}"
                        )
                else:
                    print(f"[status] batches={n} cams_ready=0/{len(cams)}")
            time.sleep(0.05)
    finally:
        stop_evt.set()
        engine.stop()
        time.sleep(0.2)

    with engine._stats_lock:
        stats = list(engine.stats)

    if not stats:
        print("No inference batches completed.")
        return 1

    sizes = [s.batch_size for s in stats]
    collect = [s.collect_s for s in stats]
    gpu_ms = [s.inference_gpu_ms for s in stats if s.inference_gpu_ms == s.inference_gpu_ms]  # not NaN
    wall = [s.inference_wall_s for s in stats]

    full = sum(1 for x in sizes if x >= args.batch_size)

    print("\n=== SUMMARY ===")
    print(f"batches: {len(stats)}")
    print(f"batch_size: min={min(sizes)} max={max(sizes)} avg={sum(sizes)/len(sizes):.2f} full={full} ({(full/len(sizes))*100:.1f}%)")
    print(
        "collect_time(s): "
        f"min={min(collect):.4f} p50={_pct(collect, 0.50):.4f} p90={_pct(collect, 0.90):.4f} "
        f"max={max(collect):.4f} avg={sum(collect)/len(collect):.4f}"
    )
    print(
        "inference_wall(s): "
        f"min={min(wall):.4f} p50={_pct(wall, 0.50):.4f} p90={_pct(wall, 0.90):.4f} "
        f"max={max(wall):.4f} avg={sum(wall)/len(wall):.4f}"
    )
    if gpu_ms:
        print(
            "inference_gpu(ms): "
            f"min={min(gpu_ms):.2f} p50={_pct(gpu_ms, 0.50):.2f} p90={_pct(gpu_ms, 0.90):.2f} "
            f"max={max(gpu_ms):.2f} avg={sum(gpu_ms)/len(gpu_ms):.2f}"
        )
    else:
        print("inference_gpu(ms): no GPU timings captured")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

