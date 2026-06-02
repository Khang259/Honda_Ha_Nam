from pydantic import BaseModel, Field

class CameraFlagRequest(BaseModel):
    """Body: đặt flag của camera_id = enable."""

    id: str = Field(..., description="camera_id trong Mongo (vd: 1)")
    enable: bool = Field(..., description="")
