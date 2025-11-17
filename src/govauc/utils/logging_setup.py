"""
Logging configuration for GovAUC.
"""

import logging
import os
from datetime import datetime
from pathlib import Path


def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    console: bool = True,
    file: bool = True,
) -> logging.Logger:
    """
    Set up logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for log files
        console: Enable console logging
        file: Enable file logging

    Returns:
        Root logger
    """
    # Create log directory
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))

    # Clear existing handlers
    logger.handlers = []

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, log_level.upper()))
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # File handler
    if file:
        log_file = os.path.join(
            log_dir, f"govauc_{datetime.now().strftime('%Y%m%d')}.log"
        )
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.info(f"Logging initialized: level={log_level}, console={console}, file={file}")

    return logger
