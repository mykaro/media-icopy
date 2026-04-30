"""MTP implementation of FileSource using Windows Shell API (pywin32)."""

import os
import shutil
import tempfile
import logging
import time
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any, BinaryIO

# Only import win32com here, as per rules
try:
    import win32com.client
    import pythoncom
except ImportError:
    win32com = None  # type: ignore
    pythoncom = None  # type: ignore

# Removed i18n import as adapters shouldn't depend on UI localization
from ..domain.models import RemoteFile
from ..domain.exceptions import TransientError, FatalError, DeviceDisconnectedError
from .cleanup_stream import CleanupStream

# Shell API Constants
SSF_DRIVES = 17
SHCNE_ASSOCCHANGED = 0x08000000
SHCNF_IDLIST = 0x0000
HWND_BROADCAST = 0xFFFF
WM_DEVICECHANGE = 0x0219
DBT_DEVNODES_CHANGED = 0x0007
FOF_SILENT_NO_UI = 4 | 16 | 1024  # FOF_SILENT | FOF_NOCONFIRMATION | FOF_NOERRORUI

# Copy & Retry Configuration
REPORT_INTERVAL_FILES = 20
COPY_START_RETRIES = 200
COPY_START_RETRY_DELAY = 0.05
COPY_WAIT_RETRIES = 1200
COPY_WAIT_RETRY_DELAY = 0.1
STABLE_SIZE_CHECKS = 3  # require N consecutive stable reads for unknown-size files

logger = logging.getLogger(__name__)


class MTPDeviceRegistry:
    """Registry for discovering and managing MTP devices."""

    @staticmethod
    def list_available_devices() -> list[str]:
        """Lists all portable devices visible in 'This PC'.

        Returns:
            A list of strings representing the names of available devices.
        """
        try:
            # We don't want to fail if pythoncom is not available in some envs
            if pythoncom:
                pythoncom.CoInitialize()  # type: ignore

            shell = win32com.client.Dispatch("Shell.Application")  # type: ignore
            this_pc = shell.NameSpace(SSF_DRIVES)
            if not this_pc:
                return []

            devices = []
            for item in this_pc.Items():
                # Portable devices usually are folders without a local filesystem path
                if item.IsFolder and not os.path.exists(item.Path):
                    devices.append(item.Name)
            return sorted(devices)
        except Exception as e:
            logger.debug(f"Error listing devices: {e}")
            return []

    @staticmethod
    def refresh_shell_cache() -> None:
        """
        Broadcasts shell notifications to force Windows to invalidate the MTP
        device cache. Call this after a device reconnect to ensure the Shell
        namespace reflects the current device state.

        This simulates what Explorer restart does, but without killing explorer.exe.
        Not guaranteed to work in 100% of cases — depends on Windows MTP stack version.
        """
        try:
            import ctypes

            # 1. Notify shell that namespace associations changed → triggers re-enumeration
            ctypes.windll.shell32.SHChangeNotify(
                SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None
            )

            # 2. Broadcast device-change event to all windows (including Explorer)
            ctypes.windll.user32.PostMessageW(
                HWND_BROADCAST, WM_DEVICECHANGE, DBT_DEVNODES_CHANGED, 0
            )
        except (OSError, RuntimeError) as e:
            logger.debug(f"Shell cache refresh failed (non-critical): {e}")
            pass  # Non-critical — fail silently, the user can retry manually


