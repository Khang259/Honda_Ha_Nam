from __future__ import annotations

import threading
from typing import List, Optional, Sequence

from shared.setup_log import setup_logger

logger = setup_logger("inference_engine_pool", "logs/inference_engine_pool/log")


class InferenceEnginePool:
    """
    Wrapper cho nhiều InferenceEngine để:
    - chia đều camera theo GPU (round-robin theo camera_index)
    - giữ interface pause/resume/stop tương thích với API routes hiện có
    """

    def __init__(self, engines: Sequence[object]):
        self.engines: List[object] = list(engines)
        self._paused = threading.Event()
        if not self.engines:
            self._paused.set()

    def get_engine_for_camera_index(self, camera_index: int) -> Optional[object]:
        if not self.engines:
            return None
        return self.engines[int(camera_index) % len(self.engines)]

    def pause(self) -> None:
        for e in self.engines:
            try:
                e.pause()
            except Exception:
                pass
        self._paused.set()
        logger.info("InferenceEnginePool paused")

    def resume(self) -> None:
        for e in self.engines:
            try:
                e.resume()
            except Exception:
                pass
        self._paused.clear()
        logger.info("InferenceEnginePool resumed")

    def stop(self) -> None:
        for e in self.engines:
            try:
                e.stop()
            except Exception:
                pass
        logger.info("InferenceEnginePool stopping all engines")

