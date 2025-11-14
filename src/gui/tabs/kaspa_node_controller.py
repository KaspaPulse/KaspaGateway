#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Contains the Controller (logic and state) for the KaspaNodeTab (View).
This file handles all business logic, state management, and subprocess
interactions for the kaspad node.
"""

from __future__ import annotations
import logging
import os
import platform
import re
import signal
import subprocess
import threading
import tkinter as tk
from tkinter import END, DISABLED, NORMAL, filedialog, messagebox
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, Tuple, cast
from types import FrameType

import psutil
import ttkbootstrap as ttk
from ttkbootstrap.constants import DISABLED, INFO, SUCCESS
from ttkbootstrap.toast import ToastNotification

from src.gui.updater import DownloadProgressWindow, GitHubUpdater, VersionChecker
from src.utils.i18n import translate
from src.utils.validation import (
    _sanitize_for_logging,
    sanitize_cli_arg,
    validate_ip_port,
    validate_url,
)
from src.gui.config_manager import ConfigManager

if TYPE_CHECKING:
    from src.gui.main_window import MainWindow
    from .kaspa_node_tab import KaspaNodeTab

logger = logging.getLogger(__name__)


class KaspaNodeController:
    """
    The Controller class for the Kaspa Node Tab.
    Manages all state and logic, interacting with the KaspaNodeTab (View).
    """

    # --- Type Hint Declarations ---
    view: "KaspaNodeTab"
    main_window: "MainWindow"
    config_manager: ConfigManager
    node_process: Optional[subprocess.Popen[bytes]]
    option_vars: Dict[str, Tuple[ttk.BooleanVar, Optional[ttk.StringVar], ...]]
    is_updating: bool
    all_vars_list: List[Tuple[Any, str, Any]]
    version_checker: Optional[VersionChecker]
    first_activation_done: bool
    bin_dir: str
    node_exe_path: str
    network_var: ttk.StringVar
    loglevel_var: ttk.StringVar
    log_font_size_var: ttk.IntVar
    autostart_var: ttk.BooleanVar
    use_custom_exe_var: ttk.BooleanVar
    custom_exe_path_var: ttk.StringVar
    use_custom_url_var: ttk.BooleanVar
    custom_url_var: ttk.StringVar
    custom_url_exe_path_var: ttk.StringVar
    local_node_version_var: ttk.StringVar
    latest_node_version_var: ttk.StringVar
    latest_node_date_var: ttk.StringVar
    command_preview_var: ttk.StringVar
    # --- End Type Hint Declarations ---

    def __init__(
        self,
        view: "KaspaNodeTab",
        main_window: "MainWindow",
        config_manager: ConfigManager,
    ) -> None:
        self.view: "KaspaNodeTab" = view
        self.main_window: "MainWindow" = main_window
        self.config_manager: ConfigManager = config_manager

        self.node_process: Optional[subprocess.Popen[bytes]] = None
        self.option_vars: Dict[str, Tuple[ttk.BooleanVar, Optional[ttk.StringVar], ...]] = {}
        self.is_updating: bool = False
        self.all_vars_list: List[Tuple[Any, str, Any]] = []
        self.version_checker: Optional[VersionChecker] = None
        self.first_activation_done: bool = False

        self.bin_dir: str = os.path.join(
            os.getenv(
                "LOCALAPPDATA",
                self.config_manager.get_config().get("paths", {}).get("database", ""),
            ),
            "KaspaGateway",
            "bin",
        )
        os.makedirs(self.bin_dir, exist_ok=True)
        self.node_exe_path: str = os.path.join(self.bin_dir, "kaspad.exe")

    def _get_default_options(self) -> Dict[str, Dict[str, Any]]:
        """Returns a dictionary of the default kaspad options."""
        return {
            "configfile": {"enabled": False, "value1": ""},
            "appdir": {"enabled": False, "value1": ""},
            "logdir": {"enabled": False, "value1": ""},
            "nologfiles": {"enabled": True},
            "async-threads": {"enabled": False, "value1": "16"},
            "rpclisten": {"enabled": True, "value1": "127.0.0.1", "value2": "16110"},
            "rpclisten-borsh": {
                "enabled": True,
                "value1": "127.0.0.1",
                "value2": "17110",
            },
            "rpclisten-json": {
                "enabled": True,
                "value1": "127.0.0.1",
                "value2": "18110",
            },
            "unsaferpc": {"enabled": False},
            "connect": {"enabled": False, "value1": "", "value2": ""},
            "addpeer": {"enabled": False, "value1": "", "value2": ""},
            "listen": {"enabled": True, "value1": "0.0.0.0", "value2": "16111"},
            "outpeers": {"enabled": True, "value1": "8"},
            "maxinpeers": {"enabled": True, "value1": "128"},
            "rpcmaxclients": {"enabled": True, "value1": "128"},
            "reset-db": {"enabled": False},
            "enable-unsynced-mining": {"enabled": False},
            "utxoindex": {"enabled": True},
            "max-tracked-addresses": {"enabled": False, "value1": "0"},
            "netsuffix": {"enabled": False, "value1": ""},
            "archival": {"enabled": False},
            "sanity": {"enabled": False},
            "yes": {"enabled": True},
            "uacomment": {"enabled": False, "value1": ""},
            "externalip": {"enabled": False, "value1": "", "value2": ""},
            "perf-metrics": {"enabled": True},
            "perf-metrics-interval-sec": {"enabled": False, "value1": ""},
            "disable-upnp": {"enabled": False},
            "nodnsseed": {"enabled": False},
            "nogrpc": {"enabled": False},
            "ram-scale": {"enabled": False, "value1": ""},
            "retention-period-days": {"enabled": False, "value1": ""},
        }

    def define_variables(self) -> None:
        """Initialize all ttk variables for the GUI controls."""
        self.network_var: ttk.StringVar = ttk.StringVar(value="mainnet")
        self.loglevel_var: ttk.StringVar = ttk.StringVar(value="info")
        self.log_font_size_var: ttk.IntVar = ttk.IntVar(value=9)
        self.autostart_var: ttk.BooleanVar = ttk.BooleanVar(value=False)

        self.use_custom_exe_var: ttk.BooleanVar = ttk.BooleanVar(value=False)
        self.custom_exe_path_var: ttk.StringVar = ttk.StringVar(value="")

        self.use_custom_url_var: ttk.BooleanVar = ttk.BooleanVar(value=False)
        self.custom_url_var: ttk.StringVar = ttk.StringVar(value="")
        self.custom_url_exe_path_var: ttk.StringVar = ttk.StringVar(value="kaspad.exe")

        self.local_node_version_var: ttk.StringVar = ttk.StringVar(
            value=f"{translate('Local Version')}: N/A"
        )
        self.latest_node_version_var: ttk.StringVar = ttk.StringVar(
            value=f"{translate('Latest Version')}: N/A"
        )
        self.latest_node_date_var: ttk.StringVar = ttk.StringVar(
            value=f"{translate('Updated')}: N/A"
        )

        self.command_preview_var: ttk.StringVar = ttk.StringVar()

        self.option_vars: Dict[str, Tuple[ttk.BooleanVar, Optional[ttk.StringVar], ...]] = {}
        defaults: Dict[str, Dict[str, Any]] = self._get_default_options()

        for key, values in defaults.items():
            check_var: ttk.BooleanVar = ttk.BooleanVar(value=values["enabled"])
            item_vars: List[Any] = [check_var]

            if "value1" in values:
                val1_var: ttk.StringVar = ttk.StringVar(value=values["value1"])
                item_vars.append(val1_var)
                if "value2" in values:
                    val2_var: ttk.StringVar = ttk.StringVar(value=values["value2"])
                    item_vars.append(val2_var)

            # Ensure flag-only options have length 2 (e.g., (BoolVar, None)) 
            # to prevent ValueError on unpacking in the view.
            if len(item_vars) == 1:
                 item_vars.append(None)
                 
            self.option_vars[key] = tuple(item_vars)

        self.all_vars_list: List[Tuple[Any, str, Any]] = [
            (self.autostart_var, "autostart_var", False),
            (self.use_custom_exe_var, "use_custom_exe_var", False),
            (self.custom_exe_path_var, "custom_exe_path_var", ""),
            (self.use_custom_url_var, "use_custom_url_var", False),
            (self.custom_url_var, "custom_url_var", ""),
            (
                self.custom_url_exe_path_var,
                "custom_url_exe_path_var",
                "kaspad.exe",
            ),
        ]

        self.version_checker: VersionChecker = VersionChecker(
            asset_name="kaspad.exe",
            version_var=self.latest_node_version_var,
            date_var=self.latest_node_date_var,
            log_callback=self.log_message,
            repo_url="https://api.github.com/repos/kaspanet/rusty-kaspa/releases/latest",
        )

    def _load_settings(self) -> None:
        """Load settings from the config manager into the ttk variables."""
        node_config: Dict[str, Any] = self.config_manager.get_config().get(
            "kaspa_node", {}
        )
        self.network_var.set(node_config.get("network_var", "mainnet"))
        self.loglevel_var.set(node_config.get("loglevel_var", "info"))
        self.log_font_size_var.set(node_config.get("log_font_size_var", 9))

        for var, key, default in self.all_vars_list:
            var.set(node_config.get(key, default))

        defaults: Dict[str, Dict[str, Any]] = self._get_default_options()
        ip_port_keys: List[str] = [
            "rpclisten",
            "rpclisten-borsh",
            "rpclisten-json",
            "listen",
            "connect",
            "addpeer",
            "externalip",
        ]

        # Load option and IP/Port values
        for key in self.option_vars:
            item_tuple: Tuple[ttk.BooleanVar, Optional[ttk.StringVar], ...] = self.option_vars[key]
            if len(item_tuple) > 1 and isinstance(item_tuple[1], ttk.StringVar):
                if key in ip_port_keys:
                    key_config: Dict[str, Any] = node_config.get(key, {})
                    saved_value: Optional[str] = key_config.get("value", None)

                    if saved_value is not None:
                        validation_result: Optional[Tuple[str, str]] = validate_ip_port(saved_value)
                        if validation_result:
                            val1_var: ttk.StringVar = item_tuple[1]
                            val2_var: Optional[ttk.StringVar] = (
                                item_tuple[2] if len(item_tuple) > 2 else None
                            )
                            ip, port = validation_result
                            val1_var.set(ip)
                            if val2_var:
                                val2_var.set(port)
                            item_tuple[0].set(
                                key_config.get(
                                    "enabled",
                                    defaults.get(key, {}).get("enabled", False),
                                )
                            )
                            continue

        # Load all other options
        for key, item_tuple in self.option_vars.items():
            key_config: Dict[str, Any] = node_config.get(key, {})
            check_var: ttk.BooleanVar = item_tuple[0]

            default_enabled: bool = defaults.get(key, {}).get("enabled", False)
            check_var.set(key_config.get("enabled", default_enabled))

            if len(item_tuple) > 1 and isinstance(item_tuple[1], ttk.StringVar):
                val1_var: ttk.StringVar = item_tuple[1]
                val2_var: Optional[ttk.StringVar] = (
                    item_tuple[2]
                    if len(item_tuple) > 2
                    and isinstance(item_tuple[2], ttk.StringVar)
                    else None
                )

                default_val1: str = defaults.get(key, {}).get("value1", "")
                default_val2: str = defaults.get(key, {}).get("value2", "")

                saved_value = key_config.get("value", None)

                # Skip IP/Port keys we already handled (unless they were invalid)
                if key in ip_port_keys:
                    if saved_value is not None and validate_ip_port(saved_value):
                        continue

                if saved_value is not None:
                    val1_var.set(saved_value)
                    if val2_var:
                        val2_var.set(default_val2)
                else:
                    val1_var.set(default_val1)
                    if val2_var:
                        val2_var.set(default_val2)

        self.update_command_preview()

    def controller_load_settings(self) -> None:
        """Proxy function for the view to call."""
        self._load_settings()

    def _save_settings(self, *args: Any) -> None:
        """Save the current state of ttk variables to the config manager."""
        node_config: Dict[str, Any] = self.config_manager.get_config().get("kaspa_node", {})

        node_config["network_var"] = self.network_var.get()
        node_config["loglevel_var"] = self.loglevel_var.get()
        node_config["log_font_size_var"] = self.log_font_size_var.get()

        for var, key, _ in self.all_vars_list:
            node_config[key] = var.get()

        for key, item_tuple in self.option_vars.items():
            key_config: Dict[str, Any] = {}
            check_var: ttk.BooleanVar = item_tuple[0]

            key_config["enabled"] = check_var.get()

            if len(item_tuple) > 1 and isinstance(item_tuple[1], ttk.StringVar):
                val1_var: ttk.StringVar = item_tuple[1]
                val2_var: Optional[ttk.StringVar] = None

                if len(item_tuple) > 2 and isinstance(item_tuple[2], ttk.StringVar):
                    val2_var = item_tuple[2]

                val1_value: str = sanitize_cli_arg(val1_var.get())
                val2_value: Optional[str] = sanitize_cli_arg(val2_var.get()) if val2_var else None

                value: str = val1_value
                if val1_value and val2_value:
                    value = f"{val1_value}:{val2_value}"

                if key in [
                    "rpclisten",
                    "rpclisten-borsh",
                    "rpclisten-json",
                    "listen",
                    "connect",
                    "addpeer",
                    "externalip",
                ]:
                    if check_var.get() and not validate_ip_port(value):
                        default_opts: Dict[str, Any] = self._get_default_options().get(key, {})
                        default_val1: str = default_opts.get("value1", "")
                        default_val2: str = default_opts.get("value2", "")
                        
                        messagebox.showerror(
                            translate("Invalid Input"),
                            f"{translate('Invalid Input')}: --{key}. "
                            f"{translate('Example')}: 127.0.0.1:16110 or :16110",
                        )
                        value = default_val1
                        if val2_var:
                            value += f":{default_val2}"
                        
                        # Revert UI elements
                        val1_var.set(default_val1)
                        if val2_var:
                            val2_var.set(default_val2)
                        
                key_config["value"] = value

            node_config[key] = key_config

        self.config_manager.get_config()["kaspa_node"] = node_config
        self.config_manager.save_config(self.config_manager.get_config())

    def _save_and_update_preview(self, *args: Any) -> None:
        """Wrapper to update preview and save settings, for use in tracers."""
        self.update_command_preview()
        self._save_settings()

    def _add_tracers(self) -> None:
        """Add 'write' tracers to all variables to auto-save and update."""
        self.network_var.trace_add("write", self._save_and_update_preview)
        self.loglevel_var.trace_add("write", self._save_and_update_preview)

        for var, key, _ in self.all_vars_list:
            if key not in ["use_custom_exe_var", "use_custom_url_var"]:
                var.trace_add("write", self._save_and_update_preview)

        for check_var, val_var, *rest in self.option_vars.values():
            if isinstance(check_var, ttk.BooleanVar):
                check_var.trace_add("write", self._save_and_update_preview)
                check_var.trace_add(
                    "write", lambda *a: self._update_all_entry_states()
                )
            if val_var and isinstance(val_var, ttk.StringVar):
                val_var.trace_add("write", self._save_and_update_preview)

            if len(rest) > 0 and rest[0] and isinstance(rest[0], ttk.StringVar):
                rest[0].trace_add("write", self._save_and_update_preview)
        
        # Add tracers for custom path toggles
        self.use_custom_exe_var.trace_add("write", self._on_custom_exe_toggled)
        self.use_custom_url_var.trace_add("write", self._on_custom_url_toggled)

    def update_command_preview(self, *args: Any) -> None:
        """
        Update the command preview text box based on current settings.
        This function is now the single source of truth for self.node_exe_path.
        """
        if self.use_custom_exe_var.get() and self.custom_exe_path_var.get():
            self.node_exe_path = self.custom_exe_path_var.get()
        else:
            self.node_exe_path = os.path.join(self.bin_dir, "kaspad.exe")

        if hasattr(self, "command_preview_var"):
            command_list: List[str] = self.build_args_from_settings()
            command_str: str = " ".join(command_list)
            self.command_preview_var.set(command_str)

            if hasattr(self.view, "command_preview_text"):
                try:
                    self.view.command_preview_text.text.config(state="normal")
                    self.view.command_preview_text.text.delete("1.0", END)
                    self.view.command_preview_text.text.insert("1.0", command_str)
                    self.view.command_preview_text.text.config(state="disabled")
                except tk.TclError:
                    pass

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

        logger.info("Resetting node options to default.")
        defaults: Dict[str, Dict[str, Any]] = self._get_default_options()

        for key, default_values in defaults.items():
            if key in self.option_vars:
                current_vars: Tuple[ttk.BooleanVar, Optional[ttk.StringVar], ...] = self.option_vars[key]

                current_vars[0].set(default_values.get("enabled", False))

                if ("value1" in default_values and len(current_vars) > 1 and 
                    isinstance(current_vars[1], ttk.StringVar)):
                    current_vars[1].set(default_values["value1"])

                if ("value2" in default_values and len(current_vars) > 2 and 
                    isinstance(current_vars[2], ttk.StringVar)):
                    current_vars[2].set(default_values["value2"])

        self.network_var.set("mainnet")
        self.loglevel_var.set("info")
        self.log_font_size_var.set(9)

        for var, _, default in self.all_vars_list:
            var.set(default)

        self._update_all_entry_states()
        self._save_and_update_preview()
        self._update_update_button_logic()

        ToastNotification(
            title=translate("Success"),
            message=translate("Node options have been reset to default."),
            bootstyle=SUCCESS,
            duration=3000,
        ).show_toast()

    def _on_check_toggle(self, key: str) -> None:
        """Called when any option checkbox is toggled."""
        if key not in self.option_vars:
            return

        item_tuple: Tuple[ttk.BooleanVar, Optional[ttk.StringVar], ...] = self.option_vars[key]
        check_var: ttk.BooleanVar = item_tuple[0]
        is_checked: bool = check_var.get()

        if item_tuple[1] is not None:
            try:
                if len(item_tuple) == 5:
                    label: ttk.Label = cast(ttk.Label, item_tuple[3])
                    ip_entry: ttk.Entry = cast(ttk.Entry, item_tuple[4])
                    if is_checked:
                        ip_entry.config(state="normal")
                        label.config(bootstyle="default")
                    else:
                        ip_entry.config(state="disabled")
                        label.config(bootstyle="secondary")
                elif len(item_tuple) == 8:
                    label: ttk.Label = cast(ttk.Label, item_tuple[4])
                    ip_entry: ttk.Entry = cast(ttk.Entry, item_tuple[5])
                    colon_label: ttk.Label = cast(ttk.Label, item_tuple[6])
                    port_entry: ttk.Entry = cast(ttk.Entry, item_tuple[7])
                    if is_checked:
                        ip_entry.config(state="normal")
                        port_entry.config(state="normal")
                        label.config(bootstyle="default")
                        colon_label.config(bootstyle="default")
                    else:
                        ip_entry.config(state="disabled")
                        port_entry.config(state="disabled")
                        label.config(bootstyle="secondary")
                        colon_label.config(bootstyle="secondary")
            except (tk.TclError, IndexError):
                pass

        self._save_and_update_preview()

    def _update_all_entry_states(self) -> None:
        """
        Iterates over all option_vars and sets the state (enabled/disabled)
        of their corresponding entry widgets based on the checkbox state.
        """
        for key, item_tuple in self.option_vars.items():
            if item_tuple[1] is not None:
                check_var: ttk.BooleanVar = item_tuple[0]
                is_checked: bool = check_var.get()

                try:
                    if len(item_tuple) == 5:
                        label: ttk.Label = cast(ttk.Label, item_tuple[3])
                        ip_entry: ttk.Entry = cast(ttk.Entry, item_tuple[4])
                        if is_checked:
                            ip_entry.config(state="normal")
                            label.config(bootstyle="default")
                        else:
                            ip_entry.config(state="disabled")
                            label.config(bootstyle="secondary")

                    elif len(item_tuple) == 8:
                        label: ttk.Label = cast(ttk.Label, item_tuple[4])
                        ip_entry: ttk.Entry = cast(ttk.Entry, item_tuple[5])
                        colon_label: ttk.Label = cast(ttk.Label, item_tuple[6])
                        port_entry: ttk.Entry = cast(ttk.Entry, item_tuple[7])
                        if is_checked:
                            ip_entry.config(state="normal")
                            port_entry.config(state="normal")
                            label.config(bootstyle="default")
                            colon_label.config(bootstyle="default")
                        else:
                            ip_entry.config(state="disabled")
                            port_entry.config(state="disabled")
                            label.config(bootstyle="secondary")
                            colon_label.config(bootstyle="secondary")

                except (tk.TclError, IndexError):
                    pass

    def _browse_file(
        self,
        var: ttk.StringVar,
        title: str,
        filetypes: List[Tuple[str, str]],
    ) -> None:
        """Open a file dialog and set the variable to the selected path."""
        path: str = filedialog.askopenfilename(title=translate(title), filetypes=filetypes)
        if path:
            var.set(sanitize_cli_arg(path))
            self._save_and_update_preview()


    def _update_update_button_logic(self, *args: Any) -> None:
        """
        Updates the Update/Download button text AND state.
        """
        if not hasattr(self.view, "update_button"):
            return

        self.update_command_preview()
        file_exists: bool = os.path.exists(self.node_exe_path)
        is_custom_url: bool = self.use_custom_url_var.get()
        is_custom_exe: bool = self.use_custom_exe_var.get()

        if is_custom_exe:
            self.view.update_button.config(text=translate("Update Node"))
        elif is_custom_url:
            self.view.update_button.config(text=translate("Download File"))
        elif not file_exists:
            self.view.update_button.config(text=translate("Download Node"))
        else:
            self.view.update_button.config(text=translate("Update Node"))

        is_app_busy: bool = (
            self.main_window.transaction_manager.is_fetching
            or self.main_window.is_exporting
            or self.is_updating
        )

        is_globally_active: bool = True
        if args and isinstance(args[0], bool):
            is_globally_active = args[0]

        if is_app_busy or is_custom_exe or not is_globally_active:
            self.view.update_button.config(state="disabled")
        else:
            self.view.update_button.config(state="normal")

    def _on_custom_exe_toggled(self, *args: Any) -> None:
        """Tracer for 'Use Custom kaspad.exe' checkbox."""
        self._toggle_entry_state(
            self.use_custom_exe_var, [self.view.exe_entry, self.view.exe_browse]
        )

        if self.use_custom_exe_var.get():
            self.use_custom_url_var.set(False)

        self._save_and_update_preview()

        is_active: bool = not (
            self.main_window.transaction_manager.is_fetching
            or self.main_window.is_exporting
        )
        self.set_controls_state(is_active)

    def _on_custom_url_toggled(self, *args: Any) -> None:
        """Tracer for 'Use Custom Download URL' checkbox."""
        self._toggle_entry_state(
            self.use_custom_url_var,
            [self.view.url_entry, self.view.url_path_label, self.view.url_path_entry],
        )

        if self.use_custom_url_var.get():
            self.use_custom_exe_var.set(False)

        self._save_and_update_preview()

        is_active: bool = not (
            self.main_window.transaction_manager.is_fetching
            or self.main_window.is_exporting
        )
        self.set_controls_state(is_active)

    def _toggle_entry_state(
        self, enabled_var: ttk.BooleanVar, entries: List[tk.Widget]
    ) -> None:
        """Enable or disable a list of widgets based on a BooleanVar."""
        new_state: str = "normal" if enabled_var.get() else "disabled"
        for entry in entries:
            try:
                if entry.winfo_exists():
                    entry.config(state=new_state)
            except tk.TclError:
                pass

    def _prompt_for_download_path_and_start(self) -> None:
        """
        Shows the Yes/No/Cancel prompt to select a download path.
        """
        default_path: str = self.bin_dir or os.getcwd()

        msg_template: str = (
            translate(
                "kaspad.exe not found. This component is required to run a local "
                "node. Would you like to download it now?"
            )
            + f"\n\n- {translate('Click Yes to download to default location:')}\n{default_path}\n\n"
            + f"- {translate('Click No to select a custom location.')}"
        )

        if self.use_custom_url_var.get():
            msg_template = (
                translate("Download from custom URL?")
                + f"\n\n- {translate('Click Yes to download to default location:')}\n{default_path}\n\n"
                + f"- {translate('Click No to select a custom location.')}"
            )

        user_choice: Optional[bool] = messagebox.askyesnocancel(translate("Update Node"), msg_template)

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
            self.bin_dir = chosen_path
            self.start_node_update()
        else:
            self._update_update_button_logic()

    def _on_update_button_pressed(self) -> None:
        """
        Decides whether to prompt for a path or just update.
        """
        is_custom_url: bool = self.use_custom_url_var.get()
        file_exists: bool = os.path.exists(self.node_exe_path)

        is_download_action: bool = is_custom_url or not file_exists

        if is_download_action:
            self._prompt_for_download_path_and_start()
        else:
            self.start_node_update()

    def start_node_update(self) -> None:
        """
        Performs the update/download. Assumes the path has been set.
        """
        log_text: str = (
            translate("Download File")
            if self.use_custom_url_var.get()
            else translate("Update Node")
        )
        self.log_message(f"--- {log_text} ---")

        self.is_updating = True
        self.set_controls_state(False)

        self.update_command_preview()

        repo_url: str = (
            "https://api.github.com/repos/kaspanet/rusty-kaspa/releases/latest"
        )
        asset_name_pattern: str = r"rusty-kaspa-v[\d\.]+-win64\.zip$"
        target_file_in_zip: str = "kaspad.exe"

        if self.use_custom_url_var.get() and self.custom_url_var.get():
            repo_url = self.custom_url_var.get()
            asset_name_pattern = r"\.zip$"
            target_file_in_zip = self.custom_url_exe_path_var.get()

            if (
                not re.match(r"^[\w\.\-/]+$", target_file_in_zip)
                or ".." in target_file_in_zip
            ):
                messagebox.showerror(
                    translate("Invalid Input"), "Invalid file path in zip."
                )
                self.is_updating = False
                self.set_controls_state(True)
                return

            if not repo_url.endswith(".zip") and "api.github.com" not in repo_url:
                if not validate_url(repo_url) or not repo_url.endswith(".zip"):
                    messagebox.showerror(
                        translate("Invalid Input"),
                        "Custom URL must be a direct link to a .zip file.",
                    )
                    self.is_updating = False
                    self.set_controls_state(True)
                    return

        progress_window: DownloadProgressWindow = DownloadProgressWindow(
            self.main_window, title=translate("Update Node")
        )

        def run_update_thread() -> None:
            """Worker thread function to run the GitHubUpdater."""
            try:
                updater: GitHubUpdater = GitHubUpdater(
                    repo_url=repo_url,
                    asset_name_pattern=asset_name_pattern,
                    target_file_in_zip=target_file_in_zip,
                    local_path=self.node_exe_path,
                    log_callback=self.log_message,
                    is_running_check=lambda: self.node_process
                    and self.node_process.poll() is None,
                    success_callback=self._check_local_kaspad_version,
                    cancel_event=progress_window.cancel_event,
                    show_success_popup=False,
                    progress_window=progress_window,
                )
                updater.run_update()

            except Exception as e:
                if "Download cancelled" not in str(e):
                    self.log_message(f"Update thread failed: {e}")
            finally:
                self.is_updating = False
                if self.view.winfo_exists():
                    is_active: bool = not (
                        self.main_window.transaction_manager.is_fetching
                        or self.main_window.is_exporting
                    )
                    self.view.after(0, self.set_controls_state, is_active)

        threading.Thread(target=run_update_thread, daemon=True).start()

    def _check_local_kaspad_version(
        self, prompt_if_missing: bool = False
    ) -> None:
        """
        Checks for the local kaspad version file and updates the label.
        This runs in a worker thread.
        """

        def worker() -> None:
            """Worker thread to perform file I/O."""
            version_file_path: str = f"{self.node_exe_path}.version"
            local_version: str = f"{translate('Local Version')}: N/A"
            file_exists: bool = os.path.exists(self.node_exe_path)

            try:
                if self.use_custom_exe_var.get():
                     local_version = f"{translate('Local Version')}: {translate('Custom')}"
                elif not file_exists:
                    local_version = (
                        f"{translate('Local Version')}: {translate('Not Found')}"
                    )
                    if prompt_if_missing and not self.use_custom_exe_var.get():
                        if self.view.winfo_exists():
                            self.view.after(
                                0, self._prompt_for_download_path_and_start
                            )
                elif not os.path.exists(version_file_path):
                    local_version = (
                        f"{translate('Local Version')}: {translate('Unknown')}"
                    )
                else:
                    with open(version_file_path, "r", encoding="utf-8") as f:
                        version: str = f.read().strip()
                    if not version:
                        version = translate("Unknown")
                    local_version = f"{translate('Local Version')}: {version}"
            except Exception as e:
                logger.error(
                    f"Failed to read local kaspad version file: {_sanitize_for_logging(e)}"
                )
                local_version = (
                    f"{translate('Local Version')}: {translate('Error')}"
                )
            finally:
                if self.view.winfo_exists():
                    self.view.after(
                        0, self.local_node_version_var.set, local_version
                    )
                    self.view.after(0, self._update_update_button_logic)

        threading.Thread(target=worker, daemon=True).start()

    def activate_tab(self) -> None:
        """
        Called when the tab becomes visible.
        """
        if not self.first_activation_done:
            self.first_activation_done = True
            self.view.after(100, self._delayed_activation_check)

        self.update_db_size()
        if (
            self.latest_node_version_var.get()
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
            file_exists: bool = os.path.exists(self.node_exe_path)

            if not file_exists and not self.use_custom_exe_var.get():
                self.log_message(
                    translate(
                        "kaspad.exe not found. Please use the 'Download Node' button "
                        "to download it."
                    )
                )

                default_path: str = self.bin_dir or os.getcwd()
                msg: str = (
                    translate(
                        "kaspad.exe not found. This component is required to run a local "
                        "node. Would you like to download it now?"
                    )
                    + f"\n\n- {translate('Click Yes to download to default location:')}\n{default_path}\n\n"
                    + f"- {translate('Click No to select a custom location.')}"
                )

                user_choice: Optional[bool] = messagebox.askyesnocancel(translate("Update Node"), msg)

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
                    self.bin_dir = chosen_path
                    self.start_node_update()
                else:
                    self._update_update_button_logic()

            self._check_local_kaspad_version(prompt_if_missing=False)

        except tk.TclError:
            pass
        except Exception as e:
            logger.error(f"Error during delayed activation check: {e}")

    def log_message(self, message: str) -> None:
        """Thread-safe method to log a message to the output text widget."""
        try:
            if self.view.winfo_exists():
                self.main_window.after(0, self.view._insert_output, message)
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
        args: List[str] = [self.node_exe_path]

        net: str = self.network_var.get()
        if net == "testnet":
            args.append("--testnet")
            netsuffix_check, netsuffix_val, *_ = self.option_vars["netsuffix"]
            if netsuffix_check.get() and sanitize_cli_arg(netsuffix_val.get()):
                args.append(f"--netsuffix={sanitize_cli_arg(netsuffix_val.get())}")
        elif net == "devnet":
            args.append("--devnet")
        elif net == "simnet":
            args.append("--simnet")

        if self.loglevel_var.get() != "info":
            args.append(f"--loglevel={self.loglevel_var.get()}")

        for key, item_tuple in self.option_vars.items():
            if key == "netsuffix" and net == "testnet":
                continue

            check_var: ttk.BooleanVar = item_tuple[0]

            if check_var.get():
                if len(item_tuple) > 1 and isinstance(item_tuple[1], ttk.StringVar):
                    val1_var: ttk.StringVar = item_tuple[1]
                    val2_var: Optional[ttk.StringVar] = item_tuple[2] if len(item_tuple) > 2 and isinstance(item_tuple[2], ttk.StringVar) else None

                    val1_value: str = sanitize_cli_arg(val1_var.get())
                    val2_value: Optional[str] = sanitize_cli_arg(val2_var.get()) if val2_var else None

                    value: str = val1_value
                    if val1_value and val2_value:
                        value = f"{val1_value}:{val2_value}"

                    if value:
                        args.append(f"--{key}={value}")
                else:
                    args.append(f"--{key}")

        return args

    def start_node(self, is_autostart: bool = False) -> None:
        """Start the kaspad subprocess."""
        if self.node_process and self.node_process.poll() is None:
            self.log_message(f"{translate('Node is already running.')}\n")
            return

        self.update_command_preview()

        exe_path_to_check: str = self.node_exe_path
        exe_name: str = os.path.basename(exe_path_to_check).lower()

        # Security Check 1: Block known system shells
        if exe_name in ["cmd.exe", "powershell.exe", "pwsh.exe", "bash.exe", "sh.exe"]:
            self.log_message("Error: Executable cannot be a system shell.")
            if not is_autostart:
                messagebox.showerror(
                    translate("Invalid Input"),
                    translate("Selected executable is a blocked system shell.")
                )
            return

        # Security Check 2: Check if it's a file (not a directory or non-existent)
        if not os.path.isfile(exe_path_to_check):
            self.log_message(
                f"{translate('Error')}: {translate('File not found')}:\n"
                f"{_sanitize_for_logging(exe_path_to_check)}\n"
            )
            self._update_update_button_logic()
            self.log_message(
                f"{translate('Please update the node first using the ''Update Node'' button.')}\n"
            )
            if not is_autostart:
                messagebox.showerror(
                    translate("Error"),
                    translate(
                        "Please update the node first using the 'Update Node' button."
                    ),
                )
            return

        try:
            self._save_settings()
            command_list: List[str] = self.build_args_from_settings()

            self.log_message(f"--- {translate('Starting Node')} ---\n")
            self.log_message(f"{translate('Command')}:\n{' '.join(command_list)}\n")
            self.log_message("...\n")

            startupinfo: subprocess.STARTUPINFO = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            self.node_process = subprocess.Popen(
                command_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
                text=False,
            )

            threading.Thread(
                target=self.read_output,
                args=(self.node_process.stdout,),
                daemon=True,
            ).start()

            self.view.start_button.config(state="disabled")
            self.view.stop_button.config(state="normal")
            self.set_controls_state(True)

        except Exception as e:
            self.log_message(
                f"Failed to start Kaspa Node: {_sanitize_for_logging(e)}\n"
            )
            self.node_process = None

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
        self.node_process = None
        try:
            if self.view.winfo_exists():
                self.view.after(0, self.set_controls_state, True)
        except (tk.TclError, RuntimeError):
            pass

    def stop_node(self) -> None:
        """Stop the running subprocess and its children using psutil."""
        if self.node_process and self.node_process.poll() is None:
            try:
                self.log_message(translate("Stopping Kaspa Node...") + "\n")

                # Get the process and its children
                parent: psutil.Process = psutil.Process(self.node_process.pid)
                children: List[psutil.Process] = parent.children(recursive=True)

                # Terminate the children first
                for child in children:
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                
                # Terminate the parent process
                self.node_process.terminate()

                # Wait for processes to exit
                psutil.wait_procs(children, timeout=3)

            except psutil.NoSuchProcess:
                 self.log_message(translate("Node is not running.") + "\n")

            except Exception as e:
                self.log_message(
                    f"Error while stopping node: {_sanitize_for_logging(e)}\n"
                )
            finally:
                # Fallback check before UI update to prevent TclError on shutdown
                try:
                    if self.view.winfo_exists():
                        self.on_process_exit()
                except tk.TclError:
                    pass

        else:
            self.log_message(f"{translate('Node is not running.')}\n")

    def _delete_node_files(self) -> None:
        """
        Delete the node exe and version files after a security check.
        """
        try:
            db_path: str = (
                self.config_manager.get_config().get("paths", {}).get("database", "")
            )
            safe_dir_roaming_base: str = os.path.abspath(os.path.dirname(db_path))
            
            safe_dir_roaming: str = (
                os.path.abspath(os.path.dirname(safe_dir_roaming_base))
                if safe_dir_roaming_base
                else ""
            )

            safe_dir_local: str = os.path.abspath(
                os.path.join(
                    os.getenv("LOCALAPPDATA", ""), "KaspaGateway"
                )
            )

            target_exe_path: str = os.path.abspath(self.node_exe_path)
            target_version_path: str = f"{target_exe_path}.version"

            def is_path_safe(path_to_check: str) -> bool:
                path_to_check = os.path.abspath(path_to_check)
                is_in_roaming: bool = bool(safe_dir_roaming and path_to_check.startswith(safe_dir_roaming))
                is_in_local: bool = bool(safe_dir_local and path_to_check.startswith(safe_dir_local))
                return is_in_roaming or is_in_local

            is_safe_exe: bool = is_path_safe(target_exe_path)
            is_safe_version: bool = is_path_safe(target_version_path)

            if not (is_safe_exe and is_safe_version):
                self.log_message(
                    translate("Error: Deletion path is outside the allowed directory.")
                )
                messagebox.showerror(
                    translate("Error"),
                    translate(
                        "Deletion outside user data directory is not allowed."
                    ),
                )
                return
        except Exception as e:
            self.log_message(
                f"Error during security check: {_sanitize_for_logging(e)}"
            )
            return

        if self.node_process and self.node_process.poll() is None:
            self.log_message(translate("Error: Process is running."))
            messagebox.showerror(
                translate("Error"), translate("Error: Process is running.")
            )
            return

        exe_path_to_delete: str = self.node_exe_path
        version_file_path: str = f"{exe_path_to_delete}.version"

        if not os.path.exists(exe_path_to_delete) and not os.path.exists(
            version_file_path
        ):
            ToastNotification(
                title=translate("Delete Files"),
                message=translate("Files not found."),
                bootstyle=INFO,
                duration=3000,
            ).show_toast()
            return

        if not messagebox.askyesno(
            translate("Confirm File Deletion"),
            f"{translate('Are you sure you want to delete these files? This cannot be undone.')}\n\n"
            f"- {exe_path_to_delete}\n- {version_file_path}",
        ):
            return

        try:
            if os.path.exists(exe_path_to_delete):
                os.remove(exe_path_to_delete)
                self.log_message(
                    f"Deleted: {_sanitize_for_logging(exe_path_to_delete)}"
                )
            if os.path.exists(version_file_path):
                os.remove(version_file_path)
                self.log_message(
                    f"Deleted: {_sanitize_for_logging(version_file_path)}"
                )

            self._check_local_kaspad_version()
            ToastNotification(
                title=translate("Delete Files"),
                message=translate("Files deleted successfully."),
                bootstyle=SUCCESS,
                duration=3000,
            ).show_toast()
        except Exception as e:
            logger.error(f"Failed to delete node files: {e}")
            self.log_message(
                f"{translate('Failed to delete files. Check logs.')}: {_sanitize_for_logging(e)}"
            )
            messagebox.showerror(
                translate("Error"),
                f"{translate('Failed to delete files. Check logs.')}\n{e}",
            )

    def on_close(self) -> None:
        """Cleanup function to stop the node on application close."""
        self.stop_node()

    def set_controls_state(self, active: bool) -> None:
        """
        Enable or disable all controls in this tab.
        This is the single source of truth for widget states.
        """
        is_running: bool = self.node_process and self.node_process.poll() is None
        is_active: bool = active

        try:
            if not hasattr(self.view, "start_button"):
                return

            if self.is_updating:
                self.view.start_button.config(state="disabled")
                self.view.stop_button.config(state="disabled")
                self.view.update_button.config(state="disabled")
                self.view.reset_button.config(state="disabled")
                self.view.db_size_button.config(state="disabled")
                self.view.delete_files_button.config(state="disabled")
                return

            self.view.start_button.config(
                state="disabled" if (is_running or not is_active) else "normal"
            )
            self.view.stop_button.config(
                state="normal" if (is_running and is_active) else "disabled"
            )

            self._update_update_button_logic(is_active)

            self.view.reset_button.config(
                state="normal" if is_active else "disabled"
            )
            self.view.db_size_button.config(
                state="normal" if is_active else "disabled"
            )
            self.view.delete_files_button.config(
                state="normal" if (is_active and not is_running) else "disabled"
            )
        except tk.TclError:
            pass

    def _get_default_appdir(self) -> str:
        """Gets the default kaspad application directory based on OS."""
        system: str = platform.system()
        if system == "Windows":
            return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Kaspad")
        elif system == "Darwin":
            return os.path.join(
                os.environ.get("HOME", ""), "Library", "Application Support", "Kaspad"
            )
        else:
            return os.path.join(os.environ.get("HOME", ""), ".kaspad")

    def _get_folder_size(self, folder_path: str) -> int:
        """Calculates the total size of a folder, returns -1 on error."""
        total_size: int = 0
        try:
            for dirpath, _, filenames in os.walk(folder_path):
                for f in filenames:
                    fp: str = os.path.join(dirpath, f)
                    if not os.path.islink(fp):
                        try:
                            total_size += os.path.getsize(fp)
                        except OSError:
                            pass
        except Exception as e:
            logger.warning(
                f"Could not calculate size for {_sanitize_for_logging(folder_path)}: {_sanitize_for_logging(e)}"
            )
            return -1
        return total_size

    def update_db_size(self) -> None:
        """Triggers a background thread to calculate the DB size."""
        if not hasattr(self.view, "db_size_label"):
            return

        self.view.db_size_label.config(
            text=f"{translate('DB Size')}: {translate('Calculating...')}"
        )
        self.view.db_size_button.config(state=DISABLED)
        threading.Thread(target=self._get_db_size_worker, daemon=True).start()

    def _get_db_size_worker(self) -> None:
        """Worker thread to find and calculate the database size."""
        size_str: str = ""
        try:
            appdir_check_var, appdir_string_var, *_ = self.option_vars.get(
                "appdir", (ttk.BooleanVar(value=False), ttk.StringVar(value=""))
            )
            appdir_path: str = appdir_string_var.get()
            if not appdir_check_var.get() or not appdir_path:
                appdir_path = self._get_default_appdir()

            safe_base_path: str = os.path.abspath(self._get_default_appdir())
            target_path: str = os.path.abspath(appdir_path)
            default_rusty_path: str = os.path.abspath(
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "rusty-kaspa")
            )

            if not (
                target_path.startswith(safe_base_path)
                or target_path.startswith(default_rusty_path)
            ):
                raise Exception(
                    "appdir path must be inside the default Kaspad or "
                    "rusty-kaspa data directory."
                )

            network_name: str = self.network_var.get()
            netsuffix_check, netsuffix_val, *_ = self.option_vars.get(
                "netsuffix", (ttk.BooleanVar(value=False), ttk.StringVar(value=""))
            )
            if netsuffix_check.get() and network_name == "testnet":
                net_suffix: str = netsuffix_val.get()
                if net_suffix:
                    network_name = f"testnet-{net_suffix}"

            db_path_datadir2: str = os.path.join(appdir_path, network_name, "datadir2")
            db_path_datadir: str = os.path.join(appdir_path, network_name, "datadir")

            db_path: Optional[str] = None
            if os.path.exists(db_path_datadir2):
                db_path = db_path_datadir2
            elif os.path.exists(db_path_datadir):
                db_path = db_path_datadir

            if not db_path:
                rusty_path_base: str = default_rusty_path
                rusty_net_map: Dict[str, str] = {
                    "mainnet": "kaspa-mainnet",
                    "testnet": "kaspa-testnet-11",
                    "devnet": "kaspa-devnet",
                    "simnet": "kaspa-simnet",
                }
                rusty_path: str = os.path.join(
                    rusty_path_base,
                    rusty_net_map.get(network_name, ""),
                    "datadir",
                )

                if os.path.exists(rusty_path):
                    db_path = rusty_path

            if not db_path:
                size_str = f"N/A ({translate('Not Found')})"
            else:
                size_bytes: int = self._get_folder_size(db_path)
                if size_bytes < 0:
                    size_str = translate("Error")
                elif size_bytes < 1024**2:
                    size_str = f"{size_bytes / 1024:.2f} KB"
                elif size_bytes < 1024**3:
                    size_str = f"{size_bytes / 1024**2:.2f} MB"
                else:
                    size_str = f"{size_bytes / 1024**3:.2f} GB"
        except Exception as e:
            logger.error(f"Error getting DB size: {_sanitize_for_logging(e)}")
            size_str = translate("Error")

        def ui_update() -> None:
            """Safe UI update function to run on the main thread."""
            try:
                if self.view.db_size_label:
                    self.view.db_size_label.config(
                        text=f"{translate('DB Size')}: {size_str}"
                    )
                self.view.db_size_button.config(state=NORMAL)
            except tk.TclError:
                pass

        if self.view.winfo_exists():
            self.view.after(0, ui_update)
