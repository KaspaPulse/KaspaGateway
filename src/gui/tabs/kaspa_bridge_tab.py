#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contains the GUI View classes for the Kaspa Bridge tab.
- BridgeInstanceTab: The View for a single bridge instance.
- KaspaBridgeTab: The main container Notebook that holds BridgeInstanceTabs.
"""

from __future__ import annotations

import logging
import re
import tkinter as tk
from tkinter import END, filedialog, messagebox
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

import ttkbootstrap as ttk
from ttkbootstrap.constants import (
    BOTH,
    BOTTOM,
    CENTER,
    DANGER,
    DISABLED,
    END,
    EW,
    HORIZONTAL,
    INFO,
    LEFT,
    NORMAL,
    NSEW,
    RIGHT,
    SOLID,
    SUCCESS,
    TOP,
    WORD,
    W,
    X,
    Y,
)
from ttkbootstrap.scrolled import ScrolledFrame, ScrolledText
from ttkbootstrap.toast import ToastNotification
from ttkbootstrap.tooltip import ToolTip

from src.gui.components.log_viewer import LogPane
from src.gui.tabs.kaspa_bridge_controller import BridgeInstanceController
from src.utils.i18n import translate

if TYPE_CHECKING:
    from src.gui.config_manager import ConfigManager
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


class BridgeInstanceTab(ttk.Frame):
    """
    A self-contained ttk.Frame that builds the GUI (View)
    for a single instance of the kaspa-stratum-bridge.
    Scrolling is handled *inside* the settings tab.
    The logic is handled by BridgeInstanceController.
    """

    main_window: "MainWindow"
    controller: BridgeInstanceController
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
    start_button: ttk.Button
    stop_button: ttk.Button
    apply_restart_button: ttk.Button
    update_button: ttk.Button
    reset_button: ttk.Button
    delete_files_button: ttk.Button
    autostart_cb: ttk.Checkbutton

    # New UI for startup delay & reconnect
    startup_delay_frame: ttk.Frame
    startup_delay_label: ttk.Label
    startup_delay_spin: ttk.Spinbox
    auto_reconnect_cb: ttk.Checkbutton

    external_process_frame: ttk.Frame
    external_process_label: ttk.Label
    external_process_stop_button: ttk.Button
    version_info_frame: ttk.Frame
    local_version_label: ttk.Label
    latest_version_label: ttk.Label
    latest_date_label: ttk.Label
    enable_bridge_2_cb: ttk.Checkbutton

    # New UI elements for Download URL
    url_display_frame: ttk.Frame
    download_url_label: ttk.Label
    download_url_text: ScrolledText
    set_default_url_button: ttk.Button

    main_settings_frame: ttk.Labelframe
    difficulty_frame: ttk.Labelframe
    logging_frame: ttk.Labelframe
    advanced_frame: ttk.Labelframe
    custom_paths_frame: ttk.Labelframe
    exe_cb: ttk.Checkbutton
    exe_entry: ttk.Entry
    exe_browse: ttk.Button
    config_cb: ttk.Checkbutton
    config_entry: ttk.Entry
    config_browse: ttk.Button
    url_cb: ttk.Checkbutton
    url_entry: ttk.Entry
    url_exe_path_label: ttk.Label
    url_exe_path_entry: ttk.Entry
    url_config_path_label: ttk.Label
    url_config_path_entry: ttk.Entry

    def __init__(
        self,
        master: ttk.Notebook,
        main_window: "MainWindow",
        config_manager: "ConfigManager",
        instance_id: str,
        main_bridge_tab: Optional["KaspaBridgeTab"] = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize the Bridge Instance Tab View.
        """
        super().__init__(master, **kwargs)

        self.main_window = main_window

        self.controller = BridgeInstanceController(
            self, main_window, config_manager, instance_id, main_bridge_tab
        )

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=BOTH, expand=True, padx=0, pady=0)

        self.settings_tab_frame = ttk.Frame(self.notebook, padding=0)
        self.settings_tab_frame.grid_rowconfigure(0, weight=1)
        self.settings_tab_frame.grid_columnconfigure(0, weight=1)

        self.log_tab_frame = ttk.Frame(self.notebook, padding=0)
        self.log_tab_frame.grid_rowconfigure(0, weight=1)
        self.log_tab_frame.grid_columnconfigure(0, weight=1)

        self.notebook.add(self.settings_tab_frame, text=f" {translate('Settings')} ")
        self.notebook.add(self.log_tab_frame, text=f" {translate('Log')} ")

        settings_container_frame = ttk.Frame(self.settings_tab_frame)
        settings_container_frame.grid(row=0, column=0, sticky=NSEW)

        self.settings_pane = self.create_settings_pane(settings_container_frame)

        self.settings_pane.pack(fill=BOTH, expand=True)

        self.log_pane = self.create_log_pane(self.log_tab_frame)
        self.log_pane.pack(fill=BOTH, expand=True, padx=10, pady=(0, 10))

        self.controller._add_tracers()
        self.controller.update_command_preview()

    def create_settings_pane(self, master: ttk.Frame) -> ttk.Frame:
        """Create the main settings panel with all controls."""
        settings_outer_frame = ttk.Frame(master, padding=5)
        settings_outer_frame.grid_columnconfigure(0, weight=1)
        settings_outer_frame.grid_rowconfigure(0, weight=0)
        settings_outer_frame.grid_rowconfigure(1, weight=1)

        self.preview_lf = ttk.Labelframe(
            settings_outer_frame, text=f" {translate('Command Preview')} ", padding=10
        )
        self.preview_lf.grid(row=0, column=0, sticky=NSEW, padx=5, pady=(0, 10))
        self.preview_lf.grid_columnconfigure(0, weight=1)

        self.command_preview_text = ScrolledText(
            self.preview_lf,
            height=3,
            font=("Courier New", 9),
            wrap="word",
            autohide=True,
            bootstyle="round",
        )
        self.command_preview_text.grid(row=0, column=0, sticky=EW)
        self.command_preview_text.text.config(state="disabled")

        self.copy_command_button = ttk.Button(
            self.preview_lf,
            text=translate("Copy"),
            command=self.controller.copy_command_to_clipboard,
            bootstyle="info-outline",
        )
        self.copy_command_button.grid(row=0, column=1, padx=(5, 0))

        options_frame = ttk.Frame(settings_outer_frame)
        options_frame.grid(row=1, column=0, sticky=NSEW)

        options_frame.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="group1")
        options_frame.grid_rowconfigure(0, weight=1)

        col1_frame = ttk.Frame(options_frame)
        col1_frame.grid(row=0, column=0, sticky="new", padx=(0, 5))
        col1_frame.grid_columnconfigure(0, weight=1)

        col2_frame = ttk.Frame(options_frame)
        col2_frame.grid(row=0, column=1, sticky="new", padx=5)
        col2_frame.grid_columnconfigure(0, weight=1)

        col3_frame = ttk.Frame(options_frame)
        col3_frame.grid(row=0, column=2, sticky="new", padx=5)
        col3_frame.grid_columnconfigure(0, weight=1)

        col4_frame = ttk.Frame(options_frame)
        col4_frame.grid(row=0, column=3, sticky="new", padx=(5, 0))
        col4_frame.grid_columnconfigure(0, weight=1)

        self.create_controls_frame(col1_frame).grid(
            row=0, column=0, sticky="new", pady=(0, 5)
        )

        self.create_main_settings_frame(col2_frame).grid(
            row=0, column=0, sticky="new", pady=(0, 5)
        )
        self.create_logging_frame(col2_frame).grid(
            row=1, column=0, sticky="new", pady=5
        )

        self.create_difficulty_frame(col3_frame).grid(
            row=0, column=0, sticky="new", pady=(0, 5)
        )
        self.create_advanced_frame(col3_frame).grid(
            row=1, column=0, sticky="new", pady=5
        )

        self.create_custom_paths_frame(col4_frame).grid(
            row=0, column=0, sticky="new", pady=(0, 5)
        )

        return settings_outer_frame

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
            text=translate("Start Kaspa Bridge"),
            command=self.controller.start_bridge,
            bootstyle=SUCCESS,
        )
        self.start_button.grid(row=0, column=0, sticky=EW, padx=(0, 2), pady=(0, 2))

        self.stop_button = ttk.Button(
            button_frame,
            text=translate("Stop Kaspa Bridge"),
            command=self.controller.stop_bridge,
            bootstyle=DANGER,
            state="disabled",
        )
        self.stop_button.grid(row=0, column=1, sticky=EW, padx=(2, 0), pady=(0, 2))

        self.apply_restart_button = ttk.Button(
            button_frame,
            text=translate("Apply & Restart"),
            command=self.controller.apply_and_restart_bridge,
            bootstyle="warning",
            state="disabled",
        )
        self.apply_restart_button.grid(
            row=1, column=0, sticky=EW, padx=(0, 2), pady=(2, 0)
        )
        ToolTip(
            self.apply_restart_button,
            text=translate("Apply changes and restart the bridge (if running)"),
        )

        self.update_button = ttk.Button(
            button_frame,
            text=translate("Update Bridge"),
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
            text=translate("Delete Bridge Files"),
            command=self.controller._delete_bridge_files,
            bootstyle="danger-outline",
        )
        self.delete_files_button.grid(
            row=2, column=1, sticky=EW, padx=(2, 0), pady=(2, 0)
        )

        # Startup Delay & Reconnect UI
        self.startup_delay_frame = ttk.Frame(self.controls_frame)
        self.startup_delay_frame.pack(fill=X, expand=True, pady=(10, 0))

        self.startup_delay_label = ttk.Label(
            self.startup_delay_frame,
            text=translate("Startup Delay (sec):"),
            font="-size 8",
        )
        self.startup_delay_label.pack(side=LEFT, padx=(0, 5))

        self.startup_delay_spin = ttk.Spinbox(
            self.startup_delay_frame,
            from_=0,
            to=300,
            textvariable=self.controller.startup_delay_var,
            width=5,
            font="-size 8",
        )
        self.startup_delay_spin.pack(side=LEFT)

        self.autostart_cb = ttk.Checkbutton(
            self.controls_frame,
            text=translate("Start Bridge on App Launch"),
            variable=self.controller.autostart_var,
        )
        self.autostart_cb.pack(fill=X, expand=True, pady=(5, 0), anchor="w")

        self.auto_reconnect_cb = ttk.Checkbutton(
            self.controls_frame,
            text=translate("Auto-Reconnect on Failure"),
            variable=self.controller.auto_reconnect_var,
            bootstyle="danger",
        )
        self.auto_reconnect_cb.pack(fill=X, expand=True, pady=(2, 0), anchor="w")
        ToolTip(
            self.auto_reconnect_cb,
            text=translate(
                "Automatically restart the bridge if it crashes or loses connection to the node."
            ),
        )

        self.version_info_frame = ttk.Frame(self.controls_frame)
        self.version_info_frame.pack(fill=X, expand=True, pady=(5, 0))

        self.local_version_label = ttk.Label(
            self.version_info_frame,
            textvariable=self.controller.local_bridge_version_var,
            bootstyle="secondary",
            font="-size 8",
        )
        self.local_version_label.pack(side=LEFT, padx=(0, 10))

        latest_info_frame = ttk.Frame(self.version_info_frame)
        latest_info_frame.pack(side=LEFT)

        self.latest_version_label = ttk.Label(
            latest_info_frame,
            textvariable=self.controller.latest_bridge_version_var,
            bootstyle="secondary",
            font="-size 8",
        )
        self.latest_version_label.pack(side=TOP, anchor="w")

        self.latest_date_label = ttk.Label(
            latest_info_frame,
            textvariable=self.controller.latest_bridge_date_var,
            bootstyle="secondary",
            font="-size 8",
        )
        self.latest_date_label.pack(side=TOP, anchor="w")

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
            command=self.controller.stop_external_bridge,
            bootstyle="danger",
        )
        self.external_process_stop_button.grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=5
        )

        self.external_process_frame.pack_forget()

        # --- NEW SECTION START: Download URL Display ---
        ttk.Separator(self.controls_frame).pack(fill=X, pady=(10, 5), padx=5)

        self.url_display_frame = ttk.Frame(self.controls_frame)
        self.url_display_frame.pack(
            side=BOTTOM, fill=X, expand=True, padx=5, pady=(0, 5)
        )

        self.download_url_label = ttk.Label(
            self.url_display_frame,
            text=translate("Bridge Download URL"),
            font="-size 8",
        )
        self.download_url_label.pack(anchor="w")

        # Using ScrolledText to allow multi-line display of long URLs
        self.download_url_text = ScrolledText(
            self.url_display_frame, height=3, font=("Segoe UI", 8), autohide=True
        )
        self.download_url_text.pack(fill=X, expand=True, pady=(2, 0))

        # Initialize text widget with current value
        current_url = self.controller.bridge_download_url_var.get()
        self.download_url_text.text.insert("1.0", current_url)

        # Set Default Button
        self.set_default_url_button = ttk.Button(
            self.url_display_frame,
            text=translate("Set Default"),
            command=self._on_save_url_click,
            bootstyle="secondary-outline",
            state="disabled",
        )
        self.set_default_url_button.pack(fill=X, expand=True, pady=(5, 0))

        # Bind KeyRelease to detect changes
        self.download_url_text.text.bind("<KeyRelease>", self._on_url_text_change)
        # --- NEW SECTION END ---

        if self.controller.instance_id == "_1" and self.controller.main_bridge_tab:
            ttk.Separator(self.controls_frame).pack(fill=X, pady=5, padx=2)
            self.enable_bridge_2_cb = ttk.Checkbutton(
                self.controls_frame,
                text=translate("Enable Bridge 2"),
                variable=self.controller.main_bridge_tab.enable_bridge_2_var,
            )
            self.enable_bridge_2_cb.pack(fill=X, expand=True, pady=(5, 0), anchor="w")

        return self.controls_frame

    def _on_url_text_change(self, event: Any) -> None:
        """Enable the 'Set Default' button when text changes."""
        current_text = self.download_url_text.text.get("1.0", "end-1c").strip()
        saved_text = self.controller.bridge_download_url_var.get().strip()

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
        # Reset button state
        self.set_default_url_button.config(
            state="disabled", bootstyle="secondary-outline"
        )

    def toggle_entry_state(
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

    def _create_checkbox_entry_row(
        self,
        master: ttk.Frame,
        label_key: str,
        var: Any,
        enabled_var: ttk.BooleanVar,
        tooltip_key: str,
    ) -> None:
        """Helper to create a row with a checkbox, label, and entry/entries."""
        row = ttk.Frame(master)
        row.pack(fill="x", padx=5, pady=(5, 5))

        cb = ttk.Checkbutton(row, text=translate(label_key), variable=enabled_var)
        cb.pack(side=TOP, anchor="w")
        ToolTip(cb, text=translate(tooltip_key), wraplength=300)

        entry_frame = ttk.Frame(row)
        entry_frame.pack(side=TOP, fill="x", expand=True, padx=(10, 0), pady=(2, 0))

        all_entries: List[tk.Widget] = []

        if isinstance(var, tuple) and len(var) == 2:
            ip_var, port_var = var
            port_entry = ttk.Entry(entry_frame, textvariable=port_var, width=8)
            port_entry.pack(side=tk.RIGHT, padx=(2, 0))
            all_entries.append(port_entry)

            colon_label = ttk.Label(entry_frame, text=":")
            colon_label.pack(side=tk.RIGHT)
            all_entries.append(colon_label)

            ip_entry = ttk.Entry(entry_frame, textvariable=ip_var)
            ip_entry.pack(side=tk.RIGHT, fill="x", expand=True, padx=(0, 2))
            all_entries.append(ip_entry)

        else:
            entry = ttk.Entry(entry_frame, textvariable=var)
            entry.pack(side=tk.RIGHT, fill="x", expand=True)
            all_entries.append(entry)

        enabled_var.trace_add(
            "write",
            lambda *args, ev=enabled_var, entries=all_entries: self.toggle_entry_state(
                ev, entries
            ),
        )
        self.toggle_entry_state(enabled_var, all_entries)

    def _create_flag_row(
        self,
        master: ttk.Frame,
        label_key: str,
        enabled_var: ttk.BooleanVar,
        value_var: ttk.StringVar,
        tooltip_key: str,
    ) -> None:
        """Helper to create a row with a checkbox and True/False radio buttons."""
        frame = ttk.Frame(master)
        frame.pack(fill="x", anchor="w", padx=5, pady=5)

        cb = ttk.Checkbutton(frame, text=translate(label_key), variable=enabled_var)
        cb.pack(side=TOP, anchor="w")
        ToolTip(cb, text=translate(tooltip_key), wraplength=300)

        radio_frame = ttk.Frame(frame)
        radio_frame.pack(side=TOP, fill="x", expand=True, padx=(10, 0), pady=(2, 0))

        true_rb = ttk.Radiobutton(
            radio_frame,
            text=translate("True"),
            variable=value_var,
            value="true",
        )
        true_rb.pack(side=LEFT)

        false_rb = ttk.Radiobutton(
            radio_frame,
            text=translate("False"),
            variable=value_var,
            value="false",
        )
        false_rb.pack(side=LEFT, padx=(5, 0))

        def toggle_radios(*args: Any) -> None:
            state: str = tk.NORMAL if enabled_var.get() else DISABLED
            true_rb.config(state=state)
            false_rb.config(state=state)

        enabled_var.trace_add("write", toggle_radios)
        toggle_radios()

    def create_main_settings_frame(self, master: ttk.Frame) -> ttk.Labelframe:
        """Create the 'Main Settings' labelframe."""
        self.main_settings_frame = ttk.Labelframe(
            master, text=f" {translate('Main Settings')} ", padding=10
        )
        self._create_checkbox_entry_row(
            self.main_settings_frame,
            "-kaspa (Kaspad Address)",
            self.controller.kaspa_addr_var,
            self.controller.kaspa_addr_enabled_var,
            "Tooltip_ks_kaspa",
        )
        self._create_checkbox_entry_row(
            self.main_settings_frame,
            "-stratum (e.g., :5555)",
            self.controller.stratum_port_var,
            self.controller.stratum_port_enabled_var,
            "Tooltip_ks_stratum",
        )
        return self.main_settings_frame

    def create_difficulty_frame(self, master: ttk.Frame) -> ttk.Labelframe:
        """Create the 'Difficulty & Vardiff' labelframe."""
        self.difficulty_frame = ttk.Labelframe(
            master, text=f" {translate('Difficulty & Vardiff')} ", padding=10
        )
        self._create_checkbox_entry_row(
            self.difficulty_frame,
            "-mindiff (Minimum Difficulty)",
            self.controller.min_diff_var,
            self.controller.min_diff_enabled_var,
            "Tooltip_ks_mindiff",
        )
        self._create_checkbox_entry_row(
            self.difficulty_frame,
            "-sharespermin (Shares/Min Rate)",
            self.controller.shares_per_min_var,
            self.controller.shares_per_min_enabled_var,
            "Tooltip_ks_sharespermin",
        )
        self._create_flag_row(
            self.difficulty_frame,
            "-vardiff (Enable Variable Difficulty)",
            self.controller.vardiff_enabled_var,
            self.controller.vardiff_var,
            "Tooltip_ks_vardiff",
        )
        self._create_flag_row(
            self.difficulty_frame,
            "-pow2clamp (Required for ASICs)",
            self.controller.pow2clamp_enabled_var,
            self.controller.pow2clamp_var,
            "Tooltip_ks_pow2clamp",
        )
        return self.difficulty_frame

    def create_logging_frame(self, master: ttk.Frame) -> ttk.Labelframe:
        """Create the 'Logging & Stats' labelframe."""
        self.logging_frame = ttk.Labelframe(
            master, text=f" {translate('Logging & Stats')} ", padding=10
        )
        self._create_flag_row(
            self.logging_frame,
            "-log (Enable Log File)",
            self.controller.log_file_enabled_var,
            self.controller.log_file_var,
            "Tooltip_ks_log",
        )
        self._create_flag_row(
            self.logging_frame,
            "-stats (Show Stats in Console)",
            self.controller.console_stats_enabled_var,
            self.controller.console_stats_var,
            "Tooltip_ks_stats",
        )
        self._create_flag_row(
            self.logging_frame,
            "-vardiffstats (Show Vardiff Stats)",
            self.controller.vardiff_stats_enabled_var,
            self.controller.vardiff_stats_var,
            "Tooltip_ks_vardiffstats",
        )
        return self.logging_frame

    def create_advanced_frame(self, master: ttk.Frame) -> ttk.Labelframe:
        """Create the 'Advanced' labelframe."""
        self.advanced_frame = ttk.Labelframe(
            master, text=f" {translate('Advanced')} ", padding=10
        )
        self._create_checkbox_entry_row(
            self.advanced_frame,
            "-blockwait (e.g., 3s, 2000ms)",
            self.controller.blockwait_var,
            self.controller.blockwait_enabled_var,
            "Tooltip_ks_blockwait",
        )
        self._create_checkbox_entry_row(
            self.advanced_frame,
            "-prom (e.g., :2112)",
            self.controller.prom_port_var,
            self.controller.prom_port_enabled_var,
            "Tooltip_ks_prom",
        )
        self._create_checkbox_entry_row(
            self.advanced_frame,
            "-extranonce (bytes)",
            self.controller.extranonce_var,
            self.controller.extranonce_enabled_var,
            "Tooltip_ks_extranonce",
        )
        self._create_checkbox_entry_row(
            self.advanced_frame,
            "-hcp (Health Check Port)",
            self.controller.hcp_var,
            self.controller.hcp_enabled_var,
            "Tooltip_hcp",
        )
        return self.advanced_frame

    def create_custom_paths_frame(self, master: ttk.Frame) -> ttk.Labelframe:
        """Create the 'Custom Paths' labelframe."""
        self.custom_paths_frame = ttk.Labelframe(
            master, text=f" {translate('Custom Paths')} ", padding=10
        )

        self.exe_cb = ttk.Checkbutton(
            self.custom_paths_frame,
            text=translate("Use Custom ks_bridge.exe"),
            variable=self.controller.use_custom_exe_var,
        )
        self.exe_cb.pack(side=TOP, fill=X, anchor="w")
        exe_frame = ttk.Frame(self.custom_paths_frame)
        exe_frame.pack(side=TOP, fill=X, expand=True, padx=(20, 0), pady=(2, 5))
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
                "Select ks_bridge.exe",
                [("Executable", "*.exe")],
            ),
            width=3,
            state="disabled",
        )
        self.exe_browse.pack(side=LEFT, padx=(5, 0))

        self.config_cb = ttk.Checkbutton(
            self.custom_paths_frame,
            text=translate("Use Custom config.yaml"),
            variable=self.controller.use_custom_config_var,
        )
        self.config_cb.pack(side=TOP, fill=X, anchor="w", pady=(5, 0))
        config_frame = ttk.Frame(self.custom_paths_frame)
        config_frame.pack(side=TOP, fill=X, expand=True, padx=(20, 0), pady=(2, 10))
        self.config_entry = ttk.Entry(
            config_frame,
            textvariable=self.controller.custom_config_path_var,
            state="disabled",
        )
        self.config_entry.pack(side=LEFT, fill=X, expand=True)
        self.config_browse = ttk.Button(
            config_frame,
            text="...",
            command=lambda: self.controller._browse_file(
                self.controller.custom_config_path_var,
                "Select config.yaml",
                [("YAML Config", "*.yaml"), ("All Files", "*.*")],
            ),
            width=3,
            state="disabled",
        )
        self.config_browse.pack(side=LEFT, padx=(5, 0))

        self.url_cb = ttk.Checkbutton(
            self.custom_paths_frame,
            text=translate("Use Custom Download URL"),
            variable=self.controller.use_custom_url_var,
        )
        self.url_cb.pack(side=TOP, fill=X, anchor="w", pady=(5, 0))
        url_frame = ttk.Frame(self.custom_paths_frame)
        url_frame.pack(side=TOP, fill=X, expand=True, padx=(20, 0), pady=(2, 5))
        self.url_entry = ttk.Entry(
            url_frame,
            textvariable=self.controller.custom_url_var,
            state="disabled",
        )
        self.url_entry.pack(fill=X, expand=True)

        self.url_exe_path_label = ttk.Label(
            self.custom_paths_frame,
            text=translate("Enter the exact path of the .exe inside the zip:"),
            state="disabled",
        )
        self.url_exe_path_label.pack(
            side=TOP, fill=X, anchor="w", padx=(20, 0), pady=(5, 0)
        )
        url_exe_frame = ttk.Frame(self.custom_paths_frame)
        url_exe_frame.pack(side=TOP, fill=X, expand=True, padx=(20, 0), pady=(2, 5))
        self.url_exe_path_entry = ttk.Entry(
            url_exe_frame,
            textvariable=self.controller.custom_url_exe_path_var,
            state="disabled",
        )
        self.url_exe_path_entry.pack(fill=X, expand=True)

        self.url_config_path_label = ttk.Label(
            self.custom_paths_frame,
            text=translate("Enter the exact path of the config.yaml inside the zip:"),
            state="disabled",
        )
        self.url_config_path_label.pack(
            side=TOP, fill=X, anchor="w", padx=(20, 0), pady=(5, 0)
        )
        url_config_frame = ttk.Frame(self.custom_paths_frame)
        url_config_frame.pack(side=TOP, fill=X, expand=True, padx=(20, 0), pady=(2, 5))
        self.url_config_path_entry = ttk.Entry(
            url_config_frame,
            textvariable=self.controller.custom_url_config_path_var,
            state="disabled",
        )
        self.url_config_path_entry.pack(fill=X, expand=True)

        self.toggle_entry_state(
            self.controller.use_custom_exe_var, [self.exe_entry, self.exe_browse]
        )
        self.toggle_entry_state(
            self.controller.use_custom_config_var,
            [self.config_entry, self.config_browse],
        )
        custom_url_widgets: List[tk.Widget] = [
            self.url_entry,
            self.url_exe_path_label,
            self.url_exe_path_entry,
            self.url_config_path_label,
            self.url_config_path_entry,
        ]
        self.toggle_entry_state(self.controller.use_custom_url_var, custom_url_widgets)

        return self.custom_paths_frame

    def create_log_pane(self, master: ttk.Frame) -> ttk.Labelframe:
        """Create the 'Live Log' panel using the new LogPane component."""
        self.log_pane = ttk.Labelframe(
            master, text=f" {translate('Live Log')} ", padding=10
        )
        self.log_pane.grid_rowconfigure(0, weight=1)
        self.log_pane.grid_columnconfigure(0, weight=1)

        self.log_pane_component = LogPane(self.log_pane, self.main_window)
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

    def re_translate_widgets(self) -> None:
        """Update all translatable strings in the UI."""
        self.notebook.tab(0, text=f" {translate('Settings')} ")
        self.notebook.tab(1, text=f" {translate('Log')} ")

        if hasattr(self, "log_pane_component"):
            self.log_pane_component.re_translate()

        self.controls_frame.config(text=f" {translate('Controls')} ")

        self.start_button.config(text=translate("Start Kaspa Bridge"))
        self.stop_button.config(text=translate("Stop Kaspa Bridge"))
        self.apply_restart_button.config(text=translate("Apply & Restart"))

        self.reset_button.config(text=translate("Reset"))
        self.delete_files_button.config(text=translate("Delete Bridge Files"))

        # Update startup/recovery labels
        self.startup_delay_label.config(text=translate("Startup Delay (sec):"))
        self.autostart_cb.config(text=translate("Start Bridge on App Launch"))
        self.auto_reconnect_cb.config(text=translate("Auto-Reconnect on Failure"))

        if self.controller.instance_id == "_1" and hasattr(self, "enable_bridge_2_cb"):
            self.enable_bridge_2_cb.config(text=translate("Enable Bridge 2"))

        if hasattr(self, "download_url_label"):
            self.download_url_label.config(text=translate("Bridge Download URL"))
        if hasattr(self, "set_default_url_button"):
            self.set_default_url_button.config(text=translate("Set Default"))

        self.main_settings_frame.config(text=f" {translate('Main Settings')} ")
        self.main_settings_frame.winfo_children()[0].winfo_children()[0].config(
            text=translate("-kaspa (Kaspad Address)")
        )
        self.main_settings_frame.winfo_children()[1].winfo_children()[0].config(
            text=translate("-stratum (e.g., :5555)")
        )

        self.difficulty_frame.config(text=f" {translate('Difficulty & Vardiff')} ")
        self.difficulty_frame.winfo_children()[0].winfo_children()[0].config(
            text=translate("-mindiff (Minimum Difficulty)")
        )
        self.difficulty_frame.winfo_children()[1].winfo_children()[0].config(
            text=translate("-sharespermin (Shares/Min Rate)")
        )
        self.difficulty_frame.winfo_children()[2].winfo_children()[0].config(
            text=translate("-vardiff (Enable Variable Difficulty)")
        )
        self.difficulty_frame.winfo_children()[3].winfo_children()[0].config(
            text=translate("-pow2clamp (Required for ASICs)")
        )

        self.logging_frame.config(text=f" {translate('Logging & Stats')} ")
        self.logging_frame.winfo_children()[0].winfo_children()[0].config(
            text=translate("-log (Enable Log File)")
        )
        self.logging_frame.winfo_children()[1].winfo_children()[0].config(
            text=translate("-stats (Show Stats in Console)")
        )
        self.logging_frame.winfo_children()[2].winfo_children()[0].config(
            text=translate("-vardiffstats (Show Vardiff Stats)")
        )

        self.advanced_frame.config(text=f" {translate('Advanced')} ")
        self.advanced_frame.winfo_children()[0].winfo_children()[0].config(
            text=translate("-blockwait (e.g., 3s, 2000ms)")
        )
        self.advanced_frame.winfo_children()[1].winfo_children()[0].config(
            text=translate("-prom (e.g., :2112)")
        )
        self.advanced_frame.winfo_children()[2].winfo_children()[0].config(
            text=translate("-extranonce (bytes)")
        )
        self.advanced_frame.winfo_children()[3].winfo_children()[0].config(
            text=translate("-hcp (Health Check Port)")
        )

        if hasattr(self, "custom_paths_frame"):
            self.custom_paths_frame.config(text=f" {translate('Custom Paths')} ")
            self.exe_cb.config(text=translate("Use Custom ks_bridge.exe"))
            self.config_cb.config(text=translate("Use Custom config.yaml"))
            self.url_cb.config(text=translate("Use Custom Download URL"))
            self.url_exe_path_label.config(
                text=translate("Enter the exact path of the .exe inside the zip:")
            )
            self.url_config_path_label.config(
                text=translate(
                    "Enter the exact path of the config.yaml inside the zip:"
                )
            )

        self.preview_lf.config(text=f" {translate('Command Preview')} ")
        self.copy_command_button.config(text=translate("Copy"))


