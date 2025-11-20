#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main window class for the KaspaGateway application.
Acts as the View layer and central orchestrator, delegating logic to helper classes.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import messagebox
from typing import Any, Dict, List, Optional, Tuple, cast

import pandas as pd
import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, DANGER, DISABLED, NORMAL, NSEW, X
from ttkbootstrap.toast import ToastNotification

from src.api.network import fetch_address_balance
from src.config.config import CONFIG, get_assets_path
from src.utils.profiling import log_performance
from src.utils.formatting import format_large_number
from src.utils.i18n import switch_language, translate
from src.utils.validation import _sanitize_for_logging, validate_kaspa_address

from src.gui.app_context import AppContext
from src.gui.background_services import BackgroundServices

from src.gui.components import Header, Status
from src.gui.tabs.explorer_tab import ExplorerTab
from src.gui.tabs.kaspa_bridge_tab import KaspaBridgeTab
from src.gui.tabs.kaspa_node_tab import KaspaNodeTab
from src.gui.tabs.log_tab import LogTab
from src.gui.tabs.normal_analysis_tab import NormalAnalysisTab
from src.gui.tabs.settings_tab import SettingsTab
from src.gui.tabs.top_addresses_tab import TopAddressesTab

logger = logging.getLogger(__name__)


class MainWindow(ttk.Window):
    """
    The main application window.
    Acts as the View layer and central orchestrator, delegating logic to helper classes.
    """

    def __init__(self) -> None:
        logger.info("Initializing MainWindow...")
        super().__init__(themename=CONFIG.get("theme", "superhero").lower())

        self._init_variables_and_version()

        self.app_context = AppContext(self)
        self.background_services = BackgroundServices(self)
        
        self._build_ui_structure()
        
        self.after(50, self.deferred_initialization)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _init_variables_and_version(self) -> None:
        """Initializes state variables and injects the git hash into the version."""
        default_font: Tuple[str, int] = ("DejaVu Sans", 10)
        self.style.configure(".", font=default_font)

        self._inject_git_hash_into_config()

        self.price_var = ttk.StringVar(value="...")
        self.hashrate_var = ttk.StringVar(value="...")
        self.difficulty_var = ttk.StringVar(value="...")
        self.clock_date_var = ttk.StringVar()
        self.clock_time_var = ttk.StringVar()
        self.currency_var = ttk.StringVar(value=CONFIG.get("selected_currency", "USD"))

        self.current_address: Optional[str] = None
        self.address_names_map: Dict[str, str] = {}
        self.address_names_loaded = threading.Event()
        self.cancel_event = threading.Event()
        self.previous_tab_index: int = 0
        self.is_exporting: bool = False
        self.app_initialized: bool = False
        self.all_tabs: Dict[str, ttk.Widget] = {}
        self.is_busy: bool = False

    def _inject_git_hash_into_config(self) -> None:
        """
        Updates CONFIG['version'] with the git hash so all UI components (like Header)
        display the full version automatically. Format: 1.0.0-abcdef1
        """
        base_ver: str = CONFIG.get("version", "1.0.0")
        commit: str = ""
        
        # Try to read injected version (For Frozen EXE/Production)
        try:
            from src.version_info import COMMIT_HASH
            commit = COMMIT_HASH
        except ImportError:
            pass

        # Fallback to Git command (For Dev Mode)
        if not commit:
            try:
                # Run git command to get short hash
                commit = subprocess.check_output(
                    ["git", "rev-parse", "--short", "HEAD"], 
                    stderr=subprocess.DEVNULL
                ).decode("ascii").strip()
            except Exception:
                pass
        
        if commit:
            # Append hash to version
            full_version = f"{base_ver}-{commit}"
            CONFIG["version"] = full_version
            self.title(f"KaspaGateway Version {full_version}")
        else:
            self.title(f"KaspaGateway Version {base_ver}")

    @log_performance
    def deferred_initialization(self) -> None:
        """Performs heavy initialization tasks after the UI is shown."""
        logger.info("Starting deferred initialization...")
        
        self.app_context.initialize_managers()
        self._connect_managers_to_ui()
        self._update_header_stats_from_cache()
        self._update_clock_loop()
        self.background_services.start_all()
        self._load_user_state()
        
        self.app_initialized = True
        logger.info("Application fully initialized.")

    def _build_ui_structure(self) -> None:
        """Sets up the main window geometry and basic layout containers."""
        self.geometry("1400x900")
        self.minsize(1200, 800)
        
        if os.path.exists(get_assets_path("kaspa-white.ico")):
            self.iconbitmap(get_assets_path("kaspa-white.ico"))

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header_placeholder = ttk.Frame(self, height=80)
        self.header_placeholder.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))

        self.tabview = ttk.Notebook(self, bootstyle="primary")
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)

        self.explorer_tab_frame = ttk.Frame(self.tabview)
        self.tabview.add(self.explorer_tab_frame, text=f" {translate('Explorer')} ")

        self._build_status_bar()

    def _connect_managers_to_ui(self) -> None:
        """Initializes and connects UI components with their respective managers."""
        self.header = Header(
            self, self.price_var, self.hashrate_var, self.difficulty_var,
            self.clock_date_var, self.clock_time_var, self.app_context.theme_manager,
            self._on_currency_dropdown_select, self.currency_var,
            self._on_language_change, self.app_context.config_manager
        )
        
        self.header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        self.header_placeholder.destroy()

        self._build_explorer_tab(self.explorer_tab_frame)
        
        self.analysis_tab_notebook = ttk.Notebook(self.tabview)
        analysis_frame = ttk.Frame(self.analysis_tab_notebook)
        self.normal_analysis_tab = NormalAnalysisTab(analysis_frame, self)
        self.analysis_tab_notebook.add(analysis_frame, text=translate("Standard Analysis"))

        top_addr_frame = ttk.Frame(self.tabview)
        log_frame = ttk.Frame(self.tabview)
        settings_frame = ttk.Frame(self.tabview)
        node_frame = ttk.Frame(self.tabview)
        bridge_frame = ttk.Frame(self.tabview)

        self.top_addresses_tab = TopAddressesTab(top_addr_frame, self)
        self.log_tab = LogTab(log_frame)
        self.settings_tab = SettingsTab(settings_frame, self)
        self.kaspa_node_tab = KaspaNodeTab(node_frame, self, config_manager=self.app_context.config_manager)
        self.kaspa_bridge_tab = KaspaBridgeTab(bridge_frame, self, config_manager=self.app_context.config_manager)

        self.all_tabs = {
            "Explorer": self.explorer_tab_frame,
            "Analysis": self.analysis_tab_notebook,
            "Top Addresses": top_addr_frame,
            "Log": log_frame,
            "Kaspa Node": node_frame,
            "Kaspa Bridge": bridge_frame,
            "Settings": settings_frame,
        }
        
        self._rebuild_tabs()
        self.tabview.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.app_context.price_updater.update_callback = self._on_price_update
        self.app_context.network_updater.update_callback = self._on_network_update

        self._update_ui_for_address_validity(
            validate_kaspa_address(self.explorer_tab.input_component.address_combo.get().strip())
        )

    def on_closing(self) -> None:
        """Handles the window close event."""
        if self.is_busy:
            messagebox.showwarning(translate("Busy"), translate("Please wait for the current fetch or export to complete before closing."))
            return

        if messagebox.askokcancel(translate("Quit"), translate("Are you sure you want to exit?")):
            try:
                self._save_user_state()
            except Exception:
                pass
            self.shutdown_services()
            self.destroy()

    def shutdown_services(self) -> None:
        """Cleanly shuts down all background services and database connections."""
        self.background_services.shutdown()
        if self.app_context.transaction_manager:
            self.app_context.transaction_manager.stop_fetch()
        
        self.app_context.close_all_db_connections()
        from src.database.db_locker import release_all_locks
        release_all_locks()
        logger.info("Application shutdown complete.")
    
    def reinitialize_databases(self) -> None:
        self.app_context.reinitialize_databases()

    def close_all_db_connections(self) -> None:
        self.app_context.close_all_db_connections()

    def _update_clock_loop(self) -> None:
        try:
            if not self.winfo_exists(): return
            self.clock_date_var.set(time.strftime("%Y-%m-%d"))
            self.clock_time_var.set(time.strftime("%H:%M:%S"))
            self.after(1000, self._update_clock_loop)
        except Exception: pass

    def _update_header_stats_from_cache(self) -> None:
        try:
            if prices := self.app_context.app_data_db.get_cached_prices(expired=True):
                self._update_price_display(prices)
            if stats := self.app_context.app_data_db.get_cached_network_data(expired=True):
                self._update_network_display(stats[0], stats[1])
        except Exception: pass

    def _update_price_display(self, prices: Dict[str, float]) -> None:
        code = self.currency_var.get().lower()
        price = prices.get(code, 0.0)
        self.price_var.set(f"{price:,.4f} {code.upper()}" if price > 0 else "N/A")

    def _update_network_display(self, hashrate: Optional[float], difficulty: Optional[float]) -> None:
        if hashrate: self.hashrate_var.set(f"{hashrate:.2f} PH/s")
        if difficulty: self.difficulty_var.set(f"{format_large_number(difficulty, precision=2)}")

    def _on_price_update(self, prices: Dict[str, float]) -> None:
        if self.winfo_exists():
            self.after(0, self._update_price_display, prices)
            self.after(0, self.header.update_price_tooltip, self.app_context.price_updater.get_last_updated_ts())

    def _on_network_update(self, hashrate: Optional[float], difficulty: Optional[float]) -> None:
        if self.winfo_exists():
            self.after(0, self._update_network_display, hashrate, difficulty)
            self.after(0, self.header.update_network_tooltip, self.app_context.network_updater.get_last_updated_ts())

    def update_address_balance(self, address: str) -> None:
        if hasattr(self, "explorer_tab"):
            self.explorer_tab.input_component.update_balance_display(None, None)
        threading.Thread(target=self._balance_worker, args=(address,), daemon=True).start()

    def _balance_worker(self, address: str) -> None:
        balance = fetch_address_balance(address)
        name = self.address_names_map.get(address)
        if self.current_address == address and self.winfo_exists() and hasattr(self, "explorer_tab"):
            self.after(0, self.explorer_tab.input_component.update_balance_display, balance, name)

    def on_settings_saved(self) -> None:
        logger.info("Settings saved. Refreshing UI and Services.")
        
        config = self.app_context.config_manager.get_config()
        auto_refresh = config.get("performance", {}).get("auto_refresh_enabled", False)

        if auto_refresh:
            logger.info("Auto-refresh enabled. Starting services.")
            self.app_context.price_updater.start()
            self.app_context.network_updater.start()
        else:
            logger.info("Auto-refresh disabled. Stopping services.")
            self.app_context.price_updater.stop()
            self.app_context.network_updater.stop()

        switch_language(CONFIG["language"])
        self.re_translate_ui()

    def _on_currency_dropdown_select(self, new_currency: str) -> None:
        config = self.app_context.config_manager.get_config()
        config["selected_currency"] = new_currency
        self.app_context.config_manager.save_config(config)
        self.currency_var.set(new_currency)
        self._update_price_display(self.app_context.price_updater.get_current_prices())
        
        if hasattr(self, "explorer_tab"):
            self.explorer_tab.results_component.update_currency_display(new_currency)
        if self.current_address:
            self.update_address_balance(self.current_address)
        if hasattr(self, "top_addresses_tab") and self.top_addresses_tab.is_active:
            self.top_addresses_tab.update_currency_display(new_currency)
        if hasattr(self, "normal_analysis_tab"):
            self.normal_analysis_tab.on_currency_change()

    def _on_language_change(self, lang_code: str) -> None:
        if switch_language(lang_code):
            config = self.app_context.config_manager.get_config()
            config["language"] = lang_code
            self.app_context.config_manager.save_config(config)
            self.re_translate_ui()

    def re_translate_ui(self) -> None:
        if "version" in CONFIG:
             self.title(f"KaspaGateway Version {CONFIG['version']}")
             
        self._rebuild_tabs()
        
        try: self.analysis_tab_notebook.tab(0, text=translate("Standard Analysis"))
        except: pass

        components = [
            self.header, self.explorer_tab, self.status, self.settings_tab,
            self.top_addresses_tab, self.log_tab, self.normal_analysis_tab,
            self.kaspa_node_tab, self.kaspa_bridge_tab
        ]
        for comp in components:
            if comp and hasattr(comp, "re_translate"):
                comp.re_translate()

    def _rebuild_tabs(self) -> None:
        selected = None
        try:
            if path := self.tabview.select(): selected = self.tabview.nametowidget(path)
        except: pass

        for tab in self.tabview.tabs(): self.tabview.forget(tab)

        tab_order = ["Explorer", "Kaspa Node", "Kaspa Bridge", "Analysis", "Top Addresses", "Log", "Settings"]
        visible = CONFIG.get("display", {}).get("displayed_tabs", [])

        for key in tab_order:
            if key in self.all_tabs:
                if key == "Settings" or key in visible:
                    self.tabview.add(self.all_tabs[key], text=f" {translate(key)} ")

        if selected:
            try:
                for i, tab_id in enumerate(self.tabview.tabs()):
                    if self.tabview.nametowidget(tab_id) == selected:
                        self.tabview.select(i)
                        break
            except: self.tabview.select(0)
        else:
            self.tabview.select(0)

    def _on_tab_changed(self, event: Any) -> None:
        if not self.app_initialized or not self.tabview.tabs(): return
        
        try:
            prev_text = self.tabview.tab(self.previous_tab_index, "text").strip()
            if prev_text == translate("Top Addresses"):
                self.top_addresses_tab.deactivate()
        except: pass

        try:
            sel_idx = self.tabview.index(self.tabview.select())
            sel_text = self.tabview.tab(sel_idx, "text").strip()
            self.previous_tab_index = sel_idx

            if sel_text == translate("Top Addresses"): self.top_addresses_tab.activate()
            elif sel_text == translate("Kaspa Node"): self.kaspa_node_tab.controller.activate_tab()
            elif sel_text == translate("Kaspa Bridge"): self.kaspa_bridge_tab.activate_tab()
            elif sel_text == translate("Settings"): self.settings_tab._on_outer_tab_changed(event)
            elif sel_text == translate("Analysis"):
                if hasattr(self, "normal_analysis_tab"): self.normal_analysis_tab.refresh_headers()

        except Exception as e:
            logger.error(f"Tab change error: {e}")

    def _build_explorer_tab(self, tab: ttk.Frame) -> None:
        self.explorer_tab = ExplorerTab(tab, self)
        self.explorer_tab.pack(fill=BOTH, expand=True, padx=5, pady=5)

    def _build_status_bar(self) -> None:
        f = ttk.Frame(self)
        f.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 5))
        f.grid_columnconfigure(0, weight=1)
        self.status = Status(f)
        self.status.grid(row=0, column=0, sticky="ew")
        
        self.cancel_button = ttk.Button(
            f, 
            text=translate("Cancel"), 
            command=self.cancel_operation,
            bootstyle="danger-outline",
            state="normal"
        )
        self.cancel_button.grid(row=0, column=1, sticky="e", padx=5)
        self.cancel_button.grid_remove()

        self.progress_bar = ttk.Progressbar(self, mode="indeterminate", bootstyle="success-striped")
        self.progress_bar.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 5))
        self.progress_bar.grid_remove()

    def _set_ui_for_processing(self, is_processing: bool) -> None:
        self.set_busy_state(is_processing)
        
        if is_processing:
            self.progress_bar.grid()
            self.progress_bar.start()
        else:
            self.progress_bar.stop()
            self.progress_bar.grid_remove()

    def set_busy_state(self, is_busy: bool) -> None:
        """
        Locks the UI during heavy operations while keeping the Log tab accessible.
        Prevents tab switching away from the current context.
        """
        self.is_busy = is_busy
        state = "disabled" if is_busy else "normal"
        
        current_tab_id = self.tabview.select()

        for tab_id in self.tabview.tabs():
            try:
                tab_text = self.tabview.tab(tab_id, "text")
                
                # Keep Log tab and Current Tab enabled
                is_log = "Log" in tab_text or "سجل" in tab_text
                is_current = (tab_id == current_tab_id)

                if is_current or is_log:
                     self.tabview.tab(tab_id, state="normal")
                else:
                     self.tabview.tab(tab_id, state=state)
                     
            except Exception as e:
                logger.error(f"Error updating tab state: {e}")

        if hasattr(self, "header"):
             self.header.set_controls_state(not is_busy)

        if is_busy:
            self.cancel_button.grid()
        else:
            self.cancel_button.grid_remove()
            
        if current_tab_id:
            try:
                widget = self.tabview.nametowidget(current_tab_id)
                for child in widget.winfo_children():
                    if hasattr(child, "set_controls_state"):
                         child.set_controls_state(not is_busy)
            except Exception:
                pass

        self.update_idletasks()

    def cancel_operation(self) -> None:
        if self.is_busy:
            logger.info("Cancel requested by user.")
            self.cancel_event.set()
            self.status.update_status(translate("Cancelling..."))

    def _update_ui_for_address_validity(self, is_valid: bool) -> None:
        if not hasattr(self, "explorer_tab"): return
        is_fetching = self.app_context.transaction_manager.is_fetching
        state = NORMAL if not is_fetching and is_valid else DISABLED
      
        self.explorer_tab.input_component.fetch_button.config(state=state)
        self.explorer_tab.input_component.force_fetch_button.config(state=state)
        self.explorer_tab.input_component.explorer_btn.config(state=NORMAL if is_valid else DISABLED)
        
        self.explorer_tab.explorer_filter_controls.set_input_state(is_valid and not is_fetching)
        self.explorer_tab.explorer_filter_controls.set_action_buttons_state(is_valid and not is_fetching)

    def _load_user_state(self) -> None:
        try:
            last_addr = self.app_context.app_data_db.get_user_state("last_address")
            if last_addr and validate_kaspa_address(last_addr):
                self.explorer_tab.input_component.address_combo.set(last_addr)
                self.explorer_tab.input_component._on_address_entry_change()
            
            last_filters = self.app_context.app_data_db.get_user_state("last_filters")
            if last_filters:
                filters = json.loads(last_filters)
                fc = self.explorer_tab.explorer_filter_controls
                if "start_date" in filters and filters["start_date"]:
                    fc.start_date_label.config(text=datetime.fromisoformat(filters["start_date"]).strftime("%Y-%m-%d"))
                if "end_date" in filters and filters["end_date"]:
                    fc.end_date_label.config(text=datetime.fromisoformat(filters["end_date"]).strftime("%Y-%m-%d"))
                fc.type_combo.set(filters.get("type_filter", "ALL"))
                fc.direction_combo.set(filters.get("direction_filter", "ALL"))
                
        except Exception as e:
            logger.warning(f"State load error: {e}")

    def _save_user_state(self) -> None:
        try:
            addr = self.explorer_tab.input_component.address_combo.get().strip()
            if validate_kaspa_address(addr):
                self.app_context.app_data_db.save_user_state("last_address", addr)
            
            filters = self.explorer_tab.explorer_filter_controls.get_filters()
            serializable = {
                "start_date": filters["start_date"].isoformat() if filters.get("start_date") else None,
                "end_date": filters["end_date"].isoformat() if filters.get("end_date") else None,
                "type_filter": filters.get("type_filter"),
                "direction_filter": filters.get("direction_filter"),
                "search_query": filters.get("search_query")
            }
            self.app_context.app_data_db.save_user_state("last_filters", json.dumps(serializable))
        except Exception: pass

    def reset_explorer_tab_state(self) -> None:
        self.current_address = None
        self.explorer_tab.input_component.address_combo.set("")
        self.explorer_tab.input_component.refresh_address_dropdown()
        self.explorer_tab.results_component.show_placeholder(translate("Load an address to see transactions."))
        self.normal_analysis_tab.update_data(None)

    def start_ui_update_loop(self, q: queue.Queue) -> None:
        self.explorer_tab.results_component.start_ui_update_loop(q)

    def stop_ui_update_loop(self, q: queue.Queue) -> None:
        self.explorer_tab.results_component.stop_ui_update_loop(q)

    def set_new_transaction_dataset(self, df: pd.DataFrame) -> None:
        self.explorer_tab.set_new_transaction_dataset(df)

    def finalize_ui_load(self, success: bool, msg: str, time: float) -> None:
        final_msg = f"{translate(msg)} ({time:.2f}s)"
        self.status.update_status(final_msg)
        self._set_ui_for_processing(False)
        if success and self.current_address:
            self.normal_analysis_tab.update_data(self.current_address)
            self.after(5000, lambda: self.status.update_status("Ready"))

    def prompt_to_open_file(self, path: str, msg: str) -> None:
        if messagebox.askyesno(translate("Export Successful"), f"{msg}\n\n{translate('Open exported file?')}"):
            try: webbrowser.open(os.path.abspath(path))
            except Exception as e: messagebox.showerror("Error", str(e))

    def clipboard_append(self, text: str) -> None:
        self.clipboard_clear()
        super().clipboard_append(text)
        
    def get_cancel_flag(self) -> threading.Event:
        return self.cancel_event

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()