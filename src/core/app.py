# File: src/core/app.py
"""
Defines the main application class that encapsulates the GUI
and main application logic.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from src.gui.main_window import MainWindow
from src.utils.errors import KaspaError

# Handle circular type hint for MainWindow if it needs KaspaApp
if TYPE_CHECKING:
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


class KaspaApp:
    """The main application class."""

    main_window: MainWindow

    def __init__(self) -> None:
        """Initializes the application and the main window."""
        try:
            logger.info("Initializing application core...")

            start_mw = time.perf_counter()
            self.main_window = MainWindow()
            end_mw = time.perf_counter()

            logger.info(
                f"PERF: MainWindow initialization took {end_mw - start_mw:.4f} seconds."
            )
            logger.info("KaspaApp initialized successfully.")

        except KaspaError as e:
            logger.critical(
                f"A critical, known error occurred during app initialization: {e}",
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.critical(
                f"An unexpected critical error occurred during initialization: {e}",
                exc_info=True,
            )
            raise

    def run(self) -> None:
        """Starts the Tkinter main event loop."""
        try:
            logger.info("Starting the application main event loop.")
            self.main_window.mainloop()
        except Exception as e:
            logger.critical(
                f"An unexpected error occurred in the main app loop: {e}", exc_info=True
            )
        finally:
            logger.info("Application event loop has terminated.")

    def shutdown(self) -> None:
        """Initiates a graceful shutdown of all application services."""
        logger.info("Initiating graceful shutdown of application services...")
        if hasattr(self, "main_window") and hasattr(
            self.main_window, "shutdown_services"
        ):
            # Ensure main_window has a shutdown_services method
            self.main_window.shutdown_services()
        logger.info("All services shut down gracefully.")
