from typing import Any

from lazyworker.interaction.search import search_tree
from lazyworker.wda.models import AccessibilityNode


def _tree(children: list[dict[str, Any]]) -> AccessibilityNode:
    return AccessibilityNode.model_validate(
        {
            "type": "Application",
            "rect": {"x": 0, "y": 0, "width": 400, "height": 800},
            "isVisible": True,
            "children": children,
        }
    )


_CELL_A = {"type": "Cell", "label": "Joilane Silva", "identifier": "row-1", "isVisible": True}
_CELL_B = {"type": "Cell", "label": "Maria", "identifier": "row-2", "isVisible": True}
_BTN = {"type": "Button", "label": "Joilane", "isVisible": True}
_HIDDEN = {"type": "StaticText", "label": "Joilane hidden", "isVisible": False}


def test_query_matches_substring_across_types() -> None:
    matches = search_tree(_tree([_CELL_A, _CELL_B, _BTN]), query="joilane")
    assert {n.label for n in matches} == {"Joilane Silva", "Joilane"}


def test_query_plus_type_filter() -> None:
    matches = search_tree(_tree([_CELL_A, _CELL_B, _BTN]), query="joilane", type="Cell")
    assert [n.label for n in matches] == ["Joilane Silva"]


def test_exact_field_filter_without_query() -> None:
    matches = search_tree(_tree([_CELL_A, _CELL_B]), identifier="row-2")
    assert [n.label for n in matches] == ["Maria"]


def test_query_matches_identifier() -> None:
    matches = search_tree(_tree([_CELL_A, _CELL_B]), query="row-1")
    assert [n.label for n in matches] == ["Joilane Silva"]


def test_excludes_hidden_by_default() -> None:
    tree = _tree([_BTN, _HIDDEN])
    assert [n.label for n in search_tree(tree, query="joilane")] == ["Joilane"]
    assert len(search_tree(tree, query="joilane", include_hidden=True)) == 2


def test_limit_caps_results() -> None:
    matches = search_tree(_tree([_CELL_A, _BTN]), query="joilane", limit=1)
    assert len(matches) == 1
