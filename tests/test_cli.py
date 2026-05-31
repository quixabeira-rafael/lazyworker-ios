import base64
import json
from pathlib import Path
from typing import Any

import pytest
import typer
from pytest_httpx import HTTPXMock
from typer.testing import CliRunner

from lazyworker.cli import _signing_options, app
from lazyworker.config import Config, SigningConfig, SigningMode
from lazyworker.interaction.state import SessionState, load_session_state, save_session_state

runner = CliRunner()
BASE = "http://127.0.0.1:8100"

BUTTON = {
    "type": "Button",
    "label": "Login",
    "rect": {"x": 100, "y": 200, "width": 100, "height": 40},
    "isVisible": True,
    "children": [],
}


def _tree(children: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "value": {
            "type": "Application",
            "rect": {"x": 0, "y": 0, "width": 400, "height": 800},
            "isVisible": True,
            "children": children,
        }
    }


def _use_state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("lazyworker.cli.DEFAULT_STATE_DIR", tmp_path)


def _seed_session(tmp_path: Path) -> None:
    save_session_state(
        SessionState(session_id="S1", bundle_id="com.x", base_url=BASE), tmp_path
    )


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


def test_ui_tap_without_session_exits_no_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _use_state_dir(monkeypatch, tmp_path)
    result = runner.invoke(app, ["ui", "tap", "--label", "X"])
    assert result.exit_code == 10
    assert '"no_session"' in result.stdout


def test_ui_tap_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    _use_state_dir(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    httpx_mock.add_response(url=f"{BASE}/source?format=json", json=_tree([BUTTON]))
    httpx_mock.add_response(url=f"{BASE}/session/S1/actions", method="POST", json={"value": None})
    result = runner.invoke(app, ["ui", "tap", "--label", "Login"])
    assert result.exit_code == 0
    assert '"ok": true' in result.stdout


def test_ui_tap_ambiguous_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    _use_state_dir(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    httpx_mock.add_response(url=f"{BASE}/source?format=json", json=_tree([BUTTON, BUTTON]))
    result = runner.invoke(app, ["ui", "tap", "--label", "Login"])
    assert result.exit_code == 21
    assert '"ambiguous"' in result.stdout


def test_ui_tap_dry_run_sends_no_gesture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    _use_state_dir(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    httpx_mock.add_response(url=f"{BASE}/source?format=json", json=_tree([BUTTON]))
    result = runner.invoke(app, ["ui", "tap", "--label", "Login", "--dry-run"])
    assert result.exit_code == 0
    assert '"dry_run": true' in result.stdout
    assert all("/actions" not in req.url.path for req in httpx_mock.get_requests())


def test_ui_open_persists_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    _use_state_dir(monkeypatch, tmp_path)
    httpx_mock.add_response(
        url=f"{BASE}/session", method="POST", json={"sessionId": "NEW", "value": {}}
    )
    httpx_mock.add_response(
        url=f"{BASE}/session/NEW/appium/settings", method="POST", json={"value": {}}
    )
    result = runner.invoke(app, ["ui", "open", "com.apple.Preferences", "--base-url", BASE])
    assert result.exit_code == 0
    state = load_session_state(tmp_path)
    assert state is not None and state.session_id == "NEW"


def test_ui_batch_via_stdin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    _use_state_dir(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    httpx_mock.add_response(url=f"{BASE}/source?format=json", json=_tree([BUTTON]))
    httpx_mock.add_response(url=f"{BASE}/session/S1/actions", method="POST", json={"value": None})
    httpx_mock.add_response(url=f"{BASE}/source?format=json", json=_tree([]))
    httpx_mock.add_response(url=f"{BASE}/session/S1/actions", method="POST", json={"value": None})
    ops = '[{"op": "tap", "label": "Login"}, {"op": "scroll", "direction": "down"}]'
    result = runner.invoke(app, ["ui", "batch"], input=ops)
    assert result.exit_code == 0
    assert '"ok": true' in result.stdout


def test_ui_screen_outputs_description(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    _use_state_dir(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    png = base64.b64encode(b"\x89PNG\r\n").decode()
    httpx_mock.add_response(url=f"{BASE}/screenshot", json={"value": png})
    httpx_mock.add_response(url=f"{BASE}/source?format=json", json=_tree([BUTTON]))
    out = tmp_path / "screen.png"
    result = runner.invoke(app, ["ui", "screen", "-o", str(out)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["screenshot"] == str(out)
    assert data["width"] == 400 and data["height"] == 800
    assert any(e.get("text") == "Login" for e in data["elements"])
    assert out.read_bytes() == b"\x89PNG\r\n"


def test_ui_batch_stop_on_error_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    _use_state_dir(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    httpx_mock.add_response(url=f"{BASE}/source?format=json", json=_tree([]))
    result = runner.invoke(app, ["ui", "batch"], input='[{"op": "tap", "label": "Missing"}]')
    assert result.exit_code == 20
    assert '"stopped_on": 0' in result.stdout
