#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This module defines the Input widget, which includes the address entry/dropdown,
balance display, and the main fetch/cancel buttons.
"""

from __future__ import annotations

import logging
import tkinter as tk
import webbrowser
from tkinter import messagebox
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

import pandas as pd
import ttkbootstrap as ttk
from ttkbootstrap.constants import DISABLED, LEFT, NORMAL, X, Y
from ttkbootstrap.tooltip import ToolTip

from src.config.config import CONFIG
from src.utils.i18n import translate
from src.utils.validation import (
    _address_placeholders,
    _sanitize_for_logging,
    validate_kaspa_address,
)

if TYPE_CHECKING:
    from src.gui.address_manager import AddressManager
    from src.gui.main_window import MainWindow
    from src.gui.transaction_manager import TransactionManager

logger = logging.getLogger(__name__)


class Input(ttk.Labelframe):
    """
    The main input composite widget for loading addresses and initiating fetches.
    """

    main_window: MainWindow
    transaction_manager: TransactionManager
    address_manager: AddressManager
    placeholder_active: bool

    address_label: ttk.Label
    address_combo: ttk.Combobox
    balance_label_title: ttk.Label
    balance_label_value: ttk.Label
    balance_label_name: ttk.Label
    balance_label_fiat_value: ttk.Label
    fetch_button: ttk.Button
    force_fetch_button: ttk.Button
    explorer_btn: ttk.Button
    cancel_button: ttk.Button
    fetch_tooltip: ToolTip
    force_fetch_tooltip: ToolTip
    cancel_tooltip: ToolTip

    def __init__(
        self,
        parent: ttk.Frame,
        main_window: MainWindow,
        transaction_manager: TransactionManager,
        address_manager: AddressManager,
    ) -> None:
        """
        Initializes the Input widget.
        """
        super().__init__(parent, text=f" {translate('Load Address')} ", padding=10)
        self.main_window = main_window
        self.transaction_manager = transaction_manager
        self.address_manager = address_manager

        self.placeholder_active = False

        self._build_ui()
        self.refresh_address_dropdown()

    def _build_ui(self) -> None:
        """Constructs the UI components for the input widget."""
        container = ttk.Frame(self)
        container.pack(fill=X, expand=True)
        container.grid_columnconfigure(1, weight=1)

        # --- Address Selection ---
        self.address_label = ttk.Label(container, text=translate("Kaspa Address"))
        self.address_label.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="w")

        self.address_combo = ttk.Combobox(container, values=[""])
        self.address_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.address_combo.bind("<<ComboboxSelected>>", self._on_dropdown_select)
        self.address_combo.bind("<KeyRelease>", self._on_address_entry_change)

        # --- Balance Display Area ---
        balance_container = ttk.Frame(container)
        balance_container.grid(row=0, column=2, sticky="e", padx=10, pady=5)
        balance_container.grid_columnconfigure(0, weight=1)

        # Row 1: Balance Title and KAS Value
        kas_balance_frame = ttk.Frame(balance_container)
        kas_balance_frame.pack(anchor="e")

        self.balance_label_title = ttk.Label(
            kas_balance_frame, text=f"{translate('Balance')}:"
        )
        self.balance_label_title.pack(side=LEFT, padx=(0, 5))

        self.balance_label_value = ttk.Label(
            kas_balance_frame, text="N/A", font="-weight bold", bootstyle="info"
        )
        self.balance_label_value.pack(side=LEFT)

        # Row 2: Address Name and Fiat Value
        fiat_balance_frame = ttk.Frame(balance_container)
        fiat_balance_frame.pack(anchor="e")

        self.balance_label_name = ttk.Label(
            fiat_balance_frame,
            text="",
            font="-size 9 -weight bold",
            bootstyle="success",
        )
        self.balance_label_name.pack(side=LEFT, padx=(0, 5))

        self.balance_label_fiat_value = ttk.Label(
            fiat_balance_frame, text="", font="-size 9", bootstyle="secondary"
        )
        self.balance_label_fiat_value.pack(side=LEFT)

        # --- Action Buttons ---
        button_frame = ttk.Frame(container)
        button_frame.grid(row=0, column=3, padx=5, pady=5)

        self.fetch_button = ttk.Button(
            button_frame,
            text=translate("Fetch"),
            command=self._on_load_transactions,
            bootstyle="primary",
        )
        self.fetch_button.pack(side=LEFT, fill=Y, expand=True, padx=(0, 2))

        self.force_fetch_button = ttk.Button(
            button_frame,
            text=translate("Force Fetch"),
            command=lambda: self._on_load_transactions(force=True),
            bootstyle="danger",
        )
        self.force_fetch_button.pack(side=LEFT, fill=Y, expand=True, padx=(0, 5))

        self.explorer_btn = ttk.Button(
            button_frame,
            text=translate("Explorer"),
            command=self._open_in_explorer,
        )
        self.explorer_btn.pack(side=LEFT, fill=Y, expand=True)

        self.cancel_button = ttk.Button(
            container,
            text=translate("Cancel"),
            command=self.transaction_manager.stop_fetch,
            state="disabled",
            bootstyle="secondary",
        )
        self.cancel_button.grid(row=0, column=4, padx=5, pady=5)

        # --- Tooltips ---
        self.fetch_tooltip = ToolTip(self.fetch_button, text=translate("Fetch_Tooltip"))
        self.force_fetch_tooltip = ToolTip(
            self.force_fetch_button, text=translate("Force_Fetch_Tooltip")
        )
        self.cancel_tooltip = ToolTip(
            self.cancel_button, text=translate("Cancel_Tooltip")
        )

    def _on_address_entry_change(self, event: Optional[tk.Event] = None) -> None:
        """Validates the address entry on key release."""
        addr: str = self.address_combo.get().strip()
        if hasattr(self.main_window, "_update_ui_for_address_validity"):
            self.main_window._update_ui_for_address_validity(
                validate_kaspa_address(addr)
            )

    def _open_in_explorer(self) -> None:
        """Opens the currently entered address in the Kaspa explorer."""
        addr: str = self.address_combo.get().strip()
        if validate_kaspa_address(addr):
            active_profile = CONFIG["api"]["profiles"].get(
                CONFIG["api"]["active_profile"], {}
            )
            url_template = active_profile.get("explorer", {}).get("address", "")

            if url_template:
                url = url_template.format(kaspaAddress=addr)
                webbrowser.open(url, new=2)
            else:
                logger.warning("Explorer URL template not found in config.")

    def _on_dropdown_select(self, event: Optional[tk.Event] = None) -> None:
        """
        Handles selection from the address dropdown.
        Clears the results view if a new address is selected.
        """
        choice: str = self.address_combo.get()
        address: str = choice.split(" - ")[1] if " - " in choice else choice
        self.address_combo.set(address)
        self._on_address_entry_change()

        if (
            hasattr(self.main_window, "current_address")
            and self.main_window.current_address
        ):
            if address.lower() == self.main_window.current_address.lower():
                return

        if (
            hasattr(self.main_window, "explorer_tab")
            and address != self.main_window.current_address
        ):
            self.main_window.explorer_tab.results_component.show_placeholder(
                translate("Press 'Fetch' or apply filters.")
            )
            self.main_window.explorer_tab.results_component.current_df = pd.DataFrame()

    def _on_load_transactions(self, force: bool = False) -> None:
        """Initiates the transaction fetch process."""
        address: str = self.address_combo.get().strip()

        if not validate_kaspa_address(address):
            logger.warning("Invalid Kaspa address input.")
            return

        if force and not messagebox.askyesno(
            title=translate("Force_Fetch_Confirm_Title"),
            message=translate("Force_Fetch_Confirm_Msg"),
        ):
            return

        if hasattr(self.main_window, "explorer_tab"):
            self.main_window.explorer_tab.results_component.prepare_for_force_fetch()

        # Auto-save the address if it's new
        all_known_addresses: Set[str] = {
            addr["address"].lower() for addr in self.address_manager.get_all_addresses()
        }

        if address.lower() not in all_known_addresses:
            if self.address_manager.save_address(address, ""):
                logger.info(f"New address auto-saved: {address}")
                self.refresh_address_dropdown(new_address_to_select=address)

                if (
                    hasattr(self.main_window, "settings_tab")
                    and self.main_window.settings_tab.address_tab_initialized
                    and self.main_window.settings_tab.address_tab
                ):
                    self.main_window.settings_tab.address_tab.refresh_address_list()

        # Start the fetch process
        self.main_window.update_address_balance(address)
        filters: Dict[str, Any] = (
            self.main_window.explorer_tab.explorer_filter_controls.get_filters()
        )
        self.transaction_manager.start_fetch(address, force=force, filters=filters)

    def update_balance_display(
        self, balance_kas: Optional[float], address_name: Optional[str]
    ) -> None:
        """Updates the balance labels with new data."""
        if not self.winfo_exists():
            return

        self.balance_label_name.config(text=f"{address_name}" if address_name else "")

        if balance_kas is not None:
            self.balance_label_value.config(text=f"{balance_kas:,.2f} KAS")
            currency_code: str = self.main_window.currency_var.get().lower()
            prices: Dict[str, float] = (
                self.main_window.price_updater.get_current_prices()
            )
            price: float = prices.get(currency_code, 0.0)

            if price > 0:
                fiat_value: float = balance_kas * price
                self.balance_label_fiat_value.config(
                    text=f"({fiat_value:,.2f} {currency_code.upper()})"
                )
            else:
                self.balance_label_fiat_value.config(text="")
        else:
            self.balance_label_value.config(text="N/A")
            self.balance_label_fiat_value.config(text="")

    def refresh_address_dropdown(
        self, new_address_to_select: Optional[str] = None
    ) -> None:
        """Reloads the list of saved addresses into the combobox."""
        try:
            addresses: List[Dict[str, Any]] = self.address_manager.get_all_addresses()
            address_list: List[str] = [
                (
                    f"{addr['name']} - {addr['address']}"
                    if addr.get("name")
                    else addr["address"]
                )
                for addr in addresses
            ]
            placeholder: str = translate("Enter Kaspa Address or Select from Dropdown")
            current_value: str = self.address_combo.get()

            self.address_combo.configure(values=[placeholder] + address_list)

            if new_address_to_select:
                self.address_combo.set(new_address_to_select)
            elif (
                not current_value
                or current_value in _address_placeholders
                or current_value == translate("Error loading addresses")
            ):
                self.address_combo.set(placeholder)

        except Exception as e:
            logger.error(
                f"Failed to refresh address dropdown: {_sanitize_for_logging(e)}",
                exc_info=True,
            )
            self.address_combo.configure(values=[translate("Error loading addresses")])
            self.address_combo.set(translate("Error loading addresses"))

    def set_ui_state(self, is_fetching: bool) -> None:
        """Enables or disables UI elements based on fetch state."""
        state: str = DISABLED if is_fetching else NORMAL
        is_valid_addr: bool = validate_kaspa_address(
            self.address_combo.get().strip()
        )

        try:
            # Disable/Enable Entry and Cancel button
            self.address_combo.configure(state=state)
            self.cancel_button.configure(state=NORMAL if is_fetching else DISABLED)

            # Determine state for Fetch buttons AND Explorer button
            # They should be disabled if fetching OR if address is invalid
            action_btn_state: str = (
                NORMAL if not is_fetching and is_valid_addr else DISABLED
            )

            self.fetch_button.configure(state=action_btn_state)
            self.force_fetch_button.configure(state=action_btn_state)
            self.explorer_btn.configure(state=action_btn_state)

        except tk.TclError:
            pass

    def re_translate(self) -> None:
        """Updates all translatable text in the widget."""
        self.config(text=f" {translate('Load Address')} ")
        self.address_label.config(text=translate("Kaspa Address"))
        self.fetch_button.config(text=translate("Fetch"))
        self.force_fetch_button.config(text=translate("Force Fetch"))
        self.cancel_button.config(text=translate("Cancel"))
        self.balance_label_title.config(text=f"{translate('Balance')}:")
        self.explorer_btn.config(text=translate("Explorer"))

        self.refresh_address_dropdown()

        if hasattr(self, "fetch_tooltip"):
            self.fetch_tooltip.text = translate("Fetch_Tooltip")
            self.force_fetch_tooltip.text = translate("Force_Fetch_Tooltip")
            self.cancel_tooltip.text = translate("Cancel_Tooltip")