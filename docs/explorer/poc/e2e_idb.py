"""End-to-end explorer POC driven by idb (read + act), with the honest caveat
that idb's accessibility surface OMITS some chrome (e.g. the hamburger/tab bar
on this app). So chrome targets are replayed by STORED COORDINATE (learned once,
e.g. via WDA/visual); content targets (menu rows) are resolved from idb directly.

Loop exercised on real idb data + actions:
  READ (idb describe-all) -> IDENTITY (engine) -> RECORD (JSON DB) ->
  NAVIGATE (idb tap, from the DB path) -> VERIFY (idb describe-all + identity signal).

Prereq: iOS Simulator + idb_companion reachable.  Run: python3 e2e_idb.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import explorer_poc as ex
import idb_backend as idb

UDID = os.environ.get("IDB_UDID", "A7D5487A-2EC7-47D4-8207-C487EE2A3F50")
BUNDLE = os.environ.get("WW_BUNDLE", "com.weightwatchers.wwmobile")
DB_PATH = os.path.join(os.path.dirname(__file__), "explorer_idb_db.json")

# chrome NOT exposed by idb on this app — coordinate is durable knowledge (learned via WDA/visual)
HAMBURGER_COORD = (32, 78)
HAMBURGER = {"identifier": "hamburger-menu-button"}
MODES_ROW = {"identifier": "settings-modes-row"}


def reset_home():
    subprocess.run(["xcrun", "simctl", "terminate", UDID, BUNDLE], capture_output=True)
    subprocess.run(["xcrun", "simctl", "launch", UDID, BUNDLE], capture_output=True)
    for _ in range(20):
        time.sleep(1.5)
        obs = idb.describe(UDID)
        if any((n.get("identifier") or "").startswith("home-") for n in obs["children"]):
            return obs
    return idb.describe(UDID)


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    idb.connect(UDID)
    db = ex.ExplorerDB(DB_PATH)

    print("=== COLD / discovery — read+identity+record, via idb ===")
    home = reset_home()
    home_id, _, _ = db.record_state(home, notes={"summary": "Home"})
    print(f"  home  -> {home_id}  (idb els={len(home['children'])})")

    # home -> menu : hamburger is NOT in idb's tree -> use stored coordinate
    idb.tap(UDID, *HAMBURGER_COORD); time.sleep(2.0)
    menu = idb.describe(UDID)
    menu_id, _, _ = db.record_state(menu, notes={"summary": "Menu"})
    db.record_transition(home_id, {"label": "open menu", "gesture": "tap",
                                    "selector": HAMBURGER, "target": {"at": list(HAMBURGER_COORD)}}, menu_id)
    print(f"  menu  -> {menu_id}  (idb els={len(menu['children'])})")

    # menu -> modes : the row IS in idb's tree -> resolve coordinate from idb
    mc = idb.resolve(menu, MODES_ROW)
    print(f"  modes-row resolvido no idb: {mc}")
    idb.tap(UDID, *mc); time.sleep(2.0)
    modes = idb.describe(UDID)
    modes_id, _, _ = db.record_state(modes, notes={"summary": "Modes"})
    db.record_transition(menu_id, {"label": "open modes", "gesture": "tap",
                                    "selector": MODES_ROW, "target": {"at": list(mc)}}, modes_id)
    db.save()
    print(f"  modes -> {modes_id}  (idb els={len(modes['children'])})")
    print(f"  MAP: {len(db.data['states'])} states, {len(db.data['transitions'])} transitions")

    print("\n=== WARM / replay — DB path -> idb taps (stored coords) -> identity verify ===")
    reset_home()
    path = db.shortest_path(home_id, modes_id)
    t0 = time.time()
    cur = home_id
    for t in path:
        coord = t["action"]["target"]["at"]          # stored coordinate (durable)
        idb.tap(UDID, *coord); time.sleep(1.5)
        obs = idb.describe(UDID)
        r = db.verify(cur, t["action"]["label"], obs)  # the unexpected-result signal, on idb data
        flag = "✅" if not r["unexpected"] else "⚠️ UNEXPECTED"
        print(f"  idb tap {coord} -> {r['verdict']} (expected={r['expected']} score={r['score_expected']}) {flag}")
        cur = t["to"]
    print(f"\n>>> goto Modes — replay+verify 100% idb: {time.time() - t0:.2f}s")


if __name__ == "__main__":
    main()
