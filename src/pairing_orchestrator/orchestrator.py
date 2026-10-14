"""
Distributed pairing: publish start_* Mongo, consume pool, match end local,
atomic claim + POST ICS. Empty-car / double (15s) giống PairManager.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from inference_engine.state_manager import StateManager
from pairing_orchestrator.persistence.mongo_pair_client import MongoPairClient
from pairing_orchestrator.persistence.mongo_start_event_client import MongoStartEventClient
from shared.setup_log import setup_logger

from pairing_orchestrator.dispatcher import PairingDispatcher
from pairing_orchestrator.ics_client import IcsClient
from pairing_orchestrator.mongo_pool import MongoStartPool
from pairing_orchestrator.publisher import run_publisher_loop
from pairing_orchestrator.validate_pairs_graph import build_end_to_starts
from api.settings import settings

logger = setup_logger("start_event_pairing", "logs/start_event_pairing/log")

# Chờ camera/stream ổn định sau RUN trước khi publish/dispatch ICS
RESUME_STABILIZE_SECONDS = 3.0


class StartEventPairingOrchestrator:
    def __init__(
        self,
        worker_id: str,
        state_manager: StateManager,
        validate_pairs: Set[Tuple[str, ...]],
        ics_url: str,
        snapshot_manager: Optional[Any] = None,
        lease_seconds: int = 20,
        resume_stabilize_seconds: float = RESUME_STABILIZE_SECONDS,
        start_events_collection: Optional[str] = None,
    ) -> None:
        self._worker_id = worker_id
        self._state = state_manager
        self._validate_pairs = validate_pairs
        self._snapshot_manager = snapshot_manager
        self._lease_seconds = lease_seconds
        self._resume_stabilize_seconds = float(resume_stabilize_seconds)
        self._start_events_collection = (
            start_events_collection or settings.START_EVENTS_COLLECTION
        )
        self._mongo = MongoStartEventClient(
            collection_name=self._start_events_collection
        )
        self._end_to_starts = build_end_to_starts(validate_pairs)
        # _alive: vòng đời task (chỉ False khi stop process)
        # _paused: tạm dừng nghiệp vụ (STOP cluster); task vẫn sống
        self._alive = False
        self._paused = False
        # time.time() — trước mốc này coi như đang stabilize (không publish/dispatch)
        self._resume_ready_at: float = 0.0
        self._disabled_nodes: Set[str] = set()
        self._disabled_areas: Set[str] = set()
        self._tasks: List[asyncio.Task] = []
        self._pending_empty: List[Tuple[str, float]] = []

        self._ics = IcsClient(ics_url)
        self._pool = MongoStartPool(self._start_events_collection)
        self._dispatcher: Optional[PairingDispatcher] = None
        self._start_to_area: Dict[str, str] = {}
        self._empty_starts_by_area: Dict[str, List[str]] = {}

    def pause(self) -> None:
        """Tạm dừng pairing (không publish/POST ICS). Task vẫn sống."""
        self._paused = True
        logger.info("PairingOrchestrator paused")

    def resume(self) -> None:
        """
        Tiếp tục pairing. Không recreate task.
        Reset ready/timer state và chờ stabilize để tránh lệnh ICS từ state cũ.
        Không clear _disabled_nodes/_disabled_areas — zone/node khóa tay giữ nguyên
        đến khi gọi enable_nodes/enable_areas (vd. /{zone}/start-all).
        """
        self._state.reset_ready_state_for_run()
        self._pending_empty.clear()
        self._resume_ready_at = time.time() + self._resume_stabilize_seconds
        self._paused = False
        logger.info(
            "PairingOrchestrator resumed; stabilize for %.1fs until %.3f "
            "(disabled_nodes=%s disabled_areas=%s kept)",
            self._resume_stabilize_seconds,
            self._resume_ready_at,
            len(self._disabled_nodes),
            len(self._disabled_areas),
        )

    def disable_nodes(self, node_ids: Set[str]) -> None:
        """Disable pairing cho specific nodes (zone/camera)."""
        self._disabled_nodes.update(node_ids)
        logger.info(f"Disabled {len(node_ids)} nodes for pairing")

    def enable_nodes(self, node_ids: Set[str]) -> None:
        """Enable pairing cho specific nodes."""
        self._disabled_nodes.difference_update(node_ids)
        logger.info(f"Enabled {len(node_ids)} nodes for pairing")

    def disable_areas(self, area_names: Set[str]) -> None:
        """Disable pairing cho specific areas."""
        self._disabled_areas.update(area_names)
        logger.info(f"Disabled {len(area_names)} areas for pairing")

    def enable_areas(self, area_names: Set[str]) -> None:
        """Enable pairing cho specific areas."""
        self._disabled_areas.difference_update(area_names)
        logger.info(f"Enabled {len(area_names)} areas for pairing")

    def _is_alive(self) -> bool:
        return self._alive

    def _is_paused(self) -> bool:
        """True khi STOP hoặc đang trong cửa sổ stabilize sau RUN."""
        if self._paused:
            return True
        return time.time() < self._resume_ready_at

    async def _consumer_loop(self) -> None:
        await self._pool.consumer_loop(self._is_alive, self._is_paused)

    async def _dispatcher_loop(self) -> None:
        assert self._dispatcher is not None
        await self._dispatcher.run_loop()

    async def start(self) -> None:
        await self._mongo.ensure_indexes()
        
        pair_client = MongoPairClient()
        pair_docs = await pair_client.get_all_pairs()
        
        self._start_to_area = {}
        self._end_to_area = {}
        self._empty_starts_by_area = {}
        for doc in pair_docs:
            start = doc.get("start")
            end = doc.get("end")
            area = doc.get("area_name", "UNKNOWN")
            if start:
                self._start_to_area[start] = area
            if end:
                self._end_to_area[end] = area
            if start and end is None:
                self._empty_starts_by_area.setdefault(area, []).append(start)
        
        logger.info(
            "Loaded %d pairs, %d areas with empty starts",
            len(pair_docs),
            len(self._empty_starts_by_area)
        )
        
        self._dispatcher = PairingDispatcher(
            state=self._state,
            validate_pairs=self._validate_pairs,
            end_to_starts=self._end_to_starts,
            ics=self._ics,
            mongo_client=self._mongo,
            pool=self._pool,
            pending_empty=self._pending_empty,
            snapshot_manager=self._snapshot_manager,
            worker_id=self._worker_id,
            lease_seconds=self._lease_seconds,
            is_alive=self._is_alive,
            is_paused=self._is_paused,
            start_to_area=self._start_to_area,
            end_to_area=self._end_to_area,
            empty_starts_by_area=self._empty_starts_by_area,
            get_disabled_nodes=lambda: self._disabled_nodes,
            get_disabled_areas=lambda: self._disabled_areas,
        )
        self._alive = True
        self._paused = False
        self._tasks = [
            asyncio.create_task(
                run_publisher_loop(
                    self._state,
                    self._mongo,
                    self._worker_id,
                    self._is_alive,
                    self._start_to_area,
                    is_paused=self._is_paused,
                ),
                name="start_event_publisher"
            ),
            asyncio.create_task(self._consumer_loop(), name="start_event_consumer"),
            asyncio.create_task(self._dispatcher_loop(), name="start_event_dispatcher"),
        ]
        logger.info("StartEventPairingOrchestrator started worker=%s", self._worker_id)

    async def stop(self) -> None:
        self._alive = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        logger.info("StartEventPairingOrchestrator stopped")
