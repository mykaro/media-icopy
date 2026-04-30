import pytest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError
from src.utils import (
    format_size,
    check_for_updates,
    _is_newer,
    format_elapsed,
    calculate_eta,
)


def test_format_size():
    assert format_size(500) == "500 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1536) == "1.5 KB"
    assert format_size(1024**2) == "1.0 MB"
    assert format_size(int(1.5 * 1024**2)) == "1.5 MB"
    assert format_size(1024**3) == "1.00 GB"
    assert format_size(int(2.25 * 1024**3)) == "2.25 GB"


def test_format_elapsed():
    assert format_elapsed(0) == "00:00"
    assert format_elapsed(5) == "00:05"
    assert format_elapsed(60) == "01:00"
    assert format_elapsed(65) == "01:05"
    assert format_elapsed(3600) == "60:00"
    assert format_elapsed(3665) == "61:05"


def test_calculate_eta():
    assert calculate_eta(0, 100, 10.0) == 0
    assert calculate_eta(10, 100, 0.0) == 0

    # 10 items in 10 seconds -> 1 item/sec -> 90 items remaining -> 90 seconds
    assert calculate_eta(10, 100, 10.0) == 90

    # 50 items in 25 seconds -> 2 items/sec -> 50 remaining -> 25 seconds
    assert calculate_eta(50, 100, 25.0) == 25

    # 100 items (done)
    assert calculate_eta(100, 100, 50.0) == 0


def test_is_newer():
    assert _is_newer("1.0.0", "1.0.1") is True
    assert _is_newer("1.0.1", "1.0.0") is False
    assert _is_newer("1.0.0", "1.1.0") is True
    assert _is_newer("1.0.0", "2.0.0") is True
    assert _is_newer("1.0", "1.0.1") is True
    assert _is_newer("1.0.1", "1.0") is False
    assert _is_newer("1.0.0", "1.0.0") is False

    # Non-semantic fallbacks
    assert _is_newer("v1", "v2") is True
    assert _is_newer("v2", "v1") is False


@patch("urllib.request.urlopen")
def test_check_for_updates_found(mock_urlopen):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = (
        b'{"tag_name": "v1.1.0", "html_url": "http://example.com"}'
    )

    # Enter context manager
    mock_urlopen.return_value.__enter__.return_value = mock_response

    result = check_for_updates("1.0.0", "user/repo")
    assert result is not None
    assert result["version"] == "1.1.0"
    assert result["url"] == "http://example.com"


@patch("urllib.request.urlopen")
def test_check_for_updates_not_found(mock_urlopen):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = (
        b'{"tag_name": "v1.0.0", "html_url": "http://example.com"}'
    )

    mock_urlopen.return_value.__enter__.return_value = mock_response

    result = check_for_updates("1.0.0", "user/repo")
    assert result is None


@patch("urllib.request.urlopen")
def test_check_for_updates_http_error(mock_urlopen):
    mock_urlopen.side_effect = HTTPError("url", 404, "Not Found", {}, None)
    result = check_for_updates("1.0.0", "user/repo")
    assert result is None


@patch("urllib.request.urlopen")
def test_check_for_updates_url_error(mock_urlopen):
    mock_urlopen.side_effect = URLError("Network unreachable")
    result = check_for_updates("1.0.0", "user/repo")
    assert result is None
