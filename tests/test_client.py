import base64

import pytest
from pytest_httpx import HTTPXMock

from lazyworker.wda.client import WdaClient
from lazyworker.wda.errors import WdaResponseError
from lazyworker.wda.session import Session

BASE_URL = "http://127.0.0.1:8100"


def test_status(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE_URL}/status",
        json={
            "value": {"ready": True, "message": "ready", "os": {"name": "iOS", "version": "17.0"}},
            "sessionId": None,
        },
    )
    with WdaClient(BASE_URL) as client:
        status = client.status()
    assert status.ready is True
    assert status.os_version == "17.0"


def test_create_session(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE_URL}/session",
        method="POST",
        json={"sessionId": "ABC123", "value": {}},
    )
    with WdaClient(BASE_URL) as client:
        session = client.create_session("com.example.app")
    assert session.id == "ABC123"
    request = httpx_mock.get_requests()[0]
    assert b"com.example.app" in request.content


def test_create_session_w3c_value(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE_URL}/session",
        method="POST",
        json={"value": {"sessionId": "XYZ789", "capabilities": {}}},
    )
    with WdaClient(BASE_URL) as client:
        session = client.create_session("com.example.app")
    assert session.id == "XYZ789"


def test_source(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE_URL}/source?format=json",
        json={"value": {"type": "Application", "children": []}},
    )
    tree = Session(WdaClient(BASE_URL), "S1").source()
    assert tree.type == "Application"


def test_screenshot(httpx_mock: HTTPXMock) -> None:
    raw = b"\x89PNG\r\n"
    httpx_mock.add_response(
        url=f"{BASE_URL}/screenshot",
        json={"value": base64.b64encode(raw).decode()},
    )
    data = Session(WdaClient(BASE_URL), "S1").screenshot()
    assert data == raw


def test_tap_sends_w3c_pointer_actions(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE_URL}/session/S1/actions",
        method="POST",
        json={"value": None},
    )
    Session(WdaClient(BASE_URL), "S1").tap(120, 240)
    request = httpx_mock.get_requests()[0]
    payload = request.content.replace(b" ", b"")
    assert b'"type":"pointer"' in payload
    assert b'"x":120' in payload
    assert b'"y":240' in payload


def test_type_text_sends_keys(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE_URL}/session/S1/wda/keys",
        method="POST",
        json={"value": None},
    )
    Session(WdaClient(BASE_URL), "S1").type_text("joilane")
    assert b"joilane" in httpx_mock.get_requests()[0].content


def test_error_payload_raises(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE_URL}/status",
        status_code=500,
        json={"value": {"error": "unknown error", "message": "boom"}},
    )
    with pytest.raises(WdaResponseError) as excinfo:
        WdaClient(BASE_URL).status()
    assert excinfo.value.status_code == 500
    assert "boom" in str(excinfo.value)
