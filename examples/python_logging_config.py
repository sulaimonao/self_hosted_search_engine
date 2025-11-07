# Example: Python dictConfig for structured JSON logging
# Usage: import logging.config; logging.config.dictConfig(LOGGING_CONFIG)
import logging
import logging.config
import os
from pythonjsonlogger import jsonlogger  # pip install python-json-logger

LOG_DIR = os.environ.get("LOG_DIR", "./logs")
SERVICE = os.environ.get("SERVICE", "webapp")
ENV = os.environ.get("ENV", "development")
LOG_PATH = f"{LOG_DIR}/{SERVICE}/{ENV}/latest.log"

# Ensure log directory exists
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s %(service)s %(env)s %(correlation_id)s"
        }
    },
    "handlers": {
        "file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "formatter": "json",
            "filename": LOG_PATH,
            "when": "midnight",
            "backupCount": 30,
            "encoding": "utf-8",
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        }
    },
    "loggers": {
        "": {
            "handlers": ["console", "file"],
            "level": os.environ.get("LOG_LEVEL", "INFO"),
        }
    }
}

_configured = False

def get_logger(name=None):
    global _configured
    if not _configured:
        logging.config.dictConfig(LOGGING_CONFIG)
        _configured = True
    return logging.getLogger(name)
