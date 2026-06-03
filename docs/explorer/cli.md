# Explorer — CLI contract

How an agent persists and reads explorer knowledge. The store (a local SQLite db,
see [`storage.md`](storage.md)) is never touched directly — every interaction goes
through `lazyworker explorer …` commands that emit JSON, like the rest of the tool.

## Design rule: nothing implicit, the tool teaches itself

The agent must be able to learn to use this with **no out-of-band knowledge**. This
is a hard requirement, not a nicety:

- **Discoverable contract.** `explorer schema` (and `--json`, `--example`) describe
  every field, its type, its constraints, and how to fill it. Mirrors `ui schema`.
- **Instructive errors.** A validation failure names the field, states the violated
  expectation, and gives the remedy — never a bare "invalid".
- **Every result carries the next step.** Outputs include a `hint` / ready-to-copy
  command, the way `ui find` attaches action tips per element.
- **Authored vs captured is always explicit.** The agent is told exactly which
  fields it supplies and which the tool captures from the live session — it never
  has to guess.

## Single source of truth (metaprogramming)

Each persisted model is one pydantic v2 model. From that single definition the tool
derives, with no parallel maintenance:

| Derived from the model | Used for |
|---|---|
| `model_json_schema()` | `explorer schema --json` — the machine-readable contract |
| `Field(description=…)` | the per-field guidance the agent reads |
| validation | rejects out-of-spec values with an instructive error |
| serialization | reads/writes the SQLite JSON columns |

The agent-facing input model contains **only authored fields** (`ScreenAnnotationInput`
— essentially `notes`); the full `ScreenRecord` (raw tree, screenshot, provenance,
ids) is captured by the command, not by the agent.

## Commands

### `explorer schema`

Describe the input contract. Read-only, no session needed.

| Form | Output |
|---|---|
| `explorer schema` | Human-readable: `YOU PROVIDE` (notes + canonical keys + rules) vs `CAPTURED FOR YOU` (screen_id, tree, screenshot, app_commit, provenance). |
| `explorer schema --json` | JSON Schema of `ScreenAnnotationInput`, descriptions included. |
| `explorer schema --example` | A concrete, fillable example JSON to copy and edit. |

### `explorer record`

Capture the current screen from the active session, attach optional authored notes,
validate, persist, and return the stored record. Needs an active session (`ui open`).

- **Input** (optional): authored fields as JSON via stdin or `--file`, same idiom as
  `ui batch`. With no input, it records the raw observation and the agent annotates later.
- **Captured by the tool**: tree, screenshot, app `HEAD` SHA, screen size, provenance,
  and the `screen_id` (newly assigned, or matched to an existing screen).
- **Output**: JSON with `ok`, `screen_id`, `matched` (new vs matched existing),
  a `captured` summary, the stored `notes`, and a `hint` for the next step.

```jsonc
// echo '{"notes":{"summary":"Login screen. Email + password."}}' | lazyworker explorer record
{
  "ok": true,
  "screen_id": "scr_0007",
  "matched": false,
  "captured": { "app_commit": "1bb1c51", "screen_size": [393, 852], "elements": 12 },
  "notes": { "summary": "Login screen. Email + password." },
  "hint": "annotate later: lazyworker explorer annotate scr_0007"
}
```

### `explorer annotate <screen_id>`

Add or update authored notes on a screen that already exists. Authoring after the
fact, separate from capture.

- **Input**: `notes` JSON via stdin or `--file`. Keys are merged into the existing
  `notes` map (a section is updated by re-sending its key).
- **Output**: the updated `notes` and `screen_id`.

## Exit codes

Reuse the established `ui` scheme (see `cli.py`): `0` ok, `10` no_session,
`30` invalid_target (validation failure), plus the WDA/connection codes. A validation
failure exits `30` with an instructive message naming the field and the fix.
