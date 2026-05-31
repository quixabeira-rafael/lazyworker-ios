from pathlib import Path

from lazyworker.config import Config


def test_defaults_when_no_file() -> None:
    config = Config.load(Path("/nonexistent/lazyworker.toml"))
    assert config.wda.base_url == "http://127.0.0.1:8100"
    assert config.wda.port == 8100
    assert config.signing.bundle_id_prefix == "com.lazyworker.wda"
    assert config.signing.team_id is None


def test_load_from_file(tmp_path: Path) -> None:
    config_file = tmp_path / "lazyworker.toml"
    config_file.write_text(
        "\n".join(
            [
                "[signing]",
                'team_id = "ABCDE12345"',
                "",
                "[wda]",
                "port = 9100",
                'base_url = "http://127.0.0.1:9100"',
            ]
        )
    )
    config = Config.load(config_file)
    assert config.signing.team_id == "ABCDE12345"
    assert config.wda.port == 9100
    assert config.wda.base_url == "http://127.0.0.1:9100"


def test_discover_walks_up(tmp_path: Path) -> None:
    (tmp_path / "lazyworker.toml").write_text("[wda]\nport = 7000\n")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    found = Config.discover(nested)
    assert found == tmp_path / "lazyworker.toml"
