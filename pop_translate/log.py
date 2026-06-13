import logging
import os
import sys

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging():
    root = logging.getLogger("pop_translate")
    if root.handlers:
        return
    level_name = os.environ.get("POP_TRANSLATE_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)


def get_logger(name):
    setup_logging()
    if name.startswith("pop_translate"):
        return logging.getLogger(name)
    return logging.getLogger(f"pop_translate.{name}")


setup_logging()
