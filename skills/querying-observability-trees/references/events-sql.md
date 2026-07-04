# Querying the `events` table (read-only SQL)

`hiloop query` runs a **read-only `SELECT`** against a single denormalized table, `events`, holding
every captured telemetry event — plus your registered views. The pragmatic flags (`--run-id`,
`--signal`, `--lineage-path`, `--since`/`--until`, `--limit`) build a `SELECT * FROM events WHERE …`
for you; `--sql` sends an arbitrary `SELECT` (inline, `@file`, or `-`/`@-` for stdin). There is one
query surface — SQL.

## How it's kept safe

Every query runs through a gateway that:

- **Forces a tenant predicate from your identity**, so your SQL is tenant-agnostic — you never write
  (and can't reach) a `tenant_id` other than your own.
- **Allows only read-only single-statement `SELECT`s.** DDL/DML (`INSERT`/`UPDATE`/`DROP`/…), multiple
  statements, `information_schema`, and file-reading functions are rejected.
- **Validates columns and functions** before executing, and **caps resources** (row limit, memory,
  timeout). An unknown column comes back as a structured `INVALID_ARGUMENT` error that names the
  offending identifier — so a typo is a clear message, not a silent empty result.

## Columns

`SELECT *` returns these (a column not set for a given signal is null). When unsure, run a small
`--limit 5 --output json` query and read the keys off the rows.

**Event spine** (every event):

- `event_id` — unique event id.
- `run_id` — the run (session) the event belongs to; `root_run_id` — the root run of its tree.
- `lineage_path` — the run-lineage path: a dotted sequence of run ULIDs from the root run to this
  event's run (e.g. `01K6Z….01K70…`); breakdown or scope by this to compare branches.
- `project_id` — the project the run records under.
- `principal` — the id of the key (or user) that wrote the event.
- `ts_wall_ns` — wall-clock timestamp in nanoseconds (what `--since`/`--until` match against);
  `ts_logical` orders events that share a nanosecond.
- `event_time` — the same instant as a SQL timestamp (use for `date_trunc`, ordering).
- `signal` — event kind: `exec` (process lifecycle), `llm` (model calls), `log` (stdio), `net`
  (other network traffic), `metric` (resource samples), `annotation` (the most common filter axis).
- `name` — operation/event name (e.g. `http.request`, `process.start`, `process.stdout`).
- `attributes_json` — signal-specific fields as a JSON string (the catch-all; wide — keep it last or
  out of table output).

**Payload reference** (events that captured a body):

- `payload_digest` — content address of the captured body. Fetch the bytes with
  `hiloop events payload <event-id>`, or resolve them in SQL with `payload_text(payload_digest)`.
- `payload_media_type`, `payload_size_bytes` — what the body is and how big.

**HTTP** (`llm` / `net` signals): `http_method`, `http_host`, `http_target`, `http_status_code`,
and `http_exchange_id` — the join key pairing a request event with its response event.

**Tracing**: `trace_id`, `span_id`, `parent_span_id`.

**Annotations** (`signal = 'annotation'`; see the `annotating-runs` skill): `target_event_id` (the
event judged) and `range_start_ns` / `range_end_ns` (for range annotations) are structural columns.
The judgment payload itself is tenant-defined and lives in `attributes_json` — read any field by
name with `hiloop_json_get(attributes_json, 'field')`, or query the schema's `ann_<schema>` view,
where promoted fields are real named columns (see "Views" below).

## Functions: from raw payloads to answers

LLM shapes (model, token counts, messages) are **not** precomputed columns — they derive from the
raw captured bodies at query time:

- `payload_text(payload_digest)` — resolve a captured body to text.
- `hiloop_sse_reassemble(text)` — reassemble a streamed (SSE) response into one JSON document.
- `hiloop_json_get(json_text, path)` — extract a scalar by dot-separated path
  (`'model'`, `'usage.output_tokens'`, `'choices.0.finish_reason'`; a leading `$.` is accepted and
  stripped). `hiloop_json_get_json(json_text, path)` returns a subtree as JSON text.
- `hiloop_genai_input_messages(body)` / `hiloop_genai_output_messages(body)` — normalize
  Anthropic/OpenAI request/response bodies into OTel-GenAI-shaped message lists.

## Patterns

Scope to one branch and its descendants:

```sql
SELECT * FROM events
WHERE run_id = '01K6Z…'
  AND (lineage_path = '01K6Z….01K70…' OR lineage_path LIKE '01K6Z….01K70….%')
```

Model calls and token totals per branch — request/response pair joined implicitly by reading the
response bodies, streamed responses reassembled first:

```sql
WITH resp AS (
  SELECT lineage_path,
         hiloop_sse_reassemble(payload_text(payload_digest)) AS body
  FROM events
  WHERE run_id = '01K6Z…' AND signal = 'llm' AND name = 'http.response'
)
SELECT lineage_path,
       count(*) AS calls,
       sum(CAST(coalesce(
             hiloop_json_get(body, 'usage.output_tokens'),
             hiloop_json_get(body, 'usage.completion_tokens')) AS BIGINT)) AS output_tokens
FROM resp
GROUP BY lineage_path
ORDER BY output_tokens DESC
```

Model calls over time, one-minute buckets:

```sql
SELECT date_trunc('minute', event_time) AS minute, count(*) AS calls
FROM events
WHERE run_id = '01K6Z…' AND signal = 'llm' AND name = 'http.request'
GROUP BY minute ORDER BY minute
```

Failed HTTP calls in one branch:

```sql
SELECT ts_wall_ns, http_host, http_target, http_status_code
FROM events
WHERE run_id = '01K6Z…' AND signal IN ('llm', 'net') AND http_status_code >= 400
  AND (lineage_path = '01K6Z….01K70…' OR lineage_path LIKE '01K6Z….01K70….%')
ORDER BY ts_wall_ns
```

Only the winning branches, by annotation — through the schema's view:

```sql
SELECT lineage_path, score, outcome
FROM ann_experiment
WHERE run_id = '01K6Z…' AND outcome = 'pass' AND score > 0.9
ORDER BY score DESC
```

## Views

Two kinds of named views resolve as `FROM`-clause tables alongside `events`:

- **`ann_<schema>`** — auto-created when you register an annotation schema (schema `experiment` →
  view `ann_experiment`; non-alphanumeric characters in the name become `_`). Columns: each
  **promoted** field under its declared name, plus the annotation's identity and anchors
  (`event_id`, `run_id`, `root_run_id`, `lineage_path`, `project_id`, `principal`, `ts_wall_ns`,
  `target_event_id`, `range_start_ns`, `range_end_ns`). The `ann_` namespace is reserved.
- **Data views** — your own saved `SELECT`s (`hiloop data-views create <name> --sql @file`), for
  derivations you keep reusing. The stored SQL is tenant-agnostic; your identity scopes every run.

## Response shape

The query returns JSON object rows: `{ "rows": [ { "col": value, … }, … ] }`, nulls omitted; 64-bit
integers (e.g. `ts_wall_ns`) come back as JSON strings so they survive every JSON parser. The CLI
renders them as a table whose columns are the union of keys across rows; `--output json` is the
untruncated machine view.

## Related commands (their own verbs, not SQL)

- **`hiloop runs tail <run-id>`** — follow a run's events live; same `--signal`/`--lineage-path` scoping.
- **`hiloop runs show <run-id>`** — one run's transcript, time-ordered, small payloads resolved inline.
- **`hiloop events payload <event-id>`** — the raw captured payload bytes, exactly as captured.
- **`hiloop telemetry branch-diff`** — set-difference of two fork branches; see the parent SKILL.md §7.
