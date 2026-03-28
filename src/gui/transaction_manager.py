#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
<<<<<<< HEAD
=======

import json
>>>>>>> dev-latest
import logging
import os
import queue
import threading
import time
<<<<<<< HEAD
from datetime import datetime as dt
from typing import Any, Dict, List, Optional, Set
=======
from tkinter import messagebox
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Tuple, cast

>>>>>>> dev-latest
import pandas as pd
from ttkbootstrap.toast import ToastNotification
from src.api.network import _make_api_request
from src.config.config import CONFIG, get_active_api_config
<<<<<<< HEAD
from src.database.db_locker import acquire_lock, release_lock
from src.utils.i18n import get_all_translations_for_key, translate
from src.utils.profiling import log_performance
from typing import TYPE_CHECKING
=======
from src.database.db_locker import release_lock
from src.utils.errors import APIError
from src.utils.i18n import get_all_translations_for_key, translate
from src.utils.profiling import log_performance
>>>>>>> dev-latest

if TYPE_CHECKING:
    from datetime import datetime as dt

    from src.database import TransactionDB
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)

@log_performance
<<<<<<< HEAD
def _process_raw_transactions(raw_txs: List[Dict[str, Any]], address: str, prices: Dict[str, float]) -> pd.DataFrame:
    if not raw_txs: return pd.DataFrame()
    processed = []
    addr_lower = address.lower()
    cols = CONFIG.get("display", {}).get("supported_currencies", [])
    
=======
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
    supported_currencies: List[str] = CONFIG.get("display", {}).get(
        "supported_currencies", []
    )

>>>>>>> dev-latest
    for tx in raw_txs:
        if not tx.get("is_accepted", False): continue
        try:
<<<<<<< HEAD
            inputs = tx.get("inputs", []) or []
            outputs = tx.get("outputs", []) or []
            is_coinbase = not inputs
            
            t_in = sum(int(o.get("amount", 0)) for o in outputs if (o.get("script_public_key_address") or "").lower() == addr_lower)
            t_out = sum(int(i.get("previous_outpoint_amount", 0)) for i in inputs if (i.get("previous_outpoint_address") or "").lower() == addr_lower)
            amt = abs(t_in - t_out) / 1e8
            
            from_a = list(set(i.get("previous_outpoint_address", "N/A") for i in inputs))
            to_a = list(set(o.get("script_public_key_address", "N/A") for o in outputs))
            
            direction = "incoming"
            if not is_coinbase and any((a or "").lower() == addr_lower for a in from_a):
                if not any((a or "").lower() == addr_lower for a in to_a): direction = "outgoing"
            
            rec = {
                "txid": tx.get("transaction_id"),
                "address": addr_lower,
                "direction": direction,
                "from_address": ", ".join(from_a) if from_a else "N/A",
                "to_address": ", ".join(to_a),
                "amount": amt,
                "block_height": tx.get("accepting_block_blue_score"),
                "timestamp": int(tx.get("block_time", 0)) // 1000,
                "type": "coinbase" if is_coinbase else "transfer"
            }
            for c in cols: rec[f"value_{c}"] = amt * prices.get(c, 0.0)
            processed.append(rec)
        except Exception: pass
    return pd.DataFrame(processed)

class TransactionManager:
    def __init__(self, main_window: MainWindow, tx_db: TransactionDB, cancel_event: threading.Event) -> None:
        self.main_window = main_window
        self.tx_db = tx_db
        self.is_fetching = False
        self._fetch_thread = None
        self._consumer_thread = None
        self._cancel_event = cancel_event
        self.start_time = 0.0
        self.ui_update_queue = queue.Queue()

    def get_thread(self): return self._fetch_thread

    def start_fetch(self, address: str, force: bool = False, filters: Optional[Dict[str, Any]] = None) -> None:
        if self.is_fetching: return
