from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from lazyworker.interaction.interactor import Interactor
from lazyworker.interaction.locator import Locator
from lazyworker.interaction.models import Action, ErrorCode, OperationResult, ScrollDirection
from lazyworker.wda.errors import WdaConnectionError, WdaResponseError

_SELECTOR_FIELDS = ("type", "label", "name", "value", "identifier")


class _BaseOp(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _TargetOp(_BaseOp):
    type: str | None = None
    label: str | None = None
    name: str | None = None
    value: str | None = None
    identifier: str | None = None
    index: int | None = None
    visible: bool | None = True
    at: tuple[int, int] | None = None

    def to_locator(self) -> Locator | None:
        if all(getattr(self, field) is None for field in _SELECTOR_FIELDS):
            return None
        return Locator(
            type=self.type,
            label=self.label,
            name=self.name,
            value=self.value,
            identifier=self.identifier,
            visible=self.visible,
            index=self.index,
        )


class TapOp(_TargetOp):
    op: Literal["tap"]


class DoubleTapOp(_TargetOp):
    op: Literal["double_tap"]


class LongPressOp(_TargetOp):
    op: Literal["long_press"]
    duration: float = 0.8


class TypeOp(_TargetOp):
    op: Literal["type"]
    text: str


class ScrollOp(_BaseOp):
    op: Literal["scroll"]
    direction: ScrollDirection
    distance: float = 0.6


class ScrollToOp(_TargetOp):
    op: Literal["scroll_to"]
    direction: ScrollDirection = ScrollDirection.DOWN
    max_swipes: int = 8


class ScreenshotOp(_BaseOp):
    op: Literal["screenshot"]


Operation = Annotated[
    TapOp | DoubleTapOp | LongPressOp | TypeOp | ScrollOp | ScrollToOp | ScreenshotOp,
    Field(discriminator="op"),
]


class Batch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop_on_error: bool = True
    operations: list[Operation]


class BatchReport(BaseModel):
    count: int
    ran: int
    stopped_on: int | None = None
    results: list[OperationResult]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ok(self) -> bool:
        return self.ran == self.count and all(result.ok for result in self.results)


def run_operation(interactor: Interactor, op: Operation) -> OperationResult:
    if isinstance(op, ScrollOp):
        return interactor.scroll(op.direction, amount=op.distance)
    if isinstance(op, ScreenshotOp):
        try:
            interactor.screenshot()
        except WdaConnectionError as exc:
            return OperationResult.failure(Action.SCREENSHOT, ErrorCode.WDA_UNREACHABLE, str(exc))
        except WdaResponseError as exc:
            return OperationResult.failure(Action.SCREENSHOT, ErrorCode.WDA_ERROR, str(exc))
        return OperationResult.success(Action.SCREENSHOT)

    locator = op.to_locator()
    point = op.at
    if isinstance(op, TapOp):
        return interactor.tap(locator, at=point)
    if isinstance(op, DoubleTapOp):
        return interactor.double_tap(locator, at=point)
    if isinstance(op, LongPressOp):
        return interactor.long_press(locator, at=point, duration=op.duration)
    if isinstance(op, TypeOp):
        return interactor.type_text(op.text, locator=locator, at=point)
    if locator is None:
        return OperationResult.failure(
            Action.SCROLL_TO, ErrorCode.INVALID_TARGET, "scroll_to requires a selector"
        )
    return interactor.scroll_to(locator, direction=op.direction, max_swipes=op.max_swipes)


class BatchRunner:
    def __init__(self, interactor: Interactor) -> None:
        self._interactor = interactor

    def run(self, batch: Batch) -> BatchReport:
        results: list[OperationResult] = []
        stopped_on: int | None = None
        for index, op in enumerate(batch.operations):
            result = run_operation(self._interactor, op)
            results.append(result)
            if not result.ok and batch.stop_on_error:
                stopped_on = index
                break
        return BatchReport(
            count=len(batch.operations),
            ran=len(results),
            stopped_on=stopped_on,
            results=results,
        )
