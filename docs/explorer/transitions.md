# Explorer — Transitions

A **Transition** is the relation between two [States](atom.md): the directed edge
`from_state --<action, wait>--> to_state`. It is where all the *dynamic* knowledge
lives (how to act, how to wait, how reliable it is). The graph is a **directed
multigraph**: parallel edges between the same pair are allowed (a surrogate key),
and `from == to` is a **self-transition** — an in-place state change (a button that
mutates the same state without navigating).

## `Transition`

| field | authored by | description |
|---|---|---|
| `transition_id` | tool | Surrogate key (allows parallel edges). |
| `from_state` / `to_state` | tool | The endpoints. `from == to` ⇒ self-transition (in-place). |
| `action` | tool (captured) | The replayable action. See [`action`](#action). |
| `wait` | learned | The wait **strategy** (no timeout). Defaults to `to_state.readiness`. See [`wait`](#wait). |
| `kind` | derived | `navigation` \| `in_place` \| `noop` — the classification of the edge (output of the matching layer). |
| `reliability` | tool (accumulated) | `{ confirmations, failures, last_confirmed }` (commit-anchored). |
| `provenance` | tool | `learned` / `last_confirmed` / `last_modified` (commit SHAs, as in States). |

## `action`

Captures everything needed to **derive the final command** for any lazyworker `ui`
action — verified complete against the CLI surface. (The command renderer itself is
deferred; this fixes that the *data* is sufficient to derive it.)

```jsonc
{
  "gesture": "tap",   // tap | double_tap | long_press | scroll | scroll_to | type | deeplink
  "target": {                                   // null for scroll and deeplink
    "selector": {                                // primary addressing
      "type": "Button", "label": null, "name": null, "value": null,
      "identifier": "login_button", "index": null, "any_visibility": false
    },
    "at": [195, 626]                             // absolute point (a fact); see "coordinate recomputability"
  },
  "params": {                                    // gesture-specific
    "text": null,        // type
    "url": null,         // deeplink
    "direction": null,   // scroll, scroll_to
    "distance": null,    // scroll
    "max_swipes": null,  // scroll_to
    "duration": null     // long_press
  }
}
```

Coverage (every gesture is derivable): `selector` covers the five selector flags +
`--index` + `--any-visibility`; `at` covers `--at X,Y`; `params` covers
`--text`/`--direction`/`--distance`/`--max-swipes`/`--duration`/the deeplink url.

### Coordinate recomputability

`at` stores the **absolute point as a fact**; portability is **derived**, never
frozen:
- **Normalize by screen size:** `point / from_state.reference.screen_size` → a
  `[0..1]` fraction, re-denormalized to the current screen at run time.
- **Visual re-location:** for canvas/Flutter targets with no selector, recompute the
  position from `from_state.reference.screenshot` via template/OCR/detect matching
  (the existing `ui screen --ocr/--detect`).

So `at` is the last-resort addressing (selector first), and even then it is
recomputable rather than brittle. `scale` (density) lives on the state's reference.

## `wait`

The wait **strategy** — durable knowledge that lets the tool move fast (it proceeds
the instant the condition holds). It stores the strategy but **never a timeout**
(timeout is environment-dependent runtime policy; the runtime applies a default
ceiling). By default a transition inherits `to_state.readiness`.

```jsonc
{
  "mode": "until",                                   // settle | until | gone | tree
  "predicate": { "key": "identifier", "value": "home-root" },  // until/gone condition
  "settle_strategy": null,                           // strict | magnitude | custom
  "threshold": null,                                 // custom settle threshold
  "settle_count": 2                                  // stable polls to accept (stability)
}
```

## Example (one state's outgoing transitions)

```jsonc
// navigation: Home -> Settings
{ "transition_id": 31, "from_state": "st_0007", "to_state": "st_0006", "kind": "navigation",
  "action": { "gesture": "tap",
              "target": { "selector": { "identifier": "hamburger-menu-button", "type": "Button" }, "at": [32, 78] },
              "params": {} },
  "wait": { "mode": "until", "predicate": { "key": "identifier", "value": "settings-root" } },
  "reliability": { "confirmations": 9, "failures": 0, "last_confirmed": "1bb1c51" } }

// self-transition: a button mutates Home in place
{ "transition_id": 32, "from_state": "st_0007", "to_state": "st_0007", "kind": "in_place",
  "action": { "gesture": "tap",
              "target": { "selector": { "identifier": "home-mode-indicator-button", "type": "Button" }, "at": [350, 78] },
              "params": {} },
  "wait": { "mode": "settle", "settle_strategy": "strict", "settle_count": 2 } }
```

## Inspiration (validated against prior art)

The model converges with established frameworks: the directed graph with self-loops
and shortest-path traversal is **GraphWalker / model-based testing** (but learned
from observation, not hand-authored); the condition-based readiness mirrors
**Selenium ExpectedConditions** and **Playwright actionability**; the weighted,
self-correcting identity mirrors **Healenium** (generalized from elements to
states). Because lazyworker is black-box over WDA — unlike gray-box **Detox** /
**Espresso IdlingResource**, which instrument the app to know it is idle — the
**learned wait strategy is our substitute for that instrumentation**.
