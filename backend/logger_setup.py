import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from tool.config import get_config


_LOGGER_INITIALIZED = False


def setup_logging():
    global _LOGGER_INITIALIZED
    if _LOGGER_INITIALIZED:
        return
    cfg = get_config("./config.json")
    app_cfg = cfg.get("app", {})
    log_dir = Path(app_cfg.get("log_dir", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    level_name = app_cfg.get("log_level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)

    # File handler (rotating)
    fh = RotatingFileHandler(log_dir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(ch)
    root.addHandler(fh)
    _LOGGER_INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)

