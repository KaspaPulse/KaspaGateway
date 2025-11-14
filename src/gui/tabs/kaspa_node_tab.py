#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Contains the GUI tab (View) for managing a local Kaspa node (kaspad).
This file should only contain widget creation and layout logic.
All logic and state is managed by KaspaNodeController.
"""

import re
import tkinter as tk
from typing import TYPE_CHECKING, Any, Dict, List, Tuple, Optional

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledFrame, ScrolledText
from ttkbootstrap.tooltip import ToolTip

from src.utils.i18n import translate

from .kaspa_node_controller import KaspaNodeController

if TYPE_CHECKING:
    from src.gui.main_window import MainWindow
    from src.gui.config_manager import ConfigManager


class KaspaNodeTab(ttk.Frame):
    """
    The main ttk.Frame (View) that contains all controls
    for running and managing a kaspad node instance.
    The logic is handled by KaspaNodeController.
    """

    # --- Type Hint Declarations ---
    controller: KaspaNodeController
    notebook: ttk.Notebook
    settings_tab_frame: ttk.Frame
    log_tab_frame: ttk.Frame
    settings_pane: ttk.Frame
    log_pane: ttk.Labelframe
    preview_lf: ttk.Labelframe
    command_preview_text: ScrolledText
    copy_command_button: ttk.Button
    controls_frame: ttk.Labelframe
    start_button: ttk.Button
    stop_button: ttk.Button
    apply_restart_button: ttk.Button
    update_button: ttk.Button
    reset_button: ttk.Button
    delete_files_button: ttk.Button
    autostart_cb: ttk.Checkbutton
    db_size_frame: ttk.Frame
    db_size_label: ttk.Label
    db_size_button: ttk.Button
    version_info_frame: ttk.Frame
    local_version_label: ttk.Label
    latest_version_label: ttk.Label
    latest_date_label: ttk.Label
    external_process_frame: ttk.Frame
    external_process_label: ttk.Label
    external_process_stop_button: ttk.Button
    network_frame: ttk.Labelframe
    netsuffix_frame: ttk.Frame
    custom_paths_frame: ttk.Labelframe
    exe_cb: ttk.Checkbutton
    exe_entry: ttk.Entry
    exe_browse: ttk.Button
    url_cb: ttk.Checkbutton
    url_entry: ttk.Entry
    url_path_label: ttk.Label
    url_path_entry: ttk.Entry
    options_lf: ttk.Labelframe
    col1_label: ttk.Label
    col2_label: ttk.Label
    col3_label: ttk.Label
    col4_rpc_label: ttk.Label
    output_text: ScrolledText
    log_font_label: ttk.Label
    log_font_spinbox: ttk.Spinbox
    # --- End Type Hint Declarations ---

    def __init__(
        self,
        master: ttk.Frame,
        main_window: "MainWindow",
        config_manager: "ConfigManager",
        **kwargs: Any,
    ) -> None:
        super().__init__(master, **kwargs)
        self.pack(fill="both", expand=True)

        self.controller = KaspaNodeController(self, main_window, config_manager)

        self.controller.define_variables()
        self.controller.controller_load_settings()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.settings_tab_frame = ttk.Frame(self.notebook, padding=0)
        self.log_tab_frame = ttk.Frame(self.notebook, padding=0)

        self.notebook.add(self.settings_tab_frame, text=translate("Settings"))
        self.notebook.add(self.log_tab_frame, text=translate("Log"))

        self.settings_pane = self.create_settings_pane(self.settings_tab_frame)
        self.settings_pane.pack(fill="both", expand=True)

        self.log_pane = self.create_log_pane(self.log_tab_frame)
        # self.log_pane is packed inside create_log_pane itself

        self.controller._add_tracers()
        self.controller._update_all_entry_states()
        self.controller.update_command_preview()

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
        settings_outer_frame.grid_rowconfigure(0, weight=0)  # Preview
        settings_outer_frame.grid_rowconfigure(1, weight=0)  # Top controls
        settings_outer_frame.grid_rowconfigure(2, weight=1)  # Options

        self.preview_lf = ttk.Labelframe(
            settings_outer_frame, text=translate("Command Preview"), padding=(10, 5)
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
        self.command_preview_text.text.config(state="normal")
        self.command_preview_text.text.bind(
            "<KeyRelease>", self.controller.on_manual_command_edit
        )

        self.copy_command_button = ttk.Button(
            self.preview_lf,
            text=translate("Copy"),
            command=self.controller.copy_command_to_clipboard,
            bootstyle="info-outline",
        )
        self.copy_command_button.grid(row=0, column=1, padx=(5, 0))

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

        self.options_lf = ttk.Labelframe(
            settings_outer_frame, text=translate("Node Options"), padding=(10, 5)
        )
        self.options_lf.grid(row=2, column=0, sticky="nsew", padx=5, pady=(2, 0))
        self.options_lf.grid_columnconfigure(0, weight=1)
        self.options_lf.grid_rowconfigure(0, weight=1)

        options_scrolled_frame = ScrolledFrame(self.options_lf, autohide=True)
        options_scrolled_frame.grid(row=0, column=0, sticky="nsew")

        options_container = options_scrolled_frame.container
        options_container.grid_columnconfigure(
            (0, 1, 2, 3), weight=1, uniform="group1"
        )

        col1 = ttk.Frame(options_container, padding=5)
        col1.grid(row=0, column=0, sticky="new", padx=(0, 5))
        col2 = ttk.Frame(options_container, padding=5)
        col2.grid(row=0, column=1, sticky="new", padx=5)
        col3 = ttk.Frame(options_container, padding=5)
        col3.grid(row=0, column=2, sticky="new", padx=5)
        col4 = ttk.Frame(options_container, padding=5)
        col4.grid(row=0, column=3, sticky="new", padx=(5, 0))

        # --- Column 1: Paths & Logging ---
        self.col1_label = ttk.Label(
            col1, text=translate("Paths & Logging"), font="-weight bold"
        )
        self.col1_label.pack(anchor="w", padx=5, pady=(0, 5))
        self.create_option_entry(col1, "--configfile", "configfile")
        self.create_option_entry(col1, "--appdir", "appdir")
        self.create_option_entry(col1, "--logdir", "logdir")
        self.create_option_flag(col1, "--nologfiles", "nologfiles")

        # --- Column 2: P2P Connectivity ---
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

        # --- Column 3: DB & Performance ---
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
            if i % 2 == 0:  # Create a new row every 2 flags
                row_frame = ttk.Frame(flag_frame)
                row_frame.pack(fill="x", expand=True)

            if row_frame:  # Check if row_frame was created
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

        # --- Column 4: RPC ---
        self.col4_rpc_label = ttk.Label(col4, text=translate("RPC"), font="-weight bold")
        self.col4_rpc_label.pack(anchor="w", padx=5, pady=(0, 5))
        self.create_option_entry(col4, "--rpclisten", "rpclisten")
        self.create_option_entry(col4, "--rpclisten-borsh", "rpclisten-borsh")
        self.create_option_entry(col4, "--rpclisten-json", "rpclisten-json")
        self.create_option_entry(col4, "--rpcmaxclients", "rpcmaxclients")
        self.create_option_flag(col4, "--unsaferpc", "unsaferpc")
        self.create_option_flag(col4, "--nogrpc", "nogrpc")

        return settings_outer_frame

    def create_option_entry(
        self, master: ttk.Frame, label_text: str, key: str
    ) -> ttk.Frame:
        """
        Creates a row for an option with an entry field (or two).
        Widgets are stored in self.controller.option_vars[key] tuple.
        """
        option_vars_tuple = self.controller.option_vars.get(key)
        if not option_vars_tuple:
            logger.warning(f"Key {key} not found in controller.option_vars")
            return ttk.Frame(master)

        check_var = option_vars_tuple[0]
        val1_var = option_vars_tuple[1] if len(option_vars_tuple) > 1 else None
        val2_var = option_vars_tuple[2] if len(option_vars_tuple) > 2 and isinstance(option_vars_tuple[2], ttk.StringVar) else None

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

        widget_list: List[ttk.Widget] = [frame, label]

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
                check_var, val1_var, val2_var, *widget_list
            )
        elif isinstance(val1_var, ttk.StringVar):
            ip_entry = ttk.Entry(entry_frame, textvariable=val1_var, state="disabled")
            ip_entry.pack(side=RIGHT, fill="x", expand=True)
            widget_list.append(ip_entry)
            self.controller.option_vars[key] = (check_var, val1_var, *widget_list)

        return frame

    def create_option_flag(
        self, master: ttk.Frame, label_text: str, key: str
    ) -> ttk.Frame:
        """
        Creates a row for a flag-only option (just a checkbox).
        Stores widgets in self.controller.option_vars[key] tuple.
        """
        check_var_tuple = self.controller.option_vars.get(key, (ttk.BooleanVar(value=False), None))
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
            master, text=translate("Controls"), padding=10
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
        self.apply_restart_button.grid(row=1, column=0, sticky=EW, padx=(0, 2), pady=(2, 0))
        ToolTip(self.apply_restart_button, text=translate("Apply changes and restart the node (if running)"))

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

        # --- DB Size ---
        self.db_size_frame = ttk.Frame(self.controls_frame, padding=(0, 2))
        self.db_size_frame.pack(fill=X, expand=True, pady=(2, 0))
        self.db_size_frame.grid_columnconfigure(0, weight=1)

        self.db_size_label = ttk.Label(
            self.db_size_frame, text=f"{translate('DB Size')}: N/A"
        )
        self.db_size_label.grid(row=0, column=0, sticky="w")
        self.db_size_button = ttk.Button(
            self.db_size_frame,
            text=translate("Refresh"),
            command=self.controller.update_db_size,
            bootstyle="info-outline",
        )
        self.db_size_button.grid(row=0, column=1, sticky="e")

        # --- Version Info ---
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

        # --- External Process Detection ---
        self.external_process_frame = ttk.Frame(self.controls_frame, bootstyle="danger")
        self.external_process_frame.pack(fill=X, expand=True, pady=(5, 0), ipady=5)
        self.external_process_frame.grid_columnconfigure(1, weight=1)

        self.external_process_label = ttk.Label(
            self.external_process_frame,
            text="",
            bootstyle="danger-inverse",
            font="-size 8 -weight bold",
            wraplength=250
        )
        self.external_process_label.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 5))

        self.external_process_stop_button = ttk.Button(
            self.external_process_frame,
            text=translate("Stop External Process"),
            command=self.controller.stop_external_node,
            bootstyle="danger",
        )
        self.external_process_stop_button.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5)
        
        self.external_process_frame.pack_forget()

        self.controller._update_update_button_logic()

        return self.controls_frame

    def create_network_frame(self, master: ttk.Frame) -> ttk.Labelframe:
        """Creates the 'Network & Logging' selection frame."""
        self.network_frame = ttk.Labelframe(
            master, text=translate("Network & Logging"), padding=10
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
             logger.error("Failed to find 'netsuffix' in option_vars")
             return self.network_frame
            
        check_var, string_var, *_ = netsuffix_vars

        self.netsuffix_frame = ttk.Frame(self.network_frame)
        self.netsuffix_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        self.netsuffix_frame.grid_columnconfigure(2, weight=1)

        cb = ttk.Checkbutton(
            self.netsuffix_frame,
            variable=check_var,
            command=lambda k="netsuffix": self.controller._on_check_toggle(k),
        )
        cb.grid(row=0, column=0, sticky="w")
        ToolTip(cb, text=translate("Tooltip_netsuffix"), wraplength=300)

        label = ttk.Label(self.netsuffix_frame, text="--netsuffix", bootstyle="secondary")
        label.grid(row=0, column=1, sticky="w", padx=(2, 5))
        ToolTip(label, text=translate("Tooltip_netsuffix"), wraplength=300)
        
        if not isinstance(string_var, ttk.StringVar):
             logger.error("netsuffix string_var is not a StringVar")
             return self.network_frame

        entry = ttk.Entry(self.netsuffix_frame, textvariable=string_var, state="disabled")
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
            master, text=translate("Custom Paths"), padding=10
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
            url_frame, textvariable=self.controller.custom_url_var, state="disabled"
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

        self.controller.use_custom_exe_var.trace_add(
            "write", self.controller._on_custom_exe_toggled
        )
        self.controller.use_custom_url_var.trace_add(
            "write", self.controller._on_custom_url_toggled
        )

        self.controller._toggle_entry_state(
            self.controller.use_custom_exe_var, [self.exe_entry, self.exe_browse]
        )
        self.controller._toggle_entry_state(
            self.controller.use_custom_url_var,
            [self.url_entry, self.url_path_label, self.url_path_entry],
        )

        return self.custom_paths_frame

    def _update_log_font(self, *args: Any) -> None:
        """Update the font size in the log window."""
        if hasattr(self, "output_text"):
            try:
                size = self.controller.log_font_size_var.get()
                self.output_text.text.config(font=("Courier New", size))
                self.output_text.text.tag_configure("error", font=f"Courier {size} bold")
                self.output_text.text.tag_configure(
                    "separator", font=f"Courier {size} bold"
                )
                if hasattr(self.controller, "config_manager"):
                    self.controller._save_settings()
            except tk.TclError:
                pass

    def create_log_pane(self, master: ttk.Frame) -> ttk.Labelframe:
        """Create the 'Live Log' panel."""
        self.log_pane = ttk.Labelframe(
            master, text=translate("Live Log"), padding=10
        )
        self.log_pane.pack(fill=BOTH, expand=True, padx=0, pady=0) 
        
        self.log_pane.grid_rowconfigure(1, weight=1)
        self.log_pane.grid_columnconfigure(0, weight=1)

        control_frame = ttk.Frame(self.log_pane)
        control_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        self.log_font_label = ttk.Label(
            control_frame, text=f"{translate('Font Size')}:"
        )
        self.log_font_label.pack(side=LEFT, padx=(0, 5))

        self.log_font_spinbox = ttk.Spinbox(
            control_frame,
            from_=6,
            to=20,
            textvariable=self.controller.log_font_size_var,
            width=3,
            command=self._update_log_font,
        )
        self.log_font_spinbox.pack(side=LEFT)

        self.output_text = ScrolledText(
            self.log_pane, wrap="word", height=20, autohide=True, bootstyle="dark"
        )
        self.output_text.grid(row=1, column=0, sticky="nsew")

        style = self.controller.main_window.style
        font_size = self.controller.log_font_size_var.get()

        try:
            self.output_text.text.tag_configure("info", foreground=style.colors.info)
            self.output_text.text.tag_configure(
                "warning", foreground=style.colors.warning
            )
            self.output_text.text.tag_configure(
                "error",
                foreground=style.colors.danger,
                font=f"Courier {font_size} bold",
            )
            self.output_text.text.tag_configure(
                "debug", foreground=style.colors.secondary
            )
        except Exception:
            pass
        self.output_text.text.tag_configure("trace", foreground="#6610F2")
        self.output_text.text.tag_configure("timestamp", foreground="#ADB5BD")
        self.output_text.text.tag_configure(
            "separator", foreground="#28A745", font=f"Courier {font_size} bold"
        )

        self.output_text.text.config(state="disabled")
        self._update_log_font()

        return self.log_pane

    def _insert_output(self, text_line: str) -> None:
        """
        Insert a line of text into the log, applying syntax highlighting.
        This method is thread-safe as it's called via self.after().
        """
        try:
            if not self.output_text.winfo_exists():
                return

            self.output_text.text.config(state="normal")
            start_index = self.output_text.text.index("end-1c linestart")
            
            self.output_text.text.insert("end", f"{text_line}\n")
            
            end_index = self.output_text.text.index("end-1c lineend")
            line_content = self.output_text.text.get(start_index, end_index).strip()

            if re.search(r"\[INFO\s*\]", line_content):
                self.output_text.text.tag_add("info", start_index, end_index)
            elif re.search(r"\[WARN\s*\]", line_content):
                self.output_text.text.tag_add("warning", start_index, end_index)
            elif re.search(r"\[ERROR\s*\]", line_content) or "error:" in line_content.lower():
                self.output_text.text.tag_add("error", start_index, end_index)
            elif re.search(r"\[DEBUG\s*\]", line_content):
                self.output_text.text.tag_add("debug", start_index, end_index)
            elif re.search(r"\[TRACE\s*\]", line_content):
                self.output_text.text.tag_add("trace", start_index, end_index)
            elif "--- Starting" in line_content or "--- Process Terminated" in line_content:
                self.output_text.text.tag_add("separator", start_index, end_index)

            timestamp_match = re.search(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", line_content)
            if timestamp_match:
                ts_start = f"{start_index}+{timestamp_match.start()}c"
                ts_end = f"{start_index}+{timestamp_match.end()}c"
                self.output_text.text.tag_add("timestamp", ts_start, ts_end)

            self.output_text.text.see("end")
            self.output_text.text.config(state="disabled")
        except tk.TclError:
            pass

    def re_translate(self) -> None:
        """Update all translatable strings in the UI."""
        self.notebook.tab(0, text=translate("Settings"))
        self.notebook.tab(1, text=translate("Log"))

        self.log_pane.config(text=translate("Live Log"))

        self.controls_frame.config(text=translate("Controls"))
        self.start_button.config(text=translate("Start Kaspa Node"))
        self.stop_button.config(text=translate("Stop Kaspa Node"))
        self.apply_restart_button.config(text=translate("Apply & Restart"))
        
        self.controller._update_update_button_logic()
        
        self.reset_button.config(text=translate("Reset"))
        self.delete_files_button.config(text=translate("Delete Node Files"))
        self.autostart_cb.config(text=translate("Start Node on App Launch"))

        if "N/A" in self.db_size_label.cget("text"):
            self.db_size_label.config(text=f"{translate('DB Size')}: N/A")
        elif translate("Calculating...") in self.db_size_label.cget("text"):
            self.db_size_label.config(
                text=f"{translate('DB Size')}: {translate('Calculating...')}"
            )
        self.db_size_button.config(text=translate("Refresh"))

        self.preview_lf.config(text=translate("Command Preview"))
        self.copy_command_button.config(text=translate("Copy"))
        self.log_font_label.config(text=f"{translate('Font Size')}:")

        self.network_frame.config(text=translate("Network & Logging"))
        
        if self.network_frame.winfo_children():
            self.network_frame.winfo_children()[0].config(text=f"{translate('Network')}:")
            if len(self.network_frame.winfo_children()) > 2:
                self.network_frame.winfo_children()[2].config(
                    text=f"{translate('Logging Level')}:"
                )

        if hasattr(self, "col1_label"):
            self.col1_label.config(text=translate("Paths & Logging"))
        if hasattr(self, "options_lf"):
            self.options_lf.config(text=translate("Node Options"))
        if hasattr(self, "col4_rpc_label"):
            self.col4_rpc_label.config(text=translate("RPC"))
        if hasattr(self, "col2_label"):
            self.col2_label.config(text=translate("P2P Connectivity"))
        if hasattr(self, "col3_label"):
            self.col3_label.config(text=translate("DB & Performance"))

        for key, item_tuple in self.controller.option_vars.items():
            if len(item_tuple) > 2 and isinstance(item_tuple[2], ttk.Frame):
                label_text_key = f"Tooltip_{key}"
                label_widget: Optional[ttk.Label] = None
                cb_widget: Optional[ttk.Checkbutton] = None

                if item_tuple[1] is not None:
                    if len(item_tuple) > 3 and isinstance(item_tuple[3], ttk.Label):
                        label_widget = item_tuple[3]
                        if item_tuple[2].winfo_children():
                            cb_widget = item_tuple[2].winfo_children()[0]
                else:
                    if len(item_tuple) > 3 and isinstance(item_tuple[3], ttk.Checkbutton):
                        cb_widget = item_tuple[3]
                
                if label_widget:
                    label_widget.config(text=f"--{key}")
                    ToolTip(label_widget, text=translate(label_text_key), wraplength=300)
                if cb_widget:
                    if item_tuple[1] is None:
                        cb_widget.config(text=f"--{key}")
                    ToolTip(cb_widget, text=translate(label_text_key), wraplength=300)

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
            self.custom_paths_frame.config(text=translate("Custom Paths"))
            self.exe_cb.config(text=translate("Use Custom kaspad.exe"))
            self.url_cb.config(text=translate("Use Custom Download URL"))
            self.url_path_label.config(
                text=translate("Enter the exact path of the .exe inside the zip:")
            )
        
        if f"{translate('Local Version')}:" not in self.controller.local_node_version_var.get():
            current_version = self.controller.local_node_version_var.get().split(":")[-1].strip()
            self.controller.local_node_version_var.set(
                f"{translate('Local Version')}: {current_version}"
            )

        if f"{translate('Latest Version')}:" not in self.controller.latest_node_version_var.get():
            current_version = self.controller.latest_node_version_var.get().split(":")[-1].strip()
            self.controller.latest_node_version_var.set(
                f"{translate('Latest Version')}: {current_version}"
            )

        if f"{translate('Updated')}:" not in self.controller.latest_node_date_var.get():
            current_date = self.controller.latest_node_date_var.get().split(":")[-1].strip()
            self.controller.latest_node_date_var.set(f"{translate('Updated')}: {current_date}")
