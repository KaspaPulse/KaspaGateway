#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main entry point for the KaspaGateway application.

This script initializes configuration, sets up logging, handles file locking,
initializes the main application class (KaspaApp), and runs the
Tkinter main event loop. It also establishes a Windows Job Object to ensure
clean termination of child processes.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
import tkinter as tk
import traceback
from tkinter import messagebox
from types import FrameType
from typing import Optional

# --- Path Setup ---
if not getattr(sys, "frozen", False):
    project_root: str = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
# --- End Path Setup ---

# --- Argument Parsing & Config Initialization ---
parser = argparse.ArgumentParser(description="KaspaGateway")
parser.add_argument(
    "--user-data-path",
    type=str,
    default=None,
    help="Specifies the directory for user data (config, logs, db).",
)

args, _ = parser.parse_known_args()

try:
    from src.config.config import CONFIG, initialize_config

    initialize_config(args.user_data_path)
except Exception as e:
    print(f"FATAL: Failed to initialize configuration: {e}")
    traceback.print_exc()
    sys.exit(1)
# --- End Config Initialization ---

# --- Logging Setup ---
try:
    from src.utils.logging_config import setup_logging

    setup_logging(
        level=CONFIG.get("log_level", "INFO"), log_path=CONFIG["paths"]["log"]
    )
except Exception as e:
    print(f"FATAL: Failed to set up logging: {e}")
    traceback.print_exc()
    sys.exit(1)

logger = logging.getLogger(__name__)
# --- End Logging Setup ---

# --- Main Application Imports ---
try:
    from src.core.app import KaspaApp
    from src.database.db_locker import acquire_all_locks, release_all_locks
    from src.utils.errors import KaspaError
except ImportError as e:
    logger.critical(f"Failed to import core application modules: {e}", exc_info=True)
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Import Error",
            f"Failed to load application components: {e}\nPlease check logs.",
        )
        root.destroy()
    except Exception:
        pass
    sys.exit(1)
# --- End Main Application Imports ---


def main() -> None:
    """
    Main application entry point.
    Initializes, sets up signal handlers, and runs the application.
    """

    # --- Job Object Management (for Windows) ---
    # This ensures that if the main app is force-killed (e.g., Task Manager),
    # all child processes (kaspad, ks_bridge) are terminated by the OS.

    # We will store the handle in the global CONFIG so controllers can access it.
    CONFIG["job_object_handle"] = None

    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            # Define necessary Windows structures for Job Objects
            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_ulonglong),
                    ("WriteOperationCount", ctypes.c_ulonglong),
                    ("OtherOperationCount", ctypes.c_ulonglong),
                    ("ReadTransferCount", ctypes.c_ulonglong),
                    ("WriteTransferCount", ctypes.c_ulonglong),
                    ("OtherTransferCount", ctypes.c_ulonglong),
                ]

            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                    ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            # Constants
            JobObjectExtendedLimitInformation: int = 9
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: int = 0x00002000

            def create_job_object() -> Optional[int]:
                """
                Creates a Windows Job Object and configures it to terminate all
                associated processes when the job handle is closed.
                """
                try:
                    kernel32 = ctypes.windll.kernel32
                    job_handle: int = kernel32.CreateJobObjectW(None, None)
                    if not job_handle:
                        logger.error(
                            f"Failed to create Job Object. Error code: {kernel32.GetLastError()}"
                        )
                        return None

                    limit_info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                    info_size: int = ctypes.sizeof(limit_info)

                    if not kernel32.QueryInformationJobObject(
                        job_handle,
                        JobObjectExtendedLimitInformation,
                        ctypes.byref(limit_info),
                        info_size,
                        None,
                    ):
                        logger.warning(
                            f"Could not query Job Object info. Error code: {kernel32.GetLastError()}. Proceeding anyway."
                        )

                    limit_info.BasicLimitInformation.LimitFlags = (
                        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                    )

                    if not kernel32.SetInformationJobObject(
                        job_handle,
                        JobObjectExtendedLimitInformation,
                        ctypes.byref(limit_info),
                        info_size,
                    ):
                        logger.error(
                            f"Failed to set Job Object info. Error code: {kernel32.GetLastError()}"
                        )
                        kernel32.CloseHandle(job_handle)
                        return None

                    logger.info(
                        f"Successfully created Job Object with handle: {job_handle}"
                    )
                    return job_handle
                except Exception as e:
                    logger.error(
                        f"An exception occurred while creating Job Object: {e}",
                        exc_info=True,
                    )
                    return None

            CONFIG["job_object_handle"] = create_job_object()

        except ImportError:
            logger.error("Failed to import ctypes, Job Object creation skipped.")
        except Exception as e:
            logger.error(f"Failed to create Job Object: {e}", exc_info=True)
    # --- End Job Object Management ---

    if not acquire_all_locks(CONFIG):
        logger.critical(
            "Failed to acquire database locks. Another instance may be running."
        )
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Application Locked",
                "Failed to acquire database lock. Another instance of KaspaGateway may already be running.",
            )
            root.destroy()
        except tk.TclError:
            pass
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
                and hasattr(app, "main_window")
                and app.main_window.winfo_exists()
                and hasattr(app.main_window, "transaction_manager")
            ):
                app.main_window.on_closing()
            else:
                sys.exit(0)
        except tk.TclError:
            pass
        except Exception as e:
            logger.error(f"Error during signal handling: {e}")
            sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, signal_handler)

    try:
        logger.info(f"--- KaspaGateway v{CONFIG.get('version')} Starting ---")

        start_init: float = time.perf_counter()
        app = KaspaApp()
        end_init: float = time.perf_counter()
        logger.info(
            f"PERF: KaspaApp() initialization took {end_init - start_init:.4f} seconds."
        )

        app.run()

    except (KaspaError, RuntimeError) as e:
        logger.critical(f"A critical application error occurred: {e}", exc_info=True)
        try:
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
        if "application has been destroyed" in str(e):
            logger.warning(f"TclError caught on shutdown: {e}")
        else:
            logger.critical(f"An unexpected TclError occurred: {e}", exc_info=True)
            sys.exit(1)

    except Exception as e:
        logger.critical(f"An unexpected fatal error occurred: {e}", exc_info=True)
        logger.critical(traceback.format_exc())
        sys.exit(1)

    finally:
        if app and hasattr(app, "shutdown"):
            app.shutdown()

        # The Job Object handle will be closed automatically by the OS when
        # this process terminates, which will trigger the child process kills.

        release_all_locks()

        logger.info("--- Application Shutdown ---")
        logging.shutdown()


if __name__ == "__main__":
    main()
