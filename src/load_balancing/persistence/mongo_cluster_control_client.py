"""
MongoDB client for cluster control operations.
Manages engine_control_status and engine_control_acks collections.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from persistence.database import get_collection
from shared.setup_log import setup_logger

logger = setup_logger("mongo_cluster_control_client", "logs/mongo_cluster_control_client/log")


class MongoClusterControlClient:
    """Client for cluster control coordination via MongoDB."""
    
    def __init__(
        self, 
        status_collection: str = "engine_control_status",
        acks_collection: str = "engine_control_acks"
    ):
        self._status_collection = status_collection
        self._acks_collection = acks_collection
    
    async def update_desired_state(
        self, 
        state: str, 
        updated_by_worker: str
    ) -> Dict[str, Any]:
        """
        Atomically update desired state and increment token.
        
        Args:
            state: "RUN" or "STOP"
            updated_by_worker: worker_id that received the HTTP request
            
        Returns:
            dict with keys: desired_state, token, timestamp, updated_by_worker
        """
        col = get_collection(self._status_collection)
        
        now = datetime.utcnow()
        now_vietnam = now + timedelta(hours=7)
        timestamp = now_vietnam.strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            result = await col.find_one_and_update(
                {"_id": "inference_status"},
                {
                    "$set": {
                        "desired_state": state,
                        "updated_by_worker": updated_by_worker,
                        "timestamp": timestamp,
                        "timestamp_utc": now
                    },
                    "$inc": {"token": 1}
                },
                upsert=True,
                return_document=True  # Return document after update
            )
            
            if result:
                logger.info(
                    f"Cluster control updated: state={state}, token={result.get('token')}, "
                    f"by_worker={updated_by_worker}"
                )
                return {
                    "desired_state": result.get("desired_state"),
                    "token": result.get("token", 0),
                    "timestamp": result.get("timestamp"),
                    "updated_by_worker": result.get("updated_by_worker")
                }
            else:
                logger.error("Failed to update cluster control status")
                return {"desired_state": state, "token": 0, "timestamp": timestamp}
                
        except Exception as e:
            logger.error(f"Error updating cluster control: {e}")
            raise
    
    async def get_current_status(self) -> Dict[str, Any]:
        """
        Get current cluster control status document.
        
        Returns:
            dict with desired_state, token, timestamp, etc.
            Returns default if document doesn't exist.
        """
        col = get_collection(self._status_collection)
        
        try:
            doc = await col.find_one({"_id": "inference_status"}, {"_id": 0})
            
            if doc:
                return {
                    "desired_state": doc.get("desired_state", "STOP"),
                    "token": doc.get("token", 0),
                    "timestamp": doc.get("timestamp"),
                    "updated_by_worker": doc.get("updated_by_worker")
                }
            else:
                # Return default if no document exists yet
                return {
                    "desired_state": "STOP",
                    "token": 0,
                    "timestamp": None,
                    "updated_by_worker": None
                }
                
        except Exception as e:
            logger.error(f"Error getting current status: {e}")
            return {
                "desired_state": "STOP",
                "token": 0,
                "timestamp": None,
                "updated_by_worker": None
            }
    
    async def write_ack(
        self, 
        worker_id: str, 
        token: int, 
        applied_state: str
    ) -> bool:
        """
        Write acknowledgment that worker has applied the command.
        
        Args:
            worker_id: ID of worker
            token: Token value that was applied
            applied_state: State that was applied ("RUN" or "STOP")
            
        Returns:
            bool: True if successful
        """
        col = get_collection(self._acks_collection)
        
        now = datetime.utcnow()
        now_vietnam = now + timedelta(hours=7)
        applied_at = now_vietnam.strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            result = await col.update_one(
                {
                    "worker_id": worker_id,
                    "token": token
                },
                {
                    "$set": {
                        "applied_state": applied_state,
                        "applied_at": applied_at,
                        "applied_at_utc": now
                    }
                },
                upsert=True
            )
            
            if result.upserted_id or result.modified_count > 0:
                logger.debug(
                    f"Ack written: worker={worker_id}, token={token}, state={applied_state}"
                )
                return True
            else:
                logger.warning(f"Failed to write ack: worker={worker_id}, token={token}")
                return False
                
        except Exception as e:
            logger.error(f"Error writing ack: {e}")
            return False
    
    async def get_acks(self, token: int) -> List[Dict[str, Any]]:
        """
        Get all acknowledgments for a specific token.
        
        Args:
            token: Token value to query
            
        Returns:
            List of ack documents (worker_id, applied_state, applied_at)
        """
        col = get_collection(self._acks_collection)
        
        try:
            cursor = col.find(
                {"token": token},
                {"_id": 0, "worker_id": 1, "token": 1, "applied_state": 1, "applied_at": 1}
            ).sort("applied_at", -1)
            
            acks = await cursor.to_list(length=None)
            return acks
            
        except Exception as e:
            logger.error(f"Error getting acks for token {token}: {e}")
            return []
    
    async def get_all_acks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent acks across all tokens (for monitoring/debugging).
        
        Args:
            limit: Max number of acks to return
            
        Returns:
            List of recent ack documents
        """
        col = get_collection(self._acks_collection)
        
        try:
            cursor = col.find(
                {},
                {"_id": 0}
            ).sort("applied_at_utc", -1).limit(limit)
            
            acks = await cursor.to_list(length=None)
            return acks
            
        except Exception as e:
            logger.error(f"Error getting all acks: {e}")
            return []
