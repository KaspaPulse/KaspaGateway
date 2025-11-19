#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main window class for the KaspaGateway application.
Handles the main GUI structure, manager initialization, and global state.
"""

from __future__ import annotations

import json
import logging
import os
import queue
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

from src.api.network import (
    fetch_address_balance,
    fetch_address_names,
    fetch_latest_release_info,
)
from src.config.config import CONFIG, get_assets_path
from src.utils.profiling import log_performance

logger = logging.getLogger(__name__)

# Performance-timed Imports
t_start_imports = time.perf_counter()
logger.debug("PERF: Importing src.database...")
from src.database import (
    AddressDB,
    AppDataDB,
    TransactionDB,
    initialize_addr_schema,
    initialize_app_data_schema,
    initialize_tx_schema,
)
from src.database.db_locker import release_all_locks as release_db_locks
from src.database.db_manager import DatabaseManager

logger.info(f"PERF: src.database imported in {time.perf_counter() - t_start_imports:.4f}s")

t_start_imports = time.perf_counter()
logger.debug("PERF: Importing GUI components...")
from src.gui.address_manager import AddressManager
from src.gui.components import Header, Status
from src.gui.config_manager import ConfigManager
from src.gui.network_updater import NetworkUpdater
from src.gui.price_updater import PriceUpdater
from src.gui.tabs.explorer_tab import ExplorerTab
from src.gui.tabs.kaspa_bridge_tab import KaspaBridgeTab
from src.gui.tabs.kaspa_node_tab import KaspaNodeTab
from src.gui.tabs.log_tab import LogTab
from src.gui.tabs.normal_analysis_tab import NormalAnalysisTab
from src.gui.tabs.settings_tab import SettingsTab
from src.gui.tabs.top_addresses_tab import TopAddressesTab
from src.gui.theme_manager import ThemeManager
from src.gui.transaction_manager import TransactionManager
from src.utils.formatting import format_large_number
from src.utils.i18n import switch_language, translate
from src.utils.validation import _sanitize_for_logging, validate_kaspa_address

logger.info(f"PERF: GUI components imported in {time.perf_counter() - t_start_imports:.4f}s")


class MainWindow(ttk.Window):
    """
    The main application window.
    """

    price_var: ttk.StringVar
    hashrate_var: ttk.StringVar
    difficulty_var: ttk.StringVar
    clock_date_var: ttk.StringVar
    clock_time_var: ttk.StringVar
    currency_var: ttk.StringVar

    current_address: Optional[str]
    address_names_map: Dict[str, str]
    address_names_loaded: threading.Event
    cancel_event: threading.Event
    ui_update_job: Optional[str]
    previous_tab_index: int
    is_exporting: bool
    app_initialized: bool

    tx_db: TransactionDB
    addr_db: AddressDB
    app_data_db: AppDataDB
    db_manager: DatabaseManager

    config_manager: ConfigManager
    theme_manager: ThemeManager
    address_manager: AddressManager
    transaction_manager: TransactionManager
    price_updater: PriceUpdater
    network_updater: NetworkUpdater

    header: Header
    tabview: ttk.Notebook
    explorer_tab_frame: ttk.Frame
    status: Status
    progress_bar: ttk.Progressbar
    header_placeholder: ttk.Frame

    explorer_tab: ExplorerTab
    analysis_tab_notebook: ttk.Notebook
    normal_analysis_tab: NormalAnalysisTab
    top_addresses_tab: TopAddressesTab
    log_tab: LogTab
    settings_tab: SettingsTab
    kaspa_node_tab: KaspaNodeTab
    kaspa_bridge_tab: KaspaBridgeTab
    all_tabs: Dict[str, ttk.Widget]

    def __init__(self) -> None:
        logger.info("Initializing MainWindow...")
        super().__init__(themename=CONFIG.get("theme", "superhero").lower())

        default_font: Tuple[str, int] = ("DejaVu Sans", 10)
        self.style.configure(".", font=default_font)

        self.price_var = ttk.StringVar(value="...")
        self.hashrate_var = ttk.StringVar(value="...")
        self.difficulty_var = ttk.StringVar(value="...")

        self.clock_date_var = ttk.StringVar()
        self.clock_time_var = ttk.StringVar()
        self.currency_var = ttk.StringVar(value=CONFIG.get("selected_currency", "USD"))

        self.current_address = None
        self.address_names_map = {}
        self.address_names_loaded = threading.Event()
        self.cancel_event = threading.Event()
        self.ui_update_job = None
        self.previous_tab_index = 0
        self.is_exporting = False
        self.app_initialized = False

        self._build_ui_structure()
        self.after(50, self.deferred_initialization)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        logger.info("MainWindow basic UI structure initialized, deferring heavy tasks.")

    @log_performance
    def deferred_initialization(self) -> None:
        logger.info("Starting deferred initialization of managers and background services.")
        t_start_deferred = time.perf_counter()

        self._initialize_managers()
        self._connect_managers_to_ui()

        self._update_header_stats_from_cache()
        self._update_clock_loop()
        self.start_background_services()

        self._load_user_state()
        self._check_and_run_autostart_services()

        self._auto_refresh_loop()

        self._start_update_check()

        t_end_deferred = time.perf_counter()
        logger.info(f"PERF: Deferred initialization complete in {t_end_deferred - t_start_deferred:.4f} seconds.")

        self.app_initialized = True

    def _build_ui_structure(self) -> None:
        logger.debug("Building main UI structure...")
        self.title(translate("KaspaGateway"))
        self.geometry("1400x900")
        self.minsize(1200, 800)
        try:
            icon_path: str = get_assets_path("kaspa-white.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            logger.warning("Application icon not found or could not be loaded.", exc_info=False)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header_placeholder = ttk.Frame(self, height=80)
        self.header_placeholder.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))

        self.tabview = ttk.Notebook(self, bootstyle="primary")
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)

        self.explorer_tab_frame = ttk.Frame(self.tabview)
        self.tabview.add(self.explorer_tab_frame, text=f" {translate('Explorer')} ")

        self._build_status_bar()
        logger.debug("Main UI structure built.")

    def _initialize_managers(self) -> None:
        logger.info("Initializing core managers and database connections...")
        db_filenames: Dict[str, str] = CONFIG["db_filenames"]
        db_path: str = CONFIG["paths"]["database"]

        self.tx_db = TransactionDB(
            os.path.join(db_path, db_filenames["transactions"]), initialize_tx_schema
        )
        self.addr_db = AddressDB(
            os.path.join(db_path, db_filenames["addresses"]), initialize_addr_schema
        )
        self.app_data_db = AppDataDB(
            os.path.join(db_path, db_filenames["app_data"]), initialize_app_data_schema
        )
        self.addr_db.migrate_schema()

        self.db_manager = DatabaseManager()
        self.config_manager = ConfigManager()

        self.theme_manager = ThemeManager(self, self.config_manager)
        self.address_manager = AddressManager(self.addr_db)

        self.transaction_manager = TransactionManager(self, self.tx_db, self.cancel_event)
        self.price_updater = PriceUpdater(self, self.app_data_db)
        self.network_updater = NetworkUpdater(self, self.app_data_db)
        logger.info("All managers initialized.")

    def close_all_db_connections(self) -> None:
        logger.warning("Closing all database connections...")
        try:
            db_objects: List[Any] = [
                getattr(self, "tx_db", None),
                getattr(self, "addr_db", None),
                getattr(self, "app_data_db", None),
            ]

            for db_obj in db_objects:
                if db_obj and hasattr(db_obj, "close"):
                    db_obj.close()
                else:
                    logger.warning(f"Could not find .close() method on {type(db_obj)}")

        except Exception as e:
            logger.error(f"Error while closing DB connections: {_sanitize_for_logging(e)}", exc_info=True)
        logger.info("All database connections closed.")

    def reinitialize_databases(self) -> None:
        logger.info("Re-initializing database connections after deletion/restore...")
        db_filenames: Dict[str, str] = CONFIG["db_filenames"]
        db_path: str = CONFIG["paths"]["database"]

        self.tx_db = TransactionDB(
            os.path.join(db_path, db_filenames["transactions"]), initialize_tx_schema
        )
        self.addr_db = AddressDB(
            os.path.join(db_path, db_filenames["addresses"]), initialize_addr_schema
        )
        self.app_data_db = AppDataDB(
            os.path.join(db_path, db_filenames["app_data"]), initialize_app_data_schema
        )

        self.address_manager.db = self.addr_db
        self.transaction_manager.tx_db = self.tx_db
        self.price_updater.db = self.app_data_db
        self.network_updater.db = self.app_data_db

        if hasattr(self, "settings_tab") and self.settings_tab.db_tab:
            self.settings_tab.db_tab.db_manager = self.db_manager
            self.settings_tab.db_tab.main_window = self

        logger.info("Database connections and dependent managers re-initialized.")

    def _connect_managers_to_ui(self) -> None:
        logger.debug("Connecting managers to UI components...")

        self.header = Header(
            self,
            self.price_var,
            self.hashrate_var,
            self.difficulty_var,
            self.clock_date_var,
            self.clock_time_var,
            self.theme_manager,
            self._on_currency_dropdown_select,
            self.currency_var,
            self._on_language_change,
            self.config_manager,
        )
        self.header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        self.header_placeholder.destroy()

        self._build_explorer_tab(self.explorer_tab_frame)

        self.analysis_tab_notebook = ttk.Notebook(self.tabview)
        analysis_container_frame = ttk.Frame(self.analysis_tab_notebook)
        self.normal_analysis_tab = NormalAnalysisTab(analysis_container_frame, self)
        self.analysis_tab_notebook.add(
            analysis_container_frame, text=translate("Standard Analysis")
        )

        top_addresses_frame = ttk.Frame(self.tabview)
        log_frame = ttk.Frame(self.tabview)
        settings_frame = ttk.Frame(self.tabview)
        kaspa_node_frame = ttk.Frame(self.tabview)
        kaspa_bridge_frame = ttk.Frame(self.tabview)

        self.top_addresses_tab = TopAddressesTab(top_addresses_frame, self)
        self.log_tab = LogTab(log_frame)
        self.settings_tab = SettingsTab(settings_frame, self)
        self.kaspa_node_tab = KaspaNodeTab(
            kaspa_node_frame, self, config_manager=self.config_manager
        )
        self.kaspa_bridge_tab = KaspaBridgeTab(
            kaspa_bridge_frame, self, config_manager=self.config_manager
        )

        self.all_tabs = {
            "Explorer": self.explorer_tab_frame,
            "Analysis": self.analysis_tab_notebook,
            "Top Addresses": top_addresses_frame,
            "Log": log_frame,
            "Kaspa Node": kaspa_node_frame,
            "Kaspa Bridge": kaspa_bridge_frame,
            "Settings": settings_frame,
        }
        self._rebuild_tabs()
        self.tabview.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.price_updater.update_callback = self._on_price_update
        self.network_updater.update_callback = self._on_network_update

        self._update_ui_for_address_validity(
            validate_kaspa_address(
                self.explorer_tab.input_component.address_combo.get().strip()
            )
        )
        logger.debug("Managers connected to UI.")

    def on_closing(self) -> None:
        """Handle the window close event."""
        is_fetching: bool = (
            hasattr(self, "transaction_manager")
            and self.transaction_manager.is_fetching
        )
        is_exporting: bool = hasattr(self, "is_exporting") and self.is_exporting

        if is_fetching or is_exporting:
            messagebox.showwarning(
                translate("Busy"),
                translate(
                    "Please wait for the current fetch or export to complete before closing."
                ),
            )
            return

        if messagebox.askokcancel(
            translate("Quit"), translate("Are you sure you want to exit?")
        ):
            try:
                if hasattr(self, "app_data_db"):
                    self._save_user_state()
            except Exception as e:
                logger.error(
                    f"Failed to save user state or close nodes on closing: {_sanitize_for_logging(e)}"
                )
            logger.info(
                "Shutdown confirmed by user. Destroying main window to trigger clean exit."
            )
            self.destroy()

    def shutdown_services(self) -> None:
        """Shut down all application services and threads gracefully."""
        logger.info("Shutting down all application services...")

        self.shutdown_background_services()
        if hasattr(self, "transaction_manager"):
            self.transaction_manager.stop_fetch()

        self.close_all_db_connections()
        release_db_locks()

        threads_to_join: List[Optional[threading.Thread]] = []
        
        # Safe access to transaction manager thread
        if hasattr(self, "transaction_manager") and hasattr(self.transaction_manager, "get_thread"):
            threads_to_join.append(self.transaction_manager.get_thread())

        if hasattr(self, "price_updater"):
            threads_to_join.append(self.price_updater.get_thread())
            
        if hasattr(self, "network_updater"):
            threads_to_join.append(self.network_updater.get_thread())

        for thread in threads_to_join:
            if thread and thread.is_alive():
                logger.debug(f"Waiting for thread {thread.name} to join...")
                thread.join(timeout=2)

        logger.info("All services shut down gracefully.")

    def shutdown_background_services(self) -> None:
        """Stop all background update loops and external processes."""
        logger.info("Shutting down background services (Price/Network updaters).")

        if hasattr(self, "price_updater"):
            self.price_updater.stop()
        if hasattr(self, "network_updater"):
            self.network_updater.stop()
        if hasattr(self, "top_addresses_tab"):
            self.top_addresses_tab.deactivate()

        if hasattr(self, "kaspa_node_tab"):
            self.kaspa_node_tab.on_close()

        if hasattr(self, "kaspa_bridge_tab"):
            self.kaspa_bridge_tab.on_close()

        logger.info("Background services confirmed shut down.")

    # ... [Rest of the class methods omitted for brevity, assume unchanged] ...
    # (Include all other methods from the original file below this line to maintain file integrity)
    # For the purpose of this fix, only shutdown_services needed patching.
    # However, to ensure a complete file overwrite, I will include the rest of standard methods.

    def start_background_services(self) -> None:
        logger.info("Starting sequential background service initialization...")
        self._start_address_name_fetch()

    def _continue_startup_after_names(self) -> None:
        logger.info("Address names loaded. Continuing with price fetch.")
        self.price_updater.initial_fetch()
        self.after(100, self._check_and_start_network_fetch)

    def _check_and_start_network_fetch(self) -> None:
        if self.price_updater.initial_fetch_complete.is_set():
            logger.info("Price fetch complete. Continuing with network stats fetch.")
            self.network_updater.initial_fetch()
            self.after(100, self._finalize_background_startup)
        else:
            self.after(100, self._check_and_start_network_fetch)

    def _finalize_background_startup(self) -> None:
        if self.network_updater.initial_fetch_complete.is_set():
            logger.info("Initial data fetches are complete. Starting periodic updates.")
            self.price_updater.start()
            self.network_updater.start()
        else:
            self.after(100, self._finalize_background_startup)

    def _rebuild_tabs(self) -> None:
        logger.debug("Rebuilding notebook tabs based on current config.")
        selected_widget: Optional[ttk.Widget] = None
        re_selected: bool = False
        try:
            if selected_widget_path := self.tabview.select():
                selected_widget = self.tabview.nametowidget(selected_widget_path)
        except Exception:
            selected_widget = None

        for tab in self.tabview.tabs():
            self.tabview.forget(tab)

        tab_order: List[str] = [
            "Explorer",
            "Kaspa Node",
            "Kaspa Bridge",
            "Analysis",
            "Top Addresses",
            "Log",
            "Settings",
        ]
        visible_tabs: List[str] = CONFIG.get("display", {}).get("displayed_tabs", [])

        for tab_key in tab_order:
            if tab_key in self.all_tabs:
                if tab_key == "Settings" or tab_key in visible_tabs:
                    self.tabview.add(
                        self.all_tabs[tab_key], text=f" {translate(tab_key)} "
                    )

        if selected_widget:
            try:
                for i, tab_id in enumerate(self.tabview.tabs()):
                    if self.tabview.nametowidget(tab_id) == selected_widget:
                        self.tabview.select(i)
                        re_selected = True
                        break
            except Exception as e:
                logger.warning(
                    f"Could not re-select tab after language/settings change: {_sanitize_for_logging(e)}"
                )

        if not re_selected and self.tabview.tabs():
            self.tabview.select(0)

    def _on_tab_changed(self, event: Any) -> None:
        if not self.app_initialized or not self.winfo_exists():
            return
        if not self.tabview.tabs():
            return
        previous_tab_text: str = "Explorer"
        try:
            total_tabs = self.tabview.index("end")
            if 0 <= self.previous_tab_index < total_tabs:
                previous_tab_text = self.tabview.tab(
                    self.previous_tab_index, "text"
                ).strip()
        except (tk.TclError, RuntimeError):
            pass

        if previous_tab_text == translate("Top Addresses"):
            try:
                self.top_addresses_tab.deactivate()
            except AttributeError:
                pass

        try:
            selected_tab_id = self.tabview.select()
            if not selected_tab_id:
                return

            selected_tab_index: int = self.tabview.index(selected_tab_id)
            selected_tab_text: str = self.tabview.tab(
                selected_tab_index, "text"
            ).strip()

            logger.info(
                f"Switched from '{_sanitize_for_logging(previous_tab_text)}' to tab: '{_sanitize_for_logging(selected_tab_text)}' (index: {selected_tab_index})"
            )

            self.previous_tab_index = selected_tab_index

            if selected_tab_text == translate("Top Addresses"):
                if hasattr(self, "top_addresses_tab"):
                    self.top_addresses_tab.activate()
            elif selected_tab_text == translate("Kaspa Node"):
                if hasattr(self, "kaspa_node_tab"):
                    self.kaspa_node_tab.activate_tab()
            elif selected_tab_text == translate("Kaspa Bridge"):
                if hasattr(self, "kaspa_bridge_tab"):
                    self.kaspa_bridge_tab.activate_tab()
            elif selected_tab_text == translate("Analysis"):
                if hasattr(self, "analysis_tab_notebook"):
                    try:
                        sub_tab_index: int = self.analysis_tab_notebook.index(
                            self.analysis_tab_notebook.select()
                        )
                        if sub_tab_index == 0 and hasattr(self, "normal_analysis_tab"):
                            self.normal_analysis_tab.refresh_headers()
                    except tk.TclError:
                         if hasattr(self, "normal_analysis_tab"):
                             self.normal_analysis_tab.refresh_headers()

            elif selected_tab_text == translate("Settings"):
                if hasattr(self, "settings_tab"):
                    self.settings_tab._on_outer_tab_changed(event)

        except tk.TclError as e:
            if "Invalid slave specification" not in str(e):
                logger.error(f"Error handling tab change (TclError): {_sanitize_for_logging(e)}")
            try:
                self.previous_tab_index = self.tabview.index(self.tabview.select())
            except (tk.TclError, RuntimeError):
                self.previous_tab_index = 0
        except Exception as e:
            logger.error(f"Error handling tab change: {_sanitize_for_logging(e)}")
            try:
                self.previous_tab_index = self.tabview.index(self.tabview.select())
            except Exception:
                self.previous_tab_index = 0

    def reset_explorer_filters_display(self) -> None:
        if hasattr(self, "explorer_tab"):
            self.explorer_tab.reset_explorer_filters_display()

    def _build_explorer_tab(self, tab: ttk.Frame) -> None:
        logger.debug("Building Explorer tab UI.")
        self.explorer_tab = ExplorerTab(tab, self)
        self.explorer_tab.pack(fill=BOTH, expand=True, padx=5, pady=5)

    def start_ui_update_loop(self, data_queue: queue.Queue[pd.DataFrame]) -> None:
        if hasattr(self, "explorer_tab") and hasattr(
            self.explorer_tab, "results_component"
        ):
            self.explorer_tab.results_component.start_ui_update_loop(data_queue)

    def stop_ui_update_loop(self, data_queue: queue.Queue[pd.DataFrame]) -> None:
        if hasattr(self, "explorer_tab") and hasattr(
            self.explorer_tab, "results_component"
        ):
            self.explorer_tab.results_component.stop_ui_update_loop(data_queue)

    def _set_ui_for_processing(self, is_processing: bool) -> None:
        active: bool = not is_processing
        logger.debug(
            f"Setting global UI state for processing: {is_processing} (active: {active})"
        )

        if hasattr(self, "header"):
            self.header.set_controls_state(active)

        all_tab_objects: List[Optional[Any]] = [
            getattr(self, "explorer_tab", None),
            getattr(self, "normal_analysis_tab", None),
            getattr(self, "top_addresses_tab", None),
            getattr(self, "log_tab", None),
            getattr(self, "settings_tab", None),
            getattr(self, "kaspa_node_tab", None),
            getattr(self, "kaspa_bridge_tab", None),
        ]

        for tab_obj in all_tab_objects:
            if tab_obj and hasattr(tab_obj, "set_controls_state"):
                try:
                    cast(Any, tab_obj).set_controls_state(active)
                except (tk.TclError, RuntimeError):
                    pass

        if (
            hasattr(self, "settings_tab")
            and hasattr(self.settings_tab, "address_tab")
            and self.settings_tab.address_tab
        ):
            is_addr_selected: bool = bool(
                self.settings_tab.address_tab.address_tree.selection()
            )
            self.settings_tab.address_tab.explorer_btn.config(
                state=NORMAL if active and is_addr_selected else DISABLED
            )

        if hasattr(self, "tabview"):
            try:
                current_tab_id: str = self.tabview.select()
                log_tab_text: str = translate("Log")

                for tab_id in self.tabview.tabs():
                    tab_text: str = self.tabview.tab(tab_id, "text").strip()

                    if is_processing:
                        if tab_id != current_tab_id and tab_text != log_tab_text:
                            self.tabview.tab(tab_id, state=DISABLED)
                    else:
                        self.tabview.tab(tab_id, state=NORMAL)
            except Exception as e:
                logger.error(
                    f"Failed to manage tab states during fetch: {_sanitize_for_logging(e)}"
                )

        if is_processing:
            self.progress_bar.grid()
            self.progress_bar.start()
        else:
            self.progress_bar.stop()
            self.progress_bar.grid_remove()

    def _update_ui_for_address_validity(self, is_valid: bool) -> None:
        if not hasattr(self, "explorer_tab"):
            return
        is_fetching: bool = self.transaction_manager.is_fetching
        fetch_state: str = NORMAL if not is_fetching and is_valid else DISABLED
        self.explorer_tab.input_component.fetch_button.config(state=fetch_state)
        self.explorer_tab.input_component.force_fetch_button.config(state=fetch_state)
        self.explorer_tab.input_component.explorer_btn.config(
            state=NORMAL if is_valid else DISABLED
        )
        if hasattr(self, "explorer_tab"):
            self.explorer_tab.explorer_filter_controls.set_input_state(
                is_valid and not is_fetching
            )
            self.explorer_tab.explorer_filter_controls.set_action_buttons_state(
                is_valid and not is_fetching
            )

    def set_new_transaction_dataset(self, all_txs_df: pd.DataFrame) -> None:
        if hasattr(self, "explorer_tab"):
            self.explorer_tab.set_new_transaction_dataset(all_txs_df)

    def append_transaction_data(self, new_txs_df: pd.DataFrame) -> None:
        if hasattr(self, "explorer_tab"):
            self.explorer_tab.append_transaction_data(new_txs_df)

    def _build_status_bar(self) -> None:
        status_frame = ttk.Frame(self)
        status_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 5))
        status_frame.grid_columnconfigure(0, weight=1)
        self.status = Status(status_frame)
        self.status.grid(row=0, column=0, sticky="ew")
        self.progress_bar = ttk.Progressbar(
            self, mode="indeterminate", bootstyle="success-striped"
        )
        self.progress_bar.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 5))
        self.progress_bar.grid_remove()

    def update_address_balance(self, address: str) -> None:
        if hasattr(self, "explorer_tab"):
            self.explorer_tab.input_component.update_balance_display(None, None)
        threading.Thread(
            target=self._balance_worker, args=(address,), daemon=True
        ).start()

    def _balance_worker(self, address: str) -> None:
        balance: Optional[float] = fetch_address_balance(address)
        name: Optional[str] = self.address_names_map.get(address)
        try:
            if (
                self.current_address == address
                and self.winfo_exists()
                and hasattr(self, "explorer_tab")
            ):
                self.after(
                    0,
                    self.explorer_tab.input_component.update_balance_display,
                    balance,
                    name,
                )
        except (RuntimeError, tk.TclError):
            pass

    def _start_address_name_fetch(self) -> None:
        self.address_names_loaded.clear()
        threading.Thread(
            target=self._address_name_worker_logic,
            daemon=True,
            name="_address_name_worker",
        ).start()

    def _save_and_update_names(self, names: Optional[List[Dict[str, str]]]) -> None:
        try:
            if names:
                self.app_data_db.save_address_names(names)
            self.address_names_map = self.app_data_db.get_address_names_map()
        except Exception as e:
            logger.error(
                f"Failed to save or update address names in main thread: {_sanitize_for_logging(e)}"
            )
        finally:
            self.address_names_loaded.set()
            logger.info("Address names loaded event set.")
            self.after(100, self._continue_startup_after_names)

    def _address_name_worker_logic(self) -> None:
        try:
            logger.debug("Fetching address names in background worker.")
            names: Optional[List[Dict[str, str]]] = fetch_address_names()
            if self.winfo_exists():
                self.after(0, self.status.update_status, "Ready")
            self.after(0, self._save_and_update_names, names)
        except Exception as e:
            logger.error(f"Failed to fetch address names: {_sanitize_for_logging(e)}")
            if self.winfo_exists():
                self.after(0, self.status.update_status, "Ready")
            self.after(0, self._save_and_update_names, None)

    def on_settings_saved(self) -> None:
        logger.info("Settings saved. Triggering full UI and data refresh.")
        switch_language(CONFIG["language"])
        self.re_translate_ui()

    def _check_and_run_autostart_services(self) -> None:
        node_config: Dict[str, Any] = self.config_manager.get_config().get(
            "kaspa_node", {}
        )
        if node_config.get("autostart_var", False):
            if hasattr(self, "kaspa_node_tab"):
                logger.info("Auto-starting Kaspa Node...")
                self.kaspa_node_tab.controller.start_node(is_autostart=True)
        if hasattr(self, "kaspa_bridge_tab"):
            logger.info("Auto-starting Kaspa Bridge(s)...")
            self.kaspa_bridge_tab.autostart_bridges(is_autostart=True)

    def _on_language_change(self, lang_code: str) -> None:
        current_lang: str = self.config_manager.get_config().get("language")
        if current_lang == lang_code:
            return
        if switch_language(lang_code):
            logger.info(f"Language changed to {lang_code}. Triggering full UI refresh.")
            config: Dict[str, Any] = self.config_manager.get_config()
            config["language"] = lang_code
            self.config_manager.save_config(config)
            self.re_translate_ui()

    def re_translate_ui(self) -> None:
        logger.info("Re-translating all UI components...")
        self.title(translate("KaspaGateway"))
        self._rebuild_tabs()
        if hasattr(self, "analysis_tab_notebook"):
            try:
                self.analysis_tab_notebook.tab(0, text=translate("Standard Analysis"))
            except tk.TclError:
                pass

        components_to_translate: List[Optional[Any]] = [
            getattr(self, "header", None),
            getattr(self, "explorer_tab", None),
            getattr(self, "status", None),
            getattr(self, "settings_tab", None),
            getattr(self, "top_addresses_tab", None),
            getattr(self, "log_tab", None),
        ]

        all_tab_objects: List[Optional[ttk.Widget]] = [
            getattr(self, "normal_analysis_tab", None),
            getattr(self, "top_addresses_tab", None),
            getattr(self, "log_tab", None),
            getattr(self, "settings_tab", None),
            getattr(self, "kaspa_node_tab", None),
            getattr(self, "kaspa_bridge_tab", None),
        ]

        for tab_obj in all_tab_objects:
            if tab_obj and hasattr(tab_obj, "re_translate"):
                cast(Any, tab_obj).re_translate()

        for component in components_to_translate:
            if component and hasattr(component, "re_translate"):
                component.re_translate()

        logger.info("UI re-translation complete.")

    def _apply_currency_change(self, new_currency: str) -> None:
        self.currency_var.set(new_currency)
        self._update_price_display(self.price_updater.get_current_prices())
        if hasattr(self, "explorer_tab"):
            self.explorer_tab.results_component.update_currency_display(
                self.currency_var.get()
            )
        if self.current_address:
            self.update_address_balance(self.current_address)
        if hasattr(self, "top_addresses_tab") and self.top_addresses_tab.is_active:
            self.top_addresses_tab.update_currency_display(self.currency_var.get())
        if hasattr(self, "normal_analysis_tab"):
            self.normal_analysis_tab.on_currency_change()

    def _on_currency_dropdown_select(self, new_currency: str) -> None:
        config: Dict[str, Any] = self.config_manager.get_config()
        config["selected_currency"] = new_currency
        self.config_manager.save_config(config)
        self._apply_currency_change(new_currency)

    def _on_price_update(self, prices: Dict[str, float]) -> None:
        try:
            if self.winfo_exists():
                self.after(0, self._update_price_display, prices)
                self.after(
                    0,
                    self.header.update_price_tooltip,
                    self.price_updater.get_last_updated_ts(),
                )
        except (RuntimeError, tk.TclError):
            logger.warning(
                "GUI update for price skipped: main loop is not running (app shutting down)."
            )

    def _on_network_update(
        self, hashrate: Optional[float], difficulty: Optional[float]
    ) -> None:
        try:
            if self.winfo_exists():
                self.after(0, self._update_network_display, hashrate, difficulty)
                self.after(
                    0,
                    self.header.update_network_tooltip,
                    self.network_updater.get_last_updated_ts(),
                )
        except (RuntimeError, tk.TclError):
            logger.warning(
                "GUI update for network stats skipped: main loop is not running (app shutting down)."
            )

    def _update_header_stats_from_cache(self) -> None:
        try:
            if prices := self.app_data_db.get_cached_prices(expired=True):
                self._update_price_display(prices)
            if stats := self.app_data_db.get_cached_network_data(expired=True):
                self._update_network_display(stats[0], stats[1])
        except Exception as e:
            logger.warning(
                f"Could not pre-load header stats from cache: {_sanitize_for_logging(e)}"
            )

    def _update_price_display(self, prices: Dict[str, float]) -> None:
        code: str = self.currency_var.get().lower()
        price: float = prices.get(code, 0.0)
        self.price_var.set(f"{price:,.4f} {code.upper()}" if price > 0 else "N/A")

    def _update_network_display(
        self, hashrate: Optional[float], difficulty: Optional[float]
    ) -> None:
        if hashrate is not None and hashrate > 0:
            self.hashrate_var.set(f"{hashrate:.2f} PH/s")
        if difficulty is not None and difficulty > 0:
            self.difficulty_var.set(f"{format_large_number(difficulty, precision=2)}")

    def _update_clock_loop(self) -> None:
        try:
            if not self.winfo_exists():
                return
            self.clock_date_var.set(time.strftime("%Y-%m-%d"))
            self.clock_time_var.set(time.strftime("%H:%M:%S"))
            self.after(1000, self._update_clock_loop)
        except (tk.TclError, RuntimeError):
            pass
        except Exception as e:
            logger.error(f"Error in clock update loop: {e}")
            pass

    def apply_explorer_filters(self) -> None:
        if hasattr(self, "explorer_tab"):
            self.explorer_tab.apply_explorer_filters()

    def finalize_ui_load(
        self,
        operation_success: bool = True,
        fetch_message: str = "Fetch completed.",
        elapsed_time: float = 0.0,
    ) -> None:
        final_message: str = f"{translate(fetch_message)} ({elapsed_time:.2f}s)"
        try:
            if self.winfo_exists():
                self.status.update_status(final_message)
                if operation_success and (
                    "completed" in fetch_message.lower()
                    or "completed" in translate(fetch_message).lower()
                ):
                    self.after(5000, lambda: self.status.update_status("Ready"))
                self._set_ui_for_processing(False)

                if self.current_address:
                    if hasattr(self, "normal_analysis_tab"):
                        self.normal_analysis_tab.update_data(self.current_address)
        except (tk.TclError, RuntimeError):
            pass

        logger.info(
            f"Final UI load state applied. Message: {_sanitize_for_logging(final_message)}"
        )

    def _load_user_state(self) -> None:
        if not hasattr(self, "explorer_tab"):
            logger.warning("Explorer tab not initialized, skipping user state load.")
            return

        logger.info("Loading previous user state.")
        try:
            last_addr: Optional[str] = self.app_data_db.get_user_state("last_address")
            last_filters_json: Optional[str] = self.app_data_db.get_user_state(
                "last_filters"
            )

            if last_addr and validate_kaspa_address(last_addr):
                self.explorer_tab.input_component.address_combo.set(last_addr)
                self.explorer_tab.input_component._on_address_entry_change()

            if last_filters_json:
                filters: Dict[str, Any] = json.loads(last_filters_json)
                fc = self.explorer_tab.explorer_filter_controls

                if "start_date" in filters and filters["start_date"]:
                    self.explorer_tab.explorer_filter_controls.start_date_label.config(
                        text=datetime.fromisoformat(filters["start_date"]).strftime(
                            "%Y-%m-%d"
                        )
                    )

                if "end_date" in filters and filters["end_date"]:
                    self.explorer_tab.explorer_filter_controls.end_date_label.config(
                        text=datetime.fromisoformat(filters["end_date"]).strftime(
                            "%Y-%m-%d"
                        )
                    )

                fc.type_combo.set(filters.get("type_filter", "ALL"))
                fc.direction_combo.set(filters.get("direction_filter", "ALL"))

                if search_query := filters.get("search_query"):
                    fc._on_focus_in(None)
                    fc.search_entry.insert(0, search_query)

            logger.info("Successfully loaded user state.")
        except Exception as e:
            logger.warning(
                f"Could not load user state: {_sanitize_for_logging(e)}", exc_info=False
            )

    def _save_user_state(self) -> None:
        if not hasattr(self, "explorer_tab"):
            logger.warning("Explorer tab not initialized, skipping user state save.")
            return

        logger.info("Saving user state.")
        try:
            addr: str = self.explorer_tab.input_component.address_combo.get().strip()
            if validate_kaspa_address(addr):
                self.app_data_db.save_user_state("last_address", addr)

            filters: Dict[str, Any] = (
                self.explorer_tab.explorer_filter_controls.get_filters()
            )
            serializable_filters: Dict[str, Optional[str]] = {
                "start_date": (
                    filters["start_date"].isoformat()
                    if filters.get("start_date")
                    else None
                ),
                "end_date": (
                    filters["end_date"].isoformat() if filters.get("end_date") else None
                ),
                "type_filter": filters.get("type_filter"),
                "direction_filter": filters.get("direction_filter"),
                "search_query": filters.get("search_query"),
            }
            self.app_data_db.save_user_state(
                "last_filters", json.dumps(serializable_filters)
            )
            logger.info("User state saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save user state: {_sanitize_for_logging(e)}")

    def _auto_refresh_loop(self) -> None:
        try:
            if not self.winfo_exists():
                return

            config: Dict[str, Any] = self.config_manager.get_config().get(
                "performance", {}
            )
            if (
                config.get("auto_refresh_enabled")
                and not self.transaction_manager.is_fetching
            ):
                if self.current_address:
                    self.update_address_balance(self.current_address)
                try:
                    current_tab_text = self.tabview.tab(self.tabview.select(), "text").strip()
                    if current_tab_text == translate("Top Addresses"):
                        logger.debug("Auto-refreshing Top Addresses tab.")
                        self.top_addresses_tab.refresh_data() 
                except Exception:
                    pass

            interval_ms: int = int(
                config.get("auto_refresh_interval_seconds", 60) * 1000
            )
            self.after(interval_ms, self._auto_refresh_loop)
        except (RuntimeError, tk.TclError):
            logger.warning("Auto-refresh loop cancelled, window is closing.")
        except Exception as e:
            logger.error(f"Error in auto-refresh loop: {e}")

    def reset_explorer_tab_state(self) -> None:
        logger.info("Resetting Explorer tab UI state to default.")
        self.current_address = None

        try:
            if hasattr(self, "explorer_tab"):
                self.explorer_tab.input_component.address_combo.set("")
                self.explorer_tab.input_component.refresh_address_dropdown()
                self.explorer_tab.input_component.update_balance_display(None, None)
                self.explorer_tab.input_component._on_address_entry_change()
                self.explorer_tab.results_component.show_placeholder(
                    translate("Load an address to see transactions.")
                )
                self.explorer_tab.explorer_filter_controls.set_input_state(False)
                self.explorer_tab.explorer_filter_controls.set_action_buttons_state(
                    False
                )
                self.explorer_tab.export_component.set_ui_state(False)

            if hasattr(self, "normal_analysis_tab"):
                self.normal_analysis_tab.update_data(None)
        except Exception as e:
            logger.error(
                f"Error during reset_explorer_tab_state, possibly due to DB lock: {e}",
                exc_info=True,
            )
            ToastNotification(
                title=translate("Error"),
                message=translate("Failed to reset UI. Check logs."),
                bootstyle=DANGER,
                duration=3000,
            ).show_toast()

    def prompt_to_open_file(self, file_path: str, success_message: str) -> None:
        try:
            if messagebox.askyesno(
                translate("Export Successful"),
                f"{success_message}\n\n{translate('Open exported file?')}",
            ):
                try:
                    webbrowser.open(os.path.abspath(file_path))
                except Exception as e:
                    logger.error(f"Failed to open file {file_path}: {e}")
                    messagebox.showerror(
                        translate("Error"), f"{translate('Could not open file:')}\n{e}"
                    )
        except (tk.TclError, RuntimeError):
            logger.warning("Prompt to open file skipped, application is closing.")

    def _start_update_check(self) -> None:
        if not CONFIG.get("check_for_updates", True):
            logger.info("Update check is disabled in config.")
            return
        logger.info("Starting background thread for update check...")
        threading.Thread(
            target=self._update_check_worker, daemon=True, name="UpdateCheckWorker"
        ).start()

    def _update_check_worker(self) -> None:
        try:
            api_url: str = (
                "https://api.github.com/repos/KaspaPulse/KaspaGateway/releases/latest"
            )

            release_data: Optional[Dict[str, Any]] = fetch_latest_release_info(api_url)

            if not release_data:
                logger.warning("Could not fetch release data.")
                return

            remote_timestamp_str: Optional[str] = release_data.get("published_at")
            if not remote_timestamp_str:
                logger.warning("Release data is missing 'published_at' timestamp.")
                return

            local_timestamp_str: Optional[str] = (
                self.app_data_db.get_last_update_timestamp()
            )

            if local_timestamp_str == remote_timestamp_str:
                logger.info(
                    f"Application is up-to-date (Timestamp: {local_timestamp_str})."
                )
                return

            logger.info(
                f"New update found. Remote: {remote_timestamp_str}, Local: {local_timestamp_str}"
            )

            if self.winfo_exists():
                self.after(0, self._notify_user_of_update, remote_timestamp_str)

        except Exception as e:
            logger.error(f"Error in update check worker: {e}", exc_info=True)

    def _notify_user_of_update(self, new_timestamp: str) -> None:
        try:
            update_message: str = translate(
                "A new version of KaspaGateway is available. Would you like to go to the download page?"
            )

            if messagebox.askyesno(translate("Update"), update_message):
                release_url: str = (
                    CONFIG.get("links", {}).get(
                        "github", "https://github.com/KaspaPulse/KaspaGateway"
                    )
                    + "/releases"
                )
                webbrowser.open(release_url, new=2)

            self.app_data_db.save_last_update_timestamp(new_timestamp)

        except (tk.TclError, RuntimeError):
            pass
