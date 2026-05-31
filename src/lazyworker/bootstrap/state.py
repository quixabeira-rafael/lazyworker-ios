from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

RUN_STATE_FILENAME = "run.json"


class RunState(BaseModel):
    """Persisted state of a running WebDriverAgent instance."""

    udid: str
    port: int
    pid: int
    base_url: str
    kind: str
    forward_pid: int | None = None


def run_state_path(state_dir: Path) -> Path:
    return state_dir / RUN_STATE_FILENAME


def save_run_state(state: RunState, state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    run_state_path(state_dir).write_text(state.model_dump_json(indent=2))


def load_run_state(state_dir: Path) -> RunState | None:
    path = run_state_path(state_dir)
    if not path.exists():
        return None
    return RunState.model_validate_json(path.read_text())


def clear_run_state(state_dir: Path) -> None:
    run_state_path(state_dir).unlink(missing_ok=True)
