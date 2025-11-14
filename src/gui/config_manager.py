import logging
from typing import Dict, Any

from src.config.config import load_config, _save_config_file, DEFAULT_CONFIG, CONFIG

logger = logging.getLogger(__name__)

class ConfigManager:
    """
    Handles loading, saving, and providing access to the application's configuration data.
    It acts as a consistent interface for the rest of the GUI to manage settings.
    """

    def get_config(self) -> Dict[str, Any]:
        """Returns the current, globally loaded configuration dictionary."""
        return CONFIG

    def get_default_config(self) -> Dict[str, Any]:
        """Returns a copy of the default configuration dictionary, useful for 'Reset to Defaults'."""
        return DEFAULT_CONFIG.copy()

    def save_config(self, new_config: Dict[str, Any]) -> bool:
        """
        Saves the provided configuration to file and reloads it globally.
        This ensures that all parts of the application immediately use the new settings.
        """
        try:
            _save_config_file(new_config)

            CONFIG.clear()
            CONFIG.update(load_config())
            logger.info("Configuration saved and reloaded successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}", exc_info=True)
            return False