---
name: annotating-runs
description: >-
  Attach durable, structured judgments to hiloop telemetry — an experiment's outcome, an eval score,
  a metric reading, a human verdict — that you can later filter and aggregate on. Covers
  `hiloop annotation-schema` (register the named JSON-Schema the payload is validated against, and
  promote the fields you query) and `hiloop annotations add`: a whole run (`--run`), one event
  (`--target-event`), a time window (`--range`), or a project (`--project`, run-less cross-run
  knowledge) — plus reading them back with `hiloop annotations list`. Promoted fields become named
  columns of the schema's `ann_<schema>` query view. Use
  when asked to annotate, label, mark, score, or record a verdict or metric on a run, experiment,
  or branch — especially so experiments can self-annotate worked/failed + a metric.
metadata:
  version: 0.5.1
---

# Annotating runs

An **annotation** is a structured judgment stamped onto a run, onto an event or time window within
it, or onto a project: an experiment's `worked`/`failed` outcome, an eval `score`, a metric reading,
a human's verdict on a branch. Annotations land in the **same `events` table** as everything else
(signal `annotation`) and carry the same `(run_id, lineage_path)` run-lineage identity as the events
they judge.

An annotation's payload is **entirely tenant-defined** — there are no built-in fields. You decide
what an annotation carries (a score, a verdict, a metrics object, a note) by registering a schema
for it. To make a field fast to filter and sort on across many runs, **promote** it at register
time: promoted fields become named columns of the schema's auto-created query view,
`ann_<schema-name>`; promoted or not, every field stays in the payload and is read back by name —
so "show me only the branches that worked" is one SQL query later (see
`querying-observability-trees`).

## 1. Register a schema (once)

Every annotation names a **schema** — a JSON Schema (draft 2020-12) its payload is validated against
at ingest, so a label set stays consistent. Promote the fields you intend to query (`--promote
field:type[:identity][:bloom]`, where `type` is `str` / `f64` / `i64` / `bool`) so they get columnar
acceleration; `:identity` makes a field part of the latest-wins supersession key, and `:bloom` adds a
point-lookup index (string fields only). Register it once per tenant:

```sh
hiloop annotation-schema register experiment --json-schema '{
    "type": "object",
    "properties": {
      "outcome":   { "enum": ["worked", "failed"] },
      "score":     { "type": "number" },
      "annotator": { "type": "string" },
      "note":      { "type": "string" }
    },
    "required": ["outcome"]
  }' \
  --promote score:f64 \
  --promote outcome:str \
  --promote annotator:str:identity
```

`--json-schema` takes inline JSON, `@file`, or `-` (stdin). An unseen name starts at version 1; an
existing name adds the next version after a backward-compatibility check. Registering also creates
the schema's query view, `ann_experiment`, with the promoted fields as named columns. Manage schemas
with `hiloop annotation-schema list` / `get <name>` / `archive <name>`.

## 2. Annotate a run (or one event, or a window)

`hiloop annotations add` stamps one annotation. Everything it carries goes in `--data` — a JSON object used
verbatim as the payload (nested objects and arrays preserved; inline, `@file`, or `-` for stdin),
validated against `--schema`. There are no special value flags — `score`, `outcome`, and `annotator`
are just payload fields:

```sh
hiloop annotations add \
  --run "$HILOOP_RUN_ID" \
  --schema experiment \
  --data '{"outcome":"worked","score":0.9833,"annotator":"code","note":"encoding arm"}'
```

- Inside a **captured run**, the run id is already in the environment as `HILOOP_RUN_ID` — which is
  exactly how an in-sandbox experiment **self-annotates** its own result. **Metrics are recorded the
  same way** — there is no stdout-metric convention; a training run annotates its own readings as it
  goes (`--data '{"metrics":{"val_bpb":0.9932},"step":1200}'`).
- `--target-event <event-id>` pins the annotation to one event; omit it for a run-level judgment.
- `--range <start>..<end>` targets a time window instead — each endpoint an RFC 3339 timestamp
  (`2026-07-03T10:14:22Z`) or a raw wall-clock nanosecond value (as returned in `ts_wall_ns` query
  columns), or both endpoints event ids (the window then spans those two events' recorded
  timestamps).
- **Retries are safe with `--event-id`.** Mint the annotation's event id yourself (a canonical
  26-character ULID): re-running with the same id returns the stored annotation instead of writing a
  duplicate, so an ambiguous failure (a 5xx, a lost response) can be retried blindly. The id names
  this logical annotation — never reuse it for different content. `--output json` prints
  `{"event_id": …}` either way. Omitted, the server mints a fresh id per invocation and a retry
  writes a new annotation.
- **Correction = a new annotation.** Readers take the newest write per (anchor, schema, target),
  refined by any `:identity` fields the schema declares — you never edit one in place.

## 3. Annotate a project — run-less, cross-run knowledge

A judgment that outlives any one run — "this approach dead-ends", a negative result, a promoted
winner — goes on the **project** instead of a run:

```sh
hiloop annotations add --project default --schema experiment \
  --data '{"outcome":"failed","note":"tokenizer swap: no effect on val_bpb"}'
```

Project annotations are durable cross-run knowledge: they survive every sandbox and show up in the
same query surface.

## 4. Read back and filter on what you annotated

`hiloop annotations list` reads a target's current annotations directly — the newest write per
(anchor, schema, target), no SQL needed:

```sh
hiloop annotations list --run <run-id>             # a run's own annotations
hiloop annotations list --run <run-id> --subtree   # the run's whole lineage subtree
hiloop annotations list --project <slug>           # a project's run-less annotations
```

`--history` returns every stored version instead of just the current one.

Annotations are also queryable immediately as SQL. The payoff — "fan out is cheap, review is the
bottleneck" — is filtering a fan-out tree down to the good branches. Promoted fields are named columns of the
schema's `ann_<schema>` view:

```sh
hiloop query --sql "
  SELECT run_id, lineage_path, outcome, score
  FROM ann_experiment
  WHERE outcome = 'worked' AND score > 0.95
  ORDER BY score DESC"
```

`hiloop runs tree <root-run-id> --columns 'experiment:score'` renders the latest rollup of a
promoted field next to each run in the lineage tree — the fastest way to eyeball a fan-out.

An unpromoted field stays in the JSON payload — read it by name from the events table with
`hiloop_json_get(attributes_json, 'note')`. See `querying-observability-trees` for the full query
surface.
