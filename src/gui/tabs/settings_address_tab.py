from __future__ import annotations
import ttkbootstrap as ttk
import logging
import os
import threading
import json
import webbrowser
from tkinter import messagebox, filedialog
import tkinter as tk
from ttkbootstrap.constants import *
from ttkbootstrap.toast import ToastNotification
from typing import Dict, Any, Optional, Tuple, List, cast, TYPE_CHECKING, Set
from datetime import datetime

from src.utils.i18n import translate
from src.utils.validation import validate_kaspa_address, sanitize_input_string
from src.config.config import CONFIG, get_active_api_config
from src.api.network import fetch_address_balance

if TYPE_CHECKING:
    from src.gui.main_window import MainWindow
    from src.gui.config_manager import ConfigManager
    from src.gui.address_manager import AddressManager
    from src.database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class SettingsAddressTab(ttk.Frame):
    """
    This class encapsulates the "Manage Addresses" tab in the settings.
    It is managed by the main SettingsTab.
    """

    # --- Type Hint Declarations ---
    main_window: 'MainWindow'
    config_manager: 'ConfigManager'
    address_manager: 'AddressManager'
    address_sort_info: Dict[str, Any]
    name_label: ttk.Label
    name_entry: ttk.Entry
    address_label_settings: ttk.Label
    address_entry: ttk.Entry
    add_edit_addr_btn: ttk.Button
    del_addr_btn: ttk.Button
    explorer_btn: ttk.Button
    clear_addr_btn: ttk.Button
    refresh_addr_btn: ttk.Button
    last_updated_addr_label: ttk.Label
    address_tree: ttk.Treeview
    export_addr_btn: ttk.Button
    import_addr_btn: ttk.Button
    # --- End Type Hint Declarations ---

    def __init__(self, parent: ttk.Frame, main_window: 'MainWindow') -> None:
        super().__init__(parent)
        self.main_window: 'MainWindow' = main_window
        self.config_manager: 'ConfigManager' = main_window.config_manager
        self.address_manager: 'AddressManager' = main_window.address_manager

        self.address_sort_info: Dict[str, Any] = {'column': 'name', 'reverse': False}

        self._configure_address_tab()

    def _configure_address_tab(self) -> None:
        """Builds the UI components for this tab."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        input_frame = ttk.Frame(self)
        input_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        input_frame.grid_columnconfigure(1, weight=1)
        input_frame.grid_columnconfigure(3, weight=1)

        self.name_label = ttk.Label(input_frame, text=f"{translate('Name:')}:")
        self.name_label.grid(row=0, column=0, padx=5, sticky="w")
        self.name_entry = ttk.Entry(input_frame)
        self.name_entry.grid(row=0, column=1, padx=5, sticky="ew")

        self.address_label_settings = ttk.Label(input_frame, text=f"{translate('Kaspa Address')}:")
        self.address_label_settings.grid(row=0, column=2, padx=5, sticky="w")
        self.address_entry = ttk.Entry(input_frame)
        self.address_entry.grid(row=0, column=3, padx=5, sticky="ew")

        controls_frame = ttk.Frame(self)
        controls_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)

        self.add_edit_addr_btn = ttk.Button(controls_frame, text=translate("Add/Edit Address"), command=self._add_edit_address)
        self.add_edit_addr_btn.pack(side=LEFT, padx=5)
        self.del_addr_btn = ttk.Button(controls_frame, text=translate("Delete Address"), command=self._delete_address, bootstyle="danger")
        self.del_addr_btn.pack(side=LEFT, padx=5)
        self.explorer_btn = ttk.Button(controls_frame, text=translate("Explorer"), command=self._open_in_explorer, state=DISABLED)
        self.explorer_btn.pack(side=LEFT, padx=5)
        self.clear_addr_btn = ttk.Button(controls_frame, text=translate("Clear Fields"), command=self._clear_address_fields, bootstyle="secondary")
        self.clear_addr_btn.pack(side=LEFT, padx=5)
        self.refresh_addr_btn = ttk.Button(controls_frame, text=translate("Refresh List"), command=self.refresh_address_list, bootstyle="info")
        self.refresh_addr_btn.pack(side=LEFT, padx=5)
        self.last_updated_addr_label = ttk.Label(controls_frame, text="")
        self.last_updated_addr_label.pack(side=LEFT, padx=10)

        table_frame = ttk.Frame(self)
        table_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        columns: Tuple[str, ...] = ("Name", "Address", "Known Name", "Balance", "Value")
        self.address_tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        self.address_tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(table_frame, orient=VERTICAL, command=self.address_tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.address_tree.configure(yscrollcommand=vsb.set)
        self.address_tree.bind("<ButtonRelease-1>", self._on_address_select)

        import_export_frame = ttk.Frame(self)
        import_export_frame.grid(row=3, column=0, sticky="e", padx=5, pady=5)

        self.export_addr_btn = ttk.Button(import_export_frame, text=translate("Export Addresses"), command=self._export_addresses)
        self.export_addr_btn.pack(side=LEFT, padx=5)
        self.import_addr_btn = ttk.Button(import_export_frame, text=translate("Import Addresses"), command=self._import_addresses)
        self.import_addr_btn.pack(side=LEFT, padx=5)

        self.re_translate()

    def _sort_addresses_by_column(self, col_id: str) -> None:
        """Sorts the address list treeview by the clicked column."""
        sort_map: Dict[str, str] = {"Name": "name", "Known Name": "known_name", "Address": "address", "Balance": "balance_float", "Value": "balance_float"}
        sort_key: Optional[str] = sort_map.get(col_id)
        if not sort_key:
            return

        if self.address_sort_info["column"] == sort_key:
            self.address_sort_info["reverse"] = not self.address_sort_info["reverse"]
        else:
            self.address_sort_info["column"] = sort_key
            self.address_sort_info["reverse"] = (sort_key == "balance_float")

        self.refresh_address_list()

    def refresh_address_list(self) -> None:
        """Clears the tree and starts a worker to fetch DB details."""
        for i in self.address_tree.get_children():
            self.address_tree.delete(i)
        self.last_updated_addr_label.config(text=f"{translate('Last Updated')}: {datetime.now().strftime('%H:%M:%S')}")
        threading.Thread(target=self._fetch_address_data_worker, daemon=True).start()

    def _fetch_address_data_worker(self) -> None:
        """Worker thread to get DB file info and row counts."""
        try:
            addresses: List[Dict[str, Any]] = self.address_manager.get_all_addresses()
            if not self.winfo_exists():
                return

            for addr in addresses:
                addr['known_name'] = self.main_window.address_names_map.get(addr['address'], '')
                addr['balance_float'] = -1.0
                addr['balance_str'] = translate("Loading...")

            def sort_key_func(item: Dict[str, Any]) -> Any:
                val: Any = item.get(self.address_sort_info['column'])
                if isinstance(val, (int, float)):
                    return val
                return str(val).lower() if val else ''

            sorted_addresses: List[Dict[str, Any]] = sorted(addresses, key=sort_key_func, reverse=self.address_sort_info['reverse'])
            item_ids_addresses_to_fetch: List[Tuple[str, str]] = []

            def insert_rows() -> None:
                """Inserts rows into the treeview on the main thread."""
                for addr_data in sorted_addresses:
                    if not self.winfo_exists():
                        return
                    values: Tuple[str, ...] = (
                        addr_data.get('name', ''),
                        addr_data['address'],
                        addr_data['known_name'],
                        addr_data['balance_str'],
                        translate("Loading...")
                    )
                    item_id: str = self.address_tree.insert("", "end", values=values)
                    item_ids_addresses_to_fetch.append((item_id, addr_data['address']))
                self.after(100, self._fetch_balances_for_tree, item_ids_addresses_to_fetch)

            self.after(0, insert_rows)

        except Exception as e:
            logger.error(f"Failed to fetch address data for settings tab: {e}")
            if self.winfo_exists():
                self.after(0, lambda: ToastNotification(title=translate("Error"), message=translate("Error loading addresses"), bootstyle=DANGER, duration=3000).show_toast())

    def _fetch_balances_for_tree(self, item_ids_addresses: List[Tuple[str, str]]) -> None:
        """Spawns worker threads to fetch balances for visible rows."""
        for item_id, address in item_ids_addresses:
            if not self.winfo_exists():
                break
            threading.Thread(target=self._fetch_single_balance, args=(item_id, address), daemon=True).start()

    def _fetch_single_balance(self, item_id: str, address: str) -> None:
        """Worker thread to fetch balance for a single address."""
        balance: Optional[float] = fetch_address_balance(address)
        balance_str: str = f"{balance:,.2f} KAS" if balance is not None else translate("N/A")
        value_str: str = translate("N/A")

        if balance is not None:
            prices: Dict[str, float] = self.main_window.price_updater.get_current_prices()
            currency_code: str = self.main_window.currency_var.get().lower()
            price: float = prices.get(currency_code, 0.0)
            value: float = balance * price
            value_str = f"{value:,.2f}" if price > 0 else translate("N/A")

        def update_ui() -> None:
            """Safe UI update for the main thread."""
            if self.winfo_exists() and self.address_tree.exists(item_id):
                self.address_tree.set(item_id, "Balance", balance_str)
                self.address_tree.set(item_id, "Value", value_str)

        if self.winfo_exists():
            self.after(0, update_ui)

    def _on_address_select(self, event: Optional[tk.Event] = None) -> None:
        """Populates the entry fields when a tree item is selected."""
        sel: Tuple[str, ...] = self.address_tree.selection()
        if not sel:
            self.explorer_btn.config(state=DISABLED)
            return

        self.explorer_btn.config(state=NORMAL)

        item_values: List[str] = self.address_tree.item(sel[0])['values']
        name: str = item_values[0]
        addr: str = item_values[1]

        self.name_entry.delete(0, END)
        self.name_entry.insert(0, name)
        self.address_entry.delete(0, END)
        self.address_entry.insert(0, addr)

    def _clear_address_fields(self) -> None:
        """Clears the entry fields and deselects the tree item."""
        self.name_entry.delete(0, END)
        self.address_entry.delete(0, END)
        sel: Tuple[str, ...] = self.address_tree.selection()
        if sel:
            self.address_tree.selection_remove(sel[0])
        self.explorer_btn.config(state=DISABLED)

    def _add_edit_address(self) -> None:
        """Saves or updates an address from the entry fields."""
        address: str = self.address_entry.get().strip()
        name: str = sanitize_input_string(self.name_entry.get())

        if not validate_kaspa_address(address):
            messagebox.showerror(translate("Invalid Input"), translate("Invalid Kaspa address"))
            return

        if self.address_manager.save_address(address, name):
            self.refresh_address_list()
            self.main_window.explorer_tab.input_component.refresh_address_dropdown()
            self._clear_address_fields()
            # ToastNotification(title=translate("Address Saved"), message=translate("Address Saved"), bootstyle=SUCCESS, duration=3000).show_toast()

    def _delete_address(self) -> None:
        """Deletes the selected address from the database."""
        sel: Tuple[str, ...] = self.address_tree.selection()
        if not sel:
            return

        addr: str = self.address_tree.item(sel[0])['values'][1]
        if messagebox.askyesno(translate("Delete Address"), f"{translate('Delete')} {addr}?"):
            if self.address_manager.delete_address(addr):
                self.refresh_address_list()
                self.main_window.explorer_tab.input_component.refresh_address_dropdown()
                self._clear_address_fields()

    def _open_in_explorer(self) -> None:
        """Opens the selected address in the block explorer."""
        sel: Tuple[str, ...] = self.address_tree.selection()
        if not sel:
            return

        addr: str = self.address_tree.item(sel[0])['values'][1]
        api_config: Dict[str, Any] = get_active_api_config()
        url: str = api_config['explorer']['address'].format(kaspaAddress=addr)
        if url:
            webbrowser.open(url, new=2)

    def _export_addresses(self) -> None:
        """Exports all saved addresses to a JSON file."""
        addresses: List[Dict[str, Any]] = self.address_manager.get_all_addresses()
        if not addresses:
            ToastNotification(title=translate("Export Addresses"), message=translate("No addresses to export."), bootstyle=INFO, duration=3000).show_toast()
            return

        ts: str = datetime.now().strftime('%Y%m%d_%H%M%S')
        initial_filename: str = f"kaspa_addresses_{ts}.json"
        export_dir: str = CONFIG.get('paths', {}).get('export', '.')
        os.makedirs(export_dir, exist_ok=True)

        file_path: Optional[str] = filedialog.asksaveasfilename(
            initialfile=initial_filename,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialdir=export_dir,
            title=translate("Export Addresses")
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(addresses, f, indent=4)
                # ToastNotification(
                #     title=translate("Export Successful"),
                #     message=f"{translate('Addresses exported to')} {os.path.basename(file_path)}",
                #     bootstyle=SUCCESS,
                #     duration=3000
                # ).show_toast()
                logger.info(f"Addresses exported to {file_path}")
            except Exception as e:
                messagebox.showerror(translate("Error"), str(e))

    def _import_addresses(self) -> None:
        """Imports addresses from a JSON file."""
        file_path: Optional[str] = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialdir=CONFIG['paths']['export'],
            title=translate("Import Addresses")
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data: Any = json.load(f)

                imported_count: int = 0
                if isinstance(data, list):
                    for item in data:
                        if (isinstance(item, dict) and
                            'address' in item and 'name' in item and
                            validate_kaspa_address(item['address'])):

                            self.address_manager.save_address(item['address'], sanitize_input_string(item['name']))
                            imported_count += 1

                ToastNotification(title=translate("Import Successful"), message=f"{imported_count} {translate('addresses imported.')}", bootstyle=SUCCESS, duration=3000).show_toast()
                self.refresh_address_list()
                self.main_window.explorer_tab.input_component.refresh_address_dropdown()
            except Exception as e:
                messagebox.showerror(translate("Error"), f"{translate('Failed to import addresses:')}\n{e}")

    def re_translate(self) -> None:
        """Re-translates all widgets in this tab."""
        self.name_label.config(text=f"{translate('Name:')}:")
        self.address_label_settings.config(text=f"{translate('Kaspa Address')}:")

        currency_code: str = self.main_window.currency_var.get().upper()
        value_header: str = f"{translate('Value')} ({currency_code})"

        col_map: Dict[str, str] = {
            "Name": "Name",
            "Address": "Kaspa Address",
            "Known Name": "Known Name",
            "Balance": "Balance",
            "Value": value_header
        }

        for col, text_key in col_map.items():
            self.address_tree.heading(col, text=f"{translate(text_key)} ↕", command=lambda c=col: self._sort_addresses_by_column(c))

        self.address_tree.column("Name", width=150, stretch=False)
        self.address_tree.column("Address", width=400, stretch=True)
        self.address_tree.column("Known Name", width=150, stretch=False)
        self.address_tree.column("Balance", width=150, stretch=False, anchor="e")
        self.address_tree.column("Value", width=150, stretch=False, anchor="e")

        btn_configs: Dict[str, ttk.Button] = {
            "Add/Edit Address": self.add_edit_addr_btn,
            "Delete Address": self.del_addr_btn,
            "Explorer": self.explorer_btn,
            "Clear Fields": self.clear_addr_btn,
            "Export Addresses": self.export_addr_btn,
            "Import Addresses": self.import_addr_btn,
            "Refresh List": self.refresh_addr_btn
        }
        for key, btn in btn_configs.items():
            btn.config(text=translate(key))

        current_time_text: str = self.last_updated_addr_label.cget("text")
        if ":" in current_time_text:
            self.last_updated_addr_label.config(text=f"{translate('Last Updated')}:{current_time_text.split(':', 1)[1]}")