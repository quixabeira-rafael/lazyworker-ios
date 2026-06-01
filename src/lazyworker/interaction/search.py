from __future__ import annotations

from lazyworker.interaction.models import Tip
from lazyworker.wda.models import AccessibilityNode

TEXT_INPUT = {"TextField", "SecureTextField", "SearchField", "TextView"}
SCROLLABLE = {"ScrollView", "Table", "CollectionView", "WebView"}
NON_ACTIONABLE = {"Application", "Window"}


def search_tree(
    node: AccessibilityNode,
    *,
    query: str | None = None,
    type: str | None = None,
    label: str | None = None,
    name: str | None = None,
    value: str | None = None,
    identifier: str | None = None,
    include_hidden: bool = False,
    limit: int | None = None,
) -> list[AccessibilityNode]:
    """Every node matching the field filters (exact) and the free-text ``query``.

    ``query`` is a case-insensitive substring tested against label/name/value/identifier, so a
    search needs no type and no exact field — the field selectors are optional extra filters
    combined with AND. Hidden nodes (``visible is False``) are skipped unless ``include_hidden``.
    """
    needle = query.lower() if query else None
    results: list[AccessibilityNode] = []
    for current in node.walk():
        if not include_hidden and current.visible is False:
            continue
        if type is not None and current.type != type:
            continue
        if label is not None and current.label != label:
            continue
        if name is not None and current.name != name:
            continue
        if value is not None and current.value != value:
            continue
        if identifier is not None and current.identifier != identifier:
            continue
        if needle is not None:
            haystack = " ".join(
                field
                for field in (current.label, current.name, current.value, current.identifier)
                if field
            ).lower()
            if needle not in haystack:
                continue
        results.append(current)
        if limit is not None and len(results) >= limit:
            break
    return results


def _quote(text: str) -> str:
    return '"' + text.replace('"', '\\"') + '"'


def _at(node: AccessibilityNode) -> str | None:
    if node.rect is None:
        return None
    cx, cy = node.rect.center
    return f"--at {cx},{cy}"


def _selector(node: AccessibilityNode) -> str | None:
    """Best single addressing for a copy-paste command: identifier > label+type > coordinate."""
    if node.identifier:
        return f"--identifier {_quote(node.identifier)}"
    if node.label:
        return f"--label {_quote(node.label)} --type {node.type}"
    return _at(node)


def tips_for(node: AccessibilityNode) -> list[Tip]:
    """Ready-to-copy example commands tailored to an element's role.

    Tappables get a ``tap``, text inputs a ``type``, scrollables ``scroll``/``scroll-to``. For
    tap/type, the primary command uses the best selector and an unambiguous ``--at`` variant is
    added when the element has a frame.
    """
    if node.type in NON_ACTIONABLE:
        return []
    if node.type in SCROLLABLE:
        return [
            Tip(action="scroll", command="lazyworker ui scroll --direction down"),
            Tip(action="scroll", command="lazyworker ui scroll --direction up"),
            Tip(action="scroll-to", command='lazyworker ui scroll-to --label "<target>"'),
        ]
    selector = _selector(node)
    if selector is None:
        return []
    action = "type" if node.type in TEXT_INPUT else "tap"

    def command(addressing: str) -> str:
        if action == "type":
            return f'lazyworker ui type --text "<text>" {addressing}'
        return f"lazyworker ui tap {addressing}"

    tips = [Tip(action=action, command=command(selector))]
    at = _at(node)
    if at is not None and not selector.startswith("--at"):
        tips.append(Tip(action=action, command=command(at)))
    return tips
