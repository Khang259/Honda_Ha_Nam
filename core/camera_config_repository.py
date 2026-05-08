from __future__ import annotations

from typing import Any, Dict, List, Optional


def _normalize_roi_value(value: Any) -> Optional[List[int]]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        try:
            return [int(value[0]), int(value[1]), int(value[2]), int(value[3])]
        except Exception:
            return None
    return None


def _normalize_rois(rois: Any) -> Dict[str, List[int]]:
    if not isinstance(rois, dict):
        return {}

    normalized: Dict[str, List[int]] = {}
    for k, v in rois.items():
        roi = _normalize_roi_value(v)
        if roi is None:
            continue
        normalized[str(k)] = roi
    return normalized


def load_cameras_from_mongodb(
    *,
    mongodb_url: str,
    db_name: str,
    collection_name: str = "node_id_test",
    worker_id: Optional[str] = None,
    connect_timeout_ms: int = 2000,
    server_selection_timeout_ms: int = 2000,
) -> List[Dict[str, Any]]:
    from pymongo import MongoClient

    client = MongoClient(
        mongodb_url,
        connectTimeoutMS=connect_timeout_ms,
        serverSelectionTimeoutMS=server_selection_timeout_ms,
    )
    try:
        col = client[db_name][collection_name]
        # Filter by worker_id if provided
        query = {"current_worker": worker_id} if worker_id else {}
        docs = list(col.find(query).sort("cameraId", 1))
    finally:
        try:
            client.close()
        except Exception:
            pass

    cameras: List[Dict[str, Any]] = []
    for idx, doc in enumerate(docs):
        if not isinstance(doc, dict):
            continue

        url = doc.get("url") or doc.get("rtsp")
        if not url:
            continue

        camera_id = doc.get("cameraId", idx)
        try:
            camera_id = int(camera_id)
        except Exception:
            camera_id = idx

        cameras.append(
            {
                "url": url,
                "cameraId": camera_id,
                "source_owner": doc.get("source_owner", 1),
                "type_model": doc.get("type_model", 1),
                "node_id": doc.get("node_id", 1),
                "area_name": doc.get("area_name"),
                "rois": _normalize_rois(doc.get("rois")),
            }
        )

    cameras.sort(key=lambda c: c.get("cameraId", 0))
    return cameras

