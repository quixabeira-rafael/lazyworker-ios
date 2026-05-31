from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class CheckStatus(StrEnum):
    OK = "ok"
    WARN = "warn"
    ACTION_REQUIRED = "action_required"
    UNAVAILABLE = "unavailable"


class CheckResult(BaseModel):
    """Outcome of a single preflight check."""

    group: str
    name: str
    status: CheckStatus
    detail: str
    remediation: str | None = None


class DoctorReport(BaseModel):
    """Aggregated preflight results."""

    results: list[CheckResult]

    @property
    def blocking(self) -> list[CheckResult]:
        return [
            r
            for r in self.results
            if r.status in (CheckStatus.ACTION_REQUIRED, CheckStatus.UNAVAILABLE)
        ]

    @property
    def next_steps(self) -> list[CheckResult]:
        """Non-OK results that carry a remediation, ordered by severity."""
        severity = {
            CheckStatus.ACTION_REQUIRED: 0,
            CheckStatus.UNAVAILABLE: 1,
            CheckStatus.WARN: 2,
        }
        actionable = [r for r in self.results if r.status != CheckStatus.OK and r.remediation]
        return sorted(actionable, key=lambda r: severity.get(r.status, 3))
