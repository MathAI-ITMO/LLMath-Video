from __future__ import annotations

import logging
import logging.config
import os
from typing import Optional, Dict, Any


def build_logging_config(logs_dir: str, level: str = "INFO") -> Dict[str, Any]:
    os.makedirs(logs_dir, exist_ok=True)
    app_log_path = os.path.join(logs_dir, "app.log")
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s %(levelname)s %(name)s %(filename)s:%(lineno)d %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": level,
                "formatter": "standard",
                "stream": "ext://sys.stdout",
            },
            "rotating_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": level,
                "formatter": "standard",
                "filename": app_log_path,
                "maxBytes": 5 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "llmath_video": {
                "level": level,
                "handlers": ["console", "rotating_file"],
                "propagate": False,
            },
            # Flask related loggers
            "werkzeug": {
                "level": "WARNING",
                "handlers": ["console", "rotating_file"],
                "propagate": False,
            },
        },
        "root": {
            "level": "WARNING",
            "handlers": ["console"],
        },
    }


def setup_logging(logs_dir: str, level: str = "INFO") -> None:
    cfg = build_logging_config(logs_dir, level)
    logging.config.dictConfig(cfg)


