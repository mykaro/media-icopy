"""Core execution logic decoupled from GUI."""

import logging
import time
from time import monotonic
from pathlib import Path
from typing import Callable

import pythoncom
from .infrastructure.config import AppConfig
from .state.db import Database
from .state.session import SessionManager, SessionState
from .adapters.mtp_adapter import MTPFileSource, MTPDeviceRegistry
from .adapters.protocol import FileSource
from .domain.batcher import generate_batches
from .domain.models import ProgressInfo, CopyStatus, MessageType, RemoteFile
from .domain.copier import copy_file
from .domain.retry import execute_with_retry
from .domain.exceptions import CopierError, FatalError, DeviceDisconnectedError
from .utils import format_size, format_elapsed
from .i18n import t


class CopierRunner:
    """
    Executes the copy pipeline.
    Can report progress via callbacks for UI integration.
    """

    def __init__(
        self,
        config: AppConfig,
        source_factory: Callable[[str], FileSource] | None = None,
        db: Database | None = None,
        session: SessionManager | None = None,
    ):
        self.config = config
        self.db = db if db is not None else Database(config.db_path)
        self.session = session if session is not None else SessionManager(self.db)
        self._source_factory = source_factory or (lambda name: MTPFileSource(name))

        self.on_log: Callable[[str, str, MessageType], None] = (
            lambda level, msg, msg_type: None
        )
        self.on_scan_progress: Callable[[int, int, int, int], None] = (
            lambda cur_folder, tot_folders, file_count, aae_count: None
        )
        self.on_progress: Callable[[ProgressInfo], None] = lambda info: None
        self.on_finish: Callable[[int, int, int], None] = (
            lambda files, bytes_copied, skipped: None
        )
        self.on_error: Callable[[Exception], None] = lambda e: None
        self.on_cancel: Callable[[], None] = lambda: None

        # State
        self._cancel_requested = False

    def log(
        self, level: str, message: str, msg_type: MessageType = MessageType.GENERAL
    ) -> None:
        """Internal logging that also triggers the callback.

        Args:
            level: The log level (e.g., 'INFO', 'ERROR').
            message: The message to log.
            msg_type: The message type (e.g., GENERAL, SCANNING).
        """
        try:
            numeric_level = getattr(logging, level.upper())
            logging.getLogger(__name__).log(numeric_level, message)
        except AttributeError:
            logging.getLogger(__name__).info(message)

        # Trigger UI callback
        self.on_log(level, message, msg_type)

    def request_cancel(self) -> None:
        """Flags the runner to stop gracefully."""
        self._cancel_requested = True

    def run(self) -> None:
        """Main execution loop."""
        shared_source = None
        try:
            self._init_session()

            if self._cancel_requested:
                self.log("WARNING", t("runner.cancelled_zero"))
                self.on_cancel()
                return

            shared_source = self._source_factory(self.config.device_name)
            existing_files_set = self._pre_cache_dest_files()

            scan_start = monotonic()
            (
                files_to_copy,
                file_to_folder,
                source_cache,
                scanned_count,
                skipped_count,
            ) = self._scan_phase(shared_source, existing_files_set)
            scan_elapsed = format_elapsed(int(monotonic() - scan_start))
            self.log(
                "INFO",
                t("runner.scan_duration", duration=scan_elapsed),
            )

            total_to_copy = len(files_to_copy)
            total_bytes_to_copy = sum(f.size_bytes for f in files_to_copy)

            aae_info = ""
            skipped_aae = getattr(shared_source, "_skipped_aae_count", 0)
            if (
                self.config.skip_aae
                and isinstance(skipped_aae, int)
                and skipped_aae > 0
            ):
                aae_info = t("runner.aae_skipped", count=skipped_aae)

            self.log(
                "INFO",
                t(
                    "runner.analysis_result",
                    found=scanned_count,
                    aae=aae_info,
                    existing=skipped_count,
                    to_copy=total_to_copy,
                ),
            )

            def filtered_generator():
                for f in files_to_copy:
                    if self._cancel_requested:
                        break
                    yield f

            self.session.transition(SessionState.BATCHING)
            batches = generate_batches(
                filtered_generator(),
                Path(self.config.dest_root),
                self.config.batch_limit_mb,
            )

            copy_start = monotonic()
            total_files_count, total_copied_bytes = self._copy_phase(
                batches,
                file_to_folder,
                source_cache,
                total_to_copy,
                total_bytes_to_copy,
            )
            copy_elapsed = format_elapsed(int(monotonic() - copy_start))
            self.log(
                "INFO",
                t("runner.copy_duration", duration=copy_elapsed),
            )

            self._finalize(total_files_count, total_copied_bytes, skipped_count)

        except Exception as e:
            self.log("ERROR", t("runner.critical_error", err=str(e)))
            self.on_error(e)
        finally:
            if shared_source:
                try:
                    shared_source.cleanup()
                except Exception as e:
                    self.log("WARNING", f"Cleanup error: {e}")
            self.db.close()

    def _init_session(self) -> None:
        # Завжди очищуємо базу перед новим скануванням, щоб почистити стару історію
        self.db.clear_all_state()
        self.session.current_session_id = None

        if pythoncom:
            pythoncom.CoInitialize()

        self.session.start_new(self.config.device_name, self.config.dest_root)
        self.log(
            "INFO",
            t(
                "runner.device_info",
                device=self.config.device_name,
                dest=self.config.dest_root,
            ),
        )

    def _pre_cache_dest_files(self) -> set[str]:
        # Pre-cache local file list to avoid thousands of disk hits
        dest_path = Path(self.config.dest_root)
        existing_files_set = set()
        if dest_path.exists():
            for p in dest_path.rglob("*"):
                if p.is_file():
                    try:
                        rel = p.relative_to(dest_path).as_posix()
                        existing_files_set.add(rel.lower())
                    except (ValueError, OSError) as e:
                        self.log(
                            "WARNING",
                            f"Skipping path entry during existing files scan: {e}",
                        )
                        continue
        return existing_files_set

    def _scan_phase(
        self, shared_source: FileSource, existing_files_set: set[str]
    ) -> tuple[list[RemoteFile], dict[str, str], dict[str, FileSource], int, int]:
        source_cache: dict[str, FileSource] = {}
        file_to_folder: dict[str, str] = {}
        total_folders = len(self.config.source_folders)
        scanned_count = 0
        files_to_copy = []
        skipped_count = 0

        self.session.transition(SessionState.SCANNING)
        for index, folder_path in enumerate(self.config.source_folders):
            if self._cancel_requested:
                break

            shared_source.source_folder = folder_path
            source_cache[folder_path] = shared_source
            self.log(
                "INFO",
                t(
                    "runner.scanning",
                    index=index + 1,
                    total=total_folders,
                    folder=folder_path,
                ),
                MessageType.SCANNING,
            )

            # Колбек для оновлення кількості знайдених файлів у реальному часі
            def on_file_found(count, aae_count):
                self.on_scan_progress(
                    index + 1, total_folders, scanned_count + count, aae_count
                )

            # Скидаємо лічильник пропущених AAE для кожної папки
            for f in shared_source.list_files(
                existing_files_set=existing_files_set,
                skip_aae=self.config.skip_aae,
                on_file_found=on_file_found,
            ):
                if self._cancel_requested:
                    break

                if self.config.skip_aae and f.name.lower().endswith(".aae"):
                    continue

                scanned_count += 1

                rel_p_lower = f.relative_path.lower()
                if rel_p_lower in existing_files_set:
                    skipped_count += 1
                else:
                    file_to_folder[f.object_id] = folder_path
                    files_to_copy.append(f)

            # Notify UI about scan progress (folder completed)
            self.on_scan_progress(
                index + 1,
                total_folders,
                scanned_count,
                getattr(shared_source, "_skipped_aae_count", 0),
            )

        return files_to_copy, file_to_folder, source_cache, scanned_count, skipped_count

    def _copy_phase(
        self, batches, file_to_folder, source_cache, total_to_copy, total_bytes_to_copy
    ) -> tuple[int, int]:
        self.session.transition(SessionState.COPYING)
        total_copied_bytes = 0
        total_files_count = 0
        last_folder = None

        for batch in batches:
            if self._cancel_requested:
                self.log("WARNING", t("runner.stopped_by_user"))
                break

            for task in batch.tasks:
                if self._cancel_requested:
                    break

                # Log folder change
                current_folder = task.file.relative_path.split("/")[0]
                if current_folder != last_folder:
                    self.log("INFO", t("runner.opening_folder", folder=current_folder))
                    last_folder = current_folder

                copied_bytes = self._process_task(
                    task, file_to_folder, source_cache, batch.index, total_files_count, total_to_copy, total_copied_bytes, total_bytes_to_copy
                )
                
                total_copied_bytes += copied_bytes
                total_files_count += 1
                
        return total_files_count, total_copied_bytes

    def _process_task(
        self, task, file_to_folder, source_cache, batch_index, total_files_count, total_to_copy, total_copied_bytes, total_bytes_to_copy
    ) -> int:
        try:
            source_folder = file_to_folder.get(task.file.object_id)
            if not source_folder:
                raise FatalError(
                    f"Source folder not found for '{task.file.object_id}' — file skipped."
                )
            current_source = source_cache[source_folder]

            def handle_transient_error(e: Exception):
                if isinstance(e, DeviceDisconnectedError):
                    self.log("WARNING", f"Device disconnected, refreshing cache...")
                    MTPDeviceRegistry.refresh_shell_cache()
                    time.sleep(2.0)

            result = execute_with_retry(
                copy_file,
                self.config.retry_attempts,
                self.config.retry_backoff_seconds,
                task,
                current_source,
                cancel_check=lambda: self._cancel_requested,
                on_transient_error=handle_transient_error,
            )

            if result.status == CopyStatus.SUCCESS:
                self.db.register_copied_file(task.file)

            info = ProgressInfo(
                current_file=total_files_count + 1,
                total_files=total_to_copy,
                copied_bytes=total_copied_bytes + result.copied_size_bytes,
                total_bytes=total_bytes_to_copy,
                batch_index=batch_index,
            )
            self.on_progress(info)
            return result.copied_size_bytes

        except CopierError as e:
            self.log(
                "ERROR",
                t("runner.copy_error", file=task.file.relative_path, err=str(e)),
            )
            if self.session.current_session_id is None:
                self.log("ERROR", "No active session — skipping retry queue.")
            else:
                self.db.add_to_retry_queue(
                    self.session.current_session_id, task, str(e), time.time()
                )

            info = ProgressInfo(
                current_file=total_files_count + 1,
                total_files=total_to_copy,
                copied_bytes=total_copied_bytes,
                total_bytes=total_bytes_to_copy,
                batch_index=batch_index,
            )
            self.on_progress(info)
            return 0

    def _finalize(self, total_files_count, total_copied_bytes, skipped_count):
        if not self._cancel_requested:
            self.session.complete()
            size_str = format_size(total_copied_bytes)
            self.log(
                "INFO",
                t(
                    "runner.finished_summary",
                    copied=total_files_count,
                    size=size_str,
                    skipped=skipped_count,
                ),
            )
            self.on_finish(total_files_count, total_copied_bytes, skipped_count)
        else:
            self.log("WARNING", t("runner.cancelled_summary", count=total_files_count))
            self.on_cancel()
