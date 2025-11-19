from __future__ import annotations
import logging
import queue
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
import pandas as pd
import ttkbootstrap as ttk
from ttkbootstrap.constants import CENTER, NSEW, NO, YES, VERTICAL, END
from src.config.config import get_active_api_config
from src.utils.i18n import translate

if TYPE_CHECKING:
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)

class Results(ttk.Frame):
    def __init__(self, parent: ttk.Frame, cancel_event: threading.Event, initial_currency: str) -> None:
        super().__init__(parent)
        self.main_window: MainWindow = parent.winfo_toplevel()
        self.current_currency: str = initial_currency.upper()
        self.font_size: int = 8
        self.sort_info: Dict[str, Any] = {"column": "timestamp", "reverse": True}
        self.grand_total_id: str = ""
        self.date_group_ids: Dict[str, str] = {}
        self.after_id_populate: Optional[str] = None
        self._cancel_event: threading.Event = cancel_event
        self.current_df: pd.DataFrame = pd.DataFrame()
        self.tx_db = None 
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=0, column=0, sticky=NSEW)
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)
        
        columns = ("txid", "direction", "amount", "value", "type")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings tree", bootstyle="primary", style="Custom.Treeview")
        self.tree.tag_configure("date_header", font=("-weight", "bold"))
        self.tree.tag_configure("grand_total_row", font=("-weight", "bold"), background="#343a40", foreground="white")
        
        vsb = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self.tree.yview, bootstyle="round")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky=NSEW)
        vsb.grid(row=0, column=1, sticky="ns")
        
        self._configure_headings()
        self.tree.bind("<Double-1>", self._on_double_click)
        self.show_placeholder(translate("Load an address to see transactions."))

    def _configure_headings(self) -> None:
        if not self.tree.winfo_exists(): return
        headings = {"#0": "Date/Time", "txid": "Transaction ID", "direction": "Direction", "amount": "Amount (KAS)", "value": "Value", "type": "Type"}
        for col_id, text_key in headings.items():
            t_text = translate(text_key)
            if col_id == "value": t_text = f"{t_text} ({self.current_currency})"
            self.tree.heading(col_id, text=f"{t_text} ↕", command=lambda c=col_id: self._sort_by_column(c))
        self.tree.column("#0", width=180, stretch=NO, anchor="w")
        self.tree.column("txid", width=480, stretch=YES, anchor="w")

    def _clear_tree(self) -> None:
        if self.after_id_populate:
            self.after_cancel(self.after_id_populate)
            self.after_id_populate = None
        if self.tree.winfo_exists():
            self.tree.delete(*self.tree.get_children())
        self.grand_total_id = ""
        self.date_group_ids = {}

    def show_placeholder(self, message: str) -> None:
        self._clear_tree()
        self.current_df = pd.DataFrame()
        if self.tree.winfo_exists():
            self.tree.insert("", "end", text=message, values=("", "", "", "", ""), tags=("placeholder",))

    def update_font_size(self, size: int) -> None:
        # RESTORED: Logic to actually apply font size
        if not self.tree.winfo_exists(): return
        self.font_size = size
        style = self.main_window.style
        row_h = size + 14
        style.configure("Custom.Treeview", font=("DejaVu Sans", size), rowheight=row_h)
        style.configure("Custom.Treeview.Heading", font=("DejaVu Sans", size, "bold"))
        self.tree.tag_configure("date_header", font=("DejaVu Sans", size, "bold"))
        self.tree.tag_configure("grand_total_row", font=("DejaVu Sans", size, "bold"), background="#343a40", foreground="white")
        self.tree.configure(style="Custom.Treeview")

    def display_data(self, df: pd.DataFrame, currency: str) -> None:
        if not self.winfo_exists() or not self.tree.winfo_exists(): return
        
        self.tree.grid_remove()
        self._clear_tree()
        self.current_df = df.copy()
        self.current_currency = currency.upper()

        if self.current_df.empty:
            self.show_placeholder(translate("No transactions match the current criteria."))
            self.tree.grid(row=0, column=0, sticky=NSEW)
            return

        try:
            val_key = f"value_{self.current_currency.lower()}"
            if val_key not in self.current_df.columns:
                prices = self.main_window.price_updater.get_current_prices()
                self.current_df[val_key] = self.current_df["amount"] * prices.get(self.current_currency.lower(), 0.0)

            if "timestamp" in self.current_df.columns:
                self.current_df["date"] = pd.to_datetime(self.current_df["timestamp"], unit="s").dt.date
                self.current_df.sort_values(by=["date", "timestamp"], ascending=[False, False], inplace=True)

            data = self.current_df.to_dict("records")
            
            total_kas = self.current_df["amount"].sum()
            total_val = self.current_df[val_key].sum()
            
            self.grand_total_id = self.tree.insert(
                "", 0, text=translate("Grand Total"),
                values=(f"{len(self.current_df)} {translate('TXs')}", "", f"{total_kas:,.2f}", f"{total_val:,.2f} {self.current_currency}", ""),
                tags=("grand_total_row",)
            )

            for item in data:
                if "date" not in item: continue
                d_str = item["date"].strftime("%Y-%m-%d")
                
                if d_str not in self.date_group_ids:
                    grp = self.current_df[self.current_df["date"] == item["date"]]
                    g_kas = grp["amount"].sum()
                    g_val = grp[val_key].sum()
                    did = self.tree.insert("", "end", text=d_str, values=(f"{len(grp)} {translate('TXs')}", "", f"{g_kas:,.2f}", f"{g_val:,.2f}", ""), open=False, tags=("date_header",))
                    self.date_group_ids[d_str] = did
                
                ts = item.get("timestamp", 0)
                t_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
                self.tree.insert(
                    self.date_group_ids[d_str], END, text=t_str,
                    values=(item["txid"], item["direction"], f"{item['amount']:,.2f}", f"{item[val_key]:,.2f}", item["type"]),
                    tags=(item["txid"],)
                )

        except Exception as e:
            logger.error(f"Display Error: {e}", exc_info=True)
            self.show_placeholder(f"Error: {e}")
        
        self.tree.grid(row=0, column=0, sticky=NSEW)

    def append_transactions(self, new_df: pd.DataFrame) -> None:
        if new_df.empty: return
        if self.current_df.empty:
            self.display_data(new_df, self.current_currency)
        else:
            combined = pd.concat([self.current_df, new_df]).drop_duplicates(subset="txid")
            self.display_data(combined, self.current_currency)

    # Stubs
    def re_translate(self): pass
    def _on_double_click(self, e): pass
    def _sort_by_column(self, c): pass
    def has_data(self): return not self.current_df.empty
    def get_current_view_data_as_df(self): return self.current_df
    def update_currency_display(self, c): self.display_data(self.current_df, c)
    def prepare_for_force_fetch(self): self.show_placeholder(translate("Fetching new data..."))
    def start_ui_update_loop(self, q): 
        self.after_id_populate = self.after(100, self._process_queue, q)
    def stop_ui_update_loop(self, q):
        if self.after_id_populate: self.after_cancel(self.after_id_populate)
        self._process_queue(q)
    def _process_queue(self, q):
        try:
            dfs = []
            while not q.empty(): dfs.append(q.get_nowait()); q.task_done()
            if dfs: self.append_transactions(pd.concat(dfs))
            self.after_id_populate = self.after(200, self._process_queue, q)
        except: pass
