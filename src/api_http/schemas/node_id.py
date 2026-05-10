from typing import Optional, Dict, List, Tuple
from datetime import datetime
from pydantic import BaseModel, Field

class NodeIdCreate(BaseModel):
    url: str = Field(..., description="RTSP of the camera")
    cameraId: int = Field(..., description="Camera ID (unique)")
    source_owner: Optional[str] = Field(None, description="Source owner from which PC")
    type_model: Optional[str] = Field(None, description="Type model of the models")
    node_id: str = Field(..., description="Task path where put the camera")
    area_name: Optional[str] = Field(None, description="Area name")
    rois: Optional[Dict[str, Tuple[float, float, float, float]]] = Field(
        default_factory=dict,
        description="ROIs of the camera with format [x,y,w,h]",
        max_length = 4,
        min_length = 4
    )
    current_worker: Optional[str] = Field(None, description="Worker ID currently assigned to this camera")
    fencing_token: int = Field(default=0, description="Fencing token to prevent worker conflicts")
    last_assigned: Optional[datetime] = Field(None, description="Timestamp when camera was last assigned")

class NodeIdUpdate(BaseModel):
    url: Optional[str] = Field(None, description="RTSP of the camera")
    cameraId: Optional[int] = Field(None, description="Camera ID")
    source_owner: Optional[int] = Field(None, description="Source owner from which PC")
    type_model: Optional[int] = Field(None, description="Type model of the models")
    node_id: Optional[str] = Field(None, description="Task path where put the camera")
    area_name: Optional[str] = Field(None, description="Area name")
    rois: Optional[Dict[str, Tuple[float, float, float, float]]] = Field(None, description="ROIs of the camera with format [x,y,w,h]")
    current_worker: Optional[str] = Field(None, description="Worker ID currently assigned to this camera")
    fencing_token: Optional[int] = Field(None, description="Fencing token to prevent worker conflicts")
    last_assigned: Optional[datetime] = Field(None, description="Timestamp when camera was last assigned")
