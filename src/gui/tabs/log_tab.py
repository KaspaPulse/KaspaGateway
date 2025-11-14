#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Contains the GUI tab (View) for displaying the application's log file in real-time.
This file handles the log tailing thread and the text widget display.
"""

from __future__ import annotations
import logging
import os
import time
import threading
import tkinter as tk
from typing import Optional, Any, TYPE_CHECKING, IO

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledText
from ttkbootstrap.toast import ToastNotification

from src.utils.i18n import translate

if TYPE_CHECKING:
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


class TextFile(threading.Thread):
    """
    A background thread that continuously reads new lines from a text file
    and queues them to be updated in a tkinter Text widget.
    """

    # --- Type Hint Declarations ---
    parent: "LogTab"
    file_path: str
    text_widget: tk.Text
    stop_event: threading.Event
    file: Optional[IO[str]]
    # --- End Type Hint Declarations ---

    def __init__(self, parent: "LogTab", file_path: str, text_widget: tk.Text) -> None:
        """
        Initializes the log tailing thread.

        Args:
            parent: The LogTab widget that owns this thread.
            file_path: The absolute path to the log file to monitor.
            text_widget: The tkinter Text widget to insert new lines into.
        """
        super().__init__(daemon=True, name="LogTailingThread")
        self.parent: "LogTab" = parent
        self.file_path: str = file_path
        self.text_widget: tk.Text = text_widget
        self.stop_event: threading.Event = threading.Event()
        self.file: Optional[IO[str]] = None

    def run(self) -> None:
        """
        Continuously monitors the log file for new lines.

        When a new line is found, it schedules `update_text` to be called
        on the main GUI thread. Checks for parent window existence and
        stop event to ensure graceful shutdown.
        """
        try:
            self.file = open(self.file_path, "r", encoding="utf-8")
            self.file.seek(0, 2)  # Go to the end of the file
            while not self.stop_event.is_set():
                line: str = self.file.readline()
                if not line:
                    time.sleep(0.1)
                    continue

                try:
                    # Check if parent (LogTab) still exists before calling 'after'
                    if not self.parent.winfo_exists():
                        break
                    
                    # Schedule the GUI update on the main thread
                    self.parent.after(0, self.update_text, line)
                except (tk.TclError, RuntimeError):
                    # This can happen if the application is shutting down
                    break
        except Exception as e:
            # Avoid logging harmless errors that occur during shutdown
            error_msg: str = str(e)
            if "Bad file descriptor" not in error_msg and \
               "application has been destroyed" not in error_msg:
                logger.error(f"Error reading log file: {e}")
        finally:
            if self.file:
                self.file.close()

    def update_text(self, line: str) -> None:
        """
        Thread-safe method to insert a new line into the Text widget.
        This method is executed by the main GUI thread via `self.parent.after()`.
        """
        try:
            if self.text_widget.winfo_exists():
                self.text_widget.configure(state=NORMAL)
                self.text_widget.insert(END, line)
                self.text_widget.see(END)
                self.text_widget.configure(state=DISABLED)
        except (tk.TclError, RuntimeError):
            # This can happen if the widget is destroyed during app shutdown
            pass

    def stop(self) -> None:
        """Signals the thread to stop monitoring the log file."""
        self.stop_event.set()


class LogTab(ttk.Frame):
    """
    The main ttk.Frame (View) that contains the log display
    and its associated controls.
    """

    # --- Type Hint Declarations ---
    font_size_var: ttk.IntVar
    log_text: ScrolledText
    text_file: Optional[TextFile]
    log_file_path: Optional[str]
    copy_button: ttk.Button
    font_label: ttk.Label
    font_size_spinbox: ttk.Spinbox
    # --- End Type Hint Declarations ---

    def __init__(self, parent: ttk.Frame) -> None:
        """
        Initializes the LogTab view.

        Args:
            parent: The parent ttk.Frame (usually the main notebook).
        """
        super().__init__(parent)
        self.pack(fill=BOTH, expand=True)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.font_size_var: ttk.IntVar = ttk.IntVar(value=9)
        self.log_text: ScrolledText = ScrolledText(
            self,
            wrap=WORD,
            state=DISABLED,
            font=("Courier New", self.font_size_var.get())
        )
        self.text_file: Optional[TextFile] = None
        self.log_file_path: Optional[str] = None

        self._build_controls()
        self._build_log_display()

        # Start checking for the log file to be created
        self.after(500, self._check_and_attach)

    def _build_controls(self) -> None:
        """Creates the control buttons and font size adjuster."""
        control_frame = ttk.Frame(self)
        control_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        self.copy_button = ttk.Button(
            control_frame,
            text=translate("Copy"),
            command=self._copy_to_clipboard,
            state=DISABLED
        )
        self.copy_button.pack(side=LEFT, padx=5)

        font_frame = ttk.Frame(control_frame)
        font_frame.pack(side=LEFT, padx=10)

        self.font_label = ttk.Label(font_frame, text=f"{translate('Font Size')}:")
        self.font_label.pack(side=LEFT, padx=(0, 5))

        self.font_size_spinbox = ttk.Spinbox(
            font_frame,
            from_=6,
            to=30,
            textvariable=self.font_size_var,
            width=3,
            command=self._update_font,
            state=DISABLED
        )
        self.font_size_spinbox.pack(side=LEFT)

    def _build_log_display(self) -> None:
        """Creates the main ScrolledText widget for log output."""
        self.log_text.grid(row=1, column=0, sticky="nsew")
        # Prevent Control+MouseWheel from changing font size, use spinbox instead
        self.log_text.text.bind("<Control-MouseWheel>", lambda event: "break")

    def _copy_to_clipboard(self) -> None:
        """Copies the entire content of the log text widget to the clipboard."""
        try:
            content: str = self.log_text.text.get("1.0", END)
            self.clipboard_clear()
            self.clipboard_append(content)
            ToastNotification(
                title=translate("Success"),
                message=translate("Log content copied to clipboard."),
                bootstyle=SUCCESS,
                duration=3000
            ).show_toast()
        except Exception as e:
            logger.error(f"Failed to copy log to clipboard: {e}")
            ToastNotification(
                title=translate("Error"),
                message=str(e),
                bootstyle=DANGER,
                duration=3000
            ).show_toast()

    def _update_font(self, *args: Any) -> None:
        """Applies the selected font size to the log text widget."""
        size: int = self.font_size_var.get()
        self.log_text.text.config(font=("Courier New", size))

    def _check_and_attach(self) -> None:
        """
        Checks if the logging FileHandler has been created and, if so,
        attaches the TextFile thread to monitor it.
        """
        try:
            log_dir_handlers: List[str] = [
                h.baseFilename for h in logging.getLogger().handlers
                if isinstance(h, logging.FileHandler)
            ]
            if log_dir_handlers:
                self.log_file_path = log_dir_handlers[0]
                if os.path.exists(self.log_file_path):
                    self.attach_log_file(self.log_file_path)
                else:
                    # Log file path is known but file not created yet, retry
                    self.after(1000, self._check_and_attach)
            else:
                # FileHandler not even configured yet, retry
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
        self.text_file = TextFile(self, file_path, self.log_text.text)
        self.text_file.start()
        self.set_controls_state(True)

    def set_controls_state(self, is_active: bool) -> None:
        """Enables or disables the UI controls for this tab."""
        state: str = NORMAL if is_active else DISABLED
        try:
            self.copy_button.config(state=state)
            self.font_size_spinbox.config(state=state)
        except tk.TclError:
            pass  # Widget might be destroyed on close

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
            if self.log_text.winfo_exists():
                self.log_text.text.configure(state=NORMAL)
                self.log_text.text.delete('1.0', END)
                self.log_text.text.configure(state=DISABLED)
        except (tk.TclError, RuntimeError):
            pass  # App closing
        self.after(100, self._check_and_attach)

    def stop(self) -> None:
        """Stops the log tailing thread."""
        if self.text_file and self.text_file.is_alive():
            self.text_file.stop()
            self.text_file = None

    def re_translate(self) -> None:
        """Re-translates the text on the UI widgets for this tab."""
        self.copy_button.config(text=translate("Copy"))
        self.font_label.config(text=f"{translate('Font Size')}:")