import logging
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path

_CLEANED_ONCE = False


def cleanup_old_logs(log_root: str = "logs", retention_days: int = 3) -> None:
    cutoff = datetime.now() - timedelta(days=retention_days)
    root = Path(log_root)
    if not root.exists():
        return
    for file_path in root.rglob("*.log"):
        try:
            modified = datetime.fromtimestamp(file_path.stat().st_mtime)
            if modified < cutoff:
                file_path.unlink(missing_ok=True)
        except Exception:
            # tránh crash app chỉ vì không xóa được 1 file log
            pass

def setup_logger(name, log_file, level=logging.DEBUG):
    """Setup logger with file handler."""
    global _CLEANED_ONCE
    if not _CLEANED_ONCE:
        cleanup_old_logs("logs", retention_days=3)
        _CLEANED_ONCE = True
    date_str = datetime.now().strftime("%Y%m%d")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler = logging.FileHandler(f"{log_file}_{date_str}.log")
    handler.setFormatter(formatter)
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)
    
    return logger