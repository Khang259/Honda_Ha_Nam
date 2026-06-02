"""
Cluster Control Listener - watches MongoDB for cluster-wide start/stop commands.
Uses change stream with fallback polling.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from datetime import datetime, timedelta

from persistence.database import get_collection
from load_balancing.persistence.mongo_cluster_control_client import MongoClusterControlClient
import api.state as api_state
from shared.setup_log import setup_logger

logger = setup_logger("cluster_control_listener", "logs/cluster_control_listener/log")


class ClusterControlListener:
    """
    Listens to MongoDB engine_control_status collection for cluster commands.
    Applies RUN/STOP commands to local camera_manager, inference_engine, and pairing_orchestrator.
    """
    
    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.client = MongoClusterControlClient()
        self.last_applied_token: int = -1
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def bootstrap(self) -> None:
        """
        Load initial state from MongoDB on startup.
        Apply if token is newer than last_applied_token.
        """
        try:
            status = await self.client.get_current_status()
            token = status.get("token", 0)
            desired_state = status.get("desired_state", "STOP")
            
            logger.info(
                f"Bootstrap: current cluster state={desired_state}, token={token}, "
                f"last_applied={self.last_applied_token}"
            )
            
            if token > self.last_applied_token:
                await self._apply_command(desired_state, token)
            else:
                logger.info("Bootstrap: no new commands to apply")
                
        except Exception as e:
            logger.error(f"Bootstrap error: {e}")
    
    async def _apply_command(self, desired_state: str, token: int) -> None:
        """
        Apply cluster command locally.
        
        Args:
            desired_state: "RUN" or "STOP"
            token: Token value of the command
        """
        # Guard: only apply if components are initialized
        if not api_state.camera_manager or not api_state.inference_engine:
            logger.warning(
                f"Cannot apply {desired_state}: camera_manager or inference_engine not initialized"
            )
            return
        
        try:
            if desired_state == "RUN":
                logger.info(f"Applying RUN command (token={token})")
                
                # Start all cameras
                api_state.camera_manager.start_all_cameras()
                
                # Resume inference engine
                api_state.inference_engine.resume()
                
                # Resume pairing orchestrator if available
                if api_state.pairing_orchestrator:
                    api_state.pairing_orchestrator.resume()
                
                logger.info(f"RUN command applied successfully (token={token})")
                
            elif desired_state == "STOP":
                logger.info(f"Applying STOP command (token={token})")
                
                # Stop all cameras
                api_state.camera_manager.stop_all_cameras()
                
                # Pause inference engine
                api_state.inference_engine.pause()
                
                # Pause pairing orchestrator if available
                if api_state.pairing_orchestrator:
                    api_state.pairing_orchestrator.pause()
                
                logger.info(f"STOP command applied successfully (token={token})")
            
            else:
                logger.warning(f"Unknown desired_state: {desired_state}")
                return
            
            # Update last applied token
            self.last_applied_token = token
            
            # Write acknowledgment to MongoDB
            await self.client.write_ack(
                worker_id=self.worker_id,
                token=token,
                applied_state=desired_state
            )
            
        except Exception as e:
            logger.error(f"Error applying {desired_state} command (token={token}): {e}")
    
    async def _handle_change(self, change: Dict[str, Any]) -> None:
        """
        Handle a change stream event.
        
        Args:
            change: Change event from MongoDB
        """
        try:
            full_doc = change.get("fullDocument")
            if not full_doc:
                return
            
            token = full_doc.get("token", 0)
            desired_state = full_doc.get("desired_state")
            
            if not desired_state:
                return
            
            # Dedupe: only apply if token is newer
            if token > self.last_applied_token:
                logger.info(
                    f"Change detected: state={desired_state}, token={token}, "
                    f"last_applied={self.last_applied_token}"
                )
                await self._apply_command(desired_state, token)
            else:
                logger.debug(
                    f"Ignoring change with token={token} (already applied {self.last_applied_token})"
                )
                
        except Exception as e:
            logger.error(f"Error handling change: {e}")
    
    async def _poll_status(self) -> None:
        """
        Poll MongoDB for current status (fallback when change stream unavailable).
        """
        try:
            status = await self.client.get_current_status()
            token = status.get("token", 0)
            desired_state = status.get("desired_state", "STOP")
            
            if token > self.last_applied_token:
                logger.info(
                    f"Poll detected new command: state={desired_state}, token={token}"
                )
                await self._apply_command(desired_state, token)
                
        except Exception as e:
            logger.error(f"Poll error: {e}")
    
    async def _watch_loop(self) -> None:
        """
        Main loop: watch change stream with fallback to polling.
        """
        collection_name = self.client._status_collection
        col = get_collection(collection_name)
        
        # Bootstrap first
        await self.bootstrap()
        
        try:
            # Try to use change stream
            pipeline = [
                {
                    "$match": {
                        "operationType": {"$in": ["insert", "update", "replace"]},
                        "fullDocument._id": "inference_status"
                    }
                }
            ]
            
            logger.info("Starting change stream watch on engine_control_status")
            
            async with col.watch(pipeline, full_document="updateLookup") as stream:
                async for change in stream:
                    if not self._running:
                        break
                    await self._handle_change(change)
                    
        except Exception as e:
            logger.warning(f"Change stream unavailable ({e}); falling back to polling")
            
            # Fallback to polling every 2 seconds
            while self._running:
                try:
                    await self._poll_status()
                except Exception as poll_err:
                    logger.error(f"Poll error: {poll_err}")
                
                await asyncio.sleep(2.0)
    
    async def start(self) -> None:
        """
        Start the listener.
        """
        if self._running:
            logger.warning("Listener already running")
            return
        
        self._running = True
        logger.info(f"Starting cluster control listener for worker {self.worker_id}")
        
        # Run watch loop
        await self._watch_loop()
    
    async def stop(self) -> None:
        """
        Stop the listener.
        """
        if not self._running:
            return
        
        logger.info("Stopping cluster control listener")
        self._running = False
        
        # Give time for current operation to complete
        await asyncio.sleep(0.5)
