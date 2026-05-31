from __future__ import annotations

import json
from typing import Any

from lazyworker.devices.errors import ProviderUnavailable
from lazyworker.devices.models import ConnectionType, Device, DeviceKind, DeviceState
from lazyworker.devices.runner import CommandError, CommandRunner

_RUNTIME_MARKER = ".SimRuntime."
_DEVICE_TYPE_MARKER = ".SimDeviceType."

_STATE_MAP = {
    "booted": DeviceState.BOOTED,
    "shutdown": DeviceState.SHUTDOWN,
}


def _parse_runtime(runtime: str) -> tuple[str, str | None]:
    tail = runtime.split(_RUNTIME_MARKER)[-1]
    parts = tail.split("-")
    if not parts:
        return "iOS", None
    platform = parts[0]
    version = ".".join(parts[1:]) if len(parts) > 1 else None
    return platform, version


def _parse_model(device_type: str | None) -> str | None:
    if not device_type:
        return None
    tail = device_type.split(_DEVICE_TYPE_MARKER)[-1]
    return tail.replace("-", " ")


def _parse_devices(payload: dict[str, Any]) -> list[Device]:
    devices: list[Device] = []
    for runtime, entries in payload.get("devices", {}).items():
        platform, version = _parse_runtime(runtime)
        for entry in entries:
            state = _STATE_MAP.get(str(entry.get("state", "")).lower(), DeviceState.UNKNOWN)
            devices.append(
                Device(
                    udid=entry["udid"],
                    name=entry.get("name", ""),
                    kind=DeviceKind.SIMULATOR,
                    state=state,
                    connection=ConnectionType.SIMULATOR,
                    platform=platform,
                    os_version=version,
                    model=_parse_model(entry.get("deviceTypeIdentifier")),
                    available=bool(entry.get("isAvailable", False)),
                )
            )
    return devices


class SimulatorProvider:
    """Discovers iOS simulators via ``xcrun simctl``."""

    name = "simulator"

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def list_devices(self) -> list[Device]:
        try:
            output = self._runner.run(["xcrun", "simctl", "list", "devices", "--json"])
        except FileNotFoundError as exc:
            raise ProviderUnavailable(self.name, "xcrun not found") from exc
        except CommandError as exc:
            raise ProviderUnavailable(self.name, str(exc)) from exc
        return _parse_devices(json.loads(output))
