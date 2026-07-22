---
name: querying-observability-trees
description: >-
  Capture and query hiloop's tree-native telemetry — what an agent actually did, keyed by its
  run-lineage path. Covers wrapping an agent with `hiloop run` (network capture modes, OTLP,
  labels), orienting with `hiloop runs` (list / tree / show / complete), querying with read-only
  SQL over the `events` table and registered views (`hiloop query`, pragmatic flags or `--sql`),
  following a run live with `hiloop runs tail`, scoping to a branch by `lineage_path`, fetching
  raw payload bytes with `hiloop events payload`, and diffing two runs. Use when asked to capture /
  observe / trace an agent run, query telemetry or LLM calls, compute token metrics, scope to a
  branch, follow a run live, or compare what two runs did.
metadata:
  version: 0.6.0
---

# Querying observability trees

hiloop telemetry is **tree-native**: every event is keyed by its position in the run-lineage tree
(`lineage_path`), so related runs read as one tree. You capture a run, then read it back at three
altitudes: **orient** (`hiloop runs list` / `tree` / `show`), **query** (read-only SQL with
`hiloop query`), and **watch** (`hiloop runs tail`).

## 1. Capture a run

`hiloop run` wraps any agent command and streams its telemetry to hiloop — model (LLM) calls,
tool/MCP traffic, the agent's own OpenTelemetry, and stdio — all tagged with run-lineage identity.

```sh
hiloop run --project default --label baseline -- claude -p "explain this repo"
```

The project comes from `--project` > the `HILOOP_PROJECT` env var > the active context's default
project (`hiloop config set-context <name> --project <slug>`) — with no match the command errors.
`--label` names the run in `runs list` / `tree` (one is assigned when omitted). The telemetry
endpoint is discovered from the active context automatically (`--endpoint` /
`HILOOP_TELEMETRY_ENDPOINT` override it).

