import logging
import os
from pathlib import Path

import colorlog
from platformdirs import user_data_dir


def get_logger(name: str = "OSA"):
    logger = logging.getLogger(name)

    if not logger.handlers:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, level, logging.INFO))

        color_formatter = colorlog.ColoredFormatter(
            fmt="[%(asctime)s] [%(log_color)s%(levelname)s%(reset)s] [PID:%(process)d] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        )

        file_formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [PID:%(process)d] %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )

        ch = colorlog.StreamHandler()
        ch.setFormatter(color_formatter)
        logger.addHandler(ch)

        log_dir = Path(user_data_dir("mcp-rss-feeds"))
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / "mcp-rss-feeds.log")
        fh.setFormatter(file_formatter)
        logger.addHandler(fh)

    return logger
