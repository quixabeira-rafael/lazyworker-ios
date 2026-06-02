# The iOS accessibility tree

Every `lazyworker ui` command that reads the screen — `tree`, `find`, `color`,
the `--wait-until`/`--wait-gone` predicates — works against the **accessibility
tree**: a snapshot of the on-screen UI that WebDriverAgent builds from Apple's
XCUITest engine (`GET /source`).

This page is the long-form reference. For the same content at the terminal, run:

```bash
lazyworker ui schema          # readable
lazyworker ui schema --json   # machine-readable (fields + full type catalog)
```

## Where the data comes from

```
your app (UIKit/SwiftUI)  →  Accessibility API  →  XCUITest snapshot  →  WDA /source  →  lazyworker
```

lazyworker does not invent any of these fields — it normalizes what WDA reports
for each XCUIElement. A node only carries the attributes the app actually
exposes through accessibility; if a control was never given a label or an
identifier in code, those fields come back `null`.

## Node fields

Each node of `ui tree` (and each match of `ui find`) has these fields:

| Field | Source (XCUITest / WDA) | Type | Anchor? | Meaning |
|---|---|---|:---:|---|
| `type` | `XCUIElement.ElementType` | string | ✅ | Element kind (`Button`, `Cell`, `StaticText`…). Always present. |
| `identifier` | `accessibilityIdentifier` | string \| null | ✅ | The test id set in code. **Locale-independent — the best anchor.** Often `null` on system/web content. |
| `label` | `accessibilityLabel` | string \| null | ⚠️ | Human-facing text (what VoiceOver speaks). **Changes with device language.** |
| `value` | `accessibilityValue` | string \| null | ❌ | Current value: a text field's contents, a switch's `"0"`/`"1"`, a slider's position. Reflects *state*, not identity. |
| `name` | `wdName` (identifier-or-label) | string \| null | ⚠️ | Convenience field: the identifier if set, otherwise the label. Good for display, ambiguous for anchoring. |
| `rect` | `frame` | `{x, y, width, height}` \| null | ❌ | On-screen box in **points**, origin top-left. `rect.center` is the `--at` fallback point. |
| `enabled` | `isEnabled` | bool \| null | ❌ | Accepts interaction. Disabled controls are in the tree but won't respond to a tap. |
| `visible` | `isVisible` | bool \| null | ❌ | On screen. `find`/`tap` consider only visible nodes by default (`--any-visibility` widens). |
| `children` | child elements | node[] | — | Nested nodes, depth-first. Present in `ui tree`; **omitted from `ui find` matches** (flat projection). |

### Anchoring: how to pick a selector

The whole point of the tree is to turn "the blue Save button" into a stable
selector. Order of preference:

1. **`--identifier`** — set by the app's developers for testing; survives a
   language change and a copy rewrite. If it exists, use it.
2. **`--label` + `--type`** together — when there's no identifier. The `--type`
   disambiguates (a screen often has the same label on a `StaticText` and the
   `Button` wrapping it).
3. **`--at X,Y`** from `rect.center` — last resort. Coordinates break the moment
   layout shifts, so prefer them only for elements that have no addressable
   attributes at all (decorative `Image`, custom-drawn canvas).

Never anchor on `value` (it changes as the user interacts) or on `name` alone
(you can't tell whether it came from the identifier or the label).

## Element types (the `type` field)

The `type` strings are WebDriverAgent's rendering of `XCUIElement.ElementType`.
Grouped for orientation; the union is the complete catalog.

- **Roots & containers** — `Application`, `Window`, `Sheet`, `Drawer`,
  `Popover`, `Group`, `Other`, `ScrollView`, `CollectionView`, `Table`,
  `TableRow`, `TableColumn`, `Outline`, `OutlineRow`, `Browser`, `Cell`,
  `Grid`, `LayoutArea`, `LayoutItem`, `SplitGroup`
- **Bars & navigation** — `NavigationBar`, `TabBar`, `TabGroup`, `Toolbar`,
  `StatusBar`, `MenuBar`, `MenuBarItem`, `Tab`, `DockItem`, `TouchBar`,
  `StatusItem`
- **Buttons & controls** — `Button`, `RadioButton`, `RadioGroup`, `CheckBox`,
  `DisclosureTriangle`, `PopUpButton`, `ComboBox`, `MenuButton`,
  `ToolbarButton`, `Switch`, `Toggle`, `Slider`, `Stepper`,
  `SegmentedControl`, `Link`, `ColorWell`, `IncrementArrow`, `DecrementArrow`,
  `Handle`, `Splitter`
- **Text & input** — `StaticText`, `TextField`, `SecureTextField`,
  `SearchField`, `TextV`, `Key`, `Keyboard`
- **Pickers** — `Picker`, `PickerWheel`, `DatePicker`
- **Indicators** — `PageIndicator`, `ProgressIndicator`, `ActivityIndicator`,
  `LevelIndicator`, `RatingIndicator`, `RelevanceIndicator`, `ValueIndicator`,
  `Timeline`, `Ruler`, `RulerMarker`
- **Media & misc** — `Image`, `Icon`, `Map`, `WebView`, `Menu`, `MenuItem`,
  `Alert`, `Dialog`, `HelpTag`, `Matte`, `Any`

A few that trip people up:

- **`Other`** — the catch-all. Custom-drawn views, SwiftUI containers without a
  semantic role, and many wrappers land here. Don't filter on `Other`; reach for
  the labelled child instead.
- **`StaticText` vs `Button`** — the visible label is usually a `StaticText`
  *inside* a tappable `Button`/`Cell`. Tap the container (`--type Button`), read
  text from the `StaticText`.
- **`TextV`** — a multi-line text view (Apple's `textView`), not a typo.
- **`SecureTextField`** — password fields; `value` is masked, never the real
  text.

## Gotchas

- **Hidden ≠ absent.** A node off-screen (below the fold, in another tab) is
  still in the tree with `visible: false`. `find`/`tap` skip it by default;
  `scroll-to` exists precisely to bring it into view before acting.
- **Labels are localized.** A test that taps `--label "Entrar"` breaks on an
  English build. Prefer `identifier`, or accept that label selectors are
  locale-bound.
- **Web/hybrid content is sparse.** Inside a `WebView`, identifiers are usually
  absent and the structure is flat — lean on `label`/`value` and OCR
  (`ui screen --ocr`) there.
- **The status bar (clock) lives in the tree too.** Its text changes every
  minute; never anchor on it.
- **`ui find` returns a flat projection.** Matches carry `type`, `label`,
  `name`, `value`, `identifier`, `rect`, `visible` — no `children`, no
  `enabled`. Use `ui tree` when you need the hierarchy or the enabled state.

## See also

- [`recipes.md`](recipes.md) — command combinations built on this schema.
- `lazyworker ui schema --json` — this reference as data.
