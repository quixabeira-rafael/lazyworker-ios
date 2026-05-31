from collections.abc import Sequence
from pathlib import Path

from lazyworker.bootstrap.wda import WdaProject
from lazyworker.devices.models import ConnectionType, Device, DeviceKind, DeviceState
from lazyworker.doctor.checks import (
    DoctorContext,
    build_report,
    check_port_forwarding,
    check_signing,
    device_checks,
)
from lazyworker.doctor.models import CheckStatus
from lazyworker.doctor.render import format_report
from lazyworker.doctor.signing import development_teams, parse_identities
from lazyworker.doctor.xcode import XcodeTeam, parse_provisioning_teams

SECURITY_OUTPUT = """
  1) AAAA "Apple Development: Rafael Quixabeira (23NJLMFF8P)" (CSSMERR_TP_CERT_REVOKED)
  2) BBBB "Apple Development: Rafael Quixabeira (92K8JB9444)"
  3) CCCC "Apple Development: rafael@work.com (C5AW73KQX3)"
     3 valid identities found
"""


class MappedRunner:
    def __init__(self, outputs: dict[str, str]) -> None:
        self._outputs = outputs

    def run(self, args: Sequence[str], *, timeout: float | None = None) -> str:
        for marker, value in self._outputs.items():
            if marker in args:
                return value
        raise AssertionError(f"unexpected command: {list(args)}")


def _device(
    *, dev_mode: bool | None, connection: ConnectionType = ConnectionType.NETWORK
) -> Device:
    return Device(
        udid="00008110-001928D41A44401E",
        name="iPhone de Rafael",
        kind=DeviceKind.PHYSICAL,
        state=DeviceState.CONNECTED,
        connection=connection,
        os_version="26.5",
        developer_mode_enabled=dev_mode,
    )


def _context(**overrides: object) -> DoctorContext:
    defaults: dict[str, object] = {
        "runner": MappedRunner({"find-identity": SECURITY_OUTPUT, "xcodebuild": "Xcode 26.5"}),
        "devices": [_device(dev_mode=True)],
        "project": WdaProject(source_dir=Path("/nope/WDA"), derived_data_dir=Path("/nope/dd")),
        "base_url": "http://127.0.0.1:8100",
        "target_udid": None,
        "tool_exists": lambda name: True,
        "wda_probe": lambda: False,
        "xcode_teams": [
            XcodeTeam(account="acc", team_id="DDWF7736HG", name="Personal Team", is_free=True)
        ],
        "configured_team_id": None,
    }
    defaults.update(overrides)
    return DoctorContext(**defaults)  # type: ignore[arg-type]


def test_parse_identities_extracts_team_and_revoked() -> None:
    identities = parse_identities(SECURITY_OUTPUT)
    assert len(identities) == 3
    assert identities[0].revoked is True
    assert identities[0].team_id == "23NJLMFF8P"
    assert identities[1].revoked is False
    assert identities[1].team_id == "92K8JB9444"


def test_development_teams_skips_revoked() -> None:
    teams = development_teams(parse_identities(SECURITY_OUTPUT))
    assert teams == ["92K8JB9444", "C5AW73KQX3"]


def test_check_signing_ok_with_xcode_account() -> None:
    result = check_signing(_context())
    assert result.status == CheckStatus.OK
    assert "DDWF7736HG" in result.detail
    assert "free" in result.detail


def test_check_signing_configured_team_not_in_xcode() -> None:
    result = check_signing(_context(configured_team_id="92K8JB9444"))
    assert result.status == CheckStatus.ACTION_REQUIRED
    assert "92K8JB9444" in result.detail
    assert "DDWF7736HG" in (result.remediation or "")


def test_check_signing_certs_present_but_no_xcode_account() -> None:
    result = check_signing(_context(xcode_teams=[]))
    assert result.status == CheckStatus.ACTION_REQUIRED
    assert "no Apple ID in Xcode" in result.detail
    assert "Accounts" in (result.remediation or "")


def test_check_signing_action_when_nothing() -> None:
    only_revoked = '  1) AAAA "Apple Development: X (23NJLMFF8P)" (CSSMERR_TP_CERT_REVOKED)\n'
    result = check_signing(
        _context(xcode_teams=[], runner=MappedRunner({"find-identity": only_revoked}))
    )
    assert result.status == CheckStatus.ACTION_REQUIRED
    assert "no Apple ID signed into Xcode" in result.detail


def test_parse_provisioning_teams() -> None:
    prefs = {
        "IDEProvisioningTeamByIdentifier": {
            "acc-uuid": [
                {
                    "teamID": "L8JB45GSEN",
                    "teamName": "News UK & Ireland Limited",
                    "teamType": "Company",
                    "isFreeProvisioningTeam": False,
                },
                {
                    "teamID": "DDWF7736HG",
                    "teamName": "Personal Team",
                    "teamType": "Personal Team",
                    "isFreeProvisioningTeam": True,
                },
            ]
        }
    }
    teams = parse_provisioning_teams(prefs)
    assert [t.team_id for t in teams] == ["L8JB45GSEN", "DDWF7736HG"]
    assert teams[1].is_free is True
    assert teams[0].account == "acc-uuid"


def test_parse_provisioning_teams_empty() -> None:
    assert parse_provisioning_teams({}) == []


def test_check_port_forwarding_missing() -> None:
    result = check_port_forwarding(_context(tool_exists=lambda name: False))
    assert result.status == CheckStatus.ACTION_REQUIRED
    assert "libimobiledevice" in (result.remediation or "")


def test_developer_mode_disabled_is_action() -> None:
    device = _device(dev_mode=False)
    results = device_checks(_context(devices=[device]), device)
    dev_mode = next(r for r in results if r.name == "Developer Mode")
    assert dev_mode.status == CheckStatus.ACTION_REQUIRED


def test_build_report_collects_blocking_and_next_steps() -> None:
    ctx = _context(tool_exists=lambda name: False, devices=[_device(dev_mode=False)])
    report = build_report(ctx)

    assert any(r.name == "Port forwarding" for r in report.blocking)
    assert any(r.name == "Developer Mode" for r in report.blocking)
    steps = report.next_steps
    assert steps[0].status == CheckStatus.ACTION_REQUIRED


def test_format_report_lists_next_steps() -> None:
    report = build_report(_context(tool_exists=lambda name: False))
    rendered = format_report(report)
    assert "Next steps:" in rendered
    assert "[manual]" in rendered
