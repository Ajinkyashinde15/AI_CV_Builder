import logging
import os

def get_logger(name: str = "resume_app") -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:  # prevent duplicate handlers on reload
        return logger

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.setLevel(level)

    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False  # don't double-log via root

    return logger

logger = get_logger()