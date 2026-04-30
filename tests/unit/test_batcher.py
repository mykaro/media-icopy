"""Unit tests for the Batcher logic."""

from pathlib import Path
import pytest

from src.domain.models import RemoteFile
from src.domain.batcher import generate_batches


def create_remote_file(name: str, size: int) -> RemoteFile:
    """Helper to create a RemoteFile."""
    return RemoteFile(
        object_id=name,
        relative_path=f"DCIM/{name}",
        name=name,
        size_bytes=size,
        modified_at=None,
    )


def test_batching_basic():
    """Test grouping files into batches by size limit."""
    files = [
        create_remote_file("1.jpg", 100),
        create_remote_file("2.jpg", 100),
        create_remote_file("3.jpg", 100),
    ]

    # Limit 200 bytes (using MB in function, so we mock it with small numbers for test if possible)
    # But function multiplies by 1024*1024.
    # Let's say limit is 1MB and files are 600KB each.

    kb = 1024
    files = [
        create_remote_file("1.jpg", 600 * kb),
        create_remote_file("2.jpg", 600 * kb),
        create_remote_file("3.jpg", 300 * kb),
    ]

    # 1MB limit = 1024 KB
    batches = list(generate_batches((f for f in files), Path("/test"), 1))

    assert len(batches) == 2
    assert len(batches[0].tasks) == 1  # 600KB
    assert len(batches[1].tasks) == 2  # 600KB + 300KB = 900KB
    assert batches[0].index == 0
    assert batches[1].index == 1


def test_large_file_separate_batch():
    """A file larger than limit should get its own batch."""
    kb = 1024
    files = [
        create_remote_file("small.jpg", 100 * kb),
        create_remote_file("huge.mov", 2000 * kb),  # > 1MB
        create_remote_file("small2.jpg", 100 * kb),
    ]

    batches = list(generate_batches((f for f in files), Path("/test"), 1))

    assert len(batches) == 3
    assert len(batches[0].tasks) == 1
    assert len(batches[1].tasks) == 1
    assert batches[1].tasks[0].file.name == "huge.mov"
    assert len(batches[2].tasks) == 1


def test_empty_list():
    """Empty input should yield no batches."""
    batches = list(generate_batches((f for f in []), Path("/test"), 1))
    assert len(batches) == 0


def test_exact_limit():
    """Files exactly matching the limit should be grouped together."""
    kb = 1024
    files = [
        create_remote_file("1.jpg", 512 * kb),
        create_remote_file("2.jpg", 512 * kb),
        create_remote_file("3.jpg", 1024 * kb),
    ]

    batches = list(generate_batches((f for f in files), Path("/test"), 1))

    assert len(batches) == 2
    assert len(batches[0].tasks) == 2  # 512 + 512 = 1024KB (1MB)
    assert batches[0].total_size_bytes == 1024 * kb
    assert len(batches[1].tasks) == 1  # 1024KB
