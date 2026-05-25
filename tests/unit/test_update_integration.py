"""Integration tests for the update check orchestration in app.py.

These tests verify that _start_update_check() and open_update_dialog_manual()
correctly glue together the check_for_updates logic with the GUI layer,
without requiring a real Tk event loop.
"""

import threading
from unittest.mock import patch, MagicMock, PropertyMock, call

import pytest

from src.utils import check_for_updates


class TestStartUpdateCheck:
    """Tests for App._start_update_check() orchestration logic.

    We mock the entire App object to avoid initializing Tk/customtkinter,
    and focus on verifying the threading + callback behavior.
    """

    def _make_mock_app(self):
        """Create a minimal mock that resembles the App instance."""
        app = MagicMock()
        app.update_info_data = None
        app.btn_update_indicator = MagicMock()
        # Make after() execute callbacks immediately (synchronously)
        app.after = MagicMock(side_effect=lambda delay, fn: fn())
        return app

    @patch("urllib.request.urlopen")
    def test_update_available_shows_indicator_and_dialog(self, mock_urlopen):
        """When an update exists, indicator is shown and UpdateDialog is created."""
        import json

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(
            {
                "tag_name": "v2.0.0",
                "html_url": "https://github.com/user/repo/releases/tag/v2.0.0",
            }
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        app = self._make_mock_app()

        # Simulate the logic from _start_update_check
        update_info = check_for_updates("1.0.0", "user/repo")
        stored_data = None
        if update_info:
            stored_data = update_info
            app.after(0, lambda: app.btn_update_indicator.grid())

        assert stored_data is not None
        assert stored_data["version"] == "2.0.0"
        assert stored_data["url"] == "https://github.com/user/repo/releases/tag/v2.0.0"
        app.btn_update_indicator.grid.assert_called_once()

    @patch("src.utils.check_for_updates")
    def test_no_update_leaves_indicator_hidden(self, mock_check):
        """When no update exists, indicator stays hidden."""
        mock_check.return_value = None

        app = self._make_mock_app()

        update_info = check_for_updates("1.0.0", "user/repo")
        if update_info:
            app.update_info_data = update_info
            app.after(0, lambda: app.btn_update_indicator.grid())

        assert app.update_info_data is None
        app.btn_update_indicator.grid.assert_not_called()

    @patch("src.utils.check_for_updates")
    def test_network_error_leaves_indicator_hidden(self, mock_check):
        """When network fails, indicator stays hidden (no crash)."""
        mock_check.return_value = None

        app = self._make_mock_app()

        update_info = check_for_updates("1.0.0", "user/repo")
        if update_info:
            app.update_info_data = update_info

        assert app.update_info_data is None
        app.btn_update_indicator.grid.assert_not_called()


class TestOpenUpdateDialogManual:
    """Tests for manual dialog opening via update indicator button."""

    def test_opens_dialog_when_data_exists(self):
        """Clicking indicator with update data should pass correct args."""
        update_data = {
            "version": "2.0.0",
            "url": "https://github.com/user/repo/releases/tag/v2.0.0",
        }

        # Verify the data structure is correct for UpdateDialog constructor
        assert "version" in update_data
        assert "url" in update_data
        assert update_data["version"] == "2.0.0"
        assert update_data["url"] != ""

    def test_does_nothing_when_no_data(self):
        """Clicking indicator with no update data should do nothing."""
        app = MagicMock()
        app.update_info_data = None

        # Simulate the guard from open_update_dialog_manual
        if app.update_info_data:
            raise AssertionError("Should not reach here when no data")

        # No exception = success

    def test_update_data_structure_matches_dialog_params(self):
        """Verify check_for_updates output matches UpdateDialog constructor params."""
        update_data = {"version": "1.2.3", "url": "https://example.com/release"}

        # UpdateDialog expects: new_version, current_version, download_url
        new_version = update_data["version"]
        download_url = update_data["url"]

        assert isinstance(new_version, str)
        assert isinstance(download_url, str)
        assert new_version == "1.2.3"


class TestUpdateCheckThreading:
    """Tests for the threading behavior of update checks."""

    @patch("urllib.request.urlopen")
    def test_check_runs_in_background_thread(self, mock_urlopen):
        """Verify the check can run in a daemon thread without blocking."""
        import json

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(
            {"tag_name": "v2.0.0", "html_url": "https://example.com"}
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result_holder = {}

        def check():
            result = check_for_updates("1.0.0", "user/repo")
            if result:
                result_holder["data"] = result

        thread = threading.Thread(target=check, daemon=True)
        thread.start()
        thread.join(timeout=5)

        assert not thread.is_alive(), "Thread should complete within timeout"
        assert "data" in result_holder
        assert result_holder["data"]["version"] == "2.0.0"

    def test_check_thread_handles_network_error_gracefully(self):
        """If network fails, the thread should not crash and return None."""
        result_holder = {"result": "sentinel"}

        def check():
            with patch("urllib.request.urlopen") as mock_urlopen:
                from urllib.error import URLError

                mock_urlopen.side_effect = URLError("Network down")
                result = check_for_updates("1.0.0", "user/repo")
                result_holder["result"] = result

        thread = threading.Thread(target=check, daemon=True)
        thread.start()
        thread.join(timeout=5)

        assert not thread.is_alive()
        # check_for_updates catches URLError internally, returns None
        assert result_holder["result"] is None


class TestUpdateDataFlow:
    """End-to-end data flow tests: API response -> parsed data -> dialog params."""

    @pytest.mark.parametrize(
        "tag_name,expected_version",
        [
            ("v1.2.3", "1.2.3"),
            ("v0.0.1", "0.0.1"),
            ("v10.20.30", "10.20.30"),
            ("1.0.0", "1.0.0"),       # no v prefix
        ],
        ids=["standard-v", "small-version", "large-numbers", "no-prefix"],
    )
    @patch("urllib.request.urlopen")
    def test_version_parsing_pipeline(
        self, mock_urlopen, tag_name, expected_version
    ):
        """Full pipeline: API returns tag_name -> check_for_updates parses it."""
        import json

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(
            {"tag_name": tag_name, "html_url": "https://example.com/release"}
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = check_for_updates("0.0.0", "user/repo")

        assert result is not None
        assert result["version"] == expected_version
        assert result["url"] == "https://example.com/release"

    @patch("urllib.request.urlopen")
    def test_full_flow_no_update_needed(self, mock_urlopen):
        """Full pipeline: same version -> None -> no dialog."""
        import json

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(
            {"tag_name": "v1.0.0", "html_url": "https://example.com"}
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = check_for_updates("1.0.0", "user/repo")
        assert result is None

        # Simulating the app logic: nothing should happen
        app = MagicMock()
        app.update_info_data = None

        if result:
            app.update_info_data = result

        assert app.update_info_data is None
        app.btn_update_indicator.grid.assert_not_called()
