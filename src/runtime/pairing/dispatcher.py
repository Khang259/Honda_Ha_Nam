"""Vòng điều phối: double/empty, single local còn lại, distributed claim, flush empty."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import api_http.state as api_state
from inference_core.state_manager import StateManager
from persistence.mongo.mongo_start_event_client import MongoStartEventClient
from shared.data import payload_sent_ICS, payload_sent_ICS_double, payload_sent_ICS_empty
from shared.setup_log import setup_logger

from runtime.pairing.ics_client import IcsClient
from runtime.pairing.local_pairs import enqueue_empty_pending, make_normal_pairs_local
from runtime.pairing.mongo_pool import MongoStartPool

logger = setup_logger("start_event_pairing", "logs/start_event_pairing/log")


class PairingDispatcher:
    def __init__(
        self,
        state: StateManager,
        validate_pairs: Set[Tuple[str, ...]],
        end_to_starts: Dict[str, List[str]],
        ics: IcsClient,
        mongo_client: MongoStartEventClient,
        pool: MongoStartPool,
        pending_empty: List[Tuple[str, float]],
        snapshot_manager: Optional[Any],
        worker_id: str,
        lease_seconds: int,
        is_running: Callable[[], bool],
        sleep_seconds: float = 1.0,
    ) -> None:
        self._state = state
        self._validate_pairs = validate_pairs
        self._end_to_starts = end_to_starts
        self._ics = ics
        self._mongo = mongo_client
        self._pool = pool
        self._pending_empty = pending_empty
        self._snapshot_manager = snapshot_manager
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._is_running = is_running
        self._sleep_seconds = sleep_seconds

    async def _post_ics(self, payload: Dict[str, Any]) -> bool:
        return await asyncio.to_thread(self._ics.post, payload)

    async def _dispatch_distributed_normals(self) -> None:
        for end_point in self._state.snapshot_ready_ends():
            candidates = self._end_to_starts.get(end_point, [])
            async with self._pool.pool_lock:
                pool_keys = [k for k in candidates if k in self._pool.local_start_pool]
            for start_point in pool_keys:
                if not self._is_running():
                    return
                async with self._pool.pool_lock:
                    if start_point not in self._pool.local_start_pool:
                        continue
                ok, _doc = await self._mongo.claim_ready(
                    node_id=start_point,
                    worker_id=self._worker_id,
                    lease_seconds=self._lease_seconds,
                )
                if not ok:
                    continue
                payload = payload_sent_ICS(start_point, end_point)
                success = await self._post_ics(payload)
                order_id = payload.get("orderId")
                if success:
                    await self._mongo.mark_sent(node_id=start_point, worker_id=self._worker_id)
                    self._state.set_pair_used(start_point, end_point, order_id, empty_car=False)
                    if self._snapshot_manager is not None:
                        try:
                            self._snapshot_manager.save_pair_snapshots(
                                start_point, end_point, order_id
                            )
                        except Exception:
                            pass
                    async with self._pool.pool_lock:
                        self._pool.local_start_pool.pop(start_point, None)
                    break
                await self._mongo.unlock_to_ready(node_id=start_point, worker_id=self._worker_id)

    async def run_loop(self) -> None:
        while self._is_running():
            try:
                self._state.process_starts()
                self._state.process_ends()
                now = time.time()
                enqueue_empty_pending(
                    self._state, self._validate_pairs, self._pending_empty, now
                )
                pairs, payloads = make_normal_pairs_local(self._state, self._validate_pairs)
                normal_idx = 0

                while normal_idx < len(pairs) and self._pending_empty:
                    start_empty, deadline = self._pending_empty[0]
                    if now > deadline:
                        end_empty = api_state.get_end_point_empty()
                        payload_empty = payload_sent_ICS_empty(start_empty, end_empty)
                        success = await self._post_ics(payload_empty)
                        order_id = payload_empty.get("orderId")
                        if success:
                            if self._snapshot_manager is not None:
                                try:
                                    self._snapshot_manager.save_pair_snapshots(
                                        start_empty, end_empty, order_id
                                    )
                                except Exception:
                                    pass
                            self._state.set_pair_used(
                                start_empty, end_empty, order_id, empty_car=False
                            )
                        self._pending_empty.pop(0)
                        continue

                    start_point, end_point = pairs[normal_idx]
                    end_empty = api_state.get_end_point_empty()
                    payload_double = payload_sent_ICS_double(
                        start_point, end_point, start_empty, end_empty
                    )
                    success = await self._post_ics(payload_double)
                    order_id = payload_double.get("orderId")
                    if success:
                        if self._snapshot_manager is not None:
                            try:
                                self._snapshot_manager.save_pair_snapshots(
                                    start_point, end_point, order_id
                                )
                            except Exception:
                                pass
                        self._state.set_pair_used(
                            start_point, end_point, order_id, empty_car=True
                        )
                        self._state.set_pair_used(
                            start_empty, end_empty, order_id, empty_car=False
                        )
                    self._pending_empty.pop(0)
                    normal_idx += 1

                # Giống PairManager: các normal còn lại -> gửi single local
                for start_point, end_point in pairs[normal_idx:]:
                    if not self._is_running():
                        break
                    payload = payload_sent_ICS(start_point, end_point)
                    order_id = payload.get("orderId")
                    success = await self._post_ics(payload)
                    if success:
                        if self._snapshot_manager is not None:
                            try:
                                self._snapshot_manager.save_pair_snapshots(
                                    start_point, end_point, order_id
                                )
                            except Exception:
                                pass
                        self._state.set_pair_used(
                            start_point, end_point, order_id, empty_car=False
                        )
                    else:
                        logger.error(
                            "Failed local single pair (%s, %s) orderId=%s",
                            start_point,
                            end_point,
                            order_id,
                        )

                await self._dispatch_distributed_normals()

                while self._pending_empty:
                    now_flush = time.time()
                    start_empty, deadline = self._pending_empty[0]
                    if now_flush <= deadline:
                        break
                    end_empty = api_state.get_end_point_empty()
                    payload_empty = payload_sent_ICS_empty(start_empty, end_empty)
                    success = await self._post_ics(payload_empty)
                    order_id = payload_empty.get("orderId")
                    if success:
                        if self._snapshot_manager is not None:
                            try:
                                self._snapshot_manager.save_pair_snapshots(
                                    start_empty, end_empty, order_id
                                )
                            except Exception:
                                pass
                        self._state.set_pair_used(
                            start_empty, end_empty, order_id, empty_car=False
                        )
                    self._pending_empty.pop(0)

            except Exception as e:
                logger.error("dispatcher loop error: %s", e, exc_info=True)
            await asyncio.sleep(self._sleep_seconds)
