import logging
from app.utils.timeutil import utcnow
import logging.handlers
import sys
from datetime import datetime
from typing import Optional

from app.config import config

_fmt = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def setup_logging(level: Optional[str] = None) -> None:
    """Configure the root logger: rotating file under data/logs + console handler."""
    level = level or config.LOG_LEVEL
    root = logging.getLogger()
    root.setLevel(level.upper())

    if root.handlers:
        return

    log_dir = config.LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "aegisvision.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(_fmt)
    file_handler.setLevel(level.upper())
    root.addHandler(file_handler)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_fmt)
    console.setLevel(level.upper())
    root.addHandler(console)


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger (root logger already configured on startup)."""
    return logging.getLogger(name)


def log_context() -> dict:
    """Standard structured fields for charting/analytics logging queues."""
    return {"ts": utcnow().isoformat()}