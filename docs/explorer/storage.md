# Explorer — Storage (cross-cutting)

How the knowledge store is persisted. This is the substrate every layer rests on.
It complements [`atom.md`](atom.md) (the screen record body) and is referenced by
the graph layer (nodes/edges) and the change/repair layers (evidence queue).

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
| Fast shortest-path queries | Indexed `edges` table + recursive CTE, no full re-parse |
| Easy backup | A single file (screenshots as BLOB → truly atomic) |
| Long-term efficiency | Indexes scale; no growing JSON to re-parse each call |
| Zero new dependency | `sqlite3` is in the Python standard library |
| Repair as a transaction | A screen and its edges update atomically |
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
-- Source of truth: one row per screen.
CREATE TABLE screens (
  screen_id      TEXT PRIMARY KEY,   -- opaque, stable handle (scr_0001)
  bundle_id      TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  tree           TEXT NOT NULL,      -- raw AccessibilityNode (JSON) = source of truth
  notes          TEXT,               -- authored map (JSON), json_extract-able
  provenance     TEXT NOT NULL,      -- {learned_at, last_confirmed_at, last_modified_at}
  captured_at    TEXT NOT NULL,      -- reference capture time (ISO 8601, UTC)
  app_commit     TEXT,               -- app HEAD SHA at capture (null if not in git)
  screen_w       INTEGER,
  screen_h       INTEGER,
  screenshot     BLOB                -- reference PNG, in-db for atomic backup
);

-- Directed multigraph. A surrogate key allows parallel edges between the same pair.
CREATE TABLE edges (
  edge_id     INTEGER PRIMARY KEY,
  from_id     TEXT NOT NULL REFERENCES screens(screen_id),
  to_id       TEXT NOT NULL REFERENCES screens(screen_id),
  action      TEXT NOT NULL,         -- {gesture, selector, input?} -- replayable
  reliability TEXT,                  -- Layer 4 detail
  provenance  TEXT
);
CREATE INDEX edges_from ON edges(from_id);   -- adjacency (out-edges)
CREATE INDEX edges_to   ON edges(to_id);     -- reverse adjacency (how to reach X)

-- Repair-request queue carrying frozen evidence (the daemon seam, Layer 5).
CREATE TABLE evidence (
  evidence_id        INTEGER PRIMARY KEY,
  expected_screen_id TEXT,                   -- what the map predicted
  observed_tree      TEXT NOT NULL,          -- frozen diverging snapshot (JSON)
  observed_shot      BLOB,                   -- frozen screenshot at detection
  action             TEXT,                   -- what was done, from where, at what confidence
  created_at         TEXT NOT NULL,
  app_commit         TEXT,
  status             TEXT NOT NULL           -- pending | done
);
```

## Graph model (recap)

A **directed multigraph**: nodes are screens (opaque ids), edges are directed and
carry the replayable **action**. "Go and come back" is two distinct edges (the back
action is its own learned edge); cycles are handled by a visited-set during
traversal. Shortest path is computed by a recursive CTE over `edges`, preferring
reliable edges. Details in the graph layer doc.
