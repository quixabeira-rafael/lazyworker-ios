from __future__ import annotations

import io
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lazyworker.interaction.locator import Locator, LocatorResolver
from lazyworker.interaction.models import (
    Action,
    ColorResult,
    ErrorCode,
    MatchedElement,
    OperationResult,
    PaletteColor,
    ScrollDirection,
    WaitMode,
    WaitOutcome,
)
from lazyworker.interaction.settings import (
    DEFAULT_SCROLL_DISTANCE,
    DEFAULT_SCROLL_TO_MAX_SWIPES,
    SessionOptions,
)
from lazyworker.interaction.state import load_session_state
from lazyworker.interaction.textcolor import color_palette, read_text_color
from lazyworker.interaction.wait import (
    WaitSpec,
    frame_features,
    settle_wait,
    tree_signature,
    wait_for,
)
from lazyworker.wda.client import WdaClient
from lazyworker.wda.errors import WdaConnectionError, WdaResponseError
from lazyworker.wda.models import AccessibilityNode
from lazyworker.wda.session import Session

Point = tuple[int, int]
POINT_BOX = 9  # points: side of the neighbourhood `ui color --at` samples around a point
# (tree signature, settle baseline (colour signature, fingerprint))
Before = tuple[str | None, tuple[tuple[int, ...], str] | None]


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
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session = session
        self._resolver = resolver or LocatorResolver()
        self._screen: Point | None = None
        self._status_bar_crop: int | None = None
        self._sleep = sleep
        self._clock = clock

    def snapshot(self) -> AccessibilityNode:
        return self._session.source()

    def screenshot(self) -> bytes:
        return self._session.screenshot()

    def color(
        self,
        locator: Locator | None = None,
        *,
        at: Point | None = None,
        region: tuple[int, int, int, int] | None = None,
        palette: bool = False,
    ) -> ColorResult:
        """Read background and text colour from an element box, a point (--at) or a region.

        Exactly one source must be given. ``at`` samples a small neighbourhood; ``region``
        is an explicit (x, y, width, height) box in points. Both reuse the same reader, so
        ``background`` is the box's dominant colour and ``text`` its separable foreground.
        """
        try:
            tree = self._session.source()
        except (WdaConnectionError, WdaResponseError) as exc:
            return ColorResult(ok=False, error_code=self._classify(exc), message=str(exc))
        element: MatchedElement | None = None
        if locator is not None:
            resolution = self._resolver.resolve(tree, locator)
            if resolution.node is None:
                message = (
                    "no element matched"
                    if resolution.error_code == ErrorCode.NOT_FOUND
                    else f"{resolution.candidate_count} elements matched"
                )
                return ColorResult(ok=False, error_code=resolution.error_code, message=message)
            rect = resolution.node.rect
            element = MatchedElement.from_node(resolution.node)
            if rect is None or not rect.width or not rect.height:
                return ColorResult(
                    ok=False, error_code=ErrorCode.NO_RECT, message="element has no frame",
                    element=element,
                )
            box_pts = (rect.x, rect.y, rect.width, rect.height)
        elif at is not None:
            box_pts = (at[0] - POINT_BOX // 2, at[1] - POINT_BOX // 2, POINT_BOX, POINT_BOX)
        elif region is not None:
            box_pts = region
        else:
            return ColorResult(
                ok=False, error_code=ErrorCode.INVALID_TARGET,
                message="color needs a selector, --at or --region",
            )
        try:
            png = self._session.screenshot()
        except (WdaConnectionError, WdaResponseError) as exc:
            return ColorResult(ok=False, error_code=self._classify(exc), message=str(exc),
                               element=element)
        try:
            from PIL import Image
        except ImportError:
            return ColorResult(
                ok=False, error_code=ErrorCode.OCR_UNAVAILABLE,
                message="colour reading needs Pillow; install: pip install 'lazyworker[ocr]'",
                element=element,
            )
        image = Image.open(io.BytesIO(png)).convert("RGB")
        scale = image.width / (tree.rect.width if tree.rect and tree.rect.width else image.width)
        crop = self._crop_box(image, box_pts, scale)
        if crop is None:
            return ColorResult(
                ok=False, error_code=ErrorCode.OUT_OF_BOUNDS,
                message=f"box {box_pts} is outside the screen", element=element,
            )
        reading = read_text_color(crop)
        entries = (
            [PaletteColor(color=c, ratio=r) for c, r in color_palette(crop)] if palette else None
        )
        return ColorResult(
            ok=True,
            element=element,
            background=reading.background,
            text=reading.text,
            solid_background=reading.solid_background,
            glyph_ratio=reading.glyph_ratio,
            confidence=reading.confidence,
            note=reading.note,
            palette=entries,
        )

    @staticmethod
    def _crop_box(image: Any, box_pts: tuple[int, int, int, int], scale: float) -> Any:
        x, y, w, h = box_pts
        left, top = max(0, round(x * scale)), max(0, round(y * scale))
        right = min(image.width, round((x + w) * scale))
        bottom = min(image.height, round((y + h) * scale))
        if right <= left or bottom <= top:
            return None
        return image.crop((left, top, right, bottom))

    def tap(
        self,
        locator: Locator | None = None,
        *,
        at: Point | None = None,
        dry_run: bool = False,
        wait: WaitSpec | None = None,
    ) -> OperationResult:
        return self._targeted(
            Action.TAP,
            lambda p: self._session.tap(*p),
            locator=locator,
            at=at,
            dry_run=dry_run,
            wait=wait,
        )

    def double_tap(
        self,
        locator: Locator | None = None,
        *,
        at: Point | None = None,
        dry_run: bool = False,
        wait: WaitSpec | None = None,
    ) -> OperationResult:
        return self._targeted(
            Action.DOUBLE_TAP,
            lambda p: self._session.double_tap(*p),
            locator=locator,
            at=at,
            dry_run=dry_run,
            wait=wait,
        )

    def long_press(
        self,
        locator: Locator | None = None,
        *,
        at: Point | None = None,
        duration: float = 0.8,
        dry_run: bool = False,
        wait: WaitSpec | None = None,
    ) -> OperationResult:
        return self._targeted(
            Action.LONG_PRESS,
            lambda p: self._session.long_press(*p, duration=duration),
            locator=locator,
            at=at,
            dry_run=dry_run,
            wait=wait,
        )

    def type_text(
        self,
        text: str,
        *,
        locator: Locator | None = None,
        at: Point | None = None,
        dry_run: bool = False,
        wait: WaitSpec | None = None,
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
        before = self._capture_before(wait)
        try:
            if point is not None:
                self._session.tap(*point)
            self._session.type_text(text)
        except (WdaConnectionError, WdaResponseError) as exc:
            return OperationResult.failure(
                Action.TYPE, self._classify(exc), str(exc), element=element
            )
        result = OperationResult.success(Action.TYPE, element=element, point=point)
        return self._apply_wait(result, wait, before)

    def deep_link(self, url: str, *, wait: WaitSpec | None = None) -> OperationResult:
        """Open a deep/universal link in the active session (routes to the handling app)."""
        before = self._capture_before(wait)
        try:
            self._session.deep_link(url)
        except (WdaConnectionError, WdaResponseError) as exc:
            return OperationResult.failure(Action.DEEPLINK, self._classify(exc), str(exc))
        result = OperationResult(operation=Action.DEEPLINK, ok=True, message=url)
        return self._apply_wait(result, wait, before)

    def scroll(
        self,
        direction: ScrollDirection,
        *,
        amount: float = DEFAULT_SCROLL_DISTANCE,
        dry_run: bool = False,
        wait: WaitSpec | None = None,
    ) -> OperationResult:
        try:
            width, height = self._screen_size()
        except (WdaConnectionError, WdaResponseError) as exc:
            return OperationResult.failure(Action.SCROLL, self._classify(exc), str(exc))
        start, end = _scroll_points(width, height, direction, amount)
        if dry_run:
            return OperationResult.success(Action.SCROLL, point=start, dry_run=True)
        before = self._capture_before(wait)
        try:
            self._session.swipe(start[0], start[1], end[0], end[1])
        except (WdaConnectionError, WdaResponseError) as exc:
            return OperationResult.failure(Action.SCROLL, self._classify(exc), str(exc))
        result = OperationResult.success(Action.SCROLL, point=start)
        return self._apply_wait(result, wait, before)

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
        wait: WaitSpec | None = None,
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
        before = self._capture_before(wait)
        try:
            gesture(point)
        except (WdaConnectionError, WdaResponseError) as exc:
            return OperationResult.failure(action, self._classify(exc), str(exc), element=element)
        result = OperationResult.success(action, element=element, point=point)
        return self._apply_wait(result, wait, before)

    def _capture_before(self, wait: WaitSpec | None) -> Before:
        if wait is None or wait.mode not in (WaitMode.TREE, WaitMode.SETTLE):
            return None, None
        try:
            if wait.mode == WaitMode.TREE:
                return tree_signature(self._session.source()), None
            png = self._session.screenshot()
            return None, frame_features(png, self._crop_top())
        except (WdaConnectionError, WdaResponseError):
            return None, None

    def _crop_top(self) -> int:
        """Status-bar height in pixels for this device, measured once and reused."""
        if self._status_bar_crop is None:
            try:
                info = self._session.screen_info()
                self._status_bar_crop = round(info["statusBarSize"]["height"] * info["scale"])
            except (WdaConnectionError, WdaResponseError, KeyError, TypeError):
                self._status_bar_crop = 0
        return self._status_bar_crop

    def _apply_wait(
        self,
        result: OperationResult,
        wait: WaitSpec | None,
        before: Before,
    ) -> OperationResult:
        if wait is None:
            return result
        outcome = self._run_wait(wait, before)
        result.wait = outcome
        if not outcome.ok:
            result.ok = False
            result.error_code = ErrorCode.NO_CHANGE
            result.message = f"no observed {wait.mode.value} change within {wait.timeout:.0f}s"
        return result

    def _run_wait(
        self, wait: WaitSpec, before: Before
    ) -> WaitOutcome:
        before_tree, before_settle = before
        if wait.mode == WaitMode.SETTLE:
            return self._run_settle(wait, before_settle)
        if wait.mode in (WaitMode.UNTIL, WaitMode.GONE):
            assert wait.locator is not None
            want_present = wait.mode == WaitMode.UNTIL

            def observe_predicate() -> bool:
                try:
                    tree = self._session.source()
                except (WdaConnectionError, WdaResponseError):
                    return not want_present
                resolution = self._resolver.resolve(tree, wait.locator)  # type: ignore[arg-type]
                present = resolution.error_code != ErrorCode.NOT_FOUND
                return present == want_present

            ok, satisfied, settled, attempts, elapsed = wait_for(
                observe_predicate,
                lambda holds: holds,
                timeout=wait.timeout,
                interval=wait.interval,
                settle=wait.settle,
                sleep=self._sleep,
                clock=self._clock,
            )
        else:  # TREE

            def observe_tree() -> str:
                try:
                    return tree_signature(self._session.source())
                except (WdaConnectionError, WdaResponseError):
                    return before_tree if before_tree is not None else ""

            ok, satisfied, settled, attempts, elapsed = wait_for(
                observe_tree,
                lambda sig: sig != before_tree,
                timeout=wait.timeout,
                interval=wait.interval,
                settle=wait.settle,
                sleep=self._sleep,
                clock=self._clock,
            )
        return WaitOutcome(
            mode=wait.mode,
            ok=ok,
            satisfied=satisfied,
            settled=settled,
            attempts=attempts,
            elapsed_s=round(elapsed, 3),
        )

    def _run_settle(
        self, wait: WaitSpec, baseline: tuple[tuple[int, ...], str] | None
    ) -> WaitOutcome:
        if baseline is None:
            return WaitOutcome(
                mode=wait.mode, ok=False, satisfied=False, settled=False,
                attempts=0, elapsed_s=0.0, verdict="no_change",
            )

        crop = self._crop_top()

        def observe() -> tuple[tuple[int, ...], str]:
            try:
                png = self._session.screenshot()
            except (WdaConnectionError, WdaResponseError):
                return baseline
            return frame_features(png, crop)

        outcome = settle_wait(
            observe, baseline, spec=wait, sleep=self._sleep, clock=self._clock
        )
        return WaitOutcome(
            mode=wait.mode,
            ok=outcome.settled,
            satisfied=outcome.onset,
            settled=outcome.settled,
            attempts=outcome.attempts,
            elapsed_s=outcome.elapsed_s,
            verdict=outcome.verdict,
        )

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
