from typing import Any

import pytest
from pydantic import ValidationError

from lazyworker.interaction.batch import Batch, BatchRunner, run_operation
from lazyworker.interaction.locator import Locator
from lazyworker.interaction.models import Action, ErrorCode, OperationResult, ScrollDirection


class FakeInteractor:
    def __init__(self, results: list[OperationResult]) -> None:
        self._results = list(results)
        self.calls: list[Action] = []

    def _next(self, action: Action) -> OperationResult:
        self.calls.append(action)
        return self._results.pop(0)

    def tap(self, locator: Any = None, *, at: Any = None, dry_run: bool = False) -> OperationResult:
        return self._next(Action.TAP)

    def double_tap(
        self, locator: Any = None, *, at: Any = None, dry_run: bool = False
    ) -> OperationResult:
        return self._next(Action.DOUBLE_TAP)

    def long_press(
        self, locator: Any = None, *, at: Any = None, duration: float = 0.8, dry_run: bool = False
    ) -> OperationResult:
        return self._next(Action.LONG_PRESS)

    def type_text(
        self, text: str, *, locator: Any = None, at: Any = None, dry_run: bool = False
    ) -> OperationResult:
        return self._next(Action.TYPE)

    def scroll(
        self, direction: ScrollDirection, *, amount: float = 0.6, dry_run: bool = False
    ) -> OperationResult:
        return self._next(Action.SCROLL)

    def scroll_to(
        self,
        locator: Locator,
        *,
        direction: ScrollDirection = ScrollDirection.DOWN,
        max_swipes: int = 8,
        dry_run: bool = False,
    ) -> OperationResult:
        return self._next(Action.SCROLL_TO)

    def screenshot(self) -> bytes:
        return b""


def _ok() -> OperationResult:
    return OperationResult.success(Action.TAP)


def _fail() -> OperationResult:
    return OperationResult.failure(Action.TAP, ErrorCode.NOT_FOUND, "x")


def test_batch_all_success() -> None:
    batch = Batch.model_validate(
        {"operations": [{"op": "tap", "label": "A"}, {"op": "scroll", "direction": "down"}]}
    )
    report = BatchRunner(FakeInteractor([_ok(), _ok()])).run(batch)  # type: ignore[arg-type]
    assert report.ok
    assert report.ran == 2
    assert report.count == 2


def test_batch_stop_on_error_truncates() -> None:
    batch = Batch.model_validate(
        {
            "operations": [
                {"op": "tap", "label": "A"},
                {"op": "tap", "label": "B"},
                {"op": "tap", "label": "C"},
            ]
        }
    )
    report = BatchRunner(FakeInteractor([_ok(), _fail(), _ok()])).run(batch)  # type: ignore[arg-type]
    assert not report.ok
    assert report.ran == 2
    assert report.stopped_on == 1


def test_batch_continue_on_error() -> None:
    batch = Batch.model_validate(
        {
            "stop_on_error": False,
            "operations": [{"op": "tap", "label": "A"}, {"op": "tap", "label": "B"}],
        }
    )
    report = BatchRunner(FakeInteractor([_fail(), _ok()])).run(batch)  # type: ignore[arg-type]
    assert report.ran == 2
    assert not report.ok


def test_invalid_op_missing_text_rejected() -> None:
    with pytest.raises(ValidationError):
        Batch.model_validate({"operations": [{"op": "type"}]})


def test_unknown_op_rejected() -> None:
    with pytest.raises(ValidationError):
        Batch.model_validate({"operations": [{"op": "frobnicate"}]})


def test_scroll_to_without_selector_is_invalid() -> None:
    op = Batch.model_validate({"operations": [{"op": "scroll_to", "at": [1, 2]}]}).operations[0]
    result = run_operation(FakeInteractor([]), op)  # type: ignore[arg-type]
    assert result.error_code == ErrorCode.INVALID_TARGET
