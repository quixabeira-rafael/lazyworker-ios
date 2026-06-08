"""Test the explorer engine against the REAL WebDriverAgent tree (not idb).

Reads the live WDA accessibility tree via `lazyworker ui tree`, runs it through
the explorer engine to (1) discover the screen identity and (2) list the actions
known from that screen. Learns one transition live so the action list is non-empty.

Run (with an active session: `lazyworker up && lazyworker ui open <bundle>`):
    python3 wda_identity.py
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


def lw(*args: str) -> dict:
    """Run a lazyworker command and parse its JSON stdout."""
    p = subprocess.run(["lazyworker", *args], capture_output=True, text=True)
    return json.loads(p.stdout) if p.stdout.strip() else {}


def tree() -> dict:
    return lw("ui", "tree")


def main() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    db = ex.ExplorerDB(DB_PATH)

    print("=== 1) DISCOVER IDENTITY (via WDA) ===")
    t1 = tree()
    a_id, matched, score = db.record_state(t1, notes={"summary": "Welcome / login"})
    print(f"  first read   -> recorded {a_id} (new state)")
    t2 = tree()
    best_id, best = db.match(t2)
    print(f"  second read  -> identified as {best_id} (score={round(best,2)}, matched={best>=ex.SAME})")

    print("\n=== 2) LEARN ONE TRANSITION (tap 'Log in') ===")
    subprocess.run(["lazyworker", "ui", "tap", "--identifier", "welcome-login-button",
                    "--wait", "settle"], capture_output=True, text=True)
    time.sleep(1.0)
    t3 = tree()
    b_id, b_matched, b_score = db.record_state(t3, notes={"summary": "After Log in"})
    db.record_transition(a_id, {"label": "tap Log in", "gesture": "tap",
                                "selector": {"identifier": "welcome-login-button"}},
                         b_id, wait={"mode": "settle"})
    db.save()
    print(f"  landed on {b_id} (matched_existing={b_matched})  | learned {a_id} --tap Log in--> {b_id}")

    print("\n=== 3) ACTIONS POSSIBLE FROM THE WELCOME SCREEN ===")
    result = db.actions_here(t1)
    print(f"  screen {result['state_id']} (score {result['score']}): "
          f"{len(result['actions'])} known action(s)")
    for act in result["actions"]:
        print(f"    - {act['label']:14} [{act['gesture']}] -> {act['to']} ({act['leads_to']})")


if __name__ == "__main__":
    main()
