"""Unit tests for the copier module using mocks."""

import dataclasses
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import os

from src.domain.copier import copy_file
from src.domain.models import RemoteFile, CopyTask, CopyStatus
from src.domain.exceptions import (
    DeviceDisconnectedError,
    TransientError,
    DiskFullError,
    FatalError,
)
from src.adapters.protocol import FileSource
from src.adapters.protocol import FileSource


@pytest.fixture
def mock_source():
    source = MagicMock(spec=FileSource)
    source.is_connected.return_value = True
    return source


@pytest.fixture
def sample_task(tmp_path: Path):
    file = RemoteFile("obj1", "IMG_001.JPG", "IMG_001.JPG", 1024, 0)
    dest = tmp_path / "dest" / "IMG_001.JPG"
    return CopyTask(file, str(dest))


def test_copier_device_disconnected(sample_task, mock_source):
    """Test that a disconnected device raises DeviceDisconnectedError."""
    mock_source.is_connected.return_value = False

    with pytest.raises(DeviceDisconnectedError):
        copy_file(sample_task, mock_source)


def test_copier_size_workaround(sample_task, mock_source, tmp_path: Path):
    """Test that file size of 0 or -1 uses the actual copied size without failing."""
    # Set size to 0
    sample_task.file = dataclasses.replace(sample_task.file, size_bytes=0)

    actual_size = 2048

    def mock_download(remote_file, local_path, cancel_check=None):
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(b"A" * actual_size)

    mock_source.download_file.side_effect = mock_download

    result = copy_file(sample_task, mock_source)

    assert result.status == CopyStatus.SUCCESS
    assert result.copied_size_bytes == actual_size


def test_copier_disk_full(sample_task, mock_source, tmp_path: Path):
    """Test that an OSError with winerror 112 translates to DiskFullError."""

    def mock_download(remote_file, local_path, cancel_check=None):
        error = OSError("No space left on device")
        error.winerror = 112
        raise error

    mock_source.download_file.side_effect = mock_download

    with pytest.raises(DiskFullError):
        copy_file(sample_task, mock_source)


def test_copier_unexpected_error(sample_task, mock_source):
    """Test that an unknown exception translates to FatalError."""

    mock_source.download_file.side_effect = ValueError("Some mysterious error")

    with pytest.raises(FatalError):
        copy_file(sample_task, mock_source)


def test_copier_transient_error(sample_task, mock_source):
    """Test that TransientError is propagated unchanged."""
    mock_source.download_file.side_effect = TransientError("Network hiccup")
    with pytest.raises(TransientError):
        copy_file(sample_task, mock_source)
