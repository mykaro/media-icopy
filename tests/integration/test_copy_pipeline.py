"""Integration tests for the copy pipeline using LocalFileSource."""

import pytest
from pathlib import Path
import time

from collections.abc import Generator

from src.adapters.local_source import LocalFileSource
from src.domain.copier import copy_file
from src.domain.models import RemoteFile, CopyTask, CopyStatus
from src.state.db import Database


def test_copy_pipeline_success(
    db: Database, tmp_path: Path, local_source: LocalFileSource
):
    """Test successful copy of a file from local source to destination."""
    dest_path = tmp_path / "destination"
    dest_path.mkdir()

    # Get a file from source
    files = list(local_source.list_files())
    remote_file = files[0]

    # Create task
    target_path = dest_path / remote_file.relative_path
    task = CopyTask(remote_file, str(target_path))

    # Execute copy
    result = copy_file(task, local_source)
    if result.status == CopyStatus.SUCCESS:
        db.register_copied_file(task.file)

    # Verify
    assert result.status == CopyStatus.SUCCESS
    assert target_path.exists()
    assert target_path.stat().st_size == remote_file.size_bytes

    # Verify DB registration
    assert db.is_file_copied(remote_file.relative_path) is not None


def test_copy_pipeline_mismatch_cleanup(
    db: Database, tmp_path: Path, local_source: LocalFileSource
):
    """Test that a size mismatch triggers cleanup of the .tmp file."""
    dest_path = tmp_path / "destination"
    dest_path.mkdir()

    # Mock a file with size that won't match its content
    files = list(local_source.list_files())
    # Modify the remote_file object to have a different size
    true_file = files[0]
    corrupt_file = RemoteFile(
        object_id=true_file.object_id,
        relative_path=true_file.relative_path,
        name=true_file.name,
        size_bytes=true_file.size_bytes + 1,  # Wrong size!
        modified_at=true_file.modified_at,
    )

    target_path = dest_path / corrupt_file.relative_path
    task = CopyTask(corrupt_file, str(target_path))

    # Should raise TransientError due to size mismatch
    from src.domain.exceptions import TransientError

    with pytest.raises(TransientError):
        copy_file(task, local_source)

    # Verify cleanup: neither destination nor .tmp should exist
    assert not target_path.exists()
    tmp_path_expected = target_path.with_suffix(target_path.suffix + ".tmp")
    assert not tmp_path_expected.exists()

    # Verify NOT in DB
    assert db.is_file_copied(corrupt_file.relative_path) is None
