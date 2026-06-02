"""Install/uninstall the lazyworker Claude skill as a managed symlink.

`~/.claude/skills/lazyworker/SKILL.md` is symlinked to the repo's
`.claude/skills/lazyworker/SKILL.md`, so the skill tracks the checked-out source
(this requires an editable install: `pipx install -e .`).
"""
from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from pathlib import Path

import lazyworker

SKILL_NAME = "lazyworker"


@dataclass(frozen=True)
class ClaudeSkillPaths:
    user_skills_dir: Path

    @property
    def user_skill_dir(self) -> Path:
        return self.user_skills_dir / SKILL_NAME

    @property
    def user_skill_file(self) -> Path:
        return self.user_skill_dir / "SKILL.md"

    @classmethod
    def for_user(cls, home: Path | None = None) -> ClaudeSkillPaths:
        base = home or Path.home()
        return cls(user_skills_dir=base / ".claude" / "skills")


def source_skill_path() -> Path | None:
    """The SKILL.md shipped in the repo, found relative to the installed package."""
    try:
        package_dir = Path(lazyworker.__file__).resolve().parent
    except (AttributeError, TypeError):
        return None
    candidate = package_dir.parent.parent / ".claude" / "skills" / SKILL_NAME / "SKILL.md"
    return candidate if candidate.exists() else None


def _is_managed_symlink(target: Path, source: Path | None) -> bool:
    if not target.is_symlink() or source is None:
        return False
    try:
        link_dest = Path(os.readlink(target))
        if not link_dest.is_absolute():
            link_dest = (target.parent / link_dest).resolve()
        return link_dest.resolve() == source.resolve()
    except OSError:
        return False


@dataclass(frozen=True)
class InstallResult:
    skill_file: Path
    source_file: Path | None
    installed: bool
    replaced_existing: bool
    skipped_reason: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "skill_file": str(self.skill_file),
            "source_file": str(self.source_file) if self.source_file else None,
            "installed": self.installed,
            "replaced_existing": self.replaced_existing,
            "skipped_reason": self.skipped_reason,
        }


def install(
    *, paths: ClaudeSkillPaths | None = None, source: Path | None = None
) -> InstallResult:
    paths = paths or ClaudeSkillPaths.for_user()
    src = source if source is not None else source_skill_path()
    if src is None or not src.exists():
        return InstallResult(
            skill_file=paths.user_skill_file, source_file=src, installed=False,
            replaced_existing=False,
            skipped_reason="source SKILL.md not found (install editable: pipx install -e .)",
        )
    paths.user_skill_dir.mkdir(parents=True, exist_ok=True)
    target = paths.user_skill_file
    replaced = target.exists() or target.is_symlink()
    if replaced:
        target.unlink()
    target.symlink_to(src)
    return InstallResult(
        skill_file=target, source_file=src, installed=True, replaced_existing=replaced,
        skipped_reason=None,
    )


@dataclass(frozen=True)
class UninstallResult:
    skill_file: Path
    removed: bool
    skipped_unmanaged: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "skill_file": str(self.skill_file),
            "removed": self.removed,
            "skipped_unmanaged": self.skipped_unmanaged,
        }


def uninstall(
    *, paths: ClaudeSkillPaths | None = None, source: Path | None = None
) -> UninstallResult:
    paths = paths or ClaudeSkillPaths.for_user()
    src = source if source is not None else source_skill_path()
    target = paths.user_skill_file
    if not (target.exists() or target.is_symlink()):
        return UninstallResult(skill_file=target, removed=False, skipped_unmanaged=False)
    if not _is_managed_symlink(target, src):
        return UninstallResult(skill_file=target, removed=False, skipped_unmanaged=True)
    target.unlink()
    with contextlib.suppress(OSError):
        paths.user_skill_dir.rmdir()
    return UninstallResult(skill_file=target, removed=True, skipped_unmanaged=False)


@dataclass(frozen=True)
class SkillStatus:
    skill_file: Path
    source_file: Path | None
    installed: bool
    is_managed_symlink: bool
    points_to: Path | None

    def to_dict(self) -> dict[str, object]:
        return {
            "skill_file": str(self.skill_file),
            "source_file": str(self.source_file) if self.source_file else None,
            "installed": self.installed,
            "is_managed_symlink": self.is_managed_symlink,
            "points_to": str(self.points_to) if self.points_to else None,
        }


def status(
    *, paths: ClaudeSkillPaths | None = None, source: Path | None = None
) -> SkillStatus:
    paths = paths or ClaudeSkillPaths.for_user()
    src = source if source is not None else source_skill_path()
    target = paths.user_skill_file
    points_to: Path | None = None
    if target.is_symlink():
        try:
            points_to = Path(os.readlink(target))
        except OSError:
            points_to = None
    return SkillStatus(
        skill_file=target, source_file=src,
        installed=target.exists() or target.is_symlink(),
        is_managed_symlink=_is_managed_symlink(target, src), points_to=points_to,
    )
