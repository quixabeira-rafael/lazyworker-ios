from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass

from lazyworker.bootstrap.service import DEFAULT_STATE_DIR
from lazyworker.bootstrap.wda import WdaProject
from lazyworker.devices.models import Device
from lazyworker.devices.registry import DeviceRegistry
from lazyworker.devices.runner import CommandError, CommandRunner, SubprocessRunner
from lazyworker.doctor.models import CheckResult, CheckStatus, DoctorReport
from lazyworker.doctor.signing import development_teams, list_identities
from lazyworker.doctor.xcode import XcodeTeam, load_xcode_teams
from lazyworker.wda.client import WdaClient
from lazyworker.wda.errors import WdaError

ENVIRONMENT = "Environment"


@dataclass
class DoctorContext:
    runner: CommandRunner
    devices: list[Device]
    project: WdaProject
    base_url: str
    target_udid: str | None
    tool_exists: Callable[[str], bool]
    wda_probe: Callable[[], bool]
    xcode_teams: list[XcodeTeam]
    configured_team_id: str | None = None


def check_xcode(ctx: DoctorContext) -> CheckResult:
    try:
        output = ctx.runner.run(["xcodebuild", "-version"])
    except FileNotFoundError:
        return CheckResult(
            group=ENVIRONMENT,
            name="Xcode",
            status=CheckStatus.ACTION_REQUIRED,
            detail="xcodebuild not found",
            remediation="Install Xcode and run: xcode-select --install",
        )
    except CommandError as exc:
        return CheckResult(
            group=ENVIRONMENT,
            name="Xcode",
            status=CheckStatus.ACTION_REQUIRED,
            detail=exc.stderr.strip() or "xcodebuild failed",
            remediation="Open Xcode once to finish installation, then accept the license.",
        )
    first_line = output.strip().splitlines()[0] if output.strip() else "Xcode"
    return CheckResult(group=ENVIRONMENT, name="Xcode", status=CheckStatus.OK, detail=first_line)


def check_signing(ctx: DoctorContext) -> CheckResult:
    """Device signing needs the team signed into Xcode, not just a keychain cert."""
    account_team_ids = [t.team_id for t in ctx.xcode_teams if t.team_id]

    if not account_team_ids:
        return _signing_no_account(ctx)

    free_ids = [t.team_id for t in ctx.xcode_teams if t.is_free and t.team_id]
    available = ", ".join(account_team_ids)

    if ctx.configured_team_id and ctx.configured_team_id not in account_team_ids:
        return CheckResult(
            group=ENVIRONMENT,
            name="Signing",
            status=CheckStatus.ACTION_REQUIRED,
            detail=f"configured team {ctx.configured_team_id} is not signed into Xcode",
            remediation=(
                f"Set signing.team_id to one of: {available} "
                f"(free: {', '.join(free_ids) or 'none'})."
            ),
        )

    free_hint = f"; free: {', '.join(free_ids)}" if free_ids else ""
    return CheckResult(
        group=ENVIRONMENT,
        name="Signing",
        status=CheckStatus.OK,
        detail=f"Xcode team(s): {available}{free_hint}",
    )


def _signing_no_account(ctx: DoctorContext) -> CheckResult:
    try:
        identities = list_identities(ctx.runner)
    except (FileNotFoundError, CommandError):
        identities = []
    cert_teams = development_teams(identities)
    detail = (
        f"certificates present ({', '.join(cert_teams)}) but no Apple ID in Xcode"
        if cert_teams
        else "no Apple ID signed into Xcode"
    )
    return CheckResult(
        group=ENVIRONMENT,
        name="Signing",
        status=CheckStatus.ACTION_REQUIRED,
        detail=detail,
        remediation="Sign in: Xcode > Settings > Accounts > + > Apple ID.",
    )


def check_port_forwarding(ctx: DoctorContext) -> CheckResult:
    if ctx.tool_exists("iproxy"):
        return CheckResult(
            group=ENVIRONMENT,
            name="Port forwarding",
            status=CheckStatus.OK,
            detail="iproxy available",
        )
    return CheckResult(
        group=ENVIRONMENT,
        name="Port forwarding",
        status=CheckStatus.ACTION_REQUIRED,
        detail="iproxy not found (needed for USB devices)",
        remediation="Install it: brew install libimobiledevice",
    )


