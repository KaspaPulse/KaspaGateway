#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main entry point for the KaspaGateway application.

This script initializes configuration, sets up logging, handles file locking,
initializes the main application class (KaspaApp), and runs the
Tkinter main event loop.
"""

from __future__ import annotations
import logging
import sys
import os
import time
import argparse
import tkinter as tk
from tkinter import messagebox
import traceback
import signal
from types import FrameType
from typing import Optional, List, Any

# --- Path Setup ---
# Ensure the src directory is in the path for running from source
if not getattr(sys, 'frozen', False):
    project_root: str = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
# --- End Path Setup ---

# --- Argument Parsing & Config Initialization ---
# Must be done before any other app imports that might rely on CONFIG
parser = argparse.ArgumentParser(description="KaspaGateway")
parser.add_argument(
    '--user-data-path',
    type=str,
    default=None,
    help='Specifies the directory for user data (config, logs, db).'
)
args, _ = parser.parse_known_args()

# Initialize configuration globally
try:
    from src.config.config import initialize_config, CONFIG
    initialize_config(args.user_data_path)
except Exception as e:
    # Fallback for critical config error
    print(f"FATAL: Failed to initialize configuration: {e}")
    traceback.print_exc()
    sys.exit(1)
# --- End Config Initialization ---

# --- Logging Setup ---
# Must be done after config init
try:
    from src.utils.logging_config import setup_logging
    setup_logging(level=CONFIG.get("logging_level", "INFO"), log_path=CONFIG['paths']['log'])
except Exception as e:
    print(f"FATAL: Failed to set up logging: {e}")
    traceback.print_exc()
    sys.exit(1)

logger = logging.getLogger(__name__)
# --- End Logging Setup ---

# --- Main Application Imports ---
# These must come AFTER config and logging are set up
try:
    from src.core.app import KaspaApp
    from src.utils.errors import KaspaError
    from src.database.db_locker import acquire_all_locks, release_all_locks
except ImportError as e:
    logger.critical(f"Failed to import core application modules: {e}", exc_info=True)
    # Use Tkinter for a final error message if possible
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Import Error", f"Failed to load application components: {e}\nPlease check logs.")
        root.destroy()
    except Exception:
        pass # If Tkinter fails, we already logged to console
    sys.exit(1)
# --- End Main Application Imports ---


def main() -> None:
    """
    Main application entry point.
    Initializes, sets up signal handlers, and runs the application.
    """
    
    # 1. Acquire Database Locks
    # This must be the first step to prevent multiple instances
    # and to clean up stale .wal files from a previous crash.
    if not acquire_all_locks(CONFIG):
        logger.critical("Failed to acquire database locks. Another instance may be running.")
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Application Locked",
                "Failed to acquire database lock. Another instance of KaspaGateway may already be running."
            )
            root.destroy()
        except tk.TclError:
            pass  # In case Tkinter itself fails
        except Exception as e:
            logger.error(f"Could not show final error messagebox: {e}")
        sys.exit(1)
        
    logger.info("Database locks acquired successfully.")

    app: Optional[KaspaApp] = None

    def signal_handler(sig: int, frame: Optional[FrameType]) -> None:
        """Handles graceful shutdown on SIGINT/SIGTERM."""
        logger.warning(f"Signal {sig} detected. Initiating graceful shutdown.")
        try:
            if (
                app
                and hasattr(app, 'main_window')
                and app.main_window.winfo_exists()
                and hasattr(app.main_window, 'transaction_manager')
            ):
                # Trigger the same logic as closing the window
                app.main_window.on_closing()
            else:
                # App not fully initialized, just exit
                sys.exit(0)
        except tk.TclError:
            pass  # Application is already being destroyed
        except Exception as e:
            logger.error(f"Error during signal handling: {e}")
            sys.exit(1)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 2. Initialize the Application
        logger.info(f"--- KaspaGateway v{CONFIG.get('version')} Starting ---")

        start_init = time.perf_counter()
        app = KaspaApp()
        end_init = time.perf_counter()
        logger.info(f"PERF: KaspaApp() initialization took {end_init - start_init:.4f} seconds.")

        # 3. Run the Application
        app.run()

    except (KaspaError, RuntimeError) as e:
        logger.critical(f"A critical application error occurred: {e}", exc_info=True)
        try:
            # Fallback error display if GUI fails
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("KaspaGateway - Fatal Error", str(e))
            root.destroy()
        except Exception as exc:
            logger.error(f"Could not show final error messagebox: {exc}")
        sys.exit(1)
    
    except KeyboardInterrupt:
        logger.info("Application terminated by user (KeyboardInterrupt).")
    
    except tk.TclError as e:
        # Catch TclError on shutdown
        if "application has been destroyed" in str(e):
            logger.warning(f"TclError caught on shutdown: {e}")
        else:
            logger.critical(f"An unexpected TclError occurred: {e}", exc_info=True)
            sys.exit(1)
    
    except Exception as e:
        # Catchall for any other unexpected fatal error
        logger.critical(f"An unexpected fatal error occurred: {e}", exc_info=True)
        logger.critical(traceback.format_exc())
        sys.exit(1)
        
    finally:
        # 4. Shutdown
        if app and hasattr(app, 'shutdown'):
            app.shutdown()
        
        # This is registered with atexit, but we call it manually
        # to ensure locks are released even if atexit fails.
        release_all_locks() 
        
        logger.info("--- Application Shutdown ---")
        logging.shutdown()


if __name__ == "__main__":
    main()



