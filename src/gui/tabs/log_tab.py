#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Contains the GUI tab (View) for displaying the application's log file in real-time.
This file handles the log tailing thread and the text widget display.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import tkinter as tk
from typing import IO, TYPE_CHECKING, Any, List, Optional

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from src.gui.components.log_viewer import LogPane
from src.utils.i18n import translate

if TYPE_CHECKING:
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


class TextFile(threading.Thread):
    """
    A background thread that continuously reads new lines from a text file
    and queues them to be updated in the LogPane component.
    """

    parent: "LogTab"
    file_path: str
    log_pane: LogPane
    stop_event: threading.Event
    file: Optional[IO[str]]

    def __init__(self, parent: "LogTab", file_path: str) -> None:
        """
        Initializes the log tailing thread.

        Args:
            parent: The LogTab widget that owns this thread.
            file_path: The absolute path to the log file to monitor.
        """
        super().__init__(daemon=True, name="LogTailingThread")
        self.parent: "LogTab" = parent
        self.file_path: str = file_path
        self.log_pane: LogPane = parent.log_pane_component
        self.stop_event: threading.Event = threading.Event()
        self.file: Optional[IO[str]] = None

    def run(self) -> None:
        """
        Continuously monitors the log file for new lines.

        When a new line is found, it schedules insert_line to be called
        on the main GUI thread. Checks for parent window existence and
        stop event to ensure graceful shutdown.
        """
        try:
            self.file = open(self.file_path, "r", encoding="utf-8")
            self.file.seek(0, 2)
            while not self.stop_event.is_set():
                line: str = self.file.readline()
                if not line:
                    time.sleep(0.1)
                    continue

                if not line.strip():
                    continue

                try:
                    if not self.log_pane.winfo_exists():
                        break

                    log_level = "INFO"
                    if " - TRACE " in line:
                        log_level = "TRACE"
                    elif " - DEBUG " in line:
                        log_level = "DEBUG"
                    elif " - WARNING " in line:
                        log_level = "WARN"
                    elif " - ERROR " in line:
                        log_level = "ERROR"
                    elif " - CRITICAL " in line:
                        log_level = "FATAL"

                    self.log_pane.main_window.after(
                        0, self.update_text, line, log_level
                    )
                except (tk.TclError, RuntimeError):
                    break
        except Exception as e:
            error_msg: str = str(e)
            if (
                "Bad file descriptor" not in error_msg
                and "application has been destroyed" not in error_msg
            ):
                logger.error(f"Error reading log file: {e}")
        finally:
            if self.file:
                try:
                    self.file.close()
                except OSError:
                    # Ignore errors during file closing, specifically "Bad file descriptor"
                    pass

    def update_text(self, line: str, log_level: str) -> None:
        """
        Thread-safe method to insert a new line into the LogPane.
        This method is executed by the main GUI thread via self.parent.after().
        """
        try:
            if self.log_pane.winfo_exists():
                self.log_pane.insert_line(line, log_level)
        except (tk.TclError, RuntimeError):
            pass

    def stop(self) -> None:
        """Signals the thread to stop monitoring the log file."""
        self.stop_event.set()


class LogTab(ttk.Frame):
    """
    The main ttk.Frame (View) that contains the unified LogPane
    and its associated controls.
    """

    log_pane_component: LogPane
    text_file: Optional[TextFile]
    log_file_path: Optional[str]

    def __init__(self, parent: ttk.Frame) -> None:
        """
        Initializes the LogTab view.

        Args:
            parent: The parent ttk.Frame (usually the main notebook).
        """
        super().__init__(parent)
        self.pack(fill=BOTH, expand=True)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.text_file: Optional[TextFile] = None
        self.log_file_path: Optional[str] = None

        main_window: MainWindow = self.winfo_toplevel()
        self.log_pane_component = LogPane(self, main_window)
        self.log_pane_component.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.after(500, self._check_and_attach)

    def _check_and_attach(self) -> None:
        """
        Checks if the logging FileHandler has been created and, if so,
        attaches the TextFile thread to monitor it.
        """
        try:
            log_dir_handlers: List[str] = [
                h.baseFilename
                for h in logging.getLogger().handlers
                if isinstance(h, logging.FileHandler)
            ]
            if log_dir_handlers:
                self.log_file_path = log_dir_handlers[0]
                if os.path.exists(self.log_file_path):
                    self.attach_log_file(self.log_file_path)
                else:
                    self.after(1000, self._check_and_attach)
            else:
                self.after(1000, self._check_and_attach)
        except Exception as e:
            logger.error(f"Failed to find and attach log file: {e}")
            self.after(2000, self._check_and_attach)

    def attach_log_file(self, file_path: str) -> None:
        """
        Stops any existing log reader thread and starts a new one
        for the specified file path.
        """
        if self.text_file and self.text_file.is_alive():
            self.text_file.stop()

        logger.info(f"Log tab has attached to log file: {file_path}")
        self.text_file = TextFile(self, file_path)
        self.text_file.start()

    def set_controls_state(self, is_active: bool) -> None:
        """
        This tab's controls are self-managed by the LogPane.
        This method is kept for compatibility with the main window's loop.
        """
        pass

    def reattach_log_file(self) -> None:
        """
        Public method to force a stop, clear, and re-attachment to the
        log file, typically used after log files are cleared.
        """
        logger.info("Re-attaching to log file as requested.")
        self.stop()
        self.log_file_path = None
        self.text_file = None

        try:
            if self.log_pane_component.winfo_exists():
                self.log_pane_component._clear_log()
        except (tk.TclError, RuntimeError):
            pass
        self.after(100, self._check_and_attach)

    def stop(self) -> None:
        """Stops the log tailing thread."""
        if self.text_file and self.text_file.is_alive():
            self.text_file.stop()
            self.text_file = None

    def re_translate(self) -> None:
        """Re-translates all widgets in this tab."""
        if hasattr(self, "log_pane_component"):
            self.log_pane_component.re_translate()
