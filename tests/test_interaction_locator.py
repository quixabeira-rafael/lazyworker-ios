import pytest
from pydantic import ValidationError

from lazyworker.interaction.locator import Locator, LocatorResolver
from lazyworker.interaction.models import ErrorCode
from lazyworker.wda.models import AccessibilityNode

_RECT = {"x": 0, "y": 0, "width": 10, "height": 10}


def _tree() -> AccessibilityNode:
    return AccessibilityNode.model_validate(
        {
            "type": "Application",
            "children": [
                {"type": "Button", "label": "A", "rect": _RECT, "isVisible": True, "children": []},
                {"type": "Button", "label": "B", "rect": _RECT, "isVisible": True, "children": []},
                {"type": "Button", "label": "B", "rect": _RECT, "isVisible": True, "children": []},
            ],
        }
    )


def test_single_match() -> None:
    result = LocatorResolver().resolve(_tree(), Locator(label="A"))
    assert result.error_code == ErrorCode.OK
    assert result.node is not None and result.node.label == "A"


def test_not_found() -> None:
    result = LocatorResolver().resolve(_tree(), Locator(label="Z"))
    assert result.error_code == ErrorCode.NOT_FOUND
    assert result.candidate_count == 0


def test_ambiguous() -> None:
    result = LocatorResolver().resolve(_tree(), Locator(label="B"))
    assert result.error_code == ErrorCode.AMBIGUOUS
    assert result.candidate_count == 2


def test_index_selects_match() -> None:
    result = LocatorResolver().resolve(_tree(), Locator(label="B", index=1))
    assert result.error_code == ErrorCode.OK


def test_index_out_of_range() -> None:
    result = LocatorResolver().resolve(_tree(), Locator(label="B", index=5))
    assert result.error_code == ErrorCode.NOT_FOUND


def test_empty_locator_rejected() -> None:
    with pytest.raises(ValidationError):
        Locator()
