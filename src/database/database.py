#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Defines the database interaction classes for each DuckDB database file.

This module provides specialized classes (TransactionDB, AddressDB, AppDataDB)
that inherit from DatabaseManager. Each class manages the specific schema
and queries for its corresponding database file.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any, Callable, List, Dict, Optional, Tuple, TYPE_CHECKING, Set

import duckdb
import pandas as pd

from src.database.db_base import DatabaseManager
from src.database.db_schema import (
    initialize_addr_schema,
    initialize_app_data_schema,
    initialize_tx_schema,
)
from src.utils.db_utils import retry_on_schema_error
from src.utils.formatting import mask_address
from src.utils.i18n import get_all_translations_for_key
from src.utils.errors import DatabaseError
from src.utils.profiling import log_performance

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)


class TransactionDB(DatabaseManager):
    """Manages the transaction database."""

    def __init__(self, db_path: str, schema_init: Callable[[DuckDBPyConnection], None]) -> None:
        """
        Initializes the TransactionDB.

        Args:
            db_path: The file path to the database.
            schema_init: The function to call to initialize the schema.
        """
        super().__init__(db_path)
        try:
            with self.connect() as con:
                schema_init(con)
        except Exception as e:
            logger.critical(f"Failed to initialize schema for {self.db_name}: {e}")
            raise DatabaseError(f"Failed to initialize schema for {self.db_name}: {e}") from e

    @retry_on_schema_error(initialize_tx_schema)
    def get_total_transaction_count(self) -> int:
        """Returns the total number of transactions in the database."""
        result = self.fetch_one("SELECT COUNT(*) FROM transactions")
        return result[0] if result else 0

    @log_performance
    @retry_on_schema_error(initialize_tx_schema)
    def delete_transactions_for_address(self, address: str) -> bool:
        """Deletes all transactions associated with a specific address."""
        logger.info(f"Deleting all transactions for address: {mask_address(address)}")
        query = "DELETE FROM transactions WHERE address = ?"
        return self.execute_query(query, (address,))

    @log_performance
    @retry_on_schema_error(initialize_tx_schema)
    def get_existing_txids(self, address: str) -> Set[str]:
        """Gets all existing TXIDs for an address to prevent duplicates."""
        query = "SELECT txid FROM transactions WHERE address = ?"
        results = self.fetch_all(query, (address,))
        return {row[0] for row in results}

    @log_performance
    @retry_on_schema_error(initialize_tx_schema)
    def upsert_transactions_df(self, df: pd.DataFrame) -> bool:
        """Inserts or updates transactions from a DataFrame."""
        if df.empty:
            return True
        try:
            with self.connect() as con:
                con.register('df_view', df)
                con.execute("INSERT OR REPLACE INTO transactions SELECT * FROM df_view")
            return True
        except Exception as e:
            logger.error(f"Failed to upsert transactions from DataFrame: {e}", exc_info=True)
            return False

    @log_performance
    @retry_on_schema_error(initialize_tx_schema)
    def filter_transactions(
        self,
        address: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        type_filter: str = "ALL",
        direction_filter: str = "ALL",
        search_query: Optional[str] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """
        Filters transactions for a given address based on multiple criteria.
        Handles translated filter values.
        Returns data as a list of dictionaries.
        """
        query = 'SELECT * FROM transactions WHERE address = ?'
        params: List[Any] = [address]

        if start_date:
            query += " AND timestamp >= ?"
            params.append(int(start_date.timestamp()))

        if end_date:
            query += " AND timestamp <= ?"
            params.append(int(end_date.timestamp()))

        all_key_translations: Set[str] = get_all_translations_for_key("ALL")

        if type_filter and type_filter not in all_key_translations:
            query += ' AND "type" = ?'
            if type_filter in get_all_translations_for_key("coinbase"):
                params.append('coinbase')
            else:
                params.append('transfer')

        if direction_filter and direction_filter not in all_key_translations:
            query += " AND direction = ?"
            if direction_filter in get_all_translations_for_key("incoming"):
                params.append('incoming')
            else:
                params.append('outgoing')

        if search_query:
            query += " AND (txid LIKE ? OR from_address LIKE ? OR to_address LIKE ?)"
            like_query = f"%{search_query}%"
            params.extend([like_query, like_query, like_query])

        query += " ORDER BY timestamp DESC"

        try:
            with self.connect(read_only=True) as con:
                try:
                    columns_result = con.execute("DESCRIBE transactions").fetchall()
                    columns: List[str] = [col[0] for col in columns_result]
                except duckdb.Error:
                    columns_result = con.execute("PRAGMA table_info('transactions')").fetchall()
                    columns = [col[1] for col in columns_result]

                if not columns:
                    logger.warning("Could not get column info for transactions table.")
                    return []

                results: List[Tuple[Any, ...]] = con.execute(query, tuple(params)).fetchall()

            return [dict(zip(columns, row)) for row in results]

        except Exception as e:
            logger.error(f"Failed to filter transactions: {e}", exc_info=True)
        return []


class AddressDB(DatabaseManager):
    """Manages the user's saved addresses."""

    def __init__(self, db_path: str, schema_init: Callable[[DuckDBPyConnection], None]) -> None:
        """
        Initializes the AddressDB.

        Args:
            db_path: The file path to the database.
            schema_init: The function to call to initialize the schema.
        """
        super().__init__(db_path)
        try:
            with self.connect() as con:
                schema_init(con)
        except Exception as e:
            logger.critical(f"Failed to initialize schema for {self.db_name}: {e}")
            raise DatabaseError(f"Failed to initialize schema for {self.db_name}: {e}") from e

    @retry_on_schema_error(initialize_addr_schema)
    def migrate_schema(self) -> None:
        """Applies any necessary schema migrations."""
        try:
            with self.connect() as con:
                columns: List[Tuple[Any, ...]] = con.execute("PRAGMA table_info('addresses')").fetchall()
                col_names: List[str] = [col[1] for col in columns]

                if 'created_at' not in col_names:
                    logger.info("Migrating addresses schema: Adding 'created_at' column.")
                    con.execute(
                        "ALTER TABLE addresses ADD COLUMN created_at "
                        "BIGINT DEFAULT (EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::BIGINT)"
                    )

        except Exception as e:
            logger.error(f"Failed during schema migration for addresses: {e}", exc_info=True)

    @retry_on_schema_error(initialize_addr_schema)
    def get_all_addresses(self) -> List[Dict[str, Any]]:
        """Retrieves all saved addresses."""
        query = "SELECT address, name, created_at FROM addresses ORDER BY name, created_at DESC"
        results: List[Tuple[str, str, int]] = self.fetch_all(query)
        return [{'address': row[0], 'name': row[1], 'created_at': row[2]} for row in results]

    @retry_on_schema_error(initialize_addr_schema)
    def save_address(self, address: str, name: str) -> bool:
        """Saves or updates an address. The 'created_at' column relies on its DEFAULT value."""
        query = (
            "INSERT INTO addresses (address, name) VALUES (?, ?) "
            "ON CONFLICT(address) DO UPDATE SET name = excluded.name"
        )
        return self.execute_query(query, (address, name))

    @retry_on_schema_error(initialize_addr_schema)
    def delete_address(self, address: str) -> bool:
        """Deletes an address."""
        query = "DELETE FROM addresses WHERE address = ?"
        return self.execute_query(query, (address,))

    @retry_on_schema_error(initialize_addr_schema)
    def get_total_address_count(self) -> int:
        """Returns the total number of saved addresses."""
        result = self.fetch_one("SELECT COUNT(*) FROM addresses")
        return result[0] if result else 0


class AppDataDB(DatabaseManager):
    """Manages application-wide data like cache and user state."""

    def __init__(self, db_path: str, schema_init: Callable[[DuckDBPyConnection], None]) -> None:
        """
        Initializes the AppDataDB.

        Args:
            db_path: The file path to the database.
            schema_init: The function to call to initialize the schema.
        """
        super().__init__(db_path)
        try:
            with self.connect() as con:
                schema_init(con)
        except Exception as e:
            logger.critical(f"Failed to initialize schema for {self.db_name}: {e}")
            raise DatabaseError(f"Failed to initialize schema for {self.db_name}: {e}") from e

    @retry_on_schema_error(initialize_app_data_schema)
    def get_user_state(self, key: str) -> Optional[str]:
        """Retrieves a value from the user_state table."""
        query = "SELECT value FROM user_state WHERE key = ?"
        result = self.fetch_one(query, (key,))
        return result[0] if result else None

    @retry_on_schema_error(initialize_app_data_schema)
    def save_user_state(self, key: str, value: str) -> None:
        """Saves a key-value pair to the user_state table."""
        query = "INSERT OR REPLACE INTO user_state (key, value) VALUES (?, ?)"
        self.execute_query(query, (key, value))

    @retry_on_schema_error(initialize_app_data_schema)
    def get_cached_prices(self, expired: bool = False) -> Optional[Dict[str, float]]:
        """Retrieves cached prices, handling only valid JSON."""
        query = "SELECT prices_json, last_updated FROM cache WHERE key = 'prices'"
        if not expired:
            query += " AND last_updated >= NOW() - INTERVAL '1 hour'"

        result = self.fetch_one(query)
        if not result or not result[0]:
            return None

        prices_data: str = result[0]
        try:
            # Attempt to parse as JSON.
            return json.loads(prices_data)
        except json.JSONDecodeError as e:
            # SECURITY FIX:
            # The 'ast.literal_eval' fallback has been removed to prevent
            # potential DoS attacks from malformed legacy cache data.
            # If it's not valid JSON, treat it as invalid and clear it.
            logger.error(
                f"Failed to parse cached prices as JSON. Clearing invalid cache entry. Error: {e}"
            )
            self.execute_query("DELETE FROM cache WHERE key = 'prices'")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred reading cached prices: {e}")
            return None

    @retry_on_schema_error(initialize_app_data_schema)
    def save_cached_prices(self, prices_json: str) -> None:
        """Saves prices to the cache."""
        query = "INSERT OR REPLACE INTO cache (key, prices_json, last_updated) VALUES ('prices', ?, NOW())"
        self.execute_query(query, (prices_json,))

    @retry_on_schema_error(initialize_app_data_schema)
    def get_cached_network_data(self, expired: bool = False) -> Optional[Tuple[Optional[float], Optional[float]]]:
        """RetrieVes cached network data (hashrate, difficulty)."""
        query = "SELECT prices_json, last_updated FROM cache WHERE key = 'network_stats'"
        if not expired:
            query += " AND last_updated >= NOW() - INTERVAL '1 hour'"

        result = self.fetch_one(query)
        if result and result[0]:
            try:
                data: Dict[str, Optional[float]] = json.loads(result[0])
                if data:
                    return data.get('hashrate'), data.get('difficulty')
            except json.JSONDecodeError:
                logger.warning("Failed to decode cached network data.")
        return None

    @retry_on_schema_error(initialize_app_data_schema)
    def save_cached_network_data(self, hashrate: Optional[float], difficulty: Optional[float]) -> None:
        """Saves network data to the cache."""
        data_json = json.dumps({'hashrate': hashrate, 'difficulty': difficulty})
        query = "INSERT OR REPLACE INTO cache (key, prices_json, last_updated) VALUES ('network_stats', ?, NOW())"
        self.execute_query(query, (data_json,))

    @retry_on_schema_error(initialize_app_data_schema)
    def get_cached_prices_count(self) -> int:
        """Returns the number of cached price points."""
        result = self.fetch_one("SELECT COUNT(*) FROM cache WHERE key = 'prices'")
        return result[0] if result else 0

    @retry_on_schema_error(initialize_app_data_schema)
    def clear_caches(self) -> None:
        """Clears all cached data."""
        self.execute_query("DELETE FROM cache")

    @log_performance
    @retry_on_schema_error(initialize_app_data_schema)
    def save_address_names(self, names_list: List[Dict[str, str]]) -> None:
        """Saves a list of known address names, replacing old ones."""
        query = "INSERT OR REPLACE INTO known_names (address, name) VALUES (?, ?)"
        data: List[Tuple[str, str]] = [
            (item['address'], item['name'])
            for item in names_list
            if 'address' in item and 'name' in item
        ]

        if not data:
            return

        try:
            with self.connect() as con:
                con.execute("DELETE FROM known_names")
                con.executemany(query, data)
            logger.info(f"Successfully saved {len(data)} known names.")
        except Exception as e:
            logger.error(f"Failed to save address names: {e}", exc_info=True)

    @log_performance
    @retry_on_schema_error(initialize_app_data_schema)
    def get_address_names_map(self) -> Dict[str, str]:
        """Returns all known names as a dictionary map."""
        query = "SELECT address, name FROM known_names"
        results: List[Tuple[str, str]] = self.fetch_all(query)
        return {row[0]: row[1] for row in results}

    @retry_on_schema_error(initialize_app_data_schema)
    def get_address_names_count(self) -> int:
        """Returns the total number of known names."""
        result = self.fetch_one("SELECT COUNT(*) FROM known_names")
        return result[0] if result else 0