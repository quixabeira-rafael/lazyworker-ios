---
name: lazyworker
description: Drive a real iOS app (simulator or physical device) over WebDriverAgent to observe and act on it for you — read the accessibility tree, search the screen, tap/scroll/long-press/type by selector or coordinate, follow deep links, wait until the screen settles, capture screenshots, and read element/region colours. Agent-first: every command emits JSON and a deterministic exit code, so you chain commands and branch on results instead of looking at a screen. Use it to operate an app while validating a change at dev time, and to build UI test pipelines at QA time (lazyworker observes; your test framework asserts). Use when the user asks to open/drive/automate an iOS app, tap/scroll/type in it, find an element, see "what's on screen", confirm the app shows X after an action, reproduce or validate a flow, or capture what an app does. Trigger phrases include "drive the app", "open <bundle id>", "tap the/that button", "scroll to", "type into", "what's on the screen", "find the element", "did the screen change", "validate this flow in the simulator", "automate this in the app", "screenshot the app", "what colour is", "ui tree".
---

# lazyworker

A CLI that gives an agent hands and eyes inside a running iOS app — yours to operate the app and report back, without the app's source and without Xcode at runtime. It reads the app's accessibility state and synthesizes real touches over Apple's XCUITest (WebDriverAgent).

It is **built to be driven by an agent, not a human**: every command prints structured JSON on stdout and exits with a stable code, ambiguities come back as *data* (candidate lists), and session state persists between calls so you run one command, read the result, and decide the next — a loop, not a script you write up front.

Two ways you'll use it:

- **Dev time** — operate the app on the user's behalf to *see a change working*: open the app, drive to the screen, read what's there, report back ("the new card renders, label is X, it's green"). You are the user's eyes while they edit code.
- **QA time** — compose the same primitives into a UI test pipeline. lazyworker is the *driver and the observer*; the **assertions live in whatever test framework the caller wants** (pytest, XCTest-style runners, a shell `[ $? -eq 0 ]`, …). lazyworker returns colours/text/state as data and deterministic exit codes; the harness decides pass/fail.

## Mental model (read once)

1. **Observe → act → verify.** Read the tree (or search it), act by selector or coordinate, then confirm the screen actually changed. Don't assume a tap "worked" — verify with a wait or a re-read.
2. **You need a session first.** `lazyworker up` brings up WebDriverAgent; `lazyworker ui open <bundle-id>` attaches a session to an app. Every `ui …` command afterwards reuses that persisted session — so a missing session is exit `10` (`no_session`), telling you to run `ui open` first.
3. **Two ways to address something: by selector or by coordinate.** Prefer a **selector** (`--label`, `--identifier`, `--type`, …) — it's stable and self-documenting. Fall back to `--at X,Y` only when there's no addressable element (Flutter cards, unlabelled icons, a point on a gradient).
4. **Ambiguity and absence are data, not errors to retry blindly.** Not found → exit `20`; ambiguous (many matches) → exit `21` with the candidates in the JSON; off-screen/invisible → `22`. Read the payload and refine the selector or add `--index`.
5. **Coordinates are in points; everything lines up.** Element rects, `--at`, OCR boxes and `ui color` boxes are all in screen points, so a rect from `ui find` feeds straight into `--at` or `--region`.
6. **lazyworker observes; it does not assert.** There is no `--expect`/pass-fail flag. Read the JSON (`ok`, `error_code`, colours, tree) and let your own code/test decide. This is deliberate — the tool is the runtime, the QA logic is yours.

## Start a session (do this first)

```bash
lazyworker up                       # boot a sim + launch WebDriverAgent, wait until ready
lazyworker ui open com.acme.app     # attach a session to the app (persisted for later calls)
```

If `ui …` returns exit `10` you skipped `ui open`; exit `11`/`12` mean WDA is unreachable or the session went stale (re-`open`). `lazyworker doctor` diagnoses the environment.

## What do you want to do? (pick the command)

| Situation | Command |
|---|---|
| "What's on the screen?" — find a specific thing | **`ui find`** (search; read-only) |
| "What's on the screen?" — full structure | `ui tree` (whole accessibility tree) |
| "What's on the screen?" — agent-readable layout, maybe OCR | `ui screen` (`--ocr`, `--detect`) |
| Tap a button / cell / element | **`ui tap`** (by selector, or `--at X,Y`) |
| Double-tap / long-press | `ui double-tap`, `ui long-press --duration` |
| Reveal off-screen content | **`ui scroll --direction`**, or **`ui scroll-to`** a target |
| Enter text into a field | `ui type --text "…"` (taps the field first to focus) |
| Open a deep/universal link | `ui deeplink <url>` |
| Confirm my action actually did something | add **`--wait …`** to the action |
| Read a colour (element / point / region) | `ui color` |
| Save a picture of the current screen | `ui screenshot -o path.png` |
| Run a fixed sequence of steps | `ui batch` (JSON list of ops) |

