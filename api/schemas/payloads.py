from typing import Optional

from pydantic import BaseModel


class WebhookPayload(BaseModel):
    """Webhook payload from external server (ICS)."""

    orderId: str
    status: int
    shelfCurrPosition: Optional[str] = None
    subTaskStatus: Optional[str] = None
    deviceCode: Optional[str] = None
    modelProcessCode: Optional[str] = None
    subTaskTypeId: Optional[str] = None
    subTaskId: Optional[str] = None
    deviceNum: Optional[str] = None
    qrContent: Optional[str] = None
    qrCode: Optional[str] = None
    subTaskSeq: Optional[str] = None
    shelfNumber: Optional[str] = None
    icsTaskOrderDetailId: Optional[str] = None
    processRate: Optional[str] = None


class DetectionPayload(BaseModel):
    """Detection result sent by AI worker."""

    cam_id: str
    node_id: str
    detected: bool
    coverage: Optional[float] = None


class CameraControlPayload(BaseModel):
    """Camera control payload from UI."""

    camera_index: int
    enabled: bool

