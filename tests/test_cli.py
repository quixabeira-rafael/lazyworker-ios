import base64
import json
from pathlib import Path
from typing import Any

import pytest
import typer
from pytest_httpx import HTTPXMock
from typer.testing import CliRunner

from lazyworker.cli import _apply_jq, _attach_wait_artifact, _build_wait, _signing_options, app
from lazyworker.config import Config, SigningConfig, SigningMode
from lazyworker.interaction.models import (
    Action,
    ErrorCode,
    OperationResult,
    SettleStrategy,
    WaitMode,
)
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
    monkeypatch.setattr("lazyworker.cli._state_dir", lambda: tmp_path)


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


def test_ui_find_jq_filters_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    _use_state_dir(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    httpx_mock.add_response(url=f"{BASE}/source?format=json", json=_tree([BUTTON]))
    result = runner.invoke(app, ["ui", "find", "login", "--jq", ".matches[].label"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "Login"  # raw label, filtered by jq


def test_ui_find_no_args_returns_screen_overview(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    _use_state_dir(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    httpx_mock.add_response(url=f"{BASE}/source?format=json", json=_tree([BUTTON]))
    result = runner.invoke(app, ["ui", "find"])
    assert result.exit_code == 0  # no longer an error
    data = json.loads(result.stdout)
    assert data["count"] == 1
    assert data["matches"][0]["label"] == "Login"
    assert data["matches"][0]["tips"]  # complete command tips included
    assert "no query given" in data["hint"]


def test_ui_schema_text_lists_fields_and_types() -> None:
    result = runner.invoke(app, ["ui", "schema"])
    assert result.exit_code == 0
    assert "identifier" in result.stdout
    assert "Button" in result.stdout
    assert "accessibilityLabel" in result.stdout


def test_ui_schema_json_is_structured() -> None:
    result = runner.invoke(app, ["ui", "schema", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    names = {field["name"] for field in doc["node_fields"]}
    assert {"type", "identifier", "label", "value", "rect", "visible"} <= names
    flat = [t for group in doc["element_types"].values() for t in group]
    assert "Button" in flat and "StaticText" in flat


def test_build_wait_none() -> None:
    assert _build_wait(Action.TAP, None, None, None, 5.0, 2, 0.4) is None


def test_build_wait_env_default_applies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAZYWORKER_DEFAULT_WAIT", "settle")
    spec = _build_wait(Action.TAP, None, None, None, 5.0, 2, 0.4)
    assert spec is not None and spec.mode == WaitMode.SETTLE
    assert spec.strategy == SettleStrategy.STRICT


def test_build_wait_explicit_overrides_env_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAZYWORKER_DEFAULT_WAIT", "settle")
    spec = _build_wait(Action.TAP, "tree", None, None, 5.0, 2, 0.4)
    assert spec is not None and spec.mode == WaitMode.TREE


def test_build_wait_none_opts_out_of_env_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAZYWORKER_DEFAULT_WAIT", "settle")
    assert _build_wait(Action.TAP, "none", None, None, 5.0, 2, 0.4) is None


def test_build_wait_diff_tree() -> None:
    spec = _build_wait(Action.TAP, "tree", None, None, 5.0, 2, 0.4)
    assert spec is not None and spec.mode == WaitMode.TREE


def test_build_wait_until_predicate() -> None:
    spec = _build_wait(Action.TAP, None, "label=Home", None, 5.0, 2, 0.4)
    assert spec is not None and spec.mode == WaitMode.UNTIL
    assert spec.locator is not None and spec.locator.label == "Home"


def test_build_wait_gone_predicate_by_id() -> None:
    spec = _build_wait(Action.TAP, None, None, "id=spinner", 5.0, 2, 0.4)
    assert spec is not None and spec.mode == WaitMode.GONE
    assert spec.locator is not None and spec.locator.identifier == "spinner"


def test_build_wait_invalid_predicate_exits() -> None:
    with pytest.raises(typer.Exit):
        _build_wait(Action.TAP, None, "garbage", None, 5.0, 2, 0.4)


def test_build_wait_invalid_mode_exits() -> None:
    with pytest.raises(typer.Exit):
        _build_wait(Action.TAP, "nope", None, None, 5.0, 2, 0.4)


def test_apply_jq_filters_and_raw_strings(capsys) -> None:
    with pytest.raises(typer.Exit) as exc:
        _apply_jq(Action.FIND, '{"count": 2, "matches": [{"label": "Menu"}]}', ".matches[].label")
    assert exc.value.exit_code == 0
    assert capsys.readouterr().out.strip() == "Menu"  # raw, no quotes (-r)


def test_apply_jq_invalid_program_exits_nonzero(capsys) -> None:
    with pytest.raises(typer.Exit) as exc:
        _apply_jq(Action.FIND, "{}", "this is not valid |||")
    assert exc.value.exit_code == 30  # invalid_target
    assert "jq" in capsys.readouterr().out


class _ShotInteractor:
    def __init__(self, data: bytes = b"\x89PNG\r\n") -> None:
        self.captured = 0
        self._data = data

    def screenshot(self) -> bytes:
        self.captured += 1
        return self._data


def test_attach_wait_artifact_saves_on_no_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("lazyworker.cli._state_dir", lambda: tmp_path)
    interactor = _ShotInteractor()
    result = OperationResult.failure(Action.TAP, ErrorCode.NO_CHANGE, "no observed change")
    out = _attach_wait_artifact(interactor, result, True)  # type: ignore[arg-type]
    assert out.screenshot is not None
    assert Path(out.screenshot).read_bytes() == b"\x89PNG\r\n"
    assert out.message is not None and "saved screenshot" in out.message


def test_attach_wait_artifact_skips_when_ok(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("lazyworker.cli._state_dir", lambda: tmp_path)
    interactor = _ShotInteractor()
    out = _attach_wait_artifact(interactor, OperationResult.success(Action.TAP), True)  # type: ignore[arg-type]
    assert out.screenshot is None and interactor.captured == 0


def test_attach_wait_artifact_skips_when_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("lazyworker.cli._state_dir", lambda: tmp_path)
    interactor = _ShotInteractor()
    result = OperationResult.failure(Action.TAP, ErrorCode.NO_CHANGE, "no observed change")
    out = _attach_wait_artifact(interactor, result, False)  # type: ignore[arg-type]
    assert out.screenshot is None and interactor.captured == 0


def test_ui_screen_with_ocr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    from lazyworker.interaction.ocr import OcrText

    _use_state_dir(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    monkeypatch.setattr(
        "lazyworker.cli.recognize",
        lambda *a, **k: [OcrText(text="DRAWN", box=(1, 2, 3, 4), size=(3, 4), confidence=0.99)],
    )
    png = base64.b64encode(b"\x89PNG\r\n").decode()
    httpx_mock.add_response(url=f"{BASE}/screenshot", json={"value": png})
    httpx_mock.add_response(url=f"{BASE}/source?format=json", json=_tree([BUTTON]))
    out = tmp_path / "screen.png"
    result = runner.invoke(app, ["ui", "screen", "--ocr", "-o", str(out)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ocr"][0]["text"] == "DRAWN"
    assert data["ocr"][0]["confidence"] == 0.99


def test_ui_screen_with_detect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    from lazyworker.interaction.detect import DetectedElement

    _use_state_dir(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    monkeypatch.setattr(
        "lazyworker.cli.detect",
        lambda *a, **k: [
            DetectedElement(label="back arrow", box=(1, 2, 3, 4), size=(3, 4), confidence=0.9)
        ],
    )
    png = base64.b64encode(b"\x89PNG\r\n").decode()
    httpx_mock.add_response(url=f"{BASE}/screenshot", json={"value": png})
    httpx_mock.add_response(url=f"{BASE}/source?format=json", json=_tree([BUTTON]))
    out = tmp_path / "screen.png"
    result = runner.invoke(app, ["ui", "screen", "--detect", "-o", str(out)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["detections"][0]["label"] == "back arrow"


def test_ui_batch_stop_on_error_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    _use_state_dir(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    httpx_mock.add_response(url=f"{BASE}/source?format=json", json=_tree([]))
    result = runner.invoke(app, ["ui", "batch"], input='[{"op": "tap", "label": "Missing"}]')
    assert result.exit_code == 20
    assert '"stopped_on": 0' in result.stdout


def test_ui_deeplink_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    _use_state_dir(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    httpx_mock.add_response(url=f"{BASE}/session/S1/url", method="POST", json={"value": None})
    result = runner.invoke(app, ["ui", "deeplink", "lazyworker://ping"])
    assert result.exit_code == 0
    assert '"ok": true' in result.stdout
    assert '"deeplink"' in result.stdout


def test_ui_deeplink_without_session_exits_no_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _use_state_dir(monkeypatch, tmp_path)
    result = runner.invoke(app, ["ui", "deeplink", "lazyworker://ping"])
    assert result.exit_code == 10
    assert '"no_session"' in result.stdout


def test_ui_find_query_returns_matches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    _use_state_dir(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    httpx_mock.add_response(url=f"{BASE}/source?format=json", json=_tree([BUTTON]))
    result = runner.invoke(app, ["ui", "find", "-q", "Login"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 1
    assert data["matches"][0]["label"] == "Login"


def test_ui_find_includes_tips_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    _use_state_dir(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    httpx_mock.add_response(url=f"{BASE}/source?format=json", json=_tree([BUTTON]))
    result = runner.invoke(app, ["ui", "find", "-q", "Login"])
    assert result.exit_code == 0
    tips = json.loads(result.stdout)["matches"][0]["tips"]
    assert tips and tips[0]["action"] == "tap"
    assert "lazyworker ui tap" in tips[0]["command"]


def test_ui_find_no_tips_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    _use_state_dir(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    httpx_mock.add_response(url=f"{BASE}/source?format=json", json=_tree([BUTTON]))
    result = runner.invoke(app, ["ui", "find", "-q", "Login", "--no-tips"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["matches"][0]["tips"] == []
