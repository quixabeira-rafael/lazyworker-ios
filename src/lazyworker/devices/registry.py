from __future__ import annotations

from collections.abc import Sequence

from lazyworker.devices.base import DeviceProvider
from lazyworker.devices.errors import ProviderUnavailable
from lazyworker.devices.models import ConnectionType, Device, DeviceKind, DeviceState
from lazyworker.devices.physical import PhysicalDeviceProvider
from lazyworker.devices.runner import CommandRunner, SubprocessRunner
from lazyworker.devices.simulator import SimulatorProvider


class DeviceRegistry:
    """Aggregates devices from every configured provider."""

    def __init__(self, providers: Sequence[DeviceProvider]) -> None:
        self._providers = list(providers)
        self.last_unavailable: list[ProviderUnavailable] = []

    @classmethod
    def default(cls, runner: CommandRunner | None = None) -> DeviceRegistry:
        runner = runner or SubprocessRunner()
        return cls([SimulatorProvider(runner), PhysicalDeviceProvider(runner)])

    def list(
        self,
        *,
        kind: DeviceKind | None = None,
        connection: ConnectionType | None = None,
        state: DeviceState | None = None,
        booted: bool | None = None,
        available_only: bool = False,
    ) -> list[Device]:
        devices: list[Device] = []
        self.last_unavailable = []
        for provider in self._providers:
            try:
                devices.extend(provider.list_devices())
            except ProviderUnavailable as exc:
                self.last_unavailable.append(exc)

        if kind is not None:
            devices = [d for d in devices if d.kind == kind]
        if connection is not None:
            devices = [d for d in devices if d.connection == connection]
        if state is not None:
            devices = [d for d in devices if d.state == state]
        if booted is not None:
            devices = [d for d in devices if d.is_booted == booted]
        if available_only:
            devices = [d for d in devices if d.available]
        return devices

    def find(self, udid: str) -> Device | None:
        for device in self.list():
            if device.udid == udid:
                return device
        return None
