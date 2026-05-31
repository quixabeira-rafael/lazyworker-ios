# LazyWorker Lab

A minimal SwiftUI app that exercises every event the `lazyworker ui` layer can drive, so we can
validate the tool end-to-end. Bundle id: **`com.lazyworker.lab`** (iOS 16+).

Every action records a canonical `verb:target` string into one observable surface — a `StaticText`
with `accessibilityIdentifier("event-log")`. The e2e harness reads that node back to assert exactly
what happened (e.g. `tap:btn-primary`, `toggled:switch-1=on`, `scrolled_to:row-50`,
`submitted:login=ok`).

## Build & install (simulator)

```bash
xcodebuild -project lab/LazyWorkerLab.xcodeproj -target LazyWorkerLab \
  -sdk iphonesimulator -configuration Debug \
  CONFIGURATION_BUILD_DIR="$PWD/lab/build" build

xcrun simctl boot <UDID>            # or reuse the one `lazyworker up` booted
xcrun simctl install <UDID> lab/build/LazyWorkerLab.app
xcrun simctl launch <UDID> com.lazyworker.lab
```

## Build & install (real device)

```bash
xcodebuild -project lab/LazyWorkerLab.xcodeproj -target LazyWorkerLab \
  -sdk iphoneos -configuration Debug -allowProvisioningUpdates \
  DEVELOPMENT_TEAM=<TEAM_ID> CODE_SIGNING_ALLOWED=YES \
  CONFIGURATION_BUILD_DIR="$PWD/lab/build" build

xcrun devicectl device install app --device <UDID> lab/build/LazyWorkerLab.app
xcrun devicectl device process launch --device <UDID> com.lazyworker.lab
```

## Drive it

```bash
lazyworker up                       # WDA on the simulator (signing.mode = simulator)
lazyworker ui open com.lazyworker.lab
lazyworker ui tap --identifier link-tap     # navigate to the Tap lab
lazyworker ui tap --identifier btn-primary  # -> event-log == "tap:btn-primary"
lazyworker ui close
```

The end-to-end test suite lives in `tests/e2e/` (opt-in; see its README/markers).
