import base64

import pytest
import typer
from pytest_httpx import HTTPXMock
from typer.testing import CliRunner

from lazyworker.cli import _signing_options, app
from lazyworker.config import Config, SigningConfig, SigningMode

runner = CliRunner()
BASE = "http://127.0.0.1:8100"


def test_cli_status_ok(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/status",
        json={"value": {"ready": True, "os": {"name": "iOS", "version": "17.0"}}},
    )
    result = runner.invoke(app, ["status", "--base-url", BASE])
    assert result.exit_code == 0
    assert '"ready": true' in result.stdout


def test_cli_status_error_exits_nonzero(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/status",
        status_code=500,
        json={"value": {"error": "x", "message": "boom"}},
    )
    result = runner.invoke(app, ["status", "--base-url", BASE])
    assert result.exit_code == 1


def test_cli_source_malformed_value_exits_cleanly(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}/source?format=json", json={"sessionId": "x"})
    result = runner.invoke(app, ["source", "--base-url", BASE])
    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_cli_screenshot_writes_file(httpx_mock: HTTPXMock, tmp_path) -> None:
    raw = base64.b64encode(b"\x89PNG\r\n").decode()
    httpx_mock.add_response(url=f"{BASE}/screenshot", json={"value": raw})
    out = tmp_path / "shot.png"
    result = runner.invoke(app, ["screenshot", "--base-url", BASE, "-o", str(out)])
    assert result.exit_code == 0
    assert out.read_bytes() == b"\x89PNG\r\n"


def test_signing_options_requires_team() -> None:
    config = Config(signing=SigningConfig(mode=SigningMode.FREE, team_id=None))
    with pytest.raises(typer.Exit):
        _signing_options(config)


def test_signing_options_builds_runner_bundle_id() -> None:
    config = Config(signing=SigningConfig(mode=SigningMode.FREE, team_id="ABC1234567"))
    options = _signing_options(config)
    assert options.team_id == "ABC1234567"
    assert options.runner_bundle_id.endswith(".WebDriverAgentRunner")
