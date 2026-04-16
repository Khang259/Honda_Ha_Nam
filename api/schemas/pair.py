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


class PairUpdateItem(BaseModel):
    """
    Cập nhật 1 pair: tìm theo `pairs`, gán giá trị mới nếu có.
    Nếu không truyền new_start/new_end/area_name thì chỉ cập nhật timestamp (updated_at).
    """
    pairs: PairItem = Field(..., description="Cặp (start, end) hiện có trong DB")
    new_start: Optional[str] = Field(None, description="Start mới (giữ nguyên nếu bỏ qua)")
    new_end: Optional[str] = Field(None, description="End mới (giữ nguyên nếu bỏ qua)")
    area_name: Optional[str] = Field(None, description="Area mới (giữ nguyên nếu bỏ qua)")


class UpdatePairsPayload(BaseModel):
    """Schema để cập nhật 1 hoặc nhiều pairs."""
    updates: List[PairUpdateItem] = Field(
        ...,
        min_length=1,
        description="Danh sách cập nhật (pairs + field mới tùy chọn)",
    )


class DeletePairsPayload(BaseModel):
    """Schema để xóa 1 hoặc nhiều pairs."""
    pairs: List[PairItem] = Field(..., min_length=1, description="List of pairs to delete")
