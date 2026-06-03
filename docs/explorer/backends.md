# Explorer — Read/act backends (WDA vs idb) and the exploration pattern

How the explorer reads the UI tree and acts, the two available backends and their
trade-offs, the performance findings, and the validated exploration/navigation
pattern. Grounded in lab measurements on a real app (WeightWatchers) and a
primary-source deep-research pass on the frameworks.

## The two backends

| | WebDriverAgent (WDA) | Facebook idb |
|---|---|---|
| how it reads the tree | links **XCTest.framework**; captures an **XCTest snapshot** (private `XCElementSnapshot` via `XCAXClient_iOS`), recursively walks the **full element hierarchy**, and computes WDA-custom per-element `visible`/`accessible`/`hittable` (live hit-testing) | reads the **accessibility surface directly, without XCTest**: `idb_companion`'s `FBSimulatorAccessibilityCommands` uses Apple's private **`AccessibilityPlatformTranslation`** (`AXPTranslator`/`AXPTranslationObject`) over **CoreSimulator's `SimDevice` accessibility XPC** |
| tree shape | nested, complete (incl. deep webview internals) | **flat** list of exposed elements (surface) |
| read latency (measured) | 1–7s, **scales** with hierarchy size | **~0.17–0.23s, constant** |
| actions | W3C Actions (selector-targeted) | `idb ui tap/swipe/text` (coordinate) |
| real device | **yes** (Wi-Fi/USB) | the fast AX read is **simulator-only** |
| chrome (nav/tab bar) | exposed | **global nav chrome MISSED** (per-screen back buttons usually present) |
| maintenance | actively maintained (Appium) | **maintenance-mode** at Meta |

## Why WDA is slow — and it's not our code

Measured decomposition: our process+parse is ~0.2s; **the cost is the WDA snapshot**.
WDA's `/source` must snapshot the whole accessibility hierarchy with all attributes
resolved (a known XCTest limitation), plus compute `visible`/`accessible`/`hittable`
per element (live hit-testing) — none of which exist in stock XCTest. idb sidesteps
all of it with a direct accessibility read. Mitigations on WDA: **`snapshotMaxDepth`**
(validated: depth 12 cut menu source 3.6s→1.06s while keeping all rows),
`pageSourceExcludedAttributes`, `includeHittableInPageSource=false`.

Sources: [WDA slowness (Appium)](https://appium.github.io/appium-xcuitest-driver/latest/troubleshooting/wda-slowness/) ·
[idb FBSimulatorAccessibilityCommands.m](https://github.com/facebook/idb/blob/main/FBSimulatorControl/Commands/FBSimulatorAccessibilityCommands.m) ·
[WDA XCAXClient_iOS.h](https://github.com/facebookarchive/WebDriverAgent/blob/master/PrivateHeaders/XCTest/XCAXClient_iOS.h)

## The cost is mostly designed away

- **Warm replay is source-free:** navigate by **stored coordinate** (`ui tap --at`),
  no tree read at all — so WDA's snapshot cost does not bite the common path.
- **Cold/discovery + verify** need a read → idb (15× on heavy screens) or a tuned
  shallow WDA snapshot.
- **Readiness/verify**: `--wait-until <component>` doubles as the verification
  (component appears → confirmed; times out → unexpected result).

## Portability (WDA → idb), summarized

- **Backend-agnostic (port for free):** `ui find` (search is ours), `ui color`,
  `ui screen --ocr/--detect`, `--wait settle` — they run on the screenshot or on
  the tree-as-data, not on WDA's API.
- **Direct idb equivalents:** tap/long-press/scroll/type/deeplink/screenshot,
  device list, status.
- **Medium (rework):** selector-targeted tap (resolve→coordinate), session model
  (idb is sessionless), the gesture engine, flat-tree adaptation, container grouping.
- **Hard / regression:** **real-device reads** (idb fast read is sim-only).

## Recommendation: pluggable backend

A `Reader`/`Driver` interface with two impls: **idb for the simulator** (fast
cold/discovery + everyday reads), **WDA for real devices** and as the universal
fallback (and for the global nav chrome idb can't see). The explorer learns and
replays on the same backend (or normalizes signals), with the backend tagged in
provenance — signals computed on a WDA nested tree differ from an idb flat tree.

## Validated exploration / navigation pattern

A full navigation graph built and traversed **100% via idb on a real app**, no app
relaunch, identity-driven:

- **Nodes = states**, identified by the engine's signals (id_set/type_counts/text/…
  computed on idb's flat tree).
- **Edges learned, including the return:** `menu --tap row--> dest`, and the
  **return edge** is discovered per destination — the back/close button is resolved
  *from idb* (`weekly_plan_back_button`, `settings-back-button`, `Close`, …) and the
  edge records where it actually lands (some details return to the **menu**, some
  sheets dismiss to **home**). This is the "go and come back" as two distinct edges.
- **Recovery via the graph:** when a back overshoots to home, the `home --hamburger-->
  menu` edge brings it back to continue. The hamburger is the one chrome element idb
  does NOT expose, so its coordinate is stored (learned once).
- **Avoid-list:** destructive entry points (e.g. `sign-out`) are skipped, never tapped
  autonomously.
- **Identity drives traversal:** after each action the result's identity says where we
  landed (menu / home / detail / unexpected), which selects the next edge.

This is the cold/discovery half of the loop; warm replay then navigates the learned
graph by stored coordinate + `--wait-until` verification — fast and source-free.

## idb operational notes (learned at the workbench)

- **idb returns the full list in one read, with viewport-relative coordinates** —
  off-screen rows have `y > screen_height` (or negative after scrolling up). So a
  single `describe-all` tells you every element exists, but only those with
  `0 < y < screen_height` are tappable right now.
- **`idb ui swipe` needs a `--duration`** to actually scroll. An instant (no-duration)
  swipe is a flick/no-op that does not move a list — this was the bug that made deep
  rows unreachable. A real drag (`--duration 0.6`) scrolls; the off-screen rows then
  move into the tappable viewport. A long menu typically covers in a couple of drag
  positions (it bottoms out — further drags don't change the coordinates).
- Consequence for scroll-to-find: drag with a duration, re-read, and tap a target once
  its `y` falls in `[~90, screen_height]`.
