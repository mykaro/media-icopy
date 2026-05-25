"""Unit tests for the Core Runner."""

from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest

from src.core_runner import CopierRunner
from src.infrastructure.config import AppConfig
from src.domain.models import RemoteFile, CopyStatus, CopyResult

from src.state.db import Database
from src.state.session import SessionManager
from src.adapters.protocol import FileSource

class FakeFileSource(FileSource):
    def __init__(self, files: list[RemoteFile]):
        self.files = files
        self.source_folder = ""
        self._skipped_aae_count = 0

    def is_connected(self) -> bool:
        return True

    def list_subfolders(self, relative_path: str = "") -> list[str]:
        return []

    def list_files(
        self,
        existing_files_set=None,
        skip_aae: bool = False,
        on_file_found=None,
    ):
        for f in self.files:
            if skip_aae and f.name.lower().endswith(".aae"):
                self._skipped_aae_count += 1
                continue
            if on_file_found:
                on_file_found(1, 0)
            yield f

    def download_file(self, file: RemoteFile, local_dest: Path, cancel_check=None) -> None:
        pass

    def open_stream(self, file: RemoteFile):
        pass

@pytest.fixture
def mock_config():
    config = MagicMock(spec=AppConfig)
    config.db_path = ":memory:"
    config.device_name = "Test iPhone"
    config.dest_root = "C:/TestDest"
    config.source_folders = ["DCIM/100APPLE"]
    config.batch_limit_mb = 100
    config.skip_aae = True
    config.retry_attempts = 1
    config.retry_backoff_seconds = 0
    return config

@pytest.fixture
def test_db():
    db = Database(":memory:")
    yield db
    db.close()

@patch("src.core_runner.generate_batches")
@patch("src.core_runner.execute_with_retry")
def test_runner_success(
    mock_execute_with_retry,
    mock_generate_batches,
    mock_config,
    test_db,
):
    """Test successful run of the copier runner."""
    file1 = RemoteFile("obj1", "DCIM/100APPLE/1.JPG", "1.JPG", 1024, 0)
    fake_source = FakeFileSource([file1])

    session_manager = SessionManager(test_db)
    session_manager.complete = MagicMock()

    # Mock batch generator to return one batch
    mock_batch = MagicMock()
    mock_batch.tasks = [MagicMock(file=file1)]
    mock_batch.index = 0
    mock_generate_batches.return_value = [mock_batch]

    mock_execute_with_retry.return_value = CopyResult(
        mock_batch.tasks[0], CopyStatus.SUCCESS, 1024
    )

    # Run
    runner = CopierRunner(
        config=mock_config,
        source_factory=lambda name: fake_source,
        db=test_db,
        session=session_manager
    )
    runner.run()

    # Assert
    session_manager.complete.assert_called_once()
    mock_generate_batches.assert_called_once()
    mock_execute_with_retry.assert_called_once()

def test_runner_skip_aae(mock_config, test_db):
    """Test that .AAE files are skipped if config.skip_aae is True."""
    file_jpg = RemoteFile("obj1", "1.JPG", "1.JPG", 100, 0)
    file_aae = RemoteFile("obj2", "1.AAE", "1.AAE", 10, 0)

    fake_source = FakeFileSource([file_jpg, file_aae])
    mock_config.skip_aae = True

    runner = CopierRunner(
        config=mock_config,
        source_factory=lambda name: fake_source,
        db=test_db
    )

    with patch("src.core_runner.generate_batches") as mock_generate_batches:
        mock_generate_batches.return_value = []
        runner.run()

        # Verify that only the JPG was passed to generate_batches
        generator_arg = mock_generate_batches.call_args[0][0]
        files_to_copy = list(generator_arg)
        assert len(files_to_copy) == 1
        assert files_to_copy[0].name == "1.JPG"

def test_runner_cancel(mock_config, test_db):
    """Test that requesting cancel stops the runner gracefully."""
    fake_source = FakeFileSource([])
    
    runner = CopierRunner(
        config=mock_config,
        source_factory=lambda name: fake_source,
        db=test_db
    )
    runner.request_cancel()  # Cancel immediately

    # Run, shouldn't crash or scan
    runner.run()

