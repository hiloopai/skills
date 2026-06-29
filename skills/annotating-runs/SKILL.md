---
name: annotating-runs
description: >-
  Attach durable, structured judgments to a run's telemetry — an experiment's outcome, an eval score,
  a human verdict — that you can later filter and aggregate on. Covers `hiloop annotation-schema`
  (register the named JSON-Schema the payload is validated against), `hiloop annotate` (a point
  annotation on one event), and `hiloop annotate-range` (a time window), including the typed
  `--score` / `--outcome` columns and fork identity. Use when asked to annotate, label, mark, score,
  or record a verdict on a run, experiment, or branch — especially so experiments can self-annotate
  worked/failed + a metric.
metadata:
  version: 0.1.0
---

# Annotating runs

An **annotation** is a structured judgment stamped onto a point (or window) of a run's telemetry: an
experiment's `worked`/`failed` outcome, an eval `score`, a human's verdict on a branch. Annotations
land in the **same `events` table** as everything else (signal `annotation`), carry the same
`(run_id, fork_node_id, fork_path)` fork identity as the events they judge, and expose typed `score`
and `outcome` columns — so "show me only the branches that worked" is one SQL query later (see
`querying-observability-trees`).

> Annotations go to the telemetry gateway. Set `HILOOP_TELEMETRY_ENDPOINT` (or pass `--endpoint`);
> your hiloop credential is resolved the usual way (the `authenticating` skill).

## 1. Register a schema (once)

Every annotation names a **schema** — a JSON Schema (draft 2020-12) its payload is validated against
at ingest, so a label set stays consistent. Register it once per tenant:

```sh
hiloop annotation-schema register --name experiment --json-schema '{
    "type": "object",
    "properties": {
      "outcome": { "enum": ["worked", "failed"] },
      "metric":  { "type": "number" },
      "note":    { "type": "string" }
    },
    "required": ["outcome"]
  }'
```

`--json-schema` takes inline JSON, `@file`, or `-` (stdin). An unseen name starts at version 1; an
existing name adds the next version after a backward-compatibility check. Manage them with
`hiloop annotation-schema list` / `get <name>` / `archive <name>`.

## 2. Annotate a point

`hiloop annotate` stamps one annotation. The payload (`--data`) is validated against `--schema`; its
fields must be scalars. `--score` and `--outcome` are promoted to typed columns you can filter and
aggregate on:

```sh
hiloop annotate \
  --run-id "$HILOOP_RUN_ID" \
  --fork-node-id "$HILOOP_FORK_NODE_ID" \
  --fork-path "$HILOOP_FORK_PATH" \
  --schema experiment \
  --data '{"outcome":"worked","metric":0.9833,"note":"encoding arm"}' \
  --outcome worked \
  --score 0.9833 \
  --annotator-kind code
```

- `--annotator-kind` is who is judging: `human`, `llm`, `code`, `api` (default `human`).
- `--target-event-id <id>` pins the annotation to one event; omit it for a run/branch-level judgment.
- Inside a **captured run**, the fork identity is already in the environment as `HILOOP_RUN_ID`,
  `HILOOP_FORK_NODE_ID`, and `HILOOP_FORK_PATH` — which is exactly how an in-sandbox experiment
  **self-annotates** its own start/end and result.

## 3. Annotate a time window

When the judgment is about a span of activity rather than one event, use `hiloop annotate-range` with
inclusive wall-clock nanosecond bounds (same flags as `annotate`, plus the window):

```sh
hiloop annotate-range \
  --run-id "$HILOOP_RUN_ID" --fork-node-id "$HILOOP_FORK_NODE_ID" \
  --schema experiment --data '{"outcome":"failed"}' --outcome failed \
  --range-start-ns 1750000000000000000 --range-end-ns 1750000060000000000
```

## 4. Filter on what you annotated

Annotations are queryable immediately. The payoff — "fan out is cheap, review is the bottleneck" — is
filtering a fan-out tree down to the good branches:

```sh
hiloop telemetry query --sql "
  SELECT fork_path, score, outcome
  FROM events
  WHERE run_id = '$HILOOP_RUN_ID' AND signal = 'annotation'
        AND outcome = 'worked' AND score > 0.95
  ORDER BY score DESC"
```

See `querying-observability-trees` for the full query surface.
