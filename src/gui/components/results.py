from __future__ import annotations
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import pandas as pd
import logging
import webbrowser
import threading
import queue
from typing import List, Dict, Any, TYPE_CHECKING, Optional, Set, Tuple
from datetime import datetime, date
import tkinter as tk

from src.utils.i18n import translate, get_all_translations_for_key
from src.config.config import get_active_api_config
from ttkbootstrap.toast import ToastNotification

if TYPE_CHECKING:
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


class Results(ttk.Frame):
    """
    Manages the Treeview component for displaying transaction results.
    Handles sorting, filtering, and progressive UI updates by querying the DB.
    """
    # --- Class Attribute Type Declarations ---
    main_window: 'MainWindow'
    current_currency: str
    font_size: int
    sort_info: Dict[str, Any]
    grand_total_id: str
    date_group_ids: Dict[str, str]
    after_id_populate: Optional[str]
    _cancel_event: threading.Event
    current_df: pd.DataFrame  # Holds only the *displayed* data, not all data
    tree: ttk.Treeview
    # --- End Attribute Declarations ---

    def __init__(
        self,
        parent: ttk.Frame,
        cancel_event: threading.Event,
        initial_currency: str
    ) -> None:
        super().__init__(parent)
        self.main_window = self.winfo_toplevel()  # type: ignore
        self.current_currency = initial_currency.upper()
        self.font_size = 8
        self.sort_info = {"column": "timestamp", "reverse": True}
        self.grand_total_id = ""
        self.date_group_ids = {}
        self.after_id_populate = None
        self._cancel_event = cancel_event
        self.current_df = pd.DataFrame()  # Only stores displayed data

        self._build_ui()

    def _build_ui(self) -> None:
        """Constructs the Treeview and scrollbars."""
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=0, column=0, sticky="nsew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        columns: Tuple[str, ...] = ("txid", "direction", "amount", "value", "type")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings tree",
            bootstyle="primary",
            style="Custom.Treeview"
        )
        self.tree.tag_configure('date_header', font=('-weight', 'bold'))
        self.tree.tag_configure(
            'grand_total_row',
            font=('-weight', 'bold'),
            background='#343a40',
            foreground='white'
        )

        vsb = ttk.Scrollbar(
            tree_frame,
            orient=VERTICAL,
            command=self.tree.yview,
            bootstyle="round"
        )
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self._configure_headings()
        self.tree.bind("<Double-1>", self._on_double_click)
        self.show_placeholder(translate("Load an address to see transactions."))

    def _configure_headings(self) -> None:
        """Sets or updates the Treeview column headings."""
        headings: Dict[str, str] = {
            "#0": "Date/Time",
            "txid": "Transaction ID",
            "direction": "Direction",
            "amount": "Amount (KAS)",
            "value": "Value",
            "type": "Type"
        }
        for col_id, text_key in headings.items():
            translated_text: str = translate(text_key)
            if col_id == "value":
                translated_text = f"{translated_text} ({self.current_currency})"

            self.tree.heading(
                col_id,
                text=f"{translated_text} ↕",
                command=lambda c=col_id: self._sort_by_column(c)
            )

        self.tree.column("#0", width=180, stretch=NO, anchor='w')
        self.tree.column("txid", width=480, stretch=YES, anchor='w')
        self.tree.column("direction", width=100, anchor="center", stretch=NO)
        self.tree.column("amount", width=150, anchor="e", stretch=NO)
        self.tree.column("value", width=150, anchor="e", stretch=NO)
        self.tree.column("type", width=100, anchor="center", stretch=NO)

    def re_translate(self) -> None:
        """Reloads all translatable text in the widget."""
        self._configure_headings()

        if self.current_df.empty:
            # Re-apply placeholder text if it's currently empty
            # Check if there's a placeholder tag
            children = self.tree.get_children()
            if children and 'placeholder' in self.tree.item(children[0], 'tags'):
                if self.main_window.current_address:
                    # Check if it's the "fetching" message
                    current_text = self.tree.item(children[0], 'text')
                    if current_text == translate("Fetching new data..."):
                         self.show_placeholder(translate("Fetching new data..."))
                    else:
                        self.show_placeholder(translate("Press 'Fetch' or apply filters."))
                else:
                    self.show_placeholder(translate("Load an address to see transactions."))
            return

        if self.grand_total_id and self.tree.exists(self.grand_total_id):
            current_values: Tuple[Any, ...] = self.tree.item(self.grand_total_id, 'values')
            self.tree.item(
                self.grand_total_id,
                text=translate("Grand Total"),
                values=(
                    f"{len(self.current_df)} {translate('TXs')}",
                    current_values[1],
                    current_values[2],
                    current_values[3],
                    current_values[4]
                )
            )

        for date_id in self.date_group_ids.values():
            if self.tree.exists(date_id):
                current_values = self.tree.item(date_id, 'values')
                num_txs: str = str(current_values[0]).split(' ')[0]
                self.tree.item(
                    date_id,
                    values=(
                        f"{num_txs} {translate('TXs')}",
                        current_values[1],
                        current_values[2],
                        current_values[3],
                        current_values[4]
                    )
                )

        for item_id in self.tree.get_children(''):
            for child_id in self.tree.get_children(item_id):
                if not self.tree.exists(child_id):
                    continue
                try:
                    row: pd.DataFrame = self.current_df.loc[self.current_df['txid'] == child_id]
                    if not row.empty:
                        item: pd.Series = row.iloc[0]
                        current_values = self.tree.item(child_id, 'values')
                        new_values: List[Any] = list(current_values)
                        new_values[1] = translate(str(item.get('direction', 'N/A')).capitalize())
                        new_values[4] = translate(str(item.get('type', 'N/A')).capitalize())
                        self.tree.item(child_id, values=new_values)
                except KeyError:
                    logger.warning(f"KeyError looking up txid {child_id} in current_df during re_translate")
                except Exception as e:
                    logger.error(f"Error re-translating row {child_id}: {e}")

    def _clear_tree(self) -> None:
        """Clears all items from the tree and resets state."""
        if self.after_id_populate:
            self.after_cancel(self.after_id_populate)
            self.after_id_populate = None
        if self.tree.winfo_exists():
            self.tree.delete(*self.tree.get_children())
        self.grand_total_id = ""
        self.date_group_ids = {}

    def show_placeholder(self, message: str) -> None:
        """Clears the tree and displays a placeholder message."""
        self._clear_tree()
        self.current_df = pd.DataFrame()
        self.tree.insert("", "end", text=message, values=("", "", "", "", ""), tags=('placeholder',))

    def _on_double_click(self, event: Any) -> None:
        """Handles double-click events to open the explorer."""
        item_id: str = self.tree.identify_row(event.y)
        if not item_id or any(tag in self.tree.item(item_id, 'tags') for tag in ['date_header', 'grand_total_row', 'placeholder']):
            return

        try:
            txid: str = self.tree.item(item_id, "values")[0]
            if txid:
                url_template: str = get_active_api_config().get('explorer', {}).get('transaction', '')
                if url_template:
                    url: str = url_template.replace("{txid}", txid)
                    webbrowser.open(url, new=2)
                else:
                    logger.warning("Explorer transaction URL template not found in config.")
        except IndexError:
            logger.warning(f"Could not get txid from double-clicked item: {item_id}")

    def _sort_by_column(self, col_id: str) -> None:
        """Sorts the displayed data by the selected column."""
        if self.current_df.empty:
            return

        sort_map: Dict[str, str] = {
            "#0": "timestamp",
            "txid": "txid",
            "direction": "direction",
            "amount": "amount",
            "value": f"value_{self.current_currency.lower()}",
            "type": "type"
        }
        sort_key: Optional[str] = sort_map.get(col_id)
        if not sort_key:
            return

        if self.sort_info["column"] == sort_key:
            self.sort_info["reverse"] = not self.sort_info["reverse"]
        else:
            self.sort_info["column"] = sort_key
            self.sort_info["reverse"] = sort_key in ["timestamp", "amount", f"value_{self.current_currency.lower()}"]

        # Re-display the *current* filtered data, but sorted
        self.display_data(self.current_df, self.current_currency)

    def has_data(self) -> bool:
        """Checks if the component is holding any data."""
        return not self.current_df.empty

    def get_current_view_data_as_df(self) -> pd.DataFrame:
        """Returns the underlying DataFrame currently displayed."""
        return self.current_df

    def update_font_size(self, size: int) -> None:
        """Applies a new font size to the Treeview."""
        self.font_size = size
        style: ttk.Style = self.main_window.style
        style.configure("Custom.Treeview", rowheight=size + 14, font=("DejaVu Sans", size))
        style.configure("Custom.Treeview.Heading", font=("DejaVu Sans", size, 'bold'))
        self.tree.tag_configure('date_header', font=("DejaVu Sans", size, 'bold'))
        self.tree.tag_configure(
            'grand_total_row',
            font=("DejaVu Sans", size, 'bold'),
            background='#343a40',
            foreground='white'
        )
        self.tree.configure(style="Custom.Treeview")

    def update_currency_display(self, new_currency: str) -> None:
        """Updates all visible currency values when the user changes currency."""
        self.current_currency = new_currency.upper()
        self._configure_headings()
        if self.current_df.empty:
            return

        prices: Dict[str, float] = self.main_window.price_updater.get_current_prices()
        price: float = prices.get(new_currency.lower(), 0.0)
        value_col_key: str = f"value_{new_currency.lower()}"
        
        if 'amount' in self.current_df.columns:
            self.current_df[value_col_key] = self.current_df['amount'] * price
        else:
            logger.warning("Cannot update currency display, 'amount' column missing from current_df.")
            return

        total_value: float = self.current_df[value_col_key].sum()
        if self.grand_total_id and self.tree.exists(self.grand_total_id):
            self.tree.set(self.grand_total_id, column="value", value=f"{total_value:,.2f} {new_currency.upper()}")

        for date_str, date_id in self.date_group_ids.items():
            if self.tree.exists(date_id):
                try:
                    date_obj: date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    if 'date' in self.current_df.columns:
                        daily_value: float = self.current_df[self.current_df['date'] == date_obj][value_col_key].sum()
                        self.tree.set(date_id, column="value", value=f"{daily_value:,.2f} {new_currency.upper()}")
                except (ValueError, KeyError):
                    continue  # Skip if data is malformed

        for child_id in self.current_df['txid']:
            if self.tree.exists(child_id):
                try:
                    item_value: float = self.current_df.loc[self.current_df['txid'] == child_id, value_col_key].iloc[0]
                    self.tree.set(
                        child_id,
                        column="value",
                        value=f"{item_value:,.2f} {new_currency.upper()}" if pd.notnull(item_value) else "N/A"
                    )
                except (IndexError, KeyError):
                    continue  # Skip if row not found

    def prepare_for_force_fetch(self) -> None:
        """Clears the tree and displays a 'fetching' placeholder."""
        # show_placeholder already calls _clear_tree() and resets the df
        self.show_placeholder(translate("Fetching new data..."))

    def display_data(
        self,
        df: pd.DataFrame,
        currency: str,
        on_complete_event: Optional[threading.Event] = None
    ) -> None:
        """
        Clears and repopulates the tree with a new, *already filtered* DataFrame.
        This is the primary method for displaying a set of data.
        """
        if not self.winfo_exists():
            if on_complete_event:
                on_complete_event.set()
            return

        self.tree.update_idletasks()
        self.tree.grid_remove()
        self._clear_tree()
        self.current_df = df.copy()  # Store only the displayed data
        self.current_currency = currency.upper()

        if self.current_df.empty:
            self.show_placeholder(translate("No transactions match the current criteria."))
            if on_complete_event:
                on_complete_event.set()
            self.tree.grid(row=0, column=0, sticky="nsew")
            return

        value_col_key: str = f"value_{self.current_currency.lower()}"
        if value_col_key not in self.current_df.columns:
            price: float = self.main_window.price_updater.get_current_prices().get(self.current_currency.lower(), 0.0)
            self.current_df[value_col_key] = self.current_df['amount'] * price

        total_kas: float = self.current_df['amount'].sum()
        total_value: float = self.current_df[value_col_key].sum()
        self.grand_total_id = self.tree.insert(
            "",
            0,
            text=translate("Grand Total"),
            values=(
                f"{len(self.current_df)} {translate('TXs')}",
                "",
                f"{total_kas:,.2f}",
                f"{total_value:,.2f} {self.current_currency.upper()}",
                ""
            ),
            tags=('grand_total_row',)
        )

        if 'timestamp' in self.current_df.columns:
            self.current_df['date'] = pd.to_datetime(self.current_df['timestamp'], unit='s').dt.date
            sorted_df = self.current_df.sort_values(
                by=['date', self.sort_info['column']],
                ascending=[False, not self.sort_info['reverse']]
            )
        else:
            sorted_df = self.current_df

        data_to_display: List[Dict[str, Any]] = sorted_df.to_dict('records')
        for item in data_to_display:
            try:
                if 'date' not in item or not isinstance(item['date'], date):
                    continue
                
                date_str: str = item['date'].strftime('%Y-%m-%d')
                if date_str not in self.date_group_ids:
                    daily_df: pd.DataFrame = self.current_df[self.current_df['date'] == item['date']]
                    daily_kas: float = daily_df['amount'].sum()
                    daily_value: float = daily_df[value_col_key].sum() if value_col_key in daily_df else 0.0
                    date_id: str = self.tree.insert(
                        "",
                        "end",
                        text=date_str,
                        values=(
                            f"{len(daily_df)} {translate('TXs')}",
                            "",
                            f"{daily_kas:,.2f}",
                            f"{daily_value:,.2f} {self.current_currency.upper()}",
                            ""
                        ),
                        open=False,
                        tags=('date_header',)
                    )
                    self.date_group_ids[date_str] = date_id

                parent_id: str = self.date_group_ids[date_str]
                item_timestamp = item.get('timestamp', 0)
                item_time_str = datetime.fromtimestamp(item_timestamp).strftime('%H:%M:%S')
                
                self.tree.insert(
                    parent=parent_id,
                    index=END,
                    iid=item['txid'],
                    text=item_time_str,
                    values=(
                        item['txid'],
                        translate(str(item.get('direction', 'N/A')).capitalize()),
                        f"{item.get('amount', 0):,.2f}",
                        f"{item.get(value_col_key, 0.0):,.2f} {self.current_currency.upper()}"
                        if item.get(value_col_key) is not None else "N/A",
                        translate(str(item.get('type', 'N/A')).capitalize())
                    ),
                    tags=(item['txid'],)
                )
            except Exception as e:
                logger.warning(f"Failed to display transaction item {item.get('txid')}: {e}")

        self.tree.grid(row=0, column=0, sticky="nsew")
        if on_complete_event:
            on_complete_event.set()

    def append_transactions(self, new_txs_df: pd.DataFrame) -> None:
        """
        Appends a new DataFrame chunk to the *existing* data and incrementally
        updates the treeview. Assumes the tree is *not* empty and display_data
        has already been called for the first chunk.
        """
        if new_txs_df.empty or not self.winfo_exists():
            return

        # 1. Update the underlying dataframe
        existing_txids = set(self.current_df['txid'])
        new_txs_df = new_txs_df[~new_txs_df['txid'].isin(existing_txids)]
        if new_txs_df.empty:
            logger.debug("append_transactions received only duplicate txids, skipping UI update.")
            return

        # *** FIX 1: Add 'date' column to new_txs_df *before* concat
        if 'timestamp' in new_txs_df.columns:
            new_txs_df.loc[:, 'date'] = pd.to_datetime(new_txs_df['timestamp'], unit='s').dt.date
        else:
            logger.error("New transaction chunk missing 'timestamp' column, cannot append.")
            return

        self.current_df = pd.concat(
            [self.current_df, new_txs_df]
        ).reset_index(drop=True)
        
        # *** (This was the bug) 'date' column must exist on ALL rows *before* querying ***
        # We can skip this if display_data already added it, but this is safer:
        if 'date' not in self.current_df.columns or self.current_df['date'].isnull().any():
             self.current_df['date'] = pd.to_datetime(self.current_df['timestamp'], unit='s').dt.date


        # 2. Update Grand Total
        value_col_key: str = f"value_{self.current_currency.lower()}"
        price: float = self.main_window.price_updater.get_current_prices().get(self.current_currency.lower(), 0.0)

        total_kas: float = self.current_df['amount'].sum()
        
        # Ensure value col exists for new rows
        if value_col_key not in self.current_df.columns or self.current_df[value_col_key].isnull().any():
             self.current_df[value_col_key] = self.current_df['amount'] * price
        
        total_value: float = self.current_df[value_col_key].sum()
        
        if self.grand_total_id and self.tree.exists(self.grand_total_id):
            self.tree.item(
                self.grand_total_id,
                values=(
                    f"{len(self.current_df)} {translate('TXs')}",
                    "",
                    f"{total_kas:,.2f}",
                    f"{total_value:,.2f} {self.current_currency.upper()}",
                    ""
                )
            )

        # 3. Incrementally add new rows
        # Sort only the new batch based on current sort settings
        try:
            sorted_new_df = new_txs_df.sort_values(
                by=[self.sort_info['column']],
                ascending=[not self.sort_info['reverse']]
            )
        except KeyError:
             sorted_new_df = new_txs_df.sort_values(
                by=['timestamp'],
                ascending=[False]
            )

        data_to_insert: List[Dict[str, Any]] = sorted_new_df.to_dict('records')
        
        # Keep track of dates we've already updated in this batch
        updated_date_groups: Set[str] = set()

        for item in data_to_insert:
            try:
                if 'date' not in item or not isinstance(item['date'], date):
                    continue
                
                date_str: str = item['date'].strftime('%Y-%m-%d')
                
                # Find or create the date parent
                if date_str not in self.date_group_ids:
                    # This new batch has a new date
                    daily_df: pd.DataFrame = self.current_df[self.current_df['date'] == item['date']] # Query full df
                    daily_kas: float = daily_df['amount'].sum()
                    daily_value: float = daily_df[value_col_key].sum() if value_col_key in daily_df else 0.0
                    date_id: str = self.tree.insert(
                        "",
                        "end", # Add new dates to the end
                        text=date_str,
                        values=(
                            f"{len(daily_df)} {translate('TXs')}",
                            "",
                            f"{daily_kas:,.2f}",
                            f"{daily_value:,.2f} {self.current_currency.upper()}",
                            ""
                        ),
                        open=False, # *** FIX 2: Was True ***
                        tags=('date_header',)
                    )
                    self.date_group_ids[date_str] = date_id
                    updated_date_groups.add(date_str) # Mark as updated
                
                elif date_str not in updated_date_groups:
                    # Date parent already exists, update its summary (but only once per batch)
                    date_id = self.date_group_ids[date_str]
                    daily_df = self.current_df[self.current_df['date'] == item['date']] # Query full df
                    daily_kas = daily_df['amount'].sum()
                    daily_value = self.current_df[self.current_df['date'] == item['date']][value_col_key].sum()
                    self.tree.item(date_id, values=(
                        f"{len(daily_df)} {translate('TXs')}",
                        "",
                        f"{daily_kas:,.2f}",
                        f"{daily_value:,.2f} {self.current_currency.upper()}",
                        ""
                    ))
                    updated_date_groups.add(date_str) # Mark as updated

                parent_id: str = self.date_group_ids[date_str]
                item_timestamp = item.get('timestamp', 0)
                item_time_str = datetime.fromtimestamp(item_timestamp).strftime('%H:%M:%S')

                # Insert the new transaction row
                if not self.tree.exists(item['txid']):
                    self.tree.insert(
                        parent=parent_id,
                        index=END, # Add new transactions to the end of their date group
                        iid=item['txid'],
                        text=item_time_str,
                        values=(
                            item['txid'],
                            translate(str(item.get('direction', 'N/A')).capitalize()),
                            f"{item.get('amount', 0):,.2f}",
                            f"{item.get(value_col_key, 0.0):,.2f} {self.current_currency.upper()}"
                            if item.get(value_col_key) is not None else "N/A",
                            translate(str(item.get('type', 'N/A')).capitalize())
                        ),
                        tags=(item['txid'],)
                    )
            except Exception as e:
                logger.warning(f"Failed to display transaction item {item.get('txid')}: {e}", exc_info=True)

    def _process_data_queue(self, data_queue: "queue.Queue[pd.DataFrame]", is_first_chunk: bool) -> None:
        """
        Internal helper for processing the data queue.
        Uses display_data for the first chunk, and append_transactions for others.
        """
        if self._cancel_event.is_set() or not self.winfo_exists():
            logger.info("UI update loop cancelled or widget destroyed.")
            self.after_id_populate = None
            return

        try:
            # Process ONE chunk from the queue
            df_chunk: pd.DataFrame = data_queue.get_nowait()
            
            if is_first_chunk:
                # First chunk: Use display_data to clear and populate
                self.display_data(df_chunk, self.current_currency)
            else:
                # Subsequent chunks: Use append_transactions to add incrementally
                self.append_transactions(df_chunk)
                
            data_queue.task_done()
            
            # Schedule the next check, passing 'False' for is_first_chunk
            self.after_id_populate = self.after(
                50, self._process_data_queue, data_queue, False  # Now always False
            )

        except queue.Empty:
            # Queue is empty, check if the producer is done
            if not self.main_window.transaction_manager.is_fetching:
                logger.debug("UI update loop finished (queue empty, manager not fetching).")
                self.after_id_populate = None
                
                # --- *** FIX *** ---
                # Only show "No transactions" if we are *still* on the first chunk
                # (meaning display_data was never called) and the df is empty.
                if is_first_chunk and self.current_df.empty:
                     self.show_placeholder(translate("No transactions match the current criteria."))
                # --- *** END FIX ---
                return
            
            # Producer is still running, check again soon
            # Note: we pass 'is_first_chunk' again, in case the queue was
            # empty on the very first check.
            self.after_id_populate = self.after(
                100, self._process_data_queue, data_queue, is_first_chunk
            )
        
        except Exception as e:
            logger.error(f"Error in UI update loop: {e}", exc_info=True)
            self.after_id_populate = None

    def start_ui_update_loop(self, data_queue: "queue.Queue[pd.DataFrame]") -> None:
        """
        Starts the 'after' loop to process the UI update queue.
        This version processes ONE item at a time to allow the UI to update.
        """
        if self.after_id_populate:
            self.after_cancel(self.after_id_populate)
            self.after_id_populate = None

        # Start the processing loop, always assuming the first call is for the first chunk
        self.after_id_populate = self.after(
            50, self._process_data_queue, data_queue, True
        )

    def stop_ui_update_loop(self, data_queue: "queue.Queue[pd.DataFrame]") -> None:
        """Stops the 'after' loop and processes any remaining items."""
        logger.info("Stopping UI update loop and processing remaining queue items.")
        if self.after_id_populate:
            self.after_cancel(self.after_id_populate)
            self.after_id_populate = None

        try:
            is_first_chunk = self.current_df.empty # Check if we're stopping before *anything* was displayed
            
            while not data_queue.empty():
                if not self.winfo_exists():
                    break
                df_chunk: pd.DataFrame = data_queue.get_nowait()

                if is_first_chunk:
                    self.display_data(df_chunk, self.current_currency)
                    is_first_chunk = False # Only do this once
                else:
                    self.append_transactions(df_chunk)
                    
                data_queue.task_done()
        except queue.Empty:
            pass
        except Exception as e:
            logger.error(f"Error processing remaining UI queue: {e}", exc_info=True)
        logger.info("UI update loop stopped.")