"""End-to-end harness that drives the LazyWorker Lab app through the `lazyworker` CLI.

Opt-in: set ``LAZYWORKER_E2E=1`` and have a simulator booted with WebDriverAgent running
(`lazyworker up`) and the lab app installed (see lab/README.md). Otherwise every test skips.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

LAB_BUNDLE = "com.lazyworker.lab"
RUN_STATE = Path.home() / ".lazyworker" / "run.json"
LAZYWORKER = str(Path(sys.executable).parent / "lazyworker")


def run(*args: str, stdin: str | None = None) -> tuple[int, Any]:
    """Invoke the lazyworker CLI; return (exit_code, parsed_json_or_text)."""
    proc = subprocess.run(
        [LAZYWORKER, *args], capture_output=True, text=True, input=stdin, check=False
    )
    data: Any = None
    if proc.stdout.strip():
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            data = proc.stdout
    return proc.returncode, data


def _find(node: dict[str, Any], identifier: str) -> dict[str, Any] | None:
    if node.get("identifier") == identifier:
        return node
    for child in node.get("children", []):
        found = _find(child, identifier)
        if found is not None:
            return found
    return None


def node_by_id(identifier: str) -> dict[str, Any] | None:
    code, tree = run("ui", "tree")
    if code != 0 or not isinstance(tree, dict):
        return None
    return _find(tree, identifier)


def event_log() -> str | None:
    node = node_by_id("event-log")
    if node is None:
        return None
    return node.get("value") or node.get("label") or node.get("name")


def is_visible(identifier: str) -> bool:
    node = node_by_id(identifier)
    return bool(node and node.get("visible"))


def goto(link: str) -> None:
    code, _ = run("ui", "tap", "--identifier", link)
    if code != 0:
        run("ui", "scroll-to", "--identifier", link)
        code, _ = run("ui", "tap", "--identifier", link)
    assert code == 0, f"navigation tap on {link} failed"


@pytest.fixture(scope="session", autouse=True)
def _require_e2e() -> None:
    if os.environ.get("LAZYWORKER_E2E") != "1":
        pytest.skip("set LAZYWORKER_E2E=1 to run e2e (needs simulator + WDA + lab app)")


@pytest.fixture(scope="session")
def udid() -> str:
    if not RUN_STATE.exists():
        pytest.skip("no active WDA run; run `lazyworker up` first")
    return str(json.loads(RUN_STATE.read_text())["udid"])


@pytest.fixture(scope="session", autouse=True)
def _open_session(_require_e2e: None) -> Iterator[None]:
    code, data = run("ui", "open", LAB_BUNDLE)
    if code != 0:
        pytest.skip(f"could not open {LAB_BUNDLE}: {data}")
    yield
    run("ui", "close")


@pytest.fixture
def lab(udid: str, _open_session: None) -> None:
    """Reset to the home screen by cold-relaunching the app before each test."""
    subprocess.run(["xcrun", "simctl", "terminate", udid, LAB_BUNDLE], capture_output=True)
    subprocess.run(["xcrun", "simctl", "launch", udid, LAB_BUNDLE], capture_output=True)
    time.sleep(1.0)
