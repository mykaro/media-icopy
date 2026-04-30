"""Integration tests for failure recovery scenarios."""

import pytest
from pathlib import Path
import time

from collections.abc import Generator

from src.adapters.local_source import LocalFileSource
from src.domain.copier import copy_file
from src.domain.models import RemoteFile, CopyTask, CopyStatus
from src.state.db import Database
from src.state.session import SessionManager, SessionState


def test_recovery_full_scenario(
    db: Database, tmp_path: Path, local_source: LocalFileSource
):
    """
    Simulates a crash during copy and verifies that next run
    can resume using the same database state.
    """
    dest_path = tmp_path / "dest"
    dest_path.mkdir()

    # 1. Start session
    manager = SessionManager(db)
    manager.start_new(str(tmp_path), str(dest_path))
    manager.transition(SessionState.COPYING)

    # 2. Copy one file and 'crash'
    files = list(local_source.list_files())
    f1 = files[0]
    task1 = CopyTask(f1, str(dest_path / f1.relative_path))
    result = copy_file(task1, local_source)
    if result.status == CopyStatus.SUCCESS:
        db.register_copied_file(task1.file)

    # Simulate abrupt exit (no cleanup)
    db.close()

    # 3. Resume (new manager instance)
    db_reopened = Database(tmp_path / "test.db")
    manager2 = SessionManager(db_reopened)

    # Verify it entered RECOVERING state
    current_state = manager2.get_current_state()
    assert current_state is not None
    assert current_state["state"] == SessionState.RECOVERING.value

    # Verify f1 is already in DB as copied
    assert db_reopened.is_file_copied(f1.relative_path) is not None

    db_reopened.close()
