"""Autonomous WDA menu crawler (label-first). Fixes the earlier failure: rows are
enumerated from the tree via the engine's state_actions (Buttons addressed by LABEL
when they have no identifier), not filtered by identifier. DFS anchored on Settings,
pops with settings-back-button, recovers in-app if lost, avoids destructive rows,
records every state + transition, stops at TARGET.

Run with an active session, starting anywhere reachable. python3 wda_crawl.py
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
TARGET = 30
MAX_DEPTH = 4
SETTLE = 1.8

NAV = ("back", "close", "done", "dismiss", "skip", "info", "arrowleft", "tintable.close",
       "chevron", "show password")
AVOID = ("delete", "sign out", "signout", "log out", "logout", "switch plan", "switch-plan",
         "switch to", "med+", "med-plus", "billing", "purchase", "subscribe", "subscription",
         "payment", "redeem", "cancel", "remove", "reset", "clear", "manage account",
         "account", "send link", "continue", "forgot",
         "breastfeeding", "pregnant", "nursing",    # form questions that don't navigate cleanly
         "serving size")                            # value pickers (wheel) — hard to leave cleanly

SETTINGS_ID = None
LOSS_CAP = 12                       # global safety cap on recovery attempts
visited: set[tuple[str, str]] = set()
explored: set[str] = set()          # states whose children we already expanded
losses = 0


def tree() -> dict:
    return json.loads(subprocess.run(["lazyworker", "ui", "tree"],
                                     capture_output=True, text=True).stdout)


def ids_in(obs: dict) -> set[str]:
    return {n.get("identifier") for n in ex._walk(obs) if n.get("identifier")}


def tap_sel(sel: dict) -> bool:
    if sel.get("identifier"):
        args = ["lazyworker", "ui", "tap", "--identifier", sel["identifier"]]
    elif sel.get("label"):
        args = ["lazyworker", "ui", "tap", "--label", sel["label"]]
        if sel.get("type"):
            args += ["--type", sel["type"]]
    else:
        return False
    p = subprocess.run(args, capture_output=True, text=True)
    try:
        return json.loads(p.stdout).get("ok", False)
    except Exception:
        return False


def tap_id(identifier: str) -> None:
    subprocess.run(["lazyworker", "ui", "tap", "--identifier", identifier], capture_output=True)


def at(db: ex.ExplorerDB, state_id: str) -> bool:
    mid, score = db.match(tree())
    return score >= ex.SAME and mid == state_id


def recover_settings(db: ex.ExplorerDB) -> bool:
    for _ in range(8):
        if at(db, SETTINGS_ID):
            return True
        ids = ids_in(tree())
        if "settings-back-button" in ids:
            tap_id("settings-back-button")
        elif "nav-settings-button" in ids:
            tap_id("nav-settings-button")
        elif "settings-close-button" in ids:
            tap_id("settings-close-button")
        elif "xmark" in ids:                     # popover/picker dismiss
            tap_id("xmark")
        else:
            cl = next((n.get("label") for n in ex._walk(tree())
                       if any(w in (n.get("label") or "").lower()
                              for w in ("close", "cancel", "done"))), None)
            if not cl:
                return False
            subprocess.run(["lazyworker", "ui", "tap", "--label", cl], capture_output=True)
        time.sleep(SETTLE)
    return at(db, SETTINGS_ID)


def pop_to(db: ex.ExplorerDB, parent_id: str) -> bool:
    if "settings-back-button" in ids_in(tree()):
        tap_id("settings-back-button")
        time.sleep(SETTLE)
        if at(db, parent_id):
            return True
    if parent_id == SETTINGS_ID:
        return recover_settings(db)
    return at(db, parent_id)


def skip(label: str, sel: dict) -> bool:
    blob = f"{label} {sel.get('identifier') or ''} {sel.get('label') or ''}".lower()
    return any(w in blob for w in NAV) or any(w in blob for w in AVOID)


def replay(db: ex.ExplorerDB, state_id: str, path: list[dict]) -> bool:
    """Regain `state_id` after a loss: recover to Settings, then re-tap the path down."""
    if not recover_settings(db):
        return False
    for sel in path:
        tap_sel(sel)
        time.sleep(SETTLE)
    return at(db, state_id)


def explore(db: ex.ExplorerDB, state_id: str, obs: dict, depth: int, path: list[dict]) -> None:
    global losses
    if depth > MAX_DEPTH or len(db.data["states"]) >= TARGET or state_id in explored:
        return
    explored.add(state_id)
    for a in db.state_actions(obs)["actions"]:
        if len(db.data["states"]) >= TARGET:
            return
        sel = a["selector"] or {}
        label = a["label"] or sel.get("label") or sel.get("identifier") or ""
        key = sel.get("identifier") or sel.get("label") or ""
        if not key or skip(label, sel) or (state_id, key) in visited:
            continue
        visited.add((state_id, key))
        if not tap_sel(sel):
            continue
        time.sleep(SETTLE)
        dest = tree()
        dest_id, matched, score = db.record_state(dest, notes={"summary": label[:60]})
        db.record_transition(state_id, {"label": label[:60], "gesture": "tap", "selector": sel},
                             dest_id, wait={"mode": "settle"})
        db.save()
        print(f"  {'  '*depth}{state_id} --{label[:28]:28}--> {dest_id} "
              f"({'NEW' if not matched else 'dup'}, {score})  [total={len(db.data['states'])}]",
              flush=True)
        if dest_id != state_id and dest_id not in explored:
            explore(db, dest_id, dest, depth + 1, path + [sel])
        if dest_id != state_id and not pop_to(db, state_id):
            losses += 1
            print(f"  {'  '*depth}! lost under {label[:20]} — regaining parent ({losses})", flush=True)
            if losses >= LOSS_CAP:
                print("  loss cap reached — stopping", flush=True)
                return
            if not replay(db, state_id, path):   # re-navigate to this state and continue its rows
                return


def main() -> None:
    global SETTINGS_ID
    db = ex.ExplorerDB(DB_PATH)
    SETTINGS_ID = "st_0002"
    # seed already-fully-explored / unsafe depth-1 rows so we don't re-walk or get stuck
    for k in ("settings-app-settings-row", "settings-connected-devices-row",
              "settings-manage-account-account-row",
              "settings-health-conditions-row", "settings-program-settings-row",
              "settings-modes-row"):                 # confirmed in-place leaves
        visited.add((SETTINGS_ID, k))
    # already-explored subtrees + confirmed leaves; leave st_0005 (Goal settings) open to finish it
    explored.update({f"st_{i:04d}" for i in range(1, 25)} - {"st_0002", "st_0005"})
    # everything done except Settings(0002) and Goal settings(0005) -> finish Weight + Sleep settings
    print(f"start: {len(db.data['states'])} states; anchoring to Settings...", flush=True)
    if not recover_settings(db):
        print("could not anchor to Settings", flush=True)
        return
    explore(db, SETTINGS_ID, tree(), depth=1, path=[])
    print(f"=== DONE: {len(db.data['states'])} states, {len(db.data['transitions'])} transitions ===",
          flush=True)


if __name__ == "__main__":
    main()
