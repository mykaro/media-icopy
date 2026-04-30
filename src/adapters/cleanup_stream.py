"""Wrapper stream that auto-cleans temporary directories on close."""

import logging
import shutil
import weakref
from pathlib import Path
from typing import BinaryIO

logger = logging.getLogger(__name__)


def _cleanup_temp_dir(path: str) -> None:
    """Helper to clean up temporary directories, used by weakref.finalize."""
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        logger.error(f"Failed to remove temp dir '{path}': {e}")


class CleanupStream:
    """A file stream wrapper that removes its parent temp dir on close.

    Uses weakref.finalize as a safety net so the temp directory is
    cleaned even if .close() is never called explicitly.
    """

    def __init__(self, path: Path, parent_dir: str):
        self.file: BinaryIO = open(path, "rb")
        self.parent_dir = parent_dir
        self._finalizer = weakref.finalize(self, _cleanup_temp_dir, parent_dir)

    def read(self, size: int = -1) -> bytes:
        return self.file.read(size)

    def close(self) -> None:
        self.file.close()
        self._finalizer()

    def __enter__(self) -> "CleanupStream":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __getattr__(self, name: str) -> object:
        return getattr(self.file, name)
