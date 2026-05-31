from __future__ import annotations

import tomllib
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

CONFIG_FILENAME = "lazyworker.toml"


class SigningMode(StrEnum):
    """How WebDriverAgent is signed for a target.

    - ``simulator``: no signing required.
    - ``free``: free Apple ID, provisioning expires every 7 days (needs periodic resign).
    - ``paid``: paid Apple Developer account, ~1 year validity. Code-ready, untested.
    """

    SIMULATOR = "simulator"
    FREE = "free"
    PAID = "paid"


class SigningConfig(BaseModel):
    mode: SigningMode = SigningMode.SIMULATOR
    team_id: str | None = None
    bundle_id_prefix: str = "com.lazyworker.wda"

    @property
    def runner_bundle_id(self) -> str:
        return f"{self.bundle_id_prefix}.WebDriverAgentRunner"


class WdaConfig(BaseModel):
    base_url: str = "http://127.0.0.1:8100"
    port: int = 8100
    version: str | None = None


class TargetConfig(BaseModel):
    """The device/simulator this project drives, so the UDID needn't be repeated."""

    udid: str | None = None
    bundle_id: str | None = None


class Config(BaseModel):
    signing: SigningConfig = Field(default_factory=SigningConfig)
    wda: WdaConfig = Field(default_factory=WdaConfig)
    target: TargetConfig = Field(default_factory=TargetConfig)

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        """Load configuration from ``path`` or the nearest discovered file.

        Falls back to defaults when no file is found.
        """
        resolved = Path(path) if path is not None else cls.discover()
        if resolved is not None and resolved.exists():
            with resolved.open("rb") as handle:
                data = tomllib.load(handle)
            return cls.model_validate(data)
        return cls()

    @staticmethod
    def discover(start: str | Path | None = None) -> Path | None:
        """Search the current directory and its parents for the config file."""
        origin = Path(start) if start is not None else Path.cwd()
        for directory in (origin, *origin.parents):
            candidate = directory / CONFIG_FILENAME
            if candidate.exists():
                return candidate
        return None
