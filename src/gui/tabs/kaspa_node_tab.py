#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contains the GUI tab (View) for managing a local Kaspa node (kaspad).
This file contains widget creation, layout logic, and UI-specific event handling.
All business logic and state are managed by KaspaNodeController.
"""

from __future__ import annotations

import logging
import os
import platform
import tkinter as tk
from tkinter import END, NORMAL, DISABLED
from typing import TYPE_CHECKING, Any, List, Optional, Tuple, Dict, cast

import ttkbootstrap as ttk
from ttkbootstrap.constants import (
    BOTH,
    DANGER,
    EW,
    INFO,
    INVERSE,
    LEFT,
    NSEW,
    RIGHT,
    SUCCESS,
    TOP,
    VERTICAL,
    X,
)
from ttkbootstrap.scrolled import ScrolledText
from ttkbootstrap.tooltip import ToolTip

from src.gui.components.log_viewer import LogPane
from src.utils.i18n import translate
from src.utils.validation import sanitize_cli_arg
from .kaspa_node_controller import KaspaNodeController

if TYPE_CHECKING:
    from src.gui.config_manager import ConfigManager
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


class KaspaNodeTab(ttk.Frame):
    """
    The main ttk.Frame (View) that contains all controls
    for running and managing a kaspad node instance.
    The logic is handled by KaspaNodeController.
    """

    controller: KaspaNodeController
    notebook: ttk.Notebook
    settings_tab_frame: ttk.Frame
    log_tab_frame: ttk.Frame
    settings_pane: ttk.Frame
    log_pane: ttk.Labelframe
    log_pane_component: LogPane
    preview_lf: ttk.Labelframe
    command_preview_text: ScrolledText
    copy_command_button: ttk.Button
    controls_frame: ttk.Labelframe

    # Control Buttons
    start_button: ttk.Button
    stop_button: ttk.Button
    apply_restart_button: ttk.Button
    update_button: ttk.Button
    reset_button: ttk.Button
    delete_files_button: ttk.Button

    # Checkboxes
    autostart_cb: ttk.Checkbutton
    auto_restart_cb: ttk.Checkbutton

    # Status & Info
    db_size_frame: ttk.Frame
    db_size_label: ttk.Label
    db_size_tooltip: ToolTip
    db_size_button: ttk.Button
    version_info_frame: ttk.Frame
    local_version_label: ttk.Label
    latest_version_label: ttk.Label
    latest_date_label: ttk.Label

    # External Process Warning
    external_process_frame: ttk.Frame
    external_process_label: ttk.Label
    external_process_stop_button: ttk.Button

    # Settings Frames
    network_frame: ttk.Labelframe
    netsuffix_frame: ttk.Frame
    custom_paths_frame: ttk.Labelframe
    options_lf: ttk.Labelframe

    # Custom Path Entries
    exe_cb: ttk.Checkbutton
    exe_entry: ttk.Entry
    exe_browse: ttk.Button
    url_cb: ttk.Checkbutton
    url_entry: ttk.Entry
    url_path_label: ttk.Label
    url_path_entry: ttk.Entry

    # Labels
    col1_label: ttk.Label
    col2_label: ttk.Label
    col3_label: ttk.Label
    col4_rpc_label: ttk.Label

    # Download URL
    download_url_text: ScrolledText
    set_default_url_button: ttk.Button

    def __init__(
        self,
        master: ttk.Notebook,
        main_window: MainWindow,
        config_manager: ConfigManager,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, **kwargs)
        self.pack(fill=BOTH, expand=True)

        self.controller = KaspaNodeController(self, main_window, config_manager)
        self.controller.define_variables()
        self.controller.controller_load_settings()

        self._build_ui()
        self._initialize_controller_hooks()

    def _build_ui(self) -> None:
        """Constructs the main UI layout."""
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)

        self.settings_tab_frame = ttk.Frame(self.notebook, padding=0)
        self.log_tab_frame = ttk.Frame(self.notebook, padding=0)
        self.log_tab_frame.grid_rowconfigure(0, weight=1)
        self.log_tab_frame.grid_columnconfigure(0, weight=1)

        self.notebook.add(self.settings_tab_frame, text=f" {translate('Settings')} ")
        self.notebook.add(self.log_tab_frame, text=f" {translate('Log')} ")

        self.settings_pane = self.create_settings_pane(self.settings_tab_frame)
        self.settings_pane.pack(fill=BOTH, expand=True)

        self.log_pane = self.create_log_pane(self.log_tab_frame)
        self.log_pane.grid(row=0, column=0, sticky="nsew", padx=10, pady=(0, 10))

    def _initialize_controller_hooks(self) -> None:
        """Sets up tracers and initial updates after UI build."""
        self.controller._add_tracers()
        self.controller._update_all_entry_states()
        self.controller.update_command_preview()
        # Initialize the DB tooltip with the current path
        self._update_db_path_tooltip()

    def controller_load_settings(self) -> None:
        """Proxy to load settings from controller."""
        self.controller._load_settings()

    def activate_tab(self) -> None:
        """Called by main_window when tab is selected. Passes to controller."""
        self.controller.activate_tab()

    def on_close(self) -> None:
        """Called by main_window on shutdown. Passes to controller."""
        self.controller.on_close()

    def create_settings_pane(self, master: ttk.Frame) -> ttk.Frame:
        """Create the main settings panel with all controls."""
        settings_outer_frame = ttk.Frame(master, padding=5)
        settings_outer_frame.grid_columnconfigure(0, weight=1)
        settings_outer_frame.grid_rowconfigure(0, weight=0)
        settings_outer_frame.grid_rowconfigure(1, weight=0)
        settings_outer_frame.grid_rowconfigure(2, weight=1)

        # 1. Command Preview Section
        self.preview_lf = ttk.Labelframe(
            settings_outer_frame,
            text=f" {translate('Command Preview')} ",
            padding=(10, 5),
        )
        self.preview_lf.grid(row=0, column=0, sticky="nsew", padx=5, pady=(0, 2))
        self.preview_lf.grid_columnconfigure(0, weight=1)

        self.command_preview_text = ScrolledText(
            self.preview_lf,
            height=3,
            font=("Courier New", 9),
            wrap="word",
            autohide=True,
            bootstyle="round",
        )
        self.command_preview_text.grid(row=0, column=0, sticky="ew")
        self.command_preview_text.text.config(state="disabled")

        self.copy_command_button = ttk.Button(
            self.preview_lf,
            text=translate("Copy"),
            command=self.controller.copy_command_to_clipboard,
            bootstyle="info-outline",
        )
        self.copy_command_button.grid(row=0, column=1, padx=(5, 0))

        # 2. Top Controls Area (Controls, Network, Paths)
        top_frame = ttk.Frame(settings_outer_frame)
        top_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=2)
        top_frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="group1")

        self.create_controls_frame(top_frame).grid(
            row=0, column=0, sticky="nsew", padx=(0, 5), pady=0
        )
        self.create_network_frame(top_frame).grid(
            row=0, column=1, sticky="nsew", padx=5, pady=0
        )
        self.create_custom_paths_frame(top_frame).grid(
            row=0, column=2, sticky="nsew", padx=(5, 0), pady=0
        )

        # 3. Detailed Options Area
        self.options_lf = ttk.Labelframe(
            settings_outer_frame,
            text=f" {translate('Node Options')} ",
            padding=(10, 5),
        )
        self.options_lf.grid(row=2, column=0, sticky="nsew", padx=5, pady=(2, 0))
        self.options_lf.grid_columnconfigure(0, weight=1)
        self.options_lf.grid_rowconfigure(0, weight=1)

        self._build_options_grid(self.options_lf)

        return settings_outer_frame

    def _build_options_grid(self, parent: ttk.Labelframe) -> None:
        """Builds the 4-column grid of node options."""
        options_container = ttk.Frame(parent)
        options_container.grid(row=0, column=0, sticky="nsew")
        options_container.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="group1")

        col1 = ttk.Frame(options_container, padding=5)
        col1.grid(row=0, column=0, sticky="new", padx=(0, 5))
        col2 = ttk.Frame(options_container, padding=5)
        col2.grid(row=0, column=1, sticky="new", padx=5)
        col3 = ttk.Frame(options_container, padding=5)
        col3.grid(row=0, column=2, sticky="new", padx=5)
        col4 = ttk.Frame(options_container, padding=5)
        col4.grid(row=0, column=3, sticky="new", padx=(5, 0))

        # Column 1: Paths, Logging & Download URL
        self.col1_label = ttk.Label(
            col1, text=translate("Paths & Logging"), font="-weight bold"
        )
        self.col1_label.pack(anchor="w", padx=5, pady=(0, 5))
        self.create_option_entry(col1, "--configfile", "configfile")
        
        # Handle appdir specially to hook up auto-update logic
        self.create_option_entry(col1, "--appdir", "appdir")
        if "appdir" in self.controller.option_vars:
            appdir_tuple = self.controller.option_vars["appdir"]
            if len(appdir_tuple) > 1 and appdir_tuple[1] is not None:
                # Add trace to auto-update DB size when appdir changes
                appdir_tuple[1].trace_add("write", self._on_appdir_change)

        self.create_option_entry(col1, "--logdir", "logdir")
        self.create_option_flag(col1, "--nologfiles", "nologfiles")

        ttk.Separator(col1).pack(fill=X, pady=(15, 5), padx=5)
        self.node_download_label = ttk.Label(
            col1, text=translate("Node Download URL"), font="-size 8"
        )
        self.node_download_label.pack(anchor="w", padx=5)

        self.download_url_text = ScrolledText(
            col1, height=3, font=("Segoe UI", 8), autohide=True
        )
        self.download_url_text.pack(fill=X, expand=True, padx=5, pady=(2, 5))
        self.download_url_text.text.insert(
            "1.0", self.controller.node_download_url_var.get()
        )

        self.set_default_url_button = ttk.Button(
            col1,
            text=translate("Set Default"),
            command=self._on_save_url_click,
            bootstyle="secondary-outline",
            state="disabled",
        )
        self.set_default_url_button.pack(fill=X, padx=5, pady=(0, 5))
        self.download_url_text.text.bind("<KeyRelease>", self._on_url_text_change)

        # Column 2: Connectivity
        self.col2_label = ttk.Label(
            col2, text=translate("P2P Connectivity"), font="-weight bold"
        )
        self.col2_label.pack(anchor="w", padx=5, pady=(0, 5))
        self.create_option_entry(col2, "--listen", "listen")
        self.create_option_entry(col2, "--connect", "connect")
        self.create_option_entry(col2, "--addpeer", "addpeer")
        self.create_option_entry(col2, "--outpeers", "outpeers")
        self.create_option_entry(col2, "--maxinpeers", "maxinpeers")
        self.create_option_entry(col2, "--externalip", "externalip")
        self.create_option_flag(col2, "--disable-upnp", "disable-upnp")
        self.create_option_flag(col2, "--nodnsseed", "nodnsseed")
        self.create_option_entry(col2, "--uacomment", "uacomment")

        # Column 3: DB & Performance
        self.col3_label = ttk.Label(
            col3, text=translate("DB & Performance"), font="-weight bold"
        )
        self.col3_label.pack(anchor="w", padx=5, pady=(0, 5))

        flag_frame = ttk.Frame(col3)
        flag_frame.pack(fill="x", expand=True, pady=(0, 5))

        db_flags: List[Tuple[str, str]] = [
            ("--utxoindex", "utxoindex"),
            ("--archival", "archival"),
            ("--reset-db", "reset-db"),
            ("--perf-metrics", "perf-metrics"),
            ("--sanity", "sanity"),
            ("--enable-unsynced-mining", "enable-unsynced-mining"),
            ("--yes", "yes"),
        ]

        row_frame: Optional[ttk.Frame] = None
        for i, (label_text, key) in enumerate(db_flags):
            if i % 2 == 0:
                row_frame = ttk.Frame(flag_frame)
                row_frame.pack(fill="x", expand=True)

            if row_frame:
                flag_widget_frame = self.create_option_flag(row_frame, label_text, key)
                flag_widget_frame.pack_configure(
                    side=LEFT, fill=X, expand=True, anchor="w", pady=0, padx=0
                )
                if flag_widget_frame.winfo_children():
                    cb = flag_widget_frame.winfo_children()[0]
                    cb.pack_configure(padx=2)

        self.create_option_entry(
            col3, "--max-tracked-addresses", "max-tracked-addresses"
        )
        self.create_option_entry(
            col3, "--retention-period-days", "retention-period-days"
        )
        self.create_option_entry(col3, "--async-threads", "async-threads")
        self.create_option_entry(col3, "--ram-scale", "ram-scale")
        self.create_option_entry(
            col3, "--perf-metrics-interval-sec", "perf-metrics-interval-sec"
        )

        # Column 4: RPC
        self.col4_rpc_label = ttk.Label(
            col4, text=translate("RPC"), font="-weight bold"
        )
        self.col4_rpc_label.pack(anchor="w", padx=5, pady=(0, 5))
        self.create_option_entry(col4, "--rpclisten", "rpclisten")
        self.create_option_entry(col4, "--rpclisten-borsh", "rpclisten-borsh")
        self.create_option_entry(col4, "--rpclisten-json", "rpclisten-json")
        self.create_option_entry(col4, "--rpcmaxclients", "rpcmaxclients")
        self.create_option_flag(col4, "--unsaferpc", "unsaferpc")
        self.create_option_flag(col4, "--nogrpc", "nogrpc")

    def _on_appdir_change(self, *args: Any) -> None:
        """
        Callback triggered when appdir changes.
        Updates the DB Size tooltip and triggers the DB size calculation.
        """
        self._update_db_path_tooltip()
        self.controller.update_db_size()

    def _update_db_path_tooltip(self) -> None:
        """
        Calculates the expected DB path based on current settings and updates
        the tooltip on the DB Size label.
        """
        if not hasattr(self, "db_size_tooltip"):
            return

        try:
            # Resolve path logic mirroring the controller
            base_dir = ""
            appdir_setting = self.controller.option_vars.get("appdir")
            if appdir_setting and appdir_setting[0].get():
                if len(appdir_setting) > 1 and appdir_setting[1]:
                    base_dir = sanitize_cli_arg(appdir_setting[1].get())

            if not base_dir:
                # Default OS paths
                if platform.system() == "Windows":
                    base_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Kaspad")
                elif platform.system() == "Darwin":
                    base_dir = os.path.join(os.environ.get("HOME", ""), "Library", "Application Support", "Kaspad")
                else:
                    base_dir = os.path.join(os.environ.get("HOME", ""), ".kaspad")

            # Resolve Network Folder
            network = self.controller.network_var.get()
            net_folder = "kaspa-mainnet"
            if network == "testnet":
                suffix = "10"
                netsuffix_vars = self.controller.option_vars.get("netsuffix")
                if netsuffix_vars and netsuffix_vars[0].get():
                    suffix = netsuffix_vars[1].get()
                net_folder = f"kaspa-testnet-{suffix}"
            elif network == "devnet":
                net_folder = "kaspa-devnet"
            elif network == "simnet":
                net_folder = "kaspa-simnet"

            # Target Path
            target_path = os.path.join(base_dir, net_folder)
            self.db_size_tooltip.text = f"{translate('Data directory')}: {target_path}"

        except Exception as e:
            self.db_size_tooltip.text = f"Error resolving path: {e}"

    def _on_url_text_change(self, event: Any) -> None:
        """Enable the 'Set Default' button when text changes."""
        current_text = self.download_url_text.text.get("1.0", "end-1c").strip()
        saved_text = self.controller.node_download_url_var.get().strip()

        if current_text != saved_text:
            self.set_default_url_button.config(state="normal", bootstyle="primary")
        else:
            self.set_default_url_button.config(
                state="disabled", bootstyle="secondary-outline"
            )

    def _on_save_url_click(self) -> None:
        """Handler for the Set Default button."""
        new_url = self.download_url_text.text.get("1.0", "end-1c").strip()
        self.controller.save_download_url(new_url)
        self.set_default_url_button.config(
            state="disabled", bootstyle="secondary-outline"
        )

    def update_preview_text_widget(self, command_str: str) -> None:
        """Updates the ScrolledText widget with the command string."""
        if hasattr(self, "command_preview_text"):
            try:
                if self.focus_get() != self.command_preview_text.text:
                    self.command_preview_text.text.config(state="normal")
                    self.command_preview_text.text.delete("1.0", END)
                    self.command_preview_text.text.insert("1.0", command_str)
                    self.command_preview_text.text.config(state="disabled")
            except tk.TclError:
                pass
            except Exception:
                self.command_preview_text.text.config(state="normal")

    def create_option_entry(
        self, master: ttk.Frame, label_text: str, key: str
    ) -> ttk.Frame:
        """Creates a row for an option with an entry field."""
        option_vars_tuple = self.controller.option_vars.get(key)
        if not option_vars_tuple:
            return ttk.Frame(master)

        check_var = option_vars_tuple[0]
        val1_var = option_vars_tuple[1] if len(option_vars_tuple) > 1 else None
        val2_var = (
            option_vars_tuple[2]
            if len(option_vars_tuple) > 2
            and isinstance(option_vars_tuple[2], ttk.StringVar)
            else None
        )

        frame = ttk.Frame(master)
        frame.pack(fill="x", expand=True, pady=1)

        cb = ttk.Checkbutton(
            frame,
            variable=check_var,
            command=lambda k=key: self.controller._on_check_toggle(k),
        )
        cb.pack(side=LEFT)
        ToolTip(cb, text=translate(f"Tooltip_{key}"), wraplength=300)

        label = ttk.Label(frame, text=label_text, bootstyle="secondary")
        label.pack(side=LEFT, padx=(2, 5))
        ToolTip(label, text=translate(f"Tooltip_{key}"), wraplength=300)

        entry_frame = ttk.Frame(frame)
        entry_frame.pack(side=RIGHT, fill="x", expand=True)

        widget_list: List[tk.Widget] = [frame, label]

        if val2_var and isinstance(val1_var, ttk.StringVar):
            port_entry = ttk.Entry(
                entry_frame, textvariable=val2_var, state="disabled", width=8
            )
            port_entry.pack(side=RIGHT, padx=(2, 0))
            colon_label = ttk.Label(entry_frame, text=":", bootstyle="secondary")
            colon_label.pack(side=RIGHT)
            ip_entry = ttk.Entry(entry_frame, textvariable=val1_var, state="disabled")
            ip_entry.pack(side=RIGHT, fill="x", expand=True, padx=(0, 2))

            widget_list.extend([ip_entry, colon_label, port_entry])
            self.controller.option_vars[key] = (
                check_var,
                val1_var,
                val2_var,
                *widget_list,
            )
        elif isinstance(val1_var, ttk.StringVar):
            ip_entry = ttk.Entry(entry_frame, textvariable=val1_var, state="disabled")
            ip_entry.pack(side=RIGHT, fill="x", expand=True)
            widget_list.append(ip_entry)
            self.controller.option_vars[key] = (
                check_var,
                val1_var,
                *widget_list,
            )

        return frame

    def create_option_flag(
        self, master: ttk.Frame, label_text: str, key: str
    ) -> ttk.Frame:
        """Creates a row for a flag-only option (just a checkbox)."""
        check_var_tuple = self.controller.option_vars.get(
            key, (ttk.BooleanVar(value=False), None)
        )
        check_var = check_var_tuple[0]

        frame = ttk.Frame(master)
        frame.pack(fill="x", expand=True, pady=1, anchor="w")

        cb = ttk.Checkbutton(
            frame,
            variable=check_var,
            text=label_text,
            command=self.controller._save_and_update_preview,
        )
        cb.pack(side="left")
        ToolTip(cb, text=translate(f"Tooltip_{key}"), wraplength=300)
        self.controller.option_vars[key] = (check_var, None, frame, cb)

        return frame

    def create_controls_frame(self, master: ttk.Frame) -> ttk.Labelframe:
        """Create the main controls frame (Start, Stop, Update, etc.)."""
        self.controls_frame = ttk.Labelframe(
            master, text=f" {translate('Controls')} ", padding=10
        )

        button_frame = ttk.Frame(self.controls_frame)
        button_frame.pack(fill=X, expand=True, pady=1)
        button_frame.grid_columnconfigure((0, 1), weight=1, uniform="grp1")

        self.start_button = ttk.Button(
            button_frame,
            text=translate("Start Kaspa Node"),
            command=self.controller.start_node,
            bootstyle=SUCCESS,
        )
        self.start_button.grid(row=0, column=0, sticky=EW, padx=(0, 2), pady=(0, 2))

        self.stop_button = ttk.Button(
            button_frame,
            text=translate("Stop Kaspa Node"),
            command=self.controller.stop_node,
            bootstyle=DANGER,
            state="disabled",
        )
        self.stop_button.grid(row=0, column=1, sticky=EW, padx=(2, 0), pady=(0, 2))

        self.apply_restart_button = ttk.Button(
            button_frame,
            text=translate("Apply & Restart"),
            command=self.controller.apply_and_restart_node,
            bootstyle="warning",
            state="disabled",
        )
        self.apply_restart_button.grid(
            row=1, column=0, sticky=EW, padx=(0, 2), pady=(2, 0)
        )
        ToolTip(
            self.apply_restart_button,
            text=translate("Apply changes and restart the node (if running)"),
        )

        self.update_button = ttk.Button(
            button_frame,
            text=translate("Update Node"),
            command=self.controller._on_update_button_pressed,
            bootstyle=INFO,
        )
        self.update_button.grid(row=1, column=1, sticky=EW, padx=(2, 0), pady=(2, 0))

        self.reset_button = ttk.Button(
            button_frame,
            text=translate("Reset"),
            command=self.controller.reset_to_defaults,
            bootstyle="warning-outline",
        )
        self.reset_button.grid(row=2, column=0, sticky=EW, padx=(0, 2), pady=(2, 0))

        self.delete_files_button = ttk.Button(
            button_frame,
            text=translate("Delete Node Files"),
            command=self.controller._delete_node_files,
            bootstyle="danger-outline",
        )
        self.delete_files_button.grid(
            row=2, column=1, sticky=EW, padx=(2, 0), pady=(2, 0)
        )

        self.autostart_cb = ttk.Checkbutton(
            self.controls_frame,
            text=translate("Start Node on App Launch"),
            variable=self.controller.autostart_var,
        )
        self.autostart_cb.pack(fill=X, expand=True, pady=(2, 0), anchor="w")

        self.auto_restart_cb = ttk.Checkbutton(
            self.controls_frame,
            text=translate("Auto-Restart on Failure"),
            variable=self.controller.auto_restart_var,
            bootstyle="danger",
        )
        self.auto_restart_cb.pack(fill=X, expand=True, pady=(2, 0), anchor="w")
        ToolTip(
            self.auto_restart_cb,
            text=translate(
                "Automatically restart the node if it crashes or stops unexpectedly."
            ),
        )

        self.db_size_frame = ttk.Frame(self.controls_frame, padding=(0, 2))
        self.db_size_frame.pack(fill=X, expand=True, pady=(2, 0))
        self.db_size_frame.grid_columnconfigure(0, weight=1)

        self.db_size_label = ttk.Label(
            self.db_size_frame, text=f"{translate('DB Size')}: N/A"
        )
        self.db_size_label.grid(row=0, column=0, sticky="w")
        
        # Add Tooltip for DB Size path
        self.db_size_tooltip = ToolTip(
            self.db_size_label, 
            text=translate("Path not detected"), 
            bootstyle=(INFO, INVERSE)
        )

        self.db_size_button = ttk.Button(
            self.db_size_frame,
            text=translate("Refresh"),
            command=self.controller.update_db_size,
            bootstyle="info-outline",
        )
        self.db_size_button.grid(row=0, column=1, sticky="e")

        self.version_info_frame = ttk.Frame(self.controls_frame)
        self.version_info_frame.pack(fill=X, expand=True, pady=(2, 0))

        self.local_version_label = ttk.Label(
            self.version_info_frame,
            textvariable=self.controller.local_node_version_var,
            bootstyle="secondary",
            font="-size 8",
        )
        self.local_version_label.pack(side=LEFT, padx=(0, 10))

        self.latest_version_label = ttk.Label(
            self.version_info_frame,
            textvariable=self.controller.latest_node_version_var,
            bootstyle="secondary",
            font="-size 8",
        )
        self.latest_version_label.pack(side=LEFT, padx=(0, 10))

        self.latest_date_label = ttk.Label(
            self.version_info_frame,
            textvariable=self.controller.latest_node_date_var,
            bootstyle="secondary",
            font="-size 8",
        )
        self.latest_date_label.pack(side=LEFT)

        self.external_process_frame = ttk.Frame(self.controls_frame, bootstyle="danger")
        self.external_process_frame.pack(fill=X, expand=True, pady=(5, 0), ipady=5)
        self.external_process_frame.grid_columnconfigure(1, weight=1)

        self.external_process_label = ttk.Label(
            self.external_process_frame,
            text="",
            bootstyle="danger-inverse",
            font="-size 8 -weight bold",
            wraplength=250,
        )
        self.external_process_label.grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 5)
        )

        self.external_process_stop_button = ttk.Button(
            self.external_process_frame,
            text=translate("Stop External Process"),
            command=self.controller.stop_external_node,
            bootstyle=DANGER,
        )
        self.external_process_stop_button.grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=5
        )

        self.external_process_frame.pack_forget()
        self.controller._update_update_button_logic()

        return self.controls_frame

    def create_network_frame(self, master: ttk.Frame) -> ttk.Labelframe:
        """Creates the 'Network & Logging' selection frame."""
        self.network_frame = ttk.Labelframe(
            master, text=f" {translate('Network & Logging')} ", padding=10
        )
        self.network_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(self.network_frame, text=f"{translate('Network')}:").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        net_frame = ttk.Frame(self.network_frame)
        net_frame.grid(row=0, column=1, sticky="ew", pady=2)
        nets: List[Tuple[str, str]] = [
            ("Mainnet", "mainnet"),
            ("Testnet", "testnet"),
            ("Devnet", "devnet"),
            ("Simnet", "simnet"),
        ]

        for i, (text, value) in enumerate(nets):
            rb = ttk.Radiobutton(
                net_frame,
                text=translate(text),
                variable=self.controller.network_var,
                value=value,
                command=self.controller._save_and_update_preview,
            )
            rb.pack(side="left", padx=3)

        ttk.Label(self.network_frame, text=f"{translate('Logging Level')}:").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        log_frame = ttk.Frame(self.network_frame)
        log_frame.grid(row=1, column=1, sticky="ew", pady=2)
        log_combo = ttk.Combobox(
            log_frame,
            textvariable=self.controller.loglevel_var,
            values=["off", "error", "warn", "info", "debug", "trace"],
            state="readonly",
            width=10,
        )
        log_combo.bind("<<ComboboxSelected>>", self.controller._save_and_update_preview)
        log_combo.pack(side="left", padx=3)

        netsuffix_vars = self.controller.option_vars.get("netsuffix")
        if not netsuffix_vars:
            return self.network_frame

        check_var, string_var, *_ = netsuffix_vars

        self.netsuffix_frame = ttk.Frame(self.network_frame)
        self.netsuffix_frame.grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(2, 0)
        )
        self.netsuffix_frame.grid_columnconfigure(2, weight=1)

        cb = ttk.Checkbutton(
            self.netsuffix_frame,
            variable=check_var,
            command=lambda k="netsuffix": self.controller._on_check_toggle(k),
        )
        cb.grid(row=0, column=0, sticky="w")
        ToolTip(cb, text=translate("Tooltip_netsuffix"), wraplength=300)

        label = ttk.Label(
            self.netsuffix_frame, text="--netsuffix", bootstyle="secondary"
        )
        label.grid(row=0, column=1, sticky="w", padx=(2, 5))
        ToolTip(label, text=translate("Tooltip_netsuffix"), wraplength=300)

        if not isinstance(string_var, ttk.StringVar):
            return self.network_frame

        entry = ttk.Entry(
            self.netsuffix_frame, textvariable=string_var, state="disabled"
        )
        entry.grid(row=0, column=2, sticky="ew")

        self.controller.option_vars["netsuffix"] = (
            check_var,
            string_var,
            self.netsuffix_frame,
            label,
            entry,
        )

        return self.network_frame

    def create_custom_paths_frame(self, master: ttk.Frame) -> ttk.Labelframe:
        """Creates the 'Custom Paths' frame for EXE and URL."""
        self.custom_paths_frame = ttk.Labelframe(
            master, text=f" {translate('Custom Paths')} ", padding=10
        )

        self.exe_cb = ttk.Checkbutton(
            self.custom_paths_frame,
            text=translate("Use Custom kaspad.exe"),
            variable=self.controller.use_custom_exe_var,
        )
        self.exe_cb.pack(fill=X, anchor="w")
        exe_frame = ttk.Frame(self.custom_paths_frame)
        exe_frame.pack(fill=X, expand=True, padx=(20, 0), pady=(0, 2))
        self.exe_entry = ttk.Entry(
            exe_frame,
            textvariable=self.controller.custom_exe_path_var,
            state="disabled",
        )
        self.exe_entry.pack(side=LEFT, fill=X, expand=True)

        self.exe_browse = ttk.Button(
            exe_frame,
            text="...",
            command=lambda: self.controller._browse_file(
                self.controller.custom_exe_path_var,
                "Select kaspad.exe",
                [("Executable", "*.exe")],
            ),
            width=3,
            state="disabled",
        )
        self.exe_browse.pack(side=LEFT, padx=(5, 0))

        self.url_cb = ttk.Checkbutton(
            self.custom_paths_frame,
            text=translate("Use Custom Download URL"),
            variable=self.controller.use_custom_url_var,
        )
        self.url_cb.pack(fill=X, anchor="w", pady=(2, 0))
        url_frame = ttk.Frame(self.custom_paths_frame)
        url_frame.pack(fill=X, expand=True, padx=(20, 0), pady=(0, 2))
        self.url_entry = ttk.Entry(
            url_frame,
            textvariable=self.controller.custom_url_var,
            state="disabled",
        )
        self.url_entry.pack(fill=X, expand=True)

        self.url_path_label = ttk.Label(
            self.custom_paths_frame,
            text=translate("Enter the exact path of the .exe inside the zip:"),
            state="disabled",
        )
        self.url_path_label.pack(fill=X, anchor="w", padx=(20, 0), pady=(2, 0))
        url_path_frame = ttk.Frame(self.custom_paths_frame)
        url_path_frame.pack(fill=X, expand=True, padx=(20, 0), pady=(0, 2))
        self.url_path_entry = ttk.Entry(
            url_path_frame,
            textvariable=self.controller.custom_url_exe_path_var,
            state="disabled",
        )
        self.url_path_entry.pack(fill=X, expand=True)

        self.controller._toggle_entry_state(
            self.controller.use_custom_exe_var,
            [self.exe_entry, self.exe_browse],
        )
        self.controller._toggle_entry_state(
            self.controller.use_custom_url_var,
            [
                self.url_entry,
                self.url_path_label,
                self.url_path_entry,
            ],
        )

        return self.custom_paths_frame

    def create_log_pane(self, master: ttk.Frame) -> ttk.Labelframe:
        """Create the 'Live Log' panel using the new LogPane component."""
        self.log_pane = ttk.Labelframe(
            master, text=f" {translate('Live Log')} ", padding=10
        )
        self.log_pane.grid_rowconfigure(0, weight=1)
        self.log_pane.grid_columnconfigure(0, weight=1)

        self.log_pane_component = LogPane(self.log_pane, self.controller.main_window)
        self.log_pane_component.pack(fill=BOTH, expand=True, padx=0, pady=0)

        # Set the controller's font size var to sync with the new component's var
        self.controller.log_font_size_var = self.log_pane_component.log_font_size_var
        # Link the spinbox command to the new component's method
        self.log_pane_component.log_font_spinbox.config(
            command=self.controller._update_log_font
        )
        self.log_pane_component.log_font_size_var.set(
            self.controller.log_font_size_var.get()
        )

        return self.log_pane

    def re_translate(self) -> None:
        """Update all translatable strings in the UI."""
        self.notebook.tab(0, text=translate("Settings"))
        self.notebook.tab(1, text=translate("Log"))

        if hasattr(self, "log_pane_component"):
            self.log_pane_component.re_translate()

        self.controls_frame.config(text=f" {translate('Controls')} ")
        self.start_button.config(text=translate("Start Kaspa Node"))
        self.stop_button.config(text=translate("Stop Kaspa Node"))
        self.apply_restart_button.config(text=translate("Apply & Restart"))

        self.controller._update_update_button_logic()

        self.reset_button.config(text=translate("Reset"))
        self.delete_files_button.config(text=translate("Delete Node Files"))
        self.autostart_cb.config(text=translate("Start Node on App Launch"))
        self.auto_restart_cb.config(text=translate("Auto-Restart on Failure"))

        if hasattr(self, "node_download_label"):
            self.node_download_label.config(text=translate("Node Download URL"))
        
        if hasattr(self, "set_default_url_button"):
            self.set_default_url_button.config(text=translate("Set Default"))

        if "N/A" in self.db_size_label.cget("text"):
            self.db_size_label.config(text=f"{translate('DB Size')}: N/A")
        elif translate("Calculating...") in self.db_size_label.cget("text"):
            self.db_size_label.config(
                text=f"{translate('DB Size')}: {translate('Calculating...')}"
            )
        self.db_size_button.config(text=translate("Refresh"))

        self.preview_lf.config(text=f" {translate('Command Preview')} ")
        self.copy_command_button.config(text=translate("Copy"))

        self.network_frame.config(text=f" {translate('Network & Logging')} ")

        if self.network_frame.winfo_children():
            self.network_frame.winfo_children()[0].config(
                text=f"{translate('Network')}:"
            )
            if len(self.network_frame.winfo_children()) > 2:
                self.network_frame.winfo_children()[2].config(
                    text=f"{translate('Logging Level')}:"
                )

        if hasattr(self, "col1_label"):
            self.col1_label.config(text=translate("Paths & Logging"))
        if hasattr(self, "options_lf"):
            self.options_lf.config(text=f" {translate('Node Options')} ")
        if hasattr(self, "col4_rpc_label"):
            self.col4_rpc_label.config(text=translate("RPC"))
        if hasattr(self, "col2_label"):
            self.col2_label.config(text=translate("P2P Connectivity"))
        if hasattr(self, "col3_label"):
            self.col3_label.config(text=translate("DB & Performance"))

        for key, item_tuple in self.controller.option_vars.items():
            if len(item_tuple) > 2:
                label_text_key = f"Tooltip_{key}"
                label_widget: Optional[ttk.Label] = None
                cb_widget: Optional[ttk.Checkbutton] = None

                try:
                    if item_tuple[1] is not None:
                        if len(item_tuple) > 3 and isinstance(item_tuple[3], ttk.Label):
                            label_widget = item_tuple[3]
                            if item_tuple[2].winfo_children():
                                cb_widget = item_tuple[2].winfo_children()[0]
                    else:
                        if len(item_tuple) > 3 and isinstance(
                            item_tuple[3], ttk.Checkbutton
                        ):
                            cb_widget = item_tuple[3]
                except (IndexError, AttributeError):
                    continue

                if label_widget:
                    label_widget.config(text=f"--{key}")
                    ToolTip(
                        label_widget,
                        text=translate(label_text_key),
                        wraplength=300,
                    )
                if cb_widget:
                    if item_tuple[1] is None:
                        cb_widget.config(text=f"--{key}")
                    ToolTip(
                        cb_widget,
                        text=translate(label_text_key),
                        wraplength=300,
                    )

        if hasattr(self, "netsuffix_frame") and self.netsuffix_frame.winfo_children():
            self.netsuffix_frame.winfo_children()[1].config(text="--netsuffix")
            ToolTip(
                self.netsuffix_frame.winfo_children()[0],
                text=translate("Tooltip_netsuffix"),
                wraplength=300,
            )
            ToolTip(
                self.netsuffix_frame.winfo_children()[1],
                text=translate("Tooltip_netsuffix"),
                wraplength=300,
            )

        if hasattr(self, "custom_paths_frame"):
            self.custom_paths_frame.config(text=f" {translate('Custom Paths')} ")
            self.exe_cb.config(text=translate("Use Custom kaspad.exe"))
            self.url_cb.config(text=translate("Use Custom Download URL"))
            self.url_path_label.config(
                text=translate("Enter the exact path of the .exe inside the zip:")
            )

        if (
            f"{translate('Local Version')}:"
            not in self.controller.local_node_version_var.get()
        ):
            current_version = (
                self.controller.local_node_version_var.get().split(":")[-1].strip()
            )
            self.controller.local_node_version_var.set(
                f"{translate('Local Version')}: {current_version}"
            )

        if (
            f"{translate('Latest Version')}:"
            not in self.controller.latest_node_version_var.get()
        ):
            current_version = (
                self.controller.latest_node_version_var.get().split(":")[-1].strip()
            )
            self.controller.latest_node_version_var.set(
                f"{translate('Latest Version')}: {current_version}"
            )

        if f"{translate('Updated')}:" not in self.controller.latest_node_date_var.get():
            current_date = (
                self.controller.latest_node_date_var.get().split(":")[-1].strip()
            )
            self.controller.latest_node_date_var.set(
                f"{translate('Updated')}: {current_date}"
            )
