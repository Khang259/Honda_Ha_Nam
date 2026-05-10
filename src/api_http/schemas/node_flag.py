"""Schema request cho gán flag node trong StateManager."""

from pydantic import BaseModel, Field


class NodeFlagRequest(BaseModel):
    """Body: đặt flag của node_id = enable."""

    id: str = Field(..., description="node_id trong StateManager (vd: start_10000060)")
    enable: bool = Field(..., description="Giá trị flag cần gán (flag == enable)")
