"""Canonical reference for the iOS accessibility-tree node schema.

Single source of truth shared by ``lazyworker ui schema`` (text and ``--json``)
and ``docs/tree-schema.md``. The node fields mirror :class:`AccessibilityNode`
(what ``ui tree`` emits) and the element-type catalog mirrors WebDriverAgent's
``XCUIElement.ElementType`` string mapping (what shows up in ``type``).
"""

from __future__ import annotations

from typing import TypedDict


class FieldSpec(TypedDict):
    name: str
    source: str
    type: str
    stable: bool
    description: str


NODE_FIELDS: list[FieldSpec] = [
    {
        "name": "type",
        "source": "XCUIElement.ElementType",
        "type": "string",
        "stable": True,
        "description": "Element kind, e.g. Button, Cell, StaticText. Always present. "
        "See the element-type catalog.",
    },
    {
        "name": "identifier",
        "source": "accessibilityIdentifier",
        "type": "string | null",
        "stable": True,
        "description": "The test id set in code. Locale-independent and the best "
        "anchor for selectors. Often null on system or web content.",
    },
    {
        "name": "label",
        "source": "accessibilityLabel",
        "type": "string | null",
        "stable": False,
        "description": "Human-facing text (the spoken VoiceOver string). Changes "
        "with the device language, so it is a weak anchor for selectors.",
    },
    {
        "name": "value",
        "source": "accessibilityValue",
        "type": "string | null",
        "stable": False,
        "description": "Current value: a text field's contents, a switch's '0'/'1', "
        "a slider's position. Reflects state, not identity.",
    },
    {
        "name": "name",
        "source": "wdName (identifier or label)",
        "type": "string | null",
        "stable": False,
        "description": "Convenience field: the identifier if set, otherwise the "
        "label. Good for display, ambiguous for anchoring (you cannot tell which "
        "source it came from).",
    },
    {
        "name": "rect",
        "source": "frame",
        "type": "{x, y, width, height} | null",
        "stable": False,
        "description": "On-screen box in points, origin at the top-left. Use "
        "rect.center for an --at coordinate fallback.",
    },
    {
        "name": "enabled",
        "source": "isEnabled",
        "type": "bool | null",
        "stable": False,
        "description": "Whether the element accepts interaction. Disabled controls "
        "are present in the tree but will not respond to a tap.",
    },
    {
        "name": "visible",
        "source": "isVisible",
        "type": "bool | null",
        "stable": False,
        "description": "Whether the element is on screen. find/tap consider only "
        "visible nodes by default; pass --any-visibility to include the rest.",
    },
    {
        "name": "children",
        "source": "child elements",
        "type": "array of nodes",
        "stable": False,
        "description": "Nested nodes, depth-first. Present in `ui tree`; omitted "
        "from `ui find` matches (which return a flat projection).",
    },
]


# XCUIElement.ElementType string names as emitted by WebDriverAgent, grouped for
# readability. The flat union of all groups is the complete catalog.
ELEMENT_TYPES: dict[str, list[str]] = {
    "Roots & containers": [
        "Application", "Window", "Sheet", "Drawer", "Popover", "Group", "Other",
        "ScrollView", "CollectionView", "Table", "TableRow", "TableColumn",
        "Outline", "OutlineRow", "Browser", "Cell", "Grid", "LayoutArea",
        "LayoutItem", "SplitGroup",
    ],
    "Bars & navigation": [
        "NavigationBar", "TabBar", "TabGroup", "Toolbar", "StatusBar", "MenuBar",
        "MenuBarItem", "Tab", "DockItem", "TouchBar", "StatusItem",
    ],
    "Buttons & controls": [
        "Button", "RadioButton", "RadioGroup", "CheckBox", "DisclosureTriangle",
        "PopUpButton", "ComboBox", "MenuButton", "ToolbarButton", "Switch",
        "Toggle", "Slider", "Stepper", "SegmentedControl", "Link", "ColorWell",
        "IncrementArrow", "DecrementArrow", "Handle", "Splitter",
    ],
    "Text & input": [
        "StaticText", "TextField", "SecureTextField", "SearchField", "TextV",
        "Key", "Keyboard",
    ],
    "Pickers": [
        "Picker", "PickerWheel", "DatePicker",
    ],
    "Indicators": [
        "PageIndicator", "ProgressIndicator", "ActivityIndicator", "LevelIndicator",
        "RatingIndicator", "RelevanceIndicator", "ValueIndicator", "Timeline",
        "Ruler", "RulerMarker",
    ],
    "Media & misc": [
        "Image", "Icon", "Map", "WebView", "Menu", "MenuItem", "Alert", "Dialog",
        "HelpTag", "Matte", "Any",
    ],
}


_ANCHORING = (
    "Anchor selectors on `identifier` when present (stable across locales); "
    "fall back to `label` + `type` together; use `--at` from rect.center only as "
    "a last resort. `value` reflects state, not identity."
)


def schema_document() -> dict[str, object]:
    """Machine-readable schema: node fields plus the element-type catalog."""
    return {
        "node_fields": NODE_FIELDS,
        "element_types": ELEMENT_TYPES,
        "notes": {
            "anchoring": _ANCHORING,
            "visibility": "find/tap default to visible nodes; --any-visibility "
            "widens the search.",
            "find_projection": "`ui find` returns type, label, name, value, "
            "identifier, rect, visible (no children, no enabled).",
        },
    }


def render_schema_text() -> str:
    """Human-readable reference printed by `ui schema` without --json."""
    lines: list[str] = []
    lines.append("iOS accessibility-tree node schema")
    lines.append("=" * 34)
    lines.append("")
    lines.append("Each node of `ui tree` / `ui find` has these fields:")
    lines.append("")
    for field in NODE_FIELDS:
        anchor = "stable" if field["stable"] else "volatile"
        lines.append(f"  {field['name']}  ({field['type']}, {anchor})")
        lines.append(f"      from {field['source']}")
        lines.append(f"      {field['description']}")
        lines.append("")
    lines.append(f"Anchoring: {_ANCHORING}")
    lines.append("")
    lines.append("Element types (the `type` field):")
    lines.append("")
    for group, types in ELEMENT_TYPES.items():
        lines.append(f"  {group}:")
        lines.append(f"      {', '.join(types)}")
        lines.append("")
    return "\n".join(lines)
