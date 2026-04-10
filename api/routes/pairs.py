from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from api.clients.mongo_pair_client import MongoPairClient
from api.schemas.pair import (
    AddPairsPayload,
    DeletePairsPayload,
    UpdatePairsPayload,
)

router = APIRouter()
pair_client = MongoPairClient()


@router.get("/all", response_model=List[Dict[str, Any]])
async def get_all_pairs():
    """Lấy tất cả validate pairs (tất cả area)."""
    docs = await pair_client.get_all_pairs()
    return docs


@router.get("/{area_name}", response_model=List[Dict[str, Any]])
async def get_pairs_by_area(area_name: str):
    """Lấy validate pairs theo area_name."""
    docs = await pair_client.get_pairs_by_area(area_name)
    return docs


@router.post("/add")
async def add_pairs(payload: AddPairsPayload) -> Dict[str, Any]:
    """
    Thêm 1 hoặc nhiều pairs vào hệ thống.
    Mỗi document có created_at và updated_at (cùng thời điểm khi tạo).
    """
    pairs_dict = [p.model_dump() for p in payload.pairs]
    inserted_count, duplicate_pairs = await pair_client.add_pairs(
        payload.area_name, pairs_dict
    )

    if duplicate_pairs:
        return {
            "code": 1001,
            "message": f"Inserted {inserted_count} pair(s), {len(duplicate_pairs)} duplicate(s) skipped",
            "count": inserted_count,
            "duplicates": duplicate_pairs,
        }

    return {
        "code": 1000,
        "message": f"Inserted {inserted_count} pair(s) successfully",
        "count": inserted_count,
    }


@router.put("/update")
async def update_pairs(payload: UpdatePairsPayload) -> Dict[str, Any]:
    """
    Cập nhật 1 hoặc nhiều pairs: tìm theo `match`, gán new_start/new_end/area_name nếu có.
    Luôn cập nhật `updated_at`. Nếu bản ghi thiếu `created_at` thì gán lúc cập nhật.
    """
    items = [u.model_dump(exclude_unset=True) for u in payload.updates]
    modified_count, not_found = await pair_client.update_pairs(items)

    if not_found:
        return {
            "code": 1002,
            "message": f"Updated {modified_count} pair(s); {len(not_found)} match(es) not found",
            "count": modified_count,
            "not_found": not_found,
        }

    return {
        "code": 1000,
        "message": f"Updated {modified_count} pair(s) successfully",
        "count": modified_count,
    }


@router.delete("/delete")
async def delete_pairs(payload: DeletePairsPayload) -> Dict[str, Any]:
    """Xóa 1 hoặc nhiều pairs cụ thể theo start và end."""
    pairs_dict = [p.model_dump() for p in payload.pairs]
    deleted_count = await pair_client.delete_pairs(pairs_dict)

    if deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="No matching pairs found to delete",
        )

    return {
        "code": 1000,
        "message": f"Deleted {deleted_count} pair(s) successfully",
        "count": deleted_count,
    }
