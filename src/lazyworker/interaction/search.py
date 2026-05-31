from __future__ import annotations

from lazyworker.wda.models import AccessibilityNode


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
