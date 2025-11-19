#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unified LogPane Component (View & Controller).

This module provides a reusable, high-performance log viewing widget.
It replaces the duplicated log logic from the main, node, and bridge tabs.
It includes features like log level filtering, text search, syntax highlighting,
and performance optimizations for handling large log outputs.
"""

from __future__ import annotations

import logging
import re
import tkinter as tk
from tkinter import DISABLED, END, NORMAL, WORD
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

import ttkbootstrap as ttk
from ttkbootstrap.constants import (
    BOTH,
    DANGER,
    DISABLED,
    END,
    EW,
    HORIZONTAL,
    INFO,
    LEFT,
    NORMAL,
    NSEW,
    RIGHT,
    SUCCESS,
    VERTICAL,
    WORD,
    W,
    X,
    Y,
)
from ttkbootstrap.scrolled import ScrolledText
from ttkbootstrap.toast import ToastNotification
from ttkbootstrap.tooltip import ToolTip

from src.utils.i18n import translate

if TYPE_CHECKING:
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


class LogPane(ttk.Frame):
    """
    A unified, reusable component for displaying formatted log output.

    It includes controls for filtering, searching, font size, auto-scrolling,
    and copying, along with built-in syntax highlighting for Kaspa logs.
    """

    main_window: "MainWindow"
    log_level_var: ttk.StringVar
    search_var: ttk.StringVar
    log_font_size_var: ttk.IntVar
    log_autoscroll_var: ttk.BooleanVar
    log_levels: List[str]
    log_level_tags: Set[str]
    last_search_index: str
    output_text: ScrolledText
    log_font_label: ttk.Label
    log_font_spinbox: ttk.Spinbox
    clear_log_button: ttk.Button
    copy_log_button: ttk.Button
    log_autoscroll_cb: ttk.Checkbutton
    log_level_combo: ttk.Combobox
    search_entry: ttk.Entry
    search_next_btn: ttk.Button
    search_prev_btn: ttk.Button

    def __init__(
        self,
        parent: ttk.Frame,
        main_window: "MainWindow",
        max_lines: int = 2000,
    ) -> None:
        """
        Initialize the LogPane component.

        Args:
            parent: The parent widget.
            main_window: The main application window instance.
            max_lines: The maximum number of log lines to keep in the widget.
        """
        super().__init__(parent)
        self.main_window: "MainWindow" = main_window
        self.max_lines: int = max_lines

        self.log_level_var = ttk.StringVar(value=translate("ALL"))
        self.search_var = ttk.StringVar()
        self.log_font_size_var = ttk.IntVar(value=9)
        self.log_autoscroll_var = ttk.BooleanVar(value=True)
        self.last_search_index: str = "1.0"
        self.log_levels: List[str] = [
            "ALL",
            "TRACE",
            "DEBUG",
            "INFO",
            "WARN",
            "ERROR",
            "FATAL",
        ]
        self.log_level_tags: Set[str] = {
            "trace_tag",
            "debug_tag",
            "info_tag",
            "warn_tag",
            "error_tag",
            "fatal_tag",
            "separator_tag",
            "message_tag",
            "key_tag",
            "value_tag",
            "timestamp_tag",
        }

        self._build_ui()

    def _build_ui(self) -> None:
        """Constructs the UI components for the log pane."""
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        control_frame = ttk.Frame(self)
        control_frame.grid(row=0, column=0, sticky=EW, pady=(0, 5))

        log_level_label = ttk.Label(control_frame, text=f"{translate('Severity')}:")
        log_level_label.pack(side=LEFT, padx=(5, 2))

        self.log_level_combo = ttk.Combobox(
            control_frame,
            textvariable=self.log_level_var,
            values=[translate(lvl) for lvl in self.log_levels],
            state="readonly",
            width=8,
        )
        self.log_level_combo.pack(side=LEFT, padx=(0, 10))
        self.log_level_combo.bind("<<ComboboxSelected>>", self._on_log_level_change)
        ToolTip(self.log_level_combo, text=translate("Filter log by severity"))

        self.search_entry = ttk.Entry(
            control_frame, textvariable=self.search_var, width=30
        )
        self.search_entry.pack(side=LEFT, padx=(0, 5), fill=X, expand=True)
        self.search_entry.bind("<Return>", self._search_next)
        self.search_entry.bind("<Control-f>", lambda e: self.search_entry.focus())

        self.search_prev_btn = ttk.Button(
            control_frame,
            text="▲",
            command=self._search_prev,
            bootstyle="outline",
            width=2,
        )
        self.search_prev_btn.pack(side=LEFT, padx=0)
        ToolTip(self.search_prev_btn, text=translate("Find Previous"))

        self.search_next_btn = ttk.Button(
            control_frame,
            text="▼",
            command=self._search_next,
            bootstyle="outline",
            width=2,
        )
        self.search_next_btn.pack(side=LEFT, padx=(2, 10))
        ToolTip(self.search_next_btn, text=translate("Find Next"))

        self.log_autoscroll_cb = ttk.Checkbutton(
            control_frame,
            text=translate("Auto-Scroll"),
            variable=self.log_autoscroll_var,
            bootstyle="round-toggle",
        )
        self.log_autoscroll_cb.pack(side=RIGHT, padx=5)

        self.copy_log_button = ttk.Button(
            control_frame,
            text=translate("Copy Log"),
            command=self._copy_log_to_clipboard,
            bootstyle="info-outline",
        )
        self.copy_log_button.pack(side=RIGHT, padx=(0, 5))

        self.clear_log_button = ttk.Button(
            control_frame,
            text=translate("Clear Log"),
            command=self._clear_log,
            bootstyle="info-outline",
        )
        self.clear_log_button.pack(side=RIGHT, padx=5)

        self.log_font_label = ttk.Label(
            control_frame, text=f"{translate('Font Size')}:"
        )
        self.log_font_label.pack(side=RIGHT, padx=(5, 2))

        self.log_font_spinbox = ttk.Spinbox(
            control_frame,
            from_=6,
            to=20,
            textvariable=self.log_font_size_var,
            width=3,
            command=self._on_font_size_change,
        )
        self.log_font_spinbox.pack(side=RIGHT)

        self.output_text = ScrolledText(
            self,
            wrap=WORD,
            autohide=True,
            bootstyle="dark",
            spacing1=0,
            spacing2=0,
            spacing3=0,
        )
        self.output_text.grid(row=1, column=0, sticky=NSEW)
        self.output_text.text.config(state=DISABLED)

        self._configure_syntax_highlighting()
        self._on_font_size_change()

    def _configure_syntax_highlighting(self) -> None:
        """Sets up the color tags for log levels and patterns."""
        try:
            style = self.main_window.style
            font_size = self.log_font_size_var.get()
            font_name = "Courier New"
            font_bold = (font_name, font_size, "bold")
            font_normal = (font_name, font_size)

            self.output_text.text.tag_configure(
                "trace_tag", foreground="#6610F2", font=font_normal
            )
            self.output_text.text.tag_configure(
                "debug_tag", foreground=style.colors.secondary, font=font_normal
            )
            self.output_text.text.tag_configure(
                "info_tag", foreground=style.colors.info, font=font_normal
            )
            self.output_text.text.tag_configure(
                "warn_tag", foreground=style.colors.warning, font=font_normal
            )
            self.output_text.text.tag_configure(
                "error_tag", foreground=style.colors.danger, font=font_bold
            )
            self.output_text.text.tag_configure(
                "fatal_tag", foreground=style.colors.danger, font=font_bold
            )
            self.output_text.text.tag_configure(
                "timestamp_tag", foreground="#ADB5BD", font=font_normal
            )
            self.output_text.text.tag_configure(
                "separator_tag",
                foreground=style.colors.success,
                font=font_bold,
            )
            self.output_text.text.tag_configure(
                "message_tag", foreground="#ABEBC6", font=font_normal
            )
            self.output_text.text.tag_configure(
                "key_tag", foreground="#5DADE2", font=font_normal
            )
            self.output_text.text.tag_configure(
                "value_tag", foreground="#FAD7A0", font=font_normal
            )
            self.output_text.text.tag_configure(
                "search_hit_tag", background="yellow", foreground="black"
            )
        except (tk.TclError, AttributeError):
            pass

    def _on_log_level_change(self, event: Optional[Any] = None) -> None:
        """Applies log level filtering by hiding/showing tagged lines."""
        selected_level_str_translated = self.log_level_var.get()
        selected_level_str = "ALL"
        for key in self.log_levels:
            if translate(key) == selected_level_str_translated:
                selected_level_str = key
                break

        if not hasattr(self, "output_text"):
            return

        try:
            self.output_text.text.config(state=NORMAL)

            if selected_level_str == "ALL":
                for tag in self.log_level_tags:
                    self.output_text.text.tag_configure(tag, elide=False)
            else:
                selected_level_index = self.log_levels.index(selected_level_str)
                for i, level in enumerate(self.log_levels[1:]):
                    tag = f"{level.lower()}_tag"
                    should_elide = i < selected_level_index
                    self.output_text.text.tag_configure(tag, elide=should_elide)

            self.output_text.text.tag_configure("timestamp_tag", elide=False)
            self.output_text.text.tag_configure("message_tag", elide=False)
            self.output_text.text.tag_configure("key_tag", elide=False)
            self.output_text.text.tag_configure("value_tag", elide=False)
            self.output_text.text.tag_configure("separator_tag", elide=False)

        except Exception as e:
            logger.error(f"Error applying log filter: {e}")
        finally:
            if hasattr(self, "output_text"):
                self.output_text.text.config(state=DISABLED)

    def _on_font_size_change(self, *args: Any) -> None:
        """Update the font size in the log window and all configured tags."""
        if not hasattr(self, "output_text"):
            return

        try:
            size = self.log_font_size_var.get()
            font_name = "Courier New"
            font_bold = (font_name, size, "bold")
            font_normal = (font_name, size)

            self.output_text.text.config(font=font_normal)

            self.output_text.text.tag_configure("trace_tag", font=font_normal)
            self.output_text.text.tag_configure("debug_tag", font=font_normal)
            self.output_text.text.tag_configure("info_tag", font=font_normal)
            self.output_text.text.tag_configure("warn_tag", font=font_normal)
            self.output_text.text.tag_configure("error_tag", font=font_bold)
            self.output_text.text.tag_configure("fatal_tag", font=font_bold)
            self.output_text.text.tag_configure("timestamp_tag", font=font_normal)
            self.output_text.text.tag_configure("separator_tag", font=font_bold)
            self.output_text.text.tag_configure("message_tag", font=font_normal)
            self.output_text.text.tag_configure("key_tag", font=font_normal)
            self.output_text.text.tag_configure("value_tag", font=font_normal)

        except (tk.TclError, AttributeError):
            pass

    def _clear_log(self) -> None:
        """Clears the log text widget."""
        try:
            if self.output_text.winfo_exists():
                self.output_text.text.config(state=NORMAL)
                self.output_text.text.delete("1.0", END)
                self.output_text.text.config(state=DISABLED)
                self.last_search_index = "1.0"
        except tk.TclError:
            pass

    def _copy_log_to_clipboard(self) -> None:
        """Copies the entire content of the log text widget to the clipboard."""
        try:
            content: str = self.output_text.text.get("1.0", END)
            self.main_window.clipboard_clear()
            self.main_window.clipboard_append(content)
            ToastNotification(
                title=translate("Success"),
                message=translate("Log content copied to clipboard."),
                bootstyle=SUCCESS,
                duration=3000,
            ).show_toast()
        except Exception as e:
            logger.error(f"Failed to copy log to clipboard: {e}")
            ToastNotification(
                title=translate("Error"),
                message=str(e),
                bootstyle=DANGER,
                duration=3000,
            ).show_toast()

    def _search(self, forward: bool = True) -> None:
        """Internal search function."""
        search_term = self.search_var.get()
        if not search_term:
            return

        try:
            self.output_text.text.tag_remove("search_hit_tag", "1.0", END)

            start_index = self.last_search_index
            if forward:
                start_index = f"{start_index} +1c"
                pos = self.output_text.text.search(
                    search_term, start_index, END, nocase=True
                )
            else:
                start_index = f"{start_index} -1c"
                pos = self.output_text.text.search(
                    search_term, start_index, "1.0", nocase=True, backwards=True
                )

            if pos:
                end_pos = f"{pos}+{len(search_term)}c"
                self.output_text.text.tag_add("search_hit_tag", pos, end_pos)
                self.output_text.text.see(pos)
                self.last_search_index = pos
            else:
                self.last_search_index = "1.0" if forward else END
                if forward:
                    pos = self.output_text.text.search(
                        search_term, "1.0", END, nocase=True
                    )
                else:
                    pos = self.output_text.text.search(
                        search_term, END, "1.0", nocase=True, backwards=True
                    )

                if pos:
                    end_pos = f"{pos}+{len(search_term)}c"
                    self.output_text.text.tag_add("search_hit_tag", pos, end_pos)
                    self.output_text.text.see(pos)
                    self.last_search_index = pos
                else:
                    ToastNotification(
                        title=translate("Search"),
                        message=translate("No matches found."),
                        bootstyle=INFO,
                        duration=2000,
                    ).show_toast()

        except tk.TclError:
            self.last_search_index = "1.0"
        except Exception as e:
            logger.error(f"Error during log search: {e}")
            self.last_search_index = "1.0"

    def _search_next(self, event: Optional[Any] = None) -> None:
        """Handler for searching forward."""
        self._search(forward=True)

    def _search_prev(self, event: Optional[Any] = None) -> None:
        """Handler for searching backward."""
        self._search(forward=False)

    def insert_line(self, text_line: str, log_level: str = "INFO") -> None:
        """
        Public method to insert a new line of text into the log,
        applying syntax highlighting and filtering.
        """
        try:
            if not self.output_text.winfo_exists():
                return

            self.output_text.text.config(state=NORMAL)
            start_index: str = self.output_text.text.index("end-1c linestart")

            level_lower = log_level.lower()
            line_tag = f"{level_lower}_tag"

            if line_tag not in self.log_level_tags:
                if "---" in text_line:
                    line_tag = "separator_tag"
                else:
                    line_tag = "info_tag"
                    level_lower = "info"

            selected_level_str = "ALL"
            selected_level_str_translated = self.log_level_var.get()
            for key in self.log_levels:
                if translate(key) == selected_level_str_translated:
                    selected_level_str = key
                    break

            should_elide = False
            if selected_level_str != "ALL":
                try:
                    selected_index = self.log_levels.index(selected_level_str)
                    line_index = self.log_levels.index(level_lower.upper())
                    if line_index < selected_index:
                        should_elide = True
                except ValueError:
                    if line_tag != "separator_tag":
                        if selected_index > self.log_levels.index("INFO"):
                            should_elide = True
                    pass

            self.output_text.text.insert(END, text_line, (line_tag,))
            end_index: str = self.output_text.text.index("end-1c lineend")

            if should_elide:
                self.output_text.text.tag_add(line_tag, start_index, end_index)
                self.output_text.text.tag_configure(line_tag, elide=True)
            else:
                self.output_text.text.tag_configure(line_tag, elide=False)

            line_content: str = self.output_text.text.get(
                start_index, end_index
            ).strip()

            ts_match: Optional[re.Match[str]] = re.search(
                r'time="([^"]+)"', line_content
            )
            if ts_match:
                start = f"{start_index}+{ts_match.start(1)}c"
                end = f"{start_index}+{ts_match.end(1)}c"
                self.output_text.text.tag_add("timestamp_tag", start, end)

            msg_match: Optional[re.Match[str]] = re.search(
                r'msg="([^"]*)"', line_content
            )
            if msg_match:
                start = f"{start_index}+{msg_match.start(1)}c"
                end = f"{start_index}+{msg_match.end(1)}c"
                self.output_text.text.tag_add("message_tag", start, end)

            kv_matches = re.finditer(r'(\w+)=("([^"]*)"|([^\s]+))', line_content)
            for match in kv_matches:
                key: str = match.group(1)
                if key in ["time", "msg", "level"]:
                    continue

                key_start = f"{start_index}+{match.start(1)}c"
                key_end = f"{start_index}+{match.end(1)}c"
                self.output_text.text.tag_add("key_tag", key_start, key_end)

                val_group_idx: int = 3 if match.group(3) is not None else 4
                val_start_idx: int = match.start(val_group_idx)
                val_end_idx: int = match.end(val_group_idx)

                val_start = f"{start_index}+{val_start_idx}c"
                val_end = f"{start_index}+{val_end_idx}c"
                self.output_text.text.tag_add("value_tag", val_start, val_end)

            num_lines = int(self.output_text.text.index("end-1c").split(".")[0])
            if num_lines > self.max_lines:
                self.output_text.text.delete("1.0", f"{num_lines - self.max_lines}.0")

            if self.log_autoscroll_var.get():
                self.output_text.text.see(END)

        except tk.TclError:
            pass
        except Exception as e:
            logger.error(f"Error inserting log line: {e}", exc_info=True)
        finally:
            if hasattr(self, "output_text") and self.output_text.winfo_exists():
                self.output_text.text.config(state=DISABLED)

    def re_translate(self) -> None:
        """Updates all translatable text in the widget."""
        self.log_level_var.set(translate(self.log_level_var.get()))
        self.log_level_combo["values"] = [translate(lvl) for lvl in self.log_levels]

        ToolTip(self.log_level_combo, text=translate("Filter log by severity"))
        ToolTip(self.search_prev_btn, text=translate("Find Previous"))
        ToolTip(self.search_next_btn, text=translate("Find Next"))

        self.log_autoscroll_cb.config(text=translate("Auto-Scroll"))
        self.copy_log_button.config(text=translate("Copy Log"))
        self.clear_log_button.config(text=translate("Clear Log"))
        self.log_font_label.config(text=f"{translate('Font Size')}:")
