from typing import Any

from lazyworker.interaction.interactor import Interactor
from lazyworker.interaction.locator import Locator
from lazyworker.interaction.models import ErrorCode, WaitMode
from lazyworker.interaction.wait import WaitSpec, tree_signature, wait_for
from lazyworker.wda.models import AccessibilityNode


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


# --- wait_for engine ---


def test_wait_for_changes_then_settles() -> None:
    clock = FakeClock()
    observations = iter(["A", "B", "B"])
    ok, satisfied, settled, attempts, _ = wait_for(
        lambda: next(observations),
        lambda s: s != "A",
        timeout=10,
        interval=1,
        settle=2,
        sleep=clock.advance,
        clock=clock,
    )
    assert ok and satisfied and settled
    assert attempts == 3


def test_wait_for_times_out_without_change() -> None:
    clock = FakeClock()
    ok, satisfied, _, _, _ = wait_for(
        lambda: "A",
        lambda s: s != "A",
        timeout=3,
        interval=1,
        settle=2,
        sleep=clock.advance,
        clock=clock,
    )
    assert not ok and not satisfied


def test_wait_for_satisfied_but_never_settles() -> None:
    clock = FakeClock()
    observations = iter(["B", "C", "D", "E", "F"])
    ok, satisfied, settled, _, _ = wait_for(
        lambda: next(observations),
        lambda s: s != "A",
        timeout=3,
        interval=1,
        settle=2,
        sleep=clock.advance,
        clock=clock,
    )
    assert not ok
    assert satisfied and not settled


# --- tree_signature ---


def _tree(children: list[dict[str, Any]]) -> AccessibilityNode:
    return AccessibilityNode.model_validate(
        {
            "type": "Application",
            "rect": {"x": 0, "y": 0, "width": 400, "height": 800},
            "isVisible": True,
            "children": children,
        }
    )


_LOGIN = {
    "type": "Button",
    "label": "Login",
    "rect": {"x": 100, "y": 200, "width": 100, "height": 40},
    "isVisible": True,
    "children": [],
}
_WELCOME = {
    "type": "StaticText",
    "label": "Welcome",
    "rect": {"x": 100, "y": 200, "width": 100, "height": 40},
    "isVisible": True,
    "children": [],
}


def test_tree_signature_stable_for_same_content() -> None:
    assert tree_signature(_tree([_LOGIN])) == tree_signature(_tree([_LOGIN]))


def test_tree_signature_changes_with_content() -> None:
    assert tree_signature(_tree([_LOGIN])) != tree_signature(_tree([_WELCOME]))


def test_tree_signature_ignores_hidden() -> None:
    hidden = {"type": "StaticText", "label": "secret", "isVisible": False, "children": []}
    assert tree_signature(_tree([_LOGIN, hidden])) == tree_signature(_tree([_LOGIN]))


# --- Interactor integration ---


class FakeSession:
    def __init__(self, trees: list[AccessibilityNode]) -> None:
        self._trees = list(trees)
        self.gestures: list[tuple[int, int]] = []

    def source(self) -> AccessibilityNode:
        return self._trees.pop(0) if len(self._trees) > 1 else self._trees[0]

    def tap(self, x: int, y: int) -> None:
        self.gestures.append((x, y))

    def screenshot(self) -> bytes:
        return b""


def _interactor(trees: list[AccessibilityNode]) -> Interactor:
    clock = FakeClock()
    return Interactor(FakeSession(trees), sleep=clock.advance, clock=clock)  # type: ignore[arg-type]


def test_tap_wait_tree_detects_change() -> None:
    before = _tree([_LOGIN])
    after = _tree([_WELCOME])
    interactor = _interactor([before, before, after])  # resolve, capture-before, then wait
    spec = WaitSpec(mode=WaitMode.TREE, timeout=10, interval=1, settle=2)
    result = interactor.tap(Locator(label="Login"), wait=spec)
    assert result.ok
    assert result.wait is not None and result.wait.mode == WaitMode.TREE and result.wait.ok


def test_tap_wait_tree_no_change_is_no_change() -> None:
    before = _tree([_LOGIN])
    interactor = _interactor([before])  # always the same tree
    spec = WaitSpec(mode=WaitMode.TREE, timeout=2, interval=1, settle=2)
    result = interactor.tap(Locator(label="Login"), wait=spec)
    assert not result.ok
    assert result.error_code == ErrorCode.NO_CHANGE
    assert result.wait is not None and not result.wait.ok


def test_tap_wait_until_predicate_appears() -> None:
    resolve = _tree([_LOGIN])
    appeared = _tree([_WELCOME])
    interactor = _interactor([resolve, appeared, appeared])
    spec = WaitSpec(
        mode=WaitMode.UNTIL, locator=Locator(label="Welcome"), timeout=10, interval=1, settle=2
    )
    result = interactor.tap(Locator(label="Login"), wait=spec)
    assert result.ok
    assert result.wait is not None and result.wait.mode == WaitMode.UNTIL and result.wait.ok
