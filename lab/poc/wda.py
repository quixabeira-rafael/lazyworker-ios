"""Minimal WebDriverAgent client for the steady-state capture POC.

Talks to a running WDA instance directly so the capture loop has no overhead
beyond the HTTP request and base64 decode.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx

STATE_DIR = Path(__file__).resolve().parents[2] / ".lazyworker"


def load_runtime() -> tuple[str, str]:
    """Return (base_url, session_id) from the persisted lazyworker state."""
    run = json.loads((STATE_DIR / "run.json").read_text())
    session = json.loads((STATE_DIR / "session.json").read_text())
    return run["base_url"], session["session_id"]


class Wda:
    def __init__(self, base_url: str, session_id: str, timeout: float = 15.0) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout)
        self._session = session_id

    def close(self) -> None:
        self._client.close()

    def screenshot(self) -> bytes:
        """Return raw PNG bytes (session-less endpoint)."""
        body = self._client.get("/screenshot").json()
        return base64.b64decode(body["value"])

    def tap(self, x: int, y: int, hold_ms: int = 100) -> None:
        self._client.post(
            f"/session/{self._session}/actions",
            json={
                "actions": [
                    {
                        "type": "pointer",
                        "id": "finger1",
                        "parameters": {"pointerType": "touch"},
                        "actions": [
                            {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                            {"type": "pointerDown", "button": 0},
                            {"type": "pause", "duration": hold_ms},
                            {"type": "pointerUp", "button": 0},
                        ],
                    }
                ]
            },
        )

    def source(self) -> dict:
        return self._client.get(
            f"/session/{self._session}/source", params={"format": "json"}
        ).json()["value"]
