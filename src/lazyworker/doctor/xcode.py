from __future__ import annotations

import plistlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

XCODE_PREFS = Path.home() / "Library" / "Preferences" / "com.apple.dt.Xcode.plist"


@dataclass
class XcodeTeam:
    account: str
    team_id: str | None
    name: str | None = None
    team_type: str | None = None
    is_free: bool = False


def parse_provisioning_teams(prefs: dict[str, Any]) -> list[XcodeTeam]:
    """Extract the teams of every account signed into Xcode.

    Xcode 15+ stores them under ``IDEProvisioningTeamByIdentifier``; older
    versions used ``IDEProvisioningTeams``.
    """
    accounts = prefs.get("IDEProvisioningTeamByIdentifier")
    if not isinstance(accounts, dict):
        accounts = prefs.get("IDEProvisioningTeams")
    if not isinstance(accounts, dict):
        return []

    teams: list[XcodeTeam] = []
    for account, entries in accounts.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            teams.append(
                XcodeTeam(
                    account=str(account),
                    team_id=entry.get("teamID"),
                    name=entry.get("teamName"),
                    team_type=entry.get("teamType"),
                    is_free=bool(entry.get("isFreeProvisioningTeam", False)),
                )
            )
    return teams


def load_xcode_prefs(path: Path | None = None) -> dict[str, Any]:
    target = path or XCODE_PREFS
    if not target.exists():
        return {}
    with target.open("rb") as handle:
        loaded = plistlib.load(handle)
    return loaded if isinstance(loaded, dict) else {}


def load_xcode_teams(path: Path | None = None) -> list[XcodeTeam]:
    return parse_provisioning_teams(load_xcode_prefs(path))
