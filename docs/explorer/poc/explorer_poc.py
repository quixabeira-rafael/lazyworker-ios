"""Explorer POC — a single JSON-file database of States + Transitions.

Validates, end to end and self-contained (stdlib only, synthetic data):
  - the persisted structure (states + transitions) in one .json file;
  - the generic identity function (feature vector + IDF, no app-specific hardcoding);
  - online clustering on record (dedup the same screen, mint a new id otherwise);
  - filtered, contextual verification of `state A --action B--> ?`;
  - the "unexpected result" signal (confirmed / no_op / wrong_destination / unknown).

Run: python3 explorer_poc.py
"""

from __future__ import annotations

import json
import math
import os
import unicodedata
from collections import Counter

SAME, DIFF = 0.85, 0.35
INTERACTIVE = {"Button", "Cell", "Switch", "TextField", "SecureTextField", "Slider", "Link"}
WEIGHTS = {"id_set": 3.0, "type_counts": 2.0, "text_set": 1.0, "scalars": 1.0}
TITLE_WEIGHT = {"navbar": 3.5, "guess": 2.0}
DB_PATH = os.path.join(os.path.dirname(__file__), "explorer_db.json")


# --- feature extraction (generic: no app-specific ids/prefixes) ---

def _norm(text: str) -> str:
    if not text:
        return ""
    d = unicodedata.normalize("NFKD", text)
    return " ".join("".join(c for c in d if not unicodedata.combining(c)).lower().split())


def _walk(node):
    yield node
    for child in node.get("children", []) or []:
        yield from _walk(child)


def features(tree: dict) -> dict:
    nodes = [n for n in _walk(tree) if n.get("visible", True)]
    ids = {n["identifier"] for n in nodes if n.get("identifier")}
    type_counts = Counter(n.get("type") for n in nodes)
    text = {_norm(n.get(f) or "") for n in nodes for f in ("label", "value", "name") if _norm(n.get(f) or "")}
    navbar = next((n for n in nodes if n.get("type") == "NavigationBar"), None)
    if navbar is not None:
        title = _norm(navbar.get("name") or navbar.get("label") or "")
        title_src = "navbar"
    else:  # heuristic guess: the first text in reading order
        statics = [_norm(n.get("label") or n.get("value") or "") for n in nodes
                   if n.get("type") == "StaticText" and _norm(n.get("label") or n.get("value") or "")]
        title = statics[0] if statics else None
        title_src = "guess"
    return {
        "ids": ids, "type_counts": type_counts, "text": text,
        "title": title, "title_src": title_src,
        "interactive": sum(1 for n in nodes if n.get("type") in INTERACTIVE),
        "text_count": len(text),
    }


# --- similarity primitives ---

def _idf_jaccard(a: set, b: set, idf: dict, default: float) -> float:
    inter = sum(idf.get(x, default) for x in a & b)
    union = sum(idf.get(x, default) for x in a | b)
    return inter / union if union else 0.0


def _count_sim(a: Counter, b: Counter) -> float:
    keys = set(a) | set(b)
    num = sum(abs(a.get(k, 0) - b.get(k, 0)) for k in keys)
    den = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
    return 1 - num / den if den else 1.0


def _scalar(a: int, b: int) -> float:
    return 1 - abs(a - b) / max(a, b, 1)


def identity(fa: dict, fb: dict, idf: dict, tidf: dict, default: float) -> float:
    """Weighted feature-vector similarity in [0,1], normalized over present features."""
    parts, weights = {}, {}
    if fa["ids"] and fb["ids"]:
        parts["id_set"] = _idf_jaccard(fa["ids"], fb["ids"], idf, default)
        weights["id_set"] = WEIGHTS["id_set"]
    if fa["title"] and fb["title"]:
        parts["title"] = 1.0 if fa["title"] == fb["title"] else 0.0
        # weight by EXTRACTION SOURCE: a structural navbar title is trusted more than a guess
        src = "navbar" if fa["title_src"] == "navbar" and fb["title_src"] == "navbar" else "guess"
        weights["title"] = TITLE_WEIGHT[src]
    parts["type_counts"] = _count_sim(fa["type_counts"], fb["type_counts"])
    weights["type_counts"] = WEIGHTS["type_counts"]
    if fa["text"] and fb["text"]:
        parts["text_set"] = _idf_jaccard(fa["text"], fb["text"], tidf, default)
        weights["text_set"] = WEIGHTS["text_set"]
    parts["scalars"] = (_scalar(fa["interactive"], fb["interactive"]) + _scalar(fa["text_count"], fb["text_count"])) / 2
    weights["scalars"] = WEIGHTS["scalars"]
    return sum(parts[k] * weights[k] for k in parts) / sum(weights.values())


def band(score: float) -> str:
    return "SAME" if score >= SAME else "DIFF" if score <= DIFF else "ESCALATE"


# --- the JSON-file database ---

