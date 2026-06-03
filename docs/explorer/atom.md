# Explorer — Layer 1: the atom (screen record)

The **atom** is a single observation of the app at one instant, plus the durable
knowledge attached to it. It is the unit the whole explorer knowledge store is
built on.

This document registers the **body** of the atom: what is persisted per screen,
field by field. It does not cover identity/signal algorithms (Layer 2), the
navigation graph (Layer 3), matching (Layer 4), change detection (Layer 5), or
the repair loop (Layer 6).

## Persistence principle (the bucket rule)

What may enter the persistence layer is decided by what kind of data it is:

| Kind of data | Persisted? | Feeds signals? |
|---|---|---|
| Pure derivation of (raw + algorithm) — signals, hashes, scores | **No** | — |
| Raw fact from the app — reference tree, screenshot | **Yes** | Yes (recomputed) |
| Accumulated history — provenance, volatility | **Yes** | Yes (confidence prior) |
| Authored knowledge — `notes` | **Yes** | **No — agentic use only** |

Signals are **never** stored. They are recomputed on the fly, with the current
algorithm, from the raw reference tree and the live observation — so the store
can never fall out of sync with the matching code.

## `ScreenRecord`

The persisted body of one screen.

| Field | Type | Authored by | Required | Description |
|---|---|---|---|---|
| `schema_version` | int | tool | yes | Version of this model, for migration. Never set by hand. |
| `screen_id` | string | tool | yes | Opaque, stable, immutable handle (e.g. `scr_0001`). Edges reference it. Not derived from signals (so it survives algorithm changes). Agents reference it, never invent or change it. |
| `bundle_id` | string | tool | yes | The app this screen belongs to. |
| `notes` | object | **agent** | no | Free authored annotations, keyed by section. The agent's field. Never parsed for signals. See [`notes`](#notes). |
| `reference` | object | tool | yes | The canonical raw observation — the source of truth. See [`reference`](#reference). |
| `provenance` | object | tool | yes | Temporal envelope of when this knowledge was learned/confirmed/changed. See [`provenance`](#provenance). |

### `notes`

A map of free-text annotations. **Authored by the agent (or a human).** Each
value is free text and may be multi-line markdown. Retrieval is deterministic
through the bundled jq engine — the agent reads a section by key, never by
parsing prose.

```json
"notes": {
  "summary": "Login screen. Email + password.",
  "flow": "Successful login -> Home (scr_0007). 'Forgot password' opens a modal.",
  "gotchas": "Locks for 30s after 3 failed attempts.",
  "el:login_button": "Opens a paywall when the trial account is expired."
}
```

Canonical keys (soft convention — the agent always knows to look for these):

| Key | Holds |
|---|---|
| `summary` | One or two sentences: what this screen **is** and its purpose. Present tense, durable. |
| `flow` | Where actions lead, in human terms. Reference `screen_id`s when known. |
| `gotchas` | Warnings and edge conditions: rate limits, destructive actions, paywalls, flakiness. |
| `el:<ref>` | A per-element behavioural note, keyed by the element's `ref`. |

Rules for the author:
- Any other key is allowed; prefer lowercase-kebab keys for predictable grep/jq.
- Write **durable facts**, never transient content (no specific usernames, counts,
  timestamps) — that belongs to the live observation, not the annotation.
- Do not restate signals (types, identifiers, structure). Notes add intent and
  behaviour the tree cannot express.
- Keep it concise.

Agent access (deterministic, no prose parsing):

| Want | Command |
|---|---|
| List available sections | `jq '.notes \| keys'` |
| Read one section | `jq -r '.notes.gotchas'` |
| Read an element note | `jq -r '.notes."el:login_button"'` |
| Search across screens | `jq 'select(.notes \| to_entries[] \| .value \| test("paywall";"i"))'` |

### `reference`

The canonical raw observation: the **source of truth** from which every signal
is recomputed. **Captured by the tool**, never hand-authored.

| Field | Type | Description |
|---|---|---|
| `captured_at` | string (ISO 8601, UTC) | When the observation was captured. |
| `app_commit` | string \| null | App repo `HEAD` SHA at capture (`git rev-parse HEAD`). `null` when the app is not under git. The exact anchor for `git diff <sha>..HEAD`. |
| `screen_size` | [int, int] | Screen size in points: `[width, height]`. |
| `tree` | object | The raw `AccessibilityNode` tree, verbatim. Stored whole, with no field trimming — trimming would bake interpretation into storage. |
| `screenshot` | string | Path to the reference PNG, relative to the store root. |

### `provenance`

Accumulated temporal history. **Maintained by the tool.** Each entry pairs a
timestamp with the app SHA at that moment.

| Field | Type | Description |
|---|---|---|
| `learned_at` | {`at`, `commit`} | First time this screen was seen and recorded. |
| `last_confirmed_at` | {`at`, `commit`} | Last time a match confirmed this knowledge as still valid. |
| `last_modified_at` | {`at`, `commit`} | Last time this record was repaired/updated. |

Counters that feed the confidence prior (e.g. confirmations, drifts) live with
Layer 4 (matching), not here.

## Full example

```json
{
  "schema_version": 1,
  "screen_id": "scr_0001",
  "bundle_id": "com.example.app",
  "notes": {
    "summary": "Login screen. Email + password.",
    "flow": "Successful login -> Home (scr_0007). 'Forgot password' opens a modal.",
    "gotchas": "Locks for 30s after 3 failed attempts.",
    "el:login_button": "Opens a paywall when the trial account is expired."
  },
  "reference": {
    "captured_at": "2026-06-01T09:00:00Z",
    "app_commit": "e814719",
    "screen_size": [393, 852],
    "tree": { "type": "Application", "children": ["..."] },
    "screenshot": "screens/scr_0001.png"
  },
  "provenance": {
    "learned_at":        { "at": "2026-06-01T09:00:00Z", "commit": "e814719" },
    "last_confirmed_at": { "at": "2026-06-03T12:00:00Z", "commit": "1bb1c51" },
    "last_modified_at":  { "at": "2026-06-02T15:00:00Z", "commit": "7aaee8f" }
  }
}
```
