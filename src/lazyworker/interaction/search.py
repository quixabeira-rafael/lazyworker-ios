from __future__ import annotations

import json
import unicodedata

from lazyworker.interaction import jqengine
from lazyworker.interaction.models import Tip
from lazyworker.wda.models import AccessibilityNode

TEXT_INPUT = {"TextField", "SecureTextField", "SearchField", "TextView"}
SCROLLABLE = {"ScrollView", "Table", "CollectionView", "WebView"}
NON_ACTIONABLE = {"Application", "Window"}


def _normalize(text: str) -> str:
    """Lower-case, strip accents and collapse whitespace (incl. newlines).

    Makes the free-text query forgiving: 'comecar' matches 'Começar' and a query
    matches across an element's multi-line label."""
    decomposed = unicodedata.normalize("NFKD", text)
    folded = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(folded.lower().split())


def _haystack(node: AccessibilityNode) -> str:
    """All searchable text of a node — type plus every text field — normalized."""
    fields = (node.type, node.label, node.name, node.value, node.identifier)
    return _normalize(" ".join(field for field in fields if field))


def _search_program(
    *,
    query: str | None,
    type: str | None,
    label: str | None,
    name: str | None,
    value: str | None,
    identifier: str | None,
    include_hidden: bool,
    limit: int | None,
) -> str:
    """Build the jq program that filters the flattened node list down to indices.

    The matching lives entirely in jq; Python only supplies the normalized ``_q``
    haystack (accent folding is the one thing jq cannot do) and the node index.
    Values are embedded as JSON literals, so they are quoted safely.
    """
    selects: list[str] = []
    if not include_hidden:
        selects.append("select(.visible != false)")
    for field, value_ in (
        ("type", type), ("label", label), ("name", name),
        ("value", value), ("identifier", identifier),
    ):
        if value_ is not None:
            selects.append(f"select(.{field} == {json.dumps(value_)})")
    needle = _normalize(query) if query else ""
    if needle:
        selects.append(f"select(._q | contains({json.dumps(needle)}))")
    program = "[ .[]" + "".join(f" | {clause}" for clause in selects) + " | ._i ]"
    if limit is not None:
        program += f" | .[0:{limit}]"
    return program + " | .[]"


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

    ``query`` is a forgiving substring (case-insensitive, accent-folded, whitespace-collapsed)
    tested against the node's type and every text field (label/name/value/identifier), so a
    plain ``find back`` matches "Back" whether it sits in the id, the label, anywhere. The field
    selectors are optional exact extra filters combined with AND. Hidden nodes (``visible is
    False``) are skipped unless ``include_hidden``.

    The filtering runs in jq: each node is projected to its searchable fields plus a normalized
    ``_q`` haystack and its index ``_i``, jq selects the matching indices, and those map back to
    the original nodes (in tree order).
    """
    nodes = list(node.walk())
    payload = [
        {
            "type": current.type,
            "label": current.label,
            "name": current.name,
            "value": current.value,
            "identifier": current.identifier,
            "visible": current.visible,
            "_q": _haystack(current),
            "_i": index,
        }
        for index, current in enumerate(nodes)
    ]
    program = _search_program(
        query=query, type=type, label=label, name=name, value=value,
        identifier=identifier, include_hidden=include_hidden, limit=limit,
    )
    indices = jqengine.evaluate(program, payload)
    return [nodes[index] for index in indices if isinstance(index, int)]


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
