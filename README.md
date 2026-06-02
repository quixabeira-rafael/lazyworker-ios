# lazyworker

**Agent-first iOS automation over [WebDriverAgent](https://github.com/appium/WebDriverAgent).**

`lazyworker` drives iOS **production apps** — on simulators and real devices — by reading their
accessibility state and acting on it. It needs **no app source code** and **no Xcode integration
at runtime** (Xcode is used only once, to build/sign WebDriverAgent).

It is designed to be driven by an **autonomous agent**, not only by a human at a keyboard. Every
command is a small, composable building block with machine-friendly behaviour:

- **Structured output** — every command prints JSON to stdout.
- **Deterministic exit codes** — branch on `$?` without parsing the output (`0` ok, `20` not
  found, `21` ambiguous, `10` no session, …).
- **Errors are data** — an ambiguous selector returns the candidate elements; a failed wait
  returns a screenshot path. Failures are inspectable, not opaque.
- **Self-describing** — rich `--help` on every command and flag, so an agent can discover what is
  possible at runtime.
- **Observe → act → verify** — read the tree/screen, act by selector or coordinate, and require a
  *verified* change via a built-in smart wait.

## How it works

```
agent / script
      │  CLI (JSON in, JSON out, exit codes)
      ▼
  lazyworker ──HTTP──► WebDriverAgent ──► XCUITest ──► iOS app (simulator or device)
```

`lazyworker` talks raw HTTP to a WebDriverAgent runner, which uses Apple's XCUITest to read the
accessibility tree and synthesize real touches/gestures. You build WDA once with `bootstrap`,
start it with `up`, and then observe and act.

## Requirements

- macOS with Xcode (used once by `bootstrap` to build/sign WebDriverAgent).
- Python >= 3.11.
- For real devices: an Apple ID signed into Xcode (free or paid), Developer Mode enabled on the
  device, and `iproxy` (`brew install libimobiledevice`) for the USB connection path.

## Install

```bash
pipx install .          # global, isolated CLI available on your PATH
# for development (editable — picks up source changes), from the repo root:
make install            # pipx install -e . using the project's Python (3.11+)
```

Make sure `~/.local/bin` is on your PATH (`pipx ensurepath`). After that, `lazyworker` works from
any directory — including inside the app repo you want to drive.

Optional extras enable extra screen-understanding backends:

```bash
pipx install '.[ocr]'      # Apple Vision OCR for `ui screen --ocr`
pipx install '.[detect]'   # local visual UI detector for `ui screen --detect`
```

## Quick start (simulator)

```bash
lazyworker doctor                         # preflight: what's ready, what to fix
lazyworker bootstrap                      # build WebDriverAgent for the simulator (run once)
lazyworker up                             # boot a simulator, launch WDA, wait until ready

lazyworker ui open com.apple.Preferences  # open an app, create a session
lazyworker ui tap --label General --type Button
lazyworker ui scroll --direction down
lazyworker ui screen -o screen.png        # JSON breakdown of what's on screen
lazyworker ui close

lazyworker down                           # stop WDA
```

## Real device

Configure signing in `lazyworker.toml` (see `lazyworker.toml.example`), then:

```bash
lazyworker doctor --udid <udid>   # checks signing team, Developer Mode, port-forward
lazyworker bootstrap              # builds a signed WDA for the device
lazyworker up                     # USB: launches WDA + iproxy port-forward
lazyworker up --network           # Wi-Fi: reaches WDA at its advertised LAN URL (no iproxy)
```

`lazyworker doctor` lists the Team IDs signed into Xcode (free ones flagged) so you can fill in
`signing.team_id`.

## Commands

### Top-level

| Command | Purpose |
|---|---|
| `bootstrap` | Fetch and build WebDriverAgent (simulator, or signed for device per config). Run once. |
| `up` | Boot/target a simulator or device, launch WDA, wait until ready; persists run state. |
| `down` | Tear down the running WDA instance (`--shutdown-simulator` to also stop the sim). |
| `status` | WebDriverAgent status as JSON. |
| `source` | Current accessibility tree as JSON. |
| `screenshot` | Capture the current screen to a PNG (`-o PATH`). |
| `devices` | List simulators and physical devices (USB/network) as JSON; filters: `--kind/--connection/--booted`. |
| `doctor` | Environment/device preflight; reports the actions needed to automate (`--json` for machines). |
| `ui` | Agentic interaction subgroup — open a session and act on the tree (see below). |

After `up`, the read commands (`status`, `source`, `screenshot`) automatically target the active
WDA via the saved run state.

### Agentic interaction (`ui`)

An agent opens an app — which creates a tuned session that survives across CLI calls — then
observes and acts. Every action prints an `OperationResult` JSON and exits with a deterministic
code so an agent can branch on `$?`.

| Command | Purpose |
|---|---|
| `ui open BUNDLE_ID` | Open an app, create a tuned session, and persist it (`--reuse/--no-reuse`, `--snapshot-max-depth`, `--snapshot-timeout`, `--wait-for-quiescence`). |
| `ui close` | Close the active app session. |
| `ui tree` | Print the current accessibility tree (session-tuned snapshot). |
| `ui find` | Search the tree (read-only); return every element matching a free-text query and/or selectors. |
| `ui tap` | Tap an element (by selector) or a coordinate. |
| `ui double-tap` | Double-tap an element or a coordinate. |
| `ui long-press` | Long-press an element or a coordinate (`--duration`). |
| `ui scroll` | Scroll the screen in a direction (`--direction`, `--distance`). |
| `ui scroll-to` | Scroll until an element becomes visible (`--direction`, `--max-swipes`). |
| `ui type` | Type text (`--text`), optionally tapping a field first to focus it. |
| `ui deeplink URL` | Open a deep/universal link via the active session. |
| `ui screenshot` | Capture the current screen to a PNG (`-o PATH`). |
| `ui screen` | Emit a textual breakdown of the screen as JSON (`--ocr`, `--detect`, `-o PATH`). |
| `ui batch` | Run an ordered JSON list of operations (`--file` or stdin; `--stop-on-error/--continue-on-error`). |

**Addressing.** Every action targets an element by **selector** or a raw **coordinate**:

- Selectors: `--type`, `--label`, `--name`, `--value`, `--identifier`, with `--index` to pick one
  of several matches and `--any-visibility` to include hidden elements.
- Coordinate: `--at X,Y` (a real touch — it hits the view via hit-testing, even for elements that
  are not in the accessibility tree).
- `--dry-run` resolves and reports the target/point without acting.

Ambiguity is returned as data, not a blind error:

```json
{ "operation": "tap", "ok": false, "error_code": "ambiguous", "candidate_count": 2,
  "candidates": [ { "type": "Button", "label": "Save" }, { "type": "StaticText", "label": "Save" } ] }
```

**Search.** `ui find` is read-only and returns *every* match — free text alone (no type needed),
with selectors as optional extra filters:

```bash
lazyworker ui find -q "joilane"               # any element whose text/id contains "joilane"
lazyworker ui find -q "joilane" --type Cell   # type as an extra filter
lazyworker ui find --identifier btn-primary   # exact field match
```

Each match carries **tips** — ready-to-copy commands tailored to the element (a `Button` → a
`tap`, a `TextField` → a `type`, a `ScrollView` → `scroll`/`scroll-to`), using the best selector
plus an unambiguous `--at` fallback. Use `--no-tips` for lean output.

```json
{ "count": 1, "matches": [
  { "type": "Button", "label": "Primary", "identifier": "btn-primary", "rect": {…}, "visible": true,
    "tips": [
      { "action": "tap", "command": "lazyworker ui tap --identifier \"btn-primary\"" },
      { "action": "tap", "command": "lazyworker ui tap --at 206,142" } ] } ] }
```

**Smart wait.** Append a wait to any action and the result is only `ok` once a *verified* change
settles — otherwise it fails with `no_change` (exit `25`):

- `--wait tree` — wait for a structural change in the accessibility tree.
- `--wait settle` — wait for the screen to stop animating after the action (colour-aware,
  identity-based; reports `settled`/`busy`/`no_change`). Postures: `settle:magnitude` /
  `settle:custom=<n>` use a colour-magnitude threshold instead (the magnitude default is `1.0`,
  overridable via the `LAZYWORKER_SETTLE_ONSET` env var).
- `--wait-until key=value` / `--wait-gone key=value` — wait until a selector appears / disappears
  (keys: `type|label|name|value|identifier|id`, e.g. `--wait-until id=spinner`).
- Tune with `--wait-timeout`, `--wait-settle` (stable polls required), `--wait-interval`.
- Set a default wait for every action with the `LAZYWORKER_DEFAULT_WAIT` env var (e.g.
  `settle`); an explicit `--wait` overrides it, and `--wait none` opts out for one call.
- On a failed wait, a screenshot of the final state is saved and its path is attached to the
  result (`--no-wait-shot` to disable).

```bash
lazyworker ui tap --identifier submit --wait-until "id=home"
lazyworker ui tap --label "Começar" --wait settle
```

**Exit codes.** `0` ok, `10` no_session, `11` wda_unreachable, `12` session_invalid,
`13` wda_error, `20` not_found, `21` ambiguous, `22` not_visible, `23` out_of_bounds, `24` timeout,
`25` no_change, `30` invalid_target, `31` ocr_unavailable, `32` detector_unavailable, `1` internal.

### Screen understanding (`ui screen`)

`ui screen` turns the current screen into agent-consumable text: the screenshot path, the screen
box, and a flat list of elements (each a box with `box=[x,y,w,h]`, `size`, text, role, and a
`container` grouping hint), in reading order.

```json
{ "screenshot": "…/screen-….png", "width": 402, "height": 874,
  "elements": [
    { "role": "Other", "identifier": "card-1", "box": [16,163,370,89] },
    { "role": "StaticText", "text": "Saldo", "box": [32,179,32,15], "container": "card-1" },
    { "role": "StaticText", "text": "R$ 1.234,56", "box": [32,202,151,34], "container": "card-1" } ] }
```

- `--ocr` also runs **Apple Vision** OCR (`pip install 'lazyworker[ocr]'`), recovering text that is
  **not** in the accessibility tree — drawn text, images, custom views — as
  `{text, box, size, confidence}` in the same screen-point coordinates. A component outside the
  tree can then be tapped by coordinate: OCR gives the box, `ui tap --at <cx>,<cy>` taps its centre.
- `--detect` also runs a **local visual UI detector** (OmniParser; `pip install 'lazyworker[detect]'`),
  finding icons/buttons/regions from pixels as `{label, box, size, confidence, container}`. It is
  heavy (downloads model weights, loads PyTorch) — use it for exploration, not per-action.

### Aggregate operations (`ui batch`)

Pipe an ordered JSON array of ops (stop-on-error by default) to run a whole flow in one call:

```bash
echo '[{"op":"tap","label":"Search"},
       {"op":"type","text":"joilane"},
       {"op":"tap","label":"joilane","type":"Cell"}]' | lazyworker ui batch
```

The report contains a per-operation `OperationResult` array and exits with the first failure's
code.

## Configuration (`lazyworker.toml`)

```toml
[signing]
mode = "free"            # simulator | free | paid
team_id = "XXXXXXXXXX"   # required for free/paid; a team signed into Xcode
bundle_id_prefix = "com.example.wda"

[target]
udid = "…"               # the simulator/device this repo drives (so you can omit --udid)
# bundle_id = "com.example.app"

[wda]
base_url = "http://127.0.0.1:8100"
port = 8100              # give each project a distinct port to run several WDAs at once
# version = "v9.0.0"     # optional: pin the WDA git ref
```

`lazyworker.toml` is discovered by walking up from the current directory, so **each app
repo/worktree pins its own target and port**. Runtime state (the active WDA, the `ui` session,
screenshots) lives per-project under `<repo>/.lazyworker/` (gitignore it), while the shared WDA
build stays global under `~/.lazyworker/`. This lets you drive **different simulators from
different repos at the same time** — give each its own `[target] udid` and `[wda] port`.

## Library

The CLI is a thin layer over a typed Python library, usable directly:

```python
from lazyworker import WdaClient

with WdaClient("http://127.0.0.1:8100") as client:
    session = client.create_session("com.apple.Preferences")
    tree = session.source()
    cell = next(c for c in tree.find_all(type="Cell") if c.rect)
    session.tap(*cell.rect.center)
    session.type_text("hello")
```

Session actions: `source`, `screenshot`, `tap`, `double_tap`, `long_press`, `swipe`, `type_text`,
`apply_settings`, `deep_link`, `terminate`, `delete`. The accessibility tree supports `walk`,
`find`, and `find_all`. The `lazyworker.interaction` package adds the agentic layer: `Interactor`
(selector-resolving actions returning `OperationResult`), `Locator`, and `BatchRunner`.

## Development

```bash
python3.13 -m venv .venv
make dev      # editable install with [dev] extras into .venv
make gate     # ruff + mypy + pytest
make install  # (re)install the global CLI in editable mode
```

## License

MIT — see [LICENSE](LICENSE).
