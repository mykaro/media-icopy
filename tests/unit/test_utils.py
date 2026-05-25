"""Comprehensive tests for utility functions, with focus on update checking."""

import json
import pytest
from unittest.mock import patch, MagicMock, call
from urllib.error import HTTPError, URLError

from src.utils import (
    format_size,
    check_for_updates,
    _is_newer,
    format_elapsed,
    calculate_eta,
)


# ---------------------------------------------------------------------------
# format_size
# ---------------------------------------------------------------------------

def test_format_size():
    assert format_size(500) == "500 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1536) == "1.5 KB"
    assert format_size(1024**2) == "1.0 MB"
    assert format_size(int(1.5 * 1024**2)) == "1.5 MB"
    assert format_size(1024**3) == "1.00 GB"
    assert format_size(int(2.25 * 1024**3)) == "2.25 GB"


# ---------------------------------------------------------------------------
# format_elapsed
# ---------------------------------------------------------------------------

def test_format_elapsed():
    assert format_elapsed(0) == "00:00"
    assert format_elapsed(5) == "00:05"
    assert format_elapsed(60) == "01:00"
    assert format_elapsed(65) == "01:05"
    assert format_elapsed(3600) == "60:00"
    assert format_elapsed(3665) == "61:05"


# ---------------------------------------------------------------------------
# calculate_eta
# ---------------------------------------------------------------------------

def test_calculate_eta():
    assert calculate_eta(0, 100, 10.0) == 0
    assert calculate_eta(10, 100, 0.0) == 0

    # 10 items in 10 seconds -> 1 item/sec -> 90 items remaining -> 90 seconds
    assert calculate_eta(10, 100, 10.0) == 90

    # 50 items in 25 seconds -> 2 items/sec -> 50 remaining -> 25 seconds
    assert calculate_eta(50, 100, 25.0) == 25

    # 100 items (done)
    assert calculate_eta(100, 100, 50.0) == 0


# ===========================================================================
# _is_newer — exhaustive version comparison tests
# ===========================================================================

class TestIsNewer:
    """Tests for semantic version comparison logic."""

    # --- Standard semver: newer detected ---
    @pytest.mark.parametrize(
        "current,latest",
        [
            ("1.0.0", "1.0.1"),    # patch bump
            ("1.0.0", "1.1.0"),    # minor bump
            ("1.0.0", "2.0.0"),    # major bump
            ("0.0.1", "0.0.2"),    # smallest bump
            ("0.9.9", "1.0.0"),    # rollover to major
            ("1.9.9", "1.10.0"),   # minor double-digit
        ],
        ids=[
            "patch-bump",
            "minor-bump",
            "major-bump",
            "smallest-bump",
            "rollover-major",
            "minor-double-digit",
        ],
    )
    def test_newer_version_detected(self, current, latest):
        assert _is_newer(current, latest) is True

    # --- Standard semver: NOT newer ---
    @pytest.mark.parametrize(
        "current,latest",
        [
            ("1.0.1", "1.0.0"),    # patch downgrade
            ("1.1.0", "1.0.0"),    # minor downgrade
            ("2.0.0", "1.0.0"),    # major downgrade
            ("2.0.0", "1.9.9"),    # major vs high minor
            ("1.10.0", "1.9.9"),   # double-digit minor
        ],
        ids=[
            "patch-downgrade",
            "minor-downgrade",
            "major-downgrade",
            "major-vs-high-minor",
            "double-digit-minor-no-upgrade",
        ],
    )
    def test_older_version_not_newer(self, current, latest):
        assert _is_newer(current, latest) is False

    # --- Equal versions ---
    @pytest.mark.parametrize(
        "version",
        ["1.0.0", "0.0.0", "99.99.99", "0.1.0"],
        ids=["standard", "zero", "large", "minor-only"],
    )
    def test_equal_versions_not_newer(self, version):
        assert _is_newer(version, version) is False

    # --- Different segment lengths ---
    @pytest.mark.parametrize(
        "current,latest,expected",
        [
            ("1.0", "1.0.1", True),      # latest has extra non-zero segment
            ("1.0.1", "1.0", False),      # current has more segments
            ("1.0", "1.0.0", False),      # latest has extra zero segment — not newer
            ("1", "1.0.1", True),         # single vs triple
            ("1.0.0.0", "1.0.0.1", True), # four segments
        ],
        ids=[
            "short-current-longer-latest",
            "longer-current-short-latest",
            "extra-zero-segment",
            "single-vs-triple",
            "four-segments",
        ],
    )
    def test_different_segment_lengths(self, current, latest, expected):
        assert _is_newer(current, latest) is expected

    # --- Large version numbers ---
    def test_large_version_numbers(self):
        assert _is_newer("1.0.99", "1.0.100") is True
        assert _is_newer("99.99.99", "100.0.0") is True
        assert _is_newer("100.0.0", "99.99.99") is False

    # --- Non-semantic fallback (string comparison) ---
    @pytest.mark.parametrize(
        "current,latest,expected",
        [
            ("v1", "v2", True),
            ("v2", "v1", False),
            ("abc", "abd", True),
            ("beta", "beta", False),
            ("alpha", "beta", True),
        ],
        ids=["v1-v2", "v2-v1", "abc-abd", "equal-strings", "alpha-beta"],
    )
    def test_non_semantic_fallback(self, current, latest, expected):
        assert _is_newer(current, latest) is expected

    # --- Edge cases with empty strings ---
    def test_empty_latest_not_newer(self):
        assert _is_newer("1.0.0", "") is False

    def test_empty_current_with_valid_latest(self):
        # Empty string causes ValueError -> falls back to string comparison
        # "1.0.0" > "" is True
        assert _is_newer("", "1.0.0") is True

    def test_both_empty_not_newer(self):
        assert _is_newer("", "") is False


