---
name: annotating-runs
description: >-
  Attach durable, structured judgments to a run's telemetry — an experiment's outcome, an eval score,
  a human verdict — that you can later filter and aggregate on. Covers `hiloop annotation-schema`
  (register the named JSON-Schema the payload is validated against, and promote the fields you query),
  `hiloop annotate` (a point annotation on one event), and `hiloop annotate-range` (a time window). An
  annotation's payload is tenant-defined — promote the fields you query into typed columns; everything
  stays in the JSON payload. Use when asked to annotate, label, mark, score, or record a verdict on a
  run, experiment, or branch — especially so experiments can self-annotate worked/failed + a metric.
metadata:
  version: 0.2.0
---

# Annotating runs

An **annotation** is a structured judgment stamped onto a point (or window) of a run's telemetry: an
experiment's `worked`/`failed` outcome, an eval `score`, a human's verdict on a branch. Annotations
land in the **same `events` table** as everything else (signal `annotation`) and carry the same
`(run_id, lineage_path)` run-lineage identity as the events they judge.

An annotation's payload is **entirely tenant-defined** — there are no built-in fields. You decide
what an annotation carries (a score, a verdict, an annotator, a note, a nested object) by registering
a schema for it. To make a field fast to filter and sort on across many runs, **promote** it into a
typed column at register time; promoted or not, every field stays in the payload and is read back by
name — so "show me only the branches that worked" is one SQL query later (see
`querying-observability-trees`).

> Annotations go to the telemetry gateway. Set `HILOOP_TELEMETRY_ENDPOINT` (or pass `--endpoint`);
> your hiloop credential is resolved the usual way (the `authenticating` skill).

## 1. Register a schema (once)

Every annotation names a **schema** — a JSON Schema (draft 2020-12) its payload is validated against
at ingest, so a label set stays consistent. Promote the fields you intend to query (`--promote
field:type[:identity][:bloom]`, where `type` is `str` / `f64` / `i64` / `bool`) so they get columnar
acceleration; `:identity` makes a field part of the latest-wins supersession key, and `:bloom` adds a
point-lookup index (string fields only). Register it once per tenant:

```sh
hiloop annotation-schema register --name experiment --json-schema '{
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
existing name adds the next version after a backward-compatibility check. Manage them with
`hiloop annotation-schema list` / `get <name>` / `archive <name>`.

## 2. Annotate a point

`hiloop annotate` stamps one annotation. Everything the annotation carries goes in the payload
(`--data` for a flat object of scalars, or `--attributes-json` for a nested payload); it is validated
against `--schema`. There are no special value flags — `score`, `outcome`, and `annotator` are just
payload fields (the ones you promoted lift into typed columns for fast filter/sort while staying in
the JSON):

```sh
hiloop annotate \
  --run-id "$HILOOP_RUN_ID" \
  --lineage-path "$HILOOP_LINEAGE_PATH" \
  --schema experiment \
  --data '{"outcome":"worked","score":0.9833,"annotator":"code","note":"encoding arm"}'
```

- `--target-event-id <id>` pins the annotation to one event; omit it for a run/branch-level judgment.
- Use `--attributes-json` (inline JSON, `@file`, or `-`) when the payload nests objects or arrays;
  it preserves structure verbatim and is mutually exclusive with `--data`.
- Inside a **captured run**, the run-lineage identity is already in the environment as `HILOOP_RUN_ID`
  and `HILOOP_LINEAGE_PATH` — which is exactly how an in-sandbox experiment **self-annotates** its own
  start/end and result.

## 3. Annotate a time window

When the judgment is about a span of activity rather than one event, use `hiloop annotate-range` with
inclusive wall-clock nanosecond bounds (same payload flags as `annotate`, plus the window):

```sh
hiloop annotate-range \
  --run-id "$HILOOP_RUN_ID" --lineage-path "$HILOOP_LINEAGE_PATH" \
  --schema experiment --data '{"outcome":"failed"}' \
  --range-start-ns 1750000000000000000 --range-end-ns 1750000060000000000
```

## 4. Filter on what you annotated

Annotations are queryable immediately. The payoff — "fan out is cheap, review is the bottleneck" — is
filtering a fan-out tree down to the good branches. Every field lives in `attributes_json`, read by
name with `hiloop_json_get` (a promoted field reads from its fast column transparently; alias the
expression for readability):

```sh
hiloop telemetry query --sql "
  SELECT lineage_path,
         CAST(hiloop_json_get(attributes_json, '\$.score') AS DOUBLE) AS score,
         hiloop_json_get(attributes_json, '\$.outcome') AS outcome
  FROM events
  WHERE run_id = '$HILOOP_RUN_ID' AND signal = 'annotation'
        AND hiloop_json_get(attributes_json, '\$.outcome') = 'worked'
        AND CAST(hiloop_json_get(attributes_json, '\$.score') AS DOUBLE) > 0.95
  ORDER BY score DESC"
```

See `querying-observability-trees` for the full query surface.
