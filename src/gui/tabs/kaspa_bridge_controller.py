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
import signal
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING, cast
from types import FrameType

import psutil
import ttkbootstrap as ttk
from ttkbootstrap.constants import DANGER, INFO, SUCCESS, DISABLED, NORMAL
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
    validate_url,
)
from src.gui.config_manager import ConfigManager

if TYPE_CHECKING:
    from src.gui.tabs.kaspa_bridge_tab import (
        BridgeInstanceTab,
        KaspaBridgeTab,
    )
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


class BridgeInstanceController:
    """
    The Controller class for a single Bridge Instance Tab.
    Manages all state and logic, interacting with BridgeInstanceTab (View).
    """

    # --- Type Hint Declarations ---
    view: "BridgeInstanceTab"
    main_window: "MainWindow"
    config_manager: ConfigManager
    instance_id: str
    config_key: str
    main_bridge_tab: Optional["KaspaBridgeTab"]
    bridge_process: Optional[subprocess.Popen[bytes]]
    version_checker: Optional[VersionChecker]
    first_activation_done: bool
    is_updating: bool
    bridge_dir: str
    bridge_exe_path: str
    config_yaml_path: str
    all_vars_list: List[Tuple[Any, str, Any]]
    key_to_enabled_var_map: Dict[str, ttk.BooleanVar]
    flag_key_to_enabled_var_map: Dict[str, ttk.BooleanVar]
    
    # Dynamic variables defined in define_variables
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
    # --- End Type Hint Declarations ---

    def __init__(
        self,
        view: "BridgeInstanceTab",
        main_window: "MainWindow",
        config_manager: ConfigManager,
        instance_id: str,
        main_bridge_tab: Optional["KaspaBridgeTab"] = None,
    ) -> None:
        """
        Initializes the BridgeInstanceController.
        """
        self.view: "BridgeInstanceTab" = view
        self.main_window: "MainWindow" = main_window
        self.config_manager: ConfigManager = config_manager
        self.instance_id: str = instance_id
        self.config_key: str = f"kaspa_bridge{instance_id}"
        self.main_bridge_tab: Optional["KaspaBridgeTab"] = main_bridge_tab

        self.bridge_process: Optional[subprocess.Popen[bytes]] = None
        self.version_checker: Optional[VersionChecker] = None
        self.first_activation_done: bool = False
        self.is_updating: bool = False

        self.bridge_dir: str = os.path.join(
            os.getenv("LOCALAPPDATA", CONFIG["paths"]["database"]),
            "KaspaGateway",
            f"bin_bridge{instance_id}",
        )
        os.makedirs(self.bridge_dir, exist_ok=True)
        self.bridge_exe_path: str = os.path.join(
            self.bridge_dir, "ks_bridge.exe"
        )
        self.config_yaml_path: str = os.path.join(
            self.bridge_dir, "config.yaml"
        )


        self.define_variables()
        self._load_settings()

        if self.use_custom_exe_var.get() and self.custom_exe_path_var.get():
            self.bridge_exe_path = self.custom_exe_path_var.get()
        if (
            self.use_custom_config_var.get()
            and self.custom_config_path_var.get()
        ):
            self.config_yaml_path = self.custom_config_path_var.get()

        self.update_command_preview()

    def _bool_to_str(self, b_val: bool) -> str:
        """Converts a boolean to its string representation."""
        return "true" if b_val else "false"

    def _str_to_bool(self, s_val: str) -> bool:
        """Converts a string from radio buttons back to a boolean."""
        return s_val == "true"

    def define_variables(self) -> None:
        """Initialize all ttk variables for the GUI controls."""
        # Use default ports 5555/2112 for _1, and 5556/2113 for _2
        default_stratum: str = ":5555" if self.instance_id == "_1" else ":5556"
        default_prom: str = ":2112" if self.instance_id == "_1" else ":2113"

        # --- Entry and IP/Port Variables ---
        self.kaspa_addr_var: Tuple[ttk.StringVar, ttk.StringVar] = (
            ttk.StringVar(value="127.0.0.1"),
            ttk.StringVar(value="16110"),
        )
        self.stratum_port_var: ttk.StringVar = ttk.StringVar(
            value=default_stratum
        )
        self.prom_port_var: ttk.StringVar = ttk.StringVar(value=default_prom)
        self.hcp_var: ttk.StringVar = ttk.StringVar(value="")
        self.min_diff_var: ttk.StringVar = ttk.StringVar(value="4096")
        self.shares_per_min_var: ttk.StringVar = ttk.StringVar(value="20")
        self.blockwait_var: ttk.StringVar = ttk.StringVar(value="3s")
        self.extranonce_var: ttk.StringVar = ttk.StringVar(
            value="0" if self.instance_id == "_1" else "2"
        )
        self.custom_exe_path_var: ttk.StringVar = ttk.StringVar(value="")
        self.custom_config_path_var: ttk.StringVar = ttk.StringVar(value="")
        self.custom_url_var: ttk.StringVar = ttk.StringVar(value="")
        self.custom_url_exe_path_var: ttk.StringVar = ttk.StringVar(
            value="ks_bridge/ks_bridge.exe"
        )
        self.custom_url_config_path_var: ttk.StringVar = ttk.StringVar(
            value="ks_bridge/config.yaml"
        )
        self.command_preview_var: ttk.StringVar = ttk.StringVar()
        self.local_bridge_version_var: ttk.StringVar = ttk.StringVar(
            value=f"{translate('Local Version')}: N/A"
        )
        self.latest_bridge_version_var: ttk.StringVar = ttk.StringVar(
            value=f"{translate('Latest Version')}: N/A"
        )
        self.latest_bridge_date_var: ttk.StringVar = ttk.StringVar(
            value=f"{translate('Updated')}: N/A"
        )

        # --- Radio Button Flag Variables (str) ---
        self.vardiff_var: ttk.StringVar = ttk.StringVar(
            value=self._bool_to_str(True)
        )
        self.pow2clamp_var: ttk.StringVar = ttk.StringVar(
            value=self._bool_to_str(True)
        )
        self.log_file_var: ttk.StringVar = ttk.StringVar(
            value=self._bool_to_str(True)
        )
        self.console_stats_var: ttk.StringVar = ttk.StringVar(
            value=self._bool_to_str(True)
        )
        self.vardiff_stats_var: ttk.StringVar = ttk.StringVar(
            value=self._bool_to_str(False)
        )

        # --- Checkbox Flag Variables (bool) ---
        self.log_font_size_var: ttk.IntVar = ttk.IntVar(value=9)
        self.autostart_var: ttk.BooleanVar = ttk.BooleanVar(value=False)
        self.use_custom_exe_var: ttk.BooleanVar = ttk.BooleanVar(value=False)
        self.use_custom_config_var: ttk.BooleanVar = ttk.BooleanVar(value=False)
        self.use_custom_url_var: ttk.BooleanVar = ttk.BooleanVar(value=False)
        self.kaspa_addr_enabled_var: ttk.BooleanVar = ttk.BooleanVar(value=True)
        self.stratum_port_enabled_var: ttk.BooleanVar = ttk.BooleanVar(
            value=True
        )
        self.prom_port_enabled_var: ttk.BooleanVar = ttk.BooleanVar(value=True)
        self.hcp_enabled_var: ttk.BooleanVar = ttk.BooleanVar(value=False)
        self.min_diff_enabled_var: ttk.BooleanVar = ttk.BooleanVar(value=True)
        self.shares_per_min_enabled_var: ttk.BooleanVar = ttk.BooleanVar(
            value=True
        )
        self.blockwait_enabled_var: ttk.BooleanVar = ttk.BooleanVar(value=True)
        self.extranonce_enabled_var: ttk.BooleanVar = ttk.BooleanVar(value=True)
        self.vardiff_enabled_var: ttk.BooleanVar = ttk.BooleanVar(value=True)
        self.pow2clamp_enabled_var: ttk.BooleanVar = ttk.BooleanVar(value=True)
        self.log_file_enabled_var: ttk.BooleanVar = ttk.BooleanVar(value=True)
        self.console_stats_enabled_var: ttk.BooleanVar = ttk.BooleanVar(
            value=True
        )
        self.vardiff_stats_enabled_var: ttk.BooleanVar = ttk.BooleanVar(
            value=False
        )

        # --- Version Checker ---
        self.version_checker: VersionChecker = VersionChecker(
            asset_name="ks_bridge.exe",
            version_var=self.latest_bridge_version_var,
            date_var=self.latest_bridge_date_var,
            log_callback=self.log_message,
            repo_url="https://api.github.com/repos/aglov413/kaspa-stratum-bridge/releases/latest",
        )

        # --- Variable Mapping ---
        self.all_vars_list: List[Tuple[Any, str, Any]] = [
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
            (self.vardiff_stats_var, "vardiff_stats_var", False),
            (self.blockwait_var, "blockwait_var", "3s"),
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
            (self.shares_per_min_enabled_var, "shares_per_min_enabled_var", True),
            (self.blockwait_enabled_var, "blockwait_enabled_var", True),
            (self.extranonce_enabled_var, "extranonce_enabled_var", True),
            (self.vardiff_enabled_var, "vardiff_enabled_var", True),
            (self.pow2clamp_enabled_var, "pow2clamp_enabled_var", True),
            (self.log_file_enabled_var, "log_file_enabled_var", True),
            (self.console_stats_enabled_var, "console_stats_enabled_var", True),
            (self.vardiff_stats_enabled_var, "vardiff_stats_enabled_var", False),
        ]

        self.key_to_enabled_var_map: Dict[str, ttk.BooleanVar] = {
            "kaspa_addr_var": self.kaspa_addr_enabled_var,
            "stratum_port_var": self.stratum_port_enabled_var,
            "prom_port_var": self.prom_port_enabled_var,
            "hcp_var": self.hcp_enabled_var,
            "min_diff_var": self.min_diff_enabled_var,
            "shares_per_min_var": self.shares_per_min_enabled_var,
            "blockwait_var": self.blockwait_enabled_var,
            "extranonce_var": self.extranonce_enabled_var,
        }

        self.flag_key_to_enabled_var_map: Dict[str, ttk.BooleanVar] = {
            "vardiff_var": self.vardiff_enabled_var,
            "pow2clamp_var": self.pow2clamp_enabled_var,
            "log_file_var": self.log_file_enabled_var,
            "console_stats_var": self.console_stats_enabled_var,
            "vardiff_stats_var": self.vardiff_stats_enabled_var,
        }

    def _load_settings(self) -> None:
        """Load settings from the config manager into the ttk variables."""
        bridge_config: Dict[str, Any] = self.config_manager.get_config().get(self.config_key, {})

        for var_tuple, key, default in self.all_vars_list:
            saved_value: Any = bridge_config.get(key, default)

            if key in ["kaspa_addr_var", "stratum_port_var", "prom_port_var", "hcp_var"]:
                ip_port_str: str = ""
                if isinstance(var_tuple, tuple) and len(var_tuple) == 2:
                    ip_port_str = (
                        f"{saved_value[0]}:{saved_value[1]}"
                        if isinstance(saved_value, (list, tuple))
                        else str(saved_value)
                    )
                elif isinstance(var_tuple, ttk.StringVar):
                    ip_port_str = str(saved_value)

                validation_result: Optional[Tuple[str, str]] = validate_ip_port(ip_port_str)
                if validation_result:
                    ip, port = validation_result
                    if isinstance(var_tuple, tuple):
                        var_tuple[0].set(ip)
                        var_tuple[1].set(port)
                    elif isinstance(var_tuple, ttk.StringVar):
                        var_tuple.set(ip_port_str)
                    continue

                if isinstance(var_tuple, tuple):
                    default_ip, default_port = default
                    var_tuple[0].set(default_ip)
                    var_tuple[1].set(default_port)
                elif isinstance(var_tuple, ttk.StringVar):
                    var_tuple.set(default)
                continue

            if key in self.flag_key_to_enabled_var_map:
                if isinstance(saved_value, bool):
                    var_tuple.set(self._bool_to_str(saved_value))
                else:
                    var_tuple.set(str(saved_value))
                continue


            if isinstance(var_tuple, (ttk.StringVar, ttk.BooleanVar, ttk.IntVar)):
                var_tuple.set(saved_value)

    def _save_settings(self, *args: Any) -> None:
        """Save the current state of ttk variables to the config manager."""
        bridge_config: Dict[str, Any] = self.config_manager.get_config().get(self.config_key, {})

        for var_tuple, key, _ in self.all_vars_list:
            value_to_save: Any = None

            if key in self.flag_key_to_enabled_var_map:
                value_to_save = self._str_to_bool(var_tuple.get())

            elif isinstance(var_tuple, (ttk.StringVar, ttk.BooleanVar, ttk.IntVar)):
                value_to_save = var_tuple.get()
            elif isinstance(var_tuple, tuple) and len(var_tuple) == 2:
                ip_val: str = sanitize_cli_arg(var_tuple[0].get())
                port_val: str = sanitize_cli_arg(var_tuple[1].get())
                value_to_save = (ip_val, port_val)

            if (
                key in self.key_to_enabled_var_map
                or key in self.flag_key_to_enabled_var_map
                or isinstance(var_tuple, (ttk.StringVar, ttk.BooleanVar, ttk.IntVar))
            ):
                bridge_config[key] = value_to_save

        self.config_manager.get_config()[self.config_key] = bridge_config
        self.config_manager.save_config(self.config_manager.get_config())

    def _save_and_update_preview(self, *args: Any) -> None:
        """Wrapper to update preview and save settings, for use in tracers."""
        self.update_command_preview()
        self._save_settings()

    def _add_tracers(self) -> None:
        """Add 'write' tracers to all variables to auto-save and update."""
        for var_tuple, key, _ in self.all_vars_list:
            if key in ["use_custom_exe_var", "use_custom_config_var", "use_custom_url_var"]:
                continue

            if isinstance(var_tuple, tuple) and len(var_tuple) == 2:
                var_tuple[0].trace_add("write", self._save_and_update_preview)
                var_tuple[1].trace_add("write", self._save_and_update_preview)
            elif isinstance(var_tuple, (ttk.StringVar, ttk.BooleanVar, ttk.IntVar)):
                var_tuple.trace_add("write", self._save_and_update_preview)

        self.use_custom_exe_var.trace_add("write", self._on_custom_exe_toggled)
        self.use_custom_config_var.trace_add("write", self._on_custom_config_toggled)
        self.use_custom_url_var.trace_add("write", self._on_custom_url_toggled)

    def reset_to_defaults(self) -> None:
        """Reset all options in this tab to their default values."""
        if not messagebox.askyesno(
            translate("Confirm Reset"),
            translate(
                "Are you sure you want to reset all options to their defaults? "
                "This cannot be undone."
            ),
        ):
            return

        logger.info(f"Resetting bridge {self.instance_id} options to default.")

        for var_tuple, key, default in self.all_vars_list:
            if key in self.flag_key_to_enabled_var_map:
                var_tuple.set(self._bool_to_str(default))
            elif isinstance(var_tuple, (ttk.StringVar, ttk.BooleanVar, ttk.IntVar)):
                var_tuple.set(default)
            elif isinstance(var_tuple, tuple) and len(var_tuple) == 2:
                var_tuple[0].set(default[0])
                var_tuple[1].set(default[1])

        self._save_and_update_preview()
        self._check_local_bridge_version()

        ToastNotification(
            title=translate("Success"),
            message=translate("Bridge options have been reset to default."),
            bootstyle=SUCCESS,
            duration=3000,
        ).show_toast()

    def update_command_preview(self, *args: Any) -> None:
        """Update the command preview text box based on current settings."""
        if self.use_custom_exe_var.get() and self.custom_exe_path_var.get():
            self.bridge_exe_path = self.custom_exe_path_var.get()
        else:
            self.bridge_exe_path = os.path.join(self.bridge_dir, "ks_bridge.exe")

        if self.use_custom_config_var.get() and self.custom_config_path_var.get():
            self.config_yaml_path = self.custom_config_path_var.get()
        else:
            self.config_yaml_path = os.path.join(self.bridge_dir, "config.yaml")

        command_list: List[str] = self.build_args_from_settings()
        command_str: str = " ".join(command_list)
        self.command_preview_var.set(command_str)

        if hasattr(self.view, "update_preview_text_widget"):
            self.view.update_preview_text_widget(command_str)

    def copy_command_to_clipboard(self) -> None:
        """Copy the generated command string to the user's clipboard."""
        command: str = self.command_preview_var.get()
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
        """Start the bridge if the autostart checkbox is ticked."""
        if self.autostart_var.get():
            logger.info(f"Auto-starting Bridge {self.instance_id}...")
            self.start_bridge(is_autostart)

    def _update_update_button_logic(self, *args: Any) -> None:
        """
        Updates the Update/Download button text AND state.
        """
        if not hasattr(self.view, "update_button"):
            return

        self.update_command_preview()

        file_exists: bool = os.path.exists(
            self.bridge_exe_path
        ) and os.path.exists(self.config_yaml_path)
        is_custom_url: bool = self.use_custom_url_var.get()
        is_custom_exe: bool = self.use_custom_exe_var.get()

        if is_custom_url:
            self.view.update_button.config(text=translate("Download File"))
        elif not file_exists:
            self.view.update_button.config(text=translate("Download Bridge"))
        else:
            self.view.update_button.config(text=translate("Update Bridge"))

        is_app_busy: bool = self.is_updating
        
        is_globally_active: bool = True
        if args and isinstance(args[0], bool):
            is_globally_active = args[0]

        if is_app_busy or is_custom_exe or not is_globally_active:
            self.view.update_button.config(state="disabled")
        else:
            self.view.update_button.config(state="normal")
            
    def _on_custom_exe_toggled(self, *args: Any) -> None:
        """Tracer for 'Use Custom ks_bridge.exe' checkbox."""
        self.view.toggle_entry_state(
            self.use_custom_exe_var, [self.view.exe_entry, self.view.exe_browse]
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
            self.use_custom_config_var, [self.view.config_entry, self.view.config_browse]
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
        custom_url_widgets: List[tk.Widget] = [
            self.view.url_entry,
            self.view.url_exe_path_label,
            self.view.url_exe_path_entry,
            self.view.url_config_path_label,
            self.view.url_config_path_entry,
        ]
        self.view.toggle_entry_state(
            self.use_custom_url_var, custom_url_widgets
        )
        
        
        if self.use_custom_url_var.get():
            self.use_custom_exe_var.set(False)
            self.use_custom_config_var.set(False)

        self._save_and_update_preview()
        self.set_controls_state(True) 
            
    def _prompt_for_download_path_and_start(self) -> None:
        """
        Shows the Yes/No/Cancel prompt to select a download path.
        """
        default_path: str = self.bridge_dir or os.getcwd()
        
        if self.use_custom_url_var.get():
            msg_template: str = (
                translate("Download from custom URL?")
                + f"\n\n- {translate('Click Yes to download to default location:')}\n{default_path}\n\n"
                + f"- {translate('Click No to select a custom location.')}"
            )
        else:
            msg_template = (
                translate(
                    "ks_bridge.exe or config.yaml not found. These components are "
                    "required to run the bridge. Would you like to download them now?"
                )
                + f"\n\n- {translate('Click Yes to download to default location:')}\n"
                + f"{default_path}\n\n"
                + f"- {translate('Click No to select a custom location.')}"
            )

        user_choice: Optional[bool] = messagebox.askyesnocancel(translate("Update Bridge"), msg_template)

        chosen_path: Optional[str] = None
        if user_choice is True:
            chosen_path = default_path
        elif user_choice is False:
            chosen_path = filedialog.askdirectory(
                title=translate("Select Download Location"), initialdir=default_path
            )
        else:
            self._update_update_button_logic() 
            return

        if chosen_path:
            self.bridge_dir = chosen_path
            self.bridge_exe_path = os.path.join(self.bridge_dir, "ks_bridge.exe")
            self.config_yaml_path = os.path.join(self.bridge_dir, "config.yaml")
            self.start_bridge_update()
        else:
            self._update_update_button_logic() 

    def _on_update_button_pressed(self) -> None:
        """
        This is the command for the Update/Download button.
        It decides whether to prompt for a path or just update.
        """
        is_custom_url: bool = self.use_custom_url_var.get()
        file_exists: bool = os.path.exists(
            self.bridge_exe_path
        ) and os.path.exists(self.config_yaml_path)

        is_download_action: bool = is_custom_url or not file_exists

        if is_download_action:
            self._prompt_for_download_path_and_start()
        else:
            self.start_bridge_update()

    def start_bridge_update(self) -> None:
        """Begin the download/update process for the bridge binaries."""
        log_text: str = (
            translate("Download File")
            if self.use_custom_url_var.get()
            else translate("Update Bridge")
        )
        self.log_message(f"--- {log_text} ---")
        
        self.is_updating = True
        self.set_controls_state(False)

        self.update_command_preview()

        repo_url: str = (
            "https://api.github.com/repos/aglov413/kaspa-stratum-bridge/releases/latest"
        )
        asset_name_pattern: str = r"ks_bridge-v[\d\.]+(-dev)?\.zip$"
        target_exe: str = "ks_bridge/ks_bridge.exe"
        target_config: str = "ks_bridge/config.yaml"

        if self.use_custom_url_var.get() and self.custom_url_var.get():
            repo_url = self.custom_url_var.get()
            asset_name_pattern = r"\.zip$"
            target_exe = self.custom_url_exe_path_var.get()
            target_config = self.custom_url_config_path_var.get()

            if (
                not re.match(r"^[\w\.\-/]+$", target_exe)
                or ".." in target_exe
                or not re.match(r"^[\w\.\-/]+$", target_config)
                or ".." in target_config
            ):
                messagebox.showerror(
                    translate("Invalid Input"), "Invalid file path in zip."
                )
                self.is_updating = False
                self.set_controls_state(True)
                return

            if not repo_url.endswith(".zip") and "api.github.com" not in repo_url:
                messagebox.showerror(
                    translate("Invalid Input"),
                    translate("Custom URL must be a .zip file or a GitHub API URL."),
                )
                self.is_updating = False
                self.set_controls_state(True)
                return

        multi_target_files: List[Dict[str, str]] = [
            {"target_in_zip": target_exe, "local_path": self.bridge_exe_path},
            {"target_in_zip": target_config, "local_path": self.config_yaml_path},
        ]

        progress_window: DownloadProgressWindow = DownloadProgressWindow(
            self.main_window, title=translate("Update Bridge")
        )

        threading.Thread(
            target=self.run_update_thread,
            args=(progress_window, repo_url, asset_name_pattern, multi_target_files),
            daemon=True,
        ).start()

    def run_update_thread(
        self,
        progress_window: DownloadProgressWindow,
        repo_url: str,
        asset_name_pattern: str,
        multi_target_files: List[Dict[str, str]],
    ) -> None:
        """
        Worker thread function to run the GitHubUpdater.
        """
        try:
            updater: GitHubUpdater = GitHubUpdater(
                repo_url=repo_url,
                asset_name_pattern=asset_name_pattern,
                log_callback=self.log_message,
                is_running_check=lambda: self.bridge_process
                and self.bridge_process.poll() is None,
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
                self.log_message(f"Update thread failed: {_sanitize_for_logging(e)}")
        finally:
            self.is_updating = False
            if self.view.winfo_exists():
                self.view.after(0, self.set_controls_state, True)

    def _check_local_bridge_version(self) -> None:
        """
        Checks for the local bridge version file and updates the label.
        This is thread-safe.
        """
        try:
            is_custom_path_active: bool = self.use_custom_exe_var.get()
        except tk.TclError:
            return

        def worker() -> None:
            """Worker thread to perform file I/O."""
            local_version_text: str = ""

            if is_custom_path_active:
                local_version_text = (
                    f"{translate('Local Version')}: {translate('Custom')}"
                )
            else:
                default_exe_path: str = os.path.join(self.bridge_dir, "ks_bridge.exe")
                version_file_path: str = f"{default_exe_path}.version"
                local_version_text = f"{translate('Local Version')}: N/A"

                try:
                    if not os.path.exists(default_exe_path):
                        local_version_text = (
                            f"{translate('Local Version')}: {translate('Not Found')}"
                        )
                    elif not os.path.exists(version_file_path):
                        local_version_text = (
                            f"{translate('Local Version')}: {translate('Unknown')}"
                        )
                    else:
                        with open(version_file_path, "r", encoding="utf-8") as f:
                            version: str = f.read().strip()
                        if not version:
                            version = translate("Unknown")
                        local_version_text = f"{translate('Local Version')}: {version}"
                except Exception as e:
                    logger.error(
                        "Failed to read local bridge version file: "
                        f"{_sanitize_for_logging(e)}"
                    )
                    local_version_text = (
                        f"{translate('Local Version')}: {translate('Error')}"
                    )

            if self.view.winfo_exists():
                self.view.after(0, self.local_bridge_version_var.set, local_version_text)
                self.view.after(0, self._update_update_button_logic)

        threading.Thread(target=worker, daemon=True).start()


    def activate_tab(self) -> None:
        """
        Called when the tab becomes visible.
        """
        if not self.first_activation_done:
            self.first_activation_done = True
            self.view.after(100, self._delayed_activation_check)
        
        if (
            self.latest_bridge_version_var.get()
            == f"{translate('Latest Version')}: N/A"
            and self.version_checker
        ):
            self.version_checker.check_version()
            
    def _delayed_activation_check(self) -> None:
        """
        Performs the synchronous file check and prompt after a short delay.
        """
        try:
            if not self.view.winfo_exists():
                return
                
            self._update_update_button_logic()

            file_exists: bool = os.path.exists(
                self.bridge_exe_path
            ) and os.path.exists(self.config_yaml_path)
            
            if not file_exists and not self.use_custom_exe_var.get():
                self.log_message(
                    translate(
                        "Bridge files not found. Please use the 'Update Bridge' button "
                        "to download them."
                    )
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
        path: str = filedialog.askopenfilename(title=translate(title), filetypes=filetypes)
        if path:
            var.set(sanitize_cli_arg(path))
        self._save_and_update_preview()

    def _update_log_font(self, *args: Any) -> None:
        """Update the font size in the log window."""
        self.view.update_log_font(self.log_font_size_var.get())
        self._save_settings()

    def log_message(self, message: str) -> None:
        """
        Thread-safe method to log a message to the output text widget.
        """
        try:
            if self.view.winfo_exists():
                self.main_window.after(
                    0, self.view._insert_output, f"{_sanitize_for_logging(message)}\n"
                )
        except (tk.TclError, RuntimeError):
            pass

    def read_output(self, pipe: Any) -> None:
        """
        Read output from the subprocess pipe line by line.
        This runs in a dedicated thread.
        """
        try:
            with pipe:
                for line in iter(pipe.readline, b""):
                    try:
                        if not self.view.winfo_exists():
                            break
                        self.log_message(line.decode("utf-8", errors="ignore"))
                    except (tk.TclError, RuntimeError):
                        break
        except Exception as e:
            if (
                "Bad file descriptor" not in str(e)
                and "most likely because it was closed" not in str(e)
            ):
                try:
                    if self.view.winfo_exists():
                        self.log_message(f"Error reading process output: {e}\n")
                except (tk.TclError, RuntimeError):
                    pass
        finally:
            try:
                if self.view.winfo_exists():
                    self.main_window.after(0, self.on_process_exit)
            except (tk.TclError, RuntimeError):
                pass

    def build_args_from_settings(self) -> List[str]:
        """Build the list of command-line arguments for the subprocess."""
        args: List[str] = [self.bridge_exe_path]

        key_to_arg_map: Dict[str, str] = {
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
            arg_name: Optional[str] = key_to_arg_map.get(key)
            if not arg_name:
                continue

            if key in self.key_to_enabled_var_map:
                enabled_var: ttk.BooleanVar = self.key_to_enabled_var_map[key]
                if not enabled_var.get():
                    continue

                if isinstance(var_tuple, tuple):
                    ip, port = (
                        sanitize_cli_arg(var_tuple[0].get()),
                        sanitize_cli_arg(var_tuple[1].get()),
                    )
                    val: str = f"{ip}:{port}"
                    if ip or port:
                        args.extend([arg_name, val])
                elif isinstance(var_tuple, ttk.StringVar):
                    val: str = sanitize_cli_arg(var_tuple.get())
                    if val:
                        args.extend([arg_name, val])

            elif key in self.flag_key_to_enabled_var_map:
                enabled_var = self.flag_key_to_enabled_var_map[key]
                
                if enabled_var.get():
                    val_str: str = cast(ttk.StringVar, var_tuple).get()
                    args.append(f"{arg_name}={val_str.lower()}")

        return args

    def start_bridge(self, is_autostart: bool = False) -> None:
        """Start the kaspa-stratum-bridge subprocess."""
        if self.bridge_process and self.bridge_process.poll() is None:
            self.log_message(f"{translate('Bridge is already running.')}\n")
            return

        self.update_command_preview()

        exe_path_to_check: str = self.bridge_exe_path
        exe_name: str = os.path.basename(exe_path_to_check).lower()

        # Security Check 1: Block known system shells
        if exe_name in ["cmd.exe", "powershell.exe", "pwsh.exe", "bash.exe", "sh.exe"]:
            self.log_message("Error: Executable cannot be a system shell.")
            if not is_autostart:
                messagebox.showerror(
                    translate("Invalid Input"),
                    "Selected executable is a blocked system shell."
                )
            return

        # Security Check 2: Check if it's a file (not a directory or non-existent)
        if not os.path.isfile(exe_path_to_check) or not os.path.exists(
            self.config_yaml_path
        ):
            self.log_message(
                f"{translate('Error')}: {translate('Bridge files not found.')}\n"
                f"EXE: {_sanitize_for_logging(exe_path_to_check)}\n"
                f"Config: {_sanitize_for_logging(self.config_yaml_path)}\n"
            )
            self._update_update_button_logic()
            self.log_message(
                f"{translate('Please update the bridge first using the \"Update Bridge\" button.')}\n"
            )
            if not is_autostart:
                messagebox.showerror(
                    translate("Error"),
                    translate(
                        "Please update the bridge first using the 'Update Bridge' button."
                    ),
                )
            return

        try:
            self._save_settings()
            command_list: List[str] = self.build_args_from_settings()

            if self.kaspa_addr_enabled_var.get():
                kaspa_addr_val: str = (
                    f"{sanitize_cli_arg(self.kaspa_addr_var[0].get())}:"
                    f"{sanitize_cli_arg(self.kaspa_addr_var[1].get())}"
                )
                if not validate_ip_port(kaspa_addr_val):
                    messagebox.showerror(
                        translate("Invalid Input"),
                        "Invalid Kaspa address IP/Port for -kaspa.",
                    )
                    return

            if self.stratum_port_enabled_var.get() and not validate_ip_port(
                self.stratum_port_var.get()
            ):
                messagebox.showerror(
                    translate("Invalid Input"), "Invalid Stratum IP/Port for -stratum."
                )
                return

            if self.prom_port_enabled_var.get() and not validate_ip_port(
                self.prom_port_var.get()
            ):
                messagebox.showerror(
                    translate("Invalid Input"),
                    "Invalid Prometheus IP/Port for -prom.",
                )
                return

            if (
                self.hcp_enabled_var.get()
                and self.hcp_var.get()
                and not validate_ip_port(self.hcp_var.get())
            ):
                messagebox.showerror(
                    translate("Invalid Input"),
                    "Invalid Health Check IP/Port for -hcp.",
                )
                return

            working_dir: str = os.path.dirname(self.config_yaml_path)

            self.log_message(f"--- {translate('Starting Bridge')} ---")
            self.log_message(
                f"{translate('Working Directory')}:\n{_sanitize_for_logging(working_dir)}\n"
            )
            self.log_message(f"{translate('Command')}:\n{' '.join(command_list)}\n")
            self.log_message("...\n")

            startupinfo: subprocess.STARTUPINFO = subprocess.STARTUPINFO()
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
                f"Failed to start Kaspa Bridge: {_sanitize_for_logging(e)}\n"
            )
            self.bridge_process = None

    def on_process_exit(self) -> None:
        """Callback function when the subprocess terminates."""
        try:
            self.log_message(f"\n--- {translate('Process Terminated')} ---\n")
            if self.view.start_button.winfo_exists():
                self.view.start_button.config(state="normal")
            if self.view.stop_button.winfo_exists():
                self.view.stop_button.config(state="disabled")
        except (tk.TclError, RuntimeError):
            pass
        self.bridge_process = None
        try:
            if self.view.winfo_exists():
                self.view.after(0, self.set_controls_state, True)
        except (tk.TclError, RuntimeError):
            pass

    def stop_bridge(self) -> None:
        """Stop the running subprocess and its children using psutil."""
        if self.bridge_process and self.bridge_process.poll() is None:
            try:
                self.log_message(translate("Stopping Kaspa Bridge...") + "\n")

                # Get the process and its children
                parent: psutil.Process = psutil.Process(self.bridge_process.pid)
                children: List[psutil.Process] = parent.children(recursive=True)

                # Terminate the children first
                for child in children:
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                
                # Terminate the parent process
                self.bridge_process.terminate()

                # Wait for processes to exit
                psutil.wait_procs(children, timeout=3)

            except psutil.NoSuchProcess:
                 self.log_message(translate("Bridge is not running.") + "\n")

            except Exception as e:
                self.log_message(
                    f"Error while stopping bridge: {_sanitize_for_logging(e)}\n"
                )
            finally:
                # Fallback check before UI update to prevent TclError on shutdown
                try:
                    if self.view.winfo_exists():
                        self.on_process_exit()
                except tk.TclError:
                    pass

        else:
            self.log_message(f"{translate('Bridge is not running.')}\n")

    def _delete_bridge_files(self) -> None:
        """Delete the bridge exe, config, and version files."""
        try:
            safe_dir_local: str = os.path.abspath(
                os.path.join(os.getenv("LOCALAPPDATA", ""), "KaspaGateway")
            )
            safe_dir_roaming: str = os.path.abspath(
                os.path.join(os.getenv("APPDATA", ""), "KaspaGateway")
            )

            target_exe_path: str = os.path.abspath(self.bridge_exe_path)
            target_config_path: str = os.path.abspath(self.config_yaml_path)
            target_version_path: str = f"{target_exe_path}.version"

            def is_path_safe(path_to_check: str) -> bool:
                path_to_check = os.path.abspath(path_to_check)
                is_in_local: bool = bool(safe_dir_local and path_to_check.startswith(safe_dir_local))
                is_in_roaming: bool = bool(safe_dir_roaming and path_to_check.startswith(safe_dir_roaming))
                return is_in_local or is_in_roaming

            is_safe: bool = (
                is_path_safe(target_exe_path)
                and is_path_safe(target_config_path)
                and is_path_safe(target_version_path)
            )

            if not is_safe:
                self.log_message(
                    translate("Error: Deletion path is outside the allowed directory.")
                )
                messagebox.showerror(
                    translate("Error"),
                    translate("Deletion outside user data directory is not allowed."),
                )
                return
        except Exception as e:
            self.log_message(f"Error during security check: {_sanitize_for_logging(e)}")
            return

        if self.bridge_process and self.bridge_process.poll() is None:
            self.log_message(translate("Error: Process is running."))
            messagebox.showerror(
                translate("Error"), translate("Error: Process is running.")
            )
            return

        exe_path_to_delete: str = self.bridge_exe_path
        config_path_to_delete: str = self.config_yaml_path
        version_file_path: str = f"{exe_path_to_delete}.version"

        if (
            not os.path.exists(exe_path_to_delete)
            and not os.path.exists(config_path_to_delete)
            and not os.path.exists(version_file_path)
        ):
            ToastNotification(
                title=translate("Delete Files"),
                message=translate("Files not found."),
                bootstyle=INFO,
                duration=3000,
            ).show_toast()
            return

        msg: str = (
            f"{translate('Are you sure you want to delete these files? This cannot be undone.')}\n\n"
            f"- {exe_path_to_delete}\n"
            f"- {config_path_to_delete}\n"
            f"- {version_file_path}"
        )
        if not messagebox.askyesno(translate("Confirm File Deletion"), msg):
            return

        try:
            if os.path.exists(exe_path_to_delete):
                os.remove(exe_path_to_delete)
                self.log_message(f"Deleted: {_sanitize_for_logging(exe_path_to_delete)}")
            if os.path.exists(config_path_to_delete):
                os.remove(config_path_to_delete)
                self.log_message(
                    f"Deleted: {_sanitize_for_logging(config_path_to_delete)}"
                )
            if os.path.exists(version_file_path):
                os.remove(version_file_path)
                self.log_message(
                    f"Deleted: {_sanitize_for_logging(version_file_path)}"
                )

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
            logger.error(f"Failed to delete bridge files: {e}")
            self.log_message(
                f"{translate('Failed to delete files. Check logs.')}: {_sanitize_for_logging(e)}"
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
        
        is_running: bool = self.bridge_process and self.bridge_process.poll() is None

        try:
            self.view.start_button.config(
                state="disabled" if (is_running or not active) else "normal"
            )
            self.view.stop_button.config(
                state="normal" if (is_running and active) else "disabled"
            )
            
            self._update_update_button_logic(active)
            
            self.view.reset_button.config(state="normal" if active else "disabled")
            self.view.delete_files_button.config(
                state="normal" if active and not is_running else "disabled"
            )
        except tk.TclError:
            pass

    def re_translate(self) -> None:
        """Update all translatable strings in the UI."""
        self.view.re_translate_widgets()
        self._check_local_bridge_version()

        if (
            "N/A" in self.latest_bridge_version_var.get()
            or "Error" in self.latest_bridge_version_var.get()
            or "..." in self.latest_bridge_version_var.get()
        ):
            if self.version_checker:
                self.version_checker.check_version()
        else:
            current_version: str = self.latest_bridge_version_var.get().split(":")[-1].strip()
            self.latest_bridge_version_var.set(
                f"{translate('Latest Version')}: {current_version}"
            )

        if f"{translate('Updated')}:" not in self.latest_bridge_date_var.get():
            current_date: str = self.latest_bridge_date_var.get().split(":")[-1].strip()
            if current_date and current_date != "N/A" and current_date != "...":
                self.latest_bridge_date_var.set(f"{translate('Updated')}: {current_date}")