`hiloop run` is transparent (the child's output and exit code pass straight through) and announces
the **run id** on stderr when the run registers (`hiloop: recorded run …`) — capture it, you need
it to query. Three capture paths run in parallel:

- **Network capture** (model calls, tool/HTTP traffic): the default `--net-capture=auto` uses
  transparent capture on supported Linux hosts, and warns before falling back to an
  observation-only cooperative proxy elsewhere; `netns`/`proxy` request a mode explicitly, `off`
  disables it. Secret bindings and restrictive egress policies require the transparent mode and
  fail before the child starts if it is unavailable.
- **The embedded OTLP receiver** (the agent's own spans/logs): on by default; `--no-otlp` disables.
- **stdio capture**: always on.

Useful extras: `--env-allowlist NAME,NAME` records named env vars on the run's `process.start`
event (nothing unlisted is ever captured); `--sample-resources` records process-tree resource
samples every 15s; `--egress-deny --allow-domain <domain>` runs the command under a deny-by-default
egress policy.

Sandbox one-shots register runs too: `hiloop sandbox run` prints its run id, and platform lifecycle
events (`signal = 'runtime'`) flow for every sandbox whether or not capture is on.

## 2. Orient: list, tree, transcript

`hiloop runs` is the orientation group — find a run, see its branches, read what it did:

```sh
hiloop runs list --project default    # in-flight runs first; --status/--since/--label/--principal narrow
hiloop runs tree 01K6Z…               # the lineage tree rooted at a run, parents above children
hiloop runs show 01K70…               # one run's full event transcript, in time order
```

`runs tree` takes `--columns '<schema>:<field>[,<field>…]'` (e.g.
`experiment.v1:metrics.val_bpb`) to roll up each run's latest annotation of a registered schema
next to the tree (see `annotating-runs`), and `--usage` to add measured resource-hours and token
counts per subtree. `runs show --trace` prints a to-scale waterfall summary above the transcript;
`runs show --output json` prints `{run, events}` — the run record plus the canonical event stream,
payloads up to 64 KiB inlined under `payload_ref.inline`.

Run lifecycle is client-owned: whatever starts a run ends it (`hiloop run` and `sandbox run` do it
for you). If you register runs yourself, stamp the ending with
`hiloop runs complete <id> --status succeeded|failed|canceled` — an unclosed run reads as
`running`, flagged `(stale)` once it has been quiet past a liveness window.

## 3. The smallest query

`hiloop query` runs a read-only SQL `SELECT` over the captured events. Pragmatic flags build the
`SELECT` for you for the common case — return the model calls in a run:

```sh
hiloop query --run-id 01K6Z… --signal llm
```

Flags that build the query: `--run-id`, `--signal`, `--lineage-path`, `--fields`, `--limit`,
`--since`, `--until` (`--since`/`--until` accept RFC 3339 or nanoseconds). `--fields` picks the
columns — comma-separated plain column names, or `*` for every column; omitted, you get a minimal
default set (event id, time, signal, name, run identity, principal, payload size). The CLI prints a
table; pass `--output json` for the raw rows (always full; table cells truncate — tune with
`--max-cell-width`, `0` to disable).

Your **identity scopes the query to your tenant automatically**, so the SQL never names a tenant —
and can't reach another one. Annotation rows additionally read per project: select one
(`--project` > `HILOOP_PROJECT` > the context's project) to see its annotations — including
project-scoped ones — or filter `project_id = '<id>'` in the SQL itself.

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

> Not sure which columns exist? Run `hiloop query --run-id 01K6Z… --fields '*' --limit 5 --output json`
> and read the keys off the rows; every column is in the reference.

## 5. Walk the tree: scope to one branch

Every descendant run shares its parent's `lineage_path` prefix, so `--lineage-path` scopes a query
to a whole subtree (the run *and* its descendant runs). Lineage is logical — it records which run
descends from which, whatever mechanism created the child:

```sh
hiloop query --run-id 01K6Z… --lineage-path 01K6Z….01K70… --signal net
```

This is how you "walk the tree": query the root for the whole run, then narrow to a child run's
lineage path to descend into a branch. In raw SQL the same scoping is
`WHERE lineage_path = '01K6Z….01K70…' OR lineage_path LIKE '01K6Z….01K70….%'`.

## 6. Follow a run live: `runs tail`

While a run is still going, **stream its events** as they arrive instead of re-querying — the
streaming companion to `runs show`. One line per event; it reconnects automatically (resuming where
it left off) until you stop it with Ctrl-C (`--no-auto-resume` for a single connection):

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

## 7. Diff two runs: what did A do that B didn't?

When two runs diverge from a shared starting point, a **diff** returns the events present in one
but absent in the other — the exact set-difference of what one branch did and another didn't. It
compares two **runs** (by run id) on a semantic key: signal, name, and attributes. From the CLI it
is an anti-join through `hiloop query`:

```sh
hiloop query --sql "
  SELECT a.event_id, a.ts_wall_ns, a.signal, a.name
  FROM events a
  LEFT JOIN events b
    ON  b.run_id = '01K71…'
    AND b.signal = a.signal
    AND b.name = a.name
    AND b.attributes_json = a.attributes_json
  WHERE a.run_id = '01K70…'
    AND a.signal = 'llm'
    AND b.event_id IS NULL
  ORDER BY a.ts_wall_ns"
```

Result: one row per event unique to run A. Swap the two run ids for the reverse. Use it to find the
divergent decision, validate that a change had only its intended effect, or triage a regression
against a known-good sibling. For aggregate comparisons across many branches (counts, percentiles,
tokens), use a grouped query with a `lineage_path` breakdown (§4) instead of a set-difference diff.

## 8. Filter on annotations

Annotations land in the **same `events` table** (signal `annotation`), and every registered
annotation schema also gives you a typed view named `ann_<schema>` — the schema name lowercased,
every non-alphanumeric character turned into `_` (schema `experiment.v1` → view
`ann_experiment_v1`; `data-views list` shows the exact names) — whose columns are the fields you
promoted, plus the run-lineage identity. So "show me only the good branches" is one query:

```sh
hiloop query --sql "
  SELECT lineage_path, outcome, score
  FROM ann_experiment_v1
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
