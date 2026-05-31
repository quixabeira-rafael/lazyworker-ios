from __future__ import annotations

from typing import Protocol, runtime_checkable

from lazyworker.devices.models import Device


@runtime_checkable
class DeviceProvider(Protocol):
    """A source of devices (e.g. simulators, USB/network physical devices)."""

    name: str

    def list_devices(self) -> list[Device]: ...