## Observe — see before you act

**`ui find` is your first move on any screen.** It's read-only and returns *every* match as data, so you discover what's tappable and how to address it. The query is **positional and forgiving**: a plain substring matched (case-insensitive, accent- and whitespace-insensitive) against the node's *type and every text field* — id, label, name, value. So you don't need the flag, the type, or the exact text:

```bash
lazyworker ui find back                       # anything with "back" anywhere (id, label, …)
lazyworker ui find menu                        # matches id "hamburger-menu-button" or label "Menu"
lazyworker ui find button                      # match by type
lazyworker ui find back --type Button          # add a type filter to narrow
lazyworker ui find --identifier btn-primary    # exact field match (no free text)
```

**Read the result with `--jq`, not an inline script.** Pass a jq expression (a bundled jq engine, run with `-r`, so no `jq` install is needed) to filter/map/reduce the JSON in place — strings come out raw, objects stay JSON:

```bash
lazyworker ui find button --jq '.count'                                   # how many
lazyworker ui find button --jq '.matches[].label'                          # just the labels
lazyworker ui find back   --jq '.matches[] | select(.type=="Button") | .identifier'   # ids of buttons
lazyworker ui find chat   --jq '.matches[0].rect | "\(.x+.width/2|floor),\(.y+.height/2|floor)"'  # → feed to --at
```

So the loop is one line: `find … --jq` to pick the target, then act on it.

`--jq` takes the whole jq *program* (so `select`/`map`/`reduce`/`test`/etc. all work) but exposes no jq *flags* and forces `-r`. When you need a flag — compact `-c`, sorted `-S`, variables `--arg`, slurp `-s`, or the quoted (non-raw) form — **pipe to your own `jq` CLI**; every command emits clean JSON for exactly that:

```bash
lazyworker ui find button | jq -c '[.matches[] | select(.type=="Button")]'   # -c compact
lazyworker ui find button | jq --arg t Button '[.matches[]|select(.type==$t)]'  # --arg variable
```

Each match carries its `rect` and ready-to-copy **tips** (`--tips`, on by default) — e.g. the exact `ui tap --identifier …` to act on it. Use `find` when you don't yet know the selector; use `ui tree` only when you need the whole structure; use `ui screen` when you want a flattened, reading-order breakdown (and `--ocr`/`--detect` to recover text/elements that aren't in the accessibility tree — common in Flutter/canvas UIs).

**Unsure what a field or `type` means?** Run `lazyworker ui schema` (add `--json` for machine form) — it explains every node field, where it comes from, which to anchor on (`identifier` > `label`+`type` > `--at`), and the full catalog of element types. The long-form version with command combinations lives in `docs/tree-schema.md` and `docs/recipes.md`.

## Act — tap, scroll, type

**Tap.** Prefer a selector; the rect/center is resolved for you. Drop to `--at` only for non-addressable targets.

```bash
lazyworker ui tap --label "Continue" --type Button
lazyworker ui tap --identifier add-to-cart
lazyworker ui tap --at 195,734            # coordinate fallback (Flutter card, icon, …)
lazyworker ui tap --label Delete --dry-run  # resolve only: exit 0 if uniquely tappable, 20/21/22 if not
```

`--dry-run` is the cheap **"does this exist and is it uniquely tappable right now?"** check — it resolves and reports an exit code without touching anything.

**Scroll — two different tools, pick by intent:**

- **`ui scroll --direction down|up|left|right`** when you just need to move the viewport a step (`--distance` to tune). It's a swipe; momentum may carry it. Pair it with `--wait settle` so the fling finishes before you read the tree — otherwise you race the deceleration.
- **`ui scroll-to --identifier row-50`** when you need a *specific* element on screen — it scrolls repeatedly until the target is visible (`--max-swipes`), so you don't guess how far.

```bash
lazyworker ui scroll --direction down --wait settle    # one step, wait for it to settle
lazyworker ui scroll-to --label "Terms" --direction down   # keep scrolling until "Terms" shows
```

**Type** taps the field to focus it, then types:

```bash
lazyworker ui type --identifier field-email --text "a@b.com"
```

## Verify — make sure the action landed

After an action, don't assume — require a *verified* change with `--wait`. Pick the wait by what "done" means:

