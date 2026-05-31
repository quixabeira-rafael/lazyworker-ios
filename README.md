# lazyworker

Agent-friendly iOS automation over [WebDriverAgent](https://github.com/appium/WebDriverAgent)
(WDA) for **simulators and real devices**. It drives **production apps** — no source code,
no Xcode integration at runtime.

`lazyworker` exposes a small typed Python library and a CLI designed to be consumed by an
autonomous agent: structured (JSON) output, descriptive help, and clear, actionable errors.

## Status

Early development. Implemented so far:

- Typed WDA client: `status`, `create_session`.
- Session actions: `source` (accessibility tree), `screenshot`, `tap`, `swipe`, `deep_link`,
  `terminate`, `delete`.
- Accessibility tree model with agent-friendly traversal (`walk`, `find`, `find_all`).
- Config loader (`lazyworker.toml`).
- CLI: `status`, `doctor`, `source`, `screenshot`.

Next milestone: device lifecycle (`bootstrap`, `up`, `down`) wrapping `xcodebuild`,
`go-ios`/`tidevice` and `iproxy`.

## Requirements

- Python >= 3.11
- A running WebDriverAgent (built once with Xcode; launched without Xcode afterwards).

## Library

```python
from lazyworker import WdaClient

with WdaClient("http://127.0.0.1:8100") as client:
    session = client.create_session("com.apple.Preferences")
    tree = session.source()
    button = tree.find(label="General")
    if button and button.rect:
        session.tap(*button.rect.center)
```

## CLI

```bash
lazyworker doctor          # is WDA reachable and ready?
lazyworker status          # full status as JSON
lazyworker source          # accessibility tree as JSON
lazyworker screenshot -o screen.png
```

## Development

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy
```
