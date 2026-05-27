"""
Loguru logging setup — import this module for side effects only.

Dev  (LOG_LEVEL=DEBUG): colored human-readable output to stdout.
Prod (LOG_LEVEL=INFO+):  JSON-serialized output for Docker log drivers.
"""

import logging
import os
import sys

from loguru import logger

_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logger.remove()

if _LOG_LEVEL == "DEBUG":
    logger.add(
        sys.stdout,
        level="DEBUG",
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> <level>{level:<8}</level> {message}",
    )
else:
    logger.add(sys.stdout, level=_LOG_LEVEL, serialize=True)


class _InterceptHandler(logging.Handler):
    """Route stdlib logging calls through loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

# Silence noisy third-party debug loggers — these flood output at DEBUG level
_QUIET_LOGGERS = [
    "httpcore", "httpx", "urllib3", "filelock",
    "colormath", "transformers.modeling_utils",
    "huggingface_hub", "huggingface_hub.file_download",
]
for _name in _QUIET_LOGGERS:
    logging.getLogger(_name).setLevel(logging.WARNING)
