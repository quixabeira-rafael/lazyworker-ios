# Explorer — the atom (State)

The explorer's knowledge is a graph. Its **atom is the State**; the relation
between states is the **Transition** (see [`transitions.md`](transitions.md)).
This document registers the State model.

## Conceptual hierarchy

```
Observation  = raw substrate: one snapshot (tree + screenshot) at an instant.
State        = THE ATOM: an identity class. Its `reference` is one canonical observation.
Transition   = the relation between two states, carrying <action, wait>.
Loop         = state -> action -> wait -> state'  (how knowledge is observed and verified)
```

A State is identified by its **signals** (structure, identifiers, nav title,
visual fingerprint, …), which are **recomputed on the fly and never stored**.
Dynamic content does **not** mint a new state — only an identity change does; a
content/control change within the same identity is a self-transition.

## Persistence principle (the bucket rule)

| Kind of data | Persisted? |
|---|---|
| Pure derivation of (raw + algorithm) — signals, colours, hashes, scores, rendered commands | **No** (recomputed on the fly) |
| Raw fact from the app — reference tree, screenshot, screen size/scale | **Yes** (source of truth) |
| Accumulated history — provenance, reliability, readiness | **Yes** |
| Authored knowledge — `notes` | **Yes** (agentic use only) |

There is **no `signals` table and no `colors` table** — both are derived and
recomputed with the current algorithm, so the store can never fall out of sync
with the matching/identity code.

## `State`

| field | authored by | description |
|---|---|---|
| `state_id` | tool | Opaque, stable, immutable handle (`st_0001`). Transitions reference it. Never derived from signals (survives algorithm changes). Agents reference it, never invent it. |
| `bundle_id` | tool | The app this state belongs to. |
| `schema_version` | tool | Model version, for migration. |
| `reference` | tool | The canonical raw observation — source of truth. See below. |
| `readiness` | learned (+ authored override) | The intrinsic "arrived & ready here" condition, reused by every incoming transition. Condition-based, **no timeout**. See below. |
| `notes` | **agent** | Free authored annotations, keyed by section. Never used for matching. See [`notes`](#notes). |
| `provenance` | tool | When this knowledge was learned/confirmed/modified, anchored to app commits. See below. |

### `reference`

The canonical raw observation. **Captured by the tool**, never hand-authored.

```jsonc
{
  "captured_at": "2026-06-03T12:00:00Z",
  "app_commit": "1bb1c51",        // app HEAD SHA at capture (null if not in git); git-diff anchor
  "screen_size": [393, 852],      // points
  "scale": 3.0,                   // density (px/pt) — lets coordinates be recomputed across screens
  "tree": { "...": "raw AccessibilityNode" },
  "screenshot": "<BLOB>"          // reference PNG (in-db, atomic backup)
}
```

The raw `tree` is stored whole, with no field trimming — trimming would bake
interpretation into storage. `scale` is captured from `session.screen_info()`.

### `readiness`

The condition that means "I have arrived at this state and it is loaded." It is
**learned** (observed across arrivals) with an optional authored override, and it
is **condition-based** — it never stores a timeout (a timeout is runtime policy,
not knowledge; the runtime applies a default safety ceiling).

```jsonc
{
  "mode": "until",                              // settle | until | gone | tree
  "predicate": { "key": "identifier", "value": "home-root" }   // for until/gone
}
```

Every transition arriving at this state inherits this readiness as its `wait`
(see [`transitions.md`](transitions.md)). Knowing the *right* wait condition is
what lets the tool move fast — it proceeds the instant the condition holds.

### `notes`

A map of free-text annotations, **authored by the agent (or a human)**, never
parsed for signals. Retrieval is deterministic through the bundled jq engine.

```jsonc
"notes": {
  "summary": "Home / dashboard.",
  "flow": "Menu opens settings (st_0006).",
  "gotchas": "The 'For You' cards reload on every visit.",
  "el:home-points-tile-card": "Opens the points detail."
}
```

Canonical keys (soft convention; any other lowercase-kebab key is allowed):
`summary` (what this state is), `flow` (where actions lead; reference state_ids),
`gotchas` (warnings: rate limits, destructive actions, paywalls, flakiness),
`el:<ref>` (a per-element note). Write durable facts only — no transient content
(usernames, counts, timestamps) and no restatement of signals.

Agent access (no prose parsing): `jq '.notes | keys'`, `jq -r '.notes.gotchas'`,
`jq -r '.notes."el:home-points-tile-card"'`.

### `provenance`

Accumulated history, anchored to **app commits** (the date of each is derived from
the commit via `git show -s --format=%cI <sha>`, so no timestamp is stored — a
stored date would duplicate the commit).

```jsonc
{
  "learned":        "e814719",   // commit where first seen
  "last_confirmed": "1bb1c51",   // commit of the last confirming match
  "last_modified":  "7aaee8f"    // commit of the last repair
}
```

For staleness, a commit anchor beats a wall-clock: `git diff <sha>..HEAD` says
whether the relevant code actually changed, which is more precise than time decay.
Fallback: when the app is **not** in git (`app_commit` null), store a wall-clock
ISO timestamp instead — only in that case.
