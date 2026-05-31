from __future__ import annotations

from lazyworker.doctor.models import CheckStatus, DoctorReport

_SYMBOLS = {
    CheckStatus.OK: "OK ",
    CheckStatus.WARN: "!  ",
    CheckStatus.ACTION_REQUIRED: "X  ",
    CheckStatus.UNAVAILABLE: "?  ",
}


def format_report(report: DoctorReport) -> str:
    lines: list[str] = []
    groups: list[str] = []
    for result in report.results:
        if result.group not in groups:
            groups.append(result.group)

    for group in groups:
        lines.append(group)
        for result in report.results:
            if result.group != group:
                continue
            symbol = _SYMBOLS[result.status]
            lines.append(f"  {symbol} {result.name:<16} {result.detail}")
        lines.append("")

    steps = report.next_steps
    if steps:
        lines.append("Next steps:")
        for index, result in enumerate(steps, start=1):
            tag = "[manual] " if result.status == CheckStatus.ACTION_REQUIRED else ""
            lines.append(f"  {index}. {tag}{result.remediation}")
    else:
        lines.append("All checks passed.")

    return "\n".join(lines).rstrip() + "\n"
