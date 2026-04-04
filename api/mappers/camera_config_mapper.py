"""
Map BE /node_id responses (list or dict) to internal camera configs for CameraManager.
"""

from __future__ import annotations

from typing import Any, Dict, List, Union

BeNodeResponse = Union[Dict[str, Any], List[Any]]


def map_be_node_response_to_cameras(data: BeNodeResponse) -> List[Dict[str, Any]]:
    """
    BE may return:
    - JSON array: list of camera documents (GET /node_id/{area}, GET /node_id/all)
    - JSON object with key "cameras": list
    - JSON object: single camera document
    """
    if isinstance(data, list):
        return [_normalize_camera_item(x) for x in data if isinstance(x, dict)]

    if not isinstance(data, dict):
        raise ValueError("BE /node_id response must be a JSON object or array")

    if isinstance(data.get("cameras"), list):
        return [_normalize_camera_item(item) for item in data["cameras"] if isinstance(item, dict)]

    return [_normalize_camera_item(data)]


def map_be_node_doc_to_cameras(be_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Backward-compatible alias for dict-only callers."""
    return map_be_node_response_to_cameras(be_doc)


def _normalize_camera_item(item: Dict[str, Any]) -> Dict[str, Any]:
    url = item.get("url") or item.get("rtsp")
    if not url:
        raise ValueError("camera item missing url/rtsp")

    rois = item.get("rois") or {}

    area_name = item.get("area_name") or item.get("zone")
    if not area_name:
        area_name = "AE5"

    normalized: Dict[str, Any] = {
        "url": url,
        "area_name": area_name,
        "cameraId": item.get("cameraId", item.get("camera_id", 0)),
        "source_owner": item.get("source_owner", 1),
        "type_model": item.get("type_model", 1),
        "node_id": item.get("node_id", 1),
        "rois": rois,
    }
    return normalized
