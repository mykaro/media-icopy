"""FileSource protocol — the only interface between domain logic and file sources.

All domain code accesses files exclusively through this protocol.
Never import pywin32 outside of mtp_adapter.py.
"""

from collections.abc import Callable, Generator
from pathlib import Path
from typing import BinaryIO, Protocol

from ..domain.models import RemoteFile


class FileSource(Protocol):
    """Abstraction for a file source (iPhone via MTP, local folder, etc.).

    This MUST be the only interface between domain logic and
    the MTP/filesystem layer.
    """

    def list_files(self) -> Generator[RemoteFile, None, None]:
        """Yield files one by one — NEVER return a full list at once.

        This allows incremental processing without loading
        the entire file index into memory.

        Returns:
            A generator yielding RemoteFile objects.
        """
        ...

    def open_stream(self, file: RemoteFile) -> BinaryIO:
        """Return a stream for sequential reading of the file.

        Args:
            file: The RemoteFile object to open.

        Returns:
            A binary stream (BinaryIO) of the file content.
        """
        ...

    def download_file(
        self,
        file: RemoteFile,
        local_dest: Path,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        """Downloads the remote file directly to the local destination.

        Args:
            file: The RemoteFile object to download.
            local_dest: The local Path where the file should be saved.
            cancel_check: Optional callback to check if the operation should be cancelled.
        """
        ...

    def is_connected(self) -> bool:
        """Check device availability without raising an exception.

        Returns:
            True if the device is connected and accessible, False otherwise.
        """
        ...

    def cleanup(self) -> None:
        """Clean up any temporary resources or caches used by the source."""
        ...