def check_wda_build(ctx: DoctorContext) -> CheckResult:
    if ctx.project.has_build():
        return CheckResult(
            group=ENVIRONMENT,
            name="WDA build",
            status=CheckStatus.OK,
            detail=f"built at {ctx.project.derived_data_dir}",
        )
    return CheckResult(
        group=ENVIRONMENT,
        name="WDA build",
        status=CheckStatus.WARN,
        detail="WebDriverAgent not built yet",
        remediation="Build it: lazyworker bootstrap",
    )


def check_wda_server(ctx: DoctorContext) -> CheckResult:
    if ctx.wda_probe():
        return CheckResult(
            group=ENVIRONMENT,
            name="WDA server",
            status=CheckStatus.OK,
            detail=f"ready at {ctx.base_url}",
        )
    return CheckResult(
        group=ENVIRONMENT,
        name="WDA server",
        status=CheckStatus.WARN,
        detail="not running",
        remediation="Start it: lazyworker up",
    )


def _target_devices(ctx: DoctorContext) -> list[Device]:
    physical = [d for d in ctx.devices if d.is_physical]
    if ctx.target_udid is not None:
        return [d for d in physical if d.udid == ctx.target_udid]
    return physical


def check_devices(ctx: DoctorContext) -> CheckResult:
    physical = [d for d in ctx.devices if d.is_physical]
    if not physical:
        return CheckResult(
            group=ENVIRONMENT,
            name="Devices",
            status=CheckStatus.ACTION_REQUIRED,
            detail="no physical device detected",
            remediation="Connect an iPhone via USB (or pair over Wi-Fi) and trust this Mac.",
        )
    names = ", ".join(d.name for d in physical)
    return CheckResult(
        group=ENVIRONMENT,
        name="Devices",
        status=CheckStatus.OK,
        detail=f"{len(physical)} physical: {names}",
    )


def device_checks(ctx: DoctorContext, device: Device) -> list[CheckResult]:
    group = f"Device: {device.name} ({device.udid[:13]})"
    results: list[CheckResult] = []

    if device.developer_mode_enabled is False:
        results.append(
            CheckResult(
                group=group,
                name="Developer Mode",
                status=CheckStatus.ACTION_REQUIRED,
                detail="disabled",
                remediation=(
                    "Enable on device: Settings > Privacy & Security > "
                    "Developer Mode, then reboot."
                ),
            )
        )
    else:
        state = "enabled" if device.developer_mode_enabled else "unknown"
        results.append(
            CheckResult(
                group=group, name="Developer Mode", status=CheckStatus.OK, detail=state
            )
        )

    results.append(
        CheckResult(
            group=group,
            name="Connection",
            status=CheckStatus.OK if device.available else CheckStatus.WARN,
            detail=device.connection.value,
            remediation=(
                None
                if device.connection.value == "usb"
                else "USB is recommended for iproxy port-forwarding."
            ),
        )
    )

    results.append(
        CheckResult(
            group=group,
            name="Cert trust",
            status=CheckStatus.WARN,
            detail="cannot be detected until first install",
            remediation=(
                "After the first install, trust the certificate on device: "
                "Settings > General > VPN & Device Management."
            ),
        )
    )
    return results


def build_report(ctx: DoctorContext) -> DoctorReport:
    results: list[CheckResult] = [
        check_xcode(ctx),
        check_signing(ctx),
        check_devices(ctx),
        check_port_forwarding(ctx),
        check_wda_build(ctx),
        check_wda_server(ctx),
    ]
    for device in _target_devices(ctx):
        results.extend(device_checks(ctx, device))
    return DoctorReport(results=results)


def _default_probe(base_url: str) -> Callable[[], bool]:
    def probe() -> bool:
        try:
            with WdaClient(base_url) as client:
                return client.status().ready
        except WdaError:
            return False

    return probe


def build_default_context(
    *,
    base_url: str,
    target_udid: str | None = None,
    configured_team_id: str | None = None,
) -> DoctorContext:
    runner = SubprocessRunner()
    registry = DeviceRegistry.default(runner)
    project = WdaProject(
        source_dir=DEFAULT_STATE_DIR / "WebDriverAgent",
        derived_data_dir=DEFAULT_STATE_DIR / "DerivedData",
    )
    return DoctorContext(
        runner=runner,
        devices=registry.list(),
        project=project,
        base_url=base_url,
        target_udid=target_udid,
        tool_exists=lambda name: shutil.which(name) is not None,
        wda_probe=_default_probe(base_url),
        xcode_teams=load_xcode_teams(),
        configured_team_id=configured_team_id,
    )
