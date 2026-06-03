# Explorer — Identity & matching

How an observation is judged to be a known [State](atom.md) or not, and how a
transition's result is verified. This is the engine that powers online clustering
(assigning observations to states) and change detection (the unexpected-result
signal). Validated against a real, messy app (WeightWatchers) — see the placard.

## Hard requirement: rigorously generic

The identity function must use **no app-specific knowledge** — no hardcoded
identifier names, prefixes, chrome lists, or modal heuristics. "Background/chrome"
is defined **statistically**: whatever recurs across many states. **IDF (document
frequency over the live corpus) is the app-agnostic background discounter** — it
down-weights omnipresent tokens (chrome, modal-background) to ~0 and lets
screen-specific tokens dominate, with zero hardcoding.

> An earlier version used hardcoded foreground isolation (stripping `home-*`,
> `settings-back-button`, …). **That was rejected as casuística.** Generic
> foreground/modal isolation remains an **open problem** (the iOS tree does not
> cleanly mark modals — same window, full-screen rects, background still visible);
> if pursued, it must come from WDA structural traits, **never** from app ids.

## Identity = a weighted feature vector

`identity(observation, state) → score ∈ [0,1]`, computed over visible nodes:

| feature | similarity | weight | reliability |
|---|---|---|---|
| `title` (NavigationBar title; else top screen-specific text) | presence-aware (=1 / ≠0) | 3.5 navbar · 2.0 heuristic | weight scales with **extraction source** |
| `id_set` | IDF-weighted Jaccard | 3.0 | high (chrome auto-discounted by IDF) |
| `type_counts` (Switch/Button/Cell/…) | normalized count distance | 2.0 | factual, cheap, parallelizable |
| `text_set` | IDF-weighted Jaccard | 1.0–2.5* | low alone (dynamic) — IDF carries the title |
| `scalars` (interactive/text counts, depth) | `1 − |a−b|/max` | 1.0 | low (tiebreaker) |
| `visual` | — | **dropped** | thumbnail inflates same-theme apps; OCR only on demand |

Combination: **weighted average normalized over the features actually present**
(adaptive per-state). Two reliability principles, applied throughout:
- **Weight by informativeness:** a match on uninformative content contributes little
  (IDF mass), so chrome-only "perfect matches" cannot drive a merge.
- **Weight by extraction source:** a structural `title` (NavigationBar) is trusted
  more than a heuristic guess (`frame.texts.first`).

IDF must be computed over the **live corpus** (the whole store), and **unseen tokens
get a default high IDF, never 0** — otherwise identical sets falsely score 0.

## Usage is FILTERED by context, not 1-vs-N

At runtime the check is never "match against all N states". For a transition
`state A --action B--> ?`, the learned edge gives an **expectation** (`C`). Verify
the result against the **few relevant references**:

```
Tier 0 (common, cheap):  observed vs expected C   (and vs A for no-op)  → confirm
Tier 1 (surprise):       neither matches → broader candidate search (bucket/index)
Tier 2 (ambiguous):      grey band → escalate to the agent → learn (Layer 6)
```

This makes the common case 2–3 focused comparisons (not a scan), and the hard
1-vs-N discrimination (sibling-screen collisions) only matters on the rare surprise
path — context does the heavy lifting.

## The output: the "unexpected result" signal

The core product of verification. Not binary — it carries the **flavor**:

| flavor | observed ≈ | meaning |
|---|---|---|
| `confirmed` | expected C | the learned edge held |
| `no_op` | A | the action did nothing (dead control / already there) |
| `wrong_destination` | another known state D | the edge changed: B now leads to D |
| `unknown_destination` | no known state | new/changed screen → learn |
| `drifted` | C, with element-level change | reached C-ish, but C changed |

**One signal, two purposes** — disambiguated by the git anchor (provenance):
- the edge was learned at commit X; did the relevant app code change from X..HEAD?
  - **changed** → likely intentional → **repair the map** (self-correction)
  - **unchanged** → app should behave the same → likely **regression/flake → flag as a bug** (QA value)

The signal triggers: evidence capture (frozen before/action/after), edge reliability
update, and the repair/learning loop (Layer 6).

## Decision bands (fail-safe)

`SAME ≥ 0.85` · `DIFF ≤ 0.35` · between → `ESCALATE`. Auto-merge requires strong
evidence; anything ambiguous escalates rather than risking a **false merge** (the
worst error — it conflates two real states).

## Validated on the WeightWatchers lab

A diverse 30-screen corpus (tabs, modals, webview sheets, sibling settings screens,
re-visits), fully generic (zero hardcode):

- **0 false merges**, **0 false splits**.
- True duplicates merged, including the valuable cases: same screen across re-visits
  (dynamic content, stable identity); the **same screen cross-corpus**; and
  **distinct entry points converging on one screen** (a "find a workshop" row and a
  tab both reaching the Experiences screen).
- A switch **ON vs OFF → SAME** (the value is content, not identity).
- Genuinely-similar sibling webview sheets **escalate** (the agent decides) — the
  honest outcome when the tree alone can't separate them generically.

## Pending (Layer 6 and beyond)

- **Learned per-state weights / volatility:** the agent's verdict on an escalated
  pair is recorded → confident next time; stable text earns high weight per screen,
  dynamic text stays low. This is what turns today's escalations into confident
  decisions over time — never hardcoding.
- **Generic foreground/modal isolation** (open problem; WDA traits only).
- **Confidence/informativeness** formalized alongside the score.
