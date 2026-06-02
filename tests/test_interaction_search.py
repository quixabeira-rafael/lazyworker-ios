from typing import Any

from lazyworker.interaction.search import overview, search_tree, tips_for
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


def test_query_matches_type() -> None:
    # `ui find button` finds buttons even with no text filter
    matches = search_tree(_tree([_CELL_A, _BTN]), query="button")
    assert [n.type for n in matches] == ["Button"]


def test_query_is_accent_insensitive() -> None:
    tree = _tree([{"type": "Button", "label": "Começar", "isVisible": True}])
    assert len(search_tree(tree, query="comecar")) == 1
    assert len(search_tree(tree, query="COMEÇAR")) == 1


def test_query_collapses_whitespace_and_newlines() -> None:
    # a multi-line composite label (common in Flutter cards) still matches
    card = {"type": "Button", "label": "RapCaviar\nVarious Artists", "isVisible": True}
    assert len(search_tree(_tree([card]), query="rapcaviar various")) == 1


def test_query_matches_substring_in_identifier_or_label() -> None:
    node = {"type": "Button", "label": "Menu", "identifier": "hamburger-menu-button",
            "isVisible": True}
    # the same query hits whether the term lives in the label or the id
    assert len(search_tree(_tree([node]), query="hamburger")) == 1
    assert len(search_tree(_tree([node]), query="menu")) == 1


def test_excludes_hidden_by_default() -> None:
    tree = _tree([_BTN, _HIDDEN])
    assert [n.label for n in search_tree(tree, query="joilane")] == ["Joilane"]
    assert len(search_tree(tree, query="joilane", include_hidden=True)) == 2


def test_limit_caps_results() -> None:
    matches = search_tree(_tree([_CELL_A, _BTN]), query="joilane", limit=1)
    assert len(matches) == 1


# --- overview ---


def test_overview_returns_actionable_controls_first() -> None:
    text = {"type": "StaticText", "label": "Header", "isVisible": True}
    button = {"type": "Button", "label": "Go", "isVisible": True}
    tree = _tree([text, button])
    result = overview(tree)
    # the Button (a control) is ranked before the plain StaticText, even though it comes later
    assert [n.label for n in result] == ["Go", "Header"]


def test_overview_skips_hidden_and_non_addressable() -> None:
    tree = _tree([_HIDDEN, {"type": "Button", "isVisible": True}])  # hidden + button with no label
    # hidden is excluded; the addressless button has no tip, so it drops out too
    assert overview(tree) == []


# --- tips_for ---

_RECT = {"x": 0, "y": 0, "width": 100, "height": 40}


def _node(type_: str, **kw: Any) -> AccessibilityNode:
    return AccessibilityNode.model_validate({"type": type_, "isVisible": True, **kw})


def test_tips_button_by_identifier_plus_at_fallback() -> None:
    tips = tips_for(_node("Button", identifier="btn-primary", rect=_RECT))
    assert [t.action for t in tips] == ["tap", "tap"]
    assert tips[0].command == 'lazyworker ui tap --identifier "btn-primary"'
    assert tips[1].command == "lazyworker ui tap --at 50,20"


def test_tips_button_by_label_type_plus_at() -> None:
    tips = tips_for(_node("Button", label="Save", rect=_RECT))
    assert tips[0].command == 'lazyworker ui tap --label "Save" --type Button'
    assert tips[1].command == "lazyworker ui tap --at 50,20"


def test_tips_text_input_is_type() -> None:
    tips = tips_for(_node("TextField", identifier="email", rect=_RECT))
    assert tips[0].action == "type"
    assert tips[0].command == 'lazyworker ui type --text "<text>" --identifier "email"'


def test_tips_scrollable() -> None:
    tips = tips_for(_node("ScrollView", rect=_RECT))
    assert [t.action for t in tips] == ["scroll", "scroll", "scroll-to"]
    assert "--direction down" in tips[0].command


def test_tips_coordinate_only_single() -> None:
    tips = tips_for(_node("Image", rect=_RECT))
    assert len(tips) == 1
    assert tips[0].command == "lazyworker ui tap --at 50,20"


def test_tips_non_actionable_root_is_empty() -> None:
    assert tips_for(_node("Application", rect=_RECT)) == []


def test_tips_without_addressing_is_empty() -> None:
    assert tips_for(_node("Button")) == []
