from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lazyworker.interaction.locator import Locator, LocatorResolver
from lazyworker.interaction.models import (
    Action,
    ErrorCode,
    MatchedElement,
    OperationResult,
    ScrollDirection,
)
from lazyworker.interaction.settings import (
    DEFAULT_SCROLL_DISTANCE,
    DEFAULT_SCROLL_TO_MAX_SWIPES,
    SessionOptions,
)
from lazyworker.interaction.state import load_session_state
from lazyworker.wda.client import WdaClient
from lazyworker.wda.errors import WdaConnectionError, WdaResponseError
from lazyworker.wda.models import AccessibilityNode
from lazyworker.wda.session import Session

Point = tuple[int, int]


@dataclass(frozen=True)
class _Target:
    node: AccessibilityNode
    point: Point


def _scroll_points(
    width: int, height: int, direction: ScrollDirection, amount: float
) -> tuple[Point, Point]:
    cx, cy = width // 2, height // 2
    dx, dy = int(width * amount * 0.5), int(height * amount * 0.5)
    if direction == ScrollDirection.DOWN:
        return (cx, cy + dy), (cx, cy - dy)
    if direction == ScrollDirection.UP:
        return (cx, cy - dy), (cx, cy + dy)
    if direction == ScrollDirection.LEFT:
        return (cx + dx, cy), (cx - dx, cy)
    return (cx - dx, cy), (cx + dx, cy)


