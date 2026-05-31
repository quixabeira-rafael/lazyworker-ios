from __future__ import annotations

from pathlib import Path

from lazyworker.config import Config

# Shared across every project: the WebDriverAgent checkout and its build products.
# Re-cloning/re-building WDA per project would be wasteful, so this stays global.
HOME_DIR = Path.home() / ".lazyworker"


def home_dir() -> Path:
    """Global directory for shared, build-time artifacts (WDA source + DerivedData)."""
    return HOME_DIR


def state_dir(start: str | Path | None = None) -> Path:
    """Per-project runtime state dir (run.json, session.json, screens, logs).

    Anchored next to the discovered ``lazyworker.toml`` as ``<repo>/.lazyworker`` so two
    repos/worktrees keep independent state and can drive different simulators at once.
    Falls back to the global home dir when no project config is found.
    """
    config_path = Config.discover(start)
    if config_path is not None:
        return config_path.parent / ".lazyworker"
    return HOME_DIR
