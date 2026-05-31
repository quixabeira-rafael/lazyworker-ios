from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn

import typer

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
from lazyworker.wda.client import WdaClient
from lazyworker.wda.errors import WdaError
from lazyworker.wda.models import AccessibilityNode

app = typer.Typer(
    add_completion=False,
    help="Agent-friendly iOS automation over WebDriverAgent.",
    no_args_is_help=True,
)


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
    devices = DeviceRegistry.default().list(kind=DeviceKind.PHYSICAL, available_only=True)
    if not devices:
        _fail("No physical device available; connect and pair one (see: lazyworker doctor).")
    return devices[0].udid


def _pick_simulator() -> str:
    registry = DeviceRegistry.default()
    simulators = registry.list(kind=DeviceKind.SIMULATOR, available_only=True)
    if not simulators:
        _fail("No simulator available; specify --udid.")
    booted = [device for device in simulators if device.is_booted]
    return (booted or simulators)[0].udid


@app.command()
def bootstrap() -> None:
    """Fetch and build WebDriverAgent (simulator, or signed for device per config)."""
    config = Config.load()
    service = BootstrapService.default()
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
    except WdaError as exc:
        _fail(str(exc))
    tree = AccessibilityNode.model_validate(body["value"])
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
    except WdaError as exc:
        _fail(str(exc))
    output.write_bytes(base64.b64decode(body["value"]))
    typer.echo(str(output))
