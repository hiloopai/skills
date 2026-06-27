---
name: querying-observability-trees
description: >-
  Capture and query hiloop's tree-native telemetry — what an agent actually did, keyed by fork-tree
  node. Covers wrapping an agent with `hiloop run`, structured `hiloop telemetry query` (filters,
  breakdowns, calculations, fork_path scoping), and `branch-diff` to compare two branches. Use when
  asked to capture / observe / trace an agent run, query telemetry or LLM calls, compute cost/token
  metrics, scope to a branch, or compare what two forked branches did.
metadata:
  version: 0.1.0
---

# Querying observability trees

hiloop telemetry is **tree-native**: every event is keyed by its position in the fork tree
(`fork_path`), so the trace tree mirrors the fork tree. You capture a run, then query it with a
structured, server-validated spec — by signal, scoped to a branch, aggregated, or diffed against a
sibling branch.

## 1. Capture a run

`hiloop run` wraps any agent command and streams its telemetry to hiloop — model (LLM) calls,
tool/MCP traffic, the agent's own OpenTelemetry, and stdio — all tagged with fork-tree identity.

```sh
export HILOOP_TELEMETRY_ENDPOINT="https://telemetry.hiloop.ai:443"
export HILOOP_PROJECT_ID="default"

hiloop run -- claude -p "explain this repo"
```

It is transparent (the child's output and exit code pass straight through) and prints the **run id**
to stderr — capture it, you need it to query:

```
hiloop: capturing run 01K6Z… into project default
```

Capture is on by default. Opt out of pieces with `--no-proxy` / `--no-otlp`.

## 2. The smallest query

Return the model calls in a run:

```sh
hiloop telemetry query --run-id 01K6Z… --signal llm
```

Pragmatic flags cover the common case: `--run-id`, `--signal`, `--fork-path`, `--limit`, `--since`,
`--until`. The CLI prints a table; pass `--output json` for the raw body (always full; table values
truncate — tune with `--max-cell-width`, `0` to disable).

## 3. Filter, group, aggregate

For anything richer, send a full **QuerySpec** with `--spec` (inline JSON, `@file`, or `-` for
stdin). Count model calls and total cost, grouped by branch:

```sh
hiloop telemetry query --spec '{
  "runId": "01K6Z…",
  "filters": [{ "column": "signal", "op": "FILTER_OP_EQ", "value": { "stringValue": "llm" } }],
  "breakdowns": ["fork_path"],
  "calculations": [
    { "op": "CALCULATION_OP_COUNT" },
    { "op": "CALCULATION_OP_SUM", "column": "cost_usd" }
  ],
  "orders": [{ "column": "sum_cost_usd", "descending": true }]
}'
```

Each row is the breakdown columns plus one column per calculation (e.g. `sum_cost_usd`). With no
calculations, you get matching rows up to `limit`. The full spec — all operators, calculations, and
columns — is in [`references/query-spec.md`](references/query-spec.md). Read it before hand-writing a
complex spec.

## 4. Walk the tree: scope to one branch

Every descendant of a fork node shares its `fork_path` prefix, so set `--fork-path` (or `forkPath`)
to scope a query to a whole subtree:

```sh
hiloop telemetry query --run-id 01K6Z… --fork-path /0/1 --signal tool
```

This is how you "walk the tree": query the root for the whole run, then narrow to `/0`, `/0/1`, … to
descend into a branch.

## 5. Branch diff: what did A do that B didn't?

When two branches fork from a shared snapshot and diverge, a **branch diff** returns the events
present in one subtree but absent in the other — the exact set-difference of what one branch did and
another didn't.

```sh
hiloop telemetry branch-diff \
  --run-id 01K6Z… \
  --path-a /0/0 \
  --path-b /0/1 \
  --signal llm
```

Result: one row per event unique to branch A. Swap `--path-a`/`--path-b` for the reverse. Use it to
find the divergent decision, validate that a change had only its intended effect, or triage a
regression against a known-good sibling.

For aggregate comparisons across many branches (counts, percentiles, cost), use a grouped query with
a `fork_path` breakdown (§3) instead of a set-difference diff.
