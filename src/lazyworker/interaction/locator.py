from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, model_validator

from lazyworker.interaction.models import ErrorCode
from lazyworker.wda.models import AccessibilityNode

_SELECTOR_FIELDS = ("type", "label", "name", "value", "identifier")


class Locator(BaseModel):
    """Selector criteria for one element; every set field must match (AND)."""

    model_config = ConfigDict(extra="forbid")

    type: str | None = None
    label: str | None = None
    name: str | None = None
    value: str | None = None
    identifier: str | None = None
    visible: bool | None = True
    index: int | None = None

    @model_validator(mode="after")
    def _require_a_criterion(self) -> Locator:
        if not any(getattr(self, field) is not None for field in _SELECTOR_FIELDS):
            raise ValueError("a locator must set at least one of: " + ", ".join(_SELECTOR_FIELDS))
        return self


@dataclass(frozen=True)
class Resolution:
    node: AccessibilityNode | None
    error_code: ErrorCode
    candidate_count: int
    candidates: list[AccessibilityNode]


class LocatorResolver:
    """Resolves a locator against an already-fetched tree. No I/O."""

    def resolve(self, tree: AccessibilityNode, locator: Locator) -> Resolution:
        matches = tree.find_all(
            type=locator.type,
            label=locator.label,
            name=locator.name,
            value=locator.value,
            identifier=locator.identifier,
            visible=locator.visible,
        )
        if not matches:
            return Resolution(None, ErrorCode.NOT_FOUND, 0, [])

        if locator.index is not None:
            if 0 <= locator.index < len(matches):
                return Resolution(matches[locator.index], ErrorCode.OK, len(matches), matches)
            return Resolution(None, ErrorCode.NOT_FOUND, len(matches), matches)

        if len(matches) == 1:
            return Resolution(matches[0], ErrorCode.OK, 1, matches)
        return Resolution(None, ErrorCode.AMBIGUOUS, len(matches), matches)
