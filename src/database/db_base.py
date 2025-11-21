from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple, TypeAlias

import duckdb

# Type alias for clarity
DuckDBPyConnection: TypeAlias = duckdb.DuckDBPyConnection

logger = logging.getLogger(__name__)


class ConnectionPool:
    """
    Manages a single shared connection for a DuckDB database file.

    DuckDB operates best in embedded mode with a single connection instance
    shared across threads. This class ensures only one writeable connection
    exists per database file to prevent transaction conflicts.
    """

    def __init__(self, db_path: str, max_connections: int = 1) -> None:
        """
        Initializes the connection manager.
        
        Args:
            db_path: The path to the DuckDB database file.
            max_connections: Ignored in this implementation to enforce singleton pattern.
        """
        self.db_path: str = db_path
        self.config: Dict[str, Any] = {}
        self._shared_connection: Optional[DuckDBPyConnection] = None
        self._lock: threading.Lock = threading.Lock()
        
        logger.debug(f"SingleConnectionManager initialized for {os.path.basename(db_path)}")

    def _create_connection(self, read_only: bool = False) -> DuckDBPyConnection:
        """Creates the underlying DuckDB connection."""
        try:
            base_name = os.path.basename(self.db_path)
            logger.debug(f"Opening persistent DB connection to {base_name}")
            # Always open as read/write to support all app functions via one connection
            return duckdb.connect(
                database=self.db_path, read_only=False, config=self.config
            )
        except Exception as e:
            logger.error(
                f"Failed to create DuckDB connection for {self.db_path}: {e}",
                exc_info=True,
            )
            raise ConnectionError(f"Failed to connect to {self.db_path}: {e}")

    def get_connection(self, read_only: bool = False) -> DuckDBPyConnection:
        """
        Returns the shared database connection.
        Initializes it if it doesn't exist.
        """
        with self._lock:
            if self._shared_connection is None:
                self._shared_connection = self._create_connection()
            return self._shared_connection

    def return_connection(self, conn: DuckDBPyConnection) -> None:
        """
        No-op: The connection is kept open for the lifetime of the application
        to avoid file locking overhead and transaction conflicts.
        """
        pass

    def close_all(self) -> None:
        """Closes the shared connection safely."""
        with self._lock:
            if self._shared_connection:
                base_name = os.path.basename(self.db_path)
                logger.info(f"Closing shared connection for {base_name}...")
                try:
                    self._shared_connection.close()
                except Exception as e:
                    logger.error(f"Error closing connection for {base_name}: {e}")
                finally:
                    self._shared_connection = None


class DatabaseManager:
    """
    Base class for database managers.
    Handles thread-safe query execution using a shared connection.
    """

    def __init__(self, db_path: str) -> None:
        if not db_path:
            raise ValueError("Database path cannot be None or empty.")

        self.db_path: str = db_path
        self.db_name: str = os.path.basename(db_path)
        
        # Use the singleton connection pool
        self.connection_pool: ConnectionPool = ConnectionPool(self.db_path)
        
        # Lock to serialize write operations across threads
        self._write_lock: threading.Lock = threading.Lock()

        logger.info(f"Database manager initialized for '{self.db_path}'")

    @contextmanager
    def connect(self, read_only: bool = False) -> Iterator[DuckDBPyConnection]:
        """
        Provides the shared database connection as a context manager.
        """
        conn: Optional[DuckDBPyConnection] = None
        try:
            conn = self.connection_pool.get_connection(read_only=read_only)
            yield conn
        except Exception as e:
            logger.error(
                f"Failed to access connection for '{self.db_path}': {e}",
                exc_info=True,
            )
            raise ConnectionError(f"Failed to access database connection: {e}")
        finally:
            # Connection is maintained by the pool, no closure here
            pass

    def execute_query(
        self, query: str, params: Tuple[Any, ...] = (), read_only: bool = False
    ) -> bool:
        """
        Executes a query. 
        Uses a lock to ensure only one thread writes to the shared connection at a time.
        """
        with self._write_lock:
            try:
                with self.connect(read_only=read_only) as conn:
                    conn.execute(query, params)
                return True
            except Exception as e:
                logger.error(
                    f"Query failed on {self.db_name}: {query} | Params: {params} | Error: {e}",
                    exc_info=True,
                )
                return False

    def fetch_one(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[Any]:
        """Fetches a single result from a query."""
        try:
            with self.connect(read_only=True) as conn:
                return conn.execute(query, params).fetchone()
        except Exception as e:
            logger.error(
                f"Fetch one query failed on {self.db_name}: {query} | Params: {params} | Error: {e}",
                exc_info=True,
            )
            return None

    def fetch_all(self, query: str, params: Tuple[Any, ...] = ()) -> List[Any]:
        """Fetches all results from a query."""
        try:
            with self.connect(read_only=True) as conn:
                return conn.execute(query, params).fetchall()
        except Exception as e:
            logger.error(
                f"Fetch all query failed on {self.db_name}: {query} | Params: {params} | Error: {e}",
                exc_info=True,
            )
            return []

    def close(self) -> None:
        """Closes the shared connection for this database instance."""
        logger.info(f"Shutting down database manager for {self.db_name}...")
        self.connection_pool.close_all()