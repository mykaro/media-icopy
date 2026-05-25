"""Session state management and state machine logic."""

from enum import Enum
from typing import Any
from .db import Database


class SessionState(Enum):
    NEW = "NEW"
    SCANNING = "SCANNING"
    BATCHING = "BATCHING"
    COPYING = "COPYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"


class SessionManager:
    """
    Manages the lifecycle of a copying session.
    Encapsulates state transitions and persistence.
    """

    def __init__(self, db: Database):
        self.db = db
        self.current_session_id: int | None = None
        self._load_last_session()

    def _load_last_session(self) -> None:
        """Checks for existing session in the database."""
        session = self.db.get_last_session()
        if session:
            self.current_session_id = session["id"]
            # If session is in a semi-finished state, we might want to start in RECOVERING
            if session["state"] not in [
                SessionState.COMPLETED.value,
                SessionState.FAILED.value,
            ]:
                self.transition(SessionState.RECOVERING)

    @property
    def is_active(self) -> bool:
        """Returns True if there is an unfinished session."""
        if self.current_session_id is None:
            return False
        session = self.db.get_last_session()
        return bool(session and session["state"] != SessionState.COMPLETED.value)

    def start_new(self, source_root: str, dest_root: str) -> None:
        """Starts a fresh session, deleting any old ones if necessary.

        Args:
            source_root: The root folder of the source.
            dest_root: The root folder of the destination.
        """
        if self.current_session_id:
            # Clear retry queue first to satisfy FOREIGN KEY constraints
            self.db.clear_retry_queue(self.current_session_id)
            self.db.delete_session(self.current_session_id)

        self.current_session_id = self.db.create_session(
            source_root, dest_root, SessionState.NEW.value
        )

    def transition(self, new_state: SessionState, **kwargs: Any) -> None:
        """
        Transitions to a new state and persists it.
        Only valid if a session is currently active.

        Args:
            new_state: The new SessionState to transition to.
            **kwargs: Additional parameters to update in the session record.
        """
        if self.current_session_id is None:
            raise RuntimeError("No active session to transition.")

        self.db.update_session_state(self.current_session_id, new_state.value, **kwargs)

    def get_current_state(self) -> dict[str, Any] | None:
        """Returns the current session record from the database.

        Returns:
            The current session dictionary or None.
        """
        return self.db.get_last_session()

    def complete(self) -> None:
        """Marks the session as completed and cleans up."""
        if self.current_session_id:
            self.transition(SessionState.COMPLETED)
            # Clear retry queue to satisfy FOREIGN KEY constraints before deleting session
            self.db.clear_retry_queue(self.current_session_id)
            self.db.delete_session(self.current_session_id)
            self.current_session_id = None
