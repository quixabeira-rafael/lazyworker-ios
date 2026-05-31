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


def test_screen_breakdown(lab: None) -> None:
    import pathlib

    goto("link-card")
    out = pathlib.Path("/tmp/lwlab_screen.png")
    code, desc = run("ui", "screen", "-o", str(out))
    assert code == 0
    assert desc["width"] > 0 and desc["height"] > 0
    assert out.exists() and out.stat().st_size > 1000
    texts = [e.get("text") for e in desc["elements"]]
    assert "Saldo" in texts
    saldo = next(e for e in desc["elements"] if e.get("text") == "Saldo")
    assert len(saldo["box"]) == 4 and saldo["size"][0] > 0


def test_ocr_recovers_hidden_text(lab: None) -> None:
    import pathlib

    goto("link-ocr")
    out = pathlib.Path("/tmp/lwlab_ocr.png")
    code, desc = run("ui", "screen", "--ocr", "-o", str(out))
    assert code == 0
    # The text is hidden from the accessibility tree...
    tree_texts = [e.get("text") for e in desc["elements"]]
    assert not any(t and "7421" in t for t in tree_texts)
    # ...but OCR recovers it with a box and confidence.
    ocr = desc.get("ocr") or []
    hit = next((o for o in ocr if "7421" in o["text"]), None)
    assert hit is not None
    assert len(hit["box"]) == 4
    assert 0.0 <= hit["confidence"] <= 1.0


