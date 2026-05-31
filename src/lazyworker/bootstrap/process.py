from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import IO, Protocol, runtime_checkable


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
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGTERM)
