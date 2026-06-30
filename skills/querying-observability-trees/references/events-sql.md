# Querying the `events` table (read-only SQL)

`hiloop telemetry query` runs a **read-only `SELECT`** against a single denormalized table, `events`,
holding every captured telemetry event. The pragmatic flags (`--run-id`, `--signal`, `--lineage-path`,
`--since`/`--until`, `--limit`) build a `SELECT * FROM events WHERE …` for you; `--sql` sends an
arbitrary `SELECT` (inline, `@file`, or `-`/`@-` for stdin). There is one query surface — SQL — and
no structured spec.

## How it's kept safe

Every query runs through a gateway that:

- **Forces a tenant predicate from your identity**, so your SQL is tenant-agnostic — you never write
  (and can't reach) a `tenant_id` other than your own.
- **Allows only read-only single-statement `SELECT`s.** DDL/DML (`INSERT`/`UPDATE`/`DROP`/…), multiple
  statements, `information_schema`, and file-reading functions are rejected.
- **Validates every column against the allowlist below** before executing, and **caps resources**
  (row limit, memory, timeout). An unknown column comes back as a structured `INVALID_ARGUMENT` error
  that names the offending identifier — so a typo is a clear message, not a silent empty result.

## Columns

`SELECT *` returns these (a column not set for a given signal is null). When unsure, run a small
`--limit 5 --output json` query and read the keys off the rows.

**Event spine** (every event):

- `event_id` — unique event id.
- `run_id` — the run (session) the event belongs to.
- `lineage_path` — the run-lineage path: a dotted sequence of run ULIDs from the root run to this
  event's run (e.g. `01K6Z….01K70…`); breakdown or scope by this to compare branches.
- `ts_wall_ns` — wall-clock timestamp in nanoseconds (what `--since`/`--until` match against).
- `event_time` — the same instant as a SQL timestamp (use for `date_trunc`, ordering).
- `signal` — event kind: `llm`, `tool`, `mcp`, `stdio`, `http`, `annotation`, … (the most common
  filter axis).
- `name` — operation/event name (e.g. `llm.call`).
- `attributes_json` — signal-specific fields as a JSON string (the catch-all; wide — keep it last or
  out of table output).

**LLM / model calls** (`signal = 'llm'`):

- `gen_ai_model` — the model name.
- `prompt_tokens`, `completion_tokens`, `cached_tokens` — token counts.
- `cost_usd` — estimated model cost.

**HTTP / tool traffic**: `http_method`, `http_host`, `http_target`, `http_status_code`,
`http_exchange_id`.

**Tracing**: `trace_id`, `span_id`, `parent_span_id`.

**Annotations** (`signal = 'annotation'`; see the `annotating-runs` skill): `target_event_id` (the
event judged) and `range_start_ns` / `range_end_ns` (for range annotations) are structural columns.
The judgment payload itself is tenant-defined and lives in `attributes_json` — read any field by name
with `hiloop_json_get(attributes_json, '$.field')` (e.g. an eval `score`, a `pass`/`fail` `outcome`,
an `annotator`). Promoted fields read fast from a typed column transparently.

## Patterns

Scope to one branch and its descendants:

```sql
SELECT * FROM events
WHERE run_id = '01K6Z…'
  AND (lineage_path = '01K6Z….01K70…' OR lineage_path LIKE '01K6Z….01K70….%')
```

Cost and token totals per branch:

```sql
SELECT lineage_path,
       count(*)               AS calls,
       sum(cost_usd)          AS cost_usd,
       sum(prompt_tokens)     AS prompt_tokens,
       sum(completion_tokens) AS completion_tokens
FROM events
WHERE run_id = '01K6Z…' AND signal = 'llm'
GROUP BY lineage_path
ORDER BY cost_usd DESC
```

Cost over time, one-minute buckets:

```sql
SELECT date_trunc('minute', event_time) AS minute, sum(cost_usd) AS cost_usd
FROM events
WHERE run_id = '01K6Z…' AND signal = 'llm'
GROUP BY minute ORDER BY minute
```

Failed HTTP calls in one branch:

```sql
SELECT ts_wall_ns, http_host, http_target, http_status_code
FROM events
WHERE run_id = '01K6Z…' AND signal = 'http' AND http_status_code >= 400
  AND (lineage_path = '01K6Z….01K70…' OR lineage_path LIKE '01K6Z….01K70….%')
ORDER BY ts_wall_ns
```

Only the winning branches, by annotation:

```sql
SELECT lineage_path,
       CAST(hiloop_json_get(attributes_json, '$.score') AS DOUBLE) AS score,
       hiloop_json_get(attributes_json, '$.outcome') AS outcome
FROM events
WHERE run_id = '01K6Z…' AND signal = 'annotation'
      AND hiloop_json_get(attributes_json, '$.outcome') = 'pass'
      AND CAST(hiloop_json_get(attributes_json, '$.score') AS DOUBLE) > 0.9
ORDER BY score DESC
```

## Response shape

The query returns JSON object rows: `{ "rows": [ { "col": value, … }, … ] }`, nulls omitted. The CLI
renders them as a table whose columns are the union of keys across rows; `--output json` is the
untruncated machine view.

## Related endpoints (their own commands, not SQL)

- **`hiloop telemetry tail`** — follow a run's events live (SSE). Same scoping flags as `query`.
- **`hiloop telemetry branch-diff`** — set-difference of two fork branches; see the parent SKILL.md §6.
- **Rollup** — a fixed server-owned LLM token/cost aggregate (grouped by model + time bucket), reached
  via the passthrough: `hiloop api /v1/telemetry/rollup -X post -d '{ "spec": { "runId": "01K6Z…",
  "bucketNs": "60000000000" } }'`. For ad-hoc grouping, prefer a `--sql` `GROUP BY` over rollup.
