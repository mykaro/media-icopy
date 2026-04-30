"""Integration tests for the SQLite Database handler."""

import pytest
from pathlib import Path
import time

from collections.abc import Generator

from src.state.db import Database
from src.domain.models import RemoteFile, CopyTask


def test_db_initialization(db: Database):
    """Ensure database is initialized with tables."""
    cursor = db.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='copied_files'"
    )
    assert cursor.fetchone() is not None


def test_register_and_check_copied_file(db: Database):
    """Test registering a file and checking its status."""
    file = RemoteFile(
        object_id="obj1",
        relative_path="DCIM/100APPLE/IMG_0001.JPG",
        name="IMG_0001.JPG",
        size_bytes=1024,
        modified_at=time.time(),
    )

    # Initially not copied
    assert db.is_file_copied(file.relative_path) is None

    # Register
    db.register_copied_file(file)

    # Now it should be found
    record = db.is_file_copied(file.relative_path)
    assert record is not None
    assert record["relative_path"] == file.relative_path
    assert record["size_bytes"] == 1024


def test_session_lifecycle(db: Database):
    """Test creating, updating, and deleting sessions."""
    # Create
    session_id = db.create_session("/source", "/dest", "NEW")
    assert session_id > 0

    # Get last session
    session = db.get_last_session()
    assert session is not None
    assert session["id"] == session_id
    assert session["state"] == "NEW"

    # Update
    db.update_session_state(session_id, "COPYING", total_files=100, batch_index=5)
    updated = db.get_last_session()
    assert updated is not None
    assert updated["state"] == "COPYING"
    assert updated["total_files"] == 100
    assert updated["batch_index"] == 5

    # Delete
    db.delete_session(session_id)
    assert db.get_last_session() is None


def test_retry_queue(db: Database):
    """Test adding to and retrieving from the retry queue."""
    session_id = db.create_session("/source", "/dest", "COPYING")
    file = RemoteFile("obj1", "path/1.jpg", "1.jpg", 100, time.time())
    task = CopyTask(file, "/local/path/1.jpg", attempt=1)

    # Add to queue
    db.add_to_retry_queue(session_id, task, "MTP timeout", time.time() - 10)

    # Retrieve
    tasks = db.get_retry_tasks(session_id)
    assert len(tasks) == 1
    assert tasks[0]["relative_path"] == "path/1.jpg"
    assert tasks[0]["last_error"] == "MTP timeout"

    # Future task shouldn't be picked up
    db.add_to_retry_queue(session_id, task, "Future error", time.time() + 3600)
    tasks_now = db.get_retry_tasks(session_id)
    assert len(tasks_now) == 1  # Still 1, the future one is skipped

    # Clear
    db.clear_retry_queue(session_id)
    assert len(db.get_retry_tasks(session_id)) == 0
