#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This module contains the SettingsTab class (View/Controller).
It manages the application's configuration, including API, Performance,
Addresses, and Database maintenance tabs.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from functools import reduce
from operator import getitem
from tkinter import messagebox
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

try:
    import winreg
except ImportError:
    winreg = None  # type: ignore

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, LEFT, SUCCESS
from ttkbootstrap.toast import ToastNotification

from src.config.config import (
    CONFIG,
    CURRENCY_TRANSLATION_KEYS,
    DEFAULT_CONFIG,
    SUPPORTED_CURRENCIES,
    SUPPORTED_TABS,
)
from src.gui.tabs.settings_address_tab import SettingsAddressTab
from src.gui.tabs.settings_api_perf_tab import SettingsApiPerfTab
from src.gui.tabs.settings_db_tab import SettingsDbTab
from src.utils.i18n import get_available_languages, switch_language, translate
from src.utils.logging_config import setup_logging
from src.utils.profiling import log_performance

if TYPE_CHECKING:
    from src.gui.config_manager import ConfigManager
    from src.gui.main_window import MainWindow


logger = logging.getLogger(__name__)


def _get_nested_value(
    data: Dict[str, Any], keys: Tuple[str, ...], default: Any = None
) -> Any:
    """Safely retrieves a nested value from a dictionary."""
    try:
        return reduce(getitem, keys, data)
    except (KeyError, TypeError):
        return default


def _set_nested_value(
    data: Dict[str, Any], keys: Tuple[str, ...], value: Any
) -> None:
    """Safely sets a nested value in a dictionary."""
    for key in keys[:-1]:
        data = data.setdefault(key, {})
    data[keys[-1]] = value