=======
            # *** Real filtering happens here ***
            if not tx.get("is_accepted", False):
                continue

            inputs: List[Dict[str, Any]] = tx.get("inputs", []) or []
            outputs: List[Dict[str, Any]] = tx.get("outputs", []) or []
            is_coinbase: bool = not inputs

            from_addresses: List[str] = list(
                set(i.get("previous_outpoint_address", "N/A") for i in inputs)
            )
            to_addresses: List[str] = list(
                set(o.get("script_public_key_address", "N/A") for o in outputs)
            )

            total_in: int = sum(
                int(o.get("amount", 0))
                for o in outputs
                if (o.get("script_public_key_address") or "").lower() == address_lower
            )
            total_out: int = sum(
                int(i.get("previous_outpoint_amount", 0))
                for i in inputs
                if (i.get("previous_outpoint_address") or "").lower() == address_lower
            )

            amount_kas: float = abs(total_in - total_out) / 1e8
            is_sender: bool = any(
                (addr or "").lower() == address_lower for addr in from_addresses
            )
            is_recipient: bool = any(
                (addr or "").lower() == address_lower for addr in to_addresses
            )

            direction: str
            if is_coinbase or (is_recipient and not is_sender):
                direction = "incoming"
            else:
                direction = "outgoing"

            record: Dict[str, Any] = {
                "txid": tx.get("transaction_id"),
                "address": address_lower,
                "direction": direction,
                "from_address": (
                    ", ".join(from_addresses) if from_addresses else "N/A (Coinbase)"
                ),
                "to_address": ", ".join(to_addresses),
                "amount": amount_kas,
            }

            for currency in supported_currencies:
                record[f"value_{currency}"] = amount_kas * prices.get(currency, 0.0)

            record.update(
                {
                    "block_height": tx.get("accepting_block_blue_score"),
                    "timestamp": int(tx.get("block_time", 0)) // 1000,
                    "type": "coinbase" if is_coinbase else "transfer",
                }
            )

            processed_data.append(record)

        except (TypeError, KeyError, ValueError) as e:
            logger.warning(
                f"Skipping malformed raw tx {tx.get('transaction_id', 'N/A')}: {e}"
            )

    return pd.DataFrame(processed_data)


class TransactionManager:
    # --- Type Hint Declarations ---
    main_window: "MainWindow"
    tx_db: "TransactionDB"
    is_fetching: bool
    _fetch_thread: Optional[threading.Thread]
    _consumer_thread: Optional[threading.Thread]
    _cancel_event: threading.Event
    start_time: float
    ui_update_queue: queue.Queue[pd.DataFrame]
    # --- End Type Hint Declarations ---

    def __init__(
        self,
        main_window: "MainWindow",
        tx_db: "TransactionDB",
        cancel_event: threading.Event,
    ) -> None:
        """
        Initializes the TransactionManager.

        Args:
            main_window: The main application window.
            tx_db: The transaction database instance.
            cancel_event: A threading.Event to signal cancellation.
        """
        self.main_window: "MainWindow" = main_window
        self.tx_db: "TransactionDB" = tx_db
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
        filters: Optional[Dict[str, Any]] = None,
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

>>>>>>> dev-latest
        self.main_window.current_address = address
        self.is_fetching = True
        self._cancel_event.clear()
        if self.main_window.winfo_exists():
            self.main_window.after(0, self.main_window._set_ui_for_processing, True)
<<<<<<< HEAD
        
        if force and hasattr(self.main_window, "explorer_tab"):
            self.main_window.explorer_tab.results_component.prepare_for_force_fetch()
=======

        if force and self.winfo_exists():
            if hasattr(self.main_window, "explorer_tab"):
                self.main_window.explorer_tab.results_component.prepare_for_force_fetch()
>>>>>>> dev-latest

        self.start_time = time.time()
        self.main_window.status.update_status("Starting transaction download...")
        if self.main_window.winfo_exists():
            self.main_window.start_ui_update_loop(self.ui_update_queue)

<<<<<<< HEAD
        self._fetch_thread = threading.Thread(target=self._fetch_worker, args=(address, force, filters), daemon=True, name="FetchWorker")
=======
        self._fetch_thread = threading.Thread(
            target=self._fetch_worker,
            args=(address, force, filters),
            daemon=True,
            name="FetchWorker",
        )
>>>>>>> dev-latest
        self._fetch_thread.start()

    def stop_fetch(self):
        if self.is_fetching:
            self._cancel_event.set()

<<<<<<< HEAD
    def _db_writer_task(self, q, event):
        while True:
            try:
                df = q.get(timeout=1)
                if df is None: break
            except queue.Empty:
                if event.is_set(): break
                continue
            if not self.main_window.winfo_exists() or self._cancel_event.is_set(): break
            if df is not None and not df.empty:
                self.tx_db.upsert_transactions_df(df)
            q.task_done()
