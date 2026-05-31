from __future__ import annotations

import contextlib
import json
import sys
import time
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError

from lazyworker.bootstrap.errors import BootstrapError
from lazyworker.bootstrap.service import DEFAULT_STATE_DIR, BootstrapService
from lazyworker.bootstrap.state import load_run_state
from lazyworker.bootstrap.wda import SigningOptions
from lazyworker.config import Config, SigningMode
from lazyworker.devices.models import ConnectionType, DeviceKind
from lazyworker.devices.registry import DeviceRegistry
from lazyworker.devices.runner import CommandError
from lazyworker.doctor.checks import build_default_context, build_report
from lazyworker.doctor.render import format_report
from lazyworker.interaction.batch import Batch, BatchReport, BatchRunner
from lazyworker.interaction.detect import DetectorUnavailable, detect
from lazyworker.interaction.interactor import Interactor, build_interactor, open_session
from lazyworker.interaction.locator import Locator
from lazyworker.interaction.models import (
    Action,
    ErrorCode,
    OperationResult,
    ScrollDirection,
    WaitMode,
    exit_code_for,
)
from lazyworker.interaction.ocr import OcrUnavailable, recognize
from lazyworker.interaction.screen import describe_screen
from lazyworker.interaction.settings import (
    DEFAULT_CUSTOM_SNAPSHOT_TIMEOUT,
    DEFAULT_SCROLL_DISTANCE,
    DEFAULT_SCROLL_TO_MAX_SWIPES,
    DEFAULT_SNAPSHOT_MAX_DEPTH,
    SessionOptions,
    SnapshotSettings,
)
from lazyworker.interaction.state import (
    SessionState,
    clear_session_state,
    load_session_state,
    save_session_state,
)
from lazyworker.interaction.wait import (
    DEFAULT_INTERVAL,
    DEFAULT_SETTLE,
    DEFAULT_TIMEOUT,
    WaitSpec,
)
from lazyworker.wda.client import WdaClient
from lazyworker.wda.errors import WdaConnectionError, WdaError, WdaResponseError
from lazyworker.wda.models import AccessibilityNode
from lazyworker.wda.session import Session

app = typer.Typer(
    add_completion=False,
    help="Agent-friendly iOS automation over WebDriverAgent.",
    no_args_is_help=True,
)

ui_app = typer.Typer(
    no_args_is_help=True,
    help="Agentic app interaction: open/close a session and act on the accessibility tree.",
)
app.add_typer(ui_app, name="ui")


def _base_url(override: str | None) -> str:
    if override is not None:
        return override
    state = load_run_state(DEFAULT_STATE_DIR)
    if state is not None:
        return state.base_url
    return Config.load().wda.base_url


