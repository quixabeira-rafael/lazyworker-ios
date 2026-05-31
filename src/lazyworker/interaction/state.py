from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

SESSION_STATE_FILENAME = "session.json"


class SessionState(BaseModel):
    """Persisted active app-session id across stateless CLI invocations."""

    session_id: str
    bundle_id: str
    base_url: str


def session_state_path(state_dir: Path) -> Path:
    return state_dir / SESSION_STATE_FILENAME


def save_session_state(state: SessionState, state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    session_state_path(state_dir).write_text(state.model_dump_json(indent=2))


def load_session_state(state_dir: Path) -> SessionState | None:
    path = session_state_path(state_dir)
    if not path.exists():
        return None
    return SessionState.model_validate_json(path.read_text())


def clear_session_state(state_dir: Path) -> None:
    session_state_path(state_dir).unlink(missing_ok=True)