# ===========================================================================
# check_for_updates — exhaustive HTTP interaction tests
# ===========================================================================

class TestCheckForUpdates:
    """Tests for GitHub API update checking logic."""

    def _make_mock_response(self, status, body_dict):
        """Helper to create a mock urllib response."""
        mock_response = MagicMock()
        mock_response.status = status
        mock_response.read.return_value = json.dumps(body_dict).encode("utf-8")
        return mock_response

    # --- Happy path ---

    @patch("urllib.request.urlopen")
    def test_update_found(self, mock_urlopen):
        """Update available: returns dict with version and url."""
        mock_response = self._make_mock_response(
            200, {"tag_name": "v1.1.0", "html_url": "https://example.com/release"}
        )
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = check_for_updates("1.0.0", "user/repo")

        assert result is not None
        assert result["version"] == "1.1.0"
        assert result["url"] == "https://example.com/release"

    @patch("urllib.request.urlopen")
    def test_no_update_same_version(self, mock_urlopen):
        """Same version: returns None."""
        mock_response = self._make_mock_response(
            200, {"tag_name": "v1.0.0", "html_url": "https://example.com"}
        )
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = check_for_updates("1.0.0", "user/repo")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_no_update_older_version(self, mock_urlopen):
        """API returns older version: returns None."""
        mock_response = self._make_mock_response(
            200, {"tag_name": "v0.9.0", "html_url": "https://example.com"}
        )
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = check_for_updates("1.0.0", "user/repo")
        assert result is None

    # --- tag_name format variations ---

    @patch("urllib.request.urlopen")
    def test_tag_name_without_v_prefix(self, mock_urlopen):
        """tag_name '1.1.0' (no v prefix) should still be parsed."""
        mock_response = self._make_mock_response(
            200, {"tag_name": "1.1.0", "html_url": "https://example.com"}
        )
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = check_for_updates("1.0.0", "user/repo")
        assert result is not None
        assert result["version"] == "1.1.0"

    @patch("urllib.request.urlopen")
    def test_tag_name_empty_string(self, mock_urlopen):
        """Empty tag_name: _is_newer('1.0.0', '') -> False -> None."""
        mock_response = self._make_mock_response(
            200, {"tag_name": "", "html_url": "https://example.com"}
        )
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = check_for_updates("1.0.0", "user/repo")
        assert result is None

    # --- Missing fields ---

    @patch("urllib.request.urlopen")
    def test_missing_tag_name_field(self, mock_urlopen):
        """Response without tag_name: defaults to '' via .get()."""
        mock_response = self._make_mock_response(
            200, {"html_url": "https://example.com"}
        )
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = check_for_updates("1.0.0", "user/repo")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_missing_html_url_field(self, mock_urlopen):
        """Response without html_url: url defaults to '' in result."""
        mock_response = self._make_mock_response(
            200, {"tag_name": "v2.0.0"}
        )
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = check_for_updates("1.0.0", "user/repo")
        assert result is not None
        assert result["version"] == "2.0.0"
        assert result["url"] == ""

    # --- HTTP errors ---

    @patch("urllib.request.urlopen")
    def test_http_404_silent(self, mock_urlopen):
        """404 should be silent (no logging for missing repos)."""
        mock_urlopen.side_effect = HTTPError("url", 404, "Not Found", {}, None)
        result = check_for_updates("1.0.0", "user/repo")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_http_500_logs_warning(self, mock_urlopen):
        """500 should log a warning and return None."""
        mock_urlopen.side_effect = HTTPError(
            "url", 500, "Internal Server Error", {}, None
        )

        with patch("logging.warning") as mock_log:
            result = check_for_updates("1.0.0", "user/repo")

        assert result is None
        mock_log.assert_called_once()
        assert "500" in str(mock_log.call_args)

    @patch("urllib.request.urlopen")
    def test_http_403_rate_limit_logs_warning(self, mock_urlopen):
        """403 (rate limit) should log a warning and return None."""
        mock_urlopen.side_effect = HTTPError("url", 403, "Forbidden", {}, None)

        with patch("logging.warning") as mock_log:
            result = check_for_updates("1.0.0", "user/repo")

        assert result is None
        mock_log.assert_called_once()

    # --- Network errors ---

    @patch("urllib.request.urlopen")
    def test_url_error_network_unreachable(self, mock_urlopen):
        """URLError (network down): returns None."""
        mock_urlopen.side_effect = URLError("Network unreachable")
        result = check_for_updates("1.0.0", "user/repo")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_timeout_error(self, mock_urlopen):
        """Timeout should be caught and return None."""
        mock_urlopen.side_effect = TimeoutError("Connection timed out")

        result = check_for_updates("1.0.0", "user/repo")
        assert result is None

    # --- Invalid response data ---

    @patch("urllib.request.urlopen")
    def test_invalid_json_response(self, mock_urlopen):
        """Malformed JSON body: caught by generic Exception handler."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"not valid json {{"
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = check_for_updates("1.0.0", "user/repo")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_non_200_status_returns_none(self, mock_urlopen):
        """Status 204 (No Content): skips parsing, returns None."""
        mock_response = MagicMock()
        mock_response.status = 204
        mock_response.read.return_value = b""
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = check_for_updates("1.0.0", "user/repo")
        assert result is None

    # --- api_url parameter ---

    @patch("urllib.request.urlopen")
    def test_custom_api_url_used(self, mock_urlopen):
        """When api_url is provided, it takes priority over repo."""
        mock_response = self._make_mock_response(
            200, {"tag_name": "v2.0.0", "html_url": "https://custom.com"}
        )
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = check_for_updates(
            "1.0.0", "user/repo", api_url="https://custom.api/releases"
        )

        assert result is not None
        # Verify the custom URL was used in the Request
        req_obj = mock_urlopen.call_args[0][0]
        assert req_obj.full_url == "https://custom.api/releases"

    @patch("urllib.request.urlopen")
    def test_default_url_constructed_from_repo(self, mock_urlopen):
        """When api_url is None, URL is constructed from repo."""
        mock_response = self._make_mock_response(
            200, {"tag_name": "v1.0.0", "html_url": "https://example.com"}
        )
        mock_urlopen.return_value.__enter__.return_value = mock_response

        check_for_updates("1.0.0", "mykaro/media-icopy")

        req_obj = mock_urlopen.call_args[0][0]
        assert req_obj.full_url == (
            "https://api.github.com/repos/mykaro/media-icopy/releases/latest"
        )

    # --- User-Agent header ---

    @patch("urllib.request.urlopen")
    def test_user_agent_header_sent(self, mock_urlopen):
        """Request must include User-Agent header."""
        mock_response = self._make_mock_response(
            200, {"tag_name": "v1.0.0", "html_url": "https://example.com"}
        )
        mock_urlopen.return_value.__enter__.return_value = mock_response

        check_for_updates("1.0.0", "user/repo")

        req_obj = mock_urlopen.call_args[0][0]
        assert req_obj.get_header("User-agent") == "Media-iCopy-Updater"

    # --- Timeout parameter ---

    @patch("urllib.request.urlopen")
    def test_request_has_timeout(self, mock_urlopen):
        """urlopen must be called with a timeout."""
        mock_response = self._make_mock_response(
            200, {"tag_name": "v1.0.0", "html_url": "https://example.com"}
        )
        mock_urlopen.return_value.__enter__.return_value = mock_response

        check_for_updates("1.0.0", "user/repo")

        _, kwargs = mock_urlopen.call_args
        assert "timeout" in kwargs
        assert kwargs["timeout"] == 5
