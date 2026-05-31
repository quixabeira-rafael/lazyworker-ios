from lazyworker.interaction.settings import SessionOptions, SnapshotSettings


def test_snapshot_payload_uses_wda_keys() -> None:
    payload = SnapshotSettings(snapshotMaxDepth=20).as_payload()
    assert payload["snapshotMaxDepth"] == 20
    assert payload["waitForIdleTimeout"] == 0.0
    assert payload["animationCoolOffTimeout"] == 0.0


def test_session_options_default_no_quiescence() -> None:
    options = SessionOptions()
    assert options.wait_for_quiescence is False
    assert options.settings.customSnapshotTimeout > 0
