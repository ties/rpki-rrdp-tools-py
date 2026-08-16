"""Shared logging setup for the command line entrypoints."""

import logging
import sys
import time
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def configure_logging(
    verbose: int = 0,
    log_file: Path | None = None,
    log_level: str | None = None,
) -> None:
    """Configure console logging and an optional file."""
    # info to stdout, more detailed levels to stderr.
    stdout = logging.StreamHandler(sys.stdout)
    stdout.addFilter(lambda record: record.levelno == logging.INFO)
    stderr = logging.StreamHandler()
    stderr.addFilter(lambda record: record.levelno != logging.INFO)
    handlers: list[logging.Handler] = [stdout, stderr]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, mode="a", encoding="utf-8"))

    formatter = logging.Formatter(LOG_FORMAT)
    formatter.converter = time.gmtime
    for handler in handlers:
        handler.setFormatter(formatter)

    root_level = logging.DEBUG if verbose >= 2 else logging.WARNING
    tools_level = logging.DEBUG if verbose >= 1 else logging.INFO
    if log_level is not None:
        levels = logging.getLevelNamesMapping()
        if log_level.upper() not in levels:
            raise ValueError(f"Unknown log level: {log_level}")
        root_level = tools_level = levels[log_level.upper()]

    logging.basicConfig(level=root_level, handlers=handlers, force=True)
    logging.getLogger("rrdp_tools").setLevel(tools_level)
