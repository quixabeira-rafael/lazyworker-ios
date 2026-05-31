from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path
from typing import IO, Protocol, runtime_checkable

_TERM_GRACE_SECONDS = 5.0
_TERM_POLL_SECONDS = 0.1


@runtime_checkable
class ManagedProcess(Protocol):
    """A spawned long-running process."""

    @property
    def pid(self) -> int: ...

    def is_running(self) -> bool: ...

    def terminate(self) -> None: ...


@runtime_checkable
class ProcessManager(Protocol):
    """Spawns and terminates long-running processes."""

    def spawn(self, args: Sequence[str], *, log_path: Path | None = None) -> ManagedProcess: ...

    def terminate(self, pid: int) -> None: ...


class _SubprocessHandle:
    def __init__(self, process: subprocess.Popen[bytes], log_file: IO[bytes] | None) -> None:
        self._process = process
        self._log_file = log_file

    @property
    def pid(self) -> int:
        return self._process.pid

    def is_running(self) -> bool:
        return self._process.poll() is None

    def terminate(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
        if self._log_file is not None:
            self._log_file.close()


class SubprocessProcessManager:
    """Default process manager backed by detached :class:`subprocess.Popen`."""

    def spawn(self, args: Sequence[str], *, log_path: Path | None = None) -> ManagedProcess:
        stdout: int | IO[bytes]
        log_file: IO[bytes] | None
        if log_path is not None:
            log_file = log_path.open("wb")
            stdout = log_file
        else:
            log_file = None
            stdout = subprocess.DEVNULL
        process = subprocess.Popen(
            list(args),
            stdout=stdout,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        return _SubprocessHandle(process, log_file)

    def terminate(self, pid: int) -> None:
        """Terminate the process group, escalating to SIGKILL if it lingers.

        ``PermissionError`` (the group is gone/reaped or no longer ours) is treated
        as "stop" so we never escalate against a reused PID we do not own.
        """
        try:
            pgid = os.getpgid(pid)
        except (ProcessLookupError, PermissionError):
            return
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGTERM)
        deadline = time.monotonic() + _TERM_GRACE_SECONDS
        while time.monotonic() < deadline:
            try:
                os.killpg(pgid, 0)
            except (ProcessLookupError, PermissionError):
                return
            time.sleep(_TERM_POLL_SECONDS)
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGKILL)
