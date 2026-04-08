"""
CRUD APIs for MongoDB `node_id` collection.

These endpoints expose the same operations as `MongoCameraClient` so other
services/tools can manage camera configs without going through BE.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Path, Query

from api.clients.mongo_camera_client import MongoCameraClient

router = APIRouter(prefix="/node-id", tags=["node_id"])

_client = MongoCameraClient(collection_name="node_id")


@router.get("")
async def get_node_id(area: Optional[str] = Query(default=None, description="Filter by area_name")) -> Dict[str, Any]:
    """
    Get camera configs from MongoDB.

    - If `area` is provided: returns only that area's cameras.
    - Else: returns all cameras.
    """
    if area:
        items = await _client.get_by_area(area)
        return {"success": True, "area": area.upper(), "items": items}
    items = await _client.get_all()
    return {"success": True, "items": items}


@router.get("/all")
async def get_node_id_all() -> Dict[str, Any]:
    """Get all camera configs (alias of GET /node-id without area)."""
    items = await _client.get_all()
    return {"success": True, "items": items}

@router.get("/area/{area}")
async def get_node_id_by_area(area: str) -> Dict[str, Any]:
    """Get all camera configs by area."""
    items = await _client.get_by_area(area)
    return {"success": True, "area": area.upper(), "items": items}

#TODO: check this if this right schema
@router.post("")
async def create_node_id(camera_doc: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Insert one camera config document into MongoDB."""
    inserted_id = await _client.create(camera_doc)
    return {"success": True, "inserted_id": inserted_id}

#TODO: check this if this right schema
@router.put("/{camera_id}")
async def update_node_id_by_camera_id(
    camera_id: int = Path(..., description="cameraId of the document"),
    update_data: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """Update one camera config document by cameraId."""
    ok = await _client.update_by_camera_id(camera_id, update_data)
    return {"success": ok, "cameraId": camera_id}


@router.delete("/{camera_id}")
async def delete_node_id_by_camera_id(camera_id: int = Path(..., description="cameraId of the document")) -> Dict[str, Any]:
    """Delete one camera config document by cameraId."""
    ok = await _client.delete_by_camera_id(camera_id)
    return {"success": ok, "cameraId": camera_id}