class MTPFileSource:
    """
    Accesses iPhone files via MTP using Windows Shell API.

    Navigates to 'This PC' -> [iPhone Name] -> 'Internal Storage' -> [source_folder].
    """

    def __init__(self, device_name: str, source_folder: str = "DCIM"):
        if win32com is None:
            raise FatalError("pywin32 is not installed or not supported on this OS.")

        self.device_name = device_name
        self.source_folder = source_folder
        self._shell = win32com.client.Dispatch("Shell.Application")  # type: ignore
        self._device_folder = None  # Cache for the device folder object
        self._folder_cache: dict[str, Any] = {}

        # State for reporting
        self._scanned_count = 0
        self._skipped_aae_count = 0

    def list_subfolders(self, relative_path: str = "") -> list[str]:
        """Returns a list of subfolder names for a given relative path.

        Args:
            relative_path: The relative path to list subfolders for.

        Returns:
            A list of subfolder names.
        """
        device_folder = self._get_device_folder()
        if not device_folder:
            return []

        # If relative_path is empty, we list the root of the device (e.g. Internal Storage)
        target = (
            self._resolve_path(device_folder, relative_path)
            if relative_path
            else device_folder
        )
        if not target:
            # If resolve fails, maybe we are listing the root itself which might have items
            target = device_folder

        try:
            folder_names = [item.Name for item in target.Items() if item.IsFolder]
            return sorted(folder_names)
        except (AttributeError, RuntimeError, Exception) as e:
            logger.debug(f"Error listing subfolders at '{relative_path}': {e}")
            return []

    def _get_device_folder(self) -> Any | None:
        """Finds the iPhone Shell Folder with caching."""
        if self._device_folder:
            try:
                # Test if still accessible
                _ = self._device_folder.Items().Count
                return self._device_folder
            except (AttributeError, RuntimeError, Exception) as e:
                logger.debug(
                    f"Cached device folder no longer accessible, refreshing: {e}"
                )
                self._device_folder = None

        try:
            this_pc = self._shell.NameSpace(SSF_DRIVES)
            if not this_pc:
                return None

            # Fast iteration - Shell objects are slow, so we do as little as possible inside the loop
            items = this_pc.Items()
            for i in range(items.Count):
                item = items.Item(i)
                if self.device_name.lower() in item.Name.lower():
                    self._device_folder = item.GetFolder
                    return self._device_folder
            return None
        except Exception as e:
            logger.debug(f"Error finding device: {e}")
            return None

    def _resolve_path(self, root_folder: Any, relative_path: str) -> Any | None:
        """Navigates through Shell Folders by relative path.

        Uses ParseName() as O(1) fast path, falls back to linear
        iteration if ParseName is not supported by the shell object.
        """
        current = root_folder
        parts = relative_path.replace("\\", "/").split("/")

        for part in parts:
            if not part:
                continue
            try:
                # O(1) fast path via Shell ParseName
                child = current.ParseName(part)
                if child and child.IsFolder:
                    current = child.GetFolder
                    continue

                # Fallback: linear iteration (case-insensitive)
                found = False
                for item in current.Items():
                    if item.Name.lower() == part.lower():
                        current = item.GetFolder
                        found = True
                        break
                if not found:
                    return None
            except (AttributeError, RuntimeError, Exception) as e:
                logger.debug(
                    f"Error navigating path segment in MTP hierarchy: {e}"
                )
                return None
        return current

    def is_connected(self) -> bool:
        """Checks if the device is accessible and storage is visible.

        Returns:
            True if connected and accessible, False otherwise.
        """
        # Need to initialize COM in every thread if used there
        # pythoncom.CoInitialize()
        device_folder = self._get_device_folder()
        if not device_folder:
            return False

        # Check for 'Internal Storage' or similar
        items = device_folder.Items()
        return items.Count > 0

    def list_files(
        self,
        existing_files_set: set[str] | None = None,
        skip_aae: bool = False,
        on_file_found: Callable[[int, int], None] | None = None,
    ) -> Generator[RemoteFile, None, None]:
        """
        Recursively yields files from the source folder.
        Reports progress via on_file_found(found_count, skipped_aae_count).
        Uses existing_files_set and skip_aae to avoid metadata fetch.

        Args:
            existing_files_set: Optional set of existing file paths to optimize skipping.
            skip_aae: If True, .aae files will be skipped.
            on_file_found: Optional callback for reporting scan progress.

        Returns:
            A generator yielding RemoteFile objects.
        """
        if pythoncom:
            pythoncom.CoInitialize()

        device_folder = self._get_device_folder()
        if not device_folder:
            raise DeviceDisconnectedError(f"Device '{self.device_name}' not found.")

        target_folder = self._resolve_path(device_folder, self.source_folder)
        if not target_folder:
            logger.warning(f"Source folder '{self.source_folder}' not found.")
            return

        # Start recursive scan
        folder_basename = self.source_folder.replace("\\", "/").split("/")[-1]

        self._scanned_count = 0
        self._skipped_aae_count = 0
        yield from self._scan_recursive(
            target_folder,
            folder_basename,
            self.source_folder,
            existing_files_set or set(),
            skip_aae,
            on_file_found,
        )

    def _scan_recursive(
        self,
        folder: Any,
        rel_path: str,
        full_mtp_path: str,
        existing_files_set: set[str],
        skip_aae: bool = False,
        on_file_found: Callable[[int, int], None] | None = None,
    ) -> Generator[RemoteFile, None, None]:
        """Recursive traversal of Shell items optimized for MTP."""
        try:
            items = folder.Items()
            for item in items:
                name = item.Name
                is_folder = item.IsFolder

                current_rel = f"{rel_path}/{name}" if rel_path else name
                current_mtp = f"{full_mtp_path}/{name}" if full_mtp_path else name

                if is_folder:
                    yield from self._scan_recursive(
                        item.GetFolder,
                        current_rel,
                        current_mtp,
                        existing_files_set,
                        skip_aae,
                        on_file_found,
                    )
                else:
                    # It's a file
                    try:
                        # Optimization: Skip AAE files early to avoid ANY metadata fetch
                        if skip_aae and name.lower().endswith(".aae"):
                            self._skipped_aae_count += 1
                            # Report on every 20th combined item
                            if (
                                on_file_found
                                and (self._scanned_count + self._skipped_aae_count) % REPORT_INTERVAL_FILES
                                == 0
                            ):
                                on_file_found(
                                    self._scanned_count, self._skipped_aae_count
                                )
                            continue

                        self._scanned_count += 1

                        # Batched reporting for UI (every 20 files as requested by user)
                        if (
                            on_file_found
                            and (self._scanned_count + self._skipped_aae_count) % REPORT_INTERVAL_FILES
                            == 0
                        ):
                            on_file_found(self._scanned_count, self._skipped_aae_count)

                        rel_lower = current_rel.lower()
                        is_existing = rel_lower in existing_files_set

                        size = 0
                        if not is_existing:
                            # CRITICAL: Use System.Size instead of item.Size for MTP accuracy
                            size = item.ExtendedProperty("System.Size")
                            if size is None:
                                size = item.Size  # Fallback

                        yield RemoteFile(
                            object_id=current_mtp,
                            relative_path=current_rel,
                            name=name,
                            size_bytes=int(size or 0),
                            modified_at=None,
                        )
                    except (ValueError, TypeError, Exception) as e:
                        logger.debug(f"Skipping file {name} due to metadata error: {e}")
                        continue
        except Exception as e:
            raise TransientError(f"MTP list failed: {e}") from e

    def _find_file_item(self, file: RemoteFile) -> Any:
        """Navigate MTP hierarchy and return the Shell item for a file."""
        device_folder = self._get_device_folder()
        if not device_folder:
            raise DeviceDisconnectedError("Device disconnected.")

        parts = file.object_id.replace("\\", "/").split("/")
        current_folder = device_folder
        folder_path_key = ""

        for part in parts[:-1]:
            folder_path_key = (
                f"{folder_path_key}/{part}" if folder_path_key else part
            )
            if folder_path_key in self._folder_cache:
                current_folder = self._folder_cache[folder_path_key]
                continue

            # O(1) fast path via ParseName
            child = current_folder.ParseName(part)
            if child and child.IsFolder:
                current_folder = child.GetFolder
                self._folder_cache[folder_path_key] = current_folder
                continue

            # Fallback: linear iteration (case-insensitive)
            found = False
            for item in current_folder.Items():
                if item.Name.lower() == part.lower():
                    current_folder = item.GetFolder
                    self._folder_cache[folder_path_key] = current_folder
                    found = True
                    break
            if not found:
                raise FatalError(
                    f"Path part '{part}' not found in MTP hierarchy."
                )

        # Find the file itself — ParseName first, then fallback
        filename = parts[-1]
        file_item = current_folder.ParseName(filename)
        if file_item:
            return file_item

        for item in current_folder.Items():
            if item.Name.lower() == filename.lower():
                return item

        raise FatalError(f"File '{file.object_id}' not found on device.")

    def _copy_to_temp(
        self,
        file: RemoteFile,
        target_dir: Path,
        cancel_check: Callable[[], bool] | None = None,
    ) -> Path:
        """Copies file via Shell to a target directory and waits for completion."""
        target_item = self._find_file_item(file)

        try:
            dest_shell = self._shell.NameSpace(str(target_dir))
            dest_shell.CopyHere(target_item, FOF_SILENT_NO_UI)

            actual_temp_file = target_dir / file.name
            retries = COPY_START_RETRIES
            while not actual_temp_file.exists() and retries > 0:
                if cancel_check and cancel_check():
                    raise FatalError("Copy cancelled by user.")
                time.sleep(COPY_START_RETRY_DELAY)
                retries -= 1

            if not actual_temp_file.exists():
                raise TransientError("Timeout waiting for MTP copy to start.")

            # Wait for Windows to finish copying by polling file size
            # via lightweight os.stat() — no open() to avoid lock conflicts.
            lock_retries = COPY_WAIT_RETRIES
            prev_size = -1
            stable_count = 0
            while lock_retries > 0:
                if cancel_check and cancel_check():
                    raise FatalError("Copy cancelled by user.")

                try:
                    current_size = actual_temp_file.stat().st_size
                except OSError:
                    # File might be momentarily locked by Windows
                    prev_size = -1
                    stable_count = 0
                    time.sleep(COPY_WAIT_RETRY_DELAY)
                    lock_retries -= 1
                    continue

                if file.size_bytes > 0 and current_size >= file.size_bytes:
                    break  # Fast exit: expected size reached

                # Fallback for unknown size: require N consecutive
                # stable reads to confirm copy is truly complete.
                if current_size > 0 and current_size == prev_size:
                    stable_count += 1
                    if stable_count >= STABLE_SIZE_CHECKS:
                        break
                else:
                    stable_count = 0

                prev_size = current_size
                time.sleep(COPY_WAIT_RETRY_DELAY)
                lock_retries -= 1

            if lock_retries <= 0:
                raise TransientError(
                    "Timeout: Windows MTP copy took too long or locked the file."
                )

            return actual_temp_file

        except (TransientError, FatalError, DeviceDisconnectedError):
            raise
        except Exception as e:
            raise TransientError(f"Failed to pull file from MTP: {e}") from e

    def download_file(
        self,
        file: RemoteFile,
        local_dest: Path,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        """
        Directly uses Windows Shell to copy the file to the target drive,
        eliminating the Python IO bottleneck and cross-drive copy delays.

        Reuses a session-level temp directory to avoid per-file
        mkdtemp overhead.
        """
        local_dest.parent.mkdir(parents=True, exist_ok=True)

        # Reuse a single temp dir per parent to avoid per-file overhead
        if not hasattr(self, "_temp_dirs"):
            self._temp_dirs: dict[str, Path] = {}

        parent_key = str(local_dest.parent)
        if parent_key not in self._temp_dirs:
            self._temp_dirs[parent_key] = Path(
                tempfile.mkdtemp(prefix=".mtp_tmp_", dir=local_dest.parent)
            )
        temp_dir_path = self._temp_dirs[parent_key]

        try:
            actual_temp_file = self._copy_to_temp(
                file, temp_dir_path, cancel_check
            )

            # Atomic rename to the .tmp path requested by caller
            if local_dest.exists():
                os.remove(local_dest)
            os.replace(actual_temp_file, local_dest)

        except Exception:
            # On error, clean up temp dir and remove from cache
            # so next call creates a fresh one
            shutil.rmtree(temp_dir_path, ignore_errors=True)
            self._temp_dirs.pop(parent_key, None)
            raise

    def open_stream(self, file: RemoteFile) -> BinaryIO:
        """
        Since Shell API doesn't support direct streaming easily,
        we copy the file to a temporary location first.
        """
        temp_dir_path = Path(tempfile.mkdtemp(prefix="iphone_mtp_"))

        try:
            actual_temp_file = self._copy_to_temp(file, temp_dir_path)
            return CleanupStream(actual_temp_file, str(temp_dir_path))  # type: ignore

        except Exception as e:
            if "temp_dir_path" in locals():
                shutil.rmtree(temp_dir_path, ignore_errors=True)
            raise TransientError(f"Failed to pull file from MTP: {e}") from e

    def cleanup(self) -> None:
        """Clean up session-level temporary directories."""
        if hasattr(self, "_temp_dirs"):
            for temp_dir in self._temp_dirs.values():
                shutil.rmtree(temp_dir, ignore_errors=True)
            self._temp_dirs.clear()
