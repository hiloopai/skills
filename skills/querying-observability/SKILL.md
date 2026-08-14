---
name: querying-observability
description: >-
  Capture and query hiloop telemetry — what an agent actually did during a run. Covers wrapping an
  agent with `hiloop run` (network capture modes, OTLP, labels), orienting with `hiloop runs` (list /
  show / tail / complete), querying with read-only
  SQL over the `events` table and registered views (`hiloop query`, pragmatic flags or `--sql`),
  following a run live with `hiloop runs tail`, filtering related runs by `root_run_id` or
  `lineage_path`, and fetching raw payload bytes with `hiloop events payload`. Use when asked to
  capture / observe / trace an agent run, query telemetry or LLM calls, compute token metrics,
  follow a run live, or compare related runs.
---

# Querying observability

Capture a run, then read its telemetry back at three altitudes: **orient** (`hiloop runs list` /
`show`), **query** (read-only SQL with
`hiloop query`), and **watch** (`hiloop runs tail`).

## 1. Capture a run

`hiloop run` wraps any agent command and streams its telemetry to hiloop — model (LLM) calls,
tool/MCP traffic, the agent's own OpenTelemetry, and stdio — all tagged with run-lineage identity.

```sh
hiloop run --project default --label baseline -- claude -p "explain this repo"
```

The project comes from `--project` > the `HILOOP_PROJECT` env var > the active context's default
project (`hiloop config set-context <name> --project <slug>`) — with no match the command errors.
`--label` names the run in `runs list` (one is assigned when omitted). The telemetry endpoint is
discovered from the active context automatically (`--endpoint` / `HILOOP_TELEMETRY_ENDPOINT`
override it).

