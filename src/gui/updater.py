#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handles application updates from GitHub, including download progress,
hash verification, and version checking.
Refactored to reduce cyclomatic complexity.
"""

import hashlib
import json
import logging
import os
import re
import threading
import zipfile
from datetime import datetime, timezone
from tkinter import StringVar, messagebox
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
        super().__init__(parent)
        self.title(title)
        self.minsize(width=500, height=100)
        self.resizable(False, False)
        self.after(20, self._center_window)
        self.transient(parent)
        self.grab_set()
        self.cancel_event = threading.Event()

        self.status_var = ttk.StringVar(value=translate("Initializing..."))
        ttk.Label(
            self, textvariable=self.status_var, wraplength=480, justify=LEFT
        ).pack(pady=10, padx=10, fill=X, expand=True)

        self.progress = ttk.Progressbar(
            self, mode="indeterminate", bootstyle="info-striped"
        )
        self.progress.pack(pady=5, padx=10, fill=X, expand=False)
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
        try:
            self.update_idletasks()
            toplevel = self.master.winfo_toplevel()
            if toplevel.winfo_viewable() == 0:
                self.after(20, self._center_window)
                return

            toplevel.update_idletasks()
            main_x, main_y = toplevel.winfo_x(), toplevel.winfo_y()
            main_w, main_h = toplevel.winfo_width(), toplevel.winfo_height()
            s_w, s_h = self.winfo_reqwidth(), self.winfo_reqheight()
            x = main_x + (main_w // 2) - (s_w // 2)
            y = main_y + (main_h // 2) - (s_h // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def update_status(self, message: str) -> None:
        if self.winfo_exists():
            self.after(0, self.status_var.set, message)
            self.update_idletasks()

    def show_success(self, message: str) -> None:
        if not self.winfo_exists():
            return
        self.progress.stop()
        self.progress.config(mode="determinate", value=100, bootstyle="success")
        self.cancel_button.pack_forget()
        self.ok_button.pack(pady=10)
        self.protocol("WM_DELETE_WINDOW", self.close_window)
        self.update_idletasks()

    def show_error(self, message: str) -> None:
        if not self.winfo_exists():
            return
        self.progress.stop()
        self.progress.config(mode="determinate", value=100, bootstyle="danger")
        self.cancel_button.pack_forget()
        self.ok_button.pack(pady=10)
        self.protocol("WM_DELETE_WINDOW", self.close_window)
        self.update_idletasks()

    def cancel(self) -> None:
        self.cancel_event.set()
        self.update_status(translate("Cancelling..."))
        if self.cancel_button.winfo_exists():
            self.cancel_button.config(state=DISABLED)
        self.after(500, self.close_window)

    def close_window(self) -> None:
        if self.winfo_exists():
            self.progress.stop()
            self.grab_release()
            self.destroy()


class ProgressTracker:
    def __init__(
        self,
        progress_window: Optional[DownloadProgressWindow],
        log_callback: Callable[[str], None],
    ) -> None:
        self.progress_window = progress_window
        self.log_callback = log_callback
        self.lines: List[str] = []
        self.lock = threading.Lock()

    def _update_gui(self, final_text: str) -> None:
        if self.progress_window and self.progress_window.winfo_exists():
            self.progress_window.update_status(final_text)

    def _build_text(self, error: bool = False, success: bool = False) -> str:
        with self.lock:
            processed: List[str] = []
            for i, line in enumerate(self.lines):
                prefix = "✅ "
                if i == len(self.lines) - 1:
                    if error:
                        prefix = "❌ "
                    elif not success:
                        prefix = "... "
                processed.append(f"{prefix}{line}")
            return "\n".join(processed)

    def add_step(self, message: str) -> None:
        self.log_callback(message)
        with self.lock:
            if "..." not in message or len(self.lines) == 0:
                self.lines.append(message)
            elif self.lines:
                self.lines[-1] = message
        self._update_gui(self._build_text())

    def add_log(self, message: str) -> None:
        self.log_callback(message)

    def complete_all(self, final_message: str) -> None:
        self.log_callback(final_message)
        final_text = self._build_text(success=True)
        self._update_gui(f"{final_text}\n\n✅ {final_message}")
        if self.progress_window and self.progress_window.winfo_exists():
            self.progress_window.after(
                0, self.progress_window.show_success, final_message
            )

    def fail_all(self, error_message: str) -> None:
        self.log_callback(error_message)
        final_text = self._build_text(error=True)
        self._update_gui(f"{final_text}\n\n❌ {error_message}")
        if self.progress_window and self.progress_window.winfo_exists():
            self.progress_window.after(
                0, self.progress_window.show_error, error_message
            )


class GitHubUpdater:
    """
    Refactored GitHubUpdater to reduce complexity.
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
        self.repo_api_url = repo_url
        self.asset_name_pattern = asset_name_pattern
        self.log_callback = log_callback
        self.is_running_check = is_running_check
        self.success_callback = success_callback
        self.cancel_event = cancel_event or threading.Event()
        self.progress_window = progress_window
        self.tracker = ProgressTracker(self.progress_window, log_callback)
        self.asset_name = ""

        self.multi_target_files = multi_target_files
        self.version_file_base_path = local_path
        self._initialize_paths(target_file_in_zip, local_path)

    def _initialize_paths(
        self, target_file_in_zip: Optional[str], local_path: Optional[str]
    ) -> None:
        if self.multi_target_files is None and target_file_in_zip and local_path:
            self.multi_target_files = [
                {"target_in_zip": target_file_in_zip, "local_path": local_path}
            ]
        elif self.multi_target_files and not local_path:
            for target in self.multi_target_files:
                if "local_path" in target and target["local_path"].endswith(".exe"):
                    self.version_file_base_path = target["local_path"]
                    break
        if self.multi_target_files is None:
            raise ValueError("Updater must be initialized with valid target files.")

    def run_update(self) -> None:
        """Main update logic, split into sub-steps."""
        try:
            if self.is_running_check():
                raise Exception(translate("Error: Process is running."))

            self.tracker.add_step(translate("Checking for updates..."))

            # 1. Resolve URLs
            asset_url, hash_url, remote_time, latest_version = (
                self._resolve_update_info()
            )

            # 2. Check if local version matches
            if self._is_local_up_to_date(remote_time):
                return

            # 3. Verify Hash Security
            expected_hash = self._verify_hash_security(hash_url)

            # 4. Download
            self.tracker.add_step(
                f"{translate('Downloading {}...').format(self.asset_name)}"
            )
            download_path = self._download_asset(asset_url, expected_hash)

            # 5. Extract
            self.tracker.add_step(translate("Download complete. Extracting files..."))
            self._extract_and_install(download_path, remote_time, latest_version)

            # 6. Success
            msg = translate("Update successful!")
            self.tracker.complete_all(msg)
            if self.success_callback:
                self.success_callback()

        except Exception as e:
            logger.error(f"Update failed: {e}", exc_info=True)
            self.tracker.fail_all(f"{translate('Update failed: {}.').format(str(e))}")
        finally:
            self._cleanup_temp_files()

    def _resolve_update_info(
        self,
    ) -> Tuple[str, Optional[str], Optional[datetime], str]:
        """Determines download URLs and version info."""
        if self.repo_api_url.endswith(".zip"):
            self.asset_name = os.path.basename(self.repo_api_url)
            self.tracker.add_step(
                f"{translate('Downloading from custom URL:')}\n{self.repo_api_url}"
            )
            return self.repo_api_url, None, datetime.now(timezone.utc), "custom"

        return self._fetch_github_release_info()

    def _fetch_github_release_info(self) -> Tuple[str, Optional[str], datetime, str]:
        response = requests.get(self.repo_api_url, timeout=10)
        response.raise_for_status()
        data = response.json()

        latest_version = data.get("tag_name", "unknown")
        self.tracker.add_log(
            f"{translate('Latest version found: {}').format(latest_version)}"
        )

        if not data.get("published_at"):
            raise Exception("Release has no 'published_at' date.")

        remote_time = datetime.fromisoformat(
            data["published_at"].replace("Z", "+00:00")
        )
        asset_url, hash_url = None, None

        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if re.match(self.asset_name_pattern, name):
                asset_url = asset.get("browser_download_url")
                self.asset_name = name
            if re.match(self.asset_name_pattern + r"\.sha256$", name):
                hash_url = asset.get("browser_download_url")

        if not asset_url:
            raise Exception(
                f"{translate('Error finding asset {} in release.').format(self.asset_name_pattern)}"
            )

        return asset_url, hash_url, remote_time, latest_version

    def _is_local_up_to_date(self, remote_time: Optional[datetime]) -> bool:
        if not self.version_file_base_path or not remote_time:
            return False

        v_path = f"{self.version_file_base_path}.version"
        if os.path.exists(v_path):
            local_time = datetime.fromtimestamp(
                os.path.getmtime(v_path), tz=timezone.utc
            )
            if local_time >= remote_time:
                msg = translate("Already up to date: {}").format(
                    os.path.basename(self.version_file_base_path)
                )
                self.tracker.add_log(msg)
                self.tracker.complete_all(msg)
                if self.success_callback:
                    self.success_callback()
                return True
        else:
            self.tracker.add_log(
                translate("Local version file not found. Proceeding with update.")
            )
        return False

    def _verify_hash_security(self, hash_url: Optional[str]) -> Optional[str]:
        if not hash_url:
            reason = (
                translate("Hash file not found for custom URL.")
                if self.repo_api_url.endswith(".zip")
                else translate("Hash verification file not found.")
            )
            self.tracker.add_step(f"WARNING: {reason}")

            if not messagebox.askyesno(
                translate("Security Warning"),
                f"{translate('Update security cannot be verified (missing hash file). This may be a risk. Continue anyway?')}\n\n{translate('Reason')}: {reason}",
            ):
                raise Exception(
                    translate("Update aborted by user for security reasons.")
                )

            self.tracker.add_log(
                translate("User accepted risk. Proceeding without hash verification.")
            )
            return None

        try:
            self.tracker.add_step(translate("Downloading hash file..."))
            resp = requests.get(hash_url, timeout=10)
            resp.raise_for_status()
            return resp.text.split()[0].strip()
        except Exception as e:
            raise Exception(
                f"{translate('Update failed: Could not download hash file. {0}.').format(e)}"
            )

    def _download_asset(self, url: str, expected_hash: Optional[str]) -> str:
        download_path = "kaspa_update.tmp_download"
        if self.version_file_base_path:
            download_path = f"{self.version_file_base_path}.tmp_download"

        os.makedirs(os.path.dirname(download_path), exist_ok=True)
        sha256 = hashlib.sha256()

        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(download_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if self.cancel_event.is_set():
                        raise Exception(translate("Download cancelled by user."))
                    f.write(chunk)
                    sha256.update(chunk)

        if expected_hash:
            calculated = sha256.hexdigest()
            if calculated.lower() != expected_hash.lower():
                raise Exception(
                    f"{translate('Hash mismatch!')} Expected {expected_hash}, Got {calculated}"
                )
            self.tracker.add_log(translate("Hash verified successfully."))
        else:
            self.tracker.add_log(translate("Skipping hash verification."))

        return download_path

    def _extract_and_install(
        self, zip_path: str, remote_time: Optional[datetime], version: str
    ) -> None:
        if not self.multi_target_files:
            return

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for target in self.multi_target_files:
                if self.cancel_event.is_set():
                    raise Exception(translate("Update cancelled by user."))

                target_in_zip = target["target_in_zip"]
                local_path = target["local_path"]
                self.tracker.add_log(
                    f"{translate('Extracting {0}...').format(target_in_zip)}"
                )

                try:
                    info = zip_ref.getinfo(target_in_zip)
                except KeyError:
                    raise Exception(
                        f"{translate('File not found in zip:')} {target_in_zip}"
                    )

                # Security Check: Path Traversal
                if ".." in info.filename or os.path.isabs(info.filename):
                    raise Exception("Security Error: Invalid file path in zip.")

                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with zip_ref.open(info) as source, open(local_path, "wb") as dest:
                    dest.write(source.read())

                if remote_time:
                    try:
                        os.utime(
                            local_path,
                            (remote_time.timestamp(), remote_time.timestamp()),
                        )
                    except:
                        pass

        # Update version file
        if self.version_file_base_path:
            try:
                v_path = f"{self.version_file_base_path}.version"
                with open(v_path, "w", encoding="utf-8") as f:
                    f.write(version)
            except Exception as e:
                self.tracker.add_log(
                    f"{translate('Warning: Could not write version file: {0}.').format(e)}"
                )

    def _cleanup_temp_files(self) -> None:
        tmp_path = "kaspa_update.tmp_download"
        if self.version_file_base_path:
            tmp_path = f"{self.version_file_base_path}.tmp_download"
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass


class VersionChecker:
    def __init__(
        self,
        asset_name: str,
        version_var: StringVar,
        date_var: StringVar,
        log_callback: Callable[[str], None],
        repo_url: str,
    ) -> None:
        self.asset_name = asset_name
        self.version_var = version_var
        self.date_var = date_var
        self.log_callback = log_callback
        self.repo_api_url = repo_url
        self.thread: Optional[threading.Thread] = None

    def _format_date(self, date_str: str) -> str:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00")).strftime(
                "%Y-%m-%d"
            )
        except:
            return date_str

    def _worker(self) -> None:
        try:
            self.log_callback(
                f"{translate('Checking latest version for {}...').format(self.asset_name)}"
            )
            resp = requests.get(self.repo_api_url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            ver = data.get("tag_name", "N/A")
            date_str = self._format_date(data.get("published_at", "N/A"))

            self.version_var.set(f"{translate('Latest Version')}: {ver}")
            self.date_var.set(f"{translate('Updated')}: {date_str}")
            self.log_callback(
                f"{translate('Latest version for {}: {} ({})').format(self.asset_name, ver, date_str)}"
            )
        except Exception as e:
            logger.error(f"Version check failed: {e}")
            self.version_var.set(f"{translate('Latest Version')}: {translate('Error')}")
            self.date_var.set(f"{translate('Updated')}: {translate('Error')}")

    def check_version(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.version_var.set(f"{translate('Latest Version')}: ...")
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
