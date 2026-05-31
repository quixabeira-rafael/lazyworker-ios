from __future__ import annotations

import json
from typing import Any

from lazyworker.devices.errors import ProviderUnavailable
from lazyworker.devices.models import ConnectionType, Device, DeviceKind, DeviceState
from lazyworker.devices.runner import CommandError, CommandRunner


def _map_transport(transport: str | None) -> ConnectionType:
    if not transport:
        return ConnectionType.UNKNOWN
    value = transport.lower()
    if "wired" in value or "usb" in value:
        return ConnectionType.USB
    if "network" in value or "local" in value or "wifi" in value:
        return ConnectionType.NETWORK
    return ConnectionType.UNKNOWN


def _map_developer_mode(status: str | None) -> bool | None:
    if status is None:
        return None
    return status.lower() == "enabled"


def _extract_json(output: str) -> dict[str, Any]:
    start = output.find("{")
    if start == -1:
        raise ValueError("no JSON object found in devicectl output")
    parsed: dict[str, Any] = json.loads(output[start:])
    return parsed


def _parse_devices(payload: dict[str, Any]) -> list[Device]:
    devices: list[Device] = []
    for entry in payload.get("result", {}).get("devices", []):
        hardware = entry.get("hardwareProperties", {})
        properties = entry.get("deviceProperties", {})
        connection = entry.get("connectionProperties", {})
        paired = connection.get("pairingState") == "paired"
        udid = hardware.get("udid")
        if not udid:
            continue
        devices.append(
            Device(
                udid=udid,
                name=properties.get("name") or hardware.get("marketingName") or "",
                kind=DeviceKind.PHYSICAL,
                state=DeviceState.CONNECTED if paired else DeviceState.UNAVAILABLE,
                connection=_map_transport(connection.get("transportType")),
                platform=hardware.get("platform", "iOS"),
                os_version=properties.get("osVersionNumber"),
                model=hardware.get("marketingName"),
                available=paired,
                developer_mode_enabled=_map_developer_mode(
                    properties.get("developerModeStatus")
                ),
            )
        )
    return devices


class PhysicalDeviceProvider:
    """Discovers physical devices (USB and network) via ``xcrun devicectl``."""

    name = "physical"

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def list_devices(self) -> list[Device]:
        try:
            output = self._runner.run(
                ["xcrun", "devicectl", "list", "devices", "--json-output", "-"]
            )
        except FileNotFoundError as exc:
            raise ProviderUnavailable(self.name, "xcrun not found") from exc
        except CommandError as exc:
            raise ProviderUnavailable(self.name, str(exc)) from exc
        return _parse_devices(_extract_json(output))
