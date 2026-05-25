"""Shared test fixtures for the iPhone copier test suite."""

from collections.abc import Generator
from pathlib import Path

import pytest

from src.adapters.local_source import LocalFileSource
from src.state.db import Database


@pytest.fixture
def sample_tree(tmp_path: Path) -> Path:
    """Create a sample directory tree mimicking an iPhone DCIM structure.

    Structure:
        tmp_path/
        ├── 100APPLE/
        │   ├── IMG_0001.JPG   (1024 bytes)
        │   └── IMG_0002.HEIC  (2048 bytes)
        └── 101APPLE/
            ├── IMG_0003.MOV   (5120 bytes)
            └── IMG_0004.JPG   (512 bytes)
    """
    apple_100 = tmp_path / "100APPLE"
    apple_100.mkdir()
    (apple_100 / "IMG_0001.JPG").write_bytes(b"J" * 1024)
    (apple_100 / "IMG_0002.HEIC").write_bytes(b"H" * 2048)

    apple_101 = tmp_path / "101APPLE"
    apple_101.mkdir()
    (apple_101 / "IMG_0003.MOV").write_bytes(b"M" * 5120)
    (apple_101 / "IMG_0004.JPG").write_bytes(b"j" * 512)

    return tmp_path


@pytest.fixture
def local_source(sample_tree: Path) -> LocalFileSource:
    """Create a LocalFileSource backed by the sample_tree fixture."""
    return LocalFileSource(root=sample_tree)


@pytest.fixture
def empty_tree(tmp_path: Path) -> Path:
    """Create an empty directory for edge-case tests."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    return empty_dir


@pytest.fixture
def db(tmp_path: Path) -> Generator[Database, None, None]:
    """Fixture for a temporary database."""
    db_file = tmp_path / "test.db"
    database = Database(db_file)
    yield database
    database.close()
