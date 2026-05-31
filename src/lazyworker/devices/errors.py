from __future__ import annotations


class DeviceError(Exception):
    """Base error for the device discovery layer."""


class ProviderUnavailable(DeviceError):
    """Raised when a device provider cannot run (missing tool, command failure)."""

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(f"{provider} provider unavailable: {reason}")
        self.provider = provider
        self.reason = reason
