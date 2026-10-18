"""Logging setup shared by Lambda handlers and the local server."""
import logging
import sys
from pathlib import Path

_FMT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_CONFIGURED = False


def setup_logging(level: str = "INFO", log_dir: str | None = None) -> None:
    """Configure root logger once: console always, file when log_dir given."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    root = logging.getLogger()
    root.setLevel(level.upper())
    fmt = logging.Formatter(_FMT, datefmt="%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(Path(log_dir) / "pipeline.log", encoding="utf-8")
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

    # Quiet noisy third-party loggers
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
