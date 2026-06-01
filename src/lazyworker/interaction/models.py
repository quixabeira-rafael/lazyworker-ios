from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from lazyworker.wda.models import AccessibilityNode, Rect


class ErrorCode(StrEnum):
    OK = "ok"
    NO_SESSION = "no_session"
    SESSION_INVALID = "session_invalid"
    WDA_UNREACHABLE = "wda_unreachable"
    WDA_ERROR = "wda_error"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    NO_RECT = "no_rect"
    NOT_VISIBLE = "not_visible"
    OUT_OF_BOUNDS = "out_of_bounds"
    TIMEOUT = "timeout"
    NO_CHANGE = "no_change"
    INVALID_TARGET = "invalid_target"
    OCR_UNAVAILABLE = "ocr_unavailable"
    DETECTOR_UNAVAILABLE = "detector_unavailable"
    INTERNAL = "internal"


class Action(StrEnum):
    OPEN = "open"
    CLOSE = "close"
    TREE = "tree"
    SCREEN = "screen"
    TAP = "tap"
    DOUBLE_TAP = "double_tap"
    LONG_PRESS = "long_press"
    SCROLL = "scroll"
    SCROLL_TO = "scroll_to"
    TYPE = "type"
    SCREENSHOT = "screenshot"
    DEEPLINK = "deeplink"
    FIND = "find"


class ScrollDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


class WaitMode(StrEnum):
    TREE = "tree"
    SCREEN = "screen"
    UNTIL = "until"
    GONE = "gone"


class WaitOutcome(BaseModel):
    """Result of an explicit smart wait after an action."""

    mode: WaitMode
    ok: bool
    satisfied: bool
    settled: bool
    attempts: int
    elapsed_s: float


EXIT_CODES: dict[ErrorCode, int] = {
    ErrorCode.NO_SESSION: 10,
    ErrorCode.WDA_UNREACHABLE: 11,
    ErrorCode.SESSION_INVALID: 12,
    ErrorCode.WDA_ERROR: 13,
    ErrorCode.NOT_FOUND: 20,
    ErrorCode.AMBIGUOUS: 21,
    ErrorCode.NOT_VISIBLE: 22,
    ErrorCode.OUT_OF_BOUNDS: 23,
    ErrorCode.TIMEOUT: 24,
    ErrorCode.NO_CHANGE: 25,
    ErrorCode.INVALID_TARGET: 30,
    ErrorCode.OCR_UNAVAILABLE: 31,
    ErrorCode.DETECTOR_UNAVAILABLE: 32,
    ErrorCode.INTERNAL: 1,
}


def exit_code_for(error_code: ErrorCode) -> int:
    return EXIT_CODES.get(error_code, 1)


class MatchedElement(BaseModel):
    """Compact projection of a resolved accessibility node for result payloads."""

    model_config = ConfigDict(extra="ignore")

    type: str
    label: str | None = None
    name: str | None = None
    value: str | None = None
    identifier: str | None = None
    rect: Rect | None = None
    visible: bool | None = None

    @classmethod
    def from_node(cls, node: AccessibilityNode) -> MatchedElement:
        return cls(
            type=node.type,
            label=node.label,
            name=node.name,
            value=node.value,
            identifier=node.identifier,
            rect=node.rect,
            visible=node.visible,
        )


class Tip(BaseModel):
    """A ready-to-copy example command for acting on a found element."""

    action: str
    command: str


class FoundElement(MatchedElement):
    """A search match, plus tips on how to act on it (search-only — keeps MatchedElement clean)."""

    tips: list[Tip] = []


class SearchResult(BaseModel):
    """Read-only result of a tree search: every element matching the query/filters."""

    count: int
    matches: list[FoundElement]


class OperationResult(BaseModel):
    """Typed outcome returned by every interaction action."""

    operation: Action
    ok: bool
    error_code: ErrorCode = ErrorCode.OK
    message: str | None = None
    element: MatchedElement | None = None
    point: tuple[int, int] | None = None
    candidate_count: int | None = None
    candidates: list[MatchedElement] | None = None
    attempts: int | None = None
    dry_run: bool = False
    wait: WaitOutcome | None = None
    screenshot: str | None = None

    @classmethod
    def success(
        cls,
        operation: Action,
        *,
        element: MatchedElement | None = None,
        point: tuple[int, int] | None = None,
        attempts: int | None = None,
        dry_run: bool = False,
    ) -> OperationResult:
        return cls(
            operation=operation,
            ok=True,
            element=element,
            point=point,
            attempts=attempts,
            dry_run=dry_run,
        )

    @classmethod
    def failure(
        cls,
        operation: Action,
        error_code: ErrorCode,
        message: str,
        *,
        candidate_count: int | None = None,
        candidates: list[MatchedElement] | None = None,
        element: MatchedElement | None = None,
    ) -> OperationResult:
        return cls(
            operation=operation,
            ok=False,
            error_code=error_code,
            message=message,
            candidate_count=candidate_count,
            candidates=candidates,
            element=element,
        )
