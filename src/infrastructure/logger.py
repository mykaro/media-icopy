"""Structured logging configuration."""

import logging
import os
from pathlib import Path


def setup_logging(log_path: str, log_level: str = "INFO") -> None:
    """
    Sets up two logging streams:
    1. Human-friendly log file (logs/events.log)
    2. Console output (for progress tracking)
    """
    log_dir = os.path.dirname(log_path)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Root logger setup
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Clear existing handlers if any
    if logger.hasHandlers():
        logger.handlers.clear()

    # File Handler - Structured with | separator
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console Handler - Simple output
    console_formatter = logging.Formatter("%(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    logging.info(f"Logging initialized. Level: {log_level} | Path: {log_path}")