class ExplorerDB:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self.data = {"schema_version": 1, "next_id": 1, "states": {}, "transitions": []}
        if os.path.exists(path):
            self.data = json.load(open(path))

    def save(self):
        json.dump(self.data, open(self.path, "w"), indent=2)

    def _idf(self, extra: list[dict] | None = None):
        feats = [features(s["reference"]["tree"]) for s in self.data["states"].values()]
        feats += extra or []
        n = max(len(feats), 1)
        default = math.log(n + 1)
        df = Counter(i for f in feats for i in f["ids"])
        tdf = Counter(t for f in feats for t in f["text"])
        idf = {i: math.log(n / df[i]) if df[i] < n else 0.0 for i in df}
        tidf = {t: math.log(n / tdf[t]) if tdf[t] < n else 0.0 for t in tdf}
        return idf, tidf, default

    def match(self, observation: dict):
        """1-vs-N (cold-discovery path): best matching state id + score, or (None, 0)."""
        fo = features(observation)
        idf, tidf, default = self._idf(extra=[fo])
        best_id, best = None, 0.0
        for sid, s in self.data["states"].items():
            sc = identity(fo, features(s["reference"]["tree"]), idf, tidf, default)
            if sc > best:
                best_id, best = sid, sc
        return best_id, best

    def record_state(self, observation: dict, notes: dict | None = None, app_commit: str | None = None):
        best_id, best = self.match(observation)
        if best >= SAME:                     # online clustering: it's a known state
            return best_id, True, round(best, 2)
        sid = f"st_{self.data['next_id']:04d}"
        self.data["next_id"] += 1
        self.data["states"][sid] = {
            "state_id": sid, "schema_version": 1,
            "reference": {"tree": observation, "app_commit": app_commit},
            "notes": notes or {},
            "provenance": {"learned": app_commit, "last_confirmed": app_commit, "last_modified": app_commit},
        }
        return sid, False, round(best, 2)

    def record_transition(self, from_id, action, to_id, wait=None, kind="navigation"):
        self.data["transitions"].append({
            "from": from_id, "to": to_id, "action": action,
            "wait": wait, "kind": kind,
            "reliability": {"confirmations": 1, "failures": 0},
        })

    def verify(self, from_id: str, action_label: str, observation: dict) -> dict:
        """Contextual (filtered) verification → the unexpected-result signal."""
        fo = features(observation)
        idf, tidf, default = self._idf(extra=[fo])

        def sim_to(sid):
            return identity(fo, features(self.data["states"][sid]["reference"]["tree"]), idf, tidf, default)

        edge = next((t for t in self.data["transitions"]
                     if t["from"] == from_id and t["action"].get("label") == action_label), None)
        expected = edge["to"] if edge else None

        s_expected = sim_to(expected) if expected else 0.0
        s_from = sim_to(from_id)

        if expected and s_expected >= SAME:
            verdict, dest = "confirmed", expected
        elif s_from >= SAME:
            verdict, dest = "no_op", from_id            # action did not move us
        else:                                            # surprise → broaden the search
            best_id, best = self.match(observation)
            if best >= SAME:
                verdict, dest = ("wrong_destination", best_id) if best_id != expected else ("confirmed", best_id)
            else:
                verdict, dest = "unknown_destination", None
        return {
            "from": from_id, "action": action_label, "expected": expected,
            "verdict": verdict, "landed_on": dest,
            "score_expected": round(s_expected, 2), "score_from": round(s_from, 2),
            "unexpected": verdict != "confirmed",
        }


# --- demo / validation ---

def node(t, ident=None, label=None, value=None, children=None, visible=True):
    n = {"type": t, "visible": visible}
    if ident: n["identifier"] = ident
    if label: n["label"] = label
    if value: n["value"] = value
    if children: n["children"] = children
    return n


def login_screen(switch="0"):
    return node("Window", children=[
        node("NavigationBar", label="Sign in"),
        node("TextField", ident="email_field", label="Email"),
        node("SecureTextField", ident="password_field", label="Password"),
        node("Switch", ident="remember_me", value=switch, label="Remember me"),
        node("Button", ident="login_button", label="Continue"),
    ])


def home_screen(greeting="Welcome back"):     # dynamic content (greeting changes), stable identity
    return node("Window", children=[
        node("NavigationBar", label="Home"),
        node("StaticText", label=greeting),
        node("Cell", ident="card_steps", label="Steps"),
        node("Cell", ident="card_water", label="Water"),
        node("Button", ident="profile_button", label="Profile"),
    ])


def error_screen():
    return node("Window", children=[
        node("NavigationBar", label="Error"),
        node("StaticText", label="Invalid credentials"),
        node("Button", ident="retry_button", label="Try again"),
    ])


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    db = ExplorerDB()

    print("=== build the map ===")
    login_id, matched, _ = db.record_state(login_screen(), notes={"summary": "Login screen."}, app_commit="c0ffee1")
    print(f"record login        -> {login_id}  (matched={matched})")
    home_id, matched, _ = db.record_state(home_screen(), notes={"summary": "Home dashboard."}, app_commit="c0ffee1")
    print(f"record home         -> {home_id}  (matched={matched})")

    # online clustering: the SAME home with different dynamic content must dedup
    same_id, matched, score = db.record_state(home_screen(greeting="Good morning"), app_commit="c0ffee1")
    print(f"record home (other greeting) -> {same_id}  (matched={matched}, score={score})  <- dedup, content != identity")

    db.record_transition(login_id, {"label": "tap login_button", "gesture": "tap",
                                     "selector": {"identifier": "login_button"}},
                         home_id, wait={"mode": "until", "predicate": {"key": "identifier", "value": "card_steps"}})
    print(f"record transition   {login_id} --tap login_button--> {home_id}")
    db.save()
    print(f"\nDB written to {os.path.basename(DB_PATH)}: "
          f"{len(db.data['states'])} states, {len(db.data['transitions'])} transitions")

    print("\n=== contextual verification (state A --action B--> ?) ===")
    scenarios = [
        ("expected outcome (home, dynamic content)", home_screen(greeting="Hi again")),
        ("switch toggled on the way (still home)", home_screen()),
        ("UNEXPECTED: landed on an error screen", error_screen()),
        ("NO-OP: still on the login screen", login_screen(switch="1")),
    ]
    for desc, obs in scenarios:
        r = db.verify(login_id, "tap login_button", obs)
        flag = "  <-- UNEXPECTED RESULT" if r["unexpected"] else ""
        print(f"  {desc:42} -> {r['verdict']:20} "
              f"(expected={r['expected']} got_score={r['score_expected']}){flag}")


if __name__ == "__main__":
    main()
