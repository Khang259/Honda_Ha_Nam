"""
FastAPI application entry for AI runtime API.

DRY note: routes live in `api_http/routes/*`; app creation is in
`api_http/app_factory.py`. Setters giữ tương thích cho code gọi trực tiếp module này.
"""

from __future__ import annotations

import api_http.state as api_state
from api_http.app_factory import create_app


app = create_app()


def set_state_manager(manager) -> None:
    api_state.set_state_manager(manager)


def set_camera_manager(manager) -> None:
    api_state.set_camera_manager(manager)


def set_inference_engine(engine) -> None:
    api_state.set_inference_engine(engine)

