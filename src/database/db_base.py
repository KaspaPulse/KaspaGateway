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
            logger.debug(
                f"Creating new DB connection to {base_name} (ReadOnly: {read_only})"
            )
            # Pass read_only as a direct argument
            return duckdb.connect(
                database=self.db_path, read_only=False, config=self.config
            )
        except Exception as e:
            logger.error(
                f"Failed to create new DuckDB connection for {self.db_path}: {e}",
                exc_info=True,
            )
            raise ConnectionError(f"Failed to connect to {self.db_path}: {e}")

    def get_connection(self, read_only: bool = False) -> DuckDBPyConnection:
        """
        Gets a connection from the pool.

        Note: All connections are created writeable (read_only=False) by default to avoid
        DuckDB's file locking conflicts when mixing read/write configs in the same process.
        """
        with self._lock:
            if not self._pool.empty():
                base_name = os.path.basename(self.db_path)
                logger.debug(
                    f"Getting connection from pool for {base_name}. (Pool size: {self._pool.qsize()})"
                )
                return self._pool.get()

            if self.connection_count < self.max_connections:
                self.connection_count += 1
                base_name = os.path.basename(self.db_path)
                logger.debug(
                    f"Pool empty, creating new connection ({self.connection_count}/{self.max_connections}) for {base_name}"
                )
                # All connections are created read-write by default to avoid conflicts
                return self._create_connection(read_only=False)

            base_name = os.path.basename(self.db_path)
            logger.warning(
                f"Connection pool for {base_name} is empty and max connections ({self.max_connections}) reached. Waiting..."
            )

        # If pool was empty and max connections reached, wait for one
        return self._pool.get(block=True, timeout=10)

    def return_connection(self, conn: DuckDBPyConnection) -> None:
        """
        No-op: The connection is kept open for the lifetime of the application
        to avoid file locking overhead and transaction conflicts.
        """
        with self._lock:
            base_name = os.path.basename(self.db_path)
            if self._pool.full():
                logger.debug(f"Pool full, closing returned connection for {base_name}.")
                conn.close()
                self.connection_count -= (
                    1  # Decrement count only when connection is closed
                )
            else:
                logger.debug(
                    f"Returning connection to pool for {base_name}. (Pool size: {self._pool.qsize() + 1})"
                )
                self._pool.put(conn)

    def close_all(self) -> None:
        """Closes the shared connection safely."""
        with self._lock:
            base_name = os.path.basename(self.db_path)
            logger.warning(
                f"Closing all ({self._pool.qsize()}) pooled connections for {base_name}..."
            )
            while not self._pool.empty():
                try:
                    self._shared_connection.close()
                except Exception as e:
                    logger.error(f"Error closing a connection: {e}")
            logger.info(
                f"All connections in pool for {base_name} closed. Connection count reset to 0."
            )
            self.connection_count = 0


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

        # Use a single connection pool per database file
        self.connection_pool: ConnectionPool = ConnectionPool(self.db_path)

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
                f"Failed to establish connection to DuckDB at '{self.db_path}': {e}",
                exc_info=True,
            )
            raise ConnectionError(f"Failed to establish database connection: {e}")
        finally:
            # Connection is maintained by the pool, no closure here
            pass

    def execute_query(
        self, query: str, params: Tuple[Any, ...] = (), read_only: bool = False
    ) -> bool:
        """Executes a query that does not return data (e.g., INSERT, UPDATE, CREATE)."""
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
        """Closes all connections in the pool for this specific database instance."""
        logger.info(f"Closing connection pools for {self.db_name}...")
        self.connection_pool.close_all()
