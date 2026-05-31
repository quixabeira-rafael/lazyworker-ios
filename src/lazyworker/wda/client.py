from __future__ import annotations

from typing import Any

import httpx

from lazyworker.wda.errors import WdaConnectionError, WdaResponseError
from lazyworker.wda.models import Status
from lazyworker.wda.session import Session

DEFAULT_BASE_URL = "http://127.0.0.1:8100"
DEFAULT_TIMEOUT = 30.0


class WdaClient:
    """Thin typed HTTP client for a running WebDriverAgent server."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        http_client: httpx.Client | None = None,
    ) -> None:
        if http_client is not None:
            self._client = http_client
            self._owns_client = False
        else:
            self._client = httpx.Client(base_url=base_url, timeout=timeout)
            self._owns_client = True

    def __enter__(self) -> WdaClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> dict[str, Any]:
        """Send a request and return the parsed WDA envelope, raising on errors."""
        try:
            response = self._client.request(method, path, params=params, json=json)
        except httpx.ConnectError as exc:
            raise WdaConnectionError(
                f"Cannot reach WebDriverAgent at {self._client.base_url}: {exc}"
            ) from exc
        except httpx.HTTPError as exc:
            raise WdaConnectionError(f"HTTP error talking to WebDriverAgent: {exc}") from exc
        return self._unwrap(response)

    @staticmethod
    def _unwrap(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise WdaResponseError(
                f"WebDriverAgent returned a non-JSON response ({response.status_code})",
                status_code=response.status_code,
            ) from exc

        if not isinstance(body, dict):
            raise WdaResponseError(
                f"WebDriverAgent returned an unexpected payload ({response.status_code})",
                status_code=response.status_code,
                value=body,
            )

        value = body.get("value")
        has_error = isinstance(value, dict) and value.get("error")
        if response.status_code >= 400 or has_error:
            message = ""
            if isinstance(value, dict):
                message = value.get("message") or value.get("error") or ""
            raise WdaResponseError(
                message or f"WebDriverAgent error ({response.status_code})",
                status_code=response.status_code,
                value=value,
            )
        return dict(body)

    @staticmethod
    def value(body: dict[str, Any]) -> Any:
        """Return the ``value`` field of a WDA envelope, raising if it is absent."""
        if "value" not in body:
            raise WdaResponseError("WebDriverAgent response had no 'value' field", value=body)
        return body["value"]

    def status(self) -> Status:
        body = self.request("GET", "/status")
        payload = body.get("value")
        if not isinstance(payload, dict):
            payload = {}
        return Status.model_validate(payload)

    def create_session(
        self,
        bundle_id: str,
        *,
        arguments: list[str] | None = None,
        environment: dict[str, str] | None = None,
        wait_for_quiescence: bool = True,
    ) -> Session:
        """Launch ``bundle_id`` and return an active automation session.

        ``wait_for_quiescence=False`` returns fast for heavy apps that never go idle.
        """
        capabilities: dict[str, Any] = {"bundleId": bundle_id}
        if arguments is not None:
            capabilities["arguments"] = arguments
        if environment is not None:
            capabilities["environment"] = environment
        if not wait_for_quiescence:
            capabilities["shouldWaitForQuiescence"] = False

        body = self.request(
            "POST", "/session", json={"capabilities": {"alwaysMatch": capabilities}}
        )
        session_id = body.get("sessionId")
        if not session_id and isinstance(body.get("value"), dict):
            session_id = body["value"].get("sessionId")
        if not session_id:
            raise WdaResponseError("WebDriverAgent did not return a session id", value=body)
        return Session(self, session_id)
