#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reusable Status Bar component.
Displays status messages and quick links (Donations, Twitter, GitHub).
"""

from __future__ import annotations

import logging
import webbrowser
import tkinter as tk
from typing import Any, Optional

import ttkbootstrap as ttk
from ttkbootstrap.constants import LEFT, RIGHT, X

from src.config.config import CONFIG
from src.utils.i18n import translate

logger = logging.getLogger(__name__)


class Status(ttk.Frame):
    """
    A status bar widget that displays messages on the left
    and support links on the right.
    """

    def __init__(self, parent: tk.Widget) -> None:
        """
        Initializes the Status bar.

        Args:
            parent: The parent widget.
        """
        super().__init__(parent)
        self.grid_columnconfigure(0, weight=1)

        # Status Label (Left)
        self.label = ttk.Label(
            self, text=translate("Ready"), anchor="w", font="-size 9"
        )
        self.label.pack(side=LEFT, fill=X, expand=True, padx=(5, 0))

        # Links Frame (Right)
        self.links_frame = ttk.Frame(self)
        self.links_frame.pack(side=RIGHT, padx=5)

        self.donations_link: Optional[ttk.Label] = None
        self.twitter_link: Optional[ttk.Label] = None
        self.github_link: Optional[ttk.Label] = None

        self._build_links()

    def _build_links(self) -> None:
        """Constructs the support links on the right side."""
        self.donations_link = self._create_link("Donations", CONFIG["links"]["donation"])
        self._create_separator()
        self.twitter_link = self._create_link("Twitter", CONFIG["links"]["twitter"])
        self._create_separator()
        self.github_link = self._create_link("GitHub", CONFIG["links"]["github"])

    def _create_link(self, text_key: str, url: str) -> ttk.Label:
        """
        Helper to create a clickable link label.

        Args:
            text_key: The translation key for the link text.
            url: The URL to open when clicked.
        """
        link = ttk.Label(
            self.links_frame,
            text=translate(text_key),
            font="-size 8",
            bootstyle="info",
            cursor="hand2",
        )
        link.pack(side=LEFT)
        link.bind("<Button-1>", lambda e: webbrowser.open(url, new=2))
        
        # Add hover effect (underline)
        link.bind("<Enter>", lambda e: link.config(font="-size 8 -underline 1"))
        link.bind("<Leave>", lambda e: link.config(font="-size 8"))
        
        return link

    def _create_separator(self) -> None:
        """Adds a visual separator between links."""
        ttk.Label(
            self.links_frame, text="|", font="-size 8", foreground="gray"
        ).pack(side=LEFT, padx=5)

    def update_status(self, message_key: str, *args: Any) -> None:
        """
        Updates the status text on the left.

        Args:
            message_key: The translation key or raw string.
            *args: Arguments for string formatting.
        """
        try:
            log_message = message_key.format(*args) if args else message_key
            logger.info(f"Status updated: {log_message}")

            if self.winfo_exists():
                formatted_message = translate(message_key).format(*args)
                self.label.configure(text=formatted_message)
        except Exception as e:
            logger.error(
                f"Could not update status message for key '{message_key}': {e}",
                exc_info=True,
            )

    def re_translate(self) -> None:
        """Updates translations for the status links."""
        if self.donations_link:
            self.donations_link.config(text=translate("Donations"))
        
        # Twitter and GitHub usually remain in English, but we ensure they exist
        if self.twitter_link:
            self.twitter_link.config(text="Twitter")
        if self.github_link:
            self.github_link.config(text="GitHub")

        # Optionally translate current status if it matches a simple key
        # However, status messages are dynamic, so we usually leave the current text
        # until the next update_status call.