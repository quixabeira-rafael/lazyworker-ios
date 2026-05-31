from collections.abc import Sequence

import pytest

from lazyworker.devices.errors import ProviderUnavailable
from lazyworker.devices.models import ConnectionType, DeviceKind, DeviceState
from lazyworker.devices.physical import PhysicalDeviceProvider
from lazyworker.devices.registry import DeviceRegistry
from lazyworker.devices.runner import CommandError
from lazyworker.devices.simulator import SimulatorProvider

SIMCTL_JSON = """
{
  "devices": {
    "com.apple.CoreSimulator.SimRuntime.iOS-26-4": [
      {
        "udid": "U1",
        "isAvailable": true,
        "deviceTypeIdentifier": "com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro",
        "state": "Booted",
        "name": "iPhone 17 Pro"
      },
      {
        "udid": "U2",
        "isAvailable": true,
        "deviceTypeIdentifier": "com.apple.CoreSimulator.SimDeviceType.iPhone-17",
        "state": "Shutdown",
        "name": "iPhone 17"
      }
    ],
    "com.apple.CoreSimulator.SimRuntime.iOS-17-0": [
      {
        "udid": "U3",
        "isAvailable": false,
        "deviceTypeIdentifier": "com.apple.CoreSimulator.SimDeviceType.iPhone-15",
        "state": "Shutdown",
        "name": "iPhone 15"
      }
    ]
  }
}
"""

DEVICECTL_OUTPUT = """Name               Hostname            Identifier   State                Model
----------------   -----------------   ----------   ------------------   -----
iPhone de Rafael   host.local          ABC          available (paired)   iPhone 13 Pro Max
{
  "info": {"outcome": "success"},
  "result": {
    "devices": [
      {
        "hardwareProperties": {
          "udid": "00008110-001928D41A44401E",
          "platform": "iOS",
          "marketingName": "iPhone 13 Pro Max"
        },
        "deviceProperties": {
          "name": "iPhone de Rafael",
          "osVersionNumber": "26.5",
          "developerModeStatus": "enabled"
        },
        "connectionProperties": {
          "transportType": "localNetwork",
          "pairingState": "paired"
        }
      }
    ]
  }
}
"""


class FakeRunner:
    def __init__(self, outputs: dict[str, str]) -> None:
        self._outputs = outputs

    def run(self, args: Sequence[str]) -> str:
        for key, value in self._outputs.items():
            if key in args:
                return value
        raise AssertionError(f"unexpected command: {list(args)}")


class FailingRunner:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def run(self, args: Sequence[str]) -> str:
        raise self._exc


def test_simulator_provider_parses_state_and_version() -> None:
    provider = SimulatorProvider(FakeRunner({"simctl": SIMCTL_JSON}))
    devices = provider.list_devices()

    by_udid = {d.udid: d for d in devices}
    assert by_udid["U1"].state == DeviceState.BOOTED
    assert by_udid["U1"].is_booted is True
    assert by_udid["U1"].os_version == "26.4"
    assert by_udid["U1"].model == "iPhone 17 Pro"
    assert by_udid["U1"].connection == ConnectionType.SIMULATOR
    assert by_udid["U2"].state == DeviceState.SHUTDOWN
    assert by_udid["U3"].available is False


def test_physical_provider_strips_table_and_parses() -> None:
    provider = PhysicalDeviceProvider(FakeRunner({"devicectl": DEVICECTL_OUTPUT}))
    devices = provider.list_devices()

    assert len(devices) == 1
    device = devices[0]
    assert device.udid == "00008110-001928D41A44401E"
    assert device.kind == DeviceKind.PHYSICAL
    assert device.connection == ConnectionType.NETWORK
    assert device.state == DeviceState.CONNECTED
    assert device.os_version == "26.5"
    assert device.developer_mode_enabled is True


def test_provider_unavailable_when_tool_missing() -> None:
    provider = SimulatorProvider(FailingRunner(FileNotFoundError("xcrun")))
    with pytest.raises(ProviderUnavailable):
        provider.list_devices()


def test_provider_unavailable_on_command_error() -> None:
    provider = PhysicalDeviceProvider(
        FailingRunner(CommandError(["xcrun"], 1, "boom"))
    )
    with pytest.raises(ProviderUnavailable):
        provider.list_devices()


def test_registry_aggregates_and_filters() -> None:
    runner = FakeRunner({"simctl": SIMCTL_JSON, "devicectl": DEVICECTL_OUTPUT})
    registry = DeviceRegistry([SimulatorProvider(runner), PhysicalDeviceProvider(runner)])

    assert len(registry.list()) == 4
    assert len(registry.list(kind=DeviceKind.PHYSICAL)) == 1
    assert len(registry.list(kind=DeviceKind.SIMULATOR)) == 3
    assert len(registry.list(booted=True)) == 1
    assert len(registry.list(connection=ConnectionType.NETWORK)) == 1
    assert registry.find("00008110-001928D41A44401E") is not None
    assert registry.find("missing") is None


def test_registry_records_unavailable_providers() -> None:
    good = SimulatorProvider(FakeRunner({"simctl": SIMCTL_JSON}))
    bad = PhysicalDeviceProvider(FailingRunner(FileNotFoundError("xcrun")))
    registry = DeviceRegistry([good, bad])

    devices = registry.list()
    assert len(devices) == 3
    assert len(registry.last_unavailable) == 1
    assert registry.last_unavailable[0].provider == "physical"
