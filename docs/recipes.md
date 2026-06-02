# Recipes: command combinations

lazyworker is a set of small observe/act primitives. The leverage is in
chaining them. Each recipe below is a goal, the commands, and *why* they go
together. All commands assume a live session (`lazyworker ui open <bundle-id>`).

Read [`tree-schema.md`](tree-schema.md) first — every selector here relies on
the node fields it describes.

## 1. Orient on an unknown screen

Three lenses, cheapest first:

```bash
lazyworker ui find back               # targeted: anything matching "back"
lazyworker ui tree                    # full hierarchy (verbose; filter with --jq)
lazyworker ui screen --ocr            # pixels + text outside the tree (WebViews, canvas)
```

Use `find` when you know roughly what you're after, `tree` when you need
structure, `screen --ocr` when the tree is sparse (web/hybrid content).

## 2. Find → act on a stable anchor

`find` already prints copy-paste `tips` per match. The pattern they encode:

```bash
lazyworker ui find "Save"
# → match has identifier "btn-save"  ⇒ anchor on it, not the localized label:
lazyworker ui tap --identifier btn-save --wait settle
```

No identifier? Combine label and type so you don't hit the `StaticText` inside
the button:

```bash
lazyworker ui tap --label "Save" --type Button --wait settle
```

## 3. Pull one value out with `--jq` (no inline Python)

```bash
lazyworker ui find button --jq '.count'                         # how many buttons
lazyworker ui find "row" --jq '.matches[].identifier'           # all ids, raw
lazyworker ui find "" --type Cell --jq '.matches[].label'       # every cell's label
lazyworker ui find save --jq '.matches[0].rect'                 # first match's box
lazyworker ui find x --jq '.matches[] | select(.type=="Button") | .identifier'
```

`--jq` runs through a bundled jq engine (no install needed) but forces `-r` and exposes no jq
flags. When you need a flag (`-c`, `-S`, `--arg`, `-s`, …) or the quoted form, **pipe to your own
`jq` CLI** instead:

```bash
lazyworker ui find button | jq -c '[.matches[] | select(.type=="Button")]'
lazyworker ui find button | jq --arg t Button '.matches[] | select(.type==$t)'
```

## 4. Act → verify the screen actually changed

Every acting command can require a change, turning a blind tap into a checked
one. No change within the timeout → exit `25` (`no_change`), `ok:false`.

```bash
# wait for the screen to stop animating (best after taps that push a new view):
lazyworker ui tap --identifier checkout --wait settle

# wait for a specific element to appear / disappear (semantic, most precise):
lazyworker ui tap --identifier login --wait-until id=home-feed
lazyworker ui tap --identifier submit --wait-gone label=Loading

# structural change only (cheap; "something in the tree moved"):
lazyworker ui tap --identifier next --wait tree
```

`--wait-until`/`--wait-gone` predicates accept `type|label|name|value|id`.
Set a session-wide default with `LAZYWORKER_DEFAULT_WAIT=settle` and opt out per
call with `--wait none`.

## 5. Reach an element below the fold

`find` and `tap` ignore off-screen nodes (`visible:false`). Bring it on screen
first:

```bash
lazyworker ui scroll-to --label "Terms of Service" --direction down
lazyworker ui tap --label "Terms of Service" --type Button
```

For free scrolling that races iOS inertia, settle the fling before reading:

```bash
lazyworker ui scroll --direction down --wait settle
```

## 6. Resolve ambiguity

`tap` fails with exit `21` (`ambiguous`) when a selector matches several nodes.
Narrow it:

```bash
lazyworker ui find "Add"                       # inspect the candidates
lazyworker ui tap --label "Add" --type Button --index 0   # pick the Nth (0-based)
```

## 7. Fill a form

```bash
lazyworker ui type --text "ada@example.com" --identifier email-field
lazyworker ui type --text "hunter2" --identifier password-field
lazyworker ui tap  --identifier sign-in --wait-until id=home-feed
```

`type` taps the field first to focus it when given a selector.

## 8. Colour checks (QA reads, the caller asserts)

`ui color` only *reports* colour — lazyworker never asserts. Pick the read that
matches the shape of the question:

```bash
lazyworker ui color --identifier cta --background        # dominant box colour
lazyworker ui color --at 120,300 --text                  # glyph colour at a point
lazyworker ui color --region 0,80,375,44 --palette       # colours present + fractions
```

`--palette` is the answer to "does this region *contain* gold?" when the colour
covers only a sliver of the box (a medal, a badge) — the caller checks the
returned fractions.

## 9. Probe a selector without acting

```bash
lazyworker ui tap --identifier delete-account --dry-run
```

Resolves the selector and reports what *would* be tapped (and its point), with no
side effects. Good for validating a script before letting it loose.

## 10. Run a fixed sequence atomically

For a known flow, hand the whole list to `batch` (JSON array, `--file` or stdin)
and let it stop on the first failure:

```bash
echo '[
  {"action":"tap","identifier":"checkout","wait":"settle"},
  {"action":"type","identifier":"coupon","text":"SAVE10"},
  {"action":"tap","identifier":"apply","wait_until":"label=Applied"}
]' | lazyworker ui batch
```

## Exit codes drive branching

Scripts and agents should branch on the exit code, not parse prose:

| Code | Meaning | Typical reaction |
|---|---|---|
| `0` | ok | continue |
| `20` | not_found | screen isn't what you assumed → re-`find`/`tree` |
| `21` | ambiguous | add `--type`/`--index` |
| `22` | not_visible | `scroll-to` first |
| `24` | timeout | raise `--wait-timeout` or check the app is responsive |
| `25` | no_change | the action had no effect → the precondition was wrong |
| `10` | no_session | run `ui open <bundle-id>` |

Full list: `lazyworker ui --help`.