=======
    @log_performance
    def _db_writer_task(
        self,
        db_write_queue: queue.Queue[Optional[pd.DataFrame]],
        producer_done_event: threading.Event,
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
        start_dt: Optional["dt"] = filters.get("start_date")
        end_dt: Optional["dt"] = filters.get("end_date")

        start_ts: int = int(start_dt.timestamp()) if start_dt else 0
        end_ts: float = int(end_dt.timestamp()) if end_dt else float("inf")

        type_filter: str = filters.get("type_filter", "ALL")
        all_type_keys: Set[str] = get_all_translations_for_key("ALL")
        if type_filter not in all_type_keys:
            type_filter = (
                "coinbase"
                if type_filter in get_all_translations_for_key("coinbase")
                else "transfer"
            )

        direction_filter: str = filters.get("direction_filter", "ALL")
        all_direction_keys: Set[str] = get_all_translations_for_key("ALL")
        if direction_filter not in all_direction_keys:
            direction_filter = (
                "incoming"
                if direction_filter in get_all_translations_for_key("incoming")
                else "outgoing"
            )
>>>>>>> dev-latest

    def _get_common_filters(self, f):
        f = f or {}
        s_dt, e_dt = f.get("start_date"), f.get("end_date")
        return {
            "start_ts": int(s_dt.timestamp()) if s_dt else 0,
            "end_ts": int(e_dt.timestamp()) + 86399 if e_dt else float("inf"),
        }

<<<<<<< HEAD
    def _perform_fetch_loop(self, address, criteria, q, prices, status, existing_ids, is_full):
        api = get_active_api_config()
        limit = api.get("page_limit", 500)
        base = api.get("base_url", "")
        ep = api["endpoints"]["full_transactions"]
        
        start_ts = criteria["start_ts"]
        end_ts = criteria["end_ts"]
        offset = 0
        
        logger.info(f"FETCH LOOP STARTED. StartTS: {start_ts}, EndTS: {end_ts}")

        while True:
            if self._cancel_event.is_set(): break
            
            # FIX: Prevent URL duplication
            ep_formatted = ep.format(kaspaAddress=address, limit=limit, offset=offset)
            if ep_formatted.startswith("http"):
                url = ep_formatted
            else:
                base_clean = base.rstrip('/')
                ep_clean = ep_formatted.lstrip('/')
                url = f"{base_clean}/{ep_clean}"
            
            raw = _make_api_request(url)
            
            # FIX: Stop only if no data at all
            if not raw or len(raw) == 0: 
                logger.info("Fetch loop: No more data from API.")
                break

            timestamps = [int(tx.get("block_time", 0)) // 1000 for tx in raw]
            newest_in_batch = max(timestamps) if timestamps else 0
            oldest_in_batch = min(timestamps) if timestamps else 0
            
            logger.info(f"Batch: Range {oldest_in_batch}-{newest_in_batch} | Target Start {start_ts}")

            # Logical stop: if the newest transaction in the batch is older than the start date
            if newest_in_batch > 0 and newest_in_batch < start_ts:
                logger.info(f"Stopping fetch: Batch entirely before start date ({newest_in_batch} < {start_ts}).")
                break
                
            valid_txs = []
            for tx in raw:
                ts = int(tx.get("block_time", 0)) // 1000
                if ts < start_ts or ts > end_ts: continue
                if not is_full and tx.get("transaction_id") in existing_ids: continue
                valid_txs.append(tx)

            if valid_txs:
                df = _process_raw_transactions(valid_txs, address, prices)
                if not df.empty:
                    q.put(df)
                    self.ui_update_queue.put(df.copy())
            
            # FIX: Removed premature break and increment offset correctly
            offset += len(raw)

    def _fetch_worker(self, address, force, filters):
        status = lambda m, *a: self.main_window.after(0, self.main_window.status.update_status, m, *a)
        db_q = queue.Queue(maxsize=10)
        prod_done = threading.Event()
        self._consumer_thread = threading.Thread(target=self._db_writer_task, args=(db_q, prod_done), daemon=True)
        self._consumer_thread.start()
        
        success = True
        try:
            prices = self.main_window.price_updater.get_current_prices()
            criteria = self._get_common_filters(filters)
            
            existing = set()
            if force:
                status("Clearing local data...")
                self.tx_db.delete_transactions_for_address(address)
            else:
                local = self.tx_db.filter_transactions(address=address)
                existing = {t["txid"] for t in local}
                filtered = self.tx_db.filter_transactions(address=address, **(filters or {}))
                if filtered: self.ui_update_queue.put(pd.DataFrame(filtered))

            status("Fetching from network...")
            self._perform_fetch_loop(address, criteria, db_q, prices, status, existing, force)
            
        except Exception as e:
            success = False
            logger.error(f"Fetch Error: {e}", exc_info=True)
        finally:
            prod_done.set()
            db_q.put(None)
            if self._consumer_thread: self._consumer_thread.join()
            
            if self.main_window.winfo_exists():
                self.main_window.after(0, self.main_window.stop_ui_update_loop, self.ui_update_queue)
                self.main_window.after(100, self._finalize_fetch, "Fetch done", success, force)

    def _finalize_fetch(self, msg, success, force, show_toast=True):
        self.is_fetching = False
        self.main_window.after(0, self.main_window.finalize_ui_load, success, msg, time.time() - self.start_time)
        if force and success:
            self.main_window.after(200, self._compact_db_after_fetch)

    def _compact_db_after_fetch(self):
        logger.info("Compacting database...")
        try:
            db_name = CONFIG["db_filenames"]["transactions"]
            self.main_window.close_all_db_connections()
            time.sleep(0.5)
            release_lock(db_name)
            time.sleep(0.5)
            self.main_window.db_manager.compact_database(db_name)
            acquire_lock(db_name)
        except Exception as e:
            logger.error(f"Compaction error: {e}")
=======
    def _apply_filters_to_df(
        self, df: pd.DataFrame, filter_criteria: Dict[str, Any]
    ) -> pd.DataFrame:
        """Applies filters to a processed DataFrame before queueing for UI."""
        if df.empty:
            return df

        filtered_df = df[
            (df["timestamp"] >= filter_criteria["start_ts"])
            & (df["timestamp"] <= filter_criteria["end_ts"])
        ]
        if filter_criteria["type_filter"] not in filter_criteria["all_type_keys"]:
            filtered_df = filtered_df[
                filtered_df["type"] == filter_criteria["type_filter"]
            ]
        if (
            filter_criteria["direction_filter"]
            not in filter_criteria["all_direction_keys"]
        ):
            filtered_df = filtered_df[
                filtered_df["direction"] == filter_criteria["direction_filter"]
            ]

        return filtered_df

    @log_performance
    def _perform_incremental_fetch(
        self,
        address: str,
        filters: Optional[Dict[str, Any]],
        db_write_queue: queue.Queue[Optional[pd.DataFrame]],
        prices: Dict[str, float],
        status: Callable[..., None],
    ) -> None:
        """
        Performs an incremental fetch (force=False).
        Loads from DB first, then pages API until existing TXs are found.
        """
        api_config: Dict[str, Any] = get_active_api_config()
        chunk_size: int = api_config.get("page_limit", 500)
        filter_criteria = self._get_common_filters(filters)

        status("Loading transactions from local database...")
        initial_df = pd.DataFrame(
            self.main_window.tx_db.filter_transactions(
                address=address, **(filters or {})
            )
        )

        if not initial_df.empty:
            logger.info(
                f"Loading {len(initial_df)} transactions from local DB in chunks..."
            )
            for i in range(0, len(initial_df), chunk_size):
                if self._cancel_event.is_set():
                    raise InterruptedError("Fetch cancelled during local load.")
                df_chunk: pd.DataFrame = initial_df.iloc[i : i + chunk_size]
                self.ui_update_queue.put(df_chunk)
                time.sleep(0.01)
        else:
            logger.info("No local transactions found to load.")

        status("Checking network for new transactions...")
        if self._cancel_event.is_set():
            raise InterruptedError("Fetch cancelled.")

        existing_txids: Set[str] = self.tx_db.get_existing_txids(address)

        new_tx_count: int = 0
        offset: int = 0
        max_pages: int = cast(int, CONFIG["performance"]["max_pages"])
        page_delay: float = cast(float, CONFIG["performance"]["page_delay"])
        base: str = api_config["base_url"]
        endpoint: str = api_config["endpoints"]["full_transactions"]

        filter_start_ts_config: int = filter_criteria["start_ts"]

        for page_num in range(max_pages):
            if self._cancel_event.is_set():
                raise InterruptedError("Fetch cancelled.")

            status(
                "Scanning page {}... ({} new transactions found)",
                page_num + 1,
                new_tx_count,
            )

            url: str = f"{base}{endpoint}".format(
                kaspaAddress=address, limit=chunk_size, offset=offset
            )
            raw_data: Optional[List[Dict[str, Any]]] = _make_api_request(url)

            if raw_data is None:
                raise APIError(f"API request failed for page {page_num + 1}")

            if not raw_data:
                logger.info(
                    f"Stopping pagination on page {page_num + 1}: API returned no more transactions."
                )
                break

            txs_to_process: List[Dict[str, Any]] = [
                tx for tx in raw_data if tx.get("transaction_id") not in existing_txids
            ]

            processed_df: pd.DataFrame = pd.DataFrame()
            if txs_to_process:
                processed_df = _process_raw_transactions(
                    txs_to_process, address, prices
                )

            if not processed_df.empty:
                new_tx_count += len(processed_df)

                db_write_queue.put(processed_df)

                filtered_df = self._apply_filters_to_df(processed_df, filter_criteria)

                if not filtered_df.empty:
                    self.ui_update_queue.put(filtered_df.copy())

            if not processed_df.empty:
                if all(txid in existing_txids for txid in processed_df["txid"]):
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
                tx for tx in raw_data if tx.get("is_accepted", False)
            ]
            if not accepted_txs_timestamps:
                if len(raw_data) < chunk_size:
                    break
                offset += len(raw_data)
                continue

            oldest_ts_on_page: int = (
                int(accepted_txs_timestamps[-1].get("block_time", 0)) // 1000
            )
            if (
                filter_start_ts_config > 0
                and oldest_ts_on_page < filter_start_ts_config
            ):
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
        status: Callable[..., None],
    ) -> None:
        """
        Performs a full fetch (force=True).
        Deletes all local data first, then pages API fully.
        """
        api_config: Dict[str, Any] = get_active_api_config()
        chunk_size: int = api_config.get("page_limit", 500)
        filter_criteria = self._get_common_filters(filters)

        status("Clearing local data and starting full redownload...")
        self.tx_db.delete_transactions_for_address(address)

        status("Fetching all transactions from network...")

        new_tx_count: int = 0
        offset: int = 0
        max_pages: int = cast(int, CONFIG["performance"]["max_pages"])
        page_delay: float = cast(float, CONFIG["performance"]["page_delay"])
        base: str = api_config["base_url"]
        endpoint: str = api_config["endpoints"]["full_transactions"]

        filter_start_ts_config: int = filter_criteria["start_ts"]

        for page_num in range(max_pages):
            if self._cancel_event.is_set():
                raise InterruptedError("Fetch cancelled.")

            status(
                "Downloading page {}... ({} new transactions found)",
                page_num + 1,
                new_tx_count,
            )

            url: str = f"{base}{endpoint}".format(
                kaspaAddress=address, limit=chunk_size, offset=offset
            )
            raw_data: Optional[List[Dict[str, Any]]] = _make_api_request(url)

            if raw_data is None:
                raise APIError(f"API request failed for page {page_num + 1}")

            if not raw_data:
                logger.info(
                    f"Stopping pagination on page {page_num + 1}: API returned no more transactions."
                )
                break

            txs_to_process: List[Dict[str, Any]] = raw_data

            processed_df: pd.DataFrame = pd.DataFrame()
            if txs_to_process:
                processed_df = _process_raw_transactions(
                    txs_to_process, address, prices
                )

            if not processed_df.empty:
                new_tx_count += len(processed_df)

                db_write_queue.put(processed_df)

                filtered_df = self._apply_filters_to_df(processed_df, filter_criteria)

                if not filtered_df.empty:
                    self.ui_update_queue.put(filtered_df.copy())

            accepted_txs_timestamps: List[Dict[str, Any]] = [
                tx for tx in raw_data if tx.get("is_accepted", False)
            ]
            if not accepted_txs_timestamps:
                if len(raw_data) < chunk_size:
                    break
                offset += len(raw_data)
                continue

            oldest_ts_on_page: int = (
                int(accepted_txs_timestamps[-1].get("block_time", 0)) // 1000
            )
            if (
                filter_start_ts_config > 0
                and oldest_ts_on_page < filter_start_ts_config
            ):
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
        self, address: str, force: bool, filters: Optional[Dict[str, Any]]
    ) -> None:
        """
        Main worker thread for fetching, processing, and queuing transactions.
        Delegates to _perform_incremental_fetch or _perform_full_fetch.
        """
        logger.info("Stopping non-essential background services for fetch.")
        if hasattr(self.main_window, "price_updater"):
            self.main_window.price_updater.stop()
        if hasattr(self.main_window, "network_updater"):
            self.main_window.network_updater.stop()
        if hasattr(self.main_window, "top_addresses_tab"):
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
            name="DBWriter",
        )
        self._consumer_thread.start()

        success: bool = True
        final_message: str = "Fetch completed."

        try:
            prices: Dict[str, float] = (
                self.main_window.price_updater.get_current_prices()
            )

            if force:
                self._perform_full_fetch(
                    address, filters, db_write_queue, prices, status
                )
            else:
                self._perform_incremental_fetch(
                    address, filters, db_write_queue, prices, status
                )

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
        self._finalize_fetch(
            f"Error: {error_message}", success=False, show_toast=True, force=False
        )
        if self.winfo_exists():
            if (
                messagebox.askyesno(
                    title=translate("Network Error"),
                    message=translate("Retry fetch?").format(error_message),
                )
                and self.main_window.current_address
            ):
                filters: Optional[Dict[str, Any]] = (
                    self.main_window.explorer_tab.explorer_filter_controls.get_filters()
                )
                self.main_window.after(
                    100,
                    self.start_fetch,
                    self.main_window.current_address,
                    False,
                    filters,
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
                bootstyle="danger",
                duration=3000,
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
            db_name = CONFIG["db_filenames"]["transactions"]
            db_path = os.path.join(CONFIG["paths"]["database"], db_name)

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
            logger.error(
                f"Failed to compact database after force fetch: {e}", exc_info=True
            )
            ToastNotification(
                title=translate("Error"),
                message=f"Failed to compact database: {e}",
                bootstyle=DANGER,
                duration=3000,
            ).show_toast()
>>>>>>> dev-latest
        finally:
            self.main_window.reinitialize_databases()
<<<<<<< HEAD
            if hasattr(self.main_window, "tx_db"):
                self.tx_db = self.main_window.tx_db
            
            if hasattr(self.main_window, "explorer_tab"):
                self.main_window.explorer_tab.tx_db = self.main_window.tx_db
                logger.info("Triggering explicit UI refresh after compaction...")
                self.main_window.after(200, self.main_window.explorer_tab.apply_explorer_filters)
            
            self.main_window.status.update_status("Ready")
            self.main_window._set_ui_for_processing(False)
=======

            # 5. Re-enable UI
            self.main_window.status.update_status("Ready")
            self._set_ui_for_compaction(True)

            # Refresh DB size in settings if it's open
            if (
                hasattr(self.main_window, "settings_tab")
                and self.main_window.settings_tab.db_tab
            ):
                self.main_window.settings_tab.db_tab._refresh_db_info()

    def _set_ui_for_compaction(self, active: bool) -> None:
        """Disables UI elements during the sensitive compaction phase."""
        if not self.winfo_exists():
            return

        # Disable tab switching
        try:
            for tab_id in self.main_window.tabview.tabs():
                self.main_window.tabview.tab(
                    tab_id, state=NORMAL if active else DISABLED
                )
        except Exception:
            pass

        # Disable controls in settings
        if (
            hasattr(self.main_window, "settings_tab")
            and self.main_window.settings_tab.db_tab
        ):
            self.main_window.settings_tab.db_tab._set_buttons_state(
                NORMAL if active else DISABLED
            )

    def winfo_exists(self) -> bool:
        """Safely checks if the main window widget exists."""
        try:
            return bool(self.main_window.winfo_exists())
        except Exception:
            return False
>>>>>>> dev-latest
