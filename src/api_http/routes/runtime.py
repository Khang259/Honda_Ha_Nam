from __future__ import annotations

from fastapi import APIRouter

from api_http.settings import settings
from runtime.runtime_service import runtime_service


router = APIRouter()


@router.get("/status")
async def get_runtime_status():
    return runtime_service.status()


@router.post("/reload")
async def reload_runtime(area: str | None = None):
    target_area = (area or settings.AREA_NAME).upper()
    return await runtime_service.reload(target_area)

