# File: src/gui/input.py
from __future__ import annotations
import logging
import tkinter as tk
import webbrowser
from tkinter import messagebox
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set
import pandas as pd
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.tooltip import ToolTip
from src.config.config import CONFIG
from src.utils.i18n import translate
from src.utils.validation import _address_placeholders, _sanitize_for_logging, validate_kaspa_address

if TYPE_CHECKING:
    from src.gui.address_manager import AddressManager
    from src.gui.main_window import MainWindow
    from src.gui.transaction_manager import TransactionManager

logger = logging.getLogger(__name__)

class Input(ttk.Labelframe):
    def __init__(self, parent: ttk.Frame, main_window: MainWindow, transaction_manager: TransactionManager, address_manager: AddressManager) -> None:
        super().__init__(parent, text=f" {translate('Load Address')} ", padding=10)
        self.main_window = main_window
        self.transaction_manager = transaction_manager
        self.address_manager = address_manager
        self.placeholder_active = False
        
        # Initialize labels to None to prevent AttributeError before UI build
        self.balance_label_name = None
        self.balance_label_value = None
        self.balance_label_fiat_value = None
        
        self._build_ui()
        self.refresh_address_dropdown()

    def _build_ui(self) -> None:
        container = ttk.Frame(self)
        container.pack(fill=X, expand=True)
        container.grid_columnconfigure(1, weight=1)
        self.address_label = ttk.Label(container, text=translate("Kaspa Address"))
        self.address_label.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="w")
        self.address_combo = ttk.Combobox(container, values=[""])
        self.address_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.address_combo.bind("<<ComboboxSelected>>", self._on_dropdown_select)
        self.address_combo.bind("<KeyRelease>", self._on_address_entry_change)
        
        balance_container = ttk.Frame(container)
        balance_container.grid(row=0, column=2, sticky="e", padx=10, pady=5)
        
        # Corrected Balance UI Structure
        self.balance_label_title = ttk.Label(balance_container, text=f"{translate('Balance')}:")
        self.balance_label_title.pack(side=LEFT, padx=(0, 5))
        self.balance_label_value = ttk.Label(balance_container, text="N/A", font="-weight bold", bootstyle="info")
        self.balance_label_value.pack(side=LEFT)
        
        # Name label needs to be properly initialized
        self.balance_label_name = ttk.Label(balance_container, text="", font="-size 9 -weight bold", bootstyle="success")
        self.balance_label_name.pack(side=LEFT, padx=(5, 0))
        
        self.balance_label_fiat_value = ttk.Label(balance_container, text="", font="-size 9", bootstyle="secondary")
        self.balance_label_fiat_value.pack(side=LEFT, padx=(5, 0))
        
        btn_frame = ttk.Frame(container)
        btn_frame.grid(row=0, column=3, padx=5, pady=5)
        self.fetch_button = ttk.Button(btn_frame, text=translate("Fetch"), command=self._on_load_transactions, bootstyle="primary")
        self.fetch_button.pack(side=LEFT, padx=(0, 2))
        self.force_fetch_button = ttk.Button(btn_frame, text=translate("Force Fetch"), command=lambda: self._on_load_transactions(force=True), bootstyle="danger")
        self.force_fetch_button.pack(side=LEFT, padx=(0, 5))
        self.explorer_btn = ttk.Button(btn_frame, text=translate("Explorer"), command=self._open_in_explorer)
        self.explorer_btn.pack(side=LEFT)
        self.cancel_button = ttk.Button(container, text=translate("Cancel"), command=self.transaction_manager.stop_fetch, state="disabled", bootstyle="secondary")
        self.cancel_button.grid(row=0, column=4, padx=5, pady=5)

    def _on_address_entry_change(self, event=None):
        addr = self.address_combo.get().strip()
        if hasattr(self.main_window, "_update_ui_for_address_validity"):
            self.main_window._update_ui_for_address_validity(validate_kaspa_address(addr))

    def _open_in_explorer(self):
        addr = self.address_combo.get().strip()
        if validate_kaspa_address(addr):
            url = CONFIG["api"]["profiles"][CONFIG["api"]["active_profile"]]["explorer"]["address"].format(kaspaAddress=addr)
            webbrowser.open(url, new=2)

    def _on_dropdown_select(self, event=None):
        val = self.address_combo.get()
        addr = val.split(" - ")[1].strip() if " - " in val else val.strip()
        if addr != val: self.address_combo.set(addr)
        self._on_address_entry_change()
        
        if hasattr(self.main_window, "current_address") and self.main_window.current_address:
            if addr.lower() == self.main_window.current_address.lower(): return

        if hasattr(self.main_window, "explorer_tab") and addr != self.main_window.current_address:
            self.main_window.explorer_tab.results_component.show_placeholder(translate("Press 'Fetch' or apply filters."))
            self.main_window.explorer_tab.results_component.current_df = pd.DataFrame()

    def _on_load_transactions(self, force=False):
        addr = self.address_combo.get().strip()
        if not validate_kaspa_address(addr): return
        if force and not messagebox.askyesno(title=translate("Force_Fetch_Confirm_Title"), message=translate("Force_Fetch_Confirm_Msg")): return
        
        if hasattr(self.main_window, "explorer_tab"):
            self.main_window.explorer_tab.results_component.prepare_for_force_fetch()
            
        all_addrs = {a["address"].lower() for a in self.address_manager.get_all_addresses()}
        if addr.lower() not in all_addrs:
            self.address_manager.save_address(addr, "")
            self.refresh_address_dropdown(addr)

        self.main_window.update_address_balance(addr)
        filters = self.main_window.explorer_tab.explorer_filter_controls.get_filters()
        self.transaction_manager.start_fetch(addr, force=force, filters=filters)

    def update_balance_display(self, bal, name):
        # FIX: Check if widgets exist before configuring
        if not self.winfo_exists(): return
        if self.balance_label_value:
            self.balance_label_value.config(text=f"{bal:,.2f} KAS" if bal is not None else "N/A")
        if self.balance_label_name:
            self.balance_label_name.config(text=name or "")
        
        if bal is not None and self.balance_label_fiat_value:
            currency_code = self.main_window.currency_var.get().lower()
            prices = self.main_window.price_updater.get_current_prices()
            price = prices.get(currency_code, 0.0)
            if price > 0:
                fiat_value = bal * price
                self.balance_label_fiat_value.config(text=f"({fiat_value:,.2f} {currency_code.upper()})")
            else:
                self.balance_label_fiat_value.config(text="")
        elif self.balance_label_fiat_value:
             self.balance_label_fiat_value.config(text="")

    def refresh_address_dropdown(self, select_addr=None):
        try:
            addrs = self.address_manager.get_all_addresses()
            vals = [f"{a['name']} - {a['address']}" if a['name'] else a['address'] for a in addrs]
            self.address_combo.configure(values=[translate("Enter Kaspa Address")] + vals)
            if select_addr: self.address_combo.set(select_addr)
        except Exception as e:
            logger.error(f"Dropdown refresh error: {e}")

    def set_ui_state(self, fetching):
        s = DISABLED if fetching else NORMAL
        self.address_combo.configure(state=s)
        self.cancel_button.configure(state=NORMAL if fetching else DISABLED)
        self.fetch_button.configure(state=s)
        self.force_fetch_button.configure(state=s)

    def re_translate(self):
        self.config(text=f" {translate('Load Address')} ")
        self.address_label.config(text=translate("Kaspa Address"))
        self.fetch_button.config(text=translate("Fetch"))
        self.force_fetch_button.config(text=translate("Force Fetch"))
        self.refresh_address_dropdown()
