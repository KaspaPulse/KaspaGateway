#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handles application updates from GitHub, including download progress,
hash verification, and version checking.
"""

import hashlib
import json
import logging
import os
import re
import threading
import zipfile
from datetime import datetime, timezone
from tkinter import messagebox, StringVar
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
import ttkbootstrap as ttk
from ttkbootstrap.constants import DISABLED, LEFT, X

from src.utils.i18n import translate

logger = logging.getLogger(__name__)


class DownloadProgressWindow(ttk.Toplevel):
    """
    A modal Toplevel window that shows download/extraction progress
    with a checklist-style status label.
    """

    def __init__(self, parent: ttk.Window, title: str) -> None:
        """
        Initialize the progress window.

        Args:
            parent: The main application window.
            title: The title for the window.
        """
        super().__init__(parent)
        self.title(title)

        # Dynamic Sizing (Original functionality preserved)
        self.minsize(width=500, height=100)
        self.resizable(False, False)

        self.after(20, self._center_window)
        self.transient(parent)
        self.grab_set()
        self.cancel_event = threading.Event()

        # This label will now show a multi-line checklist
        self.status_var = ttk.StringVar(value=translate("Initializing..."))
        ttk.Label(
            self, textvariable=self.status_var, wraplength=480, justify=LEFT
        ).pack(pady=10, padx=10, fill=X, expand=True)

        self.progress = ttk.Progressbar(
            self, mode="indeterminate", bootstyle="info-striped"
        )
        self.progress.pack(
            pady=5, padx=10, fill=X, expand=False
        )
        self.progress.start(10)

        self.cancel_button = ttk.Button(
            self,
            text=translate("Cancel"),
            command=self.cancel,
            bootstyle="danger",
        )
        self.cancel_button.pack(pady=10)

        self.ok_button = ttk.Button(
            self,
            text=translate("OK"),
            command=self.close_window,
            bootstyle="success",
        )

        self.protocol("WM_DELETE_WINDOW", self.cancel)

    def _center_window(self) -> None:
        """Centers the window relative to its parent."""
        try:
            self.update_idletasks()
            toplevel = self.master.winfo_toplevel()
            if toplevel.winfo_viewable() == 0:
                self.after(20, self._center_window)
                return
            toplevel.update_idletasks()

            main_x, main_y = toplevel.winfo_x(), toplevel.winfo_y()
            main_width, main_height = toplevel.winfo_width(), toplevel.winfo_height()

            # Get the new dynamically calculated size
            s_width, s_height = self.winfo_reqwidth(), self.winfo_reqheight()
            x = main_x + (main_width // 2) - (s_width // 2)
            y = main_y + (main_height // 2) - (s_height // 2)

            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def update_status(self, message: str) -> None:
        """Thread-safe method to update the status label."""
        if self.winfo_exists():
            self.after(0, self.status_var.set, message)
            # Force window to recalculate size
            self.update_idletasks()

    def show_success(self, message: str) -> None:
        """Shows the final success state with OK button."""
        if not self.winfo_exists():
            return
        self.progress.stop()
        self.progress.config(mode="determinate", value=100, bootstyle="success")
        self.cancel_button.pack_forget()
        self.ok_button.pack(pady=10)
        self.protocol("WM_DELETE_WINDOW", self.close_window)
        self.update_idletasks()

    def show_error(self, message: str) -> None:
        """Shows the final error state with OK button."""
        if not self.winfo_exists():
            return
        self.progress.stop()
        self.progress.config(mode="determinate", value=100, bootstyle="danger")
        self.cancel_button.pack_forget()
        self.ok_button.pack(pady=10)
        self.protocol("WM_DELETE_WINDOW", self.close_window)
        self.update_idletasks()

    def cancel(self) -> None:
        """Signals the cancel event and closes the window."""
        self.cancel_event.set()
        self.update_status(translate("Cancelling..."))
        if self.cancel_button.winfo_exists():
            self.cancel_button.config(state=DISABLED)
        self.after(500, self.close_window)

    def close_window(self) -> None:
        """Closes and destroys the window."""
        if self.winfo_exists():
            self.progress.stop()
            self.grab_release()
            self.destroy()


class ProgressTracker:
    """
    Manages the checklist-style text for the DownloadProgressWindow
    and logs to the main console simultaneously.
    """

    def __init__(
        self,
        progress_window: Optional[DownloadProgressWindow],
        log_callback: Callable[[str], None],
    ) -> None:
        """
        Initialize the tracker.

        Args:
            progress_window: The DownloadProgressWindow instance.
            log_callback: The log function of the main tab.
        """
        self.progress_window = progress_window
        self.log_callback = log_callback
        self.lines: List[str] = []
        self.lock = threading.Lock()

    def _update_gui(self, final_text: str) -> None:
        """Internal thread-safe GUI update."""
        if self.progress_window and self.progress_window.winfo_exists():
            self.progress_window.update_status(final_text)

    def _build_text(self, error: bool = False, success: bool = False) -> str:
        """Constructs the checklist string from the lines list."""
        with self.lock:
            processed: List[str] = []
            for i, line in enumerate(self.lines):
                if i == len(self.lines) - 1:  # Last line
                    if error:
                        processed.append(f"❌ {line}")
                    elif success:
                        processed.append(f"✅ {line}")
                    else:
                        processed.append(f"... {line}")
                else:  # Completed lines
                    processed.append(f"✅ {line}")
            return "\n".join(processed)

    def add_step(self, message: str) -> None:
        """Adds a new step to the checklist (e.g., 'Downloading...')"""
        self.log_callback(message)

        with self.lock:
            # Don't add sub-steps (like individual file extractions) as new lines
            if "..." not in message or len(self.lines) == 0:
                self.lines.append(message)
            else:
                # Overwrite the last step if it's just logging
                if self.lines:
                    self.lines[-1] = message

        self._update_gui(self._build_text())

    def add_log(self, message: str) -> None:
        """Logs info to the main console without adding a new checklist step."""
        self.log_callback(message)

    def complete_all(self, final_message: str) -> None:
        """Marks all steps as complete and shows success state."""
        self.log_callback(final_message)
        final_text = self._build_text(success=True)
        self._update_gui(f"{final_text}\n\n✅ {final_message}")
        if self.progress_window and self.progress_window.winfo_exists():
            self.progress_window.after(
                0, self.progress_window.show_success, final_message
            )

    def fail_all(self, error_message: str) -> None:
        """Marks the last step as failed and shows error state."""
        self.log_callback(error_message)
        final_text = self._build_text(error=True)
        self._update_gui(f"{final_text}\n\n❌ {error_message}")
        if self.progress_window and self.progress_window.winfo_exists():
            self.progress_window.after(
                0, self.progress_window.show_error, error_message
            )


class GitHubUpdater:
    """
    Handles the logic of checking, downloading, verifying,
    and extracting updates from a GitHub release or custom URL.
    """

    def __init__(
        self,
        repo_url: str,
        asset_name_pattern: str,
        log_callback: Callable[[str], None],
        is_running_check: Callable[[], bool],
        target_file_in_zip: Optional[str] = None,
        local_path: Optional[str] = None,
        multi_target_files: Optional[List[Dict[str, str]]] = None,
        success_callback: Optional[Callable[[], None]] = None,
        show_success_popup: bool = True,
        cancel_event: Optional[threading.Event] = None,
        progress_window: Optional[DownloadProgressWindow] = None,
    ) -> None:

        self.repo_api_url: str = repo_url
        self.asset_name_pattern: str = asset_name_pattern
        self.is_running_check: Callable[[], bool] = is_running_check
        self.success_callback: Optional[Callable[[], None]] = success_callback
        self.show_success_popup: bool = show_success_popup
        self.cancel_event: threading.Event = cancel_event or threading.Event()
        self.asset_name: str = ""
        self.progress_window: Optional[DownloadProgressWindow] = progress_window

        self.tracker = ProgressTracker(self.progress_window, log_callback)

        self.multi_target_files: Optional[List[Dict[str, str]]] = multi_target_files
        self.version_file_base_path: Optional[str] = local_path

        # Logic to handle single vs multi-file definitions
        if self.multi_target_files is None and target_file_in_zip and local_path:
            self.multi_target_files = [
                {"target_in_zip": target_file_in_zip, "local_path": local_path}
            ]
        elif self.multi_target_files is not None and local_path:
            self.version_file_base_path = local_path
        elif self.multi_target_files is not None and not local_path:
            for target in self.multi_target_files:
                if "local_path" in target and target["local_path"].endswith(".exe"):
                    self.version_file_base_path = target["local_path"]
                    break

        if self.multi_target_files is None:
            raise ValueError(
                "Updater must be initialized with either "
                "target_file_in_zip/local_path or multi_target_files"
            )

    def run_update(self) -> None:
        """
        Executes the entire update process in the current thread.
        This should be run in a separate thread from the GUI.
        """
        try:
            if self.is_running_check():
                self.tracker.add_step(translate("Error: Process is running."))
                raise Exception(translate("Error: Process is running."))

            self.tracker.add_step(translate("Checking for updates..."))

            asset_url: Optional[str] = None
            hash_url: Optional[str] = None
            remote_time: Optional[datetime] = None
            latest_version: str = "unknown"
            found_hash_name: Optional[str] = None

            if self.repo_api_url.endswith(".zip"):
                # Handle custom ZIP URL
                asset_url = self.repo_api_url
                self.asset_name = os.path.basename(asset_url)
                remote_time = datetime.now(timezone.utc)
                latest_version = "custom"
                self.tracker.add_step(
                    f"{translate('Downloading from custom URL:')}\n{asset_url}"
                )
            else:
                # Handle GitHub API URL
                response = requests.get(self.repo_api_url, timeout=10)
                response.raise_for_status()
                release_data: Dict[str, Any] = response.json()
                latest_version = release_data.get("tag_name", "unknown")
                self.tracker.add_log(
                    f"{translate('Latest version found: {}').format(latest_version)}"
                )

                published_at_str = release_data.get("published_at")
                if not published_at_str:
                    raise Exception("Release has no 'published_at' date.")

                remote_time = datetime.fromisoformat(
                    published_at_str.replace("Z", "+00:00")
                )
                found_asset_name: Optional[str] = None

                for asset in release_data.get("assets", []):
                    asset_name = asset.get("name", "")
                    if re.match(self.asset_name_pattern, asset_name):
                        asset_url = asset.get("browser_download_url")
                        found_asset_name = asset_name

                    if re.match(self.asset_name_pattern + r"\.sha256$", asset_name):
                        hash_url = asset.get("browser_download_url")
                        found_hash_name = asset_name

                if not asset_url or not found_asset_name:
                    raise Exception(
                        f"{translate('Error finding asset {} in release.').format(self.asset_name_pattern)}"
                    )

                self.asset_name = found_asset_name
                self.tracker.add_step(
                    f"{translate('Downloading from URL:')}\n{asset_url}"
                )

                version_file_path: Optional[str] = None
                if self.version_file_base_path:
                    version_file_path = f"{self.version_file_base_path}.version"

                if version_file_path and os.path.exists(version_file_path):
                    local_mtime_timestamp = os.path.getmtime(version_file_path)
                    local_time = datetime.fromtimestamp(
                        local_mtime_timestamp, tz=timezone.utc
                    )

                    if local_time >= remote_time:
                        success_msg_local = translate(
                            "Already up to date: {}"
                        ).format(os.path.basename(self.version_file_base_path))
                        self.tracker.add_log(success_msg_local)
                        self.tracker.complete_all(success_msg_local)
                        if self.success_callback:
                            self.success_callback()
                        return
                else:
                    self.tracker.add_log(
                        translate("Local version file not found. Proceeding with update.")
                    )

            expected_hash: Optional[str] = None

            # Unified SHA256 Warning Logic
            if not hash_url:
                warning_reason = ""
                if self.repo_api_url.endswith('.zip'):
                    warning_reason = translate('Hash file not found for custom URL.')
                    self.tracker.add_step(f"WARNING: {warning_reason}")
                else:
                    warning_reason = translate('Hash verification file not found ({0}).').format(found_hash_name)
                    self.tracker.add_step(f"WARNING: {warning_reason}")

                # Always show the popup
                user_consent = messagebox.askyesno(
                    translate("Security Warning"),
                    f"{translate('Update security cannot be verified (missing hash file). This may be a risk. Continue anyway?')}\n\n"
                    f"{translate('Reason')}: {warning_reason}"
                )

                if not user_consent:
                    self.tracker.add_log(f"FATAL: {translate('User aborted update due to missing hash file.')}")
                    raise Exception(translate("Update aborted by user for security reasons."))
                else:
                    self.tracker.add_log(translate('User accepted risk. Proceeding without hash verification.'))
                    expected_hash = None
            else:
                # Hash URL *was* found, try to download it
                try:
                    self.tracker.add_step(
                        f"{translate('Downloading hash file {0}...').format(found_hash_name)}"
                    )
                    hash_response = requests.get(hash_url, timeout=10)
                    hash_response.raise_for_status()
                    expected_hash = hash_response.text.split()[0].strip()
                    self.tracker.add_log(f"Expected SHA256: {expected_hash}")
                except Exception as e:
                    error_msg = f"{translate('Update failed: Could not download hash file. {0}.').format(e)}"
                    self.tracker.add_log(f"FATAL: {error_msg}")
                    raise Exception(error_msg)
            # End SHA256 Logic

            self.tracker.add_step(
                f"{translate('Downloading {}...').format(self.asset_name)}"
            )

            download_path = "kaspa_update.tmp_download"
            if self.version_file_base_path:
                 download_path = f"{self.version_file_base_path}.tmp_download"

            os.makedirs(os.path.dirname(download_path), exist_ok=True)

            sha256_hash = hashlib.sha256()
            with requests.get(
                asset_url, stream=True, timeout=600, allow_redirects=True
            ) as r:
                r.raise_for_status()
                with open(download_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if self.cancel_event.is_set():
                            self.tracker.add_log(translate("Download cancelled."))
                            raise Exception(translate("Download cancelled by user."))

                        f.write(chunk)
                        sha256_hash.update(chunk)

            if expected_hash:
                calculated_hash = sha256_hash.hexdigest()
                if calculated_hash.lower() != expected_hash.lower():
                    self.tracker.add_log(
                        f"FATAL: {translate('Hash mismatch!')} Expected {expected_hash}, Got {calculated_hash}"
                    )
                    raise Exception(
                        f"{translate('Hash mismatch for {0}. Download aborted.').format(self.asset_name)}"
                    )
                self.tracker.add_log(translate("Hash verified successfully."))
            else:
                self.tracker.add_log(
                    f"{translate('Skipping hash verification as no valid hash was found for {}.').format(self.asset_name)}"
                )

            self.tracker.add_step(translate("Download complete. Extracting files..."))

            destination_dirs: set[str] = set()

            if self.multi_target_files is None:
                raise Exception("multi_target_files is not defined.")

            with zipfile.ZipFile(download_path, "r") as zip_ref:
                all_files_in_zip = zip_ref.namelist()

                for target in self.multi_target_files:
                    if self.cancel_event.is_set():
                        raise Exception(translate("Update cancelled by user."))

                    target_in_zip = target["target_in_zip"]
                    local_path = target["local_path"]

                    self.tracker.add_log(
                        f"{translate('Extracting {0}...').format(target_in_zip)}"
                    )

                    try:
                        target_info = zip_ref.getinfo(target_in_zip)
                    except KeyError:
                        self.tracker.add_log(
                            f"FATAL: {translate('File not found in zip:')} {target_in_zip}. "
                            f"{translate('Available files:')} {all_files_in_zip}"
                        )
                        raise Exception(
                            f"{translate('File not found in zip:')} {target_in_zip}"
                        )

                    destination_dir = os.path.dirname(local_path)
                    abs_destination_dir = os.path.abspath(destination_dir)
                    os.makedirs(abs_destination_dir, exist_ok=True)
                    destination_dirs.add(abs_destination_dir)

                    # Security Checks
                    normalized_target_info_filename = os.path.normpath(
                        target_info.filename
                    ).replace(os.path.sep, "/")
                    normalized_target_in_zip = os.path.normpath(
                        target_in_zip
                    ).replace(os.path.sep, "/")

                    if normalized_target_info_filename != normalized_target_in_zip:
                        self.tracker.add_log(
                            f"FATAL: {translate('Blocked potential path traversal attack:')} "
                            f"{target_info.filename} (Normalized: {normalized_target_info_filename}) "
                            f"vs {normalized_target_in_zip}"
                        )
                        raise Exception("Security Error: Invalid file path (Mismatch).")

                    abs_target_path = os.path.abspath(
                        os.path.join(
                            abs_destination_dir, os.path.basename(local_path)
                        )
                    )
                    if not abs_target_path.startswith(abs_destination_dir):
                        self.tracker.add_log(
                            f"FATAL: {translate('Blocked potential path traversal attack:')} {target_info.filename}"
                        )
                        raise Exception("Security Error: Invalid file path (Traversal).")
                    # End Security Checks

                    with zip_ref.open(target_info) as source_f:
                        with open(local_path, "wb") as target_f:
                            target_f.write(source_f.read())

            os.remove(download_path)

            if remote_time:
                # Try to set file modification times to the release time
                for dest_dir in destination_dirs:
                    try:
                        os.utime(dest_dir, (remote_time.timestamp(), remote_time.timestamp()))
                    except Exception:
                        pass
                for target in self.multi_target_files:
                    try:
                        os.utime(
                            target["local_path"],
                            (remote_time.timestamp(), remote_time.timestamp()),
                        )
                    except Exception:
                        pass

            # Write version file
            if self.version_file_base_path and (
                self.version_file_base_path.endswith("kaspad.exe")
                or self.version_file_base_path.endswith("ks_bridge.exe")
            ):
                try:
                    version_file_path = f"{self.version_file_base_path}.version"
                    with open(version_file_path, "w", encoding="utf-8") as vf:
                        vf.write(latest_version)
                    if remote_time:
                        os.utime(
                            version_file_path,
                            (remote_time.timestamp(), remote_time.timestamp()),
                        )
                except Exception as e:
                    self.tracker.add_log(
                        f"{translate('Warning: Could not write version file: {0}.').format(e)}"
                    )

            success_msg = translate("Update successful!")
            self.tracker.complete_all(success_msg)

            if self.success_callback:
                self.success_callback()

        except Exception as e:
            error_msg = f"{translate('Update failed: {}.').format(str(e))}"
            logger.error(f"Update failed for {self.asset_name}: {e}", exc_info=True)
            self.tracker.fail_all(error_msg)

        finally:
            tmp_download_path = "kaspa_update.tmp_download"
            if self.version_file_base_path:
                 tmp_download_path = f"{self.version_file_base_path}.tmp_download"

            if os.path.exists(tmp_download_path):
                try:
                    os.remove(tmp_download_path)
                except OSError:
                    pass


class VersionChecker:
    """
    Checks for the latest version of an asset on GitHub in a
    separate thread and updates StringVar variables.
    """

    def __init__(
        self,
        asset_name: str,
        version_var: StringVar,
        date_var: StringVar,
        log_callback: Callable[[str], None],
        repo_url: str,
    ) -> None:
        """
        Initialize the VersionChecker.

        Args:
            asset_name: The name of the asset to look for (e.g., "kaspad.exe").
            version_var: The StringVar for the latest version.
            date_var: The StringVar for the latest release date.
            log_callback: The log function of the main tab.
            repo_url: The GitHub API URL for the latest release.
        """
        self.asset_name: str = asset_name
        self.version_var: StringVar = version_var
        self.date_var: StringVar = date_var
        self.log_callback: Callable[[str], None] = log_callback
        self.repo_api_url: str = repo_url
        self.thread: Optional[threading.Thread] = None

    def _format_date(self, date_str: str) -> str:
        """Converts ISO date string to YYYY-MM-DD format."""
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return date_str

    def _worker(self) -> None:
        """
        The worker thread function that performs the web request
        and updates the StringVars.
        """
        try:
            self.log_callback(
                f"{translate('Checking latest version for {}...').format(self.asset_name)}"
            )
            response = requests.get(self.repo_api_url, timeout=10)
            response.raise_for_status()
            release_data: Dict[str, Any] = response.json()
            latest_version = release_data.get("tag_name", "N/A")
            latest_date = self._format_date(release_data.get("published_at", "N/A"))

            has_asset = False
            asset_pattern = self.asset_name

            # Specific patterns for known assets
            if self.asset_name == "kaspad.exe":
                asset_pattern = r"rusty-kaspa-v[\d\.]+-win64\.zip$"
            elif self.asset_name == "ks_bridge.exe":
                asset_pattern = r"ks_bridge-v[\d\.]+(-dev)?\.zip$"

            for asset in release_data.get("assets", []):
                if re.match(asset_pattern, asset.get("name", "")):
                    has_asset = True
                    break

            # Fallback for other assets
            if not has_asset and self.asset_name not in [
                "kaspad.exe",
                "ks_bridge.exe",
            ]:
                for asset in release_data.get("assets", []):
                    if asset.get("name") == self.asset_name:
                        has_asset = True
                        break

            if not has_asset:
                raise Exception(
                    f"{translate('Asset {} not in latest release.').format(self.asset_name)}"
                )

            self.version_var.set(f"{translate('Latest Version')}: {latest_version}")
            self.date_var.set(f"{translate('Updated')}: {latest_date}")
            self.log_callback(
                f"{translate('Latest version for {}: {} ({})').format(self.asset_name, latest_version, latest_date)}"
            )

        except Exception as e:
            logger.error(f"Failed to check version for {self.asset_name}: {e}")
            self.log_callback(
                f"{translate('Failed to check version for {}.').format(self.asset_name)}"
            )
            self.version_var.set(f"{translate('Latest Version')}: {translate('Error')}")
            self.date_var.set(f"{translate('Updated')}: {translate('Error')}")

    def check_version(self) -> None:
        """
        Starts the version check in a new thread if one is not
        already running.
        """
        if self.thread and self.thread.is_alive():
            return

        self.version_var.set(f"{translate('Latest Version')}: ...")
        self.date_var.set(f"{translate('Updated')}: ...")
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()