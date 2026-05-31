# lazyworker

Agent-friendly iOS automation over [WebDriverAgent](https://github.com/appium/WebDriverAgent)
(WDA) for **simulators and real devices**. It drives **production apps** — no source code,
and no Xcode integration at runtime (Xcode is only needed once, to build/sign WDA).

`lazyworker` exposes a small typed Python library and a CLI designed to be consumed by an
autonomous agent: structured (JSON) output, descriptive help, and clear, actionable errors.

## Requirements

- macOS with Xcode (used once by `bootstrap` to build/sign WebDriverAgent).
- Python >= 3.11.
- For real devices: an Apple ID signed into Xcode (free or paid), Developer Mode enabled on
  the device, and `iproxy` (`brew install libimobiledevice`) for the USB connection path.

## Install

```bash
pipx install .        # or: pip install .
```

## Quick start (simulator)

```bash
lazyworker doctor       # preflight: what's ready and what to fix
lazyworker bootstrap    # build WebDriverAgent for the simulator (run once)
lazyworker up           # boot a simulator, launch WDA, wait until ready
lazyworker source       # accessibility tree as JSON (targets the active WDA)
lazyworker screenshot -o screen.png
lazyworker down         # stop WDA
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

## CLI

| Command | Purpose |
|---|---|
| `doctor` | Environment/device preflight; reports required actions; `--json` for machines. |
| `devices` | List simulators and physical devices (USB/network) as JSON. |
| `bootstrap` | Fetch and build WDA (simulator, or signed for device per config). |
| `up` / `down` | Launch / tear down WDA on a simulator or device; persists run state. |
| `status` | WDA status as JSON. |
| `source` | Current accessibility tree as JSON. |
| `screenshot` | Capture the screen to a PNG. |

After `up`, the read commands auto-target the active WDA via the saved run state.

## Agentic interaction (`lazyworker ui`)

An agent opens an app (which creates a tuned session that survives across CLI calls), then acts
on the accessibility tree. Elements are addressed by **selector** (`--label/--type/--name/
--value/--identifier`, with `--index` to disambiguate) or by **coordinate** (`--at X,Y`). Every
action prints an `OperationResult` JSON to stdout and exits with a deterministic code (0 on
success; e.g. 20 not-found, 21 ambiguous, 10 no-session) so an agent can branch on `$?`.

```bash
lazyworker ui open com.apple.Preferences      # create + tune a session
lazyworker ui tree                            # accessibility tree (session-tuned snapshot)
lazyworker ui tap --label General --type Button
lazyworker ui scroll --direction down
lazyworker ui scroll-to --label "Battery"
lazyworker ui type --text "hello" --label "Search"
lazyworker ui screenshot -o screen.png
lazyworker ui close
```

Ambiguity is returned as data, not a blind error:

```json
{ "operation": "tap", "ok": false, "error_code": "ambiguous",
  "candidate_count": 2, "candidates": [ { "type": "Button", ... }, { "type": "StaticText", ... } ] }
```

Add `--dry-run` to resolve and report the target without acting.

**Screen breakdown** — `lazyworker ui screen` turns the current screen into agent-consumable
text: the screenshot path, the screen box, and a flat list of elements (each a box with
`box=[x,y,w,h]`, `size`, text, role, and a `container` grouping hint), in reading order.

```json
{ "screenshot": "~/.lazyworker/screens/screen-….png", "width": 402, "height": 874,
  "elements": [
    { "role": "Other", "identifier": "card-1", "box": [16,163,370,89] },
    { "role": "StaticText", "text": "Saldo", "box": [32,179,32,15], "container": "card-1" },
    { "role": "StaticText", "text": "R$ 1.234,56", "box": [32,202,151,34], "container": "card-1" } ] }
```

Add `--ocr` to also run Apple Vision OCR on the screenshot (`pip install 'lazyworker[ocr]'`).
This recovers text that is **not** in the accessibility tree — drawn text, images, custom views —
as `{text, box:[x,y,w,h], size, confidence}`, in the same screen-point coordinates as the tree.
A component outside the tree can then be acted on by coordinate: OCR gives the box, and
`lazyworker ui tap --at <cx>,<cy>` taps its center (a real touch hits the view via hit-testing,
regardless of accessibility).

Add `--detect` to also run a local visual UI detector — OmniParser (YOLO icon detection +
Florence-2 captioning), `pip install 'lazyworker[detect]'`, on-device. It finds icons/buttons/
regions from pixels (even ones absent from the tree) as `{label, box, size, confidence, container}`,
where `container` is the smallest tree element whose frame contains the detection. The detector is
heavy (downloads model weights, loads PyTorch); use it for exploration, not per-action.

**Aggregate operations** — pipe an ordered JSON array of ops (stop-on-error by default):

```bash
echo '[{"op":"tap","label":"Search"},
       {"op":"type","text":"joilane"},
       {"op":"tap","label":"joilane","type":"Cell"}]' | lazyworker ui batch
```

## Configuration (`lazyworker.toml`)

```toml
[signing]
mode = "free"            # simulator | free | paid
team_id = "XXXXXXXXXX"   # required for free/paid; a team signed into Xcode
bundle_id_prefix = "com.example.wda"

[wda]
base_url = "http://127.0.0.1:8100"
port = 8100
# version = "v9.0.0"     # optional: pin the WDA git ref
```

## Library

```python
from lazyworker import WdaClient

with WdaClient("http://127.0.0.1:8100") as client:
    session = client.create_session("com.apple.Preferences")
    tree = session.source()
    cell = next(c for c in tree.find_all(type="Cell") if c.rect)
    session.tap(*cell.rect.center)
    session.type_text("hello")
```

Session actions: `source`, `screenshot`, `tap`, `double_tap`, `long_press`, `swipe`,
`type_text`, `apply_settings`, `deep_link`, `terminate`, `delete`. The accessibility tree
supports `walk`, `find`, and `find_all`. The `lazyworker.interaction` package adds the
agentic layer: `Interactor` (selector-resolving actions returning `OperationResult`),
`Locator`, and `BatchRunner`.

## Development

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy
```

## License

MIT — see [LICENSE](LICENSE).
