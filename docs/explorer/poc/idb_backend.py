"""idb backend for the explorer POC — read + act via Facebook idb, no WDA/XCTest.

Surgical: the POC engine (explorer_poc.py) is unchanged. This adapter just
produces observations in the SAME node format the engine already consumes
({type, identifier, label, value, name, rect, visible, children}) and exposes
coordinate actions. idb's flat accessibility list is wrapped as a one-level tree.

Reads: `idb ui describe-all` (~0.2s, flat accessibility surface).
Acts:  `idb ui tap x y` (coordinate), `idb ui swipe`, `idb ui text`.
"""

from __future__ import annotations

import json
import os
import subprocess

IDB = os.environ.get("IDB_BIN", "/Users/rafael/Library/Python/3.9/bin/idb")


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([IDB, *args], capture_output=True, text=True)


def connect(udid: str) -> None:
    _run(["connect", udid])


def describe(udid: str) -> dict:
    """`idb ui describe-all` → a flat tree in the engine's node format."""
    p = _run(["ui", "describe-all", "--udid", udid])
    elements = json.loads(p.stdout) if p.stdout.strip() else []
    children = []
    for e in elements:
        f = e.get("frame") or {}
        rect = {"x": f.get("x", 0), "y": f.get("y", 0),
                "width": f.get("width", 0), "height": f.get("height", 0)} if f else None
        children.append({
            "type": e.get("type") or "Other",
            "identifier": e.get("AXUniqueId"),
            "label": e.get("AXLabel"),
            "value": e.get("AXValue"),
            "name": e.get("AXLabel"),
            "rect": rect,
            "visible": True,
            "children": [],
        })
    return {"type": "Application", "identifier": None, "label": None,
            "value": None, "visible": True, "children": children}


def tap(udid: str, x: float, y: float) -> None:
    _run(["ui", "tap", str(int(x)), str(int(y)), "--udid", udid])


def resolve(tree: dict, selector: dict):
    """Selector → coordinate, read from a (idb) tree's element frames."""
    for n in tree.get("children", []) or []:
        if not n.get("rect"):
            continue
        if selector.get("identifier") and n.get("identifier") == selector["identifier"]:
            r = n["rect"]; return (r["x"] + r["width"] // 2, r["y"] + r["height"] // 2)
        if selector.get("label") and n.get("label") == selector["label"]:
            r = n["rect"]; return (r["x"] + r["width"] // 2, r["y"] + r["height"] // 2)
    return None
