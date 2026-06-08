"""Build a WDA-native explorer base by walking the app menu, anchored on Settings.

Robust strategy: never rely on deep back-stacks. Always re-anchor to the Settings
menu (recovering by RELAUNCHING the app if lost), and explore at most one tap away
from it: expand Settings (depth-1), then expand each depth-1 child (depth-2). Each
destination is recorded with identity dedup and the edge is learned. WDA only.

Run after: lazyworker up && lazyworker ui open <bundle> --no-reuse  (start on Home)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import explorer_poc as ex

DB_PATH = os.path.join(os.path.dirname(__file__), "explorer_wda_db.json")
BUNDLE = os.environ.get("WW_BUNDLE", "com.weightwatchers.wwmobile")
TARGET = 30
SETTLE = 1.6

AVOID = ("delete", "sign out", "signout", "log out", "logout", "switch plan", "switch-plan",
         "switch to", "med+", "med-plus", "billing", "purchase", "subscribe", "subscription",
         "payment", "redeem", "cancel", "remove", "reset", "clear", "log a")
NAV = ("back", "close", "done", "dismiss", "skip")

SETTINGS_ID = None
visited: set[tuple[str, str]] = set()


def tree() -> dict:
    return json.loads(subprocess.run(["lazyworker", "ui", "tree"],
                                     capture_output=True, text=True).stdout)


def tap(identifier: str) -> bool:
    p = subprocess.run(["lazyworker", "ui", "tap", "--identifier", identifier],
                       capture_output=True, text=True)
    try:
        return json.loads(p.stdout).get("ok", False)
    except Exception:
        return False


def ids_in(obs: dict) -> set[str]:
    return {n.get("identifier") for n in ex._walk(obs) if n.get("identifier")}


def avoided(label: str, ident: str) -> bool:
    blob = f"{label} {ident}".lower()
    return any(a in blob for a in AVOID) or any(a in blob for a in NAV)


def at_here(db: ex.ExplorerDB, state_id: str) -> bool:
    mid, score = db.match(tree())
    return score >= ex.SAME and mid == state_id


def relaunch(db: ex.ExplorerDB) -> bool:
    """Hard recovery: relaunch the app, reopen the session, return to Settings."""
    subprocess.run(["xcrun", "simctl", "terminate", "booted", BUNDLE], capture_output=True)
    subprocess.run(["xcrun", "simctl", "launch", "booted", BUNDLE], capture_output=True)
    subprocess.run(["lazyworker", "ui", "open", BUNDLE, "--no-reuse"], capture_output=True)
    for _ in range(20):
        time.sleep(1.5)
        if "nav-settings-button" in ids_in(tree()):
            break
    tap("nav-settings-button")
    time.sleep(SETTLE)
    return at_here(db, SETTINGS_ID)


def ensure_settings(db: ex.ExplorerDB) -> bool:
    """Re-anchor to the Settings menu, via back buttons first, then relaunch."""
    for _ in range(6):
        if at_here(db, SETTINGS_ID):
            return True
        ids = ids_in(tree())
        if "settings-back-button" in ids:
            tap("settings-back-button")
        elif "settings-close-button" in ids:           # closes to home
            tap("settings-close-button"); time.sleep(SETTLE); tap("nav-settings-button")
        elif "nav-settings-button" in ids:             # we are home
            tap("nav-settings-button")
        else:
            return relaunch(db)
        time.sleep(SETTLE)
    return at_here(db, SETTINGS_ID) or relaunch(db)


def expand(db: ex.ExplorerDB, state_id: str, reach_ident: str | None) -> list[tuple[str, str]]:
    """Record every destination one tap from `state_id`. `reach_ident` is the row from
    Settings that reaches it (None ⇒ state_id IS Settings). Returns new (child, ident)."""
    def reach() -> bool:
        if not ensure_settings(db):
            return False
        if reach_ident is None:
            return True
        tap(reach_ident); time.sleep(SETTLE)
        return at_here(db, state_id)

    if not reach():
        return []
    rows = db.state_actions(tree())["actions"]
    children: list[tuple[str, str]] = []
    for a in rows:
        if len(db.data["states"]) >= TARGET:
            break
        ident = (a["selector"] or {}).get("identifier")
        if not ident or avoided(a["label"], ident) or (state_id, ident) in visited:
            continue
        visited.add((state_id, ident))
        if not tap(ident):
            continue
        time.sleep(SETTLE)
        dest = tree()
        dest_id, matched, score = db.record_state(dest, notes={"summary": a["label"]})
        db.record_transition(state_id, {"label": a["label"], "gesture": "tap",
                                        "selector": {"identifier": ident}}, dest_id,
                             wait={"mode": "settle"})
        db.save()
        print(f"  {state_id} --{a['label'][:26]:26}--> {dest_id} "
              f"(score={score}){'  NEW' if not matched else ''}  [total={len(db.data['states'])}]")
        if not matched and dest_id != state_id:
            children.append((dest_id, ident if reach_ident is None else None))
        if not reach():            # re-anchor for the next row
            break
    return children


def main() -> None:
    global SETTINGS_ID
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    db = ex.ExplorerDB(DB_PATH)

    print("=== anchor: Home + Settings ===")
    home = tree()
    home_id, _, _ = db.record_state(home, notes={"summary": "Home"})
    tap("nav-settings-button"); time.sleep(SETTLE)
    SETTINGS_ID, _, _ = db.record_state(tree(), notes={"summary": "Settings menu"})
    db.record_transition(home_id, {"label": "open settings", "gesture": "tap",
                                   "selector": {"identifier": "nav-settings-button"}}, SETTINGS_ID)
    db.save()
    print(f"  Home={home_id}  Settings={SETTINGS_ID}")

    print(f"=== depth-1: Settings rows ===")
    depth1 = expand(db, SETTINGS_ID, None)

    print(f"=== depth-2: each menu destination (only reachable directly from Settings) ===")
    for child_id, child_ident in depth1:
        if len(db.data["states"]) >= TARGET:
            break
        if child_ident is None:
            continue
        expand(db, child_id, child_ident)

    print(f"\n=== DONE: {len(db.data['states'])} states, {len(db.data['transitions'])} transitions ===")
    for sid, s in db.data["states"].items():
        out = sum(1 for t in db.data["transitions"] if t["from"] == sid)
        print(f"  {sid}: {(s['notes'].get('summary') or '')[:38]:38} ({out} actions)")


if __name__ == "__main__":
    main()
