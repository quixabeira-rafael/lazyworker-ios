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

Session actions: `source`, `screenshot`, `tap`, `swipe`, `type_text`, `deep_link`,
`terminate`, `delete`. The accessibility tree supports `walk`, `find`, and `find_all`.

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
