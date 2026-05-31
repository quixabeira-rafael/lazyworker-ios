from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_SNAPSHOT_MAX_DEPTH = 50
DEFAULT_CUSTOM_SNAPSHOT_TIMEOUT = 30.0
DEFAULT_SCROLL_DISTANCE = 0.6
DEFAULT_SCROLL_TO_MAX_SWIPES = 8


class SnapshotSettings(BaseModel):
    """Maps to ``POST /session/{id}/appium/settings``.

    Field names match WDA's camelCase keys so ``model_dump`` is the wire payload.
    """

    model_config = ConfigDict(extra="forbid")

    snapshotMaxDepth: int = DEFAULT_SNAPSHOT_MAX_DEPTH
    customSnapshotTimeout: float = DEFAULT_CUSTOM_SNAPSHOT_TIMEOUT
    waitForIdleTimeout: float = 0.0
    animationCoolOffTimeout: float = 0.0

    def as_payload(self) -> dict[str, Any]:
        return self.model_dump()


class SessionOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wait_for_quiescence: bool = False
    settings: SnapshotSettings = Field(default_factory=SnapshotSettings)
