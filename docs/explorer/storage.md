# Explorer — Storage (cross-cutting)

How the knowledge store is persisted. This is the substrate every layer rests on.
It complements [`atom.md`](atom.md) (the screen record body) and is referenced by
the graph (states/transitions) and the deferred change/repair layer.

## Decisions

- **One local SQLite database** at `<app-repo>/.lazyworker/explorer.db`.
- **Local and private.** It is never committed; `.lazyworker/` is already gitignored.
- **Backup = copy one file.** Everything (including screenshots) lives in the `.db`,
  so a backup is atomic and trivial.
- **No second store.** SQLite is the single source of truth — there is no parallel
  JSON tree or flat graph cache. Document-shaped fields (raw tree, notes, provenance)
  are stored as JSON in `TEXT` columns and queried with SQLite's built-in `json1`
  (`json_extract`).

## Why SQLite alone

The store is local and single-user, so the usual reasons to prefer flat files —
git diffs, cross-developer merges, in-repo readability — do not apply. What remains
is best served by SQLite:

| Need | How SQLite serves it |
|---|---|
| Fast shortest-path queries | Indexed `transitions` table + recursive CTE, no full re-parse |
| Easy backup | A single file (screenshots as BLOB → truly atomic) |
| Long-term efficiency | Indexes scale; no growing JSON to re-parse each call |
| Zero new dependency | `sqlite3` is in the Python standard library |
| Repair as a transaction | A state and its transitions update atomically |
| Producer/consumer queue | Transactional enqueue/dequeue for the daemon seam |

A graph database (server or embedded) is overkill: the graph is small, the query
is a plain BFS, and a server/binary dependency would add operational weight and a
worse backup story.

## What this does NOT change: the bucket rule

[`atom.md`](atom.md) governs what may be persisted. SQLite does not relax it:

- **No `signals` table.** Signals stay derived — recomputed on the fly from the raw
  reference tree with the current algorithm, never stored.
- **No `colors` table.** Colours are a pure derivation of the screenshot; recomputed
  on demand (`textcolor.py`), never stored.

The database holds only raw facts, accumulated history, and authored notes.

## Agent-first is preserved

Agents never touch the `.db` directly. They call `lazyworker explorer …` commands
that emit **JSON**, exactly like the rest of the tool. `notes` remains queryable
through `json_extract`, so per-section retrieval works at the command layer.

## The git-diff anchor is preserved

The dimensionality-reduction trick (`git diff <sha>..HEAD` to bound where drift can
be) only needs the **app source** under git plus the app SHA stored *inside* each
record. The SHA is a column, so the trick works unchanged with a local database.

## Schema (structural shape)

Per-layer column details are defined in each layer's doc; this fixes the structure.

```sql
-- The atom. Source of truth: one row per state. See atom.md.
CREATE TABLE states (
  state_id       TEXT PRIMARY KEY,   -- opaque, stable handle (st_0001)
  bundle_id      TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  tree           TEXT NOT NULL,      -- raw AccessibilityNode (JSON) = source of truth
  notes          TEXT,               -- authored map (JSON), json_extract-able
  readiness      TEXT,               -- "arrived & ready" condition (JSON, no timeout)
  provenance     TEXT NOT NULL,      -- {learned, last_confirmed, last_modified} = commit SHAs
  captured_at    TEXT NOT NULL,      -- reference capture time (ISO 8601, UTC)
  app_commit     TEXT,               -- app HEAD SHA at capture (null if not in git)
  screen_w       INTEGER,
  screen_h       INTEGER,
  scale          REAL,               -- density (px/pt) — coordinate recomputability
  screenshot     BLOB                -- reference PNG, in-db for atomic backup
);

-- The relation. Directed multigraph; surrogate key allows parallel edges; from==to is
-- a self-transition (in-place state change). See transitions.md.
CREATE TABLE transitions (
  transition_id INTEGER PRIMARY KEY,
  from_id       TEXT NOT NULL REFERENCES states(state_id),
  to_id         TEXT NOT NULL REFERENCES states(state_id),
  action        TEXT NOT NULL,       -- {gesture, target:{selector,at}, params} -- replayable
  wait          TEXT,                -- wait strategy (JSON, no timeout; inherits to_state.readiness)
  kind          TEXT,                -- navigation | in_place | noop
  reliability   TEXT,                -- {confirmations, failures, last_confirmed}
  provenance    TEXT
);
CREATE INDEX tr_from ON transitions(from_id);   -- adjacency (out-edges)
CREATE INDEX tr_to   ON transitions(to_id);     -- reverse adjacency (how to reach X)
```

The **repair/evidence layer is deferred** — self-correction is too early to model
before the map is being built and read in practice. When it lands it adds an
`evidence` table (frozen before/action/after) as the daemon's producer/consumer seam.

## Graph model (recap)

A **directed multigraph**: nodes are states (opaque ids), transitions are directed
and carry `<action, wait>`. "Go and come back" is two distinct transitions; an
in-place change is a self-transition (`from == to`); cycles are handled by a
visited-set during traversal. Shortest path is computed by a recursive CTE over
`transitions`, preferring reliable ones.
