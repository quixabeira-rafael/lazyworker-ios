from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class DeviceKind(StrEnum):
    SIMULATOR = "simulator"
    PHYSICAL = "physical"


class ConnectionType(StrEnum):
    SIMULATOR = "simulator"
    USB = "usb"
    NETWORK = "network"
    UNKNOWN = "unknown"


class DeviceState(StrEnum):
    BOOTED = "booted"
    SHUTDOWN = "shutdown"
    CONNECTED = "connected"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class Device(BaseModel):
    """A simulator or physical device discovered on the host."""

    udid: str
    name: str
    kind: DeviceKind
    state: DeviceState
    connection: ConnectionType
    platform: str = "iOS"
    os_version: str | None = None
    model: str | None = None
    available: bool = True
    developer_mode_enabled: bool | None = None

    @property
    def is_booted(self) -> bool:
        return self.state == DeviceState.BOOTED

    @property
    def is_simulator(self) -> bool:
        return self.kind == DeviceKind.SIMULATOR

    @property
    def is_physical(self) -> bool:
        return self.kind == DeviceKind.PHYSICAL
