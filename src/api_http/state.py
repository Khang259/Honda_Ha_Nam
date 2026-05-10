from typing import Any, Optional

from shared.setup_log import setup_logger

logger = setup_logger("api_state", "logs/api_state/log")

# Global state manager reference (kept for minimal refactor)
state_manager: Optional[Any] = None
camera_manager: Optional[Any] = None
inference_engine: Optional[Any] = None
end_point_empty: Optional[str] = None


def set_state_manager(manager: Any) -> None:
    """Set the state manager instance for API routes."""
    global state_manager
    state_manager = manager
    logger.info("State manager attached to API routes")


def set_camera_manager(manager: Any) -> None:
    """Set the camera manager instance for camera routes."""
    global camera_manager
    camera_manager = manager
    logger.info("Camera manager attached to API routes")


def set_inference_engine(engine: Any) -> None:
    """Set the inference engine instance for camera routes."""
    global inference_engine
    inference_engine = engine
    logger.info("Inference engine attached to API routes")

def set_end_point_empty(value: Optional[str]) -> None:
    global end_point_empty
    end_point_empty = value

def get_end_point_empty() -> Optional[str]:
    return end_point_empty
