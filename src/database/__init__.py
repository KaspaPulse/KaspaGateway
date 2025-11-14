# File: src/database/__init__.py
"""
Initializes the database module, exporting key classes and functions.
"""
from __future__ import annotations

from .database import (
    TransactionDB,
    AddressDB,
    AppDataDB,
)
from .db_manager import DatabaseManager
from .db_schema import (
    initialize_tx_schema,
    initialize_addr_schema,
    initialize_app_data_schema,
)

# Explicitly define what this module exports
__all__ = [
    "TransactionDB",
    "AddressDB",
    "AppDataDB",
    "DatabaseManager",
    "initialize_tx_schema",
    "initialize_addr_schema",
    "initialize_app_data_schema",
]


