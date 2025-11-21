#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This module contains the SettingsApiPerfTab class.
It manages General, API, and Performance settings within the Settings Tab.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import socket
import sys
import threading
import tkinter as tk
from functools import reduce
from ipaddress import ip_address
from operator import getitem
from tkinter import filedialog, messagebox
from tkinter.simpledialog import askstring
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, DISABLED, HORIZONTAL, LEFT, NORMAL, RIGHT, YES, X
from ttkbootstrap.toast import ToastNotification
from ttkbootstrap.tooltip import ToolTip

from src.config.config import (
    CONFIG,
    CURRENCY_TRANSLATION_KEYS,
    DEFAULT_CONFIG,
    SUPPORTED_CURRENCIES,
    SUPPORTED_TABS,
)
from src.utils.i18n import get_available_languages, translate
from src.utils.logging_config import setup_logging, shutdown_file_handler
from src.utils.validation import sanitize_cli_arg

if TYPE_CHECKING:
    from src.gui.config_manager import ConfigManager
    from src.gui.main_window import MainWindow
    from src.gui.tabs.settings_tab import SettingsTab

logger = logging.getLogger(__name__)


def _get_nested_value(
    d: Dict[str, Any], keys: Tuple[str, ...], default: Any = None
) -> Any:
    """Safely retrieves a nested value from a dictionary."""
    try:
        return reduce(getitem, keys, d)
    except (KeyError, TypeError):
        return default


def _set_nested_value(d: Dict[str, Any], keys: Tuple[str, ...], value: Any) -> None:
    """Safely sets a nested value in a dictionary."""
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


