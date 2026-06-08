"""Read the live screen via idb, identify it against the explorer DB, and print
the actions/transitions known to be possible from here.

Run: python3 actions_here.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import explorer_poc as ex
import idb_backend as idb

UDID = os.environ.get("IDB_UDID", "A7D5487A-2EC7-47D4-8207-C487EE2A3F50")
DB_PATH = os.path.join(os.path.dirname(__file__), "explorer_idb_db.json")


def main():
    idb.connect(UDID)
    db = ex.ExplorerDB(DB_PATH)
    obs = idb.describe(UDID)
    result = db.actions_here(obs)

    if not result["matched"]:
        print(f"unknown screen (best score {result['score']}) — nothing learned from here yet")
        return
    sid = result["state_id"]
    summary = (db.data["states"][sid].get("notes") or {}).get("summary", "")
    print(f"current screen: {sid}  ({summary})  [identity score {result['score']}]")
    if not result["actions"]:
        print("no outgoing transitions learned from this state yet")
        return
    print(f"{len(result['actions'])} action(s) possible from here:")
    for a in result["actions"]:
        print(f"  - {a['label']:14} [{a['gesture']}] -> {a['to']} ({a['leads_to']})")


if __name__ == "__main__":
    main()
