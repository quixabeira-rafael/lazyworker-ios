from __future__ import annotations

from typing import Any


class WdaError(Exception):
    """Base error for every WebDriverAgent interaction."""


class WdaConnectionError(WdaError):
    """Raised when the WDA server cannot be reached over HTTP."""


class WdaResponseError(WdaError):
    """Raised when WDA returns an error payload or an unexpected status code."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        value: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.value = value
