from pathlib import Path

from lazyworker.interaction.state import (
    SessionState,
    clear_session_state,
    load_session_state,
    save_session_state,
)


def test_roundtrip(tmp_path: Path) -> None:
    state = SessionState(session_id="A1", bundle_id="com.x", base_url="http://x")
    save_session_state(state, tmp_path)
    assert load_session_state(tmp_path) == state


def test_missing_returns_none(tmp_path: Path) -> None:
    assert load_session_state(tmp_path) is None


def test_clear_is_idempotent(tmp_path: Path) -> None:
    save_session_state(SessionState(session_id="A", bundle_id="b", base_url="u"), tmp_path)
    clear_session_state(tmp_path)
    assert load_session_state(tmp_path) is None
    clear_session_state(tmp_path)
