#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export component module.
Provides a reusable UI widget for exporting data to CSV, HTML, and PDF formats.
"""

from __future__ import annotations

from typing import Any, Callable

import ttkbootstrap as ttk
from ttkbootstrap.constants import DISABLED, LEFT, NORMAL

from src.utils.i18n import translate


class ExportComponent(ttk.Frame):
    """
    A reusable UI component containing buttons to export data
    to CSV, HTML, and PDF formats.
    """

    def __init__(
        self,
        parent: Any,
        export_callback: Callable[[str], None]
    ) -> None:
        """
        Initialize the ExportComponent.

        Args:
            parent: The parent widget.
            export_callback: Function to call with the format string ('csv', 'html', 'pdf').
        """
        super().__init__(parent, padding=(5, 5))
        self.export_callback = export_callback

        # Configure grid layout
        self.grid_columnconfigure(4, weight=1)

        # Label
        self.label = ttk.Label(self, text=translate("Export Results:"))
        self.label.pack(side=LEFT, padx=(0, 10))

        # CSV Export Button
        self.csv_button = ttk.Button(
            self,
            text=translate("Save as CSV"),
            command=lambda: self.export_callback("csv"),
            bootstyle="info",
        )
        self.csv_button.pack(side=LEFT, padx=5)

        # HTML Export Button
        self.html_button = ttk.Button(
            self,
            text=translate("Save as HTML"),
            command=lambda: self.export_callback("html"),
            bootstyle="info",
        )
        self.html_button.pack(side=LEFT, padx=5)

        # PDF Export Button
        self.pdf_button = ttk.Button(
            self,
            text=translate("Save as PDF"),
            command=lambda: self.export_callback("pdf"),
            bootstyle="info",
        )
        self.pdf_button.pack(side=LEFT, padx=5)

        # Initialize in disabled state
        self.set_ui_state(False)

    def set_ui_state(self, is_active: bool) -> None:
        """
        Enables or disables the export buttons.

        Args:
            is_active: True to enable buttons (NORMAL), False to disable (DISABLED).
        """
        state = NORMAL if is_active else DISABLED
        self.csv_button.configure(state=state)
        self.html_button.configure(state=state)
        self.pdf_button.configure(state=state)

    def re_translate(self) -> None:
        """Updates all translatable text in the component."""
        self.label.config(text=translate("Export Results:"))
        self.csv_button.config(text=translate("Save as CSV"))
        self.html_button.config(text=translate("Save as HTML"))
        self.pdf_button.config(text=translate("Save as PDF"))