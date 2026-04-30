"""Main pipeline for copying files from source to destination."""

import dataclasses
import os
from collections.abc import Callable
from pathlib import Path

from ..adapters.protocol import FileSource
from .models import CopyTask, CopyResult, CopyStatus
from .exceptions import (
    TransientError,
    FatalError,
    DeviceDisconnectedError,
    DiskFullError,
)

CHUNK_SIZE = 4 * 1024 * 1024  # 4MB chunks


def copy_file(
    task: CopyTask, source: FileSource, cancel_check: Callable[[], bool] | None = None
) -> CopyResult:
    """
    Executes the copy pipeline for a single file task.

    Pipeline:
    1. Check connection.
    2. Open source stream.
    3. Write to temporary file (.tmp extension).
    4. Verify file sizes match.
    5. Atomic rename to destination path.
    6. Register in database.
    7. Return success result or handle exceptions.

    Args:
        task: The task containing file metadata and destination path.
        source: The source adapter to read the file from.
        cancel_check: Optional callback to check if the user cancelled the operation.

    Returns:
        CopyResult indicating success and the number of bytes copied.
    """
    dest_path = Path(task.dest_path)
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".tmp")

    # Ensure destination directory exists
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Check connection
        if not source.is_connected():
            raise DeviceDisconnectedError("Device not connected before transfer.")

        # 2. Open stream and write to .tmp
        # We now use download_file direct copying which avoids python chunking bottleneck
        source.download_file(task.file, tmp_path, cancel_check=cancel_check)

        # 3. Verify size
        actual_size = tmp_path.stat().st_size
        if task.file.size_bytes in (0, -1) and actual_size > 0:
            # MTP failed to report size accurately beforehand, trust the actual transfer size
            pass
        elif actual_size != task.file.size_bytes:
            raise TransientError(
                f"Size mismatch: expected {task.file.size_bytes}, got {actual_size}"
            )

        # 4. Atomic rename (idempotent replacement)
        os.replace(tmp_path, dest_path)

        return CopyResult(
            task=task, status=CopyStatus.SUCCESS, copied_size_bytes=actual_size
        )

    except OSError as e:
        # Check for disk full (Windows specific error code is often 112)
        if "space" in str(e).lower() or getattr(e, "winerror", 0) == 112:
            raise DiskFullError(f"No space on disk: {e}") from e
        raise TransientError(f"I/O error during copy: {e}") from e

    except (TransientError, DeviceDisconnectedError) as e:
        # Re-raise to be caught by retry logic or caller
        raise

    except Exception as e:
        # Wrap unknown errors as fatal to be safe, unless we specifically know they are transient
        raise FatalError(f"Unexpected error during copy: {e}") from e

    finally:
        # Cleanup temporary file if it still exists
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
