"""LocalFileSource — test implementation of FileSource based on a local folder.

Used in all tests instead of a real MTP connection.
"""

import io
import shutil
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Optional

from ..domain.models import RemoteFile


class LocalFileSource:
    """FileSource implementation backed by a local directory.

    Implements the FileSource protocol for testing purposes.
    Scans a local folder recursively and yields RemoteFile objects.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def list_files(self) -> Generator[RemoteFile, None, None]:
        """Yield all files under root as RemoteFile objects.

        Traverses the directory recursively, yielding one file at a time.
        Directories are skipped — only regular files are yielded.
        """
        for path in sorted(self._root.rglob("*")):
            if not path.is_file():
                continue
            stat = path.stat()
            relative = path.relative_to(self._root).as_posix()
            yield RemoteFile(
                object_id=relative,  # Use relative path as a stable ID
                relative_path=relative,
                name=path.name,
                size_bytes=stat.st_size,
                modified_at=stat.st_mtime,
            )

    def open_stream(self, file: RemoteFile) -> io.BufferedReader:
        """Open a file for binary reading.

        Returns a BufferedReader (a BinaryIO subclass) for the file.
        The caller is responsible for closing the stream.
        """
        full_path = self._root / file.relative_path
        return open(full_path, "rb")  # noqa: SIM115

    def download_file(
        self,
        file: RemoteFile,
        local_dest: Path,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> None:
        """Copy file directly to local_dest (for protocol compliance).

        Uses shutil.copy2 to preserve metadata.
        """
        source_path = self._root / file.relative_path
        local_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, local_dest)

    def is_connected(self) -> bool:
        """Check if the root directory exists and is accessible."""
        return self._root.is_dir()

    def cleanup(self) -> None:
        """Clean up temporary resources (no-op for local source)."""
        pass
