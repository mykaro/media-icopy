"""Domain models for the iPhone copier application."""

from dataclasses import dataclass
from enum import Enum, auto


@dataclass(frozen=True)
class RemoteFile:
    """A file on the iPhone."""

    object_id: str  # MTP object ID for direct access
    relative_path: str  # Relative path from the copy root
    name: str
    size_bytes: int
    modified_at: float | None  # Unix timestamp, may be None


@dataclass
class ProgressInfo:
    """Information about current copy progress."""

    current_file: int
    total_files: int
    copied_bytes: int
    total_bytes: int
    batch_index: int


@dataclass
class CopyTask:
    """A unit of work: one file to be copied."""

    file: RemoteFile
    dest_path: str  # Absolute path on the PC
    attempt: int = 0


@dataclass
class Batch:
    """A batch of files for a single iteration."""

    index: int
    total_batches: int
    tasks: list[CopyTask]
    total_size_bytes: int


class CopyStatus(Enum):
    SUCCESS = auto()
    FAILED_TRANSIENT = auto()  # Retry possible
    FAILED_FATAL = auto()  # Do not retry


@dataclass
class CopyResult:
    """Result of copying a single file."""

    task: CopyTask
    status: CopyStatus
    copied_size_bytes: int = 0


class MessageType(Enum):
    GENERAL = auto()
    SCANNING = auto()
    PROGRESS = auto()