class SettingsApiPerfTab(ttk.Frame):
    """
    This class encapsulates the "API & Performance" tab.
    It acts as a sub-view for the main SettingsTab.
    """

    def __init__(
        self,
        parent: ttk.Frame,
        main_window: MainWindow,
        settings_tab: SettingsTab,
    ) -> None:
        super().__init__(parent)
        self.main_window = main_window
        self.config_manager = main_window.config_manager
        self.settings_tab = settings_tab # Reference to parent for notifications

        # Share state references with the parent SettingsTab
        self.entries = settings_tab.entries
        self.lang_vars = settings_tab.lang_vars
        self.currency_vars = settings_tab.currency_vars
        self.tab_vars = settings_tab.tab_vars
        self.tab_cbs = settings_tab.tab_cbs
        self.check_updates_var = settings_tab.check_updates_var
        self.autostart_var = settings_tab.autostart_var
        self.auto_refresh_var = settings_tab.auto_refresh_var

        self.log_level_var = ttk.StringVar()
        self.entries[("log_level",)] = self.log_level_var

        self.api_perf_labels: Dict[str, ttk.Label] = {}
        self.path_labels: Dict[str, ttk.Label] = {}
        self.tooltips_widgets: Dict[str, ToolTip] = {}
        self.labelframes: Dict[str, ttk.Labelframe] = {}

        self.current_api_key_path: Optional[Tuple[str, ...]] = None
        self.base_url_options: List[str] = []
        self._is_loading_api_ui: bool = False

        self.pack(fill=BOTH, expand=True)
        self._configure_api_perf_tab()

    def _configure_api_perf_tab(self) -> None:
        """Builds the UI components for this tab."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.inner_notebook = ttk.Notebook(self)
        self.inner_notebook.grid(row=0, column=0, sticky="nsew")

        self.general_tab = ttk.Frame(self.inner_notebook, padding=(10, 0))
        self.api_tab_frame = ttk.Frame(self.inner_notebook, padding=10)
        self.perf_tab = ttk.Frame(self.inner_notebook, padding=(10, 0))

        for container in [self.general_tab, self.api_tab_frame, self.perf_tab]:
            container.grid_columnconfigure(0, weight=1)

        self.inner_notebook.add(self.general_tab, text=translate("General"))
        self.inner_notebook.add(self.api_tab_frame, text=translate("API Settings"))
        self.inner_notebook.add(self.perf_tab, text=translate("Performance Settings"))

        self._build_general_settings(self.general_tab)
        self._build_api_management_tab(self.api_tab_frame)
        self._build_performance_settings(self.perf_tab)

    def _build_general_settings(self, parent: ttk.Frame) -> None:
        """Builds the 'General' sub-tab UI."""
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        display_options_frame = ttk.Labelframe(
            parent, text=translate("Display Settings"), padding=10
        )
        display_options_frame.grid(
            row=0, column=0, sticky="nsew", pady=(10, 15), padx=10
        )
        display_options_frame.grid_columnconfigure(
            (0, 1, 2), weight=1, uniform="group1"
        )
        self.labelframes["Display Settings"] = display_options_frame

        lang_items = {
            lang["code"]: f"{translate(lang['name'])} ({lang['code']})"
            for lang in get_available_languages()
        }
        curr_items = {
            code: f"{translate(CURRENCY_TRANSLATION_KEYS.get(code, code.upper()))} ({code.upper()})"
            for code in SUPPORTED_CURRENCIES
        }
        tab_items = {
            tab_name: translate(tab_name) for tab_name in SUPPORTED_TABS
        }

        self._setup_selectable_list(
            display_options_frame, 0, "Displayed Languages", lang_items, "lang_vars", None, "displayed_languages", num_cols=2
        )
        self._setup_selectable_list(
            display_options_frame, 1, "Displayed Currencies", curr_items, "currency_vars", None, "displayed_currencies", num_cols=3
        )
        self._setup_selectable_list(
            display_options_frame, 2, "Displayed Tabs", tab_items, "tab_vars", "tab_cbs", "displayed_tabs", num_cols=2
        )

        bottom_container = ttk.Frame(parent)
        bottom_container.grid(row=1, column=0, sticky="nsew", padx=10)
        bottom_container.grid_columnconfigure(0, weight=1)
        bottom_container.grid_columnconfigure(1, weight=2)
        bottom_container.grid_rowconfigure(0, weight=1)

        advanced_frame = ttk.Labelframe(
            bottom_container, text=translate("Advanced"), padding=10
        )
        advanced_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        advanced_frame.grid_columnconfigure(1, weight=1)
        self.labelframes["Advanced"] = advanced_frame

        check_updates_cb = ttk.Checkbutton(
            advanced_frame,
            text=translate("Check for updates on startup"),
            variable=self.check_updates_var,
            command=lambda: self.settings_tab.notify_change()
        )
        check_updates_cb.grid(row=1, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        self.entries[("check_for_updates",)] = self.check_updates_var

        self.autostart_cb = ttk.Checkbutton(
            advanced_frame,
            text=translate("Start with Windows"),
            variable=self.autostart_var,
            command=lambda: self.settings_tab.notify_change()
        )
        self.autostart_cb.grid(
            row=2, column=0, columnspan=2, sticky="w", padx=5, pady=5
        )
        self.entries[("autostart_on_windows",)] = self.autostart_var

        if sys.platform != "win32":
            self.autostart_cb.config(state=DISABLED)
            ToolTip(self.autostart_cb, text=translate("Autostart is only available on Windows."))

        log_level_frame = ttk.Frame(advanced_frame)
        log_level_frame.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        self.log_level_label = ttk.Label(
            log_level_frame, text=f"{translate('Logging Level')}:"
        )
        self.log_level_label.pack(side=LEFT, padx=(0, 5))

        self.log_level_combo = ttk.Combobox(
            log_level_frame,
            textvariable=self.log_level_var,
            values=["DEBUG", "INFO", "WARN", "ERROR"],
            state="readonly",
            width=10,
        )
        self.log_level_combo.pack(side=LEFT)
        self.log_level_combo.bind("<<ComboboxSelected>>", lambda e: self.settings_tab.notify_change())

        path_frame = ttk.Labelframe(
            bottom_container, text=translate("File Paths"), padding=10
        )
        path_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        path_frame.grid_columnconfigure(1, weight=1)
        self.labelframes["File Paths"] = path_frame
        path_keys = {
            "database": (("paths", "database"), "Database Path"),
            "export": (("paths", "export"), "Export Path"),
            "log": (("paths", "log"), "Log Path"),
            "backup": (("paths", "backup"), "Backup Directory"),
        }
        for i, (key, (key_tuple, label)) in enumerate(path_keys.items()):
            self._create_path_setting_row(path_frame, i, label, key_tuple, key)

    def _build_performance_settings(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        api_lf = ttk.Labelframe(parent, text=translate("API Performance"), padding=10)
        api_lf.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 5))
        api_lf.grid_columnconfigure(4, weight=1)
        
        self._create_setting_row(api_lf, 0, 0, "API Timeout (sec)", ("performance", "timeout"), "Tooltip_timeout", entry_width=8)
        self._create_setting_row(api_lf, 0, 2, "Retry Attempts", ("performance", "retry_attempts"), "Tooltip_retry_attempts", entry_width=8)
        self._create_setting_row(api_lf, 1, 0, "Backoff Factor", ("performance", "backoff_factor"), "Tooltip_backoff_factor", entry_width=8)
        self._create_setting_row(api_lf, 1, 2, "Max Workers", ("performance", "max_workers"), "Tooltip_max_workers", entry_width=8)
        self.labelframes["API Performance"] = api_lf

        trans_lf = ttk.Labelframe(parent, text=translate("Transaction Fetching"), padding=10)
        trans_lf.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        trans_lf.grid_columnconfigure(4, weight=1)
        self._create_setting_row(trans_lf, 0, 0, "Max Pages", ("performance", "max_pages"), "Tooltip_max_pages", entry_width=8)
        self._create_setting_row(trans_lf, 0, 2, "Page Delay (sec)", ("performance", "page_delay"), "Tooltip_page_delay", entry_width=8)
        self.labelframes["Transaction Fetching"] = trans_lf

        cache_lf = ttk.Labelframe(parent, text=translate("Caching"), padding=10)
        cache_lf.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        cache_lf.grid_columnconfigure(4, weight=1)
        self._create_setting_row(cache_lf, 0, 0, "Price Cache (hours)", ("performance", "price_cache_hours"), "Tooltip_price_cache_hours", entry_width=8)
        self._create_setting_row(cache_lf, 0, 2, "Network Cache (hours)", ("performance", "network_cache_hours"), "Tooltip_network_cache_hours", entry_width=8)
        self.labelframes["Caching"] = cache_lf

        auto_lf = ttk.Labelframe(parent, text=translate("Automatic Refresh"), padding=10)
        auto_lf.grid(row=3, column=0, sticky="nsew", padx=10, pady=10)
        auto_lf.grid_columnconfigure(3, weight=1)
        self.labelframes["Automatic Refresh"] = auto_lf

        self.auto_refresh_cb = ttk.Checkbutton(
            auto_lf, text=translate("Enable Auto-Refresh"), variable=self.auto_refresh_var,
            command=lambda: self.settings_tab.notify_change()
        )
        self.auto_refresh_cb.grid(row=0, column=0, sticky="w", pady=5, padx=(5, 20))
        self.entries[("performance", "auto_refresh_enabled")] = self.auto_refresh_var
        self._create_setting_row(auto_lf, 0, 1, "Refresh Interval (seconds)", ("performance", "auto_refresh_interval_seconds"), None, entry_width=8, padx=5)

    def _build_api_management_tab(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1, uniform="group1")
        parent.grid_columnconfigure(1, weight=3, uniform="group1")
        parent.grid_rowconfigure(0, weight=1)

        left_pane = ttk.Frame(parent)
        left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_pane.grid_rowconfigure(1, weight=1)
        left_pane.grid_columnconfigure(0, weight=1)

        right_pane = ttk.Frame(parent)
        right_pane.grid(row=0, column=1, sticky="nsew")
        right_pane.grid_rowconfigure(0, weight=1)
        right_pane.grid_columnconfigure(0, weight=1)

        profiles_lf = ttk.Labelframe(left_pane, text=translate("API Server Profiles"), padding=10)
        profiles_lf.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        profiles_lf.grid_columnconfigure(0, weight=1)
        self.labelframes["API Server Profiles"] = profiles_lf

        self.profile_combo = ttk.Combobox(profiles_lf, state="readonly", exportselection=False)
        self.profile_combo.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_select)

        profile_btn_frame = ttk.Frame(profiles_lf)
        profile_btn_frame.grid(row=1, column=0, sticky="ew")
        self.add_profile_btn = ttk.Button(profile_btn_frame, text=translate("Add"), command=self._add_new_profile, bootstyle="success-outline")
        self.add_profile_btn.pack(side=LEFT, expand=True, fill=X, padx=(0, 2))
        self.rename_profile_btn = ttk.Button(profile_btn_frame, text=translate("Rename"), command=self._rename_profile, bootstyle="info-outline")
        self.rename_profile_btn.pack(side=LEFT, expand=True, fill=X, padx=2)
        self.delete_profile_btn = ttk.Button(profile_btn_frame, text=translate("Delete"), command=self._delete_profile, bootstyle="danger-outline")
        self.delete_profile_btn.pack(side=LEFT, expand=True, fill=X, padx=(2, 0))

        endpoints_lf = ttk.Labelframe(left_pane, text=translate("API Endpoints"), padding=10)
        endpoints_lf.grid(row=1, column=0, sticky="nsew")
        endpoints_lf.grid_rowconfigure(0, weight=1)
        endpoints_lf.grid_columnconfigure(0, weight=1)
        self.labelframes["API Endpoints"] = endpoints_lf

        self.api_tree = ttk.Treeview(endpoints_lf, columns=("key",), show="tree", selectmode="browse")
        self.api_tree.grid(row=0, column=0, sticky="nsew")
        self.api_tree.bind("<<TreeviewSelect>>", self._on_api_select)

        self.reset_selected_api_btn = ttk.Button(endpoints_lf, text=translate("Reset Selected"), command=self._reset_selected_api)
        self.reset_selected_api_btn.grid(row=1, column=0, sticky="ew", pady=(5, 0))

        self.editor_lf = ttk.Labelframe(right_pane, text=translate("Edit Endpoint"), padding=15)
        self.editor_lf.grid(row=0, column=0, sticky="nsew")
        self.editor_lf.grid_columnconfigure(0, weight=1)
        self.labelframes["Edit Endpoint"] = self.editor_lf

        self.api_key_var = ttk.StringVar()
        self.api_desc_var = ttk.StringVar()
        self.api_base_url_var = ttk.StringVar()
        self.api_path_var = ttk.StringVar()
        self.api_full_url_var = ttk.StringVar()

        self.api_key_label = ttk.Label(self.editor_lf, text=f"{translate('API Key')}:", font="-weight bold")
        self.api_key_label.grid(row=0, column=0, sticky="w", pady=(0, 2))
        ttk.Entry(self.editor_lf, textvariable=self.api_key_var, state="readonly").grid(row=1, column=0, sticky="ew", pady=(0, 15))

        self.api_desc_label = ttk.Label(self.editor_lf, text=f"{translate('Description')}:")
        self.api_desc_label.grid(row=2, column=0, sticky="w", pady=(0, 2))
        ttk.Label(self.editor_lf, textvariable=self.api_desc_var, wraplength=450, justify=LEFT, bootstyle="secondary").grid(row=3, column=0, sticky="ew", pady=(0, 15))

        url_components_lf = ttk.Labelframe(self.editor_lf, text=translate("URL Components"), padding=10)
        url_components_lf.grid(row=4, column=0, sticky="ew", pady=(0, 15))
        url_components_lf.grid_columnconfigure(1, weight=1)
        self.labelframes["URL Components"] = url_components_lf

        self.api_base_url_label = ttk.Label(url_components_lf, text=translate("Base:"))
        self.api_base_url_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.api_base_url_combo = ttk.Combobox(url_components_lf, textvariable=self.api_base_url_var, values=self.base_url_options, exportselection=False)
        self.api_base_url_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        self.api_path_label = ttk.Label(url_components_lf, text=translate("Path:"))
        self.api_path_label.grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.api_path_entry = ttk.Entry(url_components_lf, textvariable=self.api_path_var)
        self.api_path_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        self.api_full_url_label = ttk.Label(self.editor_lf, text=f"{translate('Full URL Preview')}:")
        self.api_full_url_label.grid(row=5, column=0, sticky="w", pady=(0, 2))
        self.api_full_url_entry = ttk.Entry(self.editor_lf, textvariable=self.api_full_url_var, state="readonly")
        self.api_full_url_entry.grid(row=6, column=0, sticky="ew")

        self.api_base_url_var.trace_add("write", self._on_base_url_change)
        self.api_path_var.trace_add("write", self._on_path_change)

    def _is_private_ip(self, url: str) -> bool:
        try:
            match = re.match(r"^(?:https?://)?([^/:]+)", url)
            if not match: return False
            host = match.group(1)
            if host.lower() == "localhost": return True
            ip_addr = socket.gethostbyname(host)
            if ip_addr == "127.0.0.1": return True
            ip_obj = ip_address(ip_addr)
            return ip_obj.is_private or ip_obj.is_loopback
        except Exception: return True

    def _on_base_url_change(self, *args: Any) -> None:
        if self._is_loading_api_ui: return
        if not (profile_name := self.profile_combo.get()): return
        new_base_url = self.api_base_url_var.get()
        current_valid_base = _get_nested_value(CONFIG, ("api", "profiles", profile_name, "base_url"), "")

        if not new_base_url.lower().startswith("https:"):
            messagebox.showerror(translate("Invalid Input"), translate("Only HTTPS URLs are allowed for security."))
            self.api_base_url_var.set(current_valid_base)
            return
        if self._is_private_ip(new_base_url):
            messagebox.showerror(translate("Invalid Input"), translate("Local or private network URLs are not allowed for API Base URL."))
            self.api_base_url_var.set(current_valid_base)
            return

        _set_nested_value(CONFIG, ("api", "profiles", profile_name, "base_url"), new_base_url)
        if new_base_url not in self.base_url_options: self._update_base_url_options()

        if self.current_api_key_path and self.current_api_key_path[-1] not in ["base_url", "page_limit"]:
            new_path = self.api_path_var.get()
            _set_nested_value(CONFIG, self.current_api_key_path, new_base_url + new_path)
        self._update_full_url_preview()
        self.settings_tab.notify_change() # Trigger smart save check

    def _on_path_change(self, *args: Any) -> None:
        if self._is_loading_api_ui or not self.current_api_key_path: return
        key_name = self.current_api_key_path[-1]
        if key_name == "base_url": return
        new_path = self.api_path_var.get()
        if key_name == "page_limit":
            try: _set_nested_value(CONFIG, self.current_api_key_path, int(new_path))
            except ValueError: _set_nested_value(CONFIG, self.current_api_key_path, 500)
        else:
            base_url = self.api_base_url_var.get()
            _set_nested_value(CONFIG, self.current_api_key_path, base_url + new_path)
        self._update_full_url_preview()
        self.settings_tab.notify_change() # Trigger smart save check

    def _update_full_url_preview(self) -> None:
        base = self.api_base_url_var.get()
        path = self.api_path_var.get()
        self.api_full_url_var.set(base + path)

    def _setup_selectable_list(self, parent: ttk.Frame, col: int, title_key: str, items_dict: Dict[str, str], var_dict_name: str, cb_dict_name: Optional[str], config_key: str, num_cols: int = 2) -> None:
        """
        Set up a list of checkboxes, ensuring they are initialized with values from CONFIG
        AND trace changes to notify the parent SettingsTab.
        """
        lf = ttk.Labelframe(parent, text=translate(title_key), padding=10)
        lf.grid(row=0, column=col, sticky="nsew", padx=5)
        self.labelframes[title_key] = lf
        container = ttk.Frame(lf)
        container.pack(fill=BOTH, expand=YES)
        for i in range(num_cols): container.grid_columnconfigure(i, weight=1)

        select_all_var = ttk.BooleanVar()
        var_dict: Dict[str, ttk.BooleanVar] = getattr(self, var_dict_name)
        cb_dict: Optional[Dict[str, ttk.Checkbutton]] = getattr(self, cb_dict_name) if cb_dict_name else None
        
        current_config_list = CONFIG.get("display", {}).get(config_key, [])

        def on_toggle_all() -> None:
            is_checked = select_all_var.get()
            for var in var_dict.values(): var.set(is_checked)
            # Notify change after bulk update
            self.settings_tab.notify_change()

        def update_select_all_state(*args: Any) -> None:
            if not var_dict: return
            select_all_var.set(all(var.get() for var in var_dict.values()))

        setattr(self, f"_update_{var_dict_name}_select_all", update_select_all_state)
        select_all_cb = ttk.Checkbutton(container, text=translate("Select All"), variable=select_all_var, command=on_toggle_all)
        select_all_cb.grid(row=0, column=0, columnspan=num_cols, sticky="w", padx=5, pady=(0, 5))
        ttk.Separator(container, orient=HORIZONTAL).grid(row=1, column=0, columnspan=num_cols, sticky="ew", padx=5, pady=(0, 5))

        for i, (key, text) in enumerate(items_dict.items()):
            row, col_idx = (i // num_cols) + 2, i % num_cols
            
            is_selected = key in current_config_list
            var = ttk.BooleanVar(value=is_selected)
            
            var.trace_add("write", update_select_all_state)
            
            # --- CRITICAL FIX: Add trace to notify SettingsTab on change ---
            var.trace_add("write", lambda *args: self.settings_tab.notify_change())
            
            cb = ttk.Checkbutton(container, text=text, variable=var)
            cb.grid(row=row, column=col_idx, sticky="w", padx=5, pady=2)
            var_dict[key] = var
            if cb_dict is not None: cb_dict[key] = cb
        
        update_select_all_state()

    def _create_path_setting_row(self, parent: ttk.Frame, row: int, label_text_key: str, config_key_tuple: Tuple[str, ...], folder_key: str) -> None:
        label = ttk.Label(parent, text=translate(label_text_key))
        label.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)
        self.path_labels[label_text_key] = label
        entry_frame = ttk.Frame(parent)
        entry_frame.grid(row=row, column=1, sticky="ew", pady=5)
        entry_frame.grid_columnconfigure(0, weight=1)
        widget = ttk.Entry(entry_frame, width=80)
        widget.grid(row=0, column=0, sticky="ew")
        
        # --- FIX: Bind KeyRelease to notify changes ---
        widget.bind("<KeyRelease>", lambda e: self.settings_tab.notify_change())
        
        ttk.Button(entry_frame, text="📂", command=lambda w=widget: self._browse_directory(w), width=3).grid(row=0, column=1, padx=(5, 0))
        ttk.Button(entry_frame, text="🗑️", command=lambda w=widget, key=folder_key: self._clear_folder_contents(w, key), width=3).grid(row=0, column=2, padx=(2, 0))
        self.entries[config_key_tuple] = widget

    def _clear_folder_contents(self, path_entry_widget: ttk.Entry, folder_key: str) -> None:
        folder_path = path_entry_widget.get()
        if not os.path.isdir(folder_path):
            ToastNotification(title=translate("Error"), message=translate("Directory not found."), bootstyle="warning", duration=3000).show_toast()
            return

        if folder_key == "database":
            ToastNotification(title=translate("Action Moved"), message=translate("Please use the 'Database Maintenance' tab to delete databases."), bootstyle="info", duration=3000).show_toast()
            return

        if not messagebox.askyesno(translate("Confirm Deletion"), f"{translate('Clear Folder Warning').format(os.path.basename(folder_path))}"): return

        if folder_key == "log":
            threading.Thread(target=self._clear_logs_worker, args=(folder_path,), daemon=True).start()
        else:
            threading.Thread(target=self._clear_generic_folder_worker, args=(folder_path,), daemon=True).start()

    def _clear_logs_worker(self, folder_path: str) -> None:
        try:
            shutdown_file_handler()
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if os.path.isfile(item_path) and item.lower().endswith((".log", ".txt")):
                    os.unlink(item_path)
            setup_logging(level=CONFIG.get("log_level", "INFO"), log_path=CONFIG["paths"]["log"])
            self.after(0, lambda: ToastNotification(title=translate("Success"), message=f"'{os.path.basename(folder_path)}' {translate('folder cleared.')}", bootstyle="success", duration=3000).show_toast())
        except Exception as e:
            logger.error(f"Failed to clear logs: {e}")
        finally:
            self.after(100, lambda: self.main_window.log_tab.reattach_log_file())

    def _clear_generic_folder_worker(self, folder_path: str) -> None:
        try:
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if os.path.isfile(item_path): os.unlink(item_path)
                elif os.path.isdir(item_path): shutil.rmtree(item_path)
            self.after(0, lambda: ToastNotification(title=translate("Success"), message=f"'{os.path.basename(folder_path)}' {translate('folder cleared.')}", bootstyle="success", duration=3000).show_toast())
        except Exception as e:
            logger.error(f"Failed to clear folder: {e}")

    def _browse_directory(self, widget: ttk.Entry) -> None:
        path = filedialog.askdirectory(title=translate("Select Directory"))
        if path:
            widget.delete(0, "end")
            widget.insert(0, sanitize_cli_arg(path))
            # Notify change after browsing
            self.settings_tab.notify_change()

    def _create_setting_row(self, parent: ttk.Frame, grid_row: int, grid_col: int, label_text_key: str, config_key_tuple: Tuple[str, ...], tooltip_text_key: Optional[str] = None, padx: int = 5, pady: int = 5, entry_width: int = 10) -> None:
        label_frame = ttk.Frame(parent)
        label_frame.grid(row=grid_row, column=grid_col, padx=padx, pady=pady, sticky="w")
        label = ttk.Label(label_frame, text=translate(label_text_key))
        label.pack(side=LEFT, anchor="w")
        self.api_perf_labels[label_text_key] = label
        if tooltip_text_key:
            info_icon = ttk.Label(label_frame, text=" ⓘ", bootstyle="info", cursor="hand2")
            info_icon.pack(side=LEFT, anchor="w", padx=(3, 0))
            self.tooltips_widgets[tooltip_text_key] = ToolTip(info_icon, text=translate(tooltip_text_key), wraplength=300)
        widget = ttk.Entry(parent, width=entry_width)
        widget.grid(row=grid_row, column=grid_col + 1, padx=padx, pady=pady, sticky="w")
        
        # --- FIX: Bind KeyRelease to notify changes ---
        widget.bind("<KeyRelease>", lambda e: self.settings_tab.notify_change())
        
        self.entries[config_key_tuple] = widget

    def _update_base_url_options(self) -> None:
        self.base_url_options = sorted(list(set(p.get("base_url", "") for p in CONFIG["api"]["profiles"].values())))
        if hasattr(self, "api_base_url_combo"): self.api_base_url_combo["values"] = self.base_url_options

    def _populate_profile_dropdown(self) -> None:
        self._update_base_url_options()
        profiles = sorted(list(CONFIG["api"]["profiles"].keys()))
        self.profile_combo["values"] = profiles
        active_profile = CONFIG["api"]["active_profile"]
        if active_profile in profiles: self.profile_combo.set(active_profile)
        elif profiles: self.profile_combo.set(profiles[0])
        self._on_profile_select()

    def _on_profile_select(self, event: Optional[Any] = None) -> None:
        self._is_loading_api_ui = True
        profile_name = self.profile_combo.get()
        if not profile_name:
            self._is_loading_api_ui = False
            return
        CONFIG["api"]["active_profile"] = profile_name
        self._update_base_url_options()
        self._populate_api_tree()
        self.api_key_var.set("")
        self.api_desc_var.set("")
        self.api_base_url_var.set("")
        self.api_path_var.set("")
        self.api_full_url_var.set("")
        self.current_api_key_path = None
        self._is_loading_api_ui = False
        if hasattr(self, "settings_tab"): self.settings_tab.notify_change()

    def _populate_api_tree(self) -> None:
        for i in self.api_tree.get_children(): self.api_tree.delete(i)
        api_sections = {"Kaspa API Endpoints": "endpoints", "Explorer URLs": "explorer", "External APIs": "external"}
        base_url_parent = self.api_tree.insert("", "end", text="Base URL", open=True, iid="base_url_cat")
        self.api_tree.insert(base_url_parent, "end", text="Base URL", values=("base_url", "base_url"))
        self.api_tree.insert(base_url_parent, "end", text="Page Limit", values=("page_limit", "page_limit"))
        profile_name = self.profile_combo.get()
        current_profile = CONFIG.get("api", {}).get("profiles", {}).get(profile_name, DEFAULT_CONFIG["api"]["profiles"]["Default"])
        for section_title, section_key in api_sections.items():
            parent = self.api_tree.insert("", "end", text=translate(section_title), open=True, iid=section_key)
            for key in sorted(current_profile.get(section_key, {}).keys()):
                self.api_tree.insert(parent, "end", text=key, values=(key, section_key))

    def _on_api_select(self, event: Optional[Any] = None) -> None:
        self._is_loading_api_ui = True
        sel = self.api_tree.selection()
        if not sel:
            self._is_loading_api_ui = False
            return
        item = self.api_tree.item(sel[0])
        if not item["values"]:
            self._is_loading_api_ui = False
            return
        key, section_key = item["values"][0], item["values"][1]
        profile_name = self.profile_combo.get()
        self.api_key_var.set(key)
        self.api_desc_var.set(translate(f"Tooltip_api_{key}"))
        self.editor_lf.config(text=f"{translate('Edit Endpoint')}: {key}")
        self.api_base_url_combo.config(state="normal")
        self.api_path_entry.config(state=NORMAL)
        
        api_config = CONFIG["api"]["profiles"][profile_name]
        if section_key == "base_url":
            self.current_api_key_path = ("api", "profiles", profile_name, "base_url")
            self.api_base_url_var.set(api_config.get("base_url", ""))
            self.api_path_entry.config(state=DISABLED)
            self.api_path_var.set("")
        elif section_key == "page_limit":
            self.current_api_key_path = ("api", "profiles", profile_name, "page_limit")
            self.api_base_url_var.set(api_config.get("base_url", ""))
            self.api_base_url_combo.config(state=DISABLED)
            self.api_path_var.set(str(api_config.get("page_limit", 500)))
        else:
            self.current_api_key_path = ("api", "profiles", profile_name, section_key, key)
            full_url = _get_nested_value(api_config, (section_key, key), "")
            base_url = api_config.get("base_url", "")
            path = full_url[len(base_url):] if base_url and full_url.startswith(base_url) else full_url
            self.api_base_url_var.set(base_url)
            self.api_path_var.set(path)
        self._update_full_url_preview()
        self._is_loading_api_ui = False

    def _add_new_profile(self) -> None:
        new_name = askstring(translate("Add"), translate("Name:"))
        if new_name and new_name.strip() and new_name not in CONFIG["api"]["profiles"]:
            CONFIG["api"]["profiles"][new_name] = json.loads(json.dumps(DEFAULT_CONFIG["api"]["profiles"]["Default"]))
            self._populate_profile_dropdown()
            self.profile_combo.set(new_name)
            self.settings_tab.notify_change()

    def _rename_profile(self) -> None:
        old_name = self.profile_combo.get()
        if not old_name or old_name == "Default":
            messagebox.showwarning(translate("Rename"), translate("Cannot rename default profile"))
            return
        new_name = askstring(translate("Rename"), f"{translate('Name:')}:", initialvalue=old_name)
        if new_name and new_name.strip() and new_name != old_name and new_name not in CONFIG["api"]["profiles"]:
            CONFIG["api"]["profiles"][new_name] = CONFIG["api"]["profiles"].pop(old_name)
            if CONFIG["api"]["active_profile"] == old_name: CONFIG["api"]["active_profile"] = new_name
            self._populate_profile_dropdown()
            self.settings_tab.notify_change()

    def _delete_profile(self) -> None:
        profile_name = self.profile_combo.get()
        if not profile_name or profile_name == "Default":
            messagebox.showwarning(translate("Delete"), translate("Cannot delete default profile"))
            return
        if messagebox.askyesno(translate("Delete"), f"{translate('Delete')} '{profile_name}'?"):
            del CONFIG["api"]["profiles"][profile_name]
            CONFIG["api"]["active_profile"] = "Default"
            self._populate_profile_dropdown()
            self.settings_tab.notify_change()

    def _reset_selected_api(self) -> None:
        if self.current_api_key_path:
            default_value = _get_nested_value(DEFAULT_CONFIG, ("api", "profiles", "Default") + self.current_api_key_path[3:], "")
            base_url_default = DEFAULT_CONFIG["api"]["profiles"]["Default"]["base_url"]
            self._is_loading_api_ui = True
            if self.current_api_key_path[-1] == "base_url": self.api_base_url_var.set(default_value)
            elif self.current_api_key_path[-1] == "page_limit": self.api_path_var.set(str(default_value))
            else:
                self.api_base_url_var.set(base_url_default)
                path = default_value[len(base_url_default):] if default_value.startswith(base_url_default) else default_value
                self.api_path_var.set(path)
            self._is_loading_api_ui = False
            self._on_base_url_change()
            self._on_path_change()
            self.settings_tab.notify_change()

    def load_settings(self, config: Dict[str, Any]) -> None:
        for key_tuple, widget in self.entries.items():
            value = _get_nested_value(config, key_tuple)
            if isinstance(widget, ttk.BooleanVar): widget.set(bool(value))
            elif isinstance(widget, ttk.StringVar): widget.set(str(value if value is not None else ""))
            elif isinstance(widget, ttk.Entry):
                widget.delete(0, "end")
                widget.insert(0, str(value if value is not None else ""))
        
        if hasattr(self, "_update_lang_vars_select_all"): self._update_lang_vars_select_all()
        if hasattr(self, "_update_currency_vars_select_all"): self._update_currency_vars_select_all()
        if hasattr(self, "_update_tab_vars_select_all"): self._update_tab_vars_select_all()
        self._populate_profile_dropdown()

    def re_translate(self) -> None:
        for i, key in enumerate(["General", "API Settings", "Performance Settings"]): self.inner_notebook.tab(i, text=translate(key))
        for d in [self.path_labels, self.api_perf_labels, self.labelframes]:
            for key, widget in d.items(): widget.config(text=translate(key))
        for key, tooltip in self.tooltips_widgets.items(): tooltip.text = translate(key)
        
        if hasattr(self, "auto_refresh_cb"): self.auto_refresh_cb.config(text=translate("Enable Auto-Refresh"))
        if hasattr(self, "autostart_cb"): self.autostart_cb.config(text=translate("Start with Windows"))
        if hasattr(self, "log_level_label"): self.log_level_label.config(text=f"{translate('Logging Level')}:")
        
        if hasattr(self, "general_tab"):
            for widget in self.general_tab.winfo_children(): widget.destroy()
            self._build_general_settings(self.general_tab)
            self.load_settings(self.config_manager.get_config())

        # Translate API Tab elements
        self.editor_lf.config(text=translate("Edit Endpoint"))
        self.api_key_label.config(text=f"{translate('API Key')}:")
        self.api_desc_label.config(text=f"{translate('Description')}:")
        self.api_base_url_label.config(text=translate("Base:"))
        self.api_path_label.config(text=translate("Path:"))
        self.api_full_url_label.config(text=f"{translate('Full URL Preview')}:")
        self.add_profile_btn.config(text=translate("Add"))
        self.rename_profile_btn.config(text=translate("Rename"))
        self.delete_profile_btn.config(text=translate("Delete"))
        self.reset_selected_api_btn.config(text=translate("Reset Selected"))
        if hasattr(self, "profile_combo"): self._populate_profile_dropdown()
        if hasattr(self, "api_tree"): self._populate_api_tree()
