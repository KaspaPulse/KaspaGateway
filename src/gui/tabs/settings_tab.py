#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Settings Tab Controller.
Implements "Smart Save" logic to enable/disable the save button based on changes.
"""

from __future__ import annotations

import json
import logging
import sys
import ttkbootstrap as ttk
from functools import reduce
from operator import getitem
from tkinter import messagebox
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, List

try:
    import winreg
except ImportError:
    winreg = None

from ttkbootstrap.constants import BOTH, LEFT, SUCCESS, DISABLED, NORMAL
from ttkbootstrap.toast import ToastNotification

from src.config.config import (
    CONFIG,
    DEFAULT_CONFIG,
)
from src.gui.tabs.settings_address_tab import SettingsAddressTab
from src.gui.tabs.settings_api_perf_tab import SettingsApiPerfTab
from src.gui.tabs.settings_db_tab import SettingsDbTab
from src.utils.i18n import translate
from src.utils.logging_config import setup_logging
from src.utils.profiling import log_performance

if TYPE_CHECKING:
    from src.gui.config_manager import ConfigManager
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)

def _get_nested_value(data: Dict[str, Any], keys: Tuple[str, ...], default: Any = None) -> Any:
    try:
        return reduce(getitem, keys, data)
    except (KeyError, TypeError):
        return default

def _set_nested_value(data: Dict[str, Any], keys: Tuple[str, ...], value: Any) -> None:
    for key in keys[:-1]:
        data = data.setdefault(key, {})
    data[keys[-1]] = value

class SettingsTab(ttk.Frame):
    def __init__(self, parent: ttk.Frame, main_window: MainWindow) -> None:
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

        # Smart Save State
        self.original_state_snapshot: str = ""
        self._is_initializing = True

        self.api_perf_tab = None
        self.address_tab = None
        self.db_tab = None
        self.address_tab_initialized = False
        self.db_tab_initialized = False

        self.pack(fill=BOTH, expand=True)
        self._build_ui()
        
        # Delay loading to ensure UI is ready
        self.after(50, self._load_settings_into_ui)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.outer_notebook = ttk.Notebook(self)
        self.outer_notebook.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self.api_perf_frame = ttk.Frame(self.outer_notebook, padding=10)
        self.addr_frame = ttk.Frame(self.outer_notebook, padding=10)
        self.db_frame = ttk.Frame(self.outer_notebook, padding=10)

        self.outer_notebook.add(self.api_perf_frame, text=f" {translate('API & Performance')} ")
        self.outer_notebook.add(self.addr_frame, text=f" {translate('Manage Addresses')} ")
        self.outer_notebook.add(self.db_frame, text=f" {translate('Database Maintenance')} ")

        # Pass self to child so it can register callbacks
        self.api_perf_tab = SettingsApiPerfTab(self.api_perf_frame, self.main_window, self)
        self.api_perf_tab.pack(fill=BOTH, expand=True)

        self.outer_notebook.bind("<<NotebookTabChanged>>", self._on_outer_tab_changed)

        self.bottom_button_frame = ttk.Frame(self)
        self.bottom_button_frame.grid(row=1, column=0, sticky="e", pady=(15, 5), padx=15)

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
            state=DISABLED  # Default to disabled until changes are detected
        )
        self.save_button.pack(side=LEFT)

    def _on_outer_tab_changed(self, event: Any) -> None:
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
                    self.address_tab = SettingsAddressTab(self.addr_frame, self.main_window)
                    self.address_tab.pack(fill=BOTH, expand=True)
                    self.address_tab_initialized = True
                if self.address_tab:
                    self.address_tab.refresh_address_list()

            elif selected_tab_text == translate("Database Maintenance"):
                if not self.db_tab_initialized:
                    self.db_tab = SettingsDbTab(self.db_frame, self.main_window)
                    self.db_tab.pack(fill=BOTH, expand=True)
                    self.db_tab_initialized = True
                if self.db_tab:
                    self.db_tab._refresh_db_info()
        except Exception as e:
            logger.error(f"Error handling settings tab change: {e}")

    @log_performance
    def _load_settings_into_ui(self, config_data: Optional[Dict[str, Any]] = None) -> None:
        self._is_initializing = True
        config = config_data or self.config_manager.get_config()
        
        self.check_updates_var.set(config.get("check_for_updates", True))
        self.autostart_var.set(config.get("autostart_on_windows", False))
        self.auto_refresh_var.set(
            _get_nested_value(config, ("performance", "auto_refresh_enabled"), False)
        )
        
        display_config = config.get("display", {})
        
        # Helper to set vars safely
        def set_vars_from_list(var_dict, target_list):
            if not target_list: return
            for code, var in var_dict.items():
                var.set(code in target_list)

        set_vars_from_list(self.lang_vars, display_config.get("displayed_languages", DEFAULT_CONFIG["display"]["displayed_languages"]))
        set_vars_from_list(self.currency_vars, display_config.get("displayed_currencies", DEFAULT_CONFIG["display"]["displayed_currencies"]))
        set_vars_from_list(self.tab_vars, display_config.get("displayed_tabs", DEFAULT_CONFIG["display"]["displayed_tabs"]))

        if self.api_perf_tab:
            self.api_perf_tab.load_settings(config)

        # Take snapshot of the "Clean" state
        self._take_snapshot()
        self._attach_tracers()
        self._is_initializing = False
        self._check_for_changes() # Initial check

    def _take_snapshot(self) -> None:
        """Saves the current UI state as a JSON string for comparison."""
        self.original_state_snapshot = json.dumps(self._gather_current_ui_state(), sort_keys=True)

    def _gather_current_ui_state(self) -> Dict[str, Any]:
        """Collects all current values from the UI widgets into a dictionary."""
        state = {}
        
        # General Vars
        state["check_updates"] = self.check_updates_var.get()
        state["autostart"] = self.autostart_var.get()
        state["auto_refresh"] = self.auto_refresh_var.get()
        
        # Lists
        state["langs"] = sorted([k for k, v in self.lang_vars.items() if v.get()])
        state["currs"] = sorted([k for k, v in self.currency_vars.items() if v.get()])
        state["tabs"] = sorted([k for k, v in self.tab_vars.items() if v.get()])
        
        # API/Perf Tab Values
        if self.api_perf_tab:
            for key_tuple, widget in self.api_perf_tab.entries.items():
                try:
                    val = widget.get()
                    # Normalize numbers to strings for consistent comparison
                    if isinstance(val, (int, float)): val = str(val)
                    state[str(key_tuple)] = val
                except Exception: pass
            
            if hasattr(self.api_perf_tab, "profile_combo"):
                state["active_profile"] = self.api_perf_tab.profile_combo.get()
            
            # Add API endpoints if needed (basic implementation covers active profile)

        return state

    def _attach_tracers(self) -> None:
        """Attaches trace callbacks to all variables to detect changes."""
        vars_to_trace = [
            self.check_updates_var, self.autostart_var, self.auto_refresh_var
        ]
        vars_to_trace.extend(self.lang_vars.values())
        vars_to_trace.extend(self.currency_vars.values())
        vars_to_trace.extend(self.tab_vars.values())
        
        if self.api_perf_tab:
            for widget in self.api_perf_tab.entries.values():
                if isinstance(widget, ttk.Variable):
                    vars_to_trace.append(widget)
                # Note: Entry widgets usually need binding to KeyRelease or StringVar trace
        
        for var in vars_to_trace:
            try:
                # Avoid double binding if re-initialized
                if not hasattr(var, "_is_traced"):
                    var.trace_add("write", self._on_ui_change)
                    var._is_traced = True
            except Exception: pass

    def _on_ui_change(self, *args) -> None:
        """Callback triggered when any UI variable changes."""
        if not self._is_initializing:
            self._check_for_changes()

    def _check_for_changes(self) -> None:
        """Compares current state with snapshot and updates Save button."""
        current_snapshot = json.dumps(self._gather_current_ui_state(), sort_keys=True)
        has_changes = current_snapshot != self.original_state_snapshot
        
        if has_changes:
            self.save_button.config(state=NORMAL, text=f"{translate('Save Settings')} *")
        else:
            self.save_button.config(state=DISABLED, text=translate("Save Settings"))

    def notify_change(self) -> None:
        """Public method for child tabs to trigger a change check manually."""
        self._on_ui_change()

    def _handle_autostart(self, enable: bool) -> None:
        if sys.platform != "win32" or not winreg:
            if enable:
                self.autostart_var.set(False)
                messagebox.showwarning(translate("Autostart"), translate("Autostart is only available on Windows."))
            return

        app_name = "KaspaGateway"
        reg_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        try:
            exe_path = sys.executable
            if not getattr(sys, "frozen", False):
                logger.warning("Autostart disabled: Not frozen.")
                if enable:
                    self.autostart_var.set(False)
                    messagebox.showwarning(translate("Autostart"), translate("Autostart can only be set for the installed application."))
                return

            user_data_root_db = CONFIG["paths"]["database"]
            user_data_root = os.path.dirname(user_data_root_db) if user_data_root_db else ""
            command = f'"{exe_path}" --user-data-path "{user_data_root}"'

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_WRITE) as key:
                if enable:
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, command)
                else:
                    try:
                        winreg.DeleteValue(key, app_name)
                    except FileNotFoundError:
                        pass
        except Exception as e:
            logger.error(f"Autostart error: {e}")
            if enable:
                self.autostart_var.set(False)

    @log_performance
    def _save_settings(self) -> None:
        current_runtime_version = CONFIG.get("version")
        new_config = json.loads(json.dumps(self.config_manager.get_config()))
        path_changed = False
        old_log_level = new_config.get("log_level", "INFO")

        try:
            if self.api_perf_tab:
                for key_tuple, widget in self.api_perf_tab.entries.items():
                    value = widget.get()
                    if isinstance(widget, ttk.Entry):
                        value = value.strip()
                        default_value = _get_nested_value(DEFAULT_CONFIG, key_tuple)
                        if isinstance(default_value, (int, float)):
                            try:
                                value = type(default_value)(float(value))
                            except ValueError:
                                value = default_value

                    if len(key_tuple) > 1 and key_tuple[0] == "paths" and _get_nested_value(new_config, key_tuple) != value:
                        path_changed = True
                    
                    _set_nested_value(new_config, key_tuple, value)

            new_config["check_for_updates"] = self.check_updates_var.get()
            
            autostart_val = self.autostart_var.get()
            if new_config.get("autostart_on_windows") != autostart_val:
                self._handle_autostart(autostart_val)
            new_config["autostart_on_windows"] = autostart_val

            _set_nested_value(new_config, ("performance", "auto_refresh_enabled"), self.auto_refresh_var.get())

            new_config["display"]["displayed_languages"] = [c for c, v in self.lang_vars.items() if v.get()]
            if not new_config["display"]["displayed_languages"]:
                messagebox.showerror(translate("Invalid Input"), translate("Please select at least one language."))
                return

            new_config["display"]["displayed_currencies"] = [c for c, v in self.currency_vars.items() if v.get()]
            if not new_config["display"]["displayed_currencies"]:
                messagebox.showerror(translate("Invalid Input"), translate("Please select at least one currency."))
                return

            new_config["display"]["displayed_tabs"] = [n for n, v in self.tab_vars.items() if v.get()]

            if self.api_perf_tab:
                new_config["api"]["active_profile"] = self.api_perf_tab.profile_combo.get()

        except (ValueError, TypeError) as e:
            messagebox.showerror(translate("Invalid Input"), f"{translate('Invalid Input')}: {e}")
            return

        if self.config_manager.save_config(new_config):
            # Update snapshot to match new state (so button becomes disabled)
            self._take_snapshot()
            self._check_for_changes()

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
                try:
                    setup_logging(level=new_log_level, log_path=CONFIG["paths"]["log"])
                    if self.main_window.log_tab:
                        self.main_window.log_tab.reattach_log_file()
                except Exception as e:
                    logger.error(f"Failed to apply new log level: {e}")

            self.main_window.on_settings_saved()

            if path_changed:
                messagebox.showinfo(translate("Restart Required"), translate("Path settings changed. Please restart the application."))
        else:
            messagebox.showerror(translate("Error"), translate("Failed to save configuration."))

    def _reset_settings(self) -> None:
        if messagebox.askyesno(translate("Reset to Defaults"), translate("This will reset all settings to their default values and cannot be undone. Are you sure?")):
            self.autostart_var.set(False)
            self._handle_autostart(False)
            
            current_runtime_version = CONFIG.get("version")

            self._load_settings_into_ui(self.config_manager.get_default_config())
            self._save_settings()
            
            if current_runtime_version:
                 CONFIG["version"] = current_runtime_version
                 self.main_window.title(f"KaspaGateway Version {current_runtime_version}")

    def re_translate(self) -> None:
        for i, key in enumerate(["API & Performance", "Manage Addresses", "Database Maintenance"]):
            self.outer_notebook.tab(i, text=f" {translate(key)} ")

        if self.api_perf_tab: self.api_perf_tab.re_translate()
        if self.address_tab: self.address_tab.re_translate()
        if self.db_tab: self.db_tab.re_translate()

        self.save_button.config(text=translate("Save Settings"))
        self.reset_button.config(text=translate("Reset to Defaults"))
