#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reusable GUI components for the KaspaGateway application.
Includes the Header (Title, Version, Stats).
"""

from __future__ import annotations

import logging
import webbrowser
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Dict, Optional, Tuple

import ttkbootstrap as ttk
from ttkbootstrap.constants import (
    DISABLED,
    LEFT,
    NORMAL,
    RIGHT,
    TOP,
    X,
    Y,
)
from ttkbootstrap.tooltip import ToolTip

from src.config.config import CONFIG
from src.utils.i18n import get_available_languages, translate

if TYPE_CHECKING:
    from src.gui.config_manager import ConfigManager
    from src.gui.main_window import MainWindow
    from src.gui.theme_manager import ThemeManager

logger = logging.getLogger(__name__)


class Header(ttk.Frame):
    """
    The application header containing the title, version, stats (Price/Hashrate),
    clock, theme toggle, language selector, and currency selector.
    """

    def __init__(
        self,
        parent: MainWindow,
        price_var: ttk.StringVar,
        hashrate_var: ttk.StringVar,
        difficulty_var: ttk.StringVar,
        clock_date_var: ttk.StringVar,
        clock_time_var: ttk.StringVar,
        theme_manager: ThemeManager,
        currency_callback: Callable[[str], None],
        currency_var: ttk.StringVar,
        lang_callback: Callable[[str], None],
        config_manager: ConfigManager,
    ) -> None:
        """Initializes the Header component."""
        super().__init__(parent, padding=(10, 5))
        self.main_window = parent
        self.theme_manager = theme_manager
        self.config_manager = config_manager
        self.lang_callback = lang_callback
        self.currency_var = currency_var

        # UI Component References
        self.title_label: Optional[ttk.Label] = None
        self.version_label: Optional[ttk.Label] = None

        # Stats
        self.price_label: Optional[ttk.Label] = None
        self.hashrate_label: Optional[ttk.Label] = None
        self.difficulty_label: Optional[ttk.Label] = None
        self.price_tooltip: Optional[ToolTip] = None
        self.hashrate_tooltip: Optional[ToolTip] = None
        self.difficulty_tooltip: Optional[ToolTip] = None

        # Controls
        self.lang_combo: Optional[ttk.Combobox] = None
        self.theme_combo: Optional[ttk.Combobox] = None
        self.currency_combo: Optional[ttk.Combobox] = None

        # Frames
        self.price_frame: Optional[ttk.Frame] = None
        self.hashrate_frame: Optional[ttk.Frame] = None
        self.difficulty_frame: Optional[ttk.Frame] = None
        self.lang_frame: Optional[ttk.Frame] = None
        self.lang_label: Optional[ttk.Label] = None
        self.theme_label: Optional[ttk.Label] = None
        self.currency_label: Optional[ttk.Label] = None

        # Data Maps
        self.lang_display_map: Dict[str, str] = {}
        self.lang_code_map: Dict[str, str] = {}

        self._build_ui(
            price_var,
            hashrate_var,
            difficulty_var,
            clock_date_var,
            clock_time_var,
            currency_callback,
        )

    def _build_ui(
        self,
        price_var: ttk.StringVar,
        hashrate_var: ttk.StringVar,
        difficulty_var: ttk.StringVar,
        clock_date_var: ttk.StringVar,
        clock_time_var: ttk.StringVar,
        currency_callback: Callable[[str], None],
    ) -> None:
        """Constructs the header layout."""
        self.grid_columnconfigure(1, weight=1)

        # --- Left Section (Branding & Stats) ---
        left_frame = ttk.Frame(self)
        left_frame.grid(row=0, column=0, sticky="w", padx=0, pady=0)

        # Branding Frame (Title + Version)
        branding_frame = ttk.Frame(left_frame)
        branding_frame.pack(side=LEFT, padx=(0, 15), anchor="center")

        self.title_label = ttk.Label(
            branding_frame,
            text=translate("KaspaGateway"),
            font="-size 16 -weight bold",
        )
        self.title_label.pack(side=LEFT, anchor="w")

        self.version_label = ttk.Label(
            branding_frame,
            text=f"v{CONFIG.get('version', '1.0.0')}",
            font="-size 9",
            bootstyle="secondary",
        )
        # Using 's' (South) for anchor instead of 'bottom'
        self.version_label.pack(side=LEFT, anchor="s", padx=(5, 0), pady=(0, 3))

        # Separator
        ttk.Separator(left_frame, orient="vertical").pack(
            side=LEFT, fill=Y, padx=10, pady=2
        )

        # Stats Frame
        stats_frame = ttk.Frame(left_frame)
        stats_frame.pack(side=LEFT, padx=5)

        self.price_label, self.price_frame = self._create_stat_frame(
            stats_frame, "Price", price_var, "info"
        )
        self.hashrate_label, self.hashrate_frame = self._create_stat_frame(
            stats_frame, "Hashrate", hashrate_var, "success"
        )
        self.difficulty_label, self.difficulty_frame = self._create_stat_frame(
            stats_frame, "Difficulty", difficulty_var, "warning"
        )

        self.price_tooltip = ToolTip(self.price_frame, text="N/A")
        self.hashrate_tooltip = ToolTip(self.hashrate_frame, text="N/A")
        self.difficulty_tooltip = ToolTip(self.difficulty_frame, text="N/A")

        # --- Right Section (Controls & Clock) ---
        right_frame = ttk.Frame(self)
        right_frame.grid(row=0, column=2, sticky="e", padx=0, pady=0)

        # Clock
        clock_frame = ttk.Frame(right_frame)
        clock_frame.pack(side=LEFT, padx=(0, 10))

        time_box = ttk.Frame(clock_frame)
        time_box.pack(side=RIGHT)
        ttk.Label(
            time_box, textvariable=clock_time_var, font="-size 11 -weight bold"
        ).pack(anchor="e")
        ttk.Label(
            time_box, textvariable=clock_date_var, font="-size 8", bootstyle="secondary"
        ).pack(anchor="e")

        # Controls Frame
        controls_frame = ttk.Frame(right_frame)
        controls_frame.pack(side=LEFT)

        # Language Selector
        self.lang_frame = ttk.Frame(controls_frame)
        self.lang_frame.pack(side=LEFT, padx=5)
        self.lang_label = ttk.Label(
            self.lang_frame, text=f"{translate('Language')}:", font="-size 8"
        )
        self.lang_label.pack(anchor="w")
        self._setup_language_dropdown()

        # Theme Selector
        theme_frame = ttk.Frame(controls_frame)
        theme_frame.pack(side=LEFT, padx=5)
        self.theme_label = ttk.Label(
            theme_frame, text=f"{translate('Theme')}:", font="-size 8"
        )
        self.theme_label.pack(anchor="w")

        professional_themes = ["superhero", "litera", "darkly"]
        self.theme_combo = ttk.Combobox(
            theme_frame,
            values=professional_themes,
            state="readonly",
            width=10,
            font="-size 9",
        )
        current_theme = self.theme_manager.get_current_theme()
        if current_theme not in professional_themes:
            current_theme = "superhero"
        self.theme_combo.set(current_theme)
        self.theme_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: self.theme_manager.apply_theme(self.theme_combo.get()),
        )
        self.theme_combo.pack(anchor="w")

        # Currency Selector
        currency_frame = ttk.Frame(controls_frame)
        currency_frame.pack(side=LEFT, padx=5)
        self.currency_label = ttk.Label(
            currency_frame, text=f"{translate('Currency')}:", font="-size 8"
        )
        self.currency_label.pack(anchor="w")
        self.currency_combo = ttk.Combobox(
            currency_frame, values=[], state="readonly", width=6, font="-size 9"
        )
        self.currency_combo.set(self.currency_var.get())
        self.currency_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: currency_callback(self.currency_combo.get()),
        )
        self.currency_combo.pack(anchor="w")
        self._setup_currency_dropdown()

    def _setup_currency_dropdown(self) -> None:
        """Populates the currency combobox with supported currencies."""
        all_currencies = [c.upper() for c in CONFIG["display"]["supported_currencies"]]
        displayed_codes_lower = CONFIG["display"]["displayed_currencies"]
        displayed = [
            c.upper() for c in all_currencies if c.lower() in displayed_codes_lower
        ]

        if self.currency_combo:
            self.currency_combo["values"] = displayed
            if self.currency_var.get().upper() not in displayed:
                self.currency_var.set(displayed[0] if displayed else "USD")
            self.currency_combo.set(self.currency_var.get())

    def _setup_language_dropdown(self) -> None:
        """Populates the language combobox with available languages."""
        all_langs = get_available_languages()
        displayed_lang_codes = CONFIG["display"]["displayed_languages"]
        display_langs = [
            lang for lang in all_langs if lang["code"] in displayed_lang_codes
        ]

        self.lang_display_map = {
            f"{translate(lang['name'])}": lang["code"] for lang in display_langs
        }
        self.lang_code_map = {
            lang["code"]: f"{translate(lang['name'])}" for lang in display_langs
        }

        if not hasattr(self, "lang_combo") or self.lang_combo is None:
            self.lang_combo = ttk.Combobox(
                self.lang_frame,
                values=list(self.lang_display_map.keys()),
                state="readonly",
                width=12,
                font="-size 9",
            )
            self.lang_combo.bind(
                "<<ComboboxSelected>>",
                lambda e: self.lang_callback(
                    self.lang_display_map.get(self.lang_combo.get())
                ),
            )
            self.lang_combo.pack(anchor="w")
        else:
            self.lang_combo["values"] = list(self.lang_display_map.keys())

        current_lang_code = self.config_manager.get_config().get("language")
        display_val = self.lang_code_map.get(current_lang_code, "English")
        self.lang_combo.set(display_val)

    def _create_stat_frame(
        self,
        parent: ttk.Frame,
        title_key: str,
        value_var: ttk.StringVar,
        bootstyle: str,
    ) -> Tuple[ttk.Label, ttk.Frame]:
        """Creates a compact styled frame for displaying a statistic."""
        frame = ttk.Frame(parent)
        frame.pack(side=LEFT, padx=10)

        label = ttk.Label(
            frame, text=translate(title_key), font="-size 8", bootstyle="secondary"
        )
        label.pack(side=TOP, anchor="w")

        ttk.Label(
            frame,
            textvariable=value_var,
            font="-size 11 -weight bold",
            bootstyle=bootstyle,
        ).pack(side=TOP, anchor="w")

        return label, frame

    def set_controls_state(self, is_active: bool) -> None:
        """
        Enables or disables header controls (Language, Theme, Currency).
        Used to prevent changes during critical operations.
        """
        state = "readonly" if is_active else DISABLED

        try:
            if self.lang_combo:
                self.lang_combo.config(state=state)
            if self.theme_combo:
                self.theme_combo.config(state=state)
            if self.currency_combo:
                self.currency_combo.config(state=state)
        except Exception as e:
            logger.error(f"Failed to set header control state: {e}")

    def update_price_tooltip(self, timestamp: int) -> None:
        """Updates the tooltip for the price label."""
        if timestamp > 0 and self.price_tooltip:
            dt_obj = datetime.fromtimestamp(timestamp)
            formatted_time = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
            self.price_tooltip.text = (
                f"{translate('Last Price Update: {}').format(formatted_time)}"
            )
        elif self.price_tooltip:
            self.price_tooltip.text = "N/A"

    def update_network_tooltip(self, timestamp: int) -> None:
        """Updates the tooltip for network stats."""
        if timestamp > 0:
            dt_obj = datetime.fromtimestamp(timestamp)
            formatted_time = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
            tooltip_text = (
                f"{translate('Last Network Update: {}').format(formatted_time)}"
            )
            if self.hashrate_tooltip:
                self.hashrate_tooltip.text = tooltip_text
            if self.difficulty_tooltip:
                self.difficulty_tooltip.text = tooltip_text
        else:
            if self.hashrate_tooltip:
                self.hashrate_tooltip.text = "N/A"
            if self.difficulty_tooltip:
                self.difficulty_tooltip.text = "N/A"

    def re_translate(self) -> None:
        """Updates translations for all static text in the header."""
        if self.title_label:
            self.title_label.config(text=translate("KaspaGateway"))
        if self.version_label:
            self.version_label.config(text=f"v{CONFIG.get('version', '1.0.0')}")
        if self.price_label:
            self.price_label.config(text=translate("Price"))
        if self.hashrate_label:
            self.hashrate_label.config(text=translate("Hashrate"))
        if self.difficulty_label:
            self.difficulty_label.config(text=translate("Difficulty"))
        if self.lang_label:
            self.lang_label.config(text=f"{translate('Language')}:")
        if self.theme_label:
            self.theme_label.config(text=f"{translate('Theme')}:")
        if self.currency_label:
            self.currency_label.config(text=f"{translate('Currency')}:")

        self._setup_language_dropdown()
        self._setup_currency_dropdown()

        if (
            hasattr(self.main_window, "price_updater")
            and self.main_window.price_updater
        ):
            self.update_price_tooltip(
                self.main_window.price_updater.get_last_updated_ts()
            )
        if (
            hasattr(self.main_window, "network_updater")
            and self.main_window.network_updater
        ):
            self.update_network_tooltip(
                self.main_window.network_updater.get_last_updated_ts()
            )