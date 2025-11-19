import logging
import os
import sys
import time
from logging import FileHandler, StreamHandler


def setup_logging(level="INFO", log_path="."):
    os.makedirs(log_path, exist_ok=True)

    log_file_template = os.path.join(log_path, "log_{time_str}.txt")
    log_file = log_file_template.format(time_str=time.strftime("%Y-%m-%d"))

    root_logger = logging.getLogger()

    shutdown_file_handler()

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    log_format = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(threadName)s] - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)

    try:
        file_handler = FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setFormatter(log_format)
        file_handler.setLevel(level)
        root_logger.addHandler(file_handler)
    except (IOError, PermissionError) as e:
        print(
            f"Error: Could not set up log file at {log_file}. Logging to console only. Error: {e}"
        )

    root_logger.setLevel(level)
    logging.info(f"Logging initialized successfully. Level: {level}")


def shutdown_file_handler():
    root_logger = logging.getLogger()
    file_handler_to_remove = None
    for handler in root_logger.handlers:
        if isinstance(handler, FileHandler):
            file_handler_to_remove = handler
            break

    if file_handler_to_remove:
        try:
            logging.info("Shutting down logging file handler.")
            file_handler_to_remove.close()
            root_logger.removeHandler(file_handler_to_remove)
        except Exception as e:
            print(f"Error shutting down file handler: {e}")
