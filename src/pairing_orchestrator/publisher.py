"""Đẩy start_* ready lên Mongo start_events."""

from __future__ import annotations

import asyncio
from typing import Callable, Dict

from inference_engine.state_manager import StateManager
from pairing_orchestrator.persistence.mongo_start_event_client import MongoStartEventClient
from shared.setup_log import setup_logger

logger = setup_logger("start_event_pairing", "logs/start_event_pairing/log")


async def run_publisher_loop(
    state: StateManager,
    mongo_client: MongoStartEventClient,
    worker_id: str,
    is_running: Callable[[], bool],
    start_to_area: Dict[str, str],
    sleep_seconds: float = 1.0,
) -> None:
    while is_running():
        try:
            state.process_starts()
            for node_id in state.snapshot_ready_starts():
                if not str(node_id).startswith("start_"):
                    continue
                cam = state.get_camera_id_for_node(node_id)
                area_name = start_to_area.get(str(node_id))
                await mongo_client.upsert_ready(
                    node_id=str(node_id),
                    camera_id=cam,
                    assign_worker=worker_id,
                    area_name=area_name,
                )
        except Exception as e:
            logger.error("publisher loop error: %s", e, exc_info=True)
        await asyncio.sleep(sleep_seconds)
