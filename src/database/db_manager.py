import logging
import os
import shutil
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import duckdb

from src.config.config import CONFIG
from src.utils.i18n import translate

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages database file operations like info gathering, backup, restore,
    compaction, and deletion.
    """

    data_dir: str
    backup_dir: str

    def __init__(self) -> None:
        """Initializes the paths for data and backup directories."""
        self.data_dir: str = CONFIG["paths"]["database"]
        self.backup_dir: str = CONFIG["paths"]["backup"]
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
        logger.info(
            f"DB Manager initialized: Data='{self.data_dir}', Backups='{self.backup_dir}'"
        )

    def get_database_info(self) -> List[Dict[str, Any]]:
        """
        Gets database file info, accurately calculating size by including
        the .wal file if it exists.

        Returns:
            A list of dictionaries, each containing info about a DB file.
        """
        db_files: List[str] = [
            f for f in os.listdir(self.data_dir) if f.endswith(".duckdb")
        ]
        db_info: List[Dict[str, Any]] = []

        for db_name in db_files:
            file_path: str = os.path.join(self.data_dir, db_name)
            wal_path: str = f"{file_path}.wal"

            try:
                stat = os.stat(file_path)
                total_size_bytes: int = stat.st_size
                last_modified: datetime = datetime.fromtimestamp(stat.st_mtime)

                # Check for and add the size of the WAL file
                if os.path.exists(wal_path):
                    try:
                        wal_stat = os.stat(wal_path)
                        total_size_bytes += wal_stat.st_size
                    except Exception as wal_e:
                        logger.warning(
                            f"Could not get stats for WAL file {wal_path}: {wal_e}"
                        )

                db_info.append(
                    {
                        "name": db_name,
                        "size_kb": total_size_bytes / 1024.0,
                        "last_modified": last_modified,
                    }
                )
            except FileNotFoundError:
                logger.warning(f"File not found while gathering info: {file_path}")
            except Exception as e:
                logger.error(f"Could not get info for file {file_path}: {e}")

        return db_info

    def backup_database(self, db_name: str) -> Tuple[bool, str]:
        """
        Creates a binary backup of a database file using file copy (shutil).

        Args:
            db_name: The filename of the database to back up.

        Returns:
            A tuple (bool success, str message).
        """
        db_path: str = os.path.join(self.data_dir, db_name)
        backup_name: str = (
            f"{os.path.splitext(db_name)[0]}_{datetime.now().strftime('%Y%m%d%H%M%S')}.duckdb"
        )
        backup_path: str = os.path.join(self.backup_dir, backup_name)

        if not os.path.exists(db_path):
            return False, translate("Source database file not found.")

        logger.info(f"Starting file copy backup for '{db_name}' to '{backup_name}'...")
        try:
            # Use shutil.copy2 for robust binary file backup, avoiding DuckDB SQL parser/WinError 32 issues.
            shutil.copy2(db_path, backup_path)

            # Optionally copy the WAL file as well
            wal_path: str = f"{db_path}.wal"
            if os.path.exists(wal_path):
                shutil.copy2(wal_path, f"{backup_path}.wal")
                logger.debug("WAL file also copied.")

            logger.info(f"Backup successful for '{db_name}'.")
            return True, f"{translate('Backup created successfully')}: {backup_name}"
        except Exception as e:
            logger.error(f"Backup failed for {db_name}: {e}", exc_info=True)
            return False, f"{translate('Backup failed')}: {e}"

    def restore_database(
        self, backup_file_path: str, target_db_name: str
    ) -> Tuple[bool, str]:
        """
        Restores a database from a SPECIFIC backup file path chosen by the user.

        Args:
            backup_file_path: The full path to the backup file to restore from.
            target_db_name: The filename of the live database to overwrite (e.g., "Transactions.duckdb").

        Returns:
            A tuple (bool success, str message).
        """
        try:
            # Security Check: Ensure the backup path exists
            if not os.path.exists(backup_file_path):
                return False, translate("Restore failed: Backup file not found.")

            target_path: str = os.path.join(self.data_dir, target_db_name)
            backup_filename: str = os.path.basename(backup_file_path)

            # Security Check: Ensure the target path is inside the app's data directory (implicitly safe via self.data_dir)

            logger.info(
                f"Starting file copy restore for '{target_db_name}' from '{backup_filename}'..."
            )

            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except Exception as e:
                    logger.error(f"Could not remove target DB before restore: {e}")
                    return False, f"{translate('Failed to remove old database')}: {e}"

            # FIX: Use shutil.copy2 for robust binary file restoration
            shutil.copy2(backup_file_path, target_path)

            # Clean up potential remaining WAL files after restoring (DuckDB expects a clean state)
            wal_path: str = f"{target_path}.wal"
            if os.path.exists(wal_path):
                os.remove(wal_path)
                logger.debug("Removed stale WAL file after restoration.")

            logger.info(f"Restore successful for '{target_db_name}'.")
            return True, f"{translate('Database restored from')}: {backup_filename}"
        except Exception as e:
            logger.error(f"Restore failed for {target_db_name}: {e}", exc_info=True)
            return False, f"{translate('Restore failed')}: {e}"

    def compact_database(self, db_name: str) -> Tuple[bool, str]:
        """
        Compacts a database file using VACUUM and CHECKPOINT.

        Args:
            db_name: The filename of the database to compact.

        Returns:
            A tuple (bool success, str message).
        """
        db_path: str = os.path.join(self.data_dir, db_name)
        if not os.path.exists(db_path):
            return False, translate("Database file not found.")

        logger.info(f"Starting compaction for '{db_name}'...")
        try:
            with duckdb.connect(database=db_path) as con:
                con.execute("VACUUM")
                con.execute("CHECKPOINT")
            logger.info(f"Compaction successful for '{db_name}'.")
            return True, translate("Database compacted successfully.")
        except Exception as e:
            logger.error(f"Compaction failed for {db_name}: {e}", exc_info=True)
            return False, f"{translate('Compaction failed')}: {e}"

    def delete_database(self, db_name: str) -> Tuple[bool, str]:
        """
        Deletes a database file and its associated .wal file, then
        re-initializes an empty file.

        Args:
            db_name: The filename of the database to delete.

        Returns:
            A tuple (bool success, str message).
        """
        db_path: str = os.path.join(self.data_dir, db_name)
        wal_path: str = f"{db_path}.wal"

        logger.info(f"Attempting to delete database '{db_name}' and its .wal file.")

        try:
            if os.path.exists(db_path):
                size_before: float = os.path.getsize(db_path) / 1024.0
                logger.debug(
                    f"File '{db_name}' exists. Size before delete: {size_before:.2f} KB"
                )
                os.remove(db_path)
                logger.debug(f"File '{db_name}' deleted successfully.")
            else:
                logger.warning(f"File '{db_name}' not found at path, cannot delete.")

            if os.path.exists(wal_path):
                logger.debug(f"Also deleting associated WAL file for '{db_name}'.")
                os.remove(wal_path)
                logger.debug(f"WAL file for '{db_name}' deleted successfully.")

            # Re-initialize the database (create an empty file)
            logger.debug(f"Re-initializing empty database file for '{db_name}'...")
            with duckdb.connect(database=db_path) as con:
                pass  # Just create and close

            if os.path.exists(db_path):
                size_after: float = os.path.getsize(db_path) / 1024.0
                logger.debug(
                    f"File '{db_name}' re-initialized. Size after create: {size_after:.2f} KB"
                )

            logger.info(f"Database '{db_name}' was deleted and re-initialized.")
            return True, translate("Database deleted and re-initialized successfully.")
        except PermissionError as e:
            logger.error(
                f"DELETE FAILED: PermissionError for {db_name}. The file is likely still locked by the application. Error: {e}",
                exc_info=True,
            )
            return (
                False,
                f"{translate('Delete failed: PermissionError')}. {translate('Restart the application and try again.')}",
            )
        except Exception as e:
            logger.error(f"Delete failed for {db_name}: {e}", exc_info=True)
            return False, f"{translate('Delete failed')}: {e}"
