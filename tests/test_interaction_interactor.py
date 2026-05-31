from typing import Any

from pytest_httpx import HTTPXMock

from lazyworker.interaction.interactor import Interactor
from lazyworker.interaction.locator import Locator
from lazyworker.interaction.models import Action, ErrorCode, ScrollDirection
from lazyworker.wda.client import WdaClient
from lazyworker.wda.session import Session

BASE = "http://127.0.0.1:8100"
SOURCE_URL = f"{BASE}/source?format=json"
ACTIONS_URL = f"{BASE}/session/S1/actions"
KEYS_URL = f"{BASE}/session/S1/wda/keys"

BUTTON = {
    "type": "Button",
    "label": "Login",
    "rect": {"x": 100, "y": 200, "width": 100, "height": 40},
    "isVisible": True,
    "children": [],
}


def _interactor() -> Interactor:
    return Interactor(Session(WdaClient(BASE), "S1"))


def _tree(children: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "value": {
            "type": "Application",
            "rect": {"x": 0, "y": 0, "width": 400, "height": 800},
            "isVisible": True,
            "children": children,
        }
    }


def _no_gesture(httpx_mock: HTTPXMock) -> bool:
    return all("/actions" not in req.url.path for req in httpx_mock.get_requests())


def test_tap_success(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SOURCE_URL, json=_tree([BUTTON]))
    httpx_mock.add_response(url=ACTIONS_URL, method="POST", json={"value": None})
    result = _interactor().tap(Locator(label="Login"))
    assert result.ok
    assert result.operation == Action.TAP
    assert result.point == (150, 220)


def test_tap_not_found_sends_no_gesture(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SOURCE_URL, json=_tree([]))
    result = _interactor().tap(Locator(label="Login"))
    assert not result.ok
    assert result.error_code == ErrorCode.NOT_FOUND
    assert _no_gesture(httpx_mock)


def test_tap_ambiguous_lists_candidates(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SOURCE_URL, json=_tree([BUTTON, BUTTON]))
    result = _interactor().tap(Locator(label="Login"))
    assert result.error_code == ErrorCode.AMBIGUOUS
    assert result.candidate_count == 2
    assert result.candidates is not None and len(result.candidates) == 2
    assert _no_gesture(httpx_mock)


def test_tap_no_rect(httpx_mock: HTTPXMock) -> None:
    node = {"type": "Button", "label": "Login", "isVisible": True, "children": []}
    httpx_mock.add_response(url=SOURCE_URL, json=_tree([node]))
    result = _interactor().tap(Locator(label="Login"))
    assert result.error_code == ErrorCode.NO_RECT


def test_tap_dry_run_sends_no_gesture(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SOURCE_URL, json=_tree([BUTTON]))
    result = _interactor().tap(Locator(label="Login"), dry_run=True)
    assert result.ok and result.dry_run
    assert _no_gesture(httpx_mock)


def test_tap_at_coordinates(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=ACTIONS_URL, method="POST", json={"value": None})
    result = _interactor().tap(at=(50, 60))
    assert result.ok and result.point == (50, 60)


def test_tap_conflicting_target(httpx_mock: HTTPXMock) -> None:
    result = _interactor().tap(Locator(label="X"), at=(1, 2))
    assert result.error_code == ErrorCode.INVALID_TARGET


def test_tap_wda_error_classified(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SOURCE_URL, json=_tree([BUTTON]))
    httpx_mock.add_response(
        url=ACTIONS_URL, method="POST", status_code=500, json={"value": {"error": "boom"}}
    )
    result = _interactor().tap(Locator(label="Login"))
    assert result.error_code == ErrorCode.WDA_ERROR


def test_double_tap(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SOURCE_URL, json=_tree([BUTTON]))
    httpx_mock.add_response(url=ACTIONS_URL, method="POST", json={"value": None})
    result = _interactor().double_tap(Locator(label="Login"))
    assert result.ok and result.operation == Action.DOUBLE_TAP


def test_type_focus_then_keys_in_order(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SOURCE_URL, json=_tree([BUTTON]))
    httpx_mock.add_response(url=ACTIONS_URL, method="POST", json={"value": None})
    httpx_mock.add_response(url=KEYS_URL, method="POST", json={"value": None})
    result = _interactor().type_text("hi", locator=Locator(label="Login"))
    assert result.ok
    paths = [req.url.path for req in httpx_mock.get_requests()]
    assert paths.index("/session/S1/actions") < paths.index("/session/S1/wda/keys")


def test_scroll(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SOURCE_URL, json=_tree([]))
    httpx_mock.add_response(url=ACTIONS_URL, method="POST", json={"value": None})
    result = _interactor().scroll(ScrollDirection.DOWN)
    assert result.ok and result.operation == Action.SCROLL


def test_scroll_to_found_after_swipe(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SOURCE_URL, json=_tree([]))  # screen size
    httpx_mock.add_response(url=SOURCE_URL, json=_tree([]))  # attempt 1: not found
    httpx_mock.add_response(url=ACTIONS_URL, method="POST", json={"value": None})  # swipe
    httpx_mock.add_response(url=SOURCE_URL, json=_tree([BUTTON]))  # attempt 2: found
    result = _interactor().scroll_to(Locator(label="Login"), max_swipes=3)
    assert result.ok
    assert result.attempts == 2


def test_scroll_to_exhausted(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SOURCE_URL, json=_tree([]))  # screen size
    httpx_mock.add_response(url=SOURCE_URL, json=_tree([]))
    httpx_mock.add_response(url=ACTIONS_URL, method="POST", json={"value": None})
    httpx_mock.add_response(url=SOURCE_URL, json=_tree([]))
    httpx_mock.add_response(url=ACTIONS_URL, method="POST", json={"value": None})
    result = _interactor().scroll_to(Locator(label="Login"), max_swipes=2)
    assert not result.ok
    assert result.error_code == ErrorCode.NOT_VISIBLE


URL_ENDPOINT = f"{BASE}/session/S1/url"


def test_deep_link_success(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=URL_ENDPOINT, method="POST", json={"value": None})
    result = _interactor().deep_link("lazyworker://ping")
    assert result.ok
    assert result.operation == Action.DEEPLINK
    assert result.message == "lazyworker://ping"
    assert httpx_mock.get_requests()[0].url.path == "/session/S1/url"


def test_deep_link_wda_error_classified(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=URL_ENDPOINT, method="POST", status_code=500, json={"value": {"error": "boom"}}
    )
    result = _interactor().deep_link("lazyworker://ping")
    assert not result.ok
    assert result.error_code == ErrorCode.WDA_ERROR
