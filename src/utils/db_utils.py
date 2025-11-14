#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database utility functions, including decorators for error handling.
"""

import logging
import functools
import duckdb
from duckdb import CatalogException, BinderException
from typing import Callable, Any, TypeVar, TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from src.database.db_base import DatabaseManager

# Define the type alias for runtime type hint parsing
DuckDBPyConnection: TypeAlias = duckdb.DuckDBPyConnection

logger = logging.getLogger(__name__)

# Create a TypeVar to preserve the function's signature in the decorator
T = TypeVar('T')

def retry_on_schema_error(schema_init_func: Callable[[DuckDBPyConnection], None]) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator factory: If a function fails due to a schema error (e.g., table missing),
    it runs the schema_init_func to fix the schema, then retries the function once.
    
    Args:
        schema_init_func: The function to call to initialize/fix the schema 
                          (e.g., initialize_tx_schema).
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        """The actual decorator."""
        
        @functools.wraps(func)
        def wrapper(self: 'DatabaseManager', *args: Any, **kwargs: Any) -> T:
            """
            Wrapper function that adds the retry logic.
            'self' is expected to be an instance of DatabaseManager or its subclass.
            """
            try:
                # Try the original function first
                return func(self, *args, **kwargs)
            except (CatalogException, BinderException) as e:
                # CatalogException or BinderException usually happens if table/column doesn't exist
                error_str = str(e).lower()
                if "does not exist" in error_str or "no such table" in error_str or "column" in error_str:
                    
                    db_path = getattr(self, 'db_path', 'unknown_db')
                    
                    logger.warning(f"Schema error in {func.__name__} for {db_path}: {e}. Retrying after re-initializing schema...")
                    try:
                        # Fix the schema by getting a connection and calling the init function
                        with self.connect() as con:
                            schema_init_func(con)
                        
                        # Retry the original function one more time
                        return func(self, *args, **kwargs)
                    except Exception as e2:
                        logger.error(f"Failed to re-initialize schema or retry function {func.__name__}: {e2}", exc_info=True)
                        raise e2 # Raise the second error
                else:
                    # Wasn't a "does not exist" error, re-raise it
                    raise e
            except Exception as e:
                # Any other unexpected error
                logger.error(f"Unexpected error in decorated function {func.__name__}: {e}", exc_info=True)
                raise e
        return wrapper
    return decorator