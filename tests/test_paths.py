from pathlib import Path

from lazyworker.config import Config
from lazyworker.paths import HOME_DIR, home_dir, state_dir


def test_home_dir_is_global() -> None:
    assert home_dir() == HOME_DIR


def test_state_dir_anchored_to_discovered_config(tmp_path: Path) -> None:
    (tmp_path / "lazyworker.toml").write_text("[wda]\nport = 8101\n")
    assert state_dir(tmp_path) == tmp_path / ".lazyworker"


def test_state_dir_anchored_from_subdirectory(tmp_path: Path) -> None:
    (tmp_path / "lazyworker.toml").write_text("[target]\nudid = \"X\"\n")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert state_dir(nested) == tmp_path / ".lazyworker"


def test_state_dir_falls_back_to_home_without_config(tmp_path: Path) -> None:
    assert state_dir(tmp_path) == HOME_DIR


def test_config_parses_target_section(tmp_path: Path) -> None:
    config_file = tmp_path / "lazyworker.toml"
    config_file.write_text('[target]\nudid = "18DB2880"\nbundle_id = "com.x"\n')
    config = Config.load(config_file)
    assert config.target.udid == "18DB2880"
    assert config.target.bundle_id == "com.x"
