#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Manages the fetching, processing, and database persistence of Kaspa transactions.

This module coordinates background threads for fetching transaction data from the API,
processing raw JSON data into a structured format, saving it to the
TransactionDB, and queuing UI updates for the main window.
"""

from __future__ import annotations
import json
import logging
import queue
import threading
import time
import os
from tkinter import messagebox
from typing import TYPE_CHECKING, Any, cast, Callable, List, Dict, Optional, Set, Tuple

import pandas as pd
from ttkbootstrap.toast import ToastNotification

from src.api.network import _make_api_request
from src.config.config import CONFIG, get_active_api_config
from src.utils.errors import APIError
from src.utils.i18n import translate, get_all_translations_for_key
from src.utils.profiling import log_performance
from src.database.db_locker import release_lock

if TYPE_CHECKING:
    from src.database import TransactionDB
    from src.gui.main_window import MainWindow
    from datetime import datetime as dt

logger = logging.getLogger(__name__)


@log_performance
def _process_raw_transactions(
    raw_txs: List[Dict[str, Any]], address: str, prices: Dict[str, float]
) -> pd.DataFrame:
    """
    Converts a list of raw transaction JSON objects into a structured DataFrame,
    ensuring the column order matches the database schema.

    Args:
        raw_txs: A list of raw transaction dictionaries from the API.
        address: The primary address being queried.
        prices: A dictionary of current fiat prices.

    Returns:
        A pandas DataFrame of processed transactions.
    """
    if not raw_txs:
        return pd.DataFrame()

    processed_data: List[Dict[str, Any]] = []

    address_lower: str = address.lower()
    supported_currencies: List[str] = CONFIG.get('display', {}).get('supported_currencies', [])

    for tx in raw_txs:
        try:
            # *** Real filtering happens here ***
            if not tx.get('is_accepted', False):
                continue

            inputs: List[Dict[str, Any]] = tx.get('inputs', []) or []
            outputs: List[Dict[str, Any]] = tx.get('outputs', []) or []
            is_coinbase: bool = not inputs

            from_addresses: List[str] = list(set(
                i.get('previous_outpoint_address', 'N/A') for i in inputs
            ))
            to_addresses: List[str] = list(set(
                o.get('script_public_key_address', 'N/A') for o in outputs
            ))

            total_in: int = sum(
                int(o.get('amount', 0))
                for o in outputs
                if (o.get('script_public_key_address') or '').lower() == address_lower
            )
            total_out: int = sum(
                int(i.get('previous_outpoint_amount', 0))
                for i in inputs
                if (i.get('previous_outpoint_address') or '').lower() == address_lower
            )

            amount_kas: float = abs(total_in - total_out) / 1e8
            is_sender: bool = any((addr or '').lower() == address_lower for addr in from_addresses)
            is_recipient: bool = any((addr or '').lower() == address_lower for addr in to_addresses)

            direction: str
            if is_coinbase or (is_recipient and not is_sender):
                direction = 'incoming'
            else:
                direction = 'outgoing'

            record: Dict[str, Any] = {
                'txid': tx.get("transaction_id"),
                'address': address_lower,
                'direction': direction,
                'from_address': ', '.join(from_addresses) if from_addresses else 'N/A (Coinbase)',
                'to_address': ', '.join(to_addresses),
                'amount': amount_kas,
            }

            for currency in supported_currencies:
                record[f'value_{currency}'] = amount_kas * prices.get(currency, 0.0)

            record.update({
                'block_height': tx.get('accepting_block_blue_score'),
                'timestamp': int(tx.get('block_time', 0)) // 1000,
                'type': 'coinbase' if is_coinbase else 'transfer'
            })

            processed_data.append(record)

        except (TypeError, KeyError, ValueError) as e:
            logger.warning(
                f"Skipping malformed raw tx {tx.get('transaction_id', 'N/A')}: {e}"
            )

    return pd.DataFrame(processed_data)


class TransactionManager:
    # --- Type Hint Declarations ---
    main_window: 'MainWindow'
    tx_db: 'TransactionDB'
    is_fetching: bool
    _fetch_thread: Optional[threading.Thread]
    _consumer_thread: Optional[threading.Thread]
    _cancel_event: threading.Event
    start_time: float
    ui_update_queue: queue.Queue[pd.DataFrame]
    # --- End Type Hint Declarations ---


    def __init__(
        self,
        main_window: 'MainWindow',
        tx_db: 'TransactionDB',
        cancel_event: threading.Event
    ) -> None:
        """
        Initializes the TransactionManager.

        Args:
            main_window: The main application window.
            tx_db: The transaction database instance.
            cancel_event: A threading.Event to signal cancellation.
        """
        self.main_window: 'MainWindow' = main_window
        self.tx_db: 'TransactionDB' = tx_db
        self.is_fetching: bool = False
        self._fetch_thread: Optional[threading.Thread] = None
        self._consumer_thread: Optional[threading.Thread] = None
        self._cancel_event: threading.Event = cancel_event
        self.start_time: float = 0.0
        self.ui_update_queue: queue.Queue[pd.DataFrame] = queue.Queue()

    def get_thread(self) -> Optional[threading.Thread]:
        """Returns the active fetch thread, if any."""
        return self._fetch_thread

    def start_fetch(
        self,
        address: str,
        force: bool = False,
        filters: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Starts a new thread to fetch transactions for the given address.

        Args:
            address: The Kaspa address to fetch.
            force: If True, delete all local data and re-download.
            filters: Filters to apply to the initial database load.
        """
        if self.is_fetching:
            return

        self.main_window.current_address = address
        self.is_fetching = True
        self._cancel_event.clear()

        if self.winfo_exists():
            self.main_window.after(0, self.main_window._set_ui_for_processing, True)

        if force and self.winfo_exists():
            if hasattr(self.main_window, 'explorer_tab'):
                self.main_window.explorer_tab.results_component.prepare_for_force_fetch()

        self.start_time = time.time()
        self.main_window.status.update_status("Starting transaction download...")

        if self.winfo_exists():
            self.main_window.start_ui_update_loop(self.ui_update_queue)

        self._fetch_thread = threading.Thread(
            target=self._fetch_worker,
            args=(address, force, filters),
            daemon=True,
            name="FetchWorker"
        )
        self._fetch_thread.start()

    def stop_fetch(self) -> None:
        """Signals the cancellation event to stop the active fetch."""
        if self.is_fetching:
            logger.info("Fetch cancellation requested by user.")
            self._cancel_event.set()

    @log_performance
    def _db_writer_task(
        self,
        db_write_queue: queue.Queue[Optional[pd.DataFrame]],
        producer_done_event: threading.Event
    ) -> None:
        """
        Worker thread task to write processed DataFrames to the DB.
        This is its ONLY job.
        """
        try:
            while True:
                try:
                    processed_df: Optional[pd.DataFrame] = db_write_queue.get(timeout=1)
                    if processed_df is None:  # Sentinel value
                        break
                except queue.Empty:
                    if producer_done_event.is_set():
                        break  # Producer is done and queue is empty
                    continue

                if not self.winfo_exists() or self._cancel_event.is_set():
                    break
                
                if processed_df is not None and not processed_df.empty:
                    self.tx_db.upsert_transactions_df(processed_df)

                db_write_queue.task_done()

        except Exception as e:
            logger.error(f"Error in DB writer thread: {e}", exc_info=True)
        finally:
            logger.info("DB writer thread finished.")

    def _get_common_filters(self, filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Helper to parse and prepare common filter criteria."""
        filters = filters or {}
        start_dt: Optional['dt'] = filters.get('start_date')
        end_dt: Optional['dt'] = filters.get('end_date')
        
        start_ts: int = int(start_dt.timestamp()) if start_dt else 0
        end_ts: float = int(end_dt.timestamp()) if end_dt else float('inf')

        type_filter: str = filters.get('type_filter', 'ALL')
        all_type_keys: Set[str] = get_all_translations_for_key("ALL")
        if type_filter not in all_type_keys:
            type_filter = 'coinbase' if type_filter in get_all_translations_for_key("coinbase") else 'transfer'

        direction_filter: str = filters.get('direction_filter', 'ALL')
        all_direction_keys: Set[str] = get_all_translations_for_key("ALL")
        if direction_filter not in all_direction_keys:
            direction_filter = 'incoming' if direction_filter in get_all_translations_for_key("incoming") else 'outgoing'

        return {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "type_filter": type_filter,
            "direction_filter": direction_filter,
            "all_type_keys": all_type_keys,
            "all_direction_keys": all_direction_keys,
        }

    def _apply_filters_to_df(self, df: pd.DataFrame, filter_criteria: Dict[str, Any]) -> pd.DataFrame:
        """Applies filters to a processed DataFrame before queueing for UI."""
        if df.empty:
            return df

        filtered_df = df[
            (df['timestamp'] >= filter_criteria['start_ts']) &
            (df['timestamp'] <= filter_criteria['end_ts'])
        ]
        if filter_criteria['type_filter'] not in filter_criteria['all_type_keys']:
            filtered_df = filtered_df[filtered_df['type'] == filter_criteria['type_filter']]
        if filter_criteria['direction_filter'] not in filter_criteria['all_direction_keys']:
            filtered_df = filtered_df[filtered_df['direction'] == filter_criteria['direction_filter']]
        
        return filtered_df

    @log_performance
    def _perform_incremental_fetch(
        self,
        address: str,
        filters: Optional[Dict[str, Any]],
        db_write_queue: queue.Queue[Optional[pd.DataFrame]],
        prices: Dict[str, float],
        status: Callable[..., None]
    ) -> None:
        """
        Performs an incremental fetch (force=False).
        Loads from DB first, then pages API until existing TXs are found.
        """
        api_config: Dict[str, Any] = get_active_api_config()
        chunk_size: int = api_config.get('page_limit', 500)
        filter_criteria = self._get_common_filters(filters)
        
        status('Loading transactions from local database...')
        initial_df = pd.DataFrame(
            self.main_window.tx_db.filter_transactions(
                address=address, **(filters or {})
            )
        )

        if not initial_df.empty:
            logger.info(f"Loading {len(initial_df)} transactions from local DB in chunks...")
            for i in range(0, len(initial_df), chunk_size):
                if self._cancel_event.is_set():
                    raise InterruptedError("Fetch cancelled during local load.")
                df_chunk: pd.DataFrame = initial_df.iloc[i:i + chunk_size]
                self.ui_update_queue.put(df_chunk)
                time.sleep(0.01)
        else:
            logger.info("No local transactions found to load.")

        status('Checking network for new transactions...')
        if self._cancel_event.is_set():
            raise InterruptedError("Fetch cancelled.")

        existing_txids: Set[str] = self.tx_db.get_existing_txids(address)

        new_tx_count: int = 0
        offset: int = 0
        max_pages: int = cast(int, CONFIG['performance']['max_pages'])
        page_delay: float = cast(float, CONFIG['performance']['page_delay'])
        base: str = api_config['base_url']
        endpoint: str = api_config['endpoints']['full_transactions']
        
        filter_start_ts_config: int = filter_criteria['start_ts']

        for page_num in range(max_pages):
            if self._cancel_event.is_set():
                raise InterruptedError("Fetch cancelled.")

            status(
                'Scanning page {}... ({} new transactions found)',
                page_num + 1, new_tx_count
            )

            url: str = f"{base}{endpoint}".format(
                kaspaAddress=address, limit=chunk_size, offset=offset
            )
            raw_data: Optional[List[Dict[str, Any]]] = _make_api_request(url)

            if raw_data is None:
                raise APIError(f"API request failed for page {page_num + 1}")

            if not raw_data:
                logger.info(f"Stopping pagination on page {page_num + 1}: API returned no more transactions.")
                break
            
            txs_to_process: List[Dict[str, Any]] = [
                tx for tx in raw_data
                if tx.get("transaction_id") not in existing_txids
            ]
            
            processed_df: pd.DataFrame = pd.DataFrame()
            if txs_to_process:
                processed_df = _process_raw_transactions(txs_to_process, address, prices)

            if not processed_df.empty:
                new_tx_count += len(processed_df)
                
                db_write_queue.put(processed_df)
                
                filtered_df = self._apply_filters_to_df(processed_df, filter_criteria)

                if not filtered_df.empty:
                    self.ui_update_queue.put(filtered_df.copy())
            
            if not processed_df.empty:
                if all(txid in existing_txids for txid in processed_df['txid']):
                     logger.info(
                        f"Stopping pagination on page {page_num + 1}: "
                        "All transactions on this page are already in the local database."
                    )
                     break
            elif not txs_to_process and existing_txids:
                logger.info(
                    f"Stopping pagination on page {page_num + 1}: "
                    "All transactions on this page are already in the local database (pre-filter)."
                )
                break
            
            accepted_txs_timestamps: List[Dict[str, Any]] = [
                tx for tx in raw_data if tx.get('is_accepted', False)
            ]
            if not accepted_txs_timestamps:
                if len(raw_data) < chunk_size:
                    break
                offset += len(raw_data)
                continue

            oldest_ts_on_page: int = int(accepted_txs_timestamps[-1].get('block_time', 0)) // 1000
            if filter_start_ts_config > 0 and oldest_ts_on_page < filter_start_ts_config:
                logger.info(
                    f"Stopping pagination on page {page_num + 1} as its "
                    "oldest transaction is before the filter start date."
                )
                break

            if len(raw_data) < chunk_size:
                logger.info(
                    f"Stopping pagination on page {page_num + 1}: "
                    "API returned a partial page, indicating the end."
                )
                break

            offset += len(raw_data)
            if page_delay > 0:
                time.sleep(page_delay)
    
    @log_performance
    def _perform_full_fetch(
        self,
        address: str,
        filters: Optional[Dict[str, Any]],
        db_write_queue: queue.Queue[Optional[pd.DataFrame]],
        prices: Dict[str, float],
        status: Callable[..., None]
    ) -> None:
        """
        Performs a full fetch (force=True).
        Deletes all local data first, then pages API fully.
        """
        api_config: Dict[str, Any] = get_active_api_config()
        chunk_size: int = api_config.get('page_limit', 500)
        filter_criteria = self._get_common_filters(filters)

        status('Clearing local data and starting full redownload...')
        self.tx_db.delete_transactions_for_address(address)
        
        status('Fetching all transactions from network...')
        
        new_tx_count: int = 0
        offset: int = 0
        max_pages: int = cast(int, CONFIG['performance']['max_pages'])
        page_delay: float = cast(float, CONFIG['performance']['page_delay'])
        base: str = api_config['base_url']
        endpoint: str = api_config['endpoints']['full_transactions']
        
        filter_start_ts_config: int = filter_criteria['start_ts']

        for page_num in range(max_pages):
            if self._cancel_event.is_set():
                raise InterruptedError("Fetch cancelled.")

            status(
                'Downloading page {}... ({} new transactions found)',
                page_num + 1, new_tx_count
            )

            url: str = f"{base}{endpoint}".format(
                kaspaAddress=address, limit=chunk_size, offset=offset
            )
            raw_data: Optional[List[Dict[str, Any]]] = _make_api_request(url)

            if raw_data is None:
                raise APIError(f"API request failed for page {page_num + 1}")

            if not raw_data:
                logger.info(f"Stopping pagination on page {page_num + 1}: API returned no more transactions.")
                break
            
            txs_to_process: List[Dict[str, Any]] = raw_data
            
            processed_df: pd.DataFrame = pd.DataFrame()
            if txs_to_process:
                processed_df = _process_raw_transactions(txs_to_process, address, prices)

            if not processed_df.empty:
                new_tx_count += len(processed_df)
                
                db_write_queue.put(processed_df)
                
                filtered_df = self._apply_filters_to_df(processed_df, filter_criteria)

                if not filtered_df.empty:
                    self.ui_update_queue.put(filtered_df.copy())
            
            accepted_txs_timestamps: List[Dict[str, Any]] = [
                tx for tx in raw_data if tx.get('is_accepted', False)
            ]
            if not accepted_txs_timestamps:
                if len(raw_data) < chunk_size:
                    break
                offset += len(raw_data)
                continue

            oldest_ts_on_page: int = int(accepted_txs_timestamps[-1].get('block_time', 0)) // 1000
            if filter_start_ts_config > 0 and oldest_ts_on_page < filter_start_ts_config:
                logger.info(
                    f"Stopping pagination on page {page_num + 1} as its "
                    "oldest transaction is before the filter start date."
                )
                break

            if len(raw_data) < chunk_size:
                logger.info(
                    f"Stopping pagination on page {page_num + 1}: "
                    "API returned a partial page, indicating the end."
                )
                break

            offset += len(raw_data)
            if page_delay > 0:
                time.sleep(page_delay)


    @log_performance
    def _fetch_worker(
        self,
        address: str,
        force: bool,
        filters: Optional[Dict[str, Any]]
    ) -> None:
        """
        Main worker thread for fetching, processing, and queuing transactions.
        Delegates to _perform_incremental_fetch or _perform_full_fetch.
        """
        logger.info("Stopping non-essential background services for fetch.")
        if hasattr(self.main_window, 'price_updater'):
            self.main_window.price_updater.stop()
        if hasattr(self.main_window, 'network_updater'):
            self.main_window.network_updater.stop()
        if hasattr(self.main_window, 'top_addresses_tab'):
            self.main_window.top_addresses_tab.stop()

        status: Callable[..., None] = lambda key, *args: self.main_window.after(
            0, self.main_window.status.update_status, key, *args
        )

        db_write_queue: queue.Queue[Optional[pd.DataFrame]] = queue.Queue(maxsize=10)
        producer_done_event = threading.Event()

        self._consumer_thread = threading.Thread(
            target=self._db_writer_task,
            args=(db_write_queue, producer_done_event),
            daemon=True,
            name="DBWriter"
        )
        self._consumer_thread.start()

        success: bool = True
        final_message: str = "Fetch completed."

        try:
            prices: Dict[str, float] = self.main_window.price_updater.get_current_prices()

            if force:
                self._perform_full_fetch(address, filters, db_write_queue, prices, status)
            else:
                self._perform_incremental_fetch(address, filters, db_write_queue, prices, status)
            
        except InterruptedError as e:
            final_message = str(e)
            success = True
        except Exception as e:
            success = False
            final_message = str(e)
            logger.error(f"A critical fetch error occurred: {e}", exc_info=True)
            if self.winfo_exists() and not self._cancel_event.is_set():
                self.main_window.after(0, self._handle_fetch_error, str(e))
        
        finally:
            producer_done_event.set()
            db_write_queue.put(None)

            if self._consumer_thread:
                self._consumer_thread.join(timeout=300)
            
            if self.winfo_exists():
                self.main_window.after(
                    0, self.main_window.stop_ui_update_loop, self.ui_update_queue
                )
                self.main_window.after(
                    100, self._finalize_fetch, final_message, success, force
                )

            self.main_window.after(200, self.main_window.start_background_services)
            logger.info("Fetch worker has fully completed.")


    def _handle_fetch_error(self, error_message: str) -> None:
        """Handles API errors, prompting the user to retry."""
        self._finalize_fetch(f"Error: {error_message}", success=False, show_toast=True, force=False)
        if self.winfo_exists():
            if (
                messagebox.askyesno(
                    title=translate("Network Error"),
                    message=translate("Retry fetch?").format(error_message)
                ) and self.main_window.current_address
            ):
                filters: Optional[Dict[str, Any]] = self.main_window.explorer_tab.explorer_filter_controls.get_filters()
                self.main_window.after(
                    100, self.start_fetch, self.main_window.current_address, False, filters
                )
            else:
                self.main_window.status.update_status("Ready")

    def _finalize_fetch(
        self, message: str, success: bool, force: bool, show_toast: bool = True
    ) -> None:
        """Finalizes the fetch process, updates UI state, and shows notifications."""
        self.is_fetching = False
        elapsed_time: float = time.time() - self.start_time

        if self.winfo_exists():
            self.main_window.after(
                0, self.main_window.finalize_ui_load, success, message, elapsed_time
            )

        logger.info(f"{message} Total time: {elapsed_time:.2f} seconds.")

        if show_toast and not success and self.winfo_exists():
            ToastNotification(
                title=translate("Fetch Status"),
                message=translate(message),
                bootstyle='danger',
                duration=3000
            ).show_toast()

        if force and success and self.winfo_exists():
            self.main_window.after(200, self._compact_db_after_fetch)

    def _compact_db_after_fetch(self) -> None:
        """
        Runs the full, safe compaction process on the main thread
        after a successful force fetch.
        """
        if not self.winfo_exists():
            return
            
        logger.info("Force fetch complete. Compacting database to reclaim space...")
        self.main_window.status.update_status("Compacting database...")
        self._set_ui_for_compaction(False)
        
        try:
            db_name = CONFIG['db_filenames']['transactions']
            db_path = os.path.join(CONFIG['paths']['database'], db_name)

            # 1. Close all connections (this is synchronous on main thread)
            self.main_window.close_all_db_connections()
            
            # 2. Release lock
            release_lock(db_name)
            
            # 3. Compact using db_manager (which creates a new connection)
            success, msg = self.main_window.db_manager.compact_database(db_name)
            if not success:
                raise Exception(msg)
                
            logger.info("Database compaction complete.")
            
        except Exception as e:
            logger.error(f"Failed to compact database after force fetch: {e}", exc_info=True)
            ToastNotification(
                title=translate("Error"),
                message=f"Failed to compact database: {e}",
                bootstyle=DANGER,
                duration=3000
            ).show_toast()
        finally:
            # 4. Re-initialize connections
            self.main_window.reinitialize_databases()
            
            # 5. Re-enable UI
            self.main_window.status.update_status("Ready")
            self._set_ui_for_compaction(True)
            
            # Refresh DB size in settings if it's open
            if hasattr(self.main_window, 'settings_tab') and self.main_window.settings_tab.db_tab:
                self.main_window.settings_tab.db_tab._refresh_db_info()

    def _set_ui_for_compaction(self, active: bool) -> None:
        """Disables UI elements during the sensitive compaction phase."""
        if not self.winfo_exists():
            return
            
        # Disable tab switching
        try:
            for tab_id in self.main_window.tabview.tabs():
                self.main_window.tabview.tab(tab_id, state=NORMAL if active else DISABLED)
        except Exception:
            pass
            
        # Disable controls in settings
        if hasattr(self.main_window, 'settings_tab') and self.main_window.settings_tab.db_tab:
            self.main_window.settings_tab.db_tab._set_buttons_state(NORMAL if active else DISABLED)


    def winfo_exists(self) -> bool:
        """Safely checks if the main window widget exists."""
        try:
            return bool(self.main_window.winfo_exists())
        except Exception:
            return False