def _fail(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


def _signing_options(config: Config) -> SigningOptions:
    team_id = config.signing.team_id
    if team_id is None:
        _fail("signing.team_id is required for device mode; set it in lazyworker.toml.")
    return SigningOptions(team_id=team_id, runner_bundle_id=config.signing.runner_bundle_id)


def _pick_device() -> str:
    devices = sorted(
        DeviceRegistry.default().list(kind=DeviceKind.PHYSICAL, available_only=True),
        key=lambda d: d.udid,
    )
    if not devices:
        _fail("No physical device available; connect and pair one (see: lazyworker doctor).")
    if len(devices) > 1:
        listed = ", ".join(f"{d.name} ({d.udid})" for d in devices)
        _fail(f"Multiple devices found; pass --udid. Available: {listed}")
    return devices[0].udid


def _pick_simulator() -> str:
    simulators = DeviceRegistry.default().list(kind=DeviceKind.SIMULATOR, available_only=True)
    if not simulators:
        _fail("No simulator available; specify --udid.")
    booted = sorted((d for d in simulators if d.is_booted), key=lambda d: d.udid)
    if booted:
        return booted[0].udid
    return sorted(simulators, key=lambda d: d.udid)[0].udid


@app.command()
def bootstrap() -> None:
    """Fetch and build WebDriverAgent (simulator, or signed for device per config)."""
    config = Config.load()
    service = BootstrapService.default(ref=config.wda.version)
    try:
        if config.signing.mode == SigningMode.SIMULATOR:
            typer.echo("Building WebDriverAgent for the simulator (may take minutes)...")
            service.bootstrap()
        else:
            signing = _signing_options(config)
            typer.echo(f"Building signed WebDriverAgent for device (team {signing.team_id})...")
            service.bootstrap(signing=signing)
    except (BootstrapError, CommandError) as exc:
        _fail(str(exc))
    typer.echo("Bootstrap complete.")


@app.command()
def up(
    udid: str | None = typer.Option(None, "--udid", help="Device/simulator UDID (auto if unset)."),
    network: bool = typer.Option(
        False, "--network", help="Reach a device over Wi-Fi instead of USB/iproxy."
    ),
    timeout: float = typer.Option(240.0, "--timeout", help="Seconds to wait for WDA readiness."),
) -> None:
    """Launch WebDriverAgent on a simulator or physical device and wait until ready."""
    config = Config.load()
    service = BootstrapService.default()
    try:
        if config.signing.mode == SigningMode.SIMULATOR:
            target = udid or _pick_simulator()
            state = service.up(
                target, base_url=config.wda.base_url, port=config.wda.port, timeout=timeout
            )
        else:
            target = udid or _pick_device()
            state = service.up_device(
                target,
                signing=_signing_options(config),
                base_url=config.wda.base_url,
                port=config.wda.port,
                connection="network" if network else "usb",
                timeout=timeout,
            )
    except (BootstrapError, CommandError) as exc:
        _fail(str(exc))
    typer.echo(f"WDA up on {target} at {state.base_url} (pid {state.pid}).")


@app.command()
def down(
    shutdown_simulator: bool = typer.Option(
        False, "--shutdown-simulator", help="Also shut down the simulator."
    ),
) -> None:
    """Tear down the running WebDriverAgent instance."""
    state = BootstrapService.default().down(shutdown_simulator=shutdown_simulator)
    clear_session_state(DEFAULT_STATE_DIR)
    if state is None:
        typer.echo("Nothing to tear down.")
    else:
        typer.echo(f"WDA down (pid {state.pid}).")


@app.command()
def devices(
    kind: DeviceKind | None = typer.Option(None, "--kind", help="Filter by device kind."),
    connection: ConnectionType | None = typer.Option(
        None, "--connection", help="Filter by connection type."
    ),
    booted: bool = typer.Option(False, "--booted", help="Only booted simulators."),
) -> None:
    """List discovered simulators and physical devices as JSON."""
    registry = DeviceRegistry.default()
    found = registry.list(
        kind=kind,
        connection=connection,
        booted=True if booted else None,
    )
    typer.echo(json.dumps([device.model_dump(mode="json") for device in found], indent=2))
    for unavailable in registry.last_unavailable:
        typer.echo(f"warning: {unavailable}", err=True)


@app.command()
def status(base_url: str | None = typer.Option(None, "--base-url", help="WDA base URL.")) -> None:
    """Print WebDriverAgent status as JSON."""
    try:
        with WdaClient(_base_url(base_url)) as client:
            result = client.status()
    except WdaError as exc:
        _fail(str(exc))
    typer.echo(result.model_dump_json(indent=2))


@app.command()
def doctor(
    udid: str | None = typer.Option(None, "--udid", help="Focus checks on one physical device."),
    as_json: bool = typer.Option(False, "--json", help="Emit the report as JSON."),
    base_url: str | None = typer.Option(None, "--base-url", help="WDA base URL."),
) -> None:
    """Evaluate the environment and report what is needed for automation."""
    config = Config.load()
    context = build_default_context(
        base_url=_base_url(base_url),
        target_udid=udid,
        configured_team_id=config.signing.team_id,
    )
    report = build_report(context)
    if as_json:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(format_report(report), nl=False)
    if report.blocking:
        raise typer.Exit(code=1)


@app.command()
def source(base_url: str | None = typer.Option(None, "--base-url", help="WDA base URL.")) -> None:
    """Print the current accessibility tree as JSON."""
    try:
        with WdaClient(_base_url(base_url)) as client:
            body = client.request("GET", "/source", params={"format": "json"})
            value = client.value(body)
    except WdaError as exc:
        _fail(str(exc))
    tree = AccessibilityNode.model_validate(value)
    typer.echo(tree.model_dump_json(indent=2, exclude_none=True))


@app.command()
def screenshot(
    output: Path = typer.Option(Path("screenshot.png"), "--output", "-o", help="Output PNG path."),
    base_url: str | None = typer.Option(None, "--base-url", help="WDA base URL."),
) -> None:
    """Capture the current screen to a PNG file."""
    import base64

    try:
        with WdaClient(_base_url(base_url)) as client:
            body = client.request("GET", "/screenshot")
            data = base64.b64decode(client.value(body))
    except (WdaError, ValueError) as exc:
        _fail(str(exc))
    output.write_bytes(data)
    typer.echo(str(output))


# --- ui sub-group: agentic interaction ---

_Type = Annotated[str | None, typer.Option("--type", help="Element type, e.g. Button.")]
_Label = Annotated[str | None, typer.Option("--label", help="Accessibility label.")]
_Name = Annotated[str | None, typer.Option("--name", help="Accessibility name.")]
_Value = Annotated[str | None, typer.Option("--value", help="Element value.")]
_Identifier = Annotated[str | None, typer.Option("--identifier", help="Accessibility identifier.")]
_Index = Annotated[int | None, typer.Option("--index", help="Pick the Nth match (0-based).")]
_AnyVis = Annotated[bool, typer.Option("--any-visibility", help="Also match invisible elements.")]
_At = Annotated[str | None, typer.Option("--at", help="Coordinate fallback, X,Y.")]
_DryRun = Annotated[bool, typer.Option("--dry-run", help="Resolve and report without acting.")]
_UiBaseUrl = Annotated[str | None, typer.Option("--base-url", help="WDA base URL.")]
_Wait = Annotated[
    str | None, typer.Option("--wait", help="Wait for a diff after acting: tree|screen.")
]
_WaitUntil = Annotated[
    str | None, typer.Option("--wait-until", help="Wait until selector appears (key=value).")
]
_WaitGone = Annotated[
    str | None, typer.Option("--wait-gone", help="Wait until selector disappears (key=value).")
]
_WaitTimeout = Annotated[float, typer.Option("--wait-timeout", help="Smart-wait timeout (s).")]
_WaitSettle = Annotated[int, typer.Option("--wait-settle", help="Stable polls to settle.")]
_WaitInterval = Annotated[float, typer.Option("--wait-interval", help="Poll interval (s).")]


def _classify_wda(exc: WdaError) -> ErrorCode:
    if isinstance(exc, WdaConnectionError):
        return ErrorCode.WDA_UNREACHABLE
    if isinstance(exc, WdaResponseError) and (
        exc.status_code == 404 or "session" in str(exc).lower()
    ):
        return ErrorCode.SESSION_INVALID
    return ErrorCode.WDA_ERROR


def _emit(result: OperationResult) -> NoReturn:
    typer.echo(result.model_dump_json(indent=2, exclude_none=True))
    raise typer.Exit(code=0 if result.ok else exit_code_for(result.error_code))


def _emit_report(report: BatchReport) -> NoReturn:
    typer.echo(report.model_dump_json(indent=2, exclude_none=True))
    if report.ok:
        raise typer.Exit(code=0)
    failure = next((result for result in report.results if not result.ok), None)
    raise typer.Exit(code=exit_code_for(failure.error_code) if failure else 1)


def _interactor(base_url: str | None) -> Interactor:
    interactor = build_interactor(DEFAULT_STATE_DIR, base_url=base_url)
    if interactor is None:
        _emit(
            OperationResult.failure(
                Action.OPEN,
                ErrorCode.NO_SESSION,
                "no active session; run: lazyworker ui open <bundle-id>",
            )
        )
    return interactor


def _parse_at(action: Action, at: str | None) -> tuple[int, int] | None:
    if at is None:
        return None
    parts = at.split(",")
    try:
        if len(parts) != 2:
            raise ValueError
        return int(parts[0]), int(parts[1])
    except ValueError:
        _emit(
            OperationResult.failure(
                action, ErrorCode.INVALID_TARGET, f"invalid --at '{at}', expected X,Y"
            )
        )


def _locator(
    type_: str | None,
    label: str | None,
    name: str | None,
    value: str | None,
    identifier: str | None,
    index: int | None,
    any_visibility: bool,
) -> Locator | None:
    if all(item is None for item in (type_, label, name, value, identifier)):
        return None
    return Locator(
        type=type_,
        label=label,
        name=name,
        value=value,
        identifier=identifier,
        index=index,
        visible=None if any_visibility else True,
    )


_PREDICATE_FIELDS = {
    "type": "type",
    "label": "label",
    "name": "name",
    "value": "value",
    "identifier": "identifier",
    "id": "identifier",
}


def _predicate_locator(action: Action, spec: str) -> Locator:
    if "=" not in spec:
        _emit(
            OperationResult.failure(
                action, ErrorCode.INVALID_TARGET, f"invalid predicate '{spec}', expected key=value"
            )
        )
    key, _, value = spec.partition("=")
    field = _PREDICATE_FIELDS.get(key.strip())
    if field is None:
        _emit(
            OperationResult.failure(
                action, ErrorCode.INVALID_TARGET, f"unknown predicate key '{key.strip()}'"
            )
        )
    return Locator(**{field: value}, visible=True)


def _build_wait(
    action: Action,
    wait: str | None,
    wait_until: str | None,
    wait_gone: str | None,
    timeout: float,
    settle: int,
    interval: float,
) -> WaitSpec | None:
    common = {"timeout": timeout, "settle": settle, "interval": interval}
    if wait_until is not None:
        locator = _predicate_locator(action, wait_until)
        return WaitSpec(mode=WaitMode.UNTIL, locator=locator, **common)
    if wait_gone is not None:
        locator = _predicate_locator(action, wait_gone)
        return WaitSpec(mode=WaitMode.GONE, locator=locator, **common)
    if wait is None:
        return None
    if wait not in ("tree", "screen"):
        _emit(
            OperationResult.failure(
                action, ErrorCode.INVALID_TARGET, f"--wait must be 'tree' or 'screen', got '{wait}'"
            )
        )
    if wait == "screen":
        try:
            import PIL  # noqa: F401
        except ImportError:
            _emit(
                OperationResult.failure(
                    action,
                    ErrorCode.INVALID_TARGET,
                    "screen diff needs Pillow; install: pip install 'lazyworker[ocr]'",
                )
            )
    return WaitSpec(mode=WaitMode(wait), **common)


@ui_app.command("open")
def ui_open(
    bundle_id: str = typer.Argument(..., help="App bundle id, e.g. com.apple.Preferences."),
    snapshot_max_depth: int = typer.Option(DEFAULT_SNAPSHOT_MAX_DEPTH, "--snapshot-max-depth"),
    snapshot_timeout: float = typer.Option(DEFAULT_CUSTOM_SNAPSHOT_TIMEOUT, "--snapshot-timeout"),
    wait_for_quiescence: bool = typer.Option(
        False, "--wait-for-quiescence/--no-wait-for-quiescence"
    ),
    reuse: bool = typer.Option(True, "--reuse/--no-reuse", help="Reuse a live session if present."),
    base_url: _UiBaseUrl = None,
) -> None:
    """Open an app, create a tuned WDA session, and persist it."""
    url = _base_url(base_url)
    existing = load_session_state(DEFAULT_STATE_DIR)
    if reuse and existing and existing.bundle_id == bundle_id and existing.base_url == url:
        _emit(
            OperationResult(
                operation=Action.OPEN, ok=True, message=f"reused session {existing.session_id}"
            )
        )
    options = SessionOptions(
        wait_for_quiescence=wait_for_quiescence,
        settings=SnapshotSettings(
            snapshotMaxDepth=snapshot_max_depth, customSnapshotTimeout=snapshot_timeout
        ),
    )
    try:
        session = open_session(WdaClient(url), bundle_id, options)
    except WdaError as exc:
        _emit(OperationResult.failure(Action.OPEN, _classify_wda(exc), str(exc)))
    save_session_state(
        SessionState(session_id=session.id, bundle_id=bundle_id, base_url=url), DEFAULT_STATE_DIR
    )
    _emit(OperationResult(operation=Action.OPEN, ok=True, message=f"session {session.id}"))


@ui_app.command("close")
def ui_close(base_url: _UiBaseUrl = None) -> None:
    """Close the active app session."""
    state = load_session_state(DEFAULT_STATE_DIR)
    if state is None:
        _emit(OperationResult(operation=Action.CLOSE, ok=True, message="no active session"))
    with contextlib.suppress(WdaError):
        Session(WdaClient(base_url or state.base_url), state.session_id).delete()
    clear_session_state(DEFAULT_STATE_DIR)
    _emit(OperationResult(operation=Action.CLOSE, ok=True))


@ui_app.command("tree")
def ui_tree(base_url: _UiBaseUrl = None) -> None:
    """Print the current accessibility tree (using the open session's settings)."""
    interactor = _interactor(base_url)
    try:
        tree = interactor.snapshot()
    except WdaError as exc:
        _emit(OperationResult.failure(Action.TREE, _classify_wda(exc), str(exc)))
    typer.echo(tree.model_dump_json(indent=2, exclude_none=True))


@ui_app.command("tap")
def ui_tap(
    type_: _Type = None,
    label: _Label = None,
    name: _Name = None,
    value: _Value = None,
    identifier: _Identifier = None,
    index: _Index = None,
    any_visibility: _AnyVis = False,
    at: _At = None,
    dry_run: _DryRun = False,
    wait: _Wait = None,
    wait_until: _WaitUntil = None,
    wait_gone: _WaitGone = None,
    wait_timeout: _WaitTimeout = DEFAULT_TIMEOUT,
    wait_settle: _WaitSettle = DEFAULT_SETTLE,
    wait_interval: _WaitInterval = DEFAULT_INTERVAL,
    base_url: _UiBaseUrl = None,
) -> None:
    """Tap an element (by selector) or a coordinate."""
    interactor = _interactor(base_url)
    point = _parse_at(Action.TAP, at)
    locator = _locator(type_, label, name, value, identifier, index, any_visibility)
    spec = _build_wait(
        Action.TAP, wait, wait_until, wait_gone, wait_timeout, wait_settle, wait_interval
    )
    _emit(interactor.tap(locator, at=point, dry_run=dry_run, wait=spec))


@ui_app.command("double-tap")
def ui_double_tap(
    type_: _Type = None,
    label: _Label = None,
    name: _Name = None,
    value: _Value = None,
    identifier: _Identifier = None,
    index: _Index = None,
    any_visibility: _AnyVis = False,
    at: _At = None,
    dry_run: _DryRun = False,
    base_url: _UiBaseUrl = None,
) -> None:
    """Double-tap an element or a coordinate."""
    interactor = _interactor(base_url)
    point = _parse_at(Action.DOUBLE_TAP, at)
    locator = _locator(type_, label, name, value, identifier, index, any_visibility)
    _emit(interactor.double_tap(locator, at=point, dry_run=dry_run))


@ui_app.command("long-press")
def ui_long_press(
    type_: _Type = None,
    label: _Label = None,
    name: _Name = None,
    value: _Value = None,
    identifier: _Identifier = None,
    index: _Index = None,
    any_visibility: _AnyVis = False,
    at: _At = None,
    duration: float = typer.Option(0.8, "--duration", help="Hold duration in seconds."),
    dry_run: _DryRun = False,
    base_url: _UiBaseUrl = None,
) -> None:
    """Long-press an element or a coordinate."""
    interactor = _interactor(base_url)
    point = _parse_at(Action.LONG_PRESS, at)
    locator = _locator(type_, label, name, value, identifier, index, any_visibility)
    _emit(interactor.long_press(locator, at=point, duration=duration, dry_run=dry_run))


@ui_app.command("scroll")
def ui_scroll(
    direction: ScrollDirection = typer.Option(..., "--direction"),
    distance: float = typer.Option(DEFAULT_SCROLL_DISTANCE, "--distance"),
    dry_run: _DryRun = False,
    wait: _Wait = None,
    wait_until: _WaitUntil = None,
    wait_gone: _WaitGone = None,
    wait_timeout: _WaitTimeout = DEFAULT_TIMEOUT,
    wait_settle: _WaitSettle = DEFAULT_SETTLE,
    wait_interval: _WaitInterval = DEFAULT_INTERVAL,
    base_url: _UiBaseUrl = None,
) -> None:
    """Scroll the screen in a direction."""
    interactor = _interactor(base_url)
    spec = _build_wait(
        Action.SCROLL, wait, wait_until, wait_gone, wait_timeout, wait_settle, wait_interval
    )
    _emit(interactor.scroll(direction, amount=distance, dry_run=dry_run, wait=spec))


@ui_app.command("scroll-to")
def ui_scroll_to(
    type_: _Type = None,
    label: _Label = None,
    name: _Name = None,
    value: _Value = None,
    identifier: _Identifier = None,
    index: _Index = None,
    any_visibility: _AnyVis = False,
    direction: ScrollDirection = typer.Option(ScrollDirection.DOWN, "--direction"),
    max_swipes: int = typer.Option(DEFAULT_SCROLL_TO_MAX_SWIPES, "--max-swipes"),
    dry_run: _DryRun = False,
    base_url: _UiBaseUrl = None,
) -> None:
    """Scroll until an element becomes visible."""
    interactor = _interactor(base_url)
    locator = _locator(type_, label, name, value, identifier, index, any_visibility)
    if locator is None:
        _emit(
            OperationResult.failure(
                Action.SCROLL_TO, ErrorCode.INVALID_TARGET, "scroll-to requires a selector"
            )
        )
    _emit(
        interactor.scroll_to(
            locator, direction=direction, max_swipes=max_swipes, dry_run=dry_run
        )
    )


@ui_app.command("type")
def ui_type(
    text: str = typer.Option(..., "--text", help="Text to type."),
    type_: _Type = None,
    label: _Label = None,
    name: _Name = None,
    value: _Value = None,
    identifier: _Identifier = None,
    index: _Index = None,
    any_visibility: _AnyVis = False,
    at: _At = None,
    dry_run: _DryRun = False,
    wait: _Wait = None,
    wait_until: _WaitUntil = None,
    wait_gone: _WaitGone = None,
    wait_timeout: _WaitTimeout = DEFAULT_TIMEOUT,
    wait_settle: _WaitSettle = DEFAULT_SETTLE,
    wait_interval: _WaitInterval = DEFAULT_INTERVAL,
    base_url: _UiBaseUrl = None,
) -> None:
    """Type text, optionally tapping a field first to focus it."""
    interactor = _interactor(base_url)
    point = _parse_at(Action.TYPE, at)
    locator = _locator(type_, label, name, value, identifier, index, any_visibility)
    spec = _build_wait(
        Action.TYPE, wait, wait_until, wait_gone, wait_timeout, wait_settle, wait_interval
    )
    _emit(interactor.type_text(text, locator=locator, at=point, dry_run=dry_run, wait=spec))


@ui_app.command("screenshot")
def ui_screenshot(
    output: Path = typer.Option(Path("screenshot.png"), "--output", "-o"),
    base_url: _UiBaseUrl = None,
) -> None:
    """Capture the current screen to a PNG using the active session."""
    interactor = _interactor(base_url)
    try:
        data = interactor.screenshot()
    except WdaError as exc:
        _emit(OperationResult.failure(Action.SCREENSHOT, _classify_wda(exc), str(exc)))
    output.write_bytes(data)
    _emit(OperationResult(operation=Action.SCREENSHOT, ok=True, message=str(output)))


@ui_app.command("screen")
def ui_screen(
    output: Path | None = typer.Option(None, "--output", "-o", help="Screenshot PNG path."),
    ocr: bool = typer.Option(False, "--ocr", help="Also run Apple Vision OCR on the screenshot."),
    detect_visual: bool = typer.Option(
        False, "--detect", help="Also run the local visual UI detector (OmniParser)."
    ),
    base_url: _UiBaseUrl = None,
) -> None:
    """Capture the screen and emit a textual breakdown (screenshot + boxes) as JSON."""
    interactor = _interactor(base_url)
    try:
        data = interactor.screenshot()
        tree = interactor.snapshot()
    except WdaError as exc:
        _emit(OperationResult.failure(Action.SCREEN, _classify_wda(exc), str(exc)))
    path = output or (DEFAULT_STATE_DIR / "screens" / f"screen-{int(time.time())}.png")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    width = tree.rect.width if tree.rect else 0
    height = tree.rect.height if tree.rect else 0
    ocr_results = None
    if ocr:
        try:
            ocr_results = recognize(str(path), screen_width=width, screen_height=height)
        except OcrUnavailable as exc:
            _emit(OperationResult.failure(Action.SCREEN, ErrorCode.OCR_UNAVAILABLE, str(exc)))
    detections = None
    if detect_visual:
        try:
            detections = detect(str(path), screen_width=width, screen_height=height)
        except DetectorUnavailable as exc:
            _emit(OperationResult.failure(Action.SCREEN, ErrorCode.DETECTOR_UNAVAILABLE, str(exc)))
    state = load_session_state(DEFAULT_STATE_DIR)
    description = describe_screen(
        tree,
        screenshot=str(path),
        bundle_id=state.bundle_id if state else None,
        ocr=ocr_results,
        detections=detections,
    )
    typer.echo(description.model_dump_json(indent=2, exclude_none=True))


@ui_app.command("batch")
def ui_batch(
    file: Path | None = typer.Option(None, "--file", help="JSON ops array; stdin if omitted."),
    stop_on_error: bool = typer.Option(True, "--stop-on-error/--continue-on-error"),
    base_url: _UiBaseUrl = None,
) -> None:
    """Run an ordered list of operations (JSON array via --file or stdin)."""
    raw = file.read_text() if file is not None else sys.stdin.read()
    try:
        operations = json.loads(raw)
    except ValueError as exc:
        _emit(
            OperationResult.failure(Action.OPEN, ErrorCode.INVALID_TARGET, f"invalid JSON: {exc}")
        )
    try:
        batch = Batch.model_validate({"stop_on_error": stop_on_error, "operations": operations})
    except ValidationError as exc:
        _emit(OperationResult.failure(Action.OPEN, ErrorCode.INVALID_TARGET, str(exc)))
    _emit_report(BatchRunner(_interactor(base_url)).run(batch))
