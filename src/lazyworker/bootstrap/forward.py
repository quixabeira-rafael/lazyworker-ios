from __future__ import annotations

from pathlib import Path

from lazyworker.bootstrap.process import ManagedProcess, ProcessManager


class PortForwarder:
    """Forwards a local port to a device port over usbmux via ``iproxy``."""

    def __init__(self, process_manager: ProcessManager) -> None:
        self._process_manager = process_manager

    def start(
        self,
        udid: str,
        *,
        local_port: int,
        device_port: int,
        log_path: Path | None = None,
    ) -> ManagedProcess:
        return self._process_manager.spawn(
            ["iproxy", f"{local_port}:{device_port}", "-u", udid],
            log_path=log_path,
        )