class KaspaBridgeTab(ttk.Frame):
    """
    The main container tab that holds one or two BridgeInstanceTabs
    in a notebook. This is a pure View class.
    """

    main_window: "MainWindow"
    config_manager: "ConfigManager"
    bridge1_tab_instance: Optional[BridgeInstanceTab]
    bridge2_tab_instance: Optional[BridgeInstanceTab]
    first_activation_done: bool
    _initial_load_complete: bool
    enable_bridge_2_default: bool
    enable_bridge_2_var: ttk.BooleanVar

    notebook: ttk.Notebook
    bridge1_frame: ttk.Frame
    bridge2_frame: ttk.Frame

    def __init__(
        self,
        master: ttk.Frame,
        main_window: "MainWindow",
        config_manager: "ConfigManager",
        **kwargs: Any,
    ) -> None:
        """
        Initialize the main Kaspa Bridge Tab.
        """
        super().__init__(master, **kwargs)
        self.pack(fill=BOTH, expand=True, padx=0, pady=0)

        self.main_window = main_window
        self.config_manager = config_manager

        self.bridge1_tab_instance = None
        self.bridge2_tab_instance = None
        self.first_activation_done = False
        self._initial_load_complete = False

        self._load_main_settings()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=BOTH, expand=True, padx=10, pady=(0, 10))
        self.notebook.bind("<<NotebookTabChanged>>", self.on_bridge_sub_tab_changed)

        self.enable_bridge_2_var = ttk.BooleanVar(value=self.enable_bridge_2_default)
        self.enable_bridge_2_var.trace_add("write", self._save_main_settings)

        self.bridge1_frame = ttk.Frame(self.notebook, padding=0)
        self.bridge1_frame.grid_rowconfigure(0, weight=1)
        self.bridge1_frame.grid_columnconfigure(0, weight=1)

        self.bridge1_tab_instance = BridgeInstanceTab(
            self.bridge1_frame,
            main_window,
            config_manager,
            instance_id="_1",
            main_bridge_tab=self,
        )
        self.bridge1_tab_instance.grid(row=0, column=0, sticky=NSEW)
        self.notebook.add(self.bridge1_frame, text=f" {translate('Bridge 1')} ")

        self.bridge2_frame = ttk.Frame(self.notebook, padding=0)
        self.bridge2_frame.grid_rowconfigure(0, weight=1)
        self.bridge2_frame.grid_columnconfigure(0, weight=1)

        self._toggle_bridge_2(initial_load=True)

    def _load_main_settings(self) -> None:
        """Load main settings for this tab (e.g., if Bridge 2 is enabled)."""
        bridge_config: Dict[str, Any] = self.config_manager.get_config().get(
            "kaspa_bridge", {}
        )
        self.enable_bridge_2_default = bridge_config.get("enable_bridge_2", False)

    def _save_main_settings(self, *args: Any) -> None:
        """Save main settings for this tab."""
        bridge_config: Dict[str, Any] = self.config_manager.get_config().get(
            "kaspa_bridge", {}
        )
        bridge_config["enable_bridge_2"] = self.enable_bridge_2_var.get()
        self.config_manager.get_config()["kaspa_bridge"] = bridge_config
        self.config_manager.save_config(self.config_manager.get_config())

        if not self._initial_load_complete:
            return
        self._toggle_bridge_2()

    def _toggle_bridge_2(self, *args: Any, initial_load: bool = False) -> None:
        """Show or hide the Bridge 2 tab based on the checkbox."""
        if initial_load:
            self._initial_load_complete = True

        if self.enable_bridge_2_var.get():
            if self.bridge2_tab_instance is None:
                self.bridge2_tab_instance = BridgeInstanceTab(
                    self.bridge2_frame,
                    self.main_window,
                    self.config_manager,
                    instance_id="_2",
                    main_bridge_tab=self,
                )
                self.bridge2_tab_instance.grid(row=0, column=0, sticky=NSEW)
            try:
                self.notebook.add(self.bridge2_frame, text=f" {translate('Bridge 2')} ")
            except tk.TclError:
                pass
        else:
            if self.bridge2_tab_instance is not None:
                if (
                    self.bridge2_tab_instance.controller.bridge_process
                    and self.bridge2_tab_instance.controller.bridge_process.poll()
                    is None
                ):
                    if not initial_load:
                        messagebox.showwarning(
                            translate("Bridge is running"),
                            translate("Please stop Bridge 2 before disabling it."),
                        )
                        self.enable_bridge_2_var.set(True)
                    return

                try:
                    self.notebook.forget(self.bridge2_frame)
                except tk.TclError:
                    pass
                self.bridge2_tab_instance.destroy()
                self.bridge2_tab_instance = None

    def _activate_current_sub_tab(self) -> None:
        """Activates the controller of the currently selected sub-tab."""
        try:
            selected_tab_widget: tk.Widget = self.notebook.nametowidget(
                self.notebook.select()
            )
            if selected_tab_widget == self.bridge1_frame:
                if self.bridge1_tab_instance:
                    self.bridge1_tab_instance.controller.activate_tab()
            elif selected_tab_widget == self.bridge2_frame:
                if self.bridge2_tab_instance:
                    self.bridge2_tab_instance.controller.activate_tab()
        except Exception as e:
            logger.warning(f"Error handling bridge sub-tab change: {e}")

    def on_bridge_sub_tab_changed(self, event: Any) -> None:
        """
        When the user switches between Bridge 1 and Bridge 2 tabs,
        call the activate_tab method of the newly selected tab's controller.
        """
        if not self.first_activation_done:
            return
        self._activate_current_sub_tab()

    def on_close(self) -> None:
        """Propagate the on_close event to child bridge controllers."""
        if self.bridge1_tab_instance:
            self.bridge1_tab_instance.controller.on_close()
        if self.bridge2_tab_instance:
            self.bridge2_tab_instance.controller.on_close()

    def autostart_bridges(self, is_autostart: bool = False) -> None:
        """Trigger autostart for child bridge controllers."""
        if self.bridge1_tab_instance:
            self.bridge1_tab_instance.controller.autostart_if_enabled(is_autostart)
        if self.bridge2_tab_instance and self.enable_bridge_2_var.get():
            self.bridge2_tab_instance.controller.autostart_if_enabled(is_autostart)

    def re_translate(self) -> None:
        """Propagate the re_translate event to child bridge controllers."""
        self.notebook.tab(0, text=f" {translate('Bridge 1')} ")

        if self.bridge1_tab_instance:
            self.bridge1_tab_instance.controller.re_translate()
        if self.bridge2_tab_instance:
            self.notebook.tab(1, text=f" {translate('Bridge 2')} ")
            self.bridge2_tab_instance.controller.re_translate()

    def set_controls_state(self, active: bool) -> None:
        """Propagate the set_controls_state event to child bridge controllers."""
        try:
            if self.bridge1_tab_instance:
                self.bridge1_tab_instance.controller.set_controls_state(active)
                if hasattr(self.bridge1_tab_instance, "enable_bridge_2_cb"):
                    self.bridge1_tab_instance.enable_bridge_2_cb.config(
                        state=tk.NORMAL if active else DISABLED
                    )
            if self.bridge2_tab_instance:
                self.bridge2_tab_instance.controller.set_controls_state(active)
        except tk.TclError:
            pass

    def activate_tab(self) -> None:
        """
        Called when the main Kaspa Bridge tab is activated.
        Delegates activation to the currently selected sub-tab's controller.
        """
        if not self.first_activation_done:
            self.first_activation_done = True
            self.after(100, self._activate_current_sub_tab)
        else:
            self._activate_current_sub_tab()