def _box_center(box: list[int]) -> tuple[int, int]:
    x, y, w, h = box
    return (x + w // 2, y + h // 2)


def test_ocr_coordinates_align_with_tree(lab: None) -> None:
    """Calibration: the OCR box center of a visible text lands inside the SAME element's
    accessibility-tree frame -> OCR coords share the iOS point coordinate system (no scale error).
    """
    goto("link-card")
    code, desc = run("ui", "screen", "--ocr", "-o", "/tmp/lwlab_calib.png")
    assert code == 0
    title = next(e for e in desc["elements"] if e.get("identifier") == "card-title")
    saldo = next(o for o in (desc.get("ocr") or []) if o["text"] == "Saldo")
    cx, cy = _box_center(saldo["box"])
    tx, ty, tw, th = title["box"]
    margin = 6
    assert tx - margin <= cx <= tx + tw + margin, f"x off: {cx} vs {title['box']}"
    assert ty - margin <= cy <= ty + th + margin, f"y off: {cy} vs {title['box']}"


def test_tap_component_outside_tree_via_ocr(lab: None) -> None:
    """A component hidden from the accessibility tree is tapped via OCR box + --at."""
    goto("link-ocr")
    code, desc = run("ui", "screen", "--ocr", "-o", "/tmp/lwlab_ocrtap.png")
    assert code == 0
    hit = next((o for o in (desc.get("ocr") or []) if "OCR-TAP" in o["text"]), None)
    assert hit is not None, "OCR did not find the hidden tappable component"
    x, y, w, h = hit["box"]
    code, result = run("ui", "tap", "--at", f"{x + w // 2},{y + h // 2}")
    assert code == 0 and result["ok"]
    assert event_log() == "tap:ocr-hidden"


# --- smart wait: every mode, success and error ---


def test_wait_tree_change_succeeds(lab: None) -> None:
    goto("link-wait")
    code, result = run("ui", "tap", "--identifier", "wait-mutate", "--wait", "tree")
    assert code == 0 and result["ok"]
    assert result["wait"]["mode"] == "tree" and result["wait"]["ok"]


def test_wait_tree_no_change_errors(lab: None) -> None:
    goto("link-wait")
    code, result = run(
        "ui", "tap", "--identifier", "wait-noop", "--wait", "tree", "--wait-timeout", "2"
    )
    assert code == 25
    assert result["error_code"] == "no_change"
    assert not result["wait"]["ok"]


def test_wait_screen_change_succeeds(lab: None) -> None:
    goto("link-wait")
    code, result = run("ui", "tap", "--identifier", "wait-mutate", "--wait", "screen")
    assert code == 0 and result["ok"]
    assert result["wait"]["mode"] == "screen" and result["wait"]["ok"]


def test_wait_screen_no_change_errors(lab: None) -> None:
    goto("link-wait")
    code, result = run(
        "ui", "tap", "--identifier", "wait-noop", "--wait", "screen", "--wait-timeout", "2"
    )
    assert code == 25
    assert result["error_code"] == "no_change"
    assert not result["wait"]["ok"]


def test_wait_until_appears_succeeds(lab: None) -> None:
    goto("link-wait")
    assert not is_visible("wait-late")
    code, result = run("ui", "tap", "--identifier", "wait-spawn", "--wait-until", "id=wait-late")
    assert code == 0 and result["ok"]
    assert result["wait"]["mode"] == "until" and result["wait"]["ok"]
    assert is_visible("wait-late")


def test_wait_until_never_appears_errors(lab: None) -> None:
    goto("link-wait")
    code, result = run(
        "ui", "tap", "--identifier", "wait-noop", "--wait-until", "id=never", "--wait-timeout", "2"
    )
    assert code == 25
    assert result["error_code"] == "no_change"
    assert not result["wait"]["ok"]


def test_wait_gone_disappears_succeeds(lab: None) -> None:
    goto("link-wait")
    assert is_visible("wait-removable")
    code, result = run(
        "ui", "tap", "--identifier", "wait-despawn", "--wait-gone", "id=wait-removable"
    )
    assert code == 0 and result["ok"]
    assert result["wait"]["mode"] == "gone" and result["wait"]["ok"]
    assert not is_visible("wait-removable")


def test_wait_gone_stays_errors(lab: None) -> None:
    goto("link-wait")
    assert is_visible("wait-removable")
    code, result = run(
        "ui", "tap", "--identifier", "wait-noop",
        "--wait-gone", "id=wait-removable", "--wait-timeout", "2",
    )
    assert code == 25
    assert result["error_code"] == "no_change"
    assert not result["wait"]["ok"]


def test_deeplink_routes_to_app(lab: None) -> None:
    code, result = run(
        "ui", "deeplink", "lazyworker://ping", "--wait-until", "value=deeplink:ping"
    )
    assert code == 0 and result["ok"]
    assert result["wait"]["mode"] == "until" and result["wait"]["ok"]
    assert event_log() == "deeplink:ping"


def test_wait_failure_saves_screenshot(lab: None) -> None:
    import pathlib

    goto("link-wait")
    code, result = run(
        "ui", "tap", "--identifier", "wait-noop", "--wait", "screen", "--wait-timeout", "2"
    )
    assert code == 25
    shot = result.get("screenshot")
    assert shot is not None, "failed wait did not attach a screenshot path"
    assert pathlib.Path(shot).exists() and pathlib.Path(shot).stat().st_size > 1000
    assert result["message"] and "saved screenshot" in result["message"]


def test_wait_failure_no_shot_when_disabled(lab: None) -> None:
    goto("link-wait")
    code, result = run(
        "ui", "tap", "--identifier", "wait-noop",
        "--wait", "screen", "--wait-timeout", "2", "--no-wait-shot",
    )
    assert code == 25
    assert result.get("screenshot") is None


def test_double_tap_wait_tree(lab: None) -> None:
    goto("link-gesture")
    code, result = run("ui", "double-tap", "--identifier", "btn-gesture", "--wait", "tree")
    assert code == 0 and result["ok"]
    assert result["wait"]["mode"] == "tree" and result["wait"]["ok"]


def test_long_press_wait_tree(lab: None) -> None:
    goto("link-gesture")
    code, result = run("ui", "long-press", "--identifier", "btn-gesture", "--wait", "tree")
    assert code == 0 and result["ok"]
    assert result["wait"]["mode"] == "tree" and result["wait"]["ok"]


def test_screenshot(lab: None, tmp_path: object) -> None:
    import pathlib

    goto("link-screenshot")
    out = pathlib.Path("/tmp/lwlab_screenshot.png")
    code, result = run("ui", "screenshot", "-o", str(out))
    assert code == 0 and result["ok"]
    assert out.exists() and out.stat().st_size > 1000
    assert node_by_id("screenshot-marker") is not None
