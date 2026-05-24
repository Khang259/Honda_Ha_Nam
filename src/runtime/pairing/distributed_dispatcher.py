"""Điều phối POST ICS phân tán: end local + start từ Mongo pool (single / double / empty)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import api_http.state as api_state
from inference_core.state_manager import StateManager
from persistence.mongo.mongo_start_event_client import MongoStartEventClient
from shared.data import payload_sent_ICS, payload_sent_ICS_double, payload_sent_ICS_empty
from runtime.pairing.mongo_pool import MongoStartPool


class DistributedPairingDispatcher:
    """POST ICS khi start_* nằm trong start_events pool (worker khác publish), end_* ready local."""

    def __init__(
        self,
        state: StateManager,
        end_to_starts: Dict[str, List[str]],
        pool: MongoStartPool,
        mongo_client: MongoStartEventClient,
        snapshot_manager: Optional[Any],
        worker_id: str,
        lease_seconds: int,
        is_running: Callable[[], bool],
        start_to_area: Dict[str, str],
        end_to_area: Dict[str, str],
        pending_empty: List[Tuple[str, float]],
        get_disabled_nodes: Callable[[], Set[str]],
        get_disabled_areas: Callable[[], Set[str]],
        post_ics: Callable[[Dict[str, Any]], Any],
    ) -> None:
        self._state = state
        self._end_to_starts = end_to_starts
        self._pool = pool
        self._mongo = mongo_client
        self._snapshot_manager = snapshot_manager
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._is_running = is_running
        self._start_to_area = start_to_area
        self._end_to_area = end_to_area
        self._pending_empty = pending_empty
        self._get_disabled_nodes = get_disabled_nodes
        self._get_disabled_areas = get_disabled_areas
        self._post_ics = post_ics

    def _should_post_pair(self, start_point: str, end_point: str) -> bool:
        disabled_nodes = self._get_disabled_nodes()
        if start_point in disabled_nodes or end_point in disabled_nodes:
            return False
        
        disabled_areas = self._get_disabled_areas()
        if not disabled_areas:
            return True
        
        start_area = self._start_to_area.get(start_point)
        end_area = self._end_to_area.get(end_point, start_area)
        
        if start_area in disabled_areas or end_area in disabled_areas:
            return False
        
        return True

    def _should_post_empty(self, start_point: str, end_point: str) -> bool:
        disabled_nodes = self._get_disabled_nodes()
        if start_point in disabled_nodes:
            return False
        
        disabled_areas = self._get_disabled_areas()
        if not disabled_areas:
            return True
        
        start_area = self._start_to_area.get(start_point)
        if start_area in disabled_areas:
            return False
        
        return True

    def _is_node_blocked(self, node_id: str) -> bool:
        return self._state.is_node_flagged(node_id)

    async def _claim_start(self, node_id: str) -> bool:
        ok, _ = await self._mongo.claim_ready(
            node_id=node_id,
            worker_id=self._worker_id,
            lease_seconds=self._lease_seconds,
        )
        return ok

    async def _release_start(self, node_id: str) -> None:
        await self._mongo.unlock_to_ready(node_id=node_id, worker_id=self._worker_id)

    async def _pop_pool(self, node_id: str) -> None:
        async with self._pool.pool_lock:
            self._pool.local_start_pool.pop(node_id, None)

    async def _in_pool(self, node_id: str) -> bool:
        async with self._pool.pool_lock:
            return node_id in self._pool.local_start_pool

    async def _save_snapshot(self, start_point: str, end_point: str, order_id: str) -> None:
        if self._snapshot_manager is None:
            return
        try:
            self._snapshot_manager.save_pair_snapshots(start_point, end_point, order_id)
        except Exception:
            pass

    async def _after_post_success_single(
        self, start_point: str, end_point: str, order_id: str
    ) -> None:
        if str(start_point).startswith("start_"):
            await self._mongo.mark_sent(
                node_id=start_point,
                worker_id=self._worker_id,
                order_id=order_id,
            )
        self._state.set_pair_used(start_point, end_point, order_id, empty_car=False)
        await self._save_snapshot(start_point, end_point, order_id)
        await self._pop_pool(start_point)

    async def dispatch_round(self, now: float) -> None:
        await self._dispatch_singles()
        await self._dispatch_doubles(now)
        await self._dispatch_empty_flush(now)

    async def _dispatch_singles(self) -> None:
        for end_point in self._state.snapshot_ready_ends():
            if self._is_node_blocked(end_point):
                continue
            candidates = self._end_to_starts.get(end_point, [])
            async with self._pool.pool_lock:
                pool_keys = [k for k in candidates if k in self._pool.local_start_pool]
            for start_point in pool_keys:
                if not self._is_running():
                    return
                if self._is_node_blocked(start_point):
                    continue
                if not self._should_post_pair(start_point, end_point):
                    continue
                async with self._pool.pool_lock:
                    if start_point not in self._pool.local_start_pool:
                        continue
                if not await self._claim_start(start_point):
                    continue
                payload = payload_sent_ICS(start_point, end_point)
                success = await self._post_ics(payload)
                order_id = payload.get("orderId")
                if success:
                    await self._after_post_success_single(start_point, end_point, order_id)
                    break
                await self._release_start(start_point)

    async def _dispatch_doubles(self, now: float) -> None:
        if not self._pending_empty:
            return

        start_empty, deadline = self._pending_empty[0]
        if now > deadline:
            return
        if self._is_node_blocked(start_empty):
            return

        end_empty = api_state.get_end_point_empty()
        if end_empty is None:
            return

        for end_point in self._state.snapshot_ready_ends():
            if not self._is_running():
                return
            if self._is_node_blocked(end_point):
                continue

            candidates = self._end_to_starts.get(end_point, [])
            async with self._pool.pool_lock:
                pool_keys = [
                    k for k in candidates if k in self._pool.local_start_pool
                ]

            for start_point in pool_keys:
                if self._is_node_blocked(start_point):
                    continue

                area_normal = self._start_to_area.get(start_point)
                area_empty = self._start_to_area.get(start_empty)
                if area_normal != area_empty or area_normal is None:
                    continue

                if not await self._in_pool(start_point):
                    continue
                if not await self._in_pool(start_empty):
                    continue

                if not self._should_post_pair(start_point, end_point):
                    continue
                if not self._should_post_empty(start_empty, end_empty):
                    continue

                ok_normal = await self._claim_start(start_point)
                ok_empty = await self._claim_start(start_empty)
                if not (ok_normal and ok_empty):
                    if ok_normal:
                        await self._release_start(start_point)
                    if ok_empty:
                        await self._release_start(start_empty)
                    continue

                payload_double = payload_sent_ICS_double(
                    start_point, end_point, start_empty, end_empty
                )
                success = await self._post_ics(payload_double)
                order_id = payload_double.get("orderId")

                if success:
                    await self._mongo.mark_sent(
                        node_id=start_point,
                        worker_id=self._worker_id,
                        order_id=order_id,
                    )
                    await self._mongo.mark_sent(
                        node_id=start_empty,
                        worker_id=self._worker_id,
                        order_id=order_id,
                    )
                    await self._save_snapshot(start_point, end_point, order_id)
                    self._state.set_pair_used(
                        start_point, end_point, order_id, empty_car=True
                    )
                    self._state.set_pair_used(
                        start_empty, end_empty, order_id, empty_car=False
                    )
                    await self._pop_pool(start_point)
                    await self._pop_pool(start_empty)
                    self._pending_empty.pop(0)
                    return

                await self._release_start(start_point)
                await self._release_start(start_empty)

    async def _dispatch_empty_flush(self, now: float) -> None:
        while self._pending_empty:
            if not self._is_running():
                return

            start_empty, deadline = self._pending_empty[0]
            if now <= deadline:
                break

            if not await self._in_pool(start_empty):
                self._pending_empty.pop(0)
                continue

            end_empty = api_state.get_end_point_empty()
            if end_empty is None:
                self._pending_empty.pop(0)
                continue

            if not self._should_post_empty(start_empty, end_empty):
                self._pending_empty.pop(0)
                continue

            if not await self._claim_start(start_empty):
                self._pending_empty.pop(0)
                continue

            payload_empty = payload_sent_ICS_empty(start_empty, end_empty)
            success = await self._post_ics(payload_empty)
            order_id = payload_empty.get("orderId")

            if success:
                await self._mongo.mark_sent(
                    node_id=start_empty,
                    worker_id=self._worker_id,
                    order_id=order_id,
                )
                await self._save_snapshot(start_empty, end_empty, order_id)
                self._state.set_pair_used(
                    start_empty, end_empty, order_id, empty_car=False
                )
                await self._pop_pool(start_empty)
            else:
                await self._release_start(start_empty)

            self._pending_empty.pop(0)
