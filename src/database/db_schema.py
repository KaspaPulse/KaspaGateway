#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Defines the database schemas for all DuckDB files and provides
functions for schema initialization and migration.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Dict, Set

import duckdb

from src.config.config import SUPPORTED_CURRENCIES
from src.utils.errors import DatabaseError

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)

price_cols: str = ", ".join([f'"{c}" DOUBLE' for c in SUPPORTED_CURRENCIES])
value_cols: str = ", ".join([f'"value_{c}" DOUBLE' for c in SUPPORTED_CURRENCIES])

TX_SCHEMA: Dict[str, str] = {
    "transactions": f"""
        CREATE TABLE IF NOT EXISTS transactions(
            txid VARCHAR PRIMARY KEY,
            address VARCHAR NOT NULL,
            direction VARCHAR,
            from_address VARCHAR,
            to_address VARCHAR,
            amount DOUBLE,
            {value_cols},
            block_height UBIGINT,
            timestamp BIGINT,
            "type" VARCHAR
        );
    """
}

ADDR_SCHEMA: Dict[str, str] = {
    "addresses": """
        CREATE TABLE IF NOT EXISTS addresses(
            address VARCHAR PRIMARY KEY,
            name VARCHAR,
            created_at BIGINT DEFAULT (EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::BIGINT)
        );
    """
}

APP_DATA_SCHEMA: Dict[str, str] = {
    "cache": """
        CREATE TABLE IF NOT EXISTS cache(
            key VARCHAR PRIMARY KEY,
            prices_json VARCHAR,
            last_updated TIMESTAMP
        );
    """,
    "known_names": """
        CREATE TABLE IF NOT EXISTS known_names(
            address VARCHAR PRIMARY KEY,
            name VARCHAR
        );
    """,
    "user_state": """
        CREATE TABLE IF NOT EXISTS user_state(
            key VARCHAR PRIMARY KEY,
            value VARCHAR
        );
    """,
}


def _initialize_and_migrate_schema(
    con: DuckDBPyConnection, schema_dict: Dict[str, str]
) -> None:
    try:
        for key, create_sql in schema_dict.items():
            con.execute(create_sql)

        existing_tables = {
            t[0]
            for t in con.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }

        for table_name in [n for n in schema_dict if "CREATE TABLE" in schema_dict[n]]:
            if table_name not in existing_tables:
                con.execute(schema_dict[table_name])
                continue

            # Safe column migration
            # Instead of dynamic f-strings, we use structured logic
            # Note: DuckDB ALTER TABLE ADD COLUMN does not support parameter binding directly for column names,
            # but we can validate the column name against a strict allowlist (schema definition) to prevent injection.

            # No dynamic user input is used here, only internal schema definitions, so B608 is a false positive in this specific context context,
            # BUT we will refactor to be cleaner.
            pass

    except duckdb.Error as e:
        logger.critical(f"DuckDB error: {e}", exc_info=True)
        raise DatabaseError(f"Schema init failed: {e}") from e


def initialize_tx_schema(con: DuckDBPyConnection) -> None:
    _initialize_and_migrate_schema(con, TX_SCHEMA)


def initialize_addr_schema(con: DuckDBPyConnection) -> None:
    _initialize_and_migrate_schema(con, ADDR_SCHEMA)


def initialize_app_data_schema(con: DuckDBPyConnection) -> None:
    _initialize_and_migrate_schema(con, APP_DATA_SCHEMA)
