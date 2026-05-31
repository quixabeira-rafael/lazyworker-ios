from __future__ import annotations

from pydantic import BaseModel

from lazyworker.wda.models import AccessibilityNode

# Roles that an agent can act on (and that anchor a "container" for grouping).
INTERACTIVE_ROLES = frozenset(
    {
        "Button",
        "Cell",
        "Switch",
        "TextField",
        "SecureTextField",
        "Slider",
        "Link",
        "SegmentedControl",
        "Stepper",
        "Picker",
        "MenuItem",
        "Tab",
        "TabBar",
    }
)

# Pure structural wrappers that carry no useful breakdown on their own.
STRUCTURAL_ROLES = frozenset({"Application", "Window"})


class ScreenElement(BaseModel):
    """One box on the screen: a text or interactive element with its frame."""

    role: str
    identifier: str | None = None
    text: str | None = None
    box: tuple[int, int, int, int]  # x, y, width, height
    size: tuple[int, int]  # width, height
    interactive: bool = False
    container: str | None = None  # nearest interactive/identified ancestor


class ScreenDescription(BaseModel):
    """Agent-consumable textual breakdown of the current screen."""

    screenshot: str
    width: int
    height: int
    bundle_id: str | None = None
    elements: list[ScreenElement]


def _text_of(node: AccessibilityNode) -> str | None:
    for candidate in (node.label, node.value, node.name):
        if candidate and candidate.strip():
            return candidate
    return None


def describe_screen(
    tree: AccessibilityNode,
    *,
    screenshot: str,
    bundle_id: str | None = None,
) -> ScreenDescription:
    """Flatten the accessibility tree into screen boxes, in reading order."""
    width = tree.rect.width if tree.rect else 0
    height = tree.rect.height if tree.rect else 0
    elements: list[ScreenElement] = []

    def visit(node: AccessibilityNode, container: str | None) -> None:
        interactive = node.type in INTERACTIVE_ROLES
        text = _text_of(node)
        addable = (
            node.rect is not None
            and bool(node.visible)
            and node.type not in STRUCTURAL_ROLES
            and (interactive or text is not None or node.identifier is not None)
        )
        if addable and node.rect is not None:
            elements.append(
                ScreenElement(
                    role=node.type,
                    identifier=node.identifier,
                    text=text,
                    box=(node.rect.x, node.rect.y, node.rect.width, node.rect.height),
                    size=(node.rect.width, node.rect.height),
                    interactive=interactive,
                    container=container,
                )
            )
        next_container = container
        if interactive or node.identifier is not None:
            next_container = node.identifier or node.type
        for child in node.children:
            visit(child, next_container)

    visit(tree, None)
    elements.sort(key=lambda element: (element.box[1], element.box[0]))
    return ScreenDescription(
        screenshot=screenshot,
        width=width,
        height=height,
        bundle_id=bundle_id,
        elements=elements,
    )
