#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contains the Controller (logic and state) for the BridgeInstanceTab (View).
This file handles all business logic, state management, and subprocess
interactions for a single ks_bridge instance.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)

import psutil
import ttkbootstrap as ttk
from ttkbootstrap.constants import SUCCESS
from ttkbootstrap.toast import ToastNotification

from src.config.config import CONFIG
from src.gui.updater import (
    DownloadProgressWindow,
    GitHubUpdater,
    VersionChecker,
)
from src.utils.i18n import translate
from src.utils.validation import (
    _sanitize_for_logging,
    sanitize_cli_arg,
    validate_ip_port,
)

if sys.platform == "win32":
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        logging.error("ctypes or wintypes not found. Job Object support disabled.")
        ctypes = None  # type: ignore
        wintypes = None  # type: ignore
else:
    ctypes = None
    wintypes = None

if TYPE_CHECKING:
    from src.gui.config_manager import ConfigManager
    from src.gui.main_window import MainWindow
    from src.gui.tabs.kaspa_bridge_tab import (
        BridgeInstanceTab,
        KaspaBridgeTab,
    )

logger = logging.getLogger(__name__)


class BridgeInstanceController:
    """
    The Controller class for a single Bridge Instance Tab.
    Manages all state and logic, interacting with BridgeInstanceTab (View).
    """

    view: BridgeInstanceTab
    main_window: MainWindow
    config_manager: ConfigManager
    instance_id: str
    config_key: str
    main_bridge_tab: Optional[KaspaBridgeTab]
    bridge_process: Optional[subprocess.Popen[bytes]]
    version_checker: Optional[VersionChecker]
    first_activation_done: bool
    is_updating: bool
    bridge_dir: str
    bridge_exe_path: str
    config_yaml_path: str
    running_command_str: str
    external_process_pids: List[int]
    all_vars_list: List[Tuple[Any, str, Any]]
    key_to_enabled_var_map: Dict[str, ttk.BooleanVar]
    flag_key_to_enabled_var_map: Dict[str, ttk.BooleanVar]
    _stop_requested: bool

    # TK Variables
    kaspa_addr_var: Tuple[ttk.StringVar, ttk.StringVar]
    stratum_port_var: ttk.StringVar
    prom_port_var: ttk.StringVar
    hcp_var: ttk.StringVar
    min_diff_var: ttk.StringVar
    shares_per_min_var: ttk.StringVar
    blockwait_var: ttk.StringVar
    extranonce_var: ttk.StringVar
    custom_exe_path_var: ttk.StringVar
    custom_config_path_var: ttk.StringVar
    custom_url_var: ttk.StringVar
    custom_url_exe_path_var: ttk.StringVar
    custom_url_config_path_var: ttk.StringVar
    bridge_download_url_var: ttk.StringVar
    startup_delay_var: ttk.IntVar
    auto_reconnect_var: ttk.BooleanVar
    command_preview_var: ttk.StringVar
    local_bridge_version_var: ttk.StringVar
    latest_bridge_version_var: ttk.StringVar
    latest_bridge_date_var: ttk.StringVar
    vardiff_var: ttk.StringVar
    pow2clamp_var: ttk.StringVar
    log_file_var: ttk.StringVar
    console_stats_var: ttk.StringVar
    vardiff_stats_var: ttk.StringVar
    log_font_size_var: ttk.IntVar
    autostart_var: ttk.BooleanVar
    use_custom_exe_var: ttk.BooleanVar
    use_custom_config_var: ttk.BooleanVar
    use_custom_url_var: ttk.BooleanVar
    kaspa_addr_enabled_var: ttk.BooleanVar
    stratum_port_enabled_var: ttk.BooleanVar
    prom_port_enabled_var: ttk.BooleanVar
    hcp_enabled_var: ttk.BooleanVar
    min_diff_enabled_var: ttk.BooleanVar
    shares_per_min_enabled_var: ttk.BooleanVar
    blockwait_enabled_var: ttk.BooleanVar
    extranonce_enabled_var: ttk.BooleanVar
    vardiff_enabled_var: ttk.BooleanVar
    pow2clamp_enabled_var: ttk.BooleanVar
    log_file_enabled_var: ttk.BooleanVar
    console_stats_enabled_var: ttk.BooleanVar
    vardiff_stats_enabled_var: ttk.BooleanVar

    def __init__(
        self,
        view: BridgeInstanceTab,
        main_window: MainWindow,
        config_manager: ConfigManager,
        instance_id: str,
        main_bridge_tab: Optional[KaspaBridgeTab] = None,
    ) -> None:
        """Initializes the BridgeInstanceController."""
        self.view = view
        self.main_window = main_window
        self.config_manager = config_manager
        self.instance_id = instance_id
        self.config_key = f"kaspa_bridge{instance_id}"
        self.main_bridge_tab = main_bridge_tab

        self.bridge_process = None
        self.version_checker = None
        self.first_activation_done = False
        self.is_updating = False
        self.running_command_str = ""
        self.external_process_pids = []
        self._stop_requested = False

        base_path = os.path.abspath(
            os.getenv("LOCALAPPDATA", CONFIG["paths"]["database"])
        )
        self.bridge_dir = os.path.join(
            base_path,
            "KaspaGateway",
            f"bin_bridge{instance_id}",
        )
        os.makedirs(self.bridge_dir, exist_ok=True)
        self.bridge_exe_path = os.path.join(self.bridge_dir, "ks_bridge.exe")
        self.config_yaml_path = os.path.join(self.bridge_dir, "config.yaml")

        self._init_variables()
        self._load_settings()
        self._update_paths_from_settings()

    def _bool_to_str(self, b_val: bool) -> str:
        """Converts a boolean to its string representation."""
        return "true" if b_val else "false"

    def _str_to_bool(self, s_val: str) -> bool:
        """Converts a string from radio buttons back to a boolean."""
        return s_val == "true"

    def _init_variables(self) -> None:
        """Initialize all ttk variables for the GUI controls."""
        default_stratum = (
            ":5555" if self.instance_id == "_1" else ":5556"
        )
        default_prom = ":2112" if self.instance_id == "_1" else ":2113"

        self.kaspa_addr_var = (
            ttk.StringVar(value="127.0.0.1"),
            ttk.StringVar(value="16110"),
        )
        self.stratum_port_var = ttk.StringVar(value=default_stratum)
        self.prom_port_var = ttk.StringVar(value=default_prom)
        self.hcp_var = ttk.StringVar(value="")
        self.min_diff_var = ttk.StringVar(value="4096")
        self.shares_per_min_var = ttk.StringVar(value="20")
        self.blockwait_var = ttk.StringVar(value="250ms")
        self.extranonce_var = ttk.StringVar(
            value="0" if self.instance_id == "_1" else "2"
        )
        self.custom_exe_path_var = ttk.StringVar(value="")
        self.custom_config_path_var = ttk.StringVar(value="")
        self.custom_url_var = ttk.StringVar(value="")
        self.custom_url_exe_path_var = ttk.StringVar(
            value="ks_bridge/ks_bridge.exe"
        )
        self.custom_url_config_path_var = ttk.StringVar(
            value="ks_bridge/config.yaml"
        )

        self.bridge_download_url_var = ttk.StringVar(
            value="https://api.github.com/repos/aglov413/kaspa-stratum-bridge/releases/latest"
        )

        self.startup_delay_var = ttk.IntVar(value=0)
        self.auto_reconnect_var = ttk.BooleanVar(value=False)

        self.command_preview_var = ttk.StringVar()
        self.local_bridge_version_var = ttk.StringVar(
            value=f"{translate('Local Version')}: N/A"
        )
        self.latest_bridge_version_var = ttk.StringVar(
            value=f"{translate('Latest Version')}: N/A"
        )
        self.latest_bridge_date_var = ttk.StringVar(
            value=f"{translate('Updated')}: N/A"
        )

        self.vardiff_var = ttk.StringVar(value=self._bool_to_str(True))
        self.pow2clamp_var = ttk.StringVar(value=self._bool_to_str(True))
        self.log_file_var = ttk.StringVar(value=self._bool_to_str(True))
        self.console_stats_var = ttk.StringVar(value=self._bool_to_str(True))
        self.vardiff_stats_var = ttk.StringVar(value=self._bool_to_str(True))

        self.log_font_size_var = ttk.IntVar(value=9)
        self.autostart_var = ttk.BooleanVar(value=False)
        self.use_custom_exe_var = ttk.BooleanVar(value=False)
        self.use_custom_config_var = ttk.BooleanVar(value=False)
        self.use_custom_url_var = ttk.BooleanVar(value=False)
        self.kaspa_addr_enabled_var = ttk.BooleanVar(value=True)
        self.stratum_port_enabled_var = ttk.BooleanVar(value=True)
        self.prom_port_enabled_var = ttk.BooleanVar(value=True)
        self.hcp_enabled_var = ttk.BooleanVar(value=False)
        self.min_diff_enabled_var = ttk.BooleanVar(value=True)
        self.shares_per_min_enabled_var = ttk.BooleanVar(value=True)
        self.blockwait_enabled_var = ttk.BooleanVar(value=True)
        self.extranonce_enabled_var = ttk.BooleanVar(value=True)
        self.vardiff_enabled_var = ttk.BooleanVar(value=True)
        self.pow2clamp_enabled_var = ttk.BooleanVar(value=True)
        self.log_file_enabled_var = ttk.BooleanVar(value=True)
        self.console_stats_enabled_var = ttk.BooleanVar(value=True)
        self.vardiff_stats_enabled_var = ttk.BooleanVar(value=True)

        self.version_checker = VersionChecker(
            asset_name="ks_bridge.exe",
            version_var=self.latest_bridge_version_var,
            date_var=self.latest_bridge_date_var,
            log_callback=self.log_message,
            repo_url="https://api.github.com/repos/aglov413/kaspa-stratum-bridge/releases/latest",
        )

        self.all_vars_list = [
            (self.kaspa_addr_var, "kaspa_addr_var", ("127.0.0.1", "16110")),
            (self.stratum_port_var, "stratum_port_var", default_stratum),
            (self.prom_port_var, "prom_port_var", default_prom),
            (self.hcp_var, "hcp_var", ""),
            (self.min_diff_var, "min_diff_var", "4096"),
            (self.shares_per_min_var, "shares_per_min_var", "20"),
            (self.vardiff_var, "vardiff_var", True),
            (self.pow2clamp_var, "pow2clamp_var", True),
            (self.log_file_var, "log_file_var", True),
            (self.console_stats_var, "console_stats_var", True),
            (self.vardiff_stats_var, "vardiff_stats_var", True),
            (self.blockwait_var, "blockwait_var", "250ms"),
            (
                self.bridge_download_url_var,
                "bridge_download_url_var",
                "https://api.github.com/repos/aglov413/kaspa-stratum-bridge/releases/latest",
            ),
            (self.startup_delay_var, "startup_delay_var", 0),
            (self.auto_reconnect_var, "auto_reconnect_var", False),
            (
                self.extranonce_var,
                "extranonce_var",
                "0" if self.instance_id == "_1" else "2",
            ),
            (self.log_font_size_var, "log_font_size_var", 9),
            (self.autostart_var, "autostart_var", False),
            (self.use_custom_exe_var, "use_custom_exe_var", False),
            (self.custom_exe_path_var, "custom_exe_path_var", ""),
            (self.use_custom_config_var, "use_custom_config_var", False),
            (self.custom_config_path_var, "custom_config_path_var", ""),
            (self.use_custom_url_var, "use_custom_url_var", False),
            (self.custom_url_var, "custom_url_var", ""),
            (
                self.custom_url_exe_path_var,
                "custom_url_exe_path_var",
                "ks_bridge/ks_bridge.exe",
            ),
            (
                self.custom_url_config_path_var,
                "custom_url_config_path_var",
                "ks_bridge/config.yaml",
            ),
            (self.kaspa_addr_enabled_var, "kaspa_addr_enabled_var", True),
            (self.stratum_port_enabled_var, "stratum_port_enabled_var", True),
            (self.prom_port_enabled_var, "prom_port_enabled_var", True),
            (self.hcp_enabled_var, "hcp_enabled_var", False),
            (self.min_diff_enabled_var, "min_diff_enabled_var", True),
            (
                self.shares_per_min_enabled_var,
                "shares_per_min_enabled_var",
                True,
            ),
            (self.blockwait_enabled_var, "blockwait_enabled_var", True),
            (self.extranonce_enabled_var, "extranonce_enabled_var", True),
            (self.vardiff_enabled_var, "vardiff_enabled_var", True),
            (self.pow2clamp_enabled_var, "pow2clamp_enabled_var", True),
            (self.log_file_enabled_var, "log_file_enabled_var", True),
            (
                self.console_stats_enabled_var,
                "console_stats_enabled_var",
                True,
            ),
            (
                self.vardiff_stats_enabled_var,
                "vardiff_stats_enabled_var",
                True,
            ),
        ]

        self.key_to_enabled_var_map = {
            "kaspa_addr_var": self.kaspa_addr_enabled_var,
            "stratum_port_var": self.stratum_port_enabled_var,
            "prom_port_var": self.prom_port_enabled_var,
            "hcp_var": self.hcp_enabled_var,
            "min_diff_var": self.min_diff_enabled_var,
            "shares_per_min_var": self.shares_per_min_enabled_var,
            "blockwait_var": self.blockwait_enabled_var,
            "extranonce_var": self.extranonce_enabled_var,
        }

        self.flag_key_to_enabled_var_map = {
            "vardiff_var": self.vardiff_enabled_var,
            "pow2clamp_var": self.pow2clamp_enabled_var,
            "log_file_var": self.log_file_enabled_var,
            "console_stats_var": self.console_stats_enabled_var,
            "vardiff_stats_var": self.vardiff_stats_enabled_var,
        }

    def _load_settings(self) -> None:
        """Load settings from the config manager into the ttk variables."""
        bridge_config = self.config_manager.get_config().get(self.config_key, {})

        for var_tuple, key, default in self.all_vars_list:
            saved_value = bridge_config.get(key, default)
            try:
                if key == "kaspa_addr_var":
                    self._load_kaspa_addr(saved_value, var_tuple, default)
                elif key in self.flag_key_to_enabled_var_map:
                    var_tuple.set(
                        self._bool_to_str(saved_value)
                        if isinstance(saved_value, bool)
                        else str(saved_value)
                    )
                elif isinstance(
                    var_tuple, (ttk.StringVar, ttk.BooleanVar, ttk.IntVar)
                ):
                    var_tuple.set(saved_value)
            except Exception as e:
                logger.error(
                    f"Error loading setting for {key}: {e}. Resetting to default."
                )
                self._set_var_to_default(var_tuple, default)

        self.view.after(100, self.update_command_preview)

    def _load_kaspa_addr(
        self,
        saved_value: Any,
        var_tuple: Tuple[ttk.StringVar, ttk.StringVar],
        default: Tuple[str, str],
    ) -> None:
        """Helper to load the kaspa_addr_var tuple."""
        if isinstance(saved_value, (list, tuple)) and len(saved_value) == 2:
            var_tuple[0].set(saved_value[0])
            var_tuple[1].set(saved_value[1])
        elif isinstance(saved_value, str):
            ip, port = validate_ip_port(saved_value) or default
            var_tuple[0].set(ip)
            var_tuple[1].set(port)
        else:
            self._set_var_to_default(var_tuple, default)

    def _set_var_to_default(self, var_tuple: Any, default: Any) -> None:
        """Helper to reset a variable to its default value."""
        if isinstance(var_tuple, tuple):
            var_tuple[0].set(default[0])
            var_tuple[1].set(default[1])
        else:
            var_tuple.set(default)

    def _save_settings(self, *args: Any) -> None:
        """Save the current state of ttk variables to the config manager."""
        bridge_config = self.config_manager.get_config().get(self.config_key, {})

        for var_tuple, key, _ in self.all_vars_list:
            value_to_save = self._get_var_value_for_saving(var_tuple, key)
            if value_to_save is not None:
                bridge_config[key] = value_to_save

        self.config_manager.get_config()[self.config_key] = bridge_config
        self.config_manager.save_config(self.config_manager.get_config())

    def _get_var_value_for_saving(self, var_tuple: Any, key: str) -> Any:
        """Gets the serializable value from a ttk variable."""
        if key in self.flag_key_to_enabled_var_map:
            return self._str_to_bool(var_tuple.get())
        if isinstance(var_tuple, (ttk.StringVar, ttk.BooleanVar, ttk.IntVar)):
            return var_tuple.get()
        if isinstance(var_tuple, tuple) and len(var_tuple) == 2:
            ip_val = sanitize_cli_arg(var_tuple[0].get())
            port_val = sanitize_cli_arg(var_tuple[1].get())
            return (ip_val, port_val)
        return None

    def save_download_url(self, new_url: str) -> None:
        """Saves the new download URL to the config."""
        self.bridge_download_url_var.set(new_url)
        self._save_settings()
        ToastNotification(
            title=translate("Success"),
            message=translate("Download URL saved as default."),
            bootstyle=SUCCESS,
            duration=3000,
        ).show_toast()

    def _save_and_update_preview(self, *args: Any) -> None:
        """Wrapper to update preview and save settings, for use in tracers."""
        self.update_command_preview()
        self._save_settings()

        is_running = self._is_bridge_running()
        new_command = self.command_preview_var.get()

        try:
            button_state = "normal" if is_running and new_command != self.running_command_str else "disabled"
            self.view.apply_restart_button.config(state=button_state)
        except tk.TclError:
            pass

        self._update_update_button_logic(True)

    def _add_tracers(self) -> None:
        """Add 'write' tracers to all variables to auto-save and update."""
        traced_vars = self.all_vars_list
        excluded_keys = {
            "use_custom_exe_var",
            "use_custom_config_var",
            "use_custom_url_var",
            "bridge_download_url_var",
        }

        for var_tuple, key, _ in traced_vars:
            if key in excluded_keys:
                continue

            if isinstance(var_tuple, tuple) and len(var_tuple) == 2:
                var_tuple[0].trace_add("write", self._save_and_update_preview)
                var_tuple[1].trace_add("write", self._save_and_update_preview)
            elif isinstance(var_tuple, (ttk.StringVar, ttk.BooleanVar, ttk.IntVar)):
                var_tuple.trace_add("write", self._save_and_update_preview)

        for key, enabled_var in self.flag_key_to_enabled_var_map.items():
            value_var = next(
                (v[0] for v in self.all_vars_list if v[1] == key), None
            )
            if value_var and isinstance(value_var, ttk.StringVar):
                enabled_var.trace_add(
                    "write",
                    self._create_sync_callback(enabled_var, value_var),
                )

        self.use_custom_exe_var.trace_add("write", self._on_custom_exe_toggled)
        self.use_custom_config_var.trace_add(
            "write", self._on_custom_config_toggled
        )
        self.use_custom_url_var.trace_add("write", self._on_custom_url_toggled)

    def _create_sync_callback(
        self, enabled_var: ttk.BooleanVar, value_var: ttk.StringVar
    ) -> Callable[..., None]:
        """Creates a closure for the trace callback."""
        def sync_checkbox_to_radio(*args: Any) -> None:
            if enabled_var.get():
                value_var.set("true")

        return sync_checkbox_to_radio

    def reset_to_defaults(self) -> None:
        """Reset all options in this tab to their default values."""
        if not messagebox.askyesno(
            translate("Confirm Reset"),
            translate(
                "Are you sure you want to reset all options to their defaults? This cannot be undone."
            ),
        ):
            return

        logger.info(f"Resetting bridge {self.instance_id} options to default.")

        for var_tuple, key, default in self.all_vars_list:
            if key in self.flag_key_to_enabled_var_map:
                var_tuple.set(self._bool_to_str(default))
            else:
                self._set_var_to_default(var_tuple, default)

        self._save_and_update_preview()
        self._check_local_bridge_version()

        ToastNotification(
            title=translate("Success"),
            message=translate("Bridge options have been reset to default."),
            bootstyle=SUCCESS,
            duration=3000,
        ).show_toast()

    def _update_paths_from_settings(self) -> None:
        """Updates internal path variables based on current settings."""
        if self.use_custom_exe_var.get() and self.custom_exe_path_var.get():
            self.bridge_exe_path = os.path.abspath(self.custom_exe_path_var.get())
        else:
            self.bridge_exe_path = os.path.join(self.bridge_dir, "ks_bridge.exe")

        if self.use_custom_config_var.get() and self.custom_config_path_var.get():
            self.config_yaml_path = os.path.abspath(
                self.custom_config_path_var.get()
            )
        else:
            self.config_yaml_path = os.path.join(self.bridge_dir, "config.yaml")

    def update_command_preview(self, *args: Any) -> None:
        """Update the command preview text box based on current settings."""
        self._update_paths_from_settings()

        command_list = self.build_args_from_settings()
        command_str = " ".join(command_list)
        self.command_preview_var.set(command_str)

        if hasattr(self.view, "command_preview_text"):
            try:
                self.view.command_preview_text.text.config(state="normal")
                self.view.command_preview_text.text.delete("1.0", tk.END)
                self.view.command_preview_text.text.insert("1.0", command_str)
                self.view.command_preview_text.text.config(state="disabled")
            except tk.TclError:
                pass

    def copy_command_to_clipboard(self) -> None:
        """Copy the generated command string to the user's clipboard."""
        command = self.command_preview_var.get().strip()
        if command:
            self.main_window.clipboard_clear()
            self.main_window.clipboard_append(command)
            ToastNotification(
                title=translate("Success"),
                message=translate("Command copied to clipboard."),
                bootstyle=SUCCESS,
                duration=3000,
            ).show_toast()

    def autostart_if_enabled(self, is_autostart: bool = False) -> None:
        """Checks if autostart is enabled and triggers the start sequence."""
        if self.autostart_var.get():
            delay_sec = self.startup_delay_var.get()
            if is_autostart and delay_sec > 0:
                logger.info(
                    f"Auto-starting Bridge {self.instance_id} in {delay_sec} seconds..."
                )
                self.log_message(
                    f"Waiting {delay_sec}s for Node to initialize...", "INFO"
                )
                self.view.after(
                    delay_sec * 1000, lambda: self.start_bridge(is_autostart=False)
                )
            else:
                logger.info(f"Auto-starting Bridge {self.instance_id} immediately...")
                self.start_bridge(is_autostart)

    def _update_update_button_logic(self, *args: Any) -> None:
        """Updates the Update/Download button text AND state."""
        if not hasattr(self.view, "update_button"):
            return

        self.update_command_preview()

        is_running = self._is_bridge_running()
        file_exists = os.path.exists(self.bridge_exe_path) and os.path.exists(
            self.config_yaml_path
        )
        is_custom_url = self.use_custom_url_var.get()
        is_custom_exe = self.use_custom_exe_var.get()

        if is_custom_url:
            button_text = translate("Download File")
        elif not file_exists:
            button_text = translate("Download Bridge")
        else:
            button_text = translate("Update Bridge")
        self.view.update_button.config(text=button_text)

        is_app_busy = self.is_updating
        is_globally_active = args[0] if args and isinstance(args[0], bool) else True

        if is_app_busy or is_custom_exe or not is_globally_active or is_running:
            self.view.update_button.config(state="disabled")
        else:
            self.view.update_button.config(state="normal")

    def _on_custom_exe_toggled(self, *args: Any) -> None:
        """Tracer for 'Use Custom ks_bridge.exe' checkbox."""
        self.view.toggle_entry_state(
            self.use_custom_exe_var,
            [self.view.exe_entry, self.view.exe_browse],
        )

        if self.use_custom_exe_var.get():
            self.use_custom_config_var.set(True)
            self.use_custom_url_var.set(False)
        else:
            self.use_custom_config_var.set(False)

        self._save_and_update_preview()
        self.set_controls_state(True)

    def _on_custom_config_toggled(self, *args: Any) -> None:
        """Tracer for 'Use Custom config.yaml' checkbox."""
        self.view.toggle_entry_state(
            self.use_custom_config_var,
            [self.view.config_entry, self.view.config_browse],
        )

        if self.use_custom_config_var.get():
            self.use_custom_exe_var.set(True)
            self.use_custom_url_var.set(False)
        else:
            self.use_custom_exe_var.set(False)

        self._save_and_update_preview()
        self.set_controls_state(True)

    def _on_custom_url_toggled(self, *args: Any) -> None:
        """Tracer for 'Use Custom Download URL' checkbox."""
        custom_url_widgets = [
            self.view.url_entry,
            self.view.url_exe_path_label,
            self.view.url_exe_path_entry,
            self.view.url_config_path_label,
            self.view.url_config_path_entry,
        ]
        self.view.toggle_entry_state(self.use_custom_url_var, custom_url_widgets)

        if self.use_custom_url_var.get():
            self.use_custom_exe_var.set(False)
            self.use_custom_config_var.set(False)

        self._save_and_update_preview()
        self.set_controls_state(True)

    def _prompt_for_download_path_and_start(self) -> None:
        """Shows the Yes/No/Cancel prompt to select a download path."""
        default_path = self.bridge_dir or os.getcwd()

        if self.use_custom_url_var.get():
            msg = f"{translate('Download from custom URL?')}"
        else:
            msg = translate(
                "ks_bridge.exe or config.yaml not found. These components are required to run the bridge. Would you like to download them now?"
            )
        
        msg_template = (
            f"{msg}\n\n"
            f"- {translate('Click Yes to download to default location:')}\n{default_path}\n\n"
            f"- {translate('Click No to select a custom location.')}"
        )

        user_choice = messagebox.askyesnocancel(
            translate("Update Bridge"), msg_template
        )

        chosen_path = None
        if user_choice is True:
            chosen_path = default_path
        elif user_choice is False:
            chosen_path = filedialog.askdirectory(
                title=translate("Select Download Location"),
                initialdir=default_path,
            )
        
        if chosen_path:
            self.bridge_dir = chosen_path
            self.bridge_exe_path = os.path.join(self.bridge_dir, "ks_bridge.exe")
            self.config_yaml_path = os.path.join(self.bridge_dir, "config.yaml")
            self.start_bridge_update()

        self._update_update_button_logic()

    def _on_update_button_pressed(self) -> None:
        """Command for the Update/Download button."""
        is_custom_url = self.use_custom_url_var.get()
        file_exists = os.path.exists(self.bridge_exe_path) and os.path.exists(
            self.config_yaml_path
        )
        is_download_action = is_custom_url or not file_exists

        if is_download_action:
            self._prompt_for_download_path_and_start()
        else:
            self.start_bridge_update()

    def start_bridge_update(self) -> None:
        """Begin the download/update process for the bridge binaries."""
        log_text = (
            translate("Download File")
            if self.use_custom_url_var.get()
            else translate("Update Bridge")
        )
        self.log_message(f"--- {log_text} ---", "INFO")

        self.is_updating = True
        self.set_controls_state(False)
        self.update_command_preview()

        repo_url = self.bridge_download_url_var.get().strip()
        asset_name_pattern = r"ks_bridge-v[\d\.]+(-dev)?\.zip$"
        target_exe = "ks_bridge/ks_bridge.exe"
        target_config = "ks_bridge/config.yaml"

        if self.use_custom_url_var.get() and self.custom_url_var.get():
            repo_url = self.custom_url_var.get()
            asset_name_pattern = r"\.zip$"
            target_exe = self.custom_url_exe_path_var.get()
            target_config = self.custom_url_config_path_var.get()

            if not self._validate_custom_url_paths(target_exe, target_config):
                self.is_updating = False
                self.set_controls_state(True)
                return
            if not self._validate_custom_url(repo_url):
                self.is_updating = False
                self.set_controls_state(True)
                return

        multi_target_files = [
            {"target_in_zip": target_exe, "local_path": self.bridge_exe_path},
            {"target_in_zip": target_config, "local_path": self.config_yaml_path},
        ]

        progress_window = DownloadProgressWindow(
            self.main_window, title=translate("Update Bridge")
        )

        threading.Thread(
            target=self.run_update_thread,
            args=(progress_window, repo_url, asset_name_pattern, multi_target_files),
            daemon=True,
        ).start()

    def _validate_custom_url_paths(self, target_exe: str, target_config: str) -> bool:
        """Validates paths provided for custom URL download."""
        if (
            not re.match(r"^[\w\.\-/]+$", target_exe)
            or ".." in target_exe
            or not re.match(r"^[\w\.\-/]+$", target_config)
            or ".." in target_config
        ):
            messagebox.showerror(
                translate("Invalid Input"), "Invalid file path in zip."
            )
            return False
        return True

    def _validate_custom_url(self, repo_url: str) -> bool:
        """Validates the custom URL itself."""
        if not repo_url.endswith(".zip") and "api.github.com" not in repo_url:
            messagebox.showerror(
                translate("Invalid Input"),
                translate("Custom URL must be a .zip file or a GitHub API URL."),
            )
            return False
        return True

    def run_update_thread(
        self,
        progress_window: DownloadProgressWindow,
        repo_url: str,
        asset_name_pattern: str,
        multi_target_files: List[Dict[str, str]],
    ) -> None:
        """Worker thread function to run the GitHubUpdater."""
        try:
            updater = GitHubUpdater(
                repo_url=repo_url,
                asset_name_pattern=asset_name_pattern,
                log_callback=self.log_message,
                is_running_check=self._is_bridge_running,
                multi_target_files=multi_target_files,
                local_path=self.bridge_exe_path,
                success_callback=self._check_local_bridge_version,
                show_success_popup=False,
                cancel_event=progress_window.cancel_event,
                progress_window=progress_window,
            )
            updater.run_update()
        except Exception as e:
            if "Download cancelled" not in str(e):
                self.log_message(
                    f"Update thread failed: {_sanitize_for_logging(e)}", "ERROR"
                )
        finally:
            self.is_updating = False
            if self.view.winfo_exists():
                self.view.after(0, self.set_controls_state, True)

    def _check_local_bridge_version(self) -> None:
        """Checks for the local bridge version file and updates the label."""
        try:
            is_custom_path_active = self.use_custom_exe_var.get()
        except tk.TclError:
            return

        def worker() -> None:
            """Worker thread to perform file I/O."""
            local_version_text = self._get_local_version_text(is_custom_path_active)
            if self.view.winfo_exists():
                self.view.after(
                    0, self.local_bridge_version_var.set, local_version_text
                )
                self.view.after(0, self._update_update_button_logic)

        threading.Thread(target=worker, daemon=True).start()

    def _get_local_version_text(self, is_custom: bool) -> str:
        """Determines the local version string based on file existence."""
        if is_custom:
            return f"{translate('Local Version')}: {translate('Custom')}"

        default_exe_path = os.path.join(self.bridge_dir, "ks_bridge.exe")
        version_file_path = f"{default_exe_path}.version"

        try:
            if not os.path.exists(default_exe_path):
                return f"{translate('Local Version')}: {translate('Not Found')}"
            if not os.path.exists(version_file_path):
                return f"{translate('Local Version')}: {translate('Unknown')}"
            
            with open(version_file_path, "r", encoding="utf-8") as f:
                version = f.read().strip()
            
            return f"{translate('Local Version')}: {version or translate('Unknown')}"
        
        except Exception as e:
            logger.error(f"Failed to read local bridge version file: {_sanitize_for_logging(e)}")
            return f"{translate('Local Version')}: {translate('Error')}"

    def activate_tab(self) -> None:
        """Called when the tab becomes visible."""
        if not self.first_activation_done:
            self.first_activation_done = True
            self.view.after(100, self._delayed_activation_check)

        self._check_for_external_process()

        if (
            self.latest_bridge_version_var.get() == f"{translate('Latest Version')}: N/A"
            and self.version_checker
        ):
            self.version_checker.check_version()

    def _delayed_activation_check(self) -> None:
        """Performs the synchronous file check and prompt after a short delay."""
        try:
            if not self.view.winfo_exists():
                return
            self.update_command_preview()
            self._update_update_button_logic()

            file_exists = os.path.exists(self.bridge_exe_path) and os.path.exists(
                self.config_yaml_path
            )
            if not file_exists and not self.use_custom_exe_var.get():
                self.log_message(
                    translate(
                        "Bridge files not found. Please use the 'Update Bridge' button to download them."
                    ),
                    "WARN",
                )
                self._prompt_for_download_path_and_start()

            self._check_local_bridge_version()
        except tk.TclError:
            pass
        except Exception as e:
            logger.error(f"Error during delayed activation check: {e}")

    def _browse_file(
        self, var: ttk.StringVar, title: str, filetypes: List[Tuple[str, str]]
    ) -> None:
        """Open a file dialog and set the variable to the selected path."""
        path = filedialog.askopenfilename(title=translate(title), filetypes=filetypes)
        if path:
            var.set(sanitize_cli_arg(path))
        self._save_and_update_preview()

    def _update_log_font(self, *args: Any) -> None:
        """Update the font size in the log window."""
        self.view.log_pane_component.log_font_size_var.set(
            self.log_font_size_var.get()
        )
        self.view.log_pane_component._on_font_size_change()
        self._save_settings()

    def log_message(self, message: str, level: str = "INFO") -> None:
        """Thread-safe method to log a message to the unified LogPane component."""
        try:
            if self.view.winfo_exists() and hasattr(self.view, "log_pane_component"):
                sanitized_message = f"{_sanitize_for_logging(message)}\n"
                self.main_window.after(
                    0,
                    self.view.log_pane_component.insert_line,
                    sanitized_message,
                    level,
                )
        except (tk.TclError, RuntimeError):
            pass

    def read_output(self, pipe: Optional[Any]) -> None:
        """Read output from the subprocess pipe line by line."""
        if pipe is None:
            return
        try:
            with pipe:
                for line in iter(pipe.readline, b""):
                    try:
                        if not self.view.winfo_exists(): break
                        line_str = line.decode("utf-8", errors="ignore").rstrip()
                        if not line_str: continue
                        
                        log_level = self._parse_log_level(line_str)
                        self.log_message(line_str, log_level)
                    except (tk.TclError, RuntimeError):
                        break
        except Exception as e:
            if "Bad file descriptor" not in str(e) and "most likely because it was closed" not in str(e):
                try:
                    if self.view.winfo_exists():
                        self.log_message(f"Error reading process output: {e}", "ERROR")
                except (tk.TclError, RuntimeError):
                    pass
        finally:
            try:
                if self.view.winfo_exists():
                    self.main_window.after(0, self.on_process_exit)
            except (tk.TclError, RuntimeError):
                pass

    def _parse_log_level(self, line: str) -> str:
        """Parses the log level from a log line string."""
        line_lower = line.lower()
        if "level=trace" in line_lower: return "TRACE"
        if "level=debug" in line_lower: return "DEBUG"
        if "level=warn" in line_lower: return "WARN"
        if "level=error" in line_lower: return "ERROR"
        if "level=fatal" in line_lower: return "FATAL"
        return "INFO"

    def build_args_from_settings(self) -> List[str]:
        """Build the list of command-line arguments for the subprocess."""
        args = [self.bridge_exe_path]
        key_to_arg_map = {
            "kaspa_addr_var": "-kaspa",
            "stratum_port_var": "-stratum",
            "prom_port_var": "-prom",
            "hcp_var": "-hcp",
            "min_diff_var": "-mindiff",
            "shares_per_min_var": "-sharespermin",
            "vardiff_var": "-vardiff",
            "pow2clamp_var": "-pow2clamp",
            "log_file_var": "-log",
            "console_stats_var": "-stats",
            "vardiff_stats_var": "-vardiffstats",
            "blockwait_var": "-blockwait",
            "extranonce_var": "-extranonce",
        }

        for var_tuple, key, _ in self.all_vars_list:
            arg_name = key_to_arg_map.get(key)
            if not arg_name: continue

            if (
                key in self.key_to_enabled_var_map 
                and not self.key_to_enabled_var_map[key].get()
            ):
                continue
            if (
                key in self.flag_key_to_enabled_var_map
                and not self.flag_key_to_enabled_var_map[key].get()
            ):
                continue

            self._append_argument(args, arg_name, var_tuple, key)
        return args

    def _append_argument(self, args: List[str], arg_name: str, var_tuple: Any, key: str) -> None:
        """Helper to append a single argument to the command list."""
        if isinstance(var_tuple, tuple):
            ip, port = (
                sanitize_cli_arg(var_tuple[0].get()),
                sanitize_cli_arg(var_tuple[1].get()),
            )
            val = f"{ip}:{port}"
            if not ip and port:
                val = f":{port}"
            if ip or port:
                args.extend([arg_name, val])
        elif isinstance(var_tuple, ttk.StringVar):
            val_str = sanitize_cli_arg(var_tuple.get())
            if key in self.flag_key_to_enabled_var_map:
                args.append(f"{arg_name}={val_str.lower()}")
            elif val_str:
                args.extend([arg_name, val_str])

    def on_process_exit(self) -> None:
        """Callback function when the subprocess terminates."""
        self.running_command_str = ""
        try:
            self.log_message(f"\n--- {translate('Process Terminated')} ---", "WARN")
            self._update_ui_after_exit()
        except (tk.TclError, RuntimeError):
            pass
        
        self.bridge_process = None
        
        try:
            if self.view.winfo_exists():
                self.view.after(0, self.set_controls_state, True)
                self.view.after(100, self._check_for_external_process)
        except (tk.TclError, RuntimeError):
            pass

        if self.auto_reconnect_var.get() and not self._stop_requested:
            self.log_message("Auto-reconnect enabled. Restarting in 5 seconds...", "INFO")
            try:
                if self.view.winfo_exists():
                    self.view.after(5000, self.start_bridge)
            except tk.TclError:
                pass

    def _update_ui_after_exit(self) -> None:
        """Updates UI buttons after process exit."""
        if self.view.start_button.winfo_exists():
            self.view.start_button.config(state="normal")
        if self.view.stop_button.winfo_exists():
            self.view.stop_button.config(state="disabled")
        if self.view.apply_restart_button.winfo_exists():
            self.view.apply_restart_button.config(state="disabled")

    def apply_and_restart_bridge(self) -> None:
        """Stops the bridge (if running) and starts it with the new command."""
        self.log_message("Apply & Restart requested...", "INFO")
        if self._is_bridge_running():
            self.log_message("Stopping current bridge process...", "INFO")
            self.stop_bridge()
            self.view.after(1000, self._wait_for_stop_and_start)
        else:
            self.start_bridge()

    def _wait_for_stop_and_start(self, timeout: int = 5000) -> None:
        """Helper to wait for process to stop before restarting."""
        if self._is_bridge_running() and timeout > 0:
            self.view.after(500, self._wait_for_stop_and_start, timeout - 500)
        elif timeout <= 0:
            self.log_message("Error: Bridge did not stop in time. Cannot restart.", "ERROR")
            self.on_process_exit()
        else:
            self.log_message("Bridge stopped. Restarting...", "INFO")
            self.start_bridge()

    def stop_bridge(self) -> None:
        """Stop the running subprocess and its children using psutil."""
        self._stop_requested = True
        if not self._is_bridge_running() or not self.bridge_process:
            self.log_message(f"{translate('Bridge is not running.')}", "WARN")
            return

        try:
            self.log_message(translate("Stopping Kaspa Bridge..."), "INFO")
            parent = psutil.Process(self.bridge_process.pid)
            children = parent.children(recursive=True)

            for child in children:
                try: child.terminate()
                except psutil.NoSuchProcess: pass
            
            self.bridge_process.terminate()
            psutil.wait_procs(children, timeout=3)
        except psutil.NoSuchProcess:
            self.log_message(translate("Bridge is not running."), "WARN")
        except Exception as e:
            self.log_message(f"Error while stopping bridge: {_sanitize_for_logging(e)}", "ERROR")
        finally:
            try:
                if self.view.winfo_exists(): self.on_process_exit()
            except tk.TclError:
                pass

    def _check_for_external_process(self) -> None:
        """Scans for external ks_bridge processes, ignoring other managed instances."""
        self.external_process_pids.clear()
        my_pid = self.bridge_process.pid if self.bridge_process else None

        managed_pids: Set[Optional[int]] = {my_pid}
        if self.main_bridge_tab:
            self._add_managed_pids(managed_pids, self.main_bridge_tab.bridge1_tab_instance)
            self._add_managed_pids(managed_pids, self.main_bridge_tab.bridge2_tab_instance)

        try:
            for proc in psutil.process_iter(["pid", "name"]):
                if (
                    proc.name().lower() == "ks_bridge.exe"
                    and proc.pid not in managed_pids
                ):
                    self.external_process_pids.append(proc.pid)

            if self.external_process_pids:
                logger.warning(
                    f"Found external ks_bridge.exe (PIDs: {self.external_process_pids}). Managed PIDs: {managed_pids}"
                )
        except Exception as e:
            logger.warning(f"Failed to scan for external processes: {e}")

        self._update_external_process_ui()

    def _add_managed_pids(self, pid_set: Set[Optional[int]], tab_instance: Optional[BridgeInstanceTab]) -> None:
        if tab_instance and tab_instance.controller.bridge_process:
            pid_set.add(tab_instance.controller.bridge_process.pid)

    def _update_external_process_ui(self) -> None:
        """Shows or hides the external process warning frame."""
        try:
            if self.external_process_pids:
                pids_str = ", ".join(map(str, self.external_process_pids))
                msg = translate(
                    "External ks_bridge.exe found (PID: {}). Stop it to run the bridge here."
                ).format(pids_str)
                self.view.external_process_label.config(text=msg)
                self.view.external_process_frame.pack(
                    fill=X, expand=True, pady=(5, 0), ipady=5
                )
            else:
                self.view.external_process_frame.pack_forget()
        except tk.TclError:
            pass

    def stop_external_bridge(self) -> None:
        """Stops all detected external ks_bridge processes."""
        if not self.external_process_pids:
            return

        pids_str = ", ".join(map(str, self.external_process_pids))
        msg_key = "Are you sure you want to stop the external ks_bridge process (PID: {})?"

        if not messagebox.askyesno(
            translate("Confirm Stop"),
            translate(msg_key).format(pids_str),
        ):
            return

        stopped_count = 0
        failed_pids = []

        for pid in self.external_process_pids:
            try:
                proc = psutil.Process(pid)
                proc.terminate()
                self.log_message(f"Terminated external process {pid}.", "INFO")
                stopped_count += 1
            except psutil.NoSuchProcess:
                self.log_message(f"External process {pid} already stopped.", "WARN")
            except Exception as e:
                self.log_message(f"Failed to stop external process {pid}: {e}", "ERROR")
                failed_pids.append(pid)

        if stopped_count > 0:
            ToastNotification(
                title=translate("Success"),
                message=translate("External process terminated."),
                bootstyle=SUCCESS,
            ).show_toast()

        if failed_pids:
            messagebox.showerror(
                translate("Error"),
                f"Failed to stop PIDs: {', '.join(map(str, failed_pids))}",
            )

        self.view.after(500, self._check_for_external_process)

    def _delete_bridge_files(self) -> None:
        """Delete the bridge exe, config, and version files."""
        try:
            if not self._validate_deletion_safety():
                return
        except Exception as e:
            self.log_message(
                f"Error during security check: {_sanitize_for_logging(e)}",
                "ERROR",
            )
            return

        if self._is_bridge_running():
            self.log_message(translate("Error: Process is running."), "ERROR")
            messagebox.showerror(
                translate("Error"), translate("Error: Process is running.")
            )
            return

        exe_path = self.bridge_exe_path
        config_path = self.config_yaml_path
        ver_path = f"{exe_path}.version"

        if not self._confirm_deletion(exe_path, config_path, ver_path):
            return

        try:
            self._perform_deletion(exe_path, config_path, ver_path)
            if self.version_checker:
                self.version_checker.check_version()
            self._check_local_bridge_version()
            ToastNotification(
                title=translate("Delete Files"),
                message=translate("Files deleted successfully."),
                bootstyle=SUCCESS,
                duration=3000,
            ).show_toast()
        except Exception as e:
            self._handle_deletion_error(e)

    def _validate_deletion_safety(self) -> bool:
        """Confirms that deletion paths are within the app's data directory."""
        safe_dir_local = os.path.abspath(
            os.path.join(os.getenv("LOCALAPPDATA", ""), "KaspaGateway")
        )
        safe_dir_roaming = os.path.abspath(
            os.path.join(os.getenv("APPDATA", ""), "KaspaGateway")
        )
        
        target_exe_path = os.path.abspath(self.bridge_exe_path)
        target_config_path = os.path.abspath(self.config_yaml_path)
        target_version_path = f"{target_exe_path}.version"

        def is_path_safe(path: str) -> bool:
            path = os.path.abspath(path)
            return path.startswith(safe_dir_local) or path.startswith(safe_dir_roaming)

        if not all(map(is_path_safe, [target_exe_path, target_config_path, target_version_path])):
            self.log_message(
                translate("Error: Deletion path is outside the allowed directory."), "ERROR"
            )
            messagebox.showerror(
                translate("Error"),
                translate("Deletion outside user data directory is not allowed."),
            )
            return False
        return True

    def _confirm_deletion(self, exe: str, config: str, ver: str) -> bool:
        """Asks the user for final confirmation before deleting files."""
        if not any(map(os.path.exists, [exe, config, ver])):
            ToastNotification(
                title=translate("Delete Files"),
                message=translate("Files not found."),
                bootstyle=SUCCESS, # Changed to success/info style as it's just info
                duration=3000,
            ).show_toast()
            return False
        
        msg = (
            f"{translate('Are you sure you want to delete these files? This cannot be undone.')}\n\n"
            f"- {exe}\n"
            f"- {config}\n"
            f"- {ver}"
        )
        return messagebox.askyesno(translate("Confirm File Deletion"), msg)

    def _perform_deletion(self, exe: str, config: str, ver: str) -> None:
        """Performs the actual file removal."""
        for file_path in [exe, config, ver]:
            if os.path.exists(file_path):
                os.remove(file_path)
                self.log_message(f"Deleted: {_sanitize_for_logging(file_path)}", "INFO")

    def _handle_deletion_error(self, e: Exception) -> None:
        """Logs and shows error message on deletion failure."""
        logger.error(f"Failed to delete bridge files: {e}", exc_info=True)
        self.log_message(
            f"{translate('Failed to delete files. Check logs.')}: {_sanitize_for_logging(e)}",
            "ERROR",
        )
        messagebox.showerror(
            translate("Error"),
            f"{translate('Failed to delete files. Check logs.')}\n{e}",
        )

    def on_close(self) -> None:
        """Cleanup function to stop the bridge on application close."""
        self.stop_bridge()

    def set_controls_state(self, active: bool) -> None:
        """Enable or disable all controls in this tab."""
        if not hasattr(self.view, "start_button"):
            return

        is_running = self._is_bridge_running()

        try:
            self.view.start_button.config(
                state="disabled" if (is_running or not active) else "normal"
            )
            self.view.stop_button.config(
                state="normal" if (is_running and active) else "disabled"
            )
            self._update_apply_button_state(is_running, active)
            self._update_update_button_logic(active)

            self.view.reset_button.config(
                state="normal" if (active and not is_running) else "disabled"
            )
            self.view.delete_files_button.config(
                state="normal" if (active and not is_running) else "disabled"
            )

            custom_path_state = "disabled" if (is_running or not active) else "normal"
            self.view.exe_cb.config(state=custom_path_state)
            self.view.config_cb.config(state=custom_path_state)
            self.view.url_cb.config(state=custom_path_state)

            self._update_custom_path_entries(is_running, active)

        except tk.TclError:
            pass

    def _update_apply_button_state(self, is_running: bool, active: bool) -> None:
        try:
            new_command = self.command_preview_var.get().strip()
            if is_running and active and new_command != self.running_command_str:
                self.view.apply_restart_button.config(state="normal")
            else:
                self.view.apply_restart_button.config(state="disabled")
        except tk.TclError:
            self.view.apply_restart_button.config(state="disabled")

    def _update_custom_path_entries(self, is_running: bool, active: bool) -> None:
        if not is_running and active:
            self.view.toggle_entry_state(
                self.use_custom_exe_var,
                [self.view.exe_entry, self.view.exe_browse],
            )
            self.view.toggle_entry_state(
                self.use_custom_config_var,
                [self.view.config_entry, self.view.config_browse],
            )
            custom_url_widgets = [
                self.view.url_entry,
                self.view.url_exe_path_label,
                self.view.url_exe_path_entry,
                self.view.url_config_path_label,
                self.view.url_config_path_entry,
            ]
            self.view.toggle_entry_state(self.use_custom_url_var, custom_url_widgets)
        else:
            self._disable_all_custom_entries()

    def _disable_all_custom_entries(self) -> None:
        disabled_var = ttk.BooleanVar(value=False)
        self.view.toggle_entry_state(
            disabled_var, [self.view.exe_entry, self.view.exe_browse]
        )
        self.view.toggle_entry_state(
            disabled_var, [self.view.config_entry, self.view.config_browse]
        )
        custom_url_widgets = [
            self.view.url_entry,
            self.view.url_exe_path_label,
            self.view.url_exe_path_entry,
            self.view.url_config_path_label,
            self.view.url_config_path_entry,
        ]
        self.view.toggle_entry_state(disabled_var, custom_url_widgets)

    def re_translate(self) -> None:
        """Update all translatable strings in the UI."""
        self.view.re_translate_widgets()
        self._check_local_bridge_version()

        if self.version_checker:
            if "N/A" in self.latest_bridge_version_var.get() or "Error" in self.latest_bridge_version_var.get():
                self.version_checker.check_version()
            else:
                current_version = self.latest_bridge_version_var.get().split(":")[-1].strip()
                self.latest_bridge_version_var.set(
                    f"{translate('Latest Version')}: {current_version}"
                )

        if "N/A" not in self.latest_bridge_date_var.get() and "Error" not in self.latest_bridge_date_var.get():
            current_date = self.latest_bridge_date_var.get().split(":")[-1].strip()
            if current_date:
                self.latest_bridge_date_var.set(
                    f"{translate('Updated')}: {current_date}"
                )

    def _is_bridge_running(self) -> bool:
        """Checks if the bridge process is currently active."""
        return bool(self.bridge_process and self.bridge_process.poll() is None)

    def _check_external_conflicts(self, is_autostart: bool) -> bool:
        """
        Checks for external bridge processes and warns the user if any are found.
        Returns True if a conflict exists and execution should stop.
        """
        self._check_for_external_process()
        if self.external_process_pids:
            pids_str = ", ".join(map(str, self.external_process_pids))
            msg = f"External ks_bridge.exe found (PID: {pids_str}). Stop it to run the bridge here."
            self.log_message(msg, "ERROR")
            if not is_autostart:
                messagebox.showerror(translate("Error"), translate(msg))
            return True
        return False

    def _resolve_executable_and_config(self) -> Tuple[str, str]:
        """
        Determines the correct paths for the executable and config file,
        handling custom path logic and fallbacks.
        """
        # 1. Try to build the command list first to respect settings logic
        command_list = self.build_args_from_settings()
        if not command_list:
            raise Exception("Command list could not be built.")

        exe_path = command_list[0]
        config_path = ""

        # 2. Extract config path from args or settings
        try:
            config_arg_index = command_list.index("-config")
            config_path = command_list[config_arg_index + 1]
        except (ValueError, IndexError):
            if (
                self.use_custom_config_var.get()
                and self.custom_config_path_var.get()
            ):
                config_path = os.path.abspath(self.custom_config_path_var.get())
            else:
                config_path = os.path.join(self.bridge_dir, "config.yaml")
        
        return exe_path, config_path

    def _validate_files(
        self, exe_path: str, config_path: str, is_autostart: bool
    ) -> bool:
        """
        Validates that the executable and config files exist.
        Attempts to fallback to default paths if custom ones fail.
        Returns True if valid files are found, False otherwise.
        """
        if not os.path.isfile(exe_path) or not os.path.exists(config_path):
            self.log_message(
                f"File not found at '{exe_path}' or '{config_path}'. Checking defaults...",
                "ERROR",
            )
            # Fallback to default paths
            exe_path = self.bridge_exe_path
            config_path = self.config_yaml_path

            if not os.path.isfile(exe_path) or not os.path.exists(config_path):
                msg = (
                    f"{translate('Error')}: {translate('File not found')}:\n"
                    f"EXE: {_sanitize_for_logging(exe_path)}\n"
                    f"Config: {_sanitize_for_logging(config_path)}\n"
                    f"{translate('Please update the bridge first using the \"Update Bridge\" button.')}"
                )
                self.log_message(msg, "ERROR")
                self._update_update_button_logic()
                if not is_autostart:
                    messagebox.showerror(translate("Error"), msg)
                return False

        # Update internal paths to the validated ones (important if fallback happened)
        self.bridge_exe_path = exe_path
        self.config_yaml_path = config_path
        return True

    def _is_blocked_shell(self, exe_path: str, is_autostart: bool) -> bool:
        """Checks if the selected executable is a blocked system shell."""
        exe_name = os.path.basename(exe_path).lower()
        blocked_shells = [
            "cmd.exe", "powershell.exe", "pwsh.exe", "bash.exe", "sh.exe"
        ]
        if exe_name in blocked_shells:
            self.log_message("Error: Executable cannot be a system shell.", "ERROR")
            if not is_autostart:
                messagebox.showerror(
                    translate("Invalid Input"),
                    "Selected executable is a blocked system shell.",
                )
            return True
        return False

    def _validate_ip_args(self, command_list: List[str], is_autostart: bool) -> bool:
        """Validates IP/Port arguments in the command list."""
        ip_port_args = {"-kaspa", "-stratum", "-prom", "-hcp"}
        ipv6_pattern = re.compile(r"^\[[0-9a-fA-F:]+\]:(\d+)$")

        for i, arg in enumerate(command_list):
            arg_key = arg.split("=")[0]
            if arg_key in ip_port_args:
                value = ""
                if "=" in arg:
                    value = arg.split("=", 1)[1]
                elif i + 1 < len(command_list):
                    value = command_list[i + 1]

                if (
                    value
                    and not validate_ip_port(value)
                    and not ipv6_pattern.match(value)
                ):
                    if not is_autostart:
                        messagebox.showerror(
                            translate("Invalid Input"),
                            f"Invalid IP/Port format for {arg_key}: {value}",
                        )
                    return False
        return True

    def _launch_subprocess(self, command_list: List[str], working_dir: str) -> None:
        """Launches the subprocess and sets up I/O redirection."""
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

        self.bridge_process = subprocess.Popen(
            command_list,
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW,
            text=False,
        )

    def _assign_job_object(self) -> None:
        """Assigns the process to a Windows Job Object if applicable."""
        if (
            sys.platform == "win32"
            and CONFIG.get("job_object_handle")
            and ctypes
            and self.bridge_process
        ):
            job_handle = CONFIG.get("job_object_handle")
            if job_handle:
                try:
                    pid = self.bridge_process.pid
                    PROCESS_SET_QUOTA_AND_TERMINATE = 0x0101
                    h_process = ctypes.windll.kernel32.OpenProcess(
                        PROCESS_SET_QUOTA_AND_TERMINATE, False, pid
                    )

                    if h_process:
                        if ctypes.windll.kernel32.AssignProcessToJobObject(
                            job_handle, h_process
                        ):
                            logger.info(f"Assigned ks_bridge (PID: {pid}) to Job Object.")
                        else:
                            err = ctypes.windll.kernel32.GetLastError()
                            logger.error(f"Failed assign ks_bridge to Job Object. Error: {err}")
                        ctypes.windll.kernel32.CloseHandle(h_process)
                    else:
                        err = ctypes.windll.kernel32.GetLastError()
                        logger.error(f"Failed open ks_bridge process. Error: {err}")
                except Exception as e:
                    logger.error(f"Job Object assignment failed: {e}", exc_info=True)

    def start_bridge(self, is_autostart: bool = False) -> None:
        """
        Start the kaspa-stratum-bridge subprocess.
        Refactored to use helper methods for clarity and reduced complexity.
        """
        if self._is_bridge_running():
            self.log_message(f"{translate('Bridge is already running.')}", "WARN")
            return

        self._stop_requested = False

        if self._check_external_conflicts(is_autostart):
            return

        try:
            exe_path, config_path = self._resolve_executable_and_config()
        except Exception as e:
            self.log_message(f"Error parsing command/paths: {e}", "ERROR")
            if not is_autostart:
                messagebox.showerror(translate("Invalid Input"), f"Error: {e}")
            return

        if self._is_blocked_shell(exe_path, is_autostart):
            return

        if not self._validate_files(exe_path, config_path, is_autostart):
            return

        # Re-build command list with validated paths (implicitly handled by instance vars update)
        command_list = self.build_args_from_settings()
        # Override the 0th element to ensure it matches the validated exe path
        if command_list:
            command_list[0] = self.bridge_exe_path
        
        if not self._validate_ip_args(command_list, is_autostart):
            return

        command_str = " ".join(command_list)
        working_dir = os.path.dirname(self.config_yaml_path)

        self.log_message(f"--- {translate('Starting Bridge')} ---", "INFO")
        self.log_message(f"{translate('Working Directory')}:\n{_sanitize_for_logging(working_dir)}", "DEBUG")
        self.log_message(f"{translate('Command')}:\n{command_str}", "DEBUG")
        self.log_message("...", "INFO")

        try:
            self._launch_subprocess(command_list, working_dir)
            self.running_command_str = command_str
            self._assign_job_object()

            threading.Thread(
                target=self.read_output,
                args=(self.bridge_process.stdout,),
                daemon=True,
            ).start()

            self.view.start_button.config(state="disabled")
            self.view.stop_button.config(state="normal")
            self.set_controls_state(True)

        except Exception as e:
            self.log_message(
                f"Failed to start Kaspa Bridge: {_sanitize_for_logging(e)}", "FATAL"
            )
            self.bridge_process = None
