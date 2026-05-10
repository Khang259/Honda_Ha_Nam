"""
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body, Path, Query
from api_http.schemas.node_id import NodeIdCreate, NodeIdUpdate
from persistence.mongo.mongo_node_id_client import MongoNodeIdClient

router = APIRouter()

_client = MongoNodeIdClient(collection_name="node_id_test")
_end_points_client = MongoNodeIdClient(collection_name="end_points")

@router.get("/all")
async def get_node_id_all() -> Dict[str, Any]:
    """Get all camera configs (alias of GET /node-id without area)."""
    items = await _client.get_all()
    return {"code": 1000, "message": "Success", "data": items}

@router.get("/area/{area}")
async def get_node_id_by_area(area: str) -> Dict[str, Any]:
    """Get all camera configs by area."""
    items = await _client.get_by_area(area)
    return {"code": 1000, "message": "Success", "data": items}

@router.post("/create-node-id")
async def create_node_id(payload: List[NodeIdCreate] = Body(...)) -> Dict[str, Any]:
    """
    Insert nhiều camera config documents vào MongoDB.
    Trả về số lượng tạo thành công và danh sách cameraId bị trùng (nếu có).
    """
    camera_docs = [item.model_dump() for item in payload]
    inserted_count, duplicate_ids = await _client.create_many(camera_docs)
    
    if duplicate_ids:
        return {
            "code": 1001,
            "message": f"Inserted {inserted_count} node_id(s), {len(duplicate_ids)} duplicate(s)",
            "count": inserted_count,
            "duplicate_camera_ids": duplicate_ids
        }
    
    return {
        "code": 1000,
        "message": f"Created {inserted_count} node_id(s) successfully",
        "count": inserted_count
    }

@router.put("/update-node-id/{camera_id}")
async def update_node_id_by_camera_id(
    camera_id: int = Path(..., description="cameraId of the document"),
    payload: NodeIdUpdate = Body(...),
) -> Dict[str, Any]:
    """Update one camera config document by cameraId."""
    update_data = payload.model_dump(exclude_unset=True)
    ok = await _client.update_by_camera_id(camera_id, update_data)
    return {"success": ok, "cameraId": camera_id}


@router.delete("/delete-node-id/{camera_id}")
async def delete_node_id_by_camera_id(camera_id: int = Path(..., description="cameraId of the document")) -> Dict[str, Any]:
    """Delete one camera config document by cameraId."""
    ok = await _client.delete_by_camera_id(camera_id)
    return {"success": ok, "cameraId": camera_id}


#TODO: check this function
@router.post("/update-empty-car-points")
async def update_empty_car_points(end_points: str) -> Dict[str, Any]:
    data = await _end_points_client.update_empty_car_points(end_points)
    return {
        "code": 1000,
        "message": "Success",
        "data": data
    }