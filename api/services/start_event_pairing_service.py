"""
Distributed pairing: publish start_* to MongoDB, consume via change stream,
match với end_* local (ổn định >30s), atomic claim + POST ICS.
Giữ logic empty-car / double từ PairManager (queue 15s) cho tuple len==1.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

import api.state as api_state
from api.clients.mongo_start_event_client import MongoStartEventClient
from api.core.database import get_collection
from core.state_manager import StateManager
from utils.data import payload_sent_ICS, payload_sent_ICS_double, payload_sent_ICS_empty
from utils.setup_log import setup_logger

logger = setup_logger("start_event_pairing", "logs/start_event_pairing/log")


def _build_end_to_starts(validate_pairs: Set[Tuple[str, ...]]) -> Dict[str, List[str]]:
    end_to_starts: Dict[str, List[str]] = {}
    for p in validate_pairs:
        if len(p) != 2:
            continue
        s, e = p[0], p[1]
        end_to_starts.setdefault(e, []).append(s)
    return end_to_starts


class StartEventPairingOrchestrator:
    def __init__(
        self,
        worker_id: str,
        state_manager: StateManager,
        validate_pairs: Set[Tuple[str, ...]],
        ics_url: str,
        snapshot_manager: Optional[Any] = None,
        lease_seconds: int = 20,
    ):
        self._worker_id = worker_id
        self._state = state_manager
        self._validate_pairs = validate_pairs
        self._ics_url = ics_url
        self._snapshot_manager = snapshot_manager
        self._lease_seconds = lease_seconds
        self._client = MongoStartEventClient()
        self._end_to_starts = _build_end_to_starts(validate_pairs)
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._local_start_pool: Dict[str, Dict[str, Any]] = {}
        self._pool_lock = asyncio.Lock()
        self._pending_empty: List[Tuple[str, float]] = []
        self._start_events_collection = "start_events_test"

    def _post_to_ics(self, payload: Dict[str, Any]) -> bool:
        try:
            response = requests.post(self._ics_url, json=payload, timeout=30)
            if response.status_code != 200:
                logger.error("POST failed - status: %s", response.status_code)
                return False
            data = response.json()
            if data.get("code") == 1000:
                logger.debug("POST ok orderId=%s", payload.get("orderId"))
                return True
            logger.error("ICS error: %s", data)
            return False
        except Exception as e:
            logger.error("POST error: %s", e)
            return False

    def _enqueue_empty_pending(self, now: float) -> None:
        ready = set(self._state.snapshot_ready_starts())
        for pair in self._validate_pairs:
            if len(pair) != 1:
                continue
            start_empty = pair[0]
            if start_empty not in ready:
                continue
            if not any(start_empty == item[0] for item in self._pending_empty):
                self._pending_empty.append((start_empty, now + 15.0))
    #TODO: this function is need to be repaired to used double task not only local but also distributed
    def _make_normal_pairs_local(self) -> Tuple[List[Tuple[str, str]], List[Dict[str, Any]]]:
        """Cặp (start,end) khi cả hai đều ready trên worker này — dùng cho lệnh double."""
        pairs: List[Tuple[str, str]] = []
        payloads: List[Dict[str, Any]] = []
        used_starts: set = set()
        used_ends: set = set()
        ready_ends = set(self._state.snapshot_ready_ends())
        start_queue = deque(self._state.snapshot_ready_starts())
        while start_queue:
            start_point = start_queue.popleft()
            if start_point in used_starts:
                continue
            candidate_end = None
            for p in self._validate_pairs:
                if len(p) != 2:
                    continue
                s, e = p[0], p[1]
                if s != start_point:
                    continue
                if e in ready_ends and e not in used_ends:
                    candidate_end = e
                    break
            if candidate_end is None:
                continue
            pairs.append((start_point, candidate_end))
            payloads.append(payload_sent_ICS(start_point, candidate_end))
            used_starts.add(start_point)
            used_ends.add(candidate_end)
        return pairs, payloads

    #This function is used for what?
    async def _load_initial_pool(self) -> None:
        col = get_collection(self._start_events_collection)
        cursor = col.find({"flag": False, "status": "ready"}, {"_id": 0})
        docs = await cursor.to_list(length=None)
        async with self._pool_lock:
            for d in docs:
                nid = d.get("node_id")
                if nid:
                    self._local_start_pool[str(nid)] = d
        logger.info("start_event pool primed: %s docs", len(self._local_start_pool))

    async def _apply_change(self, change: Dict[str, Any]) -> None:
        fd = change.get("fullDocument")
        if not fd:
            return
        nid = fd.get("node_id")
        if not nid:
            return
        nid = str(nid)
        async with self._pool_lock:
            if fd.get("flag") or fd.get("status") == "sent":
                self._local_start_pool.pop(nid, None)
            elif fd.get("status") == "ready" and not fd.get("flag"):
                self._local_start_pool[nid] = fd

    async def _poll_pool(self) -> None:
        col = get_collection(self._start_events_collection)
        cursor = col.find({"flag": False, "status": "ready"}, {"_id": 0})
        docs = await cursor.to_list(length=None)
        async with self._pool_lock:
            for d in docs:
                nid = d.get("node_id")
                if nid:
                    self._local_start_pool[str(nid)] = d

    async def _consumer_loop(self) -> None:
        col = get_collection(self._start_events_collection)
        await self._load_initial_pool()
        try:
            pipeline = [
                {
                    "$match": {
                        "operationType": {"$in": ["insert", "update", "replace"]},
                    }
                }
            ]
            async with col.watch(pipeline, full_document="updateLookup") as stream:
                async for change in stream:
                    if not self._running:
                        break
                    await self._apply_change(change)
        except Exception as e:
            logger.warning("Change stream unavailable (%s); polling start_events", e)
            while self._running:
                try:
                    await self._poll_pool()
                except Exception as ex:
                    logger.error("poll pool error: %s", ex)
                await asyncio.sleep(2.0)

    async def _publisher_loop(self) -> None:
        while self._running:
            try:
                self._state.process_starts()
                for node_id in self._state.snapshot_ready_starts():
                    if not str(node_id).startswith("start_"):
                        continue
                    cam = self._state.get_camera_id_for_node(node_id)
                    await self._client.upsert_ready(
                        node_id=str(node_id),
                        camera_id=cam,
                        assign_worker=self._worker_id,
                    )
            except Exception as e:
                logger.error("publisher loop error: %s", e, exc_info=True)
            await asyncio.sleep(1.0)

    async def _dispatch_distributed_normals(self) -> None:
        for end_point in self._state.snapshot_ready_ends():
            candidates = self._end_to_starts.get(end_point, [])
            async with self._pool_lock:
                pool_keys = [k for k in candidates if k in self._local_start_pool]
            for start_point in pool_keys:
                if not self._running:
                    return
                async with self._pool_lock:
                    if start_point not in self._local_start_pool:
                        continue
                ok, _doc = await self._client.claim_ready(
                    node_id=start_point,
                    worker_id=self._worker_id,
                    lease_seconds=self._lease_seconds,
                )
                if not ok:
                    continue
                payload = payload_sent_ICS(start_point, end_point)
                success = await asyncio.to_thread(self._post_to_ics, payload)
                order_id = payload.get("orderId")
                if success:
                    await self._client.mark_sent(node_id=start_point, worker_id=self._worker_id)
                    self._state.set_pair_used(start_point, end_point, order_id, empty_car=False)
                    if self._snapshot_manager is not None:
                        try:
                            self._snapshot_manager.save_pair_snapshots(
                                start_point, end_point, order_id
                            )
                        except Exception:
                            pass
                    async with self._pool_lock:
                        self._local_start_pool.pop(start_point, None)
                    break
                await self._client.unlock_to_ready(node_id=start_point, worker_id=self._worker_id)

    async def _dispatcher_loop(self) -> None:
        while self._running:
            try:
                self._state.process_starts()
                self._state.process_ends()
                now = time.time()
                self._enqueue_empty_pending(now)
                pairs, payloads = self._make_normal_pairs_local()
                normal_idx = 0

                while normal_idx < len(pairs) and self._pending_empty:
                    start_empty, deadline = self._pending_empty[0]
                    if now > deadline:
                        end_empty = api_state.get_end_point_empty()
                        payload_empty = payload_sent_ICS_empty(start_empty, end_empty)
                        success = await asyncio.to_thread(self._post_to_ics, payload_empty)
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
                    success = await asyncio.to_thread(self._post_to_ics, payload_double)
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

                await self._dispatch_distributed_normals()

                while self._pending_empty:
                    now_flush = time.time()
                    start_empty, deadline = self._pending_empty[0]
                    if now_flush <= deadline:
                        break
                    end_empty = api_state.get_end_point_empty()
                    payload_empty = payload_sent_ICS_empty(start_empty, end_empty)
                    success = await asyncio.to_thread(self._post_to_ics, payload_empty)
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
            await asyncio.sleep(1.0)

    async def start(self) -> None:
        await self._client.ensure_indexes()
        self._running = True
        self._tasks = [
            asyncio.create_task(self._publisher_loop(), name="start_event_publisher"),
            asyncio.create_task(self._consumer_loop(), name="start_event_consumer"),
            asyncio.create_task(self._dispatcher_loop(), name="start_event_dispatcher"),
        ]
        logger.info("StartEventPairingOrchestrator started worker=%s", self._worker_id)

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        logger.info("StartEventPairingOrchestrator stopped")
