from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.detections import router as detections_router
from api.routes.delete_flag import router as delete_flag_router
from api.routes.health import router as health_router
from api.routes.state import router as state_router
from api.routes.cameras import router as cameras_router
from api.routes.runtime import router as runtime_router


def create_app() -> FastAPI:
    app = FastAPI(title="Honda AI Monitoring API", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(detections_router)
    app.include_router(state_router)
    app.include_router(delete_flag_router)
    app.include_router(cameras_router)
    app.include_router(runtime_router)

    return app

