from __future__ import annotations

import logging
import os
import queue
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, TypeAlias, Tuple

import duckdb

# Type alias for clarity
DuckDBPyConnection: TypeAlias = duckdb.DuckDBPyConnection

logger = logging.getLogger(__name__)


class ConnectionPool:
    """
    Manages a pool of connections for a single DuckDB database file.

    This pool handles DuckDB's limitation of (by default) not allowing
    multiple connections from the same process to a writeable file by
    managing a single set of connections.
    """

    def __init__(self, db_path: str, max_connections: int = 5):
        """
        Initializes the connection pool.

        Args:
            db_path: The path to the DuckDB database file.
            max_connections: The maximum number of connections to keep in the pool.
        """
        self.db_path: str = db_path
        self.max_connections: int = max_connections
        self.config: Dict[str, Any] = {}  # For any other DuckDB config options
        self._pool: queue.Queue[DuckDBPyConnection] = queue.Queue(
            maxsize=max_connections
        )
        self._lock: threading.Lock = threading.Lock()
        self.connection_count: int = 0
        logger.debug(f"ConnectionPool initialized for {os.path.basename(db_path)}")

    def _create_connection(self, read_only: bool = False) -> DuckDBPyConnection:
        """Creates a new database connection."""
        try:
            base_name = os.path.basename(self.db_path)
            logger.debug(f"Creating new DB connection to {base_name} (ReadOnly: {read_only})")
            # Pass read_only as a direct argument
            return duckdb.connect(
                database=self.db_path, read_only=read_only, config=self.config
            )
        except Exception as e:
            logger.error(f"Failed to create new DuckDB connection for {self.db_path}: {e}", exc_info=True)
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
                logger.debug(f"Getting connection from pool for {base_name}. (Pool size: {self._pool.qsize()})")
                return self._pool.get()

            if self.connection_count < self.max_connections:
                self.connection_count += 1
                base_name = os.path.basename(self.db_path)
                logger.debug(f"Pool empty, creating new connection ({self.connection_count}/{self.max_connections}) for {base_name}")
                # All connections are created read-write by default to avoid conflicts
                return self._create_connection(read_only=False)

            base_name = os.path.basename(self.db_path)
            logger.warning(f"Connection pool for {base_name} is empty and max connections ({self.max_connections}) reached. Waiting...")
    
        # If pool was empty and max connections reached, wait for one
        return self._pool.get(block=True, timeout=10)

    def return_connection(self, conn: DuckDBPyConnection) -> None:
        """
        Returns a connection to the pool or closes it if the pool is full.
        Also decrements the connection count when closing.
        """
        with self._lock:
            base_name = os.path.basename(self.db_path)
            if self._pool.full():
                logger.debug(f"Pool full, closing returned connection for {base_name}.")
                conn.close()
                self.connection_count -= 1  # Decrement count only when connection is closed
            else:
                logger.debug(f"Returning connection to pool for {base_name}. (Pool size: {self._pool.qsize() + 1})")
                self._pool.put(conn)

    def close_all(self) -> None:
        """Closes all connections currently in the pool and resets the count."""
        with self._lock:
            base_name = os.path.basename(self.db_path)
            logger.warning(f"Closing all ({self._pool.qsize()}) pooled connections for {base_name}...")
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    conn.close()
                except queue.Empty:
                    break
                except Exception as e:
                    logger.error(f"Error closing a connection: {e}")
            logger.info(f"All connections in pool for {base_name} closed. Connection count reset to 0.")
            self.connection_count = 0


class DatabaseManager:
    """
    Base class for database managers.
    Each subclass (TransactionDB, AddressDB, etc.) will create its own
    instance of this class and its own connection pool.
    """

    def __init__(self, db_path: str):
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
        Provides a database connection from the pool as a context manager.
        Note: The read_only flag is passed to get_connection but may be
        ignored by the pool to maintain connection compatibility.
        """
        conn: Optional[DuckDBPyConnection] = None
        try:
            conn = self.connection_pool.get_connection(read_only=read_only)
            yield conn
        except Exception as e:
            logger.error(f"Failed to establish connection to DuckDB at '{self.db_path}': {e}", exc_info=True)
            raise ConnectionError(f"Failed to establish database connection: {e}")
        finally:
            if conn:
                self.connection_pool.return_connection(conn)

    def execute_query(self, query: str, params: Tuple[Any, ...] = (), read_only: bool = False) -> bool:
        """Executes a query that does not return data (e.g., INSERT, UPDATE, CREATE)."""
        try:
            with self.connect(read_only=read_only) as conn:
                conn.execute(query, params)
            return True
        except Exception as e:
            logger.error(f"Query failed on {self.db_name}: {query} | Params: {params} | Error: {e}", exc_info=True)
            return False

    def fetch_one(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[Any]:
        """Fetches a single result from a query."""
        try:
            with self.connect(read_only=True) as conn:
                return conn.execute(query, params).fetchone()
        except Exception as e:
            logger.error(f"Fetch one query failed on {self.db_name}: {query} | Params: {params} | Error: {e}", exc_info=True)
            return None

    def fetch_all(self, query: str, params: Tuple[Any, ...] = ()) -> List[Any]:
        """Fetches all results from a query."""
        try:
            with self.connect(read_only=True) as conn:
                return conn.execute(query, params).fetchall()
        except Exception as e:
            logger.error(f"Fetch all query failed on {self.db_name}: {query} | Params: {params} | Error: {e}", exc_info=True)
            return []

    def close(self) -> None:
        """Closes all connections in the pool for this specific database instance."""
        logger.info(f"Closing connection pools for {self.db_name}...")
        self.connection_pool.close_all()