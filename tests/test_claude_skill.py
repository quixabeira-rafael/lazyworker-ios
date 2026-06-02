from __future__ import annotations

from pathlib import Path

from lazyworker import claude_skill
from lazyworker.claude_skill import ClaudeSkillPaths


def _paths(tmp_path: Path) -> ClaudeSkillPaths:
    return ClaudeSkillPaths.for_user(home=tmp_path)


def _source(tmp_path: Path) -> Path:
    src = tmp_path / "repo" / "SKILL.md"
    src.parent.mkdir(parents=True)
    src.write_text("---\nname: lazyworker\n---\n")
    return src


def test_install_creates_managed_symlink(tmp_path: Path) -> None:
    paths, src = _paths(tmp_path), _source(tmp_path)
    result = claude_skill.install(paths=paths, source=src)
    assert result.installed and not result.replaced_existing
    assert paths.user_skill_file.is_symlink()
    assert paths.user_skill_file.resolve() == src.resolve()


def test_status_reports_managed_symlink(tmp_path: Path) -> None:
    paths, src = _paths(tmp_path), _source(tmp_path)
    claude_skill.install(paths=paths, source=src)
    st = claude_skill.status(paths=paths, source=src)
    assert st.installed and st.is_managed_symlink
    assert st.points_to == src


def test_install_is_idempotent_and_replaces(tmp_path: Path) -> None:
    paths, src = _paths(tmp_path), _source(tmp_path)
    claude_skill.install(paths=paths, source=src)
    again = claude_skill.install(paths=paths, source=src)
    assert again.installed and again.replaced_existing


def test_uninstall_removes_managed_symlink(tmp_path: Path) -> None:
    paths, src = _paths(tmp_path), _source(tmp_path)
    claude_skill.install(paths=paths, source=src)
    result = claude_skill.uninstall(paths=paths, source=src)
    assert result.removed and not paths.user_skill_file.exists()


def test_uninstall_leaves_unmanaged_file_alone(tmp_path: Path) -> None:
    paths, src = _paths(tmp_path), _source(tmp_path)
    paths.user_skill_dir.mkdir(parents=True)
    paths.user_skill_file.write_text("hand-written, not ours")  # a real file, not our symlink
    result = claude_skill.uninstall(paths=paths, source=src)
    assert not result.removed and result.skipped_unmanaged
    assert paths.user_skill_file.exists()


def test_install_without_source_is_skipped(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    result = claude_skill.install(paths=paths, source=tmp_path / "missing" / "SKILL.md")
    assert not result.installed and result.skipped_reason