class SettingsTab(ttk.Frame):
    """
    The main Settings Tab container.
    Manages sub-tabs for API/Performance, Addresses, and Database Maintenance.
    """

    main_window: MainWindow
    config_manager: ConfigManager
    entries: Dict[Tuple[str, ...], Any]
    lang_vars: Dict[str, ttk.BooleanVar]
    currency_vars: Dict[str, ttk.BooleanVar]
    tab_vars: Dict[str, ttk.BooleanVar]
    tab_cbs: Dict[str, ttk.Checkbutton]
    check_updates_var: ttk.BooleanVar
    autostart_var: ttk.BooleanVar
    auto_refresh_var: ttk.BooleanVar
    
    api_perf_tab: Optional[SettingsApiPerfTab]
    address_tab: Optional[SettingsAddressTab]
    db_tab: Optional[SettingsDbTab]
    
    address_tab_initialized: bool
    db_tab_initialized: bool
    
    outer_notebook: ttk.Notebook
    api_perf_frame: ttk.Frame
    addr_frame: ttk.Frame
    db_frame: ttk.Frame
    bottom_button_frame: ttk.Frame
    reset_button: ttk.Button
    save_button: ttk.Button

    def __init__(self, parent: ttk.Frame, main_window: MainWindow) -> None:
        """
        Initializes the SettingsTab.

        Args:
            parent: The parent widget.
            main_window: Reference to the main application window.
        """
        super().__init__(parent, padding=10)
        self.main_window = main_window
        self.config_manager = main_window.config_manager

        self.entries = {}
        self.lang_vars = {}
        self.currency_vars = {}
        self.tab_vars = {}
        self.tab_cbs = {}

        self.check_updates_var = ttk.BooleanVar()
        self.autostart_var = ttk.BooleanVar()
        self.auto_refresh_var = ttk.BooleanVar()

        self.api_perf_tab = None
        self.address_tab = None
        self.db_tab = None

        self.address_tab_initialized = False
        self.db_tab_initialized = False

        self.pack(fill=BOTH, expand=True)
        self._build_ui()
        self._load_settings_into_ui()

    def _build_ui(self) -> None:
        """Constructs the UI layout for the Settings tab."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.outer_notebook = ttk.Notebook(self)
        self.outer_notebook.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self.api_perf_frame = ttk.Frame(self.outer_notebook, padding=10)
        self.addr_frame = ttk.Frame(self.outer_notebook, padding=10)
        self.db_frame = ttk.Frame(self.outer_notebook, padding=10)

        self.outer_notebook.add(
            self.api_perf_frame, text=f" {translate('API & Performance')} "
        )
        self.outer_notebook.add(
            self.addr_frame, text=f" {translate('Manage Addresses')} "
        )
        self.outer_notebook.add(
            self.db_frame, text=f" {translate('Database Maintenance')} "
        )

        self.api_perf_tab = SettingsApiPerfTab(
            self.api_perf_frame, self.main_window, self
        )
        self.api_perf_tab.pack(fill=BOTH, expand=True)

        self.outer_notebook.bind("<<NotebookTabChanged>>", self._on_outer_tab_changed)

        self.bottom_button_frame = ttk.Frame(self)
        self.bottom_button_frame.grid(
            row=1, column=0, sticky="e", pady=(15, 5), padx=15
        )

        self.reset_button = ttk.Button(
            self.bottom_button_frame,
            text=translate("Reset to Defaults"),
            command=self._reset_settings,
            bootstyle="secondary",
        )
        self.reset_button.pack(side=LEFT, padx=(0, 10))

        self.save_button = ttk.Button(
            self.bottom_button_frame,
            text=translate("Save Settings"),
            command=self._save_settings,
            bootstyle="success",
        )
        self.save_button.pack(side=LEFT)

    def _on_outer_tab_changed(self, event: Any) -> None:
        """Handles tab switching within the Settings notebook."""
        try:
            selected_tab_id = self.outer_notebook.select()
            selected_tab_text = self.outer_notebook.tab(selected_tab_id, "text").strip()

            if selected_tab_text == translate("API & Performance"):
                self.bottom_button_frame.grid()
                if self.api_perf_tab:
                    self.api_perf_tab.re_translate()
            else:
                self.bottom_button_frame.grid_remove()

            if selected_tab_text == translate("Manage Addresses"):
                if not self.address_tab_initialized:
                    logger.info("Initializing 'Manage Addresses' tab for the first time.")
                    self.address_tab = SettingsAddressTab(
                        self.addr_frame, self.main_window
                    )
                    self.address_tab.pack(fill=BOTH, expand=True)
                    self.address_tab_initialized = True
                if self.address_tab:
                    self.address_tab.refresh_address_list()

            elif selected_tab_text == translate("Database Maintenance"):
                if not self.db_tab_initialized:
                    logger.info("Initializing 'Database Maintenance' tab for the first time.")
                    self.db_tab = SettingsDbTab(self.db_frame, self.main_window)
                    self.db_tab.pack(fill=BOTH, expand=True)
                    self.db_tab_initialized = True
                if self.db_tab:
                    self.db_tab._refresh_db_info()

        except Exception as e:
            logger.error(f"Error handling settings tab change: {e}")

    @log_performance
    def _load_settings_into_ui(
        self, config_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Loads configuration data into all child tabs and variables."""
        config = config_data or self.config_manager.get_config()

        self.check_updates_var.set(config.get("check_for_updates", True))
        self.autostart_var.set(config.get("autostart_on_windows", False))
        self.auto_refresh_var.set(
            _get_nested_value(config, ("performance", "auto_refresh_enabled"), False)
        )

        display_config = config.get("display", {})
        
        for code, var in self.lang_vars.items():
            var.set(code in display_config.get("displayed_languages", []))
            
        for code, var in self.currency_vars.items():
            var.set(code in display_config.get("displayed_currencies", []))
            
        for name, var in self.tab_vars.items():
            var.set(name in display_config.get("displayed_tabs", []))

        if self.api_perf_tab:
            self.api_perf_tab.load_settings(config)

    def _handle_autostart(self, enable: bool) -> None:
        """
        Manages the Windows Registry key for autostart.
        Safely handles non-Windows platforms and non-frozen environments.
        """
        if sys.platform != "win32" or not winreg:
            if enable:
                self.autostart_var.set(False)
                messagebox.showwarning(
                    translate("Autostart"),
                    translate("Autostart is only available on Windows."),
                )
            return

        app_name = "KaspaGateway"
        reg_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        try:
            exe_path = sys.executable
            if not getattr(sys, "frozen", False):
                logger.warning(
                    "Autostart disabled: Application is not running as a frozen executable."
                )
                if enable:
                    self.autostart_var.set(False)
                    messagebox.showwarning(
                        translate("Autostart"),
                        translate("Autostart can only be set for the installed application."),
                    )
                return

            if "temp" in exe_path.lower():
                logger.warning(
                    "Autostart disabled: Application is running from a temporary directory."
                )
                if enable:
                    self.autostart_var.set(False)
                    messagebox.showwarning(
                        translate("Autostart"),
                        translate("Autostart can only be set for the installed application."),
                    )
                return

            # Use the globally initialized and validated USER_DATA_ROOT
            user_data_root_db = CONFIG["paths"]["database"]
            user_data_root = ""
            if user_data_root_db:
                user_data_root = os.path.dirname(user_data_root_db)

            command = f'"{exe_path}" --user-data-path "{user_data_root}"'

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_WRITE
            ) as key:
                if enable:
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, command)
                    logger.info(f"Enabled autostart. Command: {command}")
                else:
                    try:
                        winreg.DeleteValue(key, app_name)
                        logger.info("Disabled autostart.")
                    except FileNotFoundError:
                        logger.info(
                            "Autostart was already disabled (registry key not found)."
                        )

        except Exception as e:
            logger.error(f"Failed to update registry for autostart: {e}", exc_info=True)
            messagebox.showerror(
                translate("Error"), f"{translate('Failed to update registry:')}\n{e}"
            )
            if enable:
                self.autostart_var.set(False)

    @log_performance
    def _save_settings(self) -> None:
        """
        Gathers all settings from self and child tabs, saves to disk,
        and restores critical runtime state (like version hash).
        """
        # Capture the current runtime version (with git hash) to prevent overwrite
        current_runtime_version = CONFIG.get("version")

        new_config: Dict[str, Any] = json.loads(
            json.dumps(self.config_manager.get_config())
        )
        path_changed = False
        old_log_level = new_config.get("log_level", "INFO")

        try:
            if self.api_perf_tab:
                for key_tuple, widget in self.api_perf_tab.entries.items():
                    value: Any = None
                    if isinstance(widget, ttk.BooleanVar):
                        value = widget.get()
                    elif isinstance(widget, ttk.StringVar):
                        value = widget.get()
                    else:
                        # Assume Entry widget
                        value_str = widget.get().strip()
                        default_value = _get_nested_value(DEFAULT_CONFIG, key_tuple)
                        if isinstance(default_value, (int, float)):
                            try:
                                value = type(default_value)(float(value_str))
                            except ValueError:
                                value = default_value
                        else:
                            value = value_str

                    if (
                        len(key_tuple) > 1
                        and key_tuple[0] == "paths"
                        and _get_nested_value(new_config, key_tuple) != value
                    ):
                        path_changed = True

                    _set_nested_value(new_config, key_tuple, value)

            new_config["check_for_updates"] = self.check_updates_var.get()

            autostart_val = self.autostart_var.get()
            if new_config.get("autostart_on_windows") != autostart_val:
                self._handle_autostart(autostart_val)
            new_config["autostart_on_windows"] = autostart_val

            _set_nested_value(
                new_config,
                ("performance", "auto_refresh_enabled"),
                self.auto_refresh_var.get(),
            )

            new_config["display"]["displayed_languages"] = [
                code for code, var in self.lang_vars.items() if var.get()
            ]
            if not new_config["display"]["displayed_languages"]:
                messagebox.showerror(
                    translate("Invalid Input"),
                    translate("Please select at least one language."),
                )
                return

            new_config["display"]["displayed_currencies"] = [
                code for code, var in self.currency_vars.items() if var.get()
            ]
            if not new_config["display"]["displayed_currencies"]:
                messagebox.showerror(
                    translate("Invalid Input"),
                    translate("Please select at least one currency."),
                )
                return

            new_config["display"]["displayed_tabs"] = [
                name for name, var in self.tab_vars.items() if var.get()
            ]

            if self.api_perf_tab:
                new_config["api"]["active_profile"] = self.api_perf_tab.profile_combo.get()

        except (ValueError, TypeError) as e:
            messagebox.showerror(
                translate("Invalid Input"), f"{translate('Invalid Input')}: {e}"
            )
            return

        if self.config_manager.save_config(new_config):
            # Restore the runtime version hash immediately after reload
            if current_runtime_version:
                CONFIG["version"] = current_runtime_version
                self.main_window.title(f"KaspaGateway Version {current_runtime_version}")

            ToastNotification(
                title=translate("Configuration saved"),
                message=translate("Configuration saved"),
                bootstyle=SUCCESS,
                duration=3000,
            ).show_toast()

            new_log_level = CONFIG.get("log_level", "INFO")
            if old_log_level != new_log_level:
                logger.warning(
                    f"Log level changing from {old_log_level} to {new_log_level}"
                )
                try:
                    setup_logging(level=new_log_level, log_path=CONFIG["paths"]["log"])
                    if self.main_window.log_tab:
                        self.main_window.log_tab.reattach_log_file()
                    logger.info(f"Log level changed successfully to {new_log_level}")
                except Exception as e:
                    logger.error(f"Failed to apply new log level: {e}")

            self.main_window.on_settings_saved()

            if path_changed:
                messagebox.showinfo(
                    translate("Restart Required"),
                    translate("Path settings changed. Please restart the application."),
                )
        else:
            messagebox.showerror(
                translate("Error"), translate("Failed to save configuration.")
            )

    def _reset_settings(self) -> None:
        """Resets all settings to default values and reloads the UI."""
        if messagebox.askyesno(
            translate("Reset to Defaults"),
            translate(
                "This will reset all settings to their default values and cannot be undone. Are you sure?"
            ),
        ):
            self.autostart_var.set(False)
            self._handle_autostart(False)
            
            # Preserve version before loading defaults to ensure continuity in UI
            current_runtime_version = CONFIG.get("version")
            
            self._load_settings_into_ui(self.config_manager.get_default_config())
            self._save_settings()
            
            # Ensure version is restored if save logic didn't cover this path
            if current_runtime_version:
                CONFIG["version"] = current_runtime_version
                self.main_window.title(f"KaspaGateway Version {current_runtime_version}")

    def re_translate(self) -> None:
        """Delegates re-translation to all child tabs."""
        for i, key in enumerate(
            ["API & Performance", "Manage Addresses", "Database Maintenance"]
        ):
            self.outer_notebook.tab(i, text=f" {translate(key)} ")

        if self.api_perf_tab:
            self.api_perf_tab.re_translate()
        if self.address_tab:
            self.address_tab.re_translate()
        if self.db_tab:
            self.db_tab.re_translate()

        self.save_button.config(text=translate("Save Settings"))
        self.reset_button.config(text=translate("Reset to Defaults"))
