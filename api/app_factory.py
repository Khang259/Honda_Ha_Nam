from __future__ import annotations
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.detections import router as detections_router
from api.routes.delete_flag import router as delete_flag_router
from api.routes.health import router as health_router
from api.routes.state import router as state_router
from api.routes.cameras import router as cameras_router
from api.routes.runtime import router as runtime_router
from api.routes.node_id import router as node_id_router
from api.routes.pairs import router as pairs_router
from api.core.database import close_mongo_connection, connect_to_mongo
from api.services.runtime_service import runtime_service

from api.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo(settings.MongoDB_URL, settings.MongoDB_DB)
    await runtime_service.start(settings.AREA_NAME)
    yield
    runtime_service.stop()
    await close_mongo_connection()


def create_app() -> FastAPI:
    app = FastAPI(title="Honda AI Monitoring", 
                  version="1.0.0", 
                  lifespan=lifespan,
                  description="Honda AI Monitoring API")

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
    app.include_router(cameras_router, prefix="/engine-control", tags=["engine-control"])
    app.include_router(runtime_router)
    app.include_router(node_id_router, prefix="/node-id", tags=["node-id"])
    app.include_router(pairs_router, prefix="/pairs", tags=["pairs"])

    return app

