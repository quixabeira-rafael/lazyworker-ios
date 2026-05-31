from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _coerce_bool(value: Any) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return None


class Rect(BaseModel):
    """Element frame in screen points."""

    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


class Status(BaseModel):
    """Result of WDA ``GET /status``."""

    model_config = ConfigDict(extra="ignore")

    ready: bool = False
    message: str | None = None
    state: str | None = None
    os_name: str | None = None
    os_version: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _flatten_os(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("os"), dict):
            os_info = data["os"]
            data = {**data, "os_name": os_info.get("name"), "os_version": os_info.get("version")}
        return data


class AccessibilityNode(BaseModel):
    """A single node of the WDA accessibility tree (``GET /source?format=json``)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    type: str
    name: str | None = None
    label: str | None = None
    value: str | None = None
    identifier: str | None = Field(default=None, alias="rawIdentifier")
    rect: Rect | None = None
    enabled: bool | None = Field(default=None, alias="isEnabled")
    visible: bool | None = Field(default=None, alias="isVisible")
    children: list[AccessibilityNode] = Field(default_factory=list)

    @field_validator("enabled", "visible", mode="before")
    @classmethod
    def _validate_bool(cls, value: Any) -> bool | None:
        return _coerce_bool(value)

    def walk(self) -> Iterator[AccessibilityNode]:
        """Yield this node and every descendant, depth-first."""
        yield self
        for child in self.children:
            yield from child.walk()

    def find_all(
        self,
        *,
        type: str | None = None,
        label: str | None = None,
        name: str | None = None,
        value: str | None = None,
        identifier: str | None = None,
        visible: bool | None = None,
    ) -> list[AccessibilityNode]:
        """Return every node matching all provided attributes."""

        def matches(node: AccessibilityNode) -> bool:
            return (
                (type is None or node.type == type)
                and (label is None or node.label == label)
                and (name is None or node.name == name)
                and (value is None or node.value == value)
                and (identifier is None or node.identifier == identifier)
                and (visible is None or node.visible == visible)
            )

        return [node for node in self.walk() if matches(node)]

    def find(
        self,
        *,
        type: str | None = None,
        label: str | None = None,
        name: str | None = None,
        value: str | None = None,
        identifier: str | None = None,
        visible: bool | None = None,
    ) -> AccessibilityNode | None:
        """Return the first node matching all provided attributes, or ``None``."""
        matches = self.find_all(
            type=type,
            label=label,
            name=name,
            value=value,
            identifier=identifier,
            visible=visible,
        )
        return matches[0] if matches else None


AccessibilityNode.model_rebuild()
