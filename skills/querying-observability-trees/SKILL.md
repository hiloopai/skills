---
name: querying-observability-trees
description: >-
  Capture and query hiloop's tree-native telemetry — what an agent actually did, keyed by its
  run-lineage path. Covers wrapping an agent with `hiloop run`, orienting with `hiloop runs`
  (list / tree / show), querying with read-only SQL over the `events` table and registered views
  (`hiloop query`, pragmatic flags or `--sql`), following a run live with `hiloop runs tail`,
  scoping to a branch by `lineage_path`, fetching raw payload bytes with `hiloop events payload`,
  and `hiloop telemetry branch-diff` to compare two child runs. Use when asked to capture /
  observe / trace an agent run, query telemetry or LLM calls, compute token metrics, scope to a
  branch, follow a run live, or compare what two forked branches did.
metadata:
  version: 0.4.0
---

# Querying observability trees

hiloop telemetry is **tree-native**: every event is keyed by its position in the run-lineage tree
(`lineage_path`), so the trace tree mirrors the run tree. You capture a run, then read it back at
three altitudes: **orient** (`hiloop runs list` / `tree` / `show`), **query** (read-only SQL with
`hiloop query`), and **watch** (`hiloop runs tail`).

## 1. Capture a run

`hiloop run` wraps any agent command and streams its telemetry to hiloop — model (LLM) calls,
tool/MCP traffic, the agent's own OpenTelemetry, and stdio — all tagged with run-lineage identity.

```sh
hiloop run --project default -- claude -p "explain this repo"
```

The project comes from `--project` > the `HILOOP_PROJECT` env var > the active context's default
project (`hiloop config set-context <name> --project <slug>`) — with no match the command errors.
The telemetry endpoint is discovered from the active context automatically (`--endpoint` /
`HILOOP_TELEMETRY_ENDPOINT` override it).

`hiloop run` is transparent (the child's output and exit code pass straight through) and prints the
**run id** to stderr — capture it, you need it to query:

```
hiloop: capturing run 01K6Z… into project default
```

Capture is on by default. Opt out of pieces with `--no-proxy` / `--no-otlp`.

## 2. Orient: list, tree, transcript

`hiloop runs` is the orientation group — find a run, see its branches, read what it did:

```sh
hiloop runs list --project default    # one line per run: id, status, principal, started
hiloop runs tree 01K6Z…               # the lineage tree rooted at a run, parents above children
hiloop runs show 01K70…               # one run's full event transcript, in time order
```

`runs tree` takes `--columns '<schema>:<field>[,<field>…]'` to roll up each run's latest annotation
of a registered schema next to the tree (see `annotating-runs`). `runs show --output json` prints
`{run, events}` — the run record plus the canonical event stream, payloads up to 64 KiB inlined
under `payload_ref.inline`.

## 3. The smallest query

`hiloop query` runs a read-only SQL `SELECT` over the captured events. Pragmatic flags build the
`SELECT` for you for the common case — return the model calls in a run:

```sh
hiloop query --run-id 01K6Z… --signal llm
```

Flags that build the query: `--run-id`, `--signal`, `--lineage-path`, `--limit`, `--since`, `--until`
(`--since`/`--until` accept RFC 3339 or nanoseconds). The CLI prints a table; pass `--output json` for
the raw rows (always full; table cells truncate — tune with `--max-cell-width`, `0` to disable).

Your **identity scopes the query to your tenant automatically**, so the SQL never names a tenant — and
can't reach another one.

## 4. Filter, group, aggregate — raw SQL

For anything richer, pass a `SELECT` with `--sql` (inline, `@file`, or `-`/`@-` for stdin). The
query runs over the `events` table and every registered view — including the `ann_<schema>` views
that annotation-schema registration creates. Count model calls per branch:

```sh
hiloop query --sql "
  SELECT lineage_path, count(*) AS calls
  FROM events
  WHERE run_id = '01K6Z…' AND signal = 'llm' AND name = 'http.request'
  GROUP BY lineage_path
  ORDER BY calls DESC"
```

`--sql` is mutually exclusive with the pragmatic flags. The full column list, the signal
vocabulary, and the query rules — payload resolution, token metrics from raw bodies, how errors
come back — are in [`references/events-sql.md`](references/events-sql.md). Read it before
hand-writing a complex query.

> Not sure which columns exist? Run `hiloop query --run-id 01K6Z… --limit 5 --output json`
> and read the keys off the rows; every column is in the reference.

## 5. Walk the tree: scope to one branch

Every descendant run shares its parent's `lineage_path` prefix, so `--lineage-path` scopes a query to
a whole subtree (the run *and* its descendant runs):

```sh
hiloop query --run-id 01K6Z… --lineage-path 01K6Z….01K70… --signal net
```

This is how you "walk the tree": query the root for the whole run, then narrow to a child run's
lineage path to descend into a branch. In raw SQL the same scoping is
`WHERE lineage_path = '01K6Z….01K70…' OR lineage_path LIKE '01K6Z….01K70….%'`.

## 6. Follow a run live: `runs tail`

While a run is still going, **stream its events** as they arrive instead of re-querying — the
streaming companion to `runs show`. One line per event; it reconnects automatically (resuming where
it left off) until you stop it with Ctrl-C:

```sh
hiloop runs tail 01K6Z… --signal llm
```

Same scoping flags as `query` (`--lineage-path`, `--signal`); `--output json` prints each event as
one JSON object per line. Payload contents up to 4 KiB stream inline under `payload_ref.inline`;
larger bodies carry only their content reference — fetch the bytes exactly as captured with:

```sh
hiloop events payload <event-id>
```

This is what makes a fan-out tree watchable live — point it at the run root to watch every branch,
or at one `--lineage-path` to follow a single arm.

## 7. Branch diff: what did A do that B didn't?

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

For aggregate comparisons across many branches (counts, percentiles, tokens), use a grouped query
with a `lineage_path` breakdown (§4) instead of a set-difference diff.

## 8. Filter on annotations

Annotations land in the **same `events` table** (signal `annotation`), and every registered
annotation schema also gives you a typed view named `ann_<schema>` (schema `experiment` → view
`ann_experiment`) whose columns are the fields you promoted, plus the run-lineage identity. So
"show me only the good branches" is one query:

```sh
hiloop query --sql "
  SELECT lineage_path, outcome, score
  FROM ann_experiment
  WHERE run_id = '01K6Z…' AND outcome = 'pass' AND score > 0.9
  ORDER BY score DESC"
```

Writing those annotations (run-, event-, range-, and project-scoped, plus the schemas that validate
them) is the `annotating-runs` skill.

## 9. Save a query as a data view

A **data view** is a named, tenant-agnostic `SELECT` you can query like a table — for a derivation
you keep reusing (an LLM-exchange join, a metric series):

```sh
hiloop data-views create llm_calls --sql @llm_calls.sql --description "One row per LLM exchange"
hiloop query --sql "SELECT * FROM llm_calls WHERE run_id = '01K6Z…'"
hiloop data-views list
hiloop data-views delete llm_calls
```

The `ann_<schema>` namespace is reserved for the schema views; every other name is yours.
