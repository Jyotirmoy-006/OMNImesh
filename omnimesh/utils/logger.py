"""
Structured logging module with automatic fallback to standard library logging
if loguru is not installed.
"""

import sys

try:
    from loguru import logger as _loguru_logger
    logger = _loguru_logger
except ImportError:
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("omnimesh")

def setup_logger(log_level: str = "INFO"):
    if hasattr(logger, "remove"):
        logger.remove()
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level=log_level,
        )
    else:
        logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
