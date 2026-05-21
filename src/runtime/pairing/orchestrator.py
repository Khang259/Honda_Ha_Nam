"""
Distributed pairing: publish start_* Mongo, consume pool, match end local,
atomic claim + POST ICS. Empty-car / double (15s) giống PairManager.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Set, Tuple

from inference_core.state_manager import StateManager
from persistence.mongo.mongo_pair_client import MongoPairClient
from persistence.mongo.mongo_start_event_client import MongoStartEventClient
from shared.setup_log import setup_logger

from runtime.pairing.dispatcher import PairingDispatcher
from runtime.pairing.ics_client import IcsClient
from runtime.pairing.mongo_pool import MongoStartPool
from runtime.pairing.publisher import run_publisher_loop
from runtime.pairing.validate_pairs_graph import build_end_to_starts

logger = setup_logger("start_event_pairing", "logs/start_event_pairing/log")


class StartEventPairingOrchestrator:
    def __init__(
        self,
        worker_id: str,
        state_manager: StateManager,
        validate_pairs: Set[Tuple[str, ...]],
        ics_url: str,
        snapshot_manager: Optional[Any] = None,
        lease_seconds: int = 20,
    ) -> None:
        self._worker_id = worker_id
        self._state = state_manager
        self._validate_pairs = validate_pairs
        self._snapshot_manager = snapshot_manager
        self._lease_seconds = lease_seconds
        self._mongo = MongoStartEventClient()
        self._end_to_starts = build_end_to_starts(validate_pairs)
        self._running = False
        self._paused = False
        self._disabled_nodes: Set[str] = set()
        self._tasks: List[asyncio.Task] = []
        self._pending_empty: List[Tuple[str, float]] = []
        self._start_events_collection = "start_events_test"

        self._ics = IcsClient(ics_url)
        self._pool = MongoStartPool(self._start_events_collection)
        self._dispatcher: Optional[PairingDispatcher] = None
        self._start_to_area: Dict[str, str] = {}
        self._empty_starts_by_area: Dict[str, List[str]] = {}

    def pause(self) -> None:
        """Pause pairing (stop POST ICS)."""
        self._paused = True
        logger.info("PairingOrchestrator paused")

    def resume(self) -> None:
        """Resume pairing."""
        self._paused = False
        self._disabled_nodes.clear()
        logger.info("PairingOrchestrator resumed")

    def disable_nodes(self, node_ids: Set[str]) -> None:
        """Disable pairing cho specific nodes (zone/camera)."""
        self._disabled_nodes.update(node_ids)
        logger.info(f"Disabled {len(node_ids)} nodes for pairing")

    def enable_nodes(self, node_ids: Set[str]) -> None:
        """Enable pairing cho specific nodes."""
        self._disabled_nodes.difference_update(node_ids)
        logger.info(f"Enabled {len(node_ids)} nodes for pairing")

    def _is_running(self) -> bool:
        return self._running and not self._paused

    async def _consumer_loop(self) -> None:
        await self._pool.consumer_loop(self._is_running)

    async def _dispatcher_loop(self) -> None:
        assert self._dispatcher is not None
        await self._dispatcher.run_loop()

    async def start(self) -> None:
        await self._mongo.ensure_indexes()
        
        pair_client = MongoPairClient()
        pair_docs = await pair_client.get_all_pairs()
        
        self._start_to_area = {}
        self._empty_starts_by_area = {}
        for doc in pair_docs:
            start = doc.get("start")
            area = doc.get("area_name", "UNKNOWN")
            if start:
                self._start_to_area[start] = area
                if doc.get("end") is None:
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
            is_running=self._is_running,
            start_to_area=self._start_to_area,
            empty_starts_by_area=self._empty_starts_by_area,
            get_disabled_nodes=lambda: self._disabled_nodes,
        )
        self._running = True
        self._tasks = [
            asyncio.create_task(
                run_publisher_loop(
                    self._state,
                    self._mongo,
                    self._worker_id,
                    self._is_running,
                    self._start_to_area,
                ),
                name="start_event_publisher"
            ),
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
