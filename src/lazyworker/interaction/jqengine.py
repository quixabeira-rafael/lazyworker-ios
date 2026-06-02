"""Thin wrapper around the in-process jq engine (libjq via the ``jq`` package).

Both the tree search (``search_tree``) and the ``--jq`` output filter run their
programs here, so lazyworker never shells out to an external ``jq`` binary.
"""

from __future__ import annotations

import json
from typing import cast

import jq


class JqError(ValueError):
    """A jq program failed to compile or evaluate."""


def evaluate(program: str, value: object) -> list[object]:
    """Run ``program`` over ``value`` and return every output."""
    try:
        return cast("list[object]", jq.compile(program).input_value(value).all())
    except ValueError as exc:
        raise JqError(str(exc)) from exc


def render(values: list[object]) -> str:
    """Render outputs like ``jq -r``: strings raw, everything else as JSON."""
    lines = [v if isinstance(v, str) else json.dumps(v, indent=2, ensure_ascii=False)
             for v in values]
    return "\n".join(lines)