class Interactor:
    """Combines snapshot, locator resolution, gestures and typed results."""

    def __init__(
        self,
        session: Session,
        *,
        resolver: LocatorResolver | None = None,
    ) -> None:
        self._session = session
        self._resolver = resolver or LocatorResolver()
        self._screen: Point | None = None

    def snapshot(self) -> AccessibilityNode:
        return self._session.source()

    def screenshot(self) -> bytes:
        return self._session.screenshot()

    def tap(
        self, locator: Locator | None = None, *, at: Point | None = None, dry_run: bool = False
    ) -> OperationResult:
        return self._targeted(
            Action.TAP, lambda p: self._session.tap(*p), locator=locator, at=at, dry_run=dry_run
        )

    def double_tap(
        self, locator: Locator | None = None, *, at: Point | None = None, dry_run: bool = False
    ) -> OperationResult:
        return self._targeted(
            Action.DOUBLE_TAP,
            lambda p: self._session.double_tap(*p),
            locator=locator,
            at=at,
            dry_run=dry_run,
        )

    def long_press(
        self,
        locator: Locator | None = None,
        *,
        at: Point | None = None,
        duration: float = 0.8,
        dry_run: bool = False,
    ) -> OperationResult:
        return self._targeted(
            Action.LONG_PRESS,
            lambda p: self._session.long_press(*p, duration=duration),
            locator=locator,
            at=at,
            dry_run=dry_run,
        )

    def type_text(
        self,
        text: str,
        *,
        locator: Locator | None = None,
        at: Point | None = None,
        dry_run: bool = False,
    ) -> OperationResult:
        element: MatchedElement | None = None
        point: Point | None = at
        if locator is not None:
            target = self._resolve_target(Action.TYPE, locator)
            if isinstance(target, OperationResult):
                return target
            element = MatchedElement.from_node(target.node)
            point = target.point
        if dry_run:
            return OperationResult.success(Action.TYPE, element=element, point=point, dry_run=True)
        try:
            if point is not None:
                self._session.tap(*point)
            self._session.type_text(text)
        except (WdaConnectionError, WdaResponseError) as exc:
            return OperationResult.failure(
                Action.TYPE, self._classify(exc), str(exc), element=element
            )
        return OperationResult.success(Action.TYPE, element=element, point=point)

    def scroll(
        self,
        direction: ScrollDirection,
        *,
        amount: float = DEFAULT_SCROLL_DISTANCE,
        dry_run: bool = False,
    ) -> OperationResult:
        try:
            width, height = self._screen_size()
        except (WdaConnectionError, WdaResponseError) as exc:
            return OperationResult.failure(Action.SCROLL, self._classify(exc), str(exc))
        start, end = _scroll_points(width, height, direction, amount)
        if dry_run:
            return OperationResult.success(Action.SCROLL, point=start, dry_run=True)
        try:
            self._session.swipe(start[0], start[1], end[0], end[1])
        except (WdaConnectionError, WdaResponseError) as exc:
            return OperationResult.failure(Action.SCROLL, self._classify(exc), str(exc))
        return OperationResult.success(Action.SCROLL, point=start)

    def scroll_to(
        self,
        locator: Locator,
        *,
        direction: ScrollDirection = ScrollDirection.DOWN,
        max_swipes: int = DEFAULT_SCROLL_TO_MAX_SWIPES,
        dry_run: bool = False,
    ) -> OperationResult:
        if dry_run:
            target = self._resolve_target(Action.SCROLL_TO, locator)
            if isinstance(target, OperationResult):
                return target
            return OperationResult.success(
                Action.SCROLL_TO,
                element=MatchedElement.from_node(target.node),
                point=target.point,
                dry_run=True,
            )
        try:
            width, height = self._screen_size()
        except (WdaConnectionError, WdaResponseError) as exc:
            return OperationResult.failure(Action.SCROLL_TO, self._classify(exc), str(exc))
        start, end = _scroll_points(width, height, direction, DEFAULT_SCROLL_DISTANCE)

        for attempt in range(1, max_swipes + 1):
            try:
                tree = self._session.source()
            except (WdaConnectionError, WdaResponseError) as exc:
                return OperationResult.failure(Action.SCROLL_TO, self._classify(exc), str(exc))
            resolution = self._resolver.resolve(tree, locator)
            if (
                resolution.error_code == ErrorCode.OK
                and resolution.node is not None
                and resolution.node.rect is not None
            ):
                return OperationResult.success(
                    Action.SCROLL_TO,
                    element=MatchedElement.from_node(resolution.node),
                    point=resolution.node.rect.center,
                    attempts=attempt,
                )
            if resolution.error_code == ErrorCode.AMBIGUOUS:
                return OperationResult.failure(
                    Action.SCROLL_TO,
                    ErrorCode.AMBIGUOUS,
                    f"{resolution.candidate_count} elements matched",
                    candidate_count=resolution.candidate_count,
                    candidates=[MatchedElement.from_node(n) for n in resolution.candidates],
                )
            try:
                self._session.swipe(start[0], start[1], end[0], end[1])
            except (WdaConnectionError, WdaResponseError) as exc:
                return OperationResult.failure(Action.SCROLL_TO, self._classify(exc), str(exc))

        return OperationResult.failure(
            Action.SCROLL_TO,
            ErrorCode.NOT_VISIBLE,
            f"element not visible after {max_swipes} swipes",
        )

    def _targeted(
        self,
        action: Action,
        gesture: Callable[[Point], None],
        *,
        locator: Locator | None,
        at: Point | None,
        dry_run: bool,
    ) -> OperationResult:
        element: MatchedElement | None = None
        if at is not None:
            if locator is not None:
                return OperationResult.failure(
                    action, ErrorCode.INVALID_TARGET, "provide either a selector or --at, not both"
                )
            bounds = self._bounds_error(action, at)
            if bounds is not None:
                return bounds
            point = at
        elif locator is not None:
            target = self._resolve_target(action, locator)
            if isinstance(target, OperationResult):
                return target
            element = MatchedElement.from_node(target.node)
            point = target.point
        else:
            return OperationResult.failure(
                action, ErrorCode.INVALID_TARGET, "a selector or --at is required"
            )
        if dry_run:
            return OperationResult.success(action, element=element, point=point, dry_run=True)
        try:
            gesture(point)
        except (WdaConnectionError, WdaResponseError) as exc:
            return OperationResult.failure(action, self._classify(exc), str(exc), element=element)
        return OperationResult.success(action, element=element, point=point)

    def _bounds_error(self, action: Action, point: Point) -> OperationResult | None:
        """Best-effort bounds check; only when screen size is already known."""
        if self._screen is None:
            return None
        width, height = self._screen
        if 0 <= point[0] < width and 0 <= point[1] < height:
            return None
        return OperationResult.failure(
            action, ErrorCode.OUT_OF_BOUNDS, f"point {point} is outside screen {width}x{height}"
        )

    def _resolve_target(self, action: Action, locator: Locator) -> _Target | OperationResult:
        try:
            tree = self._session.source()
        except (WdaConnectionError, WdaResponseError) as exc:
            return OperationResult.failure(action, self._classify(exc), str(exc))
        resolution = self._resolver.resolve(tree, locator)
        if resolution.error_code == ErrorCode.NOT_FOUND:
            return OperationResult.failure(
                action, ErrorCode.NOT_FOUND, "no element matched", candidate_count=0
            )
        if resolution.error_code == ErrorCode.AMBIGUOUS:
            return OperationResult.failure(
                action,
                ErrorCode.AMBIGUOUS,
                f"{resolution.candidate_count} elements matched",
                candidate_count=resolution.candidate_count,
                candidates=[MatchedElement.from_node(n) for n in resolution.candidates],
            )
        node = resolution.node
        assert node is not None
        if node.rect is None:
            return OperationResult.failure(
                action,
                ErrorCode.NO_RECT,
                "matched element has no frame",
                element=MatchedElement.from_node(node),
            )
        return _Target(node=node, point=node.rect.center)

    def _screen_size(self) -> Point:
        if self._screen is not None:
            return self._screen
        tree = self._session.source()
        rect = tree.rect
        if rect is None or rect.width == 0 or rect.height == 0:
            raise WdaResponseError("could not determine screen size from the snapshot")
        self._screen = (rect.width, rect.height)
        return self._screen

    @staticmethod
    def _classify(exc: WdaConnectionError | WdaResponseError) -> ErrorCode:
        if isinstance(exc, WdaConnectionError):
            return ErrorCode.WDA_UNREACHABLE
        if exc.status_code == 404 or "session" in str(exc).lower():
            return ErrorCode.SESSION_INVALID
        return ErrorCode.WDA_ERROR


def open_session(client: WdaClient, bundle_id: str, options: SessionOptions) -> Session:
    session = client.create_session(bundle_id, wait_for_quiescence=options.wait_for_quiescence)
    session.apply_settings(options.settings.as_payload())
    return session


def build_interactor(state_dir: Path, *, base_url: str | None = None) -> Interactor | None:
    state = load_session_state(state_dir)
    if state is None:
        return None
    client = WdaClient(base_url or state.base_url)
    return Interactor(Session(client, state.session_id))
