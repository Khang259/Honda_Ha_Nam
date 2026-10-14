from __future__ import annotations

from fastapi import APIRouter

from pairing_orchestrator.runtime_service import runtime_service


router = APIRouter()


@router.get("/status")
async def get_runtime_status():
    return runtime_service.status()


@router.post("/reload")
async def reload_runtime():
    """Restart runtime (stop + start). Không phụ thuộc AREA_NAME."""
    return await runtime_service.reload()
