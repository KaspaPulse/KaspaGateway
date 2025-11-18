import logging
from typing import Any, Dict, List

from src.database import AddressDB
from src.utils.errors import DatabaseError
from src.utils.formatting import mask_address

logger = logging.getLogger(__name__)


class AddressManager:
    """
    Provides a clean interface for UI components to interact with the address database.
    This class acts as a data access layer, abstracting the specific database calls
    and adding a layer of error handling.
    """

    def __init__(self, db: AddressDB) -> None:
        """
        Initializes the AddressManager.

        Args:
            db: An instance of AddressDB to manage.
        """
        self.db: AddressDB = db

    def get_all_addresses(self) -> List[Dict[str, Any]]:
        """
        Fetches all saved addresses.

        Returns:
            A list of address dictionaries, or an empty list on error.
        """
        try:
            # Corrected method name from get_addresses to get_all_addresses
            return self.db.get_all_addresses()
        except DatabaseError as e:
            logger.error(f"Failed to get addresses: {e}")
            return []
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while getting addresses: {e}",
                exc_info=True,
            )
            return []

    def save_address(self, address: str, name: str) -> bool:
        """
        Saves or updates an address with its name (alias).

        Args:
            address: The Kaspa address to save.
            name: The user-defined name for the address.

        Returns:
            True if successful, False otherwise.
        """
        try:
            self.db.save_address(address, name)
            return True
        except DatabaseError as e:
            logger.error(f"Failed to save address {mask_address(address)}: {e}")
            return False

    def delete_address(self, address: str) -> bool:
        """
        Deletes a specified address from the database.

        Args:
            address: The Kaspa address to delete.

        Returns:
            True if successful, False otherwise.
        """
        try:
            self.db.delete_address(address)
            return True
        except DatabaseError as e:
            logger.error(f"Failed to delete address {mask_address(address)}: {e}")
            return False
