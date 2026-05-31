from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path

_SERVER_URL = re.compile(r"ServerURLHere->(?P<url>.*?)<-ServerURLHere")


def parse_server_url(text: str) -> str | None:
    """Extract the URL WebDriverAgent prints to its log on startup."""
    match = _SERVER_URL.search(text)
    return match.group("url") if match else None


def wait_for_server_url(
    log_path: Path,
    *,
    timeout: float,
    interval: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> str | None:
    """Poll the WDA log until it advertises its server URL, or time out."""
    deadline = clock() + timeout
    while True:
        if log_path.exists():
            url = parse_server_url(log_path.read_text(errors="ignore"))
            if url:
                return url
        if clock() >= deadline:
            return None
        sleep(interval)
