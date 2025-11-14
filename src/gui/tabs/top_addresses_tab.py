from __future__ import annotations
import ttkbootstrap as ttk
import logging
import threading
import time
import webbrowser
import os
import pandas as pd
from tkinter import filedialog, messagebox
import tkinter as tk
from ttkbootstrap.constants import *
from ttkbootstrap.toast import ToastNotification
from ttkbootstrap.tooltip import ToolTip
from src.utils.i18n import translate
from src.api.network import fetch_top_addresses
from src.config.config import CONFIG, get_active_api_config
from datetime import datetime
from src.gui.components.export import ExportComponent
from src.export import export_top_addresses_to_csv, export_top_addresses_to_html, export_top_addresses_to_pdf
from typing import Optional, Dict, Any, List, Callable, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


class TopAddressesTab(ttk.Frame):
    """
    View/Controller for the "Top Addresses" tab.
    Handles fetching, displaying, filtering, and exporting the list of
    top Kaspa addresses by balance.
    """

    # --- Type Hint Declarations ---
    main_window: 'MainWindow'
    _thread: Optional[threading.Thread]
    _stop_event: threading.Event
    full_df: pd.DataFrame
    sort_info: Dict[str, Any]
    placeholder_active: bool
    is_active: bool
    last_updated_label: ttk.Label
    save_hint_tooltip: ToolTip
    refresh_button: ttk.Button
    export_component: ExportComponent
    search_entry: ttk.Entry
    search_button: ttk.Button
    reset_button: ttk.Button
    tree: ttk.Treeview
    context_menu: tk.Menu
    # --- End Type Hint Declarations ---

    def __init__(self, parent: ttk.Frame, main_window: 'MainWindow') -> None:
        super().__init__(parent, padding=10)
        self.main_window: 'MainWindow' = main_window
        self.pack(fill=BOTH, expand=True)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.full_df = pd.DataFrame()
        self.sort_info: Dict[str, Any] = {'column': 'Rank', 'reverse': False}
        self.placeholder_active: bool = False
        self.is_active: bool = False
        self._build_ui()

    def activate(self) -> None:
        """Called when the tab becomes visible."""
        if not self.is_active:
            logger.info("Top Addresses tab activated.")
            self.is_active = True
            if self.full_df.empty:
                self.refresh_data()

    def deactivate(self) -> None:
        """Called when the tab is hidden."""
        logger.debug("Top Addresses tab deactivated.")
        self.is_active = False

    def _build_ui(self) -> None:
        """Constructs all UI components for the tab."""
        header_frame = ttk.Frame(self)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header_frame.grid_columnconfigure(1, weight=1)

        self.last_updated_label = ttk.Label(header_frame, text=f"{translate('Last Updated')}: N/A")
        self.last_updated_label.pack(side=LEFT)

        hint_label = ttk.Label(header_frame, text="💡", bootstyle="secondary")
        hint_label.pack(side=LEFT, padx=(10, 0))
        self.save_hint_tooltip = ToolTip(hint_label, text=translate("Right-click an address to add it to 'My Addresses'."))

        button_frame = ttk.Frame(header_frame)
        button_frame.pack(side=RIGHT)

        self.refresh_button = ttk.Button(button_frame, text=translate("Refresh List"), command=self.refresh_data)
        self.refresh_button.pack(side=LEFT)

        self.export_component = ExportComponent(button_frame, self.export_data)
        self.export_component.pack(side=LEFT, padx=(10, 0))

        filter_frame = ttk.Frame(self)
        filter_frame.grid(row=1, column=0, sticky="ew", pady=5)
        filter_frame.grid_columnconfigure(0, weight=1)

        self.search_entry = ttk.Entry(filter_frame)
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self._bind_events()
        self._setup_placeholder()

        self.search_button = ttk.Button(filter_frame, text=translate("Filter"), command=self._apply_filters_and_sort)
        self.search_button.grid(row=0, column=1, padx=(0, 5))

        self.reset_button = ttk.Button(filter_frame, text=translate("Reset Filter"), command=self._reset_filters)
        self.reset_button.grid(row=0, column=2)

        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=2, column=0, sticky="nsew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        columns: Tuple[str, ...] = ("rank", "name", "address", "balance", "value")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", bootstyle="primary")
        vsb = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.context_menu = tk.Menu(self, tearoff=0)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._show_context_menu)

        self.re_translate()

    def _show_context_menu(self, event: tk.Event) -> None:
        """Displays the right-click context menu."""
        item_id: str = self.tree.identify_row(event.y)
        if item_id:
            self.tree.selection_set(item_id)
            self.context_menu.post(event.x_root, event.y_root)

    def _add_selected_to_my_addresses(self) -> None:
        """Saves the selected address to the user's address book."""
        sel: Tuple[str, ...] = self.tree.selection()
        if not sel:
            return

        item: Dict[str, Any] = self.tree.item(sel[0])
        values: List[str] = item['values']
        if len(values) < 3:
            return

        known_name: str = values[1]
        address: str = values[2]

        if self.main_window.address_manager.save_address(address, known_name):
            ToastNotification(title=translate("Address Saved"), message=f"{address[:15]}... {translate('Add to My Addresses')}", bootstyle=SUCCESS, duration=3000).show_toast()

            if hasattr(self.main_window, 'settings_tab') and self.main_window.settings_tab.address_tab_initialized and self.main_window.settings_tab.address_tab:
                self.main_window.settings_tab.address_tab.refresh_address_list()

            if hasattr(self.main_window, 'explorer_tab'):
                self.main_window.explorer_tab.input_component.refresh_address_dropdown()
        else:
            ToastNotification(title=translate("Error"), message=translate("Failed to save address."), bootstyle=DANGER, duration=3000).show_toast()

    def _copy_selected_address(self) -> None:
        """Copies the selected address to the clipboard."""
        sel: Tuple[str, ...] = self.tree.selection()
        if not sel:
            return

        address: str = self.tree.item(sel[0], "values")[2]
        self.clipboard_clear()
        self.clipboard_append(address)
        ToastNotification(title=translate("Copy Address"), message=f"{address[:20]}... {translate('copied to clipboard.')}", bootstyle=INFO, duration=3000).show_toast()

    def _on_double_click(self, event: tk.Event) -> None:
        """Opens the selected address in the block explorer."""
        sel: Tuple[str, ...] = self.tree.selection()
        if not sel:
            return

        address: str = self.tree.item(sel[0], "values")[2]
        url: str = get_active_api_config()['explorer']['address'].format(kaspaAddress=address)
        webbrowser.open(url, new=2)

    def stop(self) -> None:
        """Signals the fetching thread to stop."""
        self._stop_event.set()

    def refresh_data(self) -> None:
        """Initiates a background thread to fetch top addresses."""
        if self._thread and self._thread.is_alive():
            logger.warning("Refresh already in progress.")
            return

        self.show_placeholder(translate("Loading..."))
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._fetch_worker, daemon=True, name="TopAddressesThread")
        self._thread.start()

    def _fetch_worker(self) -> None:
        """Background worker to fetch and process top addresses."""
        try:
            self.main_window.address_names_loaded.wait(timeout=10)
            if self._stop_event.is_set():
                return

            raw_data: Optional[List[Any]] = fetch_top_addresses()
            if self._stop_event.is_set():
                return

            address_list: List[Dict[str, Any]] = []
            if isinstance(raw_data, list) and len(raw_data) > 0 and 'ranking' in raw_data[0]:
                address_list = raw_data[0].get('ranking', [])
            elif isinstance(raw_data, list):
                address_list = raw_data

            if isinstance(address_list, list):
                df_data: List[Dict[str, Any]] = [{
                    "Rank": item.get('rank', i) + 1,
                    "Known Name": self.main_window.address_names_map.get(item.get('address'), ''),
                    "Address": item.get('address', 'N/A'),
                    "Balance": float(item.get('amount', 0))
                } for i, item in enumerate(address_list)]
                self.full_df = pd.DataFrame(df_data)
            else:
                self.full_df = pd.DataFrame()

        except Exception as e:
            logger.error(f"Failed to fetch or process top addresses: {e}")
            self.full_df = pd.DataFrame()
        finally:
            if self.winfo_exists():
                self.after(0, self._apply_filters_and_sort)

    def _apply_filters_and_sort(self) -> None:
        """Applies current filters and sorting to the full_df and updates the tree."""
        self._clear_tree()
        df = self.full_df.copy()

        search_term: str = self.search_entry.get().strip().lower()
        if search_term and not self.placeholder_active and not df.empty:
            df = df[df.apply(lambda row:
                search_term in str(row['Address']).lower() or
                search_term in str(row['Known Name']).lower() or
                search_term == str(row['Rank']),
                axis=1
            )]

        if not df.empty:
            currency_code: str = self.main_window.currency_var.get().upper()
            price: float = self.main_window.price_updater.get_current_prices().get(currency_code.lower(), 0.0)
            df['Value'] = df['Balance'] * price
            df['Balance_float'] = df['Balance']

            sort_key: str = self.sort_info['column']
            if sort_key in ['Balance', 'Value', 'Rank']:
                sort_col: str = 'Balance_float' if sort_key == 'Balance' else sort_key
                df = df.sort_values(by=sort_col, ascending=not self.sort_info['reverse'])
            else:
                df = df.sort_values(by=sort_key, ascending=not self.sort_info['reverse'], key=lambda col: col.astype(str).str.lower())

            for _, row in df.iterrows():
                self.tree.insert("", "end", iid=row['Rank'], values=(
                    row['Rank'],
                    row['Known Name'],
                    row['Address'],
                    f"{row['Balance']:,.2f}",
                    f"{row['Value']:,.2f} {currency_code}"
                ))
            self.last_updated_label.config(text=f"{translate('Last Updated')}: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            self.show_placeholder(translate("No data to display."))

        self.export_component.set_ui_state(not df.empty)

    def _reset_filters(self) -> None:
        """Clears the search entry and re-applies filters."""
        self.search_entry.delete(0, END)
        self._on_focus_out(None)
        self._apply_filters_and_sort()

    def _sort_by_column(self, col_id: str) -> None:
        """Handles tree column header clicks for sorting."""
        sort_map: Dict[str, str] = {
            "rank": "Rank",
            "name": "Known Name",
            "address": "Address",
            "balance": "Balance",
            "value": "Value"
        }
        sort_key: Optional[str] = sort_map.get(col_id)

        if not sort_key:
            return

        if self.sort_info['column'] == sort_key:
            self.sort_info['reverse'] = not self.sort_info['reverse']
        else:
            self.sort_info['column'] = sort_key
            self.sort_info['reverse'] = sort_key in ["Balance", "Value", "Rank"]

        self._apply_filters_and_sort()

    def update_currency_display(self, new_currency: str) -> None:
        """Updates the 'Value' column when the global currency changes."""
        self._configure_tree_headings()
        if self.full_df.empty:
            return

        price: float = self.main_window.price_updater.get_current_prices().get(new_currency.lower(), 0.0)

        for item_id in self.tree.get_children():
            values: Tuple[str, ...] = self.tree.item(item_id, 'values')
            try:
                balance_str: str = str(values[3]).replace(",", "")
                if balance_str:
                    balance: float = float(balance_str)
                    new_value: float = balance * price
                    self.tree.set(item_id, column="value", value=f"{new_value:,.2f} {new_currency.upper()}")
            except (ValueError, IndexError, TypeError):
                continue

    def _configure_tree_headings(self) -> None:
        """Sets or updates the treeview column headings with translations."""
        currency_code: str = self.main_window.currency_var.get().upper()
        headings: Dict[str, str] = {
            "rank": "Rank",
            "name": "Known Name",
            "address": "Address",
            "balance": "Balance (KAS)",
            "value": f"Value ({currency_code})"
        }
        for col_id, text_key in headings.items():
            translated_text: str = translate(text_key)
            self.tree.heading(col_id, text=f"{translated_text} ↕", command=lambda c=col_id: self._sort_by_column(c))

        self.tree.column("rank", width=80, stretch=NO, anchor='center')
        self.tree.column("name", width=200, stretch=NO)
        self.tree.column("address", width=500, stretch=YES)
        self.tree.column("balance", width=180, anchor='e', stretch=NO)
        self.tree.column("value", width=150, anchor='e', stretch=NO)

    def re_translate(self) -> None:
        """Reloads all translatable text in the tab."""
        current_text: str = self.last_updated_label.cget("text")
        if ":" in current_text:
            self.last_updated_label.config(text=f"{translate('Last Updated')}:{current_text.split(':', 1)[1]}")
        else:
            self.last_updated_label.config(text=f"{translate('Last Updated')}: N/A")

        self.refresh_button.config(text=translate("Refresh List"))
        self.search_button.config(text=translate("Filter"))
        self.reset_button.config(text=translate("Reset Filter"))
        self.save_hint_tooltip.text = translate("Right-click an address to add it to 'My Addresses'.")
        self._configure_tree_headings()

        self.context_menu.delete(0, END)
        self.context_menu.add_command(label=translate("Add to My Addresses"), command=self._add_selected_to_my_addresses)
        self.context_menu.add_command(label=translate("Copy Address"), command=self._copy_selected_address)

        
        current_state: str = self.search_entry.cget("state")
        if self.placeholder_active:
            self.search_entry.delete(0, "end")
        self._setup_placeholder()
        self.search_entry.config(state=current_state)
        self.export_component.re_translate()

        if self.full_df.empty:
            self.show_placeholder(translate("Press 'Refresh List' to load top addresses."))

    def _setup_placeholder(self) -> None:
        """Sets or resets the placeholder text in the search entry."""
        self.placeholder: str = translate("Search by Rank, Name, or Address...")
        self.placeholder_color: str = 'grey'
        self.default_fg_color: str = self.search_entry.cget("foreground")
        if not self.search_entry.get() or self.placeholder_active:
            self.search_entry.delete(0, "end")
            self.search_entry.insert(0, self.placeholder)
            self.search_entry.config(foreground=self.placeholder_color)
            self.placeholder_active = True

    def _bind_events(self) -> None:
        """Binds focus events to the search entry for placeholder handling."""
        self.search_entry.bind('<FocusIn>', self._on_focus_in)
        self.search_entry.bind('<FocusOut>', self._on_focus_out)

    def _on_focus_in(self, event: tk.Event) -> None:
        """Removes placeholder text on focus."""
        if self.placeholder_active:
            self.placeholder_active = False
            self.search_entry.delete(0, "end")
            self.search_entry.config(foreground=self.default_fg_color)

    def _on_focus_out(self, event: Optional[tk.Event]) -> None:
        """Restores placeholder text if entry is empty."""
        if not self.search_entry.get():
            self._setup_placeholder()

    def _clear_tree(self) -> None:
        """Removes all items from the treeview."""
        if self.tree.winfo_exists():
            self.tree.delete(*self.tree.get_children())

    def show_placeholder(self, message: str) -> None:
        """Clears the tree and displays a placeholder message."""
        self._clear_tree()
        self.tree.insert("", "end", values=("", "", message, "", ""), tags=('placeholder',))

    def export_data(self, export_format: str) -> None:
        """Initiates the data export process."""
        if self.full_df.empty:
            ToastNotification(title=translate("Export Results:"), message=translate("No data to export."), bootstyle=WARNING, duration=3000).show_toast()
            return

        ts: str = datetime.now().strftime('%Y%m%d_%H%M%S')
        initial_filename: str = f"kaspa_top_addresses_{ts}.{export_format}"
        export_dir: str = CONFIG.get('paths', {}).get('export', '.')
        os.makedirs(export_dir, exist_ok=True)

        file_path: Optional[str] = filedialog.asksaveasfilename(
            initialfile=initial_filename,
            defaultextension=f".{export_format}",
            filetypes=[(f"{export_format.upper()} files", f"*.{export_format}")],
            title=f"{translate('Save as')} {export_format.upper()}",
            initialdir=export_dir
        )
        if not file_path:
            return

        self.main_window.status.update_status(f"Exporting to {export_format.upper()}...")
        df_to_export = self.full_df.copy()
        price: float = self.main_window.price_updater.get_current_prices().get(self.main_window.currency_var.get().lower(), 0.0)
        df_to_export['Value'] = df_to_export['Balance'] * price

        export_args: Dict[str, Any] = {
            "df": df_to_export,
            "file_path": file_path,
            "currency": self.main_window.currency_var.get(),
        }

        threading.Thread(target=self._export_worker, args=(export_format, export_args), daemon=True).start()

    def _export_worker(self, export_format: str, export_args: Dict[str, Any]) -> None:
        """Background thread to handle the file I/O for exporting."""
        logger.info(f"Exporting top addresses to {export_format.upper()} at {export_args['file_path']}")
        try:
            export_map: Dict[str, Callable[..., Tuple[bool, str, str]]] = {
                'csv': export_top_addresses_to_csv,
                'html': export_top_addresses_to_html,
                'pdf': export_top_addresses_to_pdf
            }
            export_func: Optional[Callable[..., Tuple[bool, str, str]]] = export_map.get(export_format)

            if not export_func:
                raise ValueError(f"No export function found for format: {export_format}")

            success, msg_key, details = export_func(**export_args)
            final_msg: str = f"{translate(msg_key)}: {details}" if details else translate(msg_key)

            if self.winfo_exists():
                if success:
                    logger.info(f"Export successful. File saved to {export_args['file_path']}")
                    self.main_window.after(100, self.main_window.prompt_to_open_file, export_args["file_path"], final_msg)
                else:
                    self.main_window.after(0, lambda: messagebox.showerror(translate("Error"), final_msg))

        except Exception as e:
            logger.error(f"Export worker failed for top addresses: {e}", exc_info=True)
            if self.winfo_exists():
                self.main_window.after(0, lambda: ToastNotification(title=translate("Error"), message=translate("Check logs for details."), bootstyle=DANGER, duration=3000).show_toast())
        finally:
            if self.winfo_exists():
                self.main_window.after(0, self.main_window.status.update_status, "Ready")