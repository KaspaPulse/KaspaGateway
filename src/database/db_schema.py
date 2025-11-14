#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Defines the database schemas for all DuckDB files and provides
functions for schema initialization and migration.

This module expects to be called with an active DuckDB connection
and does not create its own connections.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, Set, TYPE_CHECKING

import duckdb
from duckdb import CatalogException, BinderException

from src.config.config import SUPPORTED_CURRENCIES
from src.utils.errors import DatabaseError

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)

# --- Schema Definitions ---

# Dynamically create column definitions for fiat currencies
price_cols: str = ", ".join([f'"{c}" DOUBLE' for c in SUPPORTED_CURRENCIES])
value_cols: str = ", ".join([f'"value_{c}" DOUBLE' for c in SUPPORTED_CURRENCIES])

# Known column sets for reference
KNOWN_PRICE_CACHE_COLS: Set[str] = set(SUPPORTED_CURRENCIES)
KNOWN_TX_COLS: Set[str] = {
    "txid",
    "address",
    "direction",
    "from_address",
    "to_address",
    "amount",
    "block_height",
    "timestamp",
    "type",
}

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
            created_at BIGINT NOT NULL DEFAULT (EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::BIGINT)
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

# --- End Schema Definitions ---


def _initialize_and_migrate_schema(
    con: DuckDBPyConnection, schema_dict: Dict[str, str]
) -> None:
    """
    Internal function to create tables, sequences, and migrate columns
    for a database using a provided connection.
    """
    try:
        # 1. Initialization: Create all tables and sequences
        for key, create_sql in schema_dict.items():
            con.execute(create_sql)

        # 2. Migration: Check for missing tables/columns
        existing_tables_result = con.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
        existing_tables = {table[0] for table in existing_tables_result}

        tables_in_schema = [
            name for name, sql in schema_dict.items() if "CREATE TABLE" in sql
        ]

        for table_name in tables_in_schema:
            if table_name not in existing_tables:
                # This should have been caught by the init step,
                # but we run it again for safety.
                logger.warning(
                    f"Migration: Table '{table_name}' not found. "
                    "Creating it now."
                )
                seq_key = f"seq_{table_name}"
                if seq_key in schema_dict:
                    con.execute(schema_dict[seq_key])
                con.execute(schema_dict[table_name])
                continue

            # Table exists, check its columns
            try:
                existing_cols_result = con.execute(
                    f"SELECT column_name FROM information_schema.columns "
                    f"WHERE table_name = '{table_name}'"
                ).fetchall()
                
                existing_cols = {col[0].lower() for col in existing_cols_result}
                create_sql = schema_dict[table_name]

                # Regex to find all column definitions in the CREATE statement
                # Finds: (full_col_name, col_name_only, col_type)
                required_cols_tuples = re.findall(
                    r'(\"?(\w+)\"?)\s+(VARCHAR|DOUBLE|BIGINT|UBIGINT|BOOLEAN|JSON|TIMESTAMP)',
                    create_sql,
                    re.IGNORECASE,
                )

                for full_col_name, col_name_only, col_type in required_cols_tuples:
                    if col_name_only.lower() not in existing_cols:
                        logger.warning(
                            f"Migration: Adding column {full_col_name} "
                            f"({col_type.upper()}) to table '{table_name}'."
                        )
                        con.execute(
                            f'ALTER TABLE "{table_name}" '
                            f"ADD COLUMN {full_col_name} {col_type.upper()};"
                        )
            except duckdb.Error as table_error:
                logger.warning(
                    f"Could not check table '{table_name}' for column "
                    f"migration. Error: {table_error}"
                )
                continue

    except duckdb.Error as e:
        logger.critical(
            f"CRITICAL: DuckDB error during schema init/migration: {e}",
            exc_info=True,
        )
        raise DatabaseError(f"Failed to initialize/migrate schema: {e}") from e


# --- Public Initializer Functions ---
# These are used by DatabaseManager instances and the retry decorator

def initialize_tx_schema(con: DuckDBPyConnection) -> None:
    """Public initializer for Transaction schema."""
    _initialize_and_migrate_schema(con, TX_SCHEMA)


def initialize_addr_schema(con: DuckDBPyConnection) -> None:
    """Public initializer for Address schema."""
    _initialize_and_migrate_schema(con, ADDR_SCHEMA)


def initialize_app_data_schema(con: DuckDBPyConnection) -> None:
    """Public initializer for AppData schema."""
    _initialize_and_migrate_schema(con, APP_DATA_SCHEMA)



