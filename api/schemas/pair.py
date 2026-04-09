from typing import Optional, List
from pydantic import BaseModel, Field


class PairItem(BaseModel):
    """Schema cho 1 pair (start-end)."""
    start: str = Field(..., description="Start node ID")
    end: Optional[str] = Field(None, description="End node ID (null for empty vehicle)")


class AddPairsPayload(BaseModel):
    """Schema để thêm 1 hoặc nhiều pairs."""
    area_name: str = Field(..., description="Area name (e.g., AE5, AE6)")
    pairs: List[PairItem] = Field(..., min_length=1, description="List of pairs to add")


class DeletePairsPayload(BaseModel):
    """Schema để xóa 1 hoặc nhiều pairs."""
    pairs: List[PairItem] = Field(..., min_length=1, description="List of pairs to delete")
