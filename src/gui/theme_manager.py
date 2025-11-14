import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.gui.main_window import MainWindow
    from src.gui.config_manager import ConfigManager

logger = logging.getLogger(__name__)

THEME_MAP = {
    "system": "superhero",  # Defaulting 'System' to a consistent dark theme
    "light": "litera",
    "dark": "darkly"
}

class ThemeManager:
    """
    Manages the application's visual theme, allowing users to switch between
    available ttkbootstrap themes and persisting their choice.
    """
    def __init__(self, main_window: 'MainWindow', config_manager: 'ConfigManager'):
        self.main_window = main_window
        self.config_manager = config_manager
        logger.info("ThemeManager initialized.")

    def get_current_theme(self) -> str:
        """
        Gets the current theme from the configuration, converting old names if necessary
        for backward compatibility.
        """
        theme = self.config_manager.get_config().get("theme", "superhero").lower()
        return THEME_MAP.get(theme, theme) # Return new name if old is found, else return as-is

    def apply_theme(self, theme: str):
        """
        Applies a new theme to the application and saves the selection.
        """
        try:
            theme_lower = theme.lower()
            

            theme_lower = THEME_MAP.get(theme_lower, theme_lower)

            if theme_lower not in self.main_window.style.theme_names():
                logger.warning(f"Invalid theme '{theme_lower}', defaulting to superhero.")
                theme_lower = "superhero"
            

            self.main_window.style.theme_use(theme_lower)
            
            logger.info(f"Theme changed to: {theme_lower}")
            

            current_config = self.config_manager.get_config()
            if current_config.get("theme") != theme_lower:
                current_config["theme"] = theme_lower
                self.config_manager.save_config(current_config)

        except Exception as e:
            logger.error(f"Error applying theme '{theme}': {e}", exc_info=True)
