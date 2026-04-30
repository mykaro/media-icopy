"""Custom exception hierarchy for the iPhone copier application."""


class CopierError(Exception):
    """Base exception for all copier errors."""


class TransientError(CopierError):
    """Retryable error (MTP timeout, USB disconnect, disk write error)."""


class FatalError(CopierError):
    """Non-retryable error (disk full, file inaccessible on iPhone)."""


class DeviceDisconnectedError(TransientError):
    """iPhone was disconnected during operation."""


class DiskFullError(FatalError):
    """No free space on the destination disk."""
