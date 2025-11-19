#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
import queue
import threading
import time
from datetime import datetime as dt
from typing import Any, Dict, List, Optional, Set
import pandas as pd
from ttkbootstrap.toast import ToastNotification
from src.api.network import _make_api_request
from src.config.config import CONFIG, get_active_api_config
from src.database.db_locker import acquire_lock, release_lock
from src.utils.i18n import get_all_translations_for_key, translate
from src.utils.profiling import log_performance
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.database import TransactionDB
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)

@log_performance
def _process_raw_transactions(raw_txs: List[Dict[str, Any]], address: str, prices: Dict[str, float]) -> pd.DataFrame:
    if not raw_txs: return pd.DataFrame()
    processed = []
    addr_lower = address.lower()
    cols = CONFIG.get("display", {}).get("supported_currencies", [])
    
    for tx in raw_txs:
        if not tx.get("is_accepted", False): continue
        try:
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
        self.main_window.current_address = address
        self.is_fetching = True
        self._cancel_event.clear()
        if self.main_window.winfo_exists():
            self.main_window.after(0, self.main_window._set_ui_for_processing, True)
        
        if force and hasattr(self.main_window, "explorer_tab"):
            self.main_window.explorer_tab.results_component.prepare_for_force_fetch()

        self.start_time = time.time()
        self.main_window.status.update_status("Starting transaction download...")
        if self.main_window.winfo_exists():
            self.main_window.start_ui_update_loop(self.ui_update_queue)

        self._fetch_thread = threading.Thread(target=self._fetch_worker, args=(address, force, filters), daemon=True, name="FetchWorker")
        self._fetch_thread.start()

    def stop_fetch(self):
        if self.is_fetching:
            self._cancel_event.set()

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

    def _get_common_filters(self, f):
        f = f or {}
        s_dt, e_dt = f.get("start_date"), f.get("end_date")
        return {
            "start_ts": int(s_dt.timestamp()) if s_dt else 0,
            "end_ts": int(e_dt.timestamp()) + 86399 if e_dt else float("inf"),
        }

    def _perform_fetch_loop(self, address, criteria, q, prices, status, existing_ids, is_full):
        api = get_active_api_config()
        limit = api.get("page_limit", 500)
        base = api["base_url"]
        ep = api["endpoints"]["full_transactions"]
        
        start_ts = criteria["start_ts"]
        end_ts = criteria["end_ts"]
        offset = 0
        
        logger.info(f"FETCH LOOP STARTED. StartTS: {start_ts}, EndTS: {end_ts}")

        while True:
            if self._cancel_event.is_set(): break
            
            url = f"{base}{ep.format(kaspaAddress=address, limit=limit, offset=offset)}"
            raw = _make_api_request(url)
            if not raw: 
                logger.info("Fetch loop: No more data from API.")
                break

            timestamps = [int(tx.get("block_time", 0)) // 1000 for tx in raw]
            newest_in_batch = max(timestamps) if timestamps else 0
            oldest_in_batch = min(timestamps) if timestamps else 0
            
            logger.info(f"Batch: Range {oldest_in_batch}-{newest_in_batch} | Target Start {start_ts}")

            # CRITICAL FIX: 
            # Only stop if the NEWEST transaction in this batch is older than our start date filter.
            # This ensures we keep fetching until we reach the relevant time window.
            if newest_in_batch < start_ts:
                logger.info(f"Stopping fetch: Batch entirely before start date ({newest_in_batch} < {start_ts}).")
                break
                
            valid_txs = []
            for tx in raw:
                ts = int(tx.get("block_time", 0)) // 1000
                # Skip individual transactions outside range, but continue batch
                if ts < start_ts or ts > end_ts: continue
                if not is_full and tx.get("transaction_id") in existing_ids: continue
                valid_txs.append(tx)

            if valid_txs:
                df = _process_raw_transactions(valid_txs, address, prices)
                if not df.empty:
                    q.put(df)
                    # Send directly to UI queue for immediate feedback
                    self.ui_update_queue.put(df.copy())
            
            if len(raw) < limit:
                break
            
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
        finally:
            self.main_window.reinitialize_databases()
            if hasattr(self.main_window, "tx_db"):
                self.tx_db = self.main_window.tx_db
            
            if hasattr(self.main_window, "explorer_tab"):
                self.main_window.explorer_tab.tx_db = self.main_window.tx_db
                logger.info("Triggering explicit UI refresh after compaction...")
                self.main_window.after(200, self.main_window.explorer_tab.apply_explorer_filters)
            
            self.main_window.status.update_status("Ready")
            self.main_window._set_ui_for_processing(False)
