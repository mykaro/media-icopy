"""Unit tests for the SessionManager and state transitions."""

import pytest
from pathlib import Path

from collections.abc import Generator

from src.state.db import Database
from src.state.session import SessionManager, SessionState


def test_session_start_new(db: Database):
    manager = SessionManager(db)
    assert manager.current_session_id is None

    manager.start_new("/src", "/dest")
    assert manager.current_session_id is not None

    state = manager.get_current_state()
    assert state is not None
    assert state["state"] == SessionState.NEW.value


def test_session_transitions(db: Database):
    manager = SessionManager(db)
    manager.start_new("/src", "/dest")

    manager.transition(SessionState.SCANNING)
    state1 = manager.get_current_state()
    assert state1 is not None
    assert state1["state"] == SessionState.SCANNING.value

    manager.transition(SessionState.COPYING, batch_index=2)
    state = manager.get_current_state()
    assert state is not None
    assert state["state"] == SessionState.COPYING.value
    assert state["batch_index"] == 2


def test_session_recovery_on_init(db: Database):
    # Manually create an unfinished session in DB
    db.create_session("/s", "/d", SessionState.SCANNING.value)

    # Initialize manager — should detect it and transition to RECOVERING
    manager = SessionManager(db)
    assert manager.current_session_id is not None
    state = manager.get_current_state()
    assert state is not None
    assert state["state"] == SessionState.RECOVERING.value


def test_session_completion(db: Database):
    manager = SessionManager(db)
    manager.start_new("/src", "/dest")

    manager.complete()
    assert manager.current_session_id is None
    assert manager.get_current_state() is None  # Since we delete on complete per spec
