#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Provides a robust, process-aware file locking mechanism for DuckDB databases.

This utility creates .lock files alongside database files to prevent multiple
instances of the application from running simultaneously.

It critically handles stale locks left behind by crashed processes by:
1. Checking if the PID in the .lock file is still active.
2. If the PID is dead, it removes both the stale .lock file AND
   the associated .duckdb.wal file, which resolves the
   "database is locked" IOException on the next startup.
"""

from __future__ import annotations

import atexit
import logging
import os
from typing import Any, Dict, List, Optional

try:
    import psutil
except ImportError:
    print("Error: 'psutil' library not found. Please install it: pip install psutil")
    psutil = None  # type: ignore

from src.config.config import CONFIG
from src.utils.errors import DatabaseError

logger = logging.getLogger(__name__)

# Module-level state to track held locks
_held_locks: Dict[str, int] = {}  # {db_name: file_descriptor}
_lock_dir: str = ""


def _get_lock_path(db_name: str) -> str:
    """
    Returns the full path for a database's .lock file.
    """
    if not _lock_dir:
        _initialize_lock_dir(CONFIG)
    return os.path.join(_lock_dir, f"{db_name}.lock")


def _get_wal_path(db_name: str) -> str:
    """
    Returns the full path for a database's .wal file.
    """
    base_path: str = os.path.join(_lock_dir, db_name)
    return f"{base_path}.wal"


def _initialize_lock_dir(config: Dict[str, Any]) -> None:
    """
    Initializes the global lock directory variable.
    """
    global _lock_dir
    _lock_dir = config.get("paths", {}).get("database", ".")
    os.makedirs(_lock_dir, exist_ok=True)


def _cleanup_stale_lock(db_name: str, lock_path: str) -> bool:
    """
    Checks if a lock file is stale (from a dead PID) and cleans it up,
    including the .wal file.

    Returns:
        True if the lock was stale and cleaned up, False if it's held
        by an active process.
    """
    if not psutil:
        logger.error("psutil is not installed. Cannot check for stale locks.")
        raise DatabaseError("psutil library is required for lock management.")

    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            pid_str: str = f.read().strip()

        if not pid_str:
            raise ValueError("Lock file is empty.")
        
        pid: int = int(pid_str)

        if psutil.pid_exists(pid):
            # Process is still running, lock is valid.
            logger.warning(
                f"Database {db_name} is locked by an active process (PID: {pid})."
            )
            return False

        # Process is dead, lock is stale.
        logger.warning(
            f"Stale lock file found for {db_name} (PID: {pid}). Cleaning up..."
        )

    except (IOError, ValueError, psutil.Error) as e:
        logger.warning(
            f"Could not read or validate stale lock file {lock_path}: {e}. Assuming stale."
        )

    try:
        # Clean up the stale .lock file
        os.remove(lock_path)

        # CRITICAL: Clean up the associated .wal file (DuckDB recovery mechanism)
        wal_path: str = _get_wal_path(db_name)
        if os.path.exists(wal_path):
            os.remove(wal_path)
            logger.info(f"Removed stale WAL file: {wal_path}")

        return True

    except OSError as e:
        logger.error(f"Failed to clean up stale lock/WAL for {db_name}: {e}")
        return False


def acquire_lock(db_name: str) -> bool:
    """
    Attempts to acquire an exclusive, process-aware lock for a database.
    """
    if not _lock_dir:
        _initialize_lock_dir(CONFIG)

    lock_path: str = _get_lock_path(db_name)

    try:
        if os.path.exists(lock_path):
            if not _cleanup_stale_lock(db_name, lock_path):
                # Lock is valid and held by another process
                return False

        # At this point, no valid lock file exists
        # Attempt to create the lock file exclusively (O_EXCL ensures atomicity)
        # We need the file descriptor (fd) to ensure the file remains open/locked
        fd: int = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)

        # Write current PID to the lock file
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))

        _held_locks[db_name] = fd
        logger.debug(f"Acquired lock for {db_name}.")
        return True

    except FileExistsError:
        # Race condition: another process created the lock just now
        logger.warning(
            f"Lock for {db_name} acquired by another process during race condition."
        )
        return False
    except (IOError, OSError) as e:
        logger.error(f"Failed to acquire lock for {db_name}: {e}")
        return False


def release_lock(db_name: str) -> None:
    """
    Releases the lock for a specific database, cleaning up both .lock and .wal files.
    Safely handles file descriptor closure to avoid OSError 9 (Bad file descriptor).
    """
    if db_name not in _held_locks:
        return

    fd: int = _held_locks.pop(db_name)
    lock_path: str = _get_lock_path(db_name)
    wal_path: str = _get_wal_path(db_name)

    try:
        # Close the file handle
        # We catch OSError in case the OS has already invalidated the handle
        os.close(fd)
    except OSError as e:
        # Errno 9 is "Bad file descriptor", which means it's already closed.
        # This is benign during shutdown or rapid restart cycles.
        if e.errno != 9:
            logger.warning(f"Could not close lock file handle for {db_name}: {e}")

    try:
        # Remove the .lock file
        if os.path.exists(lock_path):
            os.remove(lock_path)
    except OSError as e:
        logger.error(f"Failed to remove lock file {lock_path}: {e}")

    try:
        # Remove the .wal file on clean exit to ensure clean startup
        if os.path.exists(wal_path):
            os.remove(wal_path)
            logger.debug(f"Cleanly removed WAL file: {wal_path}")
    except OSError as e:
        logger.error(f"Failed to remove WAL file {wal_path}: {e}")

    logger.debug(f"Released lock for {db_name}.")


def acquire_all_locks(config: Dict[str, Any]) -> bool:
    """
    Attempts to acquire locks for all databases defined in the config.
    """
    _initialize_lock_dir(config)

    db_filenames: Dict[str, str] = config.get("db_filenames", {})
    if not db_filenames:
        logger.error("No database filenames found in config. Cannot acquire locks.")
        return False

    locked_dbs: List[str] = []
    for db_name in db_filenames.values():
        if not acquire_lock(db_name):
            # Failed to get a lock, release all acquired locks and fail
            logger.critical(
                f"Failed to acquire lock for {db_name}. Another instance may be running."
            )
            release_all_locks()
            return False
        locked_dbs.append(db_name)

    logger.info(f"Successfully acquired locks for all databases: {locked_dbs}")
    # Register the cleanup function to run at Python exit
    atexit.register(release_all_locks)
    return True


def release_all_locks() -> None:
    """
    Releases all currently held database locks.
    """
    if not _held_locks:
        return

    logger.info("Releasing all database locks...")
    # Create a copy of keys as release_lock modifies the dict
    for db_name in list(_held_locks.keys()):
        release_lock(db_name)
    logger.info("All database locks released.")