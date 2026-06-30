---
name: querying-observability-trees
description: >-
  Capture and query hiloop's tree-native telemetry — what an agent actually did, keyed by its
  run-lineage path. Covers wrapping an agent with `hiloop run`, querying with read-only SQL over the `events`
  table (`hiloop telemetry query`, pragmatic flags or `--sql`), following a run live with
  `hiloop telemetry tail`, scoping to a branch by `lineage_path`, and `branch-diff` to compare two
  child runs. Use when asked to capture / observe / trace an agent run, query telemetry or LLM calls,
  compute cost/token metrics, scope to a branch, follow a run live, or compare what two forked
  branches did.
metadata:
  version: 0.3.0
---

# Querying observability trees

hiloop telemetry is **tree-native**: every event is keyed by its position in the run-lineage tree
(`lineage_path`), so the trace tree mirrors the run tree. You capture a run, then read it back with
**read-only SQL** over a single `events` table — scoped to a branch, aggregated, followed live, or
diffed against a sibling run.

## 1. Capture a run

`hiloop run` wraps any agent command and streams its telemetry to hiloop — model (LLM) calls,
tool/MCP traffic, the agent's own OpenTelemetry, and stdio — all tagged with run-lineage identity.

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

Capture is on by default. Opt out of pieces with `--no-proxy` / `--no-otlp`. `--endpoint` is required
(or set `HILOOP_TELEMETRY_ENDPOINT`).

## 2. The smallest query

`hiloop telemetry query` runs a read-only SQL `SELECT` over the run's events. Pragmatic flags build
the `SELECT` for you for the common case — return the model calls in a run:

```sh
hiloop telemetry query --run-id 01K6Z… --signal llm
```

Flags that build the query: `--run-id`, `--signal`, `--lineage-path`, `--limit`, `--since`, `--until`
(`--since`/`--until` accept RFC 3339 or nanoseconds). The CLI prints a table; pass `--output json` for
the raw rows (always full; table cells truncate — tune with `--max-cell-width`, `0` to disable).

Your **identity scopes the query to your tenant automatically**, so the SQL never names a tenant — and
can't reach another one.

## 3. Filter, group, aggregate — raw SQL

For anything richer, pass a `SELECT` with `--sql` (inline, `@file`, or `-`/`@-` for stdin). The
query runs over the `events` table. Count model calls and total cost, grouped by branch:

```sh
hiloop telemetry query --sql "
  SELECT lineage_path, count(*) AS calls, sum(cost_usd) AS cost
  FROM events
  WHERE run_id = '01K6Z…' AND signal = 'llm'
  GROUP BY lineage_path
  ORDER BY cost DESC"
```

`--sql` is mutually exclusive with the pragmatic flags. The full column list and the query rules —
what's allowed, how errors come back, how to discover columns — are in
[`references/events-sql.md`](references/events-sql.md). Read it before hand-writing a complex query.

> Not sure which columns exist? Run `hiloop telemetry query --run-id 01K6Z… --limit 5 --output json`
> and read the keys off the rows; every column is in the reference.

## 4. Walk the tree: scope to one branch

Every descendant run shares its parent's `lineage_path` prefix, so `--lineage-path` scopes a query to
a whole subtree (the run *and* its descendant runs):

```sh
hiloop telemetry query --run-id 01K6Z… --lineage-path 01K6Z….01K70… --signal tool
```

This is how you "walk the tree": query the root for the whole run, then narrow to a child run's
lineage path to descend into a branch. In raw SQL the same scoping is
`WHERE lineage_path = '01K6Z….01K70…' OR lineage_path LIKE '01K6Z….01K70….%'`.

## 5. Follow a run live: `tail`

While a run is still going, **stream its events** as they arrive instead of re-querying — the
companion to `query`. One line per event; it reconnects automatically (resuming where it left off)
until you stop it with Ctrl-C:

```sh
hiloop telemetry tail --run-id 01K6Z… --signal llm
```

Same scoping flags as `query` (`--lineage-path`, `--signal`). This is what makes a fan-out tree
watchable live — point it at the run root to watch every branch, or at one `--lineage-path` to follow
a single arm.

## 6. Branch diff: what did A do that B didn't?

When two child runs branch from a shared snapshot and diverge, a **branch diff** returns the events
present in one run's subtree but absent in the other — the exact set-difference of what one branch did
and another didn't. It compares two **runs** (by run id), not two lineage paths.

```sh
hiloop telemetry branch-diff \
  --run-id-a 01K70… \
  --run-id-b 01K71… \
  --signal llm
```

Result: one row per event unique to run A. Swap `--run-id-a`/`--run-id-b` for the reverse. Use it to
find the divergent decision, validate that a change had only its intended effect, or triage a
regression against a known-good sibling. (Branch diff is its own endpoint — it encodes run-tree
semantics the bare `events` table doesn't surface — not something you hand-write as SQL.)

For aggregate comparisons across many branches (counts, percentiles, cost), use a grouped query with
a `lineage_path` breakdown (§3) instead of a set-difference diff.

## 7. Filter on annotations

Annotations land in the **same `events` table** (signal `annotation`), carrying typed `score` and
`outcome` columns plus the same run-lineage identity as the events they judge. So "show me only the good
branches" is one query:

```sh
hiloop telemetry query --sql "
  SELECT lineage_path, score, outcome
  FROM events
  WHERE run_id = '01K6Z…' AND signal = 'annotation'
        AND outcome = 'pass' AND score > 0.9
  ORDER BY score DESC"
```

Writing those annotations (point, range, and the schemas that validate them) is the
`annotating-runs` skill.
