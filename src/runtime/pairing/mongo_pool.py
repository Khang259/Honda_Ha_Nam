from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict

from persistence.database import get_collection
from shared.setup_log import setup_logger

logger = setup_logger("start_event_pairing", "logs/start_event_pairing/log")


class MongoStartPool:
    """Đồng bộ pool start_events từ Mongo (change stream)."""
    def __init__(self, collection_name: str) -> None:
        self._collection_name = collection_name
        self.local_start_pool: Dict[str, Dict[str, Any]] = {}
        self.pool_lock = asyncio.Lock()

    async def load_initial(self) -> None:
        col = get_collection(self._collection_name)
        cursor = col.find({"flag": False, "status": "ready"}, {"_id": 0})
        docs = await cursor.to_list(length=None)
        async with self.pool_lock:
            for d in docs:
                nid = d.get("node_id")
                if nid:
                    self.local_start_pool[str(nid)] = d
        logger.info("start_event pool primed: %s docs", len(self.local_start_pool))

    async def apply_change(self, change: Dict[str, Any]) -> None:
        fd = change.get("fullDocument")
        if not fd:
            return
        nid = fd.get("node_id")
        if not nid:
            return
        nid = str(nid)
        async with self.pool_lock:
            if fd.get("flag") or fd.get("status") == "sent":
                self.local_start_pool.pop(nid, None)
            elif fd.get("status") == "ready" and not fd.get("flag"):
                self.local_start_pool[nid] = fd

    async def poll_pool(self) -> None:
        col = get_collection(self._collection_name)
        cursor = col.find({"flag": False, "status": "ready"}, {"_id": 0})
        docs = await cursor.to_list(length=None)
        async with self.pool_lock:
            for d in docs:
                nid = d.get("node_id")
                if nid:
                    self.local_start_pool[str(nid)] = d

    async def consumer_loop(self, is_running: Callable[[], bool]) -> None:
        col = get_collection(self._collection_name)
        await self.load_initial()
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
                    if not is_running():
                        break
                    await self.apply_change(change)
        except Exception as e:
            logger.warning("Change stream unavailable (%s); polling start_events", e)
            while is_running():
                try:
                    await self.poll_pool()
                except Exception as ex:
                    logger.error("poll pool error: %s", ex)
                await asyncio.sleep(2.0)
