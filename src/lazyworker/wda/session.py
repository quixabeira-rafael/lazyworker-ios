from __future__ import annotations

import base64
import binascii
from typing import TYPE_CHECKING, Any

from lazyworker.wda.errors import WdaResponseError
from lazyworker.wda.models import AccessibilityNode

if TYPE_CHECKING:
    from lazyworker.wda.client import WdaClient

TAP_HOLD_MS = 100
DOUBLE_TAP_GAP_MS = 120
LONG_PRESS_SECONDS = 0.8


class Session:
    """An active WDA session bound to a launched application."""

    def __init__(self, client: WdaClient, session_id: str) -> None:
        self._client = client
        self.id = session_id

    def source(self) -> AccessibilityNode:
        """Return the current accessibility tree."""
        body = self._client.request("GET", "/source", params={"format": "json"})
        return AccessibilityNode.model_validate(self._client.value(body))

    def screenshot(self) -> bytes:
        """Return the current screen as PNG bytes."""
        body = self._client.request("GET", "/screenshot")
        try:
            return base64.b64decode(self._client.value(body))
        except (binascii.Error, ValueError) as exc:
            raise WdaResponseError("WebDriverAgent returned an invalid screenshot") from exc

    def tap(self, x: int, y: int) -> None:
        self._perform_pointer(
            [
                {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                {"type": "pointerDown", "button": 0},
                {"type": "pause", "duration": TAP_HOLD_MS},
                {"type": "pointerUp", "button": 0},
            ]
        )

    def double_tap(self, x: int, y: int, *, gap_ms: int = DOUBLE_TAP_GAP_MS) -> None:
        self._perform_pointer(
            [
                {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                {"type": "pointerDown", "button": 0},
                {"type": "pause", "duration": TAP_HOLD_MS},
                {"type": "pointerUp", "button": 0},
                {"type": "pause", "duration": gap_ms},
                {"type": "pointerDown", "button": 0},
                {"type": "pause", "duration": TAP_HOLD_MS},
                {"type": "pointerUp", "button": 0},
            ]
        )

    def long_press(self, x: int, y: int, *, duration: float = LONG_PRESS_SECONDS) -> None:
        self._perform_pointer(
            [
                {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                {"type": "pointerDown", "button": 0},
                {"type": "pause", "duration": int(duration * 1000)},
                {"type": "pointerUp", "button": 0},
            ]
        )

    def apply_settings(self, settings: dict[str, Any]) -> None:
        """Apply WDA session settings (e.g. snapshot depth/timeout)."""
        self._client.request(
            "POST", f"/session/{self.id}/appium/settings", json={"settings": settings}
        )

    def swipe(
        self,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        *,
        duration: float = 0.5,
    ) -> None:
        self._perform_pointer(
            [
                {"type": "pointerMove", "duration": 0, "x": from_x, "y": from_y},
                {"type": "pointerDown", "button": 0},
                {"type": "pointerMove", "duration": int(duration * 1000), "x": to_x, "y": to_y},
                {"type": "pointerUp", "button": 0},
            ]
        )

    def _perform_pointer(self, actions: list[dict[str, Any]]) -> None:
        self._client.request(
            "POST",
            f"/session/{self.id}/actions",
            json={
                "actions": [
                    {
                        "type": "pointer",
                        "id": "finger1",
                        "parameters": {"pointerType": "touch"},
                        "actions": actions,
                    }
                ]
            },
        )

    def type_text(self, text: str) -> None:
        """Type text into the currently focused element."""
        self._client.request("POST", f"/session/{self.id}/wda/keys", json={"value": [text]})

    def deep_link(self, url: str) -> None:
        """Open a URL (universal/deep link) in the active app."""
        self._client.request("POST", f"/session/{self.id}/url", json={"url": url})

    def terminate(self, bundle_id: str) -> None:
        self._client.request(
            "POST", f"/session/{self.id}/wda/apps/terminate", json={"bundleId": bundle_id}
        )

    def delete(self) -> None:
        """Close this WDA session."""
        self._client.request("DELETE", f"/session/{self.id}")
