from __future__ import annotations

from lazyworker.devices.runner import CommandError, CommandRunner


class SimulatorController:
    """Boots and shuts down iOS simulators via ``xcrun simctl``."""

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def boot(self, udid: str) -> None:
        try:
            self._runner.run(["xcrun", "simctl", "boot", udid])
        except CommandError as exc:
            if "Booted" not in exc.stderr:
                raise

    def shutdown(self, udid: str) -> None:
        try:
            self._runner.run(["xcrun", "simctl", "shutdown", udid])
        except CommandError as exc:
            if "Shutdown" not in exc.stderr:
                raise
