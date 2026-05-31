from __future__ import annotations

import re
from dataclasses import dataclass

from lazyworker.devices.runner import CommandRunner

_IDENTITY_LINE = re.compile(
    r'^\s*\d+\)\s+(?P<fingerprint>[0-9A-Fa-f]+)\s+"(?P<name>[^"]+)"(?P<tail>.*)$'
)
_TEAM_ID = re.compile(r"\(([0-9A-Z]{10})\)")


@dataclass
class SigningIdentity:
    fingerprint: str
    name: str
    team_id: str | None
    revoked: bool


def parse_identities(output: str) -> list[SigningIdentity]:
    identities: list[SigningIdentity] = []
    for line in output.splitlines():
        match = _IDENTITY_LINE.match(line)
        if match is None:
            continue
        name = match.group("name")
        team_match = _TEAM_ID.search(name)
        identities.append(
            SigningIdentity(
                fingerprint=match.group("fingerprint"),
                name=name,
                team_id=team_match.group(1) if team_match else None,
                revoked="REVOKED" in match.group("tail").upper(),
            )
        )
    return identities


def list_identities(runner: CommandRunner) -> list[SigningIdentity]:
    """Return signing identities, or raise on missing/failing ``security``."""
    output = runner.run(["security", "find-identity", "-v", "-p", "codesigning"])
    return parse_identities(output)


def development_teams(identities: list[SigningIdentity]) -> list[str]:
    """Distinct, non-revoked Apple Development team ids, preserving order."""
    teams: list[str] = []
    for identity in identities:
        if identity.revoked or "Apple Development" not in identity.name:
            continue
        if identity.team_id and identity.team_id not in teams:
            teams.append(identity.team_id)
    return teams
