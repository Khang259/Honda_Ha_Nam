from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.clients.mongo_pair_client import MongoPairClient

router = APIRouter()
pair_client = MongoPairClient()


class PairItem(BaseModel):
    start: str
    end: Optional[str] = None


class AreaPairsPayload(BaseModel):
    area_name: str
    pairs: List[PairItem]


class DeletePairsPayload(BaseModel):
    area_name: str
    pairs: List[PairItem]


@router.get("/all", response_model=List[Dict[str, Any]])
async def get_all_pairs():
    """Lấy tất cả validate pairs (tất cả area)."""
    docs = await pair_client.get_all_pairs()
    return docs


@router.get("/area/{area_name}", response_model=Dict[str, Any])
async def get_pairs_by_area(area_name: str):
    """Lấy validate pairs theo area_name."""
    doc = await pair_client.get_pairs_by_area(area_name)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Area {area_name} not found")
    return doc


@router.post("/create", response_model=Dict[str, str])
async def create_area(payload: AreaPairsPayload):
    """Tạo mới area với pairs. Lỗi 400 nếu area đã tồn tại."""
    try:
        pairs_dict = [p.model_dump() for p in payload.pairs]
        inserted_id = await pair_client.create_area(payload.area_name, pairs_dict)
        return {"message": f"Area {payload.area_name} created", "id": inserted_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/update", response_model=Dict[str, str])
async def update_area(payload: AreaPairsPayload):
    """Cập nhật toàn bộ pairs cho area đã tồn tại. Lỗi 404 nếu area không tồn tại."""
    pairs_dict = [p.model_dump() for p in payload.pairs]
    success = await pair_client.update_area(payload.area_name, pairs_dict)
    if not success:
        raise HTTPException(status_code=404, detail=f"Area {payload.area_name} not found")
    return {"message": f"Area {payload.area_name} updated"}


@router.delete("/pairs", response_model=Dict[str, str])
async def delete_pairs(payload: DeletePairsPayload):
    """Xóa 1 hoặc nhiều pairs cụ thể trong area."""
    pairs_dict = [p.model_dump() for p in payload.pairs]
    success = await pair_client.delete_pairs(payload.area_name, pairs_dict)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Area {payload.area_name} not found or pairs not matched",
        )
    return {"message": f"Deleted {len(pairs_dict)} pairs from area {payload.area_name}"}