"""Unit tests for the retry logic."""

import pytest
import time
from unittest.mock import MagicMock

from src.domain.retry import execute_with_retry
from src.domain.exceptions import TransientError, FatalError


def test_retry_success_first_time():
    func = MagicMock(return_value="success")
    result = execute_with_retry(func, 3, [0, 0])

    assert result == "success"
    assert func.call_count == 1


def test_retry_success_after_failure(monkeypatch):
    # Mock sleep to speed up tests
    monkeypatch.setattr(time, "sleep", lambda x: None)

    func = MagicMock()
    func.side_effect = [TransientError("fail 1"), "success"]

    result = execute_with_retry(func, 3, [0, 0])

    assert result == "success"
    assert func.call_count == 2


def test_retry_max_attempts_reached(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda x: None)

    func = MagicMock()
    func.side_effect = TransientError("persistent fail")

    with pytest.raises(TransientError, match="persistent fail"):
        execute_with_retry(func, 3, [0, 0])

    assert func.call_count == 3


def test_retry_fatal_stops_immediately():
    """FatalError should stop retries immediately and not use backoff."""
    call_count = 0

    def fail_fatal():
        nonlocal call_count
        call_count += 1
        raise FatalError("Disk Full")

    start_time = time.time()
    with pytest.raises(FatalError, match="Disk Full"):
        execute_with_retry(fail_fatal, 3, [1, 1, 1])

    # Should only run once
    assert call_count == 1
    # Should not wait
    assert time.time() - start_time < 0.5


def test_retry_calls_on_transient_error():
    """Should call on_transient_error callback when TransientError occurs."""
    call_count = 0
    callback_calls = 0

    def fail_once():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TransientError("Connection Lost")
        return "success"

    def callback(e):
        nonlocal callback_calls
        callback_calls += 1
        assert isinstance(e, TransientError)

    result = execute_with_retry(fail_once, 3, [0, 0, 0], on_transient_error=callback)

    assert result == "success"
    assert call_count == 2
    assert callback_calls == 1
