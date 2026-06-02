"""
MongoDB client for start-events shared storage.

Collection design:
- 1 document per start node_id (unique).
- Workers publish start_* ready events (flag=false).
- Workers claim via lease to avoid duplicate sends.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pymongo import ReturnDocument

from persistence.database import get_collection
from shared.setup_log import setup_logger

logger = setup_logger("mongo_start_event_client", "logs/mongo_start_event_client/log")


class MongoStartEventClient:
    def __init__(self, collection_name: str = "start_events_test", node_collection_name: str = "node_id"):
        self._collection_name = collection_name
        self._node_collection_name = node_collection_name

    async def ensure_indexes(self) -> None:
        """Create required indexes (idempotent)."""
        col = get_collection(self._collection_name)
        try:
            await col.create_index([("node_id", 1)], unique=True, name="uniq_node_id")
            await col.create_index(
                [("status", 1), ("flag", 1), ("claim_until", 1)],
                name="status_flag_claimUntil",
            )
            await col.create_index(
                [("order_id", 1), ("flag", 1)],
                name="orderId_flag",
            )
        except Exception as e:
            logger.error(f"Failed to ensure indexes: {e}")

    async def _get_camera_fencing_token(self, camera_id: int) -> Optional[int]:
        """Fetch fencing_token from node_id for a camera (best-effort)."""
        try:
            col = get_collection(self._node_collection_name)
            doc = await col.find_one({"cameraId": int(camera_id)}, {"fencing_token": 1, "_id": 0})
            if not doc:
                return None
            token = doc.get("fencing_token")
            return int(token) if token is not None else None
        except Exception:
            return None

    async def upsert_ready(
        self,
        *,
        node_id: str,
        camera_id: Optional[int],
        assign_worker: str,
        area_name: Optional[str] = None,
    ) -> bool:
        """
        Publish/refresh a ready start-event.
        - Do not overwrite a sent event (flag=true).
        - Keep flag=false for retry semantics.
        """
        try:
            col = get_collection(self._collection_name)
            existing = await col.find_one({"node_id": node_id}, {"_id": 1, "flag": 1})
            if existing is not None and existing.get("flag") is True:
                return True

            now = datetime.utcnow()

            fencing_token: Optional[int] = None
            if camera_id is not None:
                fencing_token = await self._get_camera_fencing_token(int(camera_id))

            filt: Dict[str, Any] = {"node_id": node_id, "flag": {"$ne": True}}
            update: Dict[str, Any] = {
                "$setOnInsert": {
                    "node_id": node_id,
                    "created_at": now,
                },
                "$set": {
                    "cameraId": int(camera_id) if camera_id is not None else None,
                    "assign_worker": assign_worker,
                    "last_worker": assign_worker,
                    "status": "ready",
                    "flag": False,
                    "ready_at": now,
                    "updated_at": now,
                    "area_name": area_name if area_name else None,
                },
            }
            if fencing_token is not None:
                update["$set"]["fencing_token"] = int(fencing_token)

            await col.update_one(filt, update, upsert=True)
            return True
        except Exception as e:
            logger.error(f"Failed to upsert_ready for {node_id}: {e}", exc_info=True)
            return False

    async def claim_ready(
        self,
        *,
        node_id: str,
        worker_id: str,
        lease_seconds: int = 20,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Atomic claim a ready event via lease.
        Claim succeeds only when:
        - flag == false
        - status == ready
        - claim_until is missing or <= now
        """
        try:
            col = get_collection(self._collection_name)
            now = datetime.utcnow()
            claim_until = now + timedelta(seconds=int(lease_seconds))

            filt = {
                "node_id": node_id,
                "flag": False,
                "status": "ready",
                "$or": [{"claim_until": {"$exists": False}}, {"claim_until": {"$lte": now}}],
            }
            update = {
                "$set": {
                    "status": "claimed",
                    "claim_owner": worker_id,
                    "claim_until": claim_until,
                    "last_worker": worker_id,
                    "updated_at": now,
                }
            }

            doc = await col.find_one_and_update(
                filt, update, return_document=ReturnDocument.AFTER
            )
            if not doc:
                return False, None

            doc.pop("_id", None)
            return True, doc
        except Exception as e:
            logger.error(f"Failed to claim_ready for {node_id}: {e}", exc_info=True)
            return False, None

    async def mark_sent(self, *, node_id: str, worker_id: str, order_id: str) -> bool:
        """Mark an event sent successfully (flag=true)."""
        try:
            col = get_collection(self._collection_name)
            now = datetime.utcnow()
            result = await col.update_one(
                {"node_id": node_id},
                {
                    "$set": {
                        "flag": True,
                        "status": "sent",
                        "order_id": order_id,
                        "sent_at": now,
                        "last_worker": worker_id,
                        "updated_at": now,
                    },
                    "$unset": {"claim_owner": "", "claim_until": ""},
                },
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to mark_sent for {node_id}: {e}", exc_info=True)
            return False

    async def unlock_to_ready(self, *, node_id: str, worker_id: str) -> bool:
        """
        Unlock a claimed event back to ready (keep flag=false) for retry.
        Useful when external request failed.
        """
        try:
            col = get_collection(self._collection_name)
            now = datetime.utcnow()
            result = await col.update_one(
                {"node_id": node_id, "flag": False},
                {
                    "$set": {"status": "ready", "last_worker": worker_id, "updated_at": now},
                    "$unset": {"claim_owner": "", "claim_until": ""},
                },
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to unlock_to_ready for {node_id}: {e}", exc_info=True)
            return False

    async def reset_all_sent_to_pending(self) -> Dict[str, Any]:
        """
        Reset TẤT CẢ docs có flag=True và status=sent thành flag=False và status=pending.
        
        Returns:
            Dict với count và thông tin reset
        """
        try:
            col = get_collection(self._collection_name)
            now = datetime.utcnow()
            
            result = await col.update_many(
                {"flag": True, "status": "sent"},
                {
                    "$set": {
                        "flag": False,
                        "status": "pending",
                        "updated_at": now,
                        "admin_reset_at": now,
                    },
                    "$unset": {
                        "claim_owner": "",
                        "claim_until": "",
                        "sent_at": "",
                    },
                },
            )
            
            count = result.modified_count
            logger.info(f"Reset {count} sent events to pending")
            return {
                "success": True,
                "count": count,
                "message": f"Reset {count} docs from sent to pending"
            }
        except Exception as e:
            logger.error(f"Failed to reset_all_sent_to_pending: {e}", exc_info=True)
            return {
                "success": False,
                "count": 0,
                "error": str(e)
            }

    async def reset_to_pending_after_delay(
        self,
        *,
        node_id: str,
        worker_id: str,
        delay_seconds: int = 5,
    ) -> bool:
        """
        Webhook-driven reset for distributed mode.

        Requirement: after webhook reset, wait delay_seconds (default 30s),
        then atomically update start_events doc:
        - status = "pending"
        - flag = False
        and clear lease/sent metadata.
        """
        await asyncio.sleep(max(0, int(delay_seconds)))
        try:
            col = get_collection(self._collection_name)
            now = datetime.utcnow()
            result = await col.update_one(
                {"node_id": node_id},
                {
                    "$set": {
                        "status": "pending",
                        "flag": False,
                        "last_worker": worker_id,
                        "updated_at": now,
                        "reset_by_webhook_at": now,
                    },
                    "$unset": {
                        "claim_owner": "",
                        "claim_until": "",
                        "sent_at": "",
                    },
                },
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(
                f"Failed to reset_to_pending_after_delay for {node_id}: {e}",
                exc_info=True,
            )
            return False

    async def get_starts_by_order_id(self, order_id: str) -> List[Dict[str, Any]]:
        """Query all start_ nodes for a given order_id."""
        try:
            col = get_collection(self._collection_name)
            cursor = col.find(
                {"order_id": order_id},
                {"_id": 0, "node_id": 1, "area_name": 1, "flag": 1}
            )
            docs = await cursor.to_list(length=None)
            return docs
        except Exception as e:
            logger.error(f"Failed to get_starts_by_order_id {order_id}: {e}")
            return []

