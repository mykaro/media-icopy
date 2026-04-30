"""Data Access Layer for SQLite.

Handles all database operations including session state,
track of copied files, and retry queue.
"""

import sqlite3
from pathlib import Path
from typing import Any
import time
import threading

from ..domain.models import RemoteFile, CopyTask, CopyStatus
from ..paths import resource_path


class Database:
    """Handles connections and operations with SQLite database."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database with schema."""
        schema_path = Path(resource_path("src", "state", "schema.sql"))
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()

        with self._lock:
            # WAL mode allows concurrent reads and a single writer without locking conflicts
            self.connection.execute("PRAGMA journal_mode=WAL")
            with self.connection:
                self.connection.executescript(schema_sql)

    @property
    def connection(self) -> sqlite3.Connection:
        """Get or create sqlite3 connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            # Enable foreign keys
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Copied Files Operations ---

    def is_file_copied(self, relative_path: str) -> dict[str, Any] | None:
        """Check if file was already copied and return its record.

        Args:
            relative_path: The relative path of the file to check.

        Returns:
            A dictionary containing the record if found, else None.
        """
        cursor = self.connection.execute(
            "SELECT * FROM copied_files WHERE relative_path = ?", (relative_path,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def register_copied_file(self, file: RemoteFile) -> None:
        """Register a successfully copied file in the database.

        Args:
            file: The RemoteFile object representing the copied file.
        """
        with self._lock:
            with self.connection:
                self.connection.execute(
                    """
                    INSERT OR REPLACE INTO copied_files (relative_path, size_bytes, copied_at)
                    VALUES (?, ?, ?)
                    """,
                    (file.relative_path, file.size_bytes, time.time()),
                )

    # --- Session Operations ---

    def create_session(self, source_root: str, dest_root: str, state: str) -> int:
        """Create a new session and return its ID.

        Args:
            source_root: The root path of the source.
            dest_root: The root path of the destination.
            state: The initial state of the session.

        Returns:
            The ID of the newly created session.
        """
        with self._lock:
            with self.connection:
                cursor = self.connection.execute(
                    """
                    INSERT INTO sessions (started_at, state, source_root, dest_root)
                    VALUES (?, ?, ?, ?)
                    """,
                    (time.time(), state, source_root, dest_root),
                )
                return cursor.lastrowid or 0

    def get_last_session(self) -> dict[str, Any] | None:
        """Get the most recent session record.

        Returns:
            A dictionary representing the last session, or None if no sessions exist.
        """
        cursor = self.connection.execute(
            "SELECT * FROM sessions ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_session_state(self, session_id: int, state: str, **kwargs: Any) -> None:
        """Update session state and other optional fields.

        Args:
            session_id: The ID of the session to update.
            state: The new state of the session.
            **kwargs: Additional fields to update (e.g., total_files, batch_index).
        """
        allowed_fields = {"total_files", "batch_index"}
        updates = ["state = ?"]
        params: list[Any] = [state]

        for key, value in kwargs.items():
            if key in allowed_fields:
                updates.append(f"{key} = ?")
                params.append(value)

        params.append(session_id)
        query = f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?"

        with self._lock:
            with self.connection:
                self.connection.execute(query, params)

    def delete_session(self, session_id: int) -> None:
        """Delete session record (usually after success).

        Args:
            session_id: The ID of the session to delete.
        """
        with self._lock:
            with self.connection:
                self.connection.execute(
                    "DELETE FROM sessions WHERE id = ?", (session_id,)
                )

    # --- Retry Queue Operations ---

    def add_to_retry_queue(
        self, session_id: int, task: CopyTask, last_error: str, scheduled_at: float
    ) -> None:
        """Add a failed task to the retry queue.

        Args:
            session_id: The ID of the current session.
            task: The copy task that failed.
            last_error: A string describing the error.
            scheduled_at: The timestamp when this task should be retried.
        """
        with self._lock:
            with self.connection:
                self.connection.execute(
                    """
                    INSERT INTO retry_queue 
                    (session_id, relative_path, object_id, size_bytes, attempt, last_error, scheduled_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        task.file.relative_path,
                        task.file.object_id,
                        task.file.size_bytes,
                        task.attempt,
                        last_error,
                        scheduled_at,
                    ),
                )

    def get_retry_tasks(self, session_id: int) -> list[dict[str, Any]]:
        """Get all tasks waiting for retry for a specific session.

        Args:
            session_id: The ID of the session.

        Returns:
            A list of task dictionaries that are ready to be retried.
        """
        cursor = self.connection.execute(
            "SELECT * FROM retry_queue WHERE session_id = ? AND scheduled_at <= ?",
            (session_id, time.time()),
        )
        return [dict(row) for row in cursor.fetchall()]

    def clear_retry_queue(self, session_id: int) -> None:
        """Clear retry queue for a specific session.

        Args:
            session_id: The ID of the session.
        """
        with self._lock:
            with self.connection:
                self.connection.execute(
                    "DELETE FROM retry_queue WHERE session_id = ?", (session_id,)
                )

    # --- Utility Operations ---

    def clear_all_state(self) -> None:
        """Completely clears all state from the database for a fresh start."""
        with self._lock:
            with self.connection:
                self.connection.executescript("""
                    DELETE FROM retry_queue;
                    DELETE FROM copied_files;
                    DELETE FROM sessions;
                    """)
