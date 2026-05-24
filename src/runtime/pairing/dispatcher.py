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

from runtime.pairing.distributed_dispatcher import DistributedPairingDispatcher
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
        start_to_area: Dict[str, str],
        end_to_area: Dict[str, str],
        empty_starts_by_area: Dict[str, List[str]],
        get_disabled_nodes: Callable[[], Set[str]],
        get_disabled_areas: Callable[[], Set[str]],
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
        self._start_to_area = start_to_area
        self._end_to_area = end_to_area
        self._empty_starts_by_area = empty_starts_by_area
        self._get_disabled_nodes = get_disabled_nodes
        self._get_disabled_areas = get_disabled_areas
        self._distributed = DistributedPairingDispatcher(
            state=state,
            end_to_starts=end_to_starts,
            pool=pool,
            mongo_client=mongo_client,
            snapshot_manager=snapshot_manager,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            is_running=is_running,
            start_to_area=start_to_area,
            end_to_area=end_to_area,
            pending_empty=pending_empty,
            get_disabled_nodes=get_disabled_nodes,
            get_disabled_areas=get_disabled_areas,
            post_ics=self._post_ics,
        )

    def _should_post_pair(self, start_point: str, end_point: str) -> bool:
        """Kiểm tra pair có bị chặn bởi disabled_nodes hoặc disabled_areas."""
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
        """Kiểm tra empty có bị chặn. Empty chỉ check start node/area."""
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

    async def _post_ics(self, payload: Dict[str, Any]) -> bool:
        return await asyncio.to_thread(self._ics.post, payload)

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
                        # Empty deadline expired, gửi empty task
                        async with self._pool.pool_lock:
                            if start_empty not in self._pool.local_start_pool:
                                self._pending_empty.pop(0)
                                continue
                        
                        end_empty = api_state.get_end_point_empty()
                        if not self._should_post_empty(start_empty, end_empty):
                            self._pending_empty.pop(0)
                            continue
                        
                        ok, _doc = await self._mongo.claim_ready(
                            node_id=start_empty,
                            worker_id=self._worker_id,
                            lease_seconds=self._lease_seconds,
                        )
                        if not ok:
                            self._pending_empty.pop(0)
                            continue
                        
                        payload_empty = payload_sent_ICS_empty(start_empty, end_empty)
                        success = await self._post_ics(payload_empty)
                        order_id = payload_empty.get("orderId")
                        
                        if success:
                            await self._mongo.mark_sent(
                                node_id=start_empty,
                                worker_id=self._worker_id,
                                order_id=order_id
                            )
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
                            async with self._pool.pool_lock:
                                self._pool.local_start_pool.pop(start_empty, None)
                        else:
                            await self._mongo.unlock_to_ready(
                                node_id=start_empty, worker_id=self._worker_id
                            )
                        
                        self._pending_empty.pop(0)
                        continue

                    # Double task: check area match
                    start_point, end_point = pairs[normal_idx]
                    
                    area_normal = self._start_to_area.get(start_point)
                    area_empty = self._start_to_area.get(start_empty)
                    
                    if area_normal != area_empty or area_normal is None:
                        # Khác area hoặc không có area -> gửi normal single
                        async with self._pool.pool_lock:
                            needs_claim_normal = start_point in self._pool.local_start_pool
                        
                        if needs_claim_normal:
                            if not self._should_post_pair(start_point, end_point):
                                normal_idx += 1
                                continue
                            ok_normal, _ = await self._mongo.claim_ready(
                                node_id=start_point,
                                worker_id=self._worker_id,
                                lease_seconds=self._lease_seconds,
                            )
                            if ok_normal:
                                payload_single = payload_sent_ICS(start_point, end_point)
                                success_single = await self._post_ics(payload_single)
                                order_id_single = payload_single.get("orderId")
                                if success_single:
                                    await self._mongo.mark_sent(
                                        node_id=start_point,
                                        worker_id=self._worker_id,
                                        order_id=order_id_single
                                    )
                                    if self._snapshot_manager is not None:
                                        try:
                                            self._snapshot_manager.save_pair_snapshots(
                                                start_point, end_point, order_id_single
                                            )
                                        except Exception:
                                            pass
                                    self._state.set_pair_used(
                                        start_point, end_point, order_id_single, empty_car=False
                                    )
                                    async with self._pool.pool_lock:
                                        self._pool.local_start_pool.pop(start_point, None)
                                else:
                                    await self._mongo.unlock_to_ready(
                                        node_id=start_point, worker_id=self._worker_id
                                    )
                        
                        normal_idx += 1
                        continue
                    
                    # Cùng area -> 2-phase claim for double task
                    async with self._pool.pool_lock:
                        has_normal = start_point in self._pool.local_start_pool
                        has_empty = start_empty in self._pool.local_start_pool
                        
                        if not (has_normal and has_empty):
                            normal_idx += 1
                            continue
                    
                    ok_normal, _ = await self._mongo.claim_ready(
                        node_id=start_point,
                        worker_id=self._worker_id,
                        lease_seconds=self._lease_seconds,
                    )
                    ok_empty, _ = await self._mongo.claim_ready(
                        node_id=start_empty,
                        worker_id=self._worker_id,
                        lease_seconds=self._lease_seconds,
                    )
                    
                    if not (ok_normal and ok_empty):
                        # Rollback claims
                        if ok_normal:
                            await self._mongo.unlock_to_ready(
                                node_id=start_point, worker_id=self._worker_id
                            )
                        if ok_empty:
                            await self._mongo.unlock_to_ready(
                                node_id=start_empty, worker_id=self._worker_id
                            )
                        normal_idx += 1
                        self._pending_empty.pop(0)
                        continue
                    
                    # POST double
                    end_empty = api_state.get_end_point_empty()
                    if not self._should_post_pair(start_point, end_point) or not self._should_post_empty(start_empty, end_empty):
                        if ok_normal:
                            await self._mongo.unlock_to_ready(
                                node_id=start_point, worker_id=self._worker_id
                            )
                        if ok_empty:
                            await self._mongo.unlock_to_ready(
                                node_id=start_empty, worker_id=self._worker_id
                            )
                        normal_idx += 1
                        self._pending_empty.pop(0)
                        continue
                    
                    payload_double = payload_sent_ICS_double(
                        start_point, end_point, start_empty, end_empty
                    )
                    success = await self._post_ics(payload_double)
                    order_id = payload_double.get("orderId")
                    
                    if success:
                        # mark_sent cho CẢ 2
                        await self._mongo.mark_sent(
                            node_id=start_point,
                            worker_id=self._worker_id,
                            order_id=order_id
                        )
                        await self._mongo.mark_sent(
                            node_id=start_empty,
                            worker_id=self._worker_id,
                            order_id=order_id
                        )
                        
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
                        
                        async with self._pool.pool_lock:
                            self._pool.local_start_pool.pop(start_point, None)
                            self._pool.local_start_pool.pop(start_empty, None)
                    else:
                        # Rollback on failure
                        await self._mongo.unlock_to_ready(
                            node_id=start_point, worker_id=self._worker_id
                        )
                        await self._mongo.unlock_to_ready(
                            node_id=start_empty, worker_id=self._worker_id
                        )
                    
                    self._pending_empty.pop(0)
                    normal_idx += 1

                # Giống PairManager: các normal còn lại -> gửi single local
                for start_point, end_point in pairs[normal_idx:]:
                    if not self._is_running():
                        break
                    
                    # Kiểm tra pair có bị disable không
                    if not self._should_post_pair(start_point, end_point):
                        continue
                    
                    # Nếu start_ có trong pool, claim trước
                    needs_claim = False
                    async with self._pool.pool_lock:
                        if start_point in self._pool.local_start_pool:
                            needs_claim = True
                    
                    if needs_claim:
                        ok, _doc = await self._mongo.claim_ready(
                            node_id=start_point,
                            worker_id=self._worker_id,
                            lease_seconds=self._lease_seconds,
                        )
                        if not ok:
                            continue
                    
                    payload = payload_sent_ICS(start_point, end_point)
                    order_id = payload.get("orderId")
                    success = await self._post_ics(payload)
                    
                    if success:
                        if str(start_point).startswith("start_"):
                            await self._mongo.mark_sent(
                                node_id=start_point,
                                worker_id=self._worker_id,
                                order_id=order_id
                            )
                        
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
                        
                        async with self._pool.pool_lock:
                            self._pool.local_start_pool.pop(start_point, None)
                    else:
                        if needs_claim and str(start_point).startswith("start_"):
                            await self._mongo.unlock_to_ready(
                                node_id=start_point, worker_id=self._worker_id
                            )
                        logger.error(
                            "Failed local single pair (%s, %s) orderId=%s",
                            start_point,
                            end_point,
                            order_id,
                        )

                await self._distributed.dispatch_round(now)

            except Exception as e:
                logger.error("dispatcher loop error: %s", e, exc_info=True)
            await asyncio.sleep(self._sleep_seconds)
