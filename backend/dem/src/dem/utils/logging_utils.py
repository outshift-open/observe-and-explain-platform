#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import logging
import os


class ColoredFormatter(logging.Formatter):
    """
    A custom logging formatter that adds color to log messages based on their level.
    Metadata (asctime, name) is greyed out, and the level name is colored.
    """

    # ANSI escape codes for colors
    GREY = "\033[90m"  # Bright Black
    BLUE = "\033[34m"  # Debug
    GREEN = "\033[32m"  # Info
    YELLOW = "\033[33m"  # Warning
    RED = "\033[31m"  # Error
    BOLD_RED = "\033[31;1m"  # Critical
    RESET = "\033[0m"  # Reset to default color and style

    # Define the format string for each log level
    FORMATS = {
        logging.DEBUG: GREY
        + "%(asctime)s - %(name)s - "
        + BLUE
        + "%(levelname)s"
        + GREY
        + " - "
        + RESET
        + "%(message)s",
        logging.INFO: GREY
        + "%(asctime)s - %(name)s - "
        + GREEN
        + "%(levelname)s"
        + GREY
        + " - "
        + RESET
        + "%(message)s",
        logging.WARNING: GREY
        + "%(asctime)s - %(name)s - "
        + YELLOW
        + "%(levelname)s"
        + GREY
        + " - "
        + RESET
        + "%(message)s",
        logging.ERROR: GREY
        + "%(asctime)s - %(name)s - "
        + RED
        + "%(levelname)s"
        + GREY
        + " - "
        + RESET
        + "%(message)s",
        logging.CRITICAL: GREY
        + "%(asctime)s - %(name)s - "
        + BOLD_RED
        + "%(levelname)s"
        + GREY
        + " - "
        + RESET
        + "%(message)s",
    }

    def format(self, record):
        """
        Formats the log record, applying specific colors based on the log level.
        This method is primarily used to prepare the record for formatMessage.
        """
        log_fmt_for_level = self.FORMATS.get(record.levelno)
        record._colored_format_string = log_fmt_for_level
        formatted_message = super().format(record)
        delattr(record, "_colored_format_string")
        return formatted_message

    def formatMessage(self, record):
        """
        Applies the format string to the record's attributes.
        This method is overridden to use the level-specific colored format string.
        """
        format_string_to_use = getattr(record, "_colored_format_string", self._fmt)
        record.message = record.getMessage()
        return format_string_to_use % record.__dict__


def setup_logger(
    name: str,
    formatter_str: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
) -> logging.Logger:
    """
    Set up a logger with the specified name, level, and formatter.

    Parameters
    ----------
    name : str
        Name of the logger.
    formatter_str : str, optional
        Formatter string (default is
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ).

    Returns
    -------
    logger : logging.Logger
        Configured logger.
    """
    levels = {
        "DEBUG": logging.DEBUG,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = levels.get(level_str, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler()
    formatter = ColoredFormatter(formatter_str)
    console_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    logger.propagate = True

    return logger
