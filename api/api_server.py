"""
FastAPI application entry for AI runtime API.

DRY note: all routes live in `api/routes/*`; app creation is centralized in
`api/app_factory.py`. This module keeps backward-compatible setters used by
`api/main_api.py`.
"""

from __future__ import annotations

import api.state as api_state
from api.app_factory import create_app


app = create_app()


def set_state_manager(manager) -> None:
    api_state.set_state_manager(manager)


def set_camera_manager(manager) -> None:
    api_state.set_camera_manager(manager)


def set_inference_engine(engine) -> None:
    api_state.set_inference_engine(engine)

