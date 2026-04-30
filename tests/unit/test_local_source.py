"""Tests for LocalFileSource — the test implementation of FileSource protocol."""

from collections.abc import Generator
from pathlib import Path

import pytest

from src.adapters.local_source import LocalFileSource
from src.domain.models import RemoteFile


class TestListFiles:
    """Tests for LocalFileSource.list_files()."""

    def test_returns_generator(self, local_source: LocalFileSource) -> None:
        """list_files() must return a generator, not a list."""
        result = local_source.list_files()
        assert isinstance(result, Generator)

    def test_yields_all_files(self, local_source: LocalFileSource) -> None:
        """list_files() must yield all 4 files from sample_tree."""
        files = list(local_source.list_files())
        assert len(files) == 4

    def test_yields_remote_file_instances(self, local_source: LocalFileSource) -> None:
        """Each yielded item must be a RemoteFile dataclass."""
        files = list(local_source.list_files())
        for f in files:
            assert isinstance(f, RemoteFile)

    def test_relative_paths_are_posix(self, local_source: LocalFileSource) -> None:
        """Relative paths must use forward slashes (POSIX format)."""
        files = list(local_source.list_files())
        for f in files:
            assert "\\" not in f.relative_path
            assert "/" in f.relative_path or f.relative_path == f.name

    def test_file_sizes_are_correct(self, local_source: LocalFileSource) -> None:
        """File sizes must match the actual sizes on disk."""
        files = {f.name: f for f in local_source.list_files()}
        assert files["IMG_0001.JPG"].size_bytes == 1024
        assert files["IMG_0002.HEIC"].size_bytes == 2048
        assert files["IMG_0003.MOV"].size_bytes == 5120
        assert files["IMG_0004.JPG"].size_bytes == 512

    def test_modified_at_is_set(self, local_source: LocalFileSource) -> None:
        """modified_at must be a float (Unix timestamp), not None."""
        files = list(local_source.list_files())
        for f in files:
            assert f.modified_at is not None
            assert isinstance(f.modified_at, float)

    def test_empty_directory_yields_nothing(self, empty_tree: Path) -> None:
        """list_files() on an empty directory must yield zero files."""
        source = LocalFileSource(root=empty_tree)
        files = list(source.list_files())
        assert len(files) == 0

    def test_skips_directories(self, sample_tree: Path) -> None:
        """list_files() must not yield directory entries."""
        source = LocalFileSource(root=sample_tree)
        files = list(source.list_files())
        for f in files:
            # Directories would have size 0 and no extension typically
            assert "." in f.name  # All test files have extensions


class TestOpenStream:
    """Tests for LocalFileSource.open_stream()."""

    def test_reads_correct_content(self, local_source: LocalFileSource) -> None:
        """open_stream() must return a stream with the correct file content."""
        files = {f.name: f for f in local_source.list_files()}
        img = files["IMG_0001.JPG"]

        with local_source.open_stream(img) as stream:
            data = stream.read()

        assert len(data) == 1024
        assert data == b"J" * 1024

    def test_stream_reads_in_chunks(self, local_source: LocalFileSource) -> None:
        """Stream must support chunked reading."""
        files = {f.name: f for f in local_source.list_files()}
        mov = files["IMG_0003.MOV"]

        with local_source.open_stream(mov) as stream:
            chunk1 = stream.read(2048)
            chunk2 = stream.read(2048)
            chunk3 = stream.read(2048)

        assert len(chunk1) == 2048
        assert len(chunk2) == 2048
        assert len(chunk3) == 1024  # Remaining bytes

    def test_stream_is_binary(self, local_source: LocalFileSource) -> None:
        """open_stream() must return a binary stream."""
        files = list(local_source.list_files())
        with local_source.open_stream(files[0]) as stream:
            data = stream.read(1)
            assert isinstance(data, bytes)


class TestIsConnected:
    """Tests for LocalFileSource.is_connected()."""

    def test_connected_when_dir_exists(self, local_source: LocalFileSource) -> None:
        """is_connected() must return True when root directory exists."""
        assert local_source.is_connected() is True

    def test_not_connected_when_dir_missing(self, tmp_path: Path) -> None:
        """is_connected() must return False for a non-existent directory."""
        source = LocalFileSource(root=tmp_path / "nonexistent")
        assert source.is_connected() is False
