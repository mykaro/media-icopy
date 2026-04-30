import pytest
from unittest.mock import MagicMock, patch, ANY
from pathlib import Path
import sys

# Mock win32com and pythoncom BEFORE importing MTPFileSource
mock_win32com = MagicMock()
mock_pythoncom = MagicMock()
sys.modules["win32com"] = mock_win32com
sys.modules["win32com.client"] = mock_win32com.client
sys.modules["pythoncom"] = mock_pythoncom

from src.adapters.mtp_adapter import MTPFileSource, MTPDeviceRegistry
from src.domain.exceptions import DeviceDisconnectedError, FatalError
from src.domain.models import RemoteFile


@pytest.fixture
def mock_shell():
    with patch("src.adapters.mtp_adapter.win32com.client.Dispatch") as mock_dispatch:
        shell = MagicMock()
        mock_dispatch.return_value = shell
        yield shell


def test_registry_list_available_devices(mock_shell):
    this_pc = MagicMock()
    mock_shell.NameSpace.return_value = this_pc

    item1 = MagicMock(IsFolder=True, Path="C:\\", Name="Local Disk")
    item2 = MagicMock(
        IsFolder=True, Path="::{123}", Name="Test iPhone"
    )  # No local path = MTP

    with patch("os.path.exists", side_effect=lambda p: p == "C:\\"):
        this_pc.Items.return_value = [item1, item2]
        devices = MTPDeviceRegistry.list_available_devices()
        assert devices == ["Test iPhone"]


@patch.dict("sys.modules", {"ctypes": MagicMock()})
def test_registry_refresh_shell_cache():
    import sys

    mock_ctypes = sys.modules["ctypes"]
    MTPDeviceRegistry.refresh_shell_cache()
    mock_ctypes.windll.shell32.SHChangeNotify.assert_called_once()
    mock_ctypes.windll.user32.PostMessageW.assert_called_once()


@pytest.fixture
def mtp_source(mock_shell):
    return MTPFileSource(device_name="Test Device", source_folder="DCIM")


def test_is_connected_success(mtp_source, mock_shell):
    this_pc = MagicMock()
    mock_shell.NameSpace.return_value = this_pc

    device_item = MagicMock(Name="Test Device")
    device_folder = MagicMock()
    device_folder.Items.return_value.Count = 1  # Has internal storage
    device_item.GetFolder = device_folder

    # Mock items enumeration
    items_mock = MagicMock()
    items_mock.Count = 1
    items_mock.Item.side_effect = lambda i: device_item
    this_pc.Items.return_value = items_mock

    assert mtp_source.is_connected() is True


def test_is_connected_disconnected(mtp_source, mock_shell):
    this_pc = MagicMock()
    mock_shell.NameSpace.return_value = this_pc

    items_mock = MagicMock()
    items_mock.Count = 0
    this_pc.Items.return_value = items_mock

    assert mtp_source.is_connected() is False


def test_list_subfolders(mtp_source, mock_shell):
    # Setup hierarchy
    this_pc = MagicMock()
    mock_shell.NameSpace.return_value = this_pc

    device_item = MagicMock(Name="Test Device")
    device_folder = MagicMock()
    device_item.GetFolder = device_folder

    this_pc_items = MagicMock()
    this_pc_items.Count = 1
    this_pc_items.Item.side_effect = lambda i: device_item
    this_pc.Items.return_value = this_pc_items

    # Internal storage folder
    internal_storage = MagicMock(Name="Internal Storage", IsFolder=True)
    dcim_folder = MagicMock(Name="DCIM", IsFolder=True)
    device_folder.Items.return_value = [internal_storage, dcim_folder]

    folders = mtp_source.list_subfolders()
    assert folders == ["DCIM", "Internal Storage"]


def test_list_files(mtp_source, mock_shell):
    # Very deep mock setup for MTP hierarchy
    this_pc = MagicMock()
    mock_shell.NameSpace.return_value = this_pc

    device_item = MagicMock(Name="Test Device")
    device_folder = MagicMock()
    device_item.GetFolder = device_folder

    this_pc_items = MagicMock()
    this_pc_items.Count = 1
    this_pc_items.Item.side_effect = lambda i: device_item
    this_pc.Items.return_value = this_pc_items

    dcim_item = MagicMock(Name="DCIM", IsFolder=True)
    dcim_folder = MagicMock()
    dcim_item.GetFolder = dcim_folder
    device_folder.Items.return_value = [dcim_item]
    # Support ParseName() fast path used by _resolve_path
    device_folder.ParseName = MagicMock(
        side_effect=lambda name: dcim_item if name == "DCIM" else None
    )

    file_item = MagicMock(Name="photo.jpg", IsFolder=False)
    file_item.ExtendedProperty.return_value = 1024
    dcim_folder.Items.return_value = [file_item]

    files = list(mtp_source.list_files())

    assert len(files) == 1
    assert files[0].name == "photo.jpg"
    assert files[0].size_bytes == 1024
    assert files[0].relative_path == "DCIM/photo.jpg"
    assert files[0].object_id == "DCIM/photo.jpg"


def test_list_files_skip_aae(mtp_source, mock_shell):
    # Setup similar to above but with AAE file
    this_pc = MagicMock()
    mock_shell.NameSpace.return_value = this_pc

    device_item = MagicMock(Name="Test Device")
    device_folder = MagicMock()
    device_item.GetFolder = device_folder
    this_pc_items = MagicMock()
    this_pc_items.Count = 1
    this_pc_items.Item.side_effect = lambda i: device_item
    this_pc.Items.return_value = this_pc_items

    dcim_item = MagicMock(Name="DCIM", IsFolder=True)
    dcim_folder = MagicMock()
    dcim_item.GetFolder = dcim_folder
    device_folder.Items.return_value = [dcim_item]
    # Support ParseName() fast path used by _resolve_path
    device_folder.ParseName = MagicMock(
        side_effect=lambda name: dcim_item if name == "DCIM" else None
    )

    file_item = MagicMock(Name="photo.aae", IsFolder=False)
    dcim_folder.Items.return_value = [file_item]

    # Should skip
    files = list(mtp_source.list_files(skip_aae=True))
    assert len(files) == 0


@patch("src.adapters.mtp_adapter.time.sleep")
def test_download_file(mock_sleep, mtp_source, mock_shell, tmp_path):
    dest_file = tmp_path / "dest" / "photo.jpg"

    # Mock find item
    target_item = MagicMock()
    mtp_source._find_file_item = MagicMock(return_value=target_item)

    remote_file = RemoteFile("DCIM/photo.jpg", "photo.jpg", "photo.jpg", 1024, 0)

    # Mock temp file creation so the loop exits
    def side_effect_copyhere(item, flags):
        # Pretend Windows copied it
        temp_dir = dest_file.parent / next(dest_file.parent.glob(".mtp_tmp_*"))
        actual_tmp = temp_dir / "photo.jpg"
        actual_tmp.parent.mkdir(parents=True, exist_ok=True)
        with open(actual_tmp, "wb") as f:
            f.write(b"x" * 1024)

    dest_namespace = MagicMock()
    dest_namespace.CopyHere.side_effect = side_effect_copyhere
    mock_shell.NameSpace.return_value = dest_namespace

    mtp_source.download_file(remote_file, dest_file)

    # Verify file was moved to final dest
    assert dest_file.exists()
    assert dest_file.stat().st_size == 1024
