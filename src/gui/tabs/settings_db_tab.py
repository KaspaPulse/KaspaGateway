# File: src/gui/tabs/settings_db_tab.py
"""
This module contains the View/Controller for the "Database Maintenance" tab
within the main Settings tab.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

import ttkbootstrap as ttk
from ttkbootstrap.constants import DANGER, DISABLED, LEFT, NORMAL, SUCCESS, VERTICAL, WARNING
from ttkbootstrap.toast import ToastNotification

from src.config.config import CONFIG
from src.database.db_locker import release_lock
from src.utils.i18n import translate

if TYPE_CHECKING:
    from src.database.db_manager import DatabaseManager
    from src.gui.config_manager import ConfigManager
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


class SettingsDbTab(ttk.Frame):
    """
    This class encapsulates the "Database Maintenance" tab in the settings.
    It is managed by the main SettingsTab.
    """

    main_window: "MainWindow"
    config_manager: "ConfigManager"
    db_manager: "DatabaseManager"
    db_buttons: Dict[str, ttk.Button]
    db_tree: ttk.Treeview
    db_btn_frame: ttk.Frame

    def __init__(self, parent: ttk.Frame, main_window: "MainWindow") -> None:
        super().__init__(parent)
        self.main_window = main_window
        self.config_manager = main_window.config_manager
        self.db_manager = main_window.db_manager
        self.db_buttons = {}

        self._configure_db_tab()

    def _configure_db_tab(self) -> None:
        """Builds the UI components for this tab."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        table_frame = ttk.Frame(self)
        table_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        columns = ("Name", "Size", "Modified", "Details")
        self.db_tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", selectmode="extended"
        )
        self.db_tree.grid(row=0, column=0, sticky="nsew")
        vsb_db = ttk.Scrollbar(table_frame, orient=VERTICAL, command=self.db_tree.yview)
        vsb_db.grid(row=0, column=1, sticky="ns")
        self.db_tree.configure(yscrollcommand=vsb_db.set)

        self.db_btn_frame = ttk.Frame(self)
        self.db_btn_frame.grid(row=1, column=0, sticky="w", padx=5, pady=5)

        btn_data = [
            ("Refresh List", self._refresh_db_info, None),
            ("Compact Database", self._compact_db, "info"),
            ("Clear Caches", self._clear_caches, "warning"),
            ("Backup", self._backup_db, None),
            ("Restore", self._restore_db, None),
            ("Delete", self._show_delete_db_dialog, "danger"),
        ]

        for key, cmd, style in btn_data:
            bootstyle = style if style else "default"
            btn = ttk.Button(
                self.db_btn_frame, text=translate(key), command=cmd, bootstyle=bootstyle
            )
            btn.pack(side=LEFT, padx=5)
            self.db_buttons[key] = btn

        self.re_translate()

    def _set_buttons_state(self, state: str) -> None:
        """Enables or disables all buttons in the DB tab."""
        try:
            for btn in self.db_buttons.values():
                if btn.winfo_exists():
                    btn.config(state=state)
        except tk.TclError:
            pass

    def _refresh_db_info(self) -> None:
        """Clears the tree and starts a worker to fetch DB details."""
        for i in self.db_tree.get_children():
            self.db_tree.delete(i)
        threading.Thread(target=self._fetch_db_details_worker, daemon=True).start()

    def _fetch_db_details_worker(self) -> None:
        """Worker thread to get DB file info and row counts."""
        db_info_list = self.db_manager.get_database_info()
        db_filenames = self.main_window.config_manager.get_config()["db_filenames"]

        for info in db_info_list:
            details = ""
            try:
                db_name_lower = info["name"].lower()
                if db_name_lower == db_filenames.get("transactions", "").lower():
                    count = self.main_window.tx_db.get_total_transaction_count()
                    details = f"{count} {translate('transactions')}"
                elif db_name_lower == db_filenames.get("addresses", "").lower():
                    count = self.main_window.addr_db.get_total_address_count()
                    details = f"{count} {translate('addresses')}"
                elif db_name_lower == db_filenames.get("app_data", "").lower():
                    price_count = self.main_window.app_data_db.get_cached_prices_count()
                    name_count = self.main_window.app_data_db.get_address_names_count()
                    details = f"{price_count} {translate('price points')}, {name_count} {translate('Known Name')}"
            except Exception as e:
                logger.warning(f"Could not fetch details for {info['name']}: {e}")
                details = translate("Error - See Logs")

            if self.winfo_exists():
                self.after(
                    0,
                    lambda info=info, details=details: self.db_tree.insert(
                        "",
                        "end",
                        values=(
                            info["name"],
                            f"{info['size_kb']:.2f}",
                            info["last_modified"].strftime("%Y-%m-%d %H:%M:%S"),
                            details,
                        ),
                    ),
                )

    def _compact_db(self) -> None:
        db_name = self._get_selected_db_name(single=True)
        if not db_name: return
        if messagebox.askyesno(translate("Compact Database"), translate("Compact Warning").format(db_name)):
            self._set_buttons_state(DISABLED)
            self.main_window.status.update_status(translate("Compacting database..."))
            threading.Thread(target=self._compact_db_worker, args=(db_name,), daemon=True).start()

    def _compact_db_worker(self, db_name: str) -> None:
        try:
            self.after(0, self.main_window.close_all_db_connections)
            time.sleep(0.5)
            release_lock(db_name)
            time.sleep(0.2)
            success, msg = self.db_manager.compact_database(db_name)
            
            def ui_update():
                self.main_window.reinitialize_databases()
                self._refresh_db_info()
                self.main_window.status.update_status(translate("Ready"))
                self._set_buttons_state(NORMAL)
                ToastNotification(title=translate("Compact Database"), message=msg, bootstyle=SUCCESS if success else DANGER, duration=3000).show_toast()
            
            self.after(0, ui_update)
        except Exception as e:
            logger.error(f"Compact DB worker failed: {e}", exc_info=True)
            self.after(0, self.main_window.reinitialize_databases)
            self.after(0, self._set_buttons_state, NORMAL)

    def _clear_caches(self) -> None:
        if messagebox.askyesno(translate("Confirm Action"), translate("Clear Caches Warning")):
            try:
                self.main_window.app_data_db.clear_caches()
                ToastNotification(title=translate("Clear Caches"), message=translate("Caches cleared successfully."), bootstyle=SUCCESS, duration=3000).show_toast()
            except Exception as e:
                logger.error(f"Failed to clear caches: {e}")
                ToastNotification(title=translate("Error"), message=str(e), bootstyle=DANGER, duration=3000).show_toast()
            finally:
                self._refresh_db_info()

    def _get_selected_db_name(self, single: bool = False) -> Optional[Any]:
        sel = self.db_tree.selection()
        if not sel:
            ToastNotification(title=translate("No Selection"), message=translate("No database selected."), bootstyle=WARNING, duration=3000).show_toast()
            return None
        if single and len(sel) > 1:
            ToastNotification(title=translate("No Selection"), message=translate("Please select only one database for this action."), bootstyle=WARNING, duration=3000).show_toast()
            return None
        if single: return self.db_tree.item(sel[0])["values"][0]
        return [self.db_tree.item(item_id)["values"][0] for item_id in sel]

    def _backup_db(self) -> None:
        db_name = self._get_selected_db_name(single=True)
        if not db_name: return
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        initial_filename = f"{os.path.splitext(db_name)[0]}_{ts}.duckdb"
        backup_file_path = filedialog.asksaveasfilename(
            initialfile=initial_filename,
            defaultextension=".duckdb",
            filetypes=[(f"{translate('Kaspa Database Backup')}", "*.duckdb"), (f"{translate('All Files')}", "*.*")],
            title=f"{translate('Save backup file for')} {db_name}",
            initialdir=self.db_manager.backup_dir,
        )
        if not backup_file_path: return
        if messagebox.askyesno(translate("Backup"), f"{translate('Create a backup of')} {db_name} {translate('to')} {os.path.basename(backup_file_path)}?"):
            self._set_buttons_state(DISABLED)
            self.main_window.status.update_status(f"Backing up {db_name}...")
            threading.Thread(target=self._perform_db_backup, args=(backup_file_path, db_name,), daemon=True).start()

    def _perform_db_backup(self, backup_file_path: str, db_name: str) -> None:
        def error_ui_update(e: Exception):
            self.main_window.reinitialize_databases()
            self._set_buttons_state(NORMAL)
            self.main_window.status.update_status(translate("Error"))
            ToastNotification(title=translate("Error"), message=str(e), bootstyle=DANGER, duration=3000).show_toast()

        try:
            self.after(0, self.main_window.close_all_db_connections)
            time.sleep(0.5)
            release_lock(db_name)
            time.sleep(0.2)
            db_path = os.path.join(self.db_manager.data_dir, db_name)
            if not os.path.exists(db_path): raise FileNotFoundError(translate("Source database file not found."))
            shutil.copy2(db_path, backup_file_path)
            if os.path.exists(f"{db_path}.wal"): shutil.copy2(f"{db_path}.wal", f"{backup_file_path}.wal")
            
            success = True
            msg = f"{translate('Backup created successfully')}: {os.path.basename(backup_file_path)}"
            
            def ui_update():
                self.main_window.reinitialize_databases()
                self._refresh_db_info()
                self.main_window.status.update_status(translate("Ready"))
                self._set_buttons_state(NORMAL)
                ToastNotification(title=translate("Backup Successful"), message=f"{msg}\n{translate('Location')}: {os.path.dirname(backup_file_path)}", bootstyle=SUCCESS, duration=5000).show_toast()

            if self.winfo_exists(): self.after(0, ui_update)
        except Exception as e:
            logger.error(f"Backup DB worker failed: {e}", exc_info=True)
            if self.winfo_exists(): self.after(0, error_ui_update, e)

    def _restore_db(self) -> None:
        target_db_name = self._get_selected_db_name(single=True)
        if not target_db_name: return
        base_name = os.path.splitext(target_db_name)[0]
        backup_file_path = filedialog.askopenfilename(
            title=f"{translate('Select backup file for')} {target_db_name}",
            initialdir=self.db_manager.backup_dir,
            defaultextension=".duckdb",
            filetypes=[(f"{translate('Kaspa Database Backup')}", f"{base_name}_*.duckdb"), (f"{translate('All Files')}", "*.*")],
        )
        if not backup_file_path: return
        if messagebox.askyesno(translate("Restore"), f"{translate('This will overwrite')} {target_db_name} {translate('with')} {os.path.basename(backup_file_path)}. {translate('Continue?')}"):
            self.main_window.status.update_status(f"Restoring {target_db_name}...")
            self._set_buttons_state(DISABLED)
            threading.Thread(target=self._perform_db_restore, args=(backup_file_path, target_db_name), daemon=True).start()

    def _perform_db_restore(self, backup_file_path: str, target_db_name: str) -> None:
        try:
            self.after(0, self.main_window.close_all_db_connections)
            time.sleep(0.5)
            release_lock(target_db_name)
            time.sleep(0.2)
            success, msg = self.db_manager.restore_database(backup_file_path, target_db_name)
            
            def ui_update():
                ToastNotification(title=translate("Restore"), message=msg, bootstyle=SUCCESS if success else DANGER, duration=3000).show_toast()
                self.main_window.reinitialize_databases()
                self._refresh_db_info()
                if target_db_name == CONFIG["db_filenames"]["addresses"]:
                    if self.main_window.settings_tab.address_tab: self.main_window.settings_tab.address_tab.refresh_address_list()
                    if hasattr(self.main_window.explorer_tab, "input_component"): self.main_window.explorer_tab.input_component.refresh_address_dropdown()
                if hasattr(self.main_window, "explorer_tab"): self.main_window.explorer_tab.apply_explorer_filters()
                self.main_window.status.update_status(translate("Ready"))
                self._set_buttons_state(NORMAL)

            if self.winfo_exists(): self.after(0, ui_update)
        except Exception as e:
            logger.error(f"Restore DB worker failed: {e}", exc_info=True)
            self.after(0, self.main_window.reinitialize_databases)
            self.after(0, self._set_buttons_state, NORMAL)

    def _show_delete_db_dialog(self) -> None:
        dbs_to_delete = self._get_selected_db_name()
        if not dbs_to_delete: return
        confirm_message = f"{translate('Selective DB Delete Warning')}\n\n- " + "\n- ".join(dbs_to_delete) + f"\n\n{translate('This action cannot be undone. Are you sure?')}"
        if messagebox.askyesno(translate("Confirm Deletion"), confirm_message):
            self._delete_selected_databases(dbs_to_delete)

    def _delete_selected_databases(self, db_names: List[str]) -> None:
        self.main_window.status.update_status(translate("Deleting databases..."))
        self._set_buttons_state(DISABLED)
        self.after(100, self._delete_db_step1_close, db_names)

    def _delete_db_step1_close(self, db_names: List[str]) -> None:
        logger.info("Delete Step 1: Closing all DB connections...")
        self.main_window.close_all_db_connections()
        for db_name in db_names: release_lock(db_name)
        self.after(200, self._delete_db_step2_delete, db_names)

    def _delete_db_step2_delete(self, db_names: List[str]) -> None:
        logger.info("Delete Step 2: Deleting database files...")
        deleted_count = 0
        failed_dbs = []
        for db_name in db_names:
            success, msg = self.db_manager.delete_database(db_name)
            if success: deleted_count += 1
            else:
                failed_dbs.append(db_name)
                logger.error(f"Failed to delete {db_name}: {msg}")
        self.after(100, self._delete_db_step3_reinit, deleted_count, failed_dbs)

    def _delete_db_step3_reinit(self, deleted_count: int, failed_dbs: List[str]) -> None:
        logger.info("Delete Step 3: Re-initializing databases and UI...")
        if deleted_count > 0: logger.info(f"{deleted_count} {translate('databases deleted successfully.')}")
        self.main_window.reinitialize_databases()
        self._refresh_db_info()
        self.main_window.reset_explorer_tab_state()
        if self.main_window.settings_tab.address_tab_initialized and self.main_window.settings_tab.address_tab:
            self.main_window.settings_tab.address_tab.refresh_address_list()
        if failed_dbs:
            ToastNotification(title=translate("Error"), message=f"{translate('failed to delete some databases. Check logs.')}", bootstyle=DANGER, duration=3000).show_toast()
        self.main_window.status.update_status(translate("Ready"))
        self._set_buttons_state(NORMAL)

    def re_translate(self) -> None:
        for key, btn in self.db_buttons.items(): btn.config(text=translate(key))
        db_cols = {"Name": "DB File", "Size": "Size (KB)", "Modified": "Last Modified", "Details": "Details"}
        for col, text_key in db_cols.items(): self.db_tree.heading(col, text=translate(text_key))
        self.db_tree.column("Name", width=150, stretch=False)
        self.db_tree.column("Size", width=100, stretch=False, anchor="e")
        self.db_tree.column("Modified", width=150, stretch=False, anchor="center")
        self.db_tree.column("Details", width=200, stretch=True)
