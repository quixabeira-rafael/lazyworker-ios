# lazyworker docs

Reference for driving iOS apps with `lazyworker ui`, written for agents.

- **[tree-schema.md](tree-schema.md)** — the iOS accessibility tree: what every
  node field means, where it comes from, how to pick a stable selector, and the
  full catalog of element `type` values. The same content is available at the
  terminal via `lazyworker ui schema` (add `--json` for the machine-readable
  form).
- **[recipes.md](recipes.md)** — command combinations: orient on a screen,
  find→act→verify, `--jq` extraction, scroll-to, colour checks, batching, and
  the exit codes to branch on.

Start with the schema, then the recipes. For the command surface itself, run
`lazyworker ui --help`.
