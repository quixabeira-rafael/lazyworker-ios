"""WDA-native explorer driver. Reads the live WDA tree via `lazyworker ui tree`
and drives the explorer engine against it. Persistent DB (not reset per call).

Subcommands:
    record "<summary>"          read current screen, record/dedup, print id+score
    match                       read current screen, best match + band
    actions                     read current screen, identify + list learned actions
    transition <from> "<lbl>" <to> [identifier]   learn an edge
    reset                       start a fresh DB

Run with an active session (lazyworker up && ui open <bundle>).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import explorer_poc as ex

DB_PATH = os.path.join(os.path.dirname(__file__), "explorer_wda_db.json")


def tree() -> dict:
    p = subprocess.run(["lazyworker", "ui", "tree"], capture_output=True, text=True)
    return json.loads(p.stdout)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "match"
    if cmd == "reset":
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        print("db reset")
        return

    db = ex.ExplorerDB(DB_PATH)

    if cmd == "record":
        note = sys.argv[2] if len(sys.argv) > 2 else ""
        sid, matched, score = db.record_state(tree(), notes={"summary": note})
        db.save()
        print(f"{sid}  matched={matched}  score={score}  ({note})")

    elif cmd == "match":
        best_id, best = db.match(tree())
        print(f"best={best_id}  score={round(best, 2)}  band={ex.band(best)}")

    elif cmd == "actions":
        r = db.actions_here(tree())
        print(f"screen={r['state_id']}  score={r['score']}  matched={r['matched']}  "
              f"actions={len(r['actions'])}")
        for a in r["actions"]:
            print(f"  - {a['label']:18} [{a['gesture']}] -> {a['to']} ({a['leads_to']})")

    elif cmd == "transition":
        from_id, label, to_id = sys.argv[2], sys.argv[3], sys.argv[4]
        ident = sys.argv[5] if len(sys.argv) > 5 else None
        sel = {"identifier": ident} if ident else {"type": "Button", "label": label}
        db.record_transition(from_id, {"label": label, "gesture": "tap", "selector": sel},
                             to_id, wait={"mode": "settle"})
        db.save()
        print(f"learned {from_id} --{label}--> {to_id}")

    elif cmd == "here":
        r = db.state_actions(tree())
        tag = f"state {r['state_id']}" if r["known"] else f"new/unknown state (score {r['score']})"
        print(f"landed on: {tag}  |  {r['action_count']} actions available")
        for a in r["actions"]:
            arrow = f" -> {a['leads_to']}" if a["leads_to"] else (" (learned)" if a["learned"] else "")
            print(f"  [{a['type']:7}] {a['label'][:46]:46} {arrow}")

    elif cmd == "list":
        for sid, s in db.data["states"].items():
            print(f"  {sid}: {s['notes'].get('summary')}")
        for t in db.data["transitions"]:
            print(f"  {t['from']} --{t['action'].get('label')}--> {t['to']}")


if __name__ == "__main__":
    main()