`hiloop run` is transparent (the child's output and exit code pass straight through) and announces
the **run id** on stderr when the run registers (`hiloop: recorded run …`) — capture it, you need
it to query. Three capture paths run in parallel:

- **Network capture** (model calls, tool/HTTP traffic): the default `--net-capture=auto` uses
  transparent capture on supported Linux hosts, and warns before falling back to an
  observation-only cooperative proxy elsewhere; `netns`/`proxy` request a mode explicitly, `off`
  disables it. Restrictive egress policies require the transparent mode and fail before the child
  starts if it is unavailable. Local runs have no secret-binding option.
- **The embedded OTLP receiver** (the agent's own spans/logs): on by default; `--no-otlp` disables.
- **stdio capture**: always on.

Useful extras: `--env-allowlist NAME,NAME` records named env vars on the run's `process.start`
event (nothing unlisted is ever captured); `--sample-resources` records process-tree resource
samples every 15s; `--egress-deny --allow-domain <domain>` runs the command under a deny-by-default
egress policy.

The same interceptor backs managed sandbox capture. There is no `hiloop sandbox run` verb.

## Sandbox ambient runs

CLI v0.18.0 returns an ambient run with every successful create:

```sh
receipt="$(hiloop sandbox create demo --output json -- sleep infinity)"
sandbox_id="$(printf '%s' "$receipt" | jq -r '.sandbox.id')"
run_id="$(printf '%s' "$receipt" | jq -r '.run_id')"
```

Read the sandbox id from `.sandbox.id`; the converged sandbox object is nested under `sandbox`, while
its ambient run id is top-level. The managed capture session writes an explicit create command,
buffered exec, SSH output, cooperative HTTP, and OTLP signals to this server-bound run. PTY
keystrokes/input and clients that bypass the proxy are not captured. An implicit image entrypoint
has proxy/OTLP capture but no process/stdio supervision.

Inside a sandbox, `hiloop run -- <command>` joins the same ambient run without registering another
run or needing a Hiloop credential. Query it exactly like a local run:

```sh
hiloop sandbox exec demo -- sh -lc 'printf "hello from sandbox\n"'
hiloop query --run-id "$run_id" --signal log
```

## 2. Orient: list, filter related runs, transcript

`hiloop runs` is the orientation group — find a run and read what it did:

```sh
hiloop runs list --project default     # in-flight first; --status/--since/--label/--principal narrow
hiloop runs list --root-run-id 01K6Z…  # runs related by the same root_run_id
hiloop runs show 01K70…                # one run's full event transcript, in time order
```

Related runs carry the same `root_run_id`, so `runs list --root-run-id <id>` returns them as a flat
listing. To put each run's own numbers beside it (the latest annotation of a
registered schema, a token or cost rollup), query for them instead: the `ann_<schema>` views take
the same `root_run_id` scoping (§8), and the `events` table groups by `lineage_path` (§4).
`runs show --output json` prints `{run, events}` — the run record plus the canonical event stream,
payloads up to 64 KiB inlined under `payload_ref.inline`.

Run lifecycle is client-owned: whatever starts a run ends it (`hiloop run` does it for you). If you
register runs yourself, stamp the ending with
`hiloop runs complete <id> --status succeeded|failed|canceled` — an unclosed run reads as
`running`, flagged `(stale)` once it has been quiet past a liveness window.

## 3. The smallest query

`hiloop query` runs a read-only SQL `SELECT` over the captured events. Pragmatic flags build the
`SELECT` for you for the common case — return the model calls in a run:

```sh
hiloop query --run-id 01K6Z… --signal llm
```

Flags that build the query: `--run-id`, `--signal`, `--fields`, `--limit`, `--since`, `--until`
(`--since`/`--until` accept RFC 3339 or nanoseconds). `--fields` picks the
columns — comma-separated plain column names, or `*` for every column; omitted, you get a minimal
default set (event id, time, signal, name, run identity, principal, payload size). The CLI prints a
table; pass `--output json` for the raw rows (always full; table cells truncate — tune with
`--max-cell-width`, `0` to disable).

Your **identity scopes the query to your organization automatically**, so the SQL never names an
organization — and can't reach another one. Annotation rows additionally read per project: select one
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

## 5. Filter related runs by lineage

When related runs carry lineage, every descendant shares its parent's `lineage_path` prefix. A
prefix predicate filters the parent and its descendants. Lineage is logical metadata; it does not
imply that the runs share filesystem state:

```sh
hiloop query --sql "
  SELECT lineage_path, signal, name, ts_wall_ns
  FROM events
  WHERE root_run_id = '01K6Z…'
    AND (lineage_path = '01K6Z….01K70…' OR lineage_path LIKE '01K6Z….01K70….%')
    AND signal = 'net'
  ORDER BY ts_wall_ns"
```

Use `root_run_id` for everything under one root, then add the `lineage_path` prefix to narrow the
result.

## 6. Follow a run live: `runs tail`

While a run is still going, **stream its events** as they arrive instead of re-querying — the
streaming companion to `runs show`. One line per event; it reconnects automatically (resuming where
it left off) until you stop it with Ctrl-C (`--no-auto-resume` for a single connection):

```sh
hiloop runs tail 01K6Z… --signal llm
```

`--signal` narrows it the same way it narrows `query`; `--output json` prints each event as
one JSON object per line. Payload contents up to 4 KiB stream inline under `payload_ref.inline`;
larger bodies carry only their content reference — fetch the bytes exactly as captured with:

```sh
hiloop events payload <event-id>
```

A tail follows one run id, so point it at the root run to watch the root's own events, or at a
child run's id to follow a single arm.

## 7. Filter on annotations

Annotations land in the **same `events` table** (signal `annotation`), and every registered
annotation schema also gives you a typed view named `ann_<schema>` — the schema name lowercased,
every non-alphanumeric character turned into `_` (schema `experiment.v1` → view
`ann_experiment_v1`; `data-views list` shows the exact names) — whose columns are the fields you
promoted, plus the run-lineage identity (`run_id`, `root_run_id`, `lineage_path`). Each view
already returns the current annotation per anchor, so scoping one by `root_run_id` compares related
runs in one query. "Show me only the good runs":

```sh
hiloop query --sql "
  SELECT run_id, lineage_path, outcome, score
  FROM ann_experiment_v1
  WHERE root_run_id = '01K6Z…' AND outcome = 'pass' AND score > 0.9
  ORDER BY score DESC"
```

Writing those annotations (run-, event-, range-, and project-scoped, plus the schemas that validate
them) is the `annotating-runs` skill.

## 8. Save a query as a data view

A **data view** is a named, organization-scoped `SELECT` you can query like a table — for a derivation
you keep reusing (an LLM-exchange join, a metric series):

```sh
hiloop data-views create llm_calls --sql @llm_calls.sql --description "One row per LLM exchange"
hiloop query --sql "SELECT * FROM llm_calls WHERE run_id = '01K6Z…'"
hiloop data-views list
hiloop data-views delete llm_calls
```

The `ann_<schema>` namespace is reserved for the schema views; every other name is yours.