| You want to wait for… | Use | Notes |
|---|---|---|
| the screen to stop animating after the action | `--wait settle` | colour-aware, identity-based; reports `settled`/`busy`/`no_change`. Best default for navigation/animation. |
| any structural change to the tree | `--wait tree` | cheap; no Pillow needed; catches non-visual changes (focus, value). |
| a specific element to appear | `--wait-until id=home` | the right tool for lazy/multi-step content (`settle` can't know more is coming). |
| a specific element to disappear | `--wait-gone label=Loading` | e.g. a spinner going away. |

```bash
lazyworker ui tap --identifier submit --wait-until "id=home"   # assert navigation happened
lazyworker ui tap --label Save --wait settle                   # wait for the screen to settle
```

No change within the timeout ⇒ exit `25` (`no_change`) and `ok:false`, with a screenshot of the final state attached. Tune with `--wait-timeout`, `--wait-settle` (stable polls), `--wait-interval`. Set a default for every action with the `LAZYWORKER_DEFAULT_WAIT` env var; `--wait none` opts out per call.

Note: a wait is the wrong tool for a **fire-and-forget action that legitimately changes nothing** (e.g. a refresh that's already up to date) — that returns `no_change`, which is correct, not a failure. Don't wait there.

## Read colours — `ui color`

Returns colour as *data* (background + text), so your code asserts. Pick the source by what you're reading:

```bash
lazyworker ui color --label "Error"                 # an element: {background, text, ...}
lazyworker ui color --label "Error" --text          # just the text (glyph) colour
lazyworker ui color --at 195,30                      # a point (small neighbourhood) — gradients, etc.
lazyworker ui color --region 16,138,358,49           # an arbitrary box: dominant + foreground
lazyworker ui color --region 16,138,358,49 --palette # list colours present → do a "contains" check
```

- Element / region give the **dominant** colour as `background` and the separable foreground as `text` (great for "is this label red?").
- `--at` samples a **neighbourhood and returns its dominant** — perfect for a large smooth region (a gradient point), wrong for a tiny icon (it reads the surrounding background).
- `--palette` lists the colours present with their pixel fractions — use it for **"does this region contain colour X?"** (a small badge, a medal, a coloured dot) where the colour is a minority and the dominant read would miss it.

Needs Pillow (`pip install 'lazyworker[ocr]'`). Status bar (the clock) is cropped automatically so it never counts as a change.

## Building a QA pipeline (assertions are yours)

The pattern: **lazyworker drives + observes; you assert in your framework.** A robot/page-object that shells out to lazyworker and branches on the JSON keeps the test logic where it belongs.

```python
# pytest-style: lazyworker observes, the test asserts
import json, subprocess

def color(*sel):
    out = subprocess.run(["lazyworker", "ui", "color", *sel], capture_output=True, text=True)
    return json.loads(out.stdout)

def test_error_banner_is_red():
    subprocess.run(["lazyworker", "ui", "tap", "--identifier", "submit", "--wait", "settle"])
    banner = color("--label", "Erro", "--background")
    assert banner["background"] is not None
    assert distance(banner["background"], (229, 57, 53)) < 30   # YOUR assertion
```

Use exit codes as built-in assertions when that's enough: `ui tap --label X --dry-run` (exists & unique → 0), `--wait-until id=Y` (appeared → 0, else 25). Anything richer (exact colour, value comparisons, contains) you compute from the JSON in your own code.

## Selectors & addressing (reference)

`--type` `--label` `--name` `--value` `--identifier` (exact match) plus `--index N` (pick the Nth of several) and `--any-visibility` (also match invisible). `--at X,Y` for a coordinate. `ui find` additionally takes `-q/--query` for substring search. Prefer selectors; reach for coordinates only when nothing is addressable.

## Exit codes (the contract)

`0` ok · `10` no_session (run `ui open`) · `11` wda_unreachable · `12` session_invalid (re-open) · `13` wda_error · `20` not_found · `21` ambiguous (candidates in JSON) · `22` not_visible · `23` out_of_bounds · `24` timeout · `25` no_change · `30` invalid_target · `31` ocr_unavailable · `32` detector_unavailable · `1` internal.

Branch on these instead of parsing text: e.g. `21` → read `candidates` and add `--index`; `20` → the screen isn't what you assumed, re-`ui find`; `25` → the action didn't change anything within the timeout.

## Beyond the daily drivers

`bootstrap` (build WDA), `down` (tear down), `status`, `source`, `devices`, `doctor` are infra/inspection — run `lazyworker <cmd> --help`. `ui batch` runs an ordered JSON list of operations (from `--file` or stdin) for a fixed, replayable sequence; prefer the observe→act→verify loop for anything adaptive.
