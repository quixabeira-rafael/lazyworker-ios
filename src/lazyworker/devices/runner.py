from __future__ import annotations

import subprocess
from collections.abc import Sequence
from typing import Protocol, runtime_checkable


class CommandError(Exception):
    """Raised when a command exits with a non-zero status."""

    def __init__(self, command: Sequence[str], returncode: int, stderr: str) -> None:
        super().__init__(f"command {list(command)} failed ({returncode}): {stderr.strip()}")
        self.command = list(command)
        self.returncode = returncode
        self.stderr = stderr


@runtime_checkable
class CommandRunner(Protocol):
    """Runs an external command and returns its stdout."""

    def run(self, args: Sequence[str], *, timeout: float | None = None) -> str: ...


class SubprocessRunner:
    """Default runner backed by :mod:`subprocess`."""

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    def run(self, args: Sequence[str], *, timeout: float | None = None) -> str:
        process = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=timeout if timeout is not None else self._timeout,
        )
        if process.returncode != 0:
            raise CommandError(args, process.returncode, process.stderr)
        return process.stdout
