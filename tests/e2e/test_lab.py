"""End-to-end cases: each event the `lazyworker ui` layer drives, asserted via the lab's
`event-log` node. Requires LAZYWORKER_E2E=1 + a booted simulator with WDA and the lab app.
"""

from __future__ import annotations

from tests.e2e.conftest import event_log, goto, is_visible, node_by_id, run


def test_tap_by_identifier(lab: None) -> None:
    goto("link-tap")
    code, result = run("ui", "tap", "--identifier", "btn-primary")
    assert code == 0 and result["ok"]
    assert event_log() == "tap:btn-primary"


def test_tap_by_label_and_type(lab: None) -> None:
    goto("link-tap")
    code, result = run("ui", "tap", "--label", "Secondary", "--type", "Button")
    assert code == 0 and result["ok"]
    assert event_log() == "tap:btn-secondary"


def test_double_tap(lab: None) -> None:
    goto("link-gesture")
    code, result = run("ui", "double-tap", "--identifier", "btn-gesture")
    assert code == 0 and result["ok"]
    assert event_log() == "double_tap:btn-gesture"


def test_long_press(lab: None) -> None:
    goto("link-gesture")
    code, result = run("ui", "long-press", "--identifier", "btn-gesture", "--duration", "0.8")
    assert code == 0 and result["ok"]
    assert event_log() == "long_press:btn-gesture"


def test_toggle_switch(lab: None) -> None:
    goto("link-toggle")
    code, result = run("ui", "tap", "--identifier", "switch-1")
    assert code == 0 and result["ok"]
    assert event_log() == "toggled:switch-1=on"


def test_type_into_textfield(lab: None) -> None:
    goto("link-type")
    code, result = run("ui", "type", "--text", "hello", "--identifier", "field-name")
    assert code == 0 and result["ok"]
    assert event_log() == "typed:hello"


def test_clear_then_secure(lab: None) -> None:
    goto("link-type")
    run("ui", "type", "--text", "hello", "--identifier", "field-name")
    code, _ = run("ui", "tap", "--identifier", "btn-clear-name")
    assert code == 0
    assert event_log() == "cleared:field-name"
    run("ui", "type", "--text", "abcde", "--identifier", "field-secret")
    assert event_log() == "typed_secure:5"


def test_scroll_to_far_row(lab: None) -> None:
    goto("link-scrollto")
    code, result = run("ui", "scroll-to", "--identifier", "row-50")
    assert code == 0 and result["ok"]
    assert event_log() == "scrolled_to:row-50"


def test_scroll_down_reveals_marker(lab: None) -> None:
    goto("link-scroll")
    assert is_visible("marker-top")
    assert not is_visible("marker-bottom")
    code, result = run("ui", "scroll", "--direction", "down")
    assert code == 0 and result["ok"]
    assert is_visible("marker-bottom")
    assert not is_visible("marker-top")


def test_ambiguity_then_index(lab: None) -> None:
    goto("link-ambiguity")
    code, result = run("ui", "tap", "--label", "Twin", "--type", "Button")
    assert code == 21
    assert result["error_code"] == "ambiguous"
    assert result["candidate_count"] == 2

    code, result = run("ui", "tap", "--label", "Twin", "--type", "Button", "--index", "0")
    assert code == 0 and result["ok"]
    assert event_log() == "tap:twin#1"


def test_batch_login_flow(lab: None) -> None:
    goto("link-batch")
    ops = (
        '[{"op":"tap","identifier":"field-user"},'
        '{"op":"type","text":"sam","identifier":"field-user"},'
        '{"op":"tap","identifier":"field-pass"},'
        '{"op":"type","text":"pw","identifier":"field-pass"},'
        '{"op":"tap","identifier":"btn-submit"}]'
    )
    code, report = run("ui", "batch", stdin=ops)
    assert code == 0
    assert report["ok"] and report["ran"] == 5
    assert event_log() == "submitted:login=ok"


def test_screenshot(lab: None, tmp_path: object) -> None:
    import pathlib

    goto("link-screenshot")
    out = pathlib.Path("/tmp/lwlab_screenshot.png")
    code, result = run("ui", "screenshot", "-o", str(out))
    assert code == 0 and result["ok"]
    assert out.exists() and out.stat().st_size > 1000
    assert node_by_id("screenshot-marker") is not None
