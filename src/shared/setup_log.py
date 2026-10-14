import logging
import os
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_CLEANED_ONCE = False


def cleanup_old_logs(log_root: str = "logs", retention_days: int = 3) -> None:
    cutoff = datetime.now() - timedelta(days=retention_days)
    root = Path(log_root)
    if not root.exists():
        return
    for file_path in root.rglob("*.log*"):
        try:
            modified = datetime.fromtimestamp(file_path.stat().st_mtime)
            if modified < cutoff:
                file_path.unlink(missing_ok=True)
        except Exception:
            pass


def _resolve_worker_id() -> str:
    """Ưu tiên env WORKER_ID (tránh circular import settings lúc module load)."""
    wid = (os.getenv("WORKER_ID") or "").strip()
    if wid:
        return wid
    try:
        from api.settings import settings

        return str(getattr(settings, "WORKER_ID", None) or "unknown")
    except Exception:
        return "unknown"


def _with_worker_log_path(log_file: str, worker_id: str) -> Path:
    """
    logs/camera_manager/log → logs/{worker_id}/camera_manager/log
    """
    path = Path(log_file)
    parts = path.parts
    if parts and parts[0] == "logs":
        rest = parts[1:] if len(parts) > 1 else ("app",)
        return Path("logs") / worker_id / Path(*rest)
    return path.parent / worker_id / path.name


def setup_logger(name, log_file, level=logging.INFO):
    """
    Logger theo worker + xoay file theo ngày (TimedRotatingFileHandler).
    Default level=INFO (tránh DEBUG quá nặng trên 4 worker).
    """
    global _CLEANED_ONCE
    if not _CLEANED_ONCE:
        cleanup_old_logs("logs", retention_days=3)
        _CLEANED_ONCE = True

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    worker_id = _resolve_worker_id()
    base_path = _with_worker_log_path(str(log_file), worker_id)
    base_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = str(base_path) + ".log"

    formatter = logging.Formatter(
        f"%(asctime)s - [{worker_id}] - %(levelname)s - %(message)s"
    )
    handler = TimedRotatingFileHandler(
        log_path,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    handler.suffix = "%Y%m%d"

    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False

    return logger
