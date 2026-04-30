"""Edge case tests for the Core Runner."""

from unittest.mock import MagicMock, patch
import pytest

from src.core_runner import CopierRunner
from src.infrastructure.config import AppConfig
from src.domain.models import RemoteFile, CopyStatus, CopyResult
from src.domain.exceptions import DeviceDisconnectedError, FatalError
from src.state.db import Database
from src.state.session import SessionManager
from src.adapters.protocol import FileSource


class EdgeCaseFileSource(FileSource):
    def __init__(self, raise_disconnect_on_list=False):
        self.source_folder = ""
        self.raise_disconnect_on_list = raise_disconnect_on_list

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
        if self.raise_disconnect_on_list:
            raise DeviceDisconnectedError("Device disconnected during scan.")
        yield from []  # Empty folder

    def download_file(self, file: RemoteFile, local_dest, cancel_check=None) -> None:
        pass

    def open_stream(self, file: RemoteFile):
        pass


@pytest.fixture
def mock_config():
    config = MagicMock(spec=AppConfig)
    config.db_path = ":memory:"
    config.device_name = "Edge iPhone"
    config.dest_root = "C:/TestDest"
    config.source_folders = ["DCIM/EmptyFolder"]
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


def test_empty_source_folder(mock_config, test_db):
    """Test behavior when the source folder has no files."""
    source = EdgeCaseFileSource()
    
    session_manager = SessionManager(test_db)
    session_manager.complete = MagicMock()

    runner = CopierRunner(
        config=mock_config,
        source_factory=lambda name: source,
        db=test_db,
        session=session_manager
    )

    with patch("src.core_runner.generate_batches") as mock_gen_batches:
        mock_gen_batches.return_value = []
        runner.run()

        # Should complete gracefully without trying to copy anything
        session_manager.complete.assert_called_once()


def test_device_disconnected_during_scan(mock_config, test_db):
    """Test behavior when the device disconnects during file listing."""
    source = EdgeCaseFileSource(raise_disconnect_on_list=True)
    
    session_manager = SessionManager(test_db)
    session_manager.complete = MagicMock()

    runner = CopierRunner(
        config=mock_config,
        source_factory=lambda name: source,
        db=test_db,
        session=session_manager
    )
    
    # We want to capture the on_error callback
    error_mock = MagicMock()
    runner.on_error = error_mock

    # It should not crash the app, but gracefully handle the exception and call on_error
    runner.run()
    
    error_mock.assert_called_once()
    exception_passed = error_mock.call_args[0][0]
    assert isinstance(exception_passed, DeviceDisconnectedError)
    
    # Complete should NOT be called because it failed
    session_manager.complete.assert_not_called()
