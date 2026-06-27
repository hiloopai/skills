# QuerySpec reference

The full structured query the `hiloop telemetry query --spec` accepts. Six parts, all optional, that
compose. Send as inline JSON, `@file.json`, or `-` (stdin).

## Shape

```jsonc
{
  "runId": "01K6Z…",            // required: the run to query
  "filters":  [ /* Filter */ ],  // conjunctive (AND-ed) typed predicates
  "breakdowns": ["fork_path"],   // group-by columns
  "calculations": [ /* Calc */ ],// aggregations; empty → return matching rows
  "orders": [ /* Order */ ],     // sort
  "timeRange": { "startNs": "…", "endNs": "…" }, // inclusive wall-clock window, nanoseconds
  "forkPath": "/0/1",            // scope to a fork-tree subtree; empty/omitted = whole run
  "limit": 100                   // max rows when not aggregating
}
```

## Filters

```jsonc
{ "column": "signal", "op": "FILTER_OP_EQ", "value": { "stringValue": "llm" } }
```

Operators: `FILTER_OP_EQ`, `FILTER_OP_NE`, `FILTER_OP_GT`, `FILTER_OP_GTE`, `FILTER_OP_LT`,
`FILTER_OP_LTE`, `FILTER_OP_CONTAINS`, `FILTER_OP_EXISTS`.

Value types in `value`: `stringValue`, `intValue`, `doubleValue`, `boolValue` (use the one matching
the column's type).

## Calculations

```jsonc
{ "op": "CALCULATION_OP_COUNT" }
{ "op": "CALCULATION_OP_SUM", "column": "cost_usd" }
```

Operators: `CALCULATION_OP_COUNT`, `CALCULATION_OP_SUM`, `CALCULATION_OP_AVG`, `CALCULATION_OP_MIN`,
`CALCULATION_OP_MAX`, `CALCULATION_OP_P50`, `CALCULATION_OP_P95`, `CALCULATION_OP_P99`.

Output column naming: `<op>_<column>`, e.g. `sum_cost_usd`, `count`, `p95_duration_ns`. Reference
these names in `orders`.

## Orders

```jsonc
{ "column": "sum_cost_usd", "descending": true }
```

## Common columns

- `signal` — event kind: `llm`, `tool`, `mcp`, `stdio`, … (filter the most common axis).
- `fork_path` — fork-tree node path; breakdown or scope by this to compare branches.
- `cost_usd` — estimated model cost.
- `name` — operation/event name.
- timing columns in nanoseconds.

Column availability depends on the signal. When unsure, run a small unfiltered query with
`--output json` and inspect the returned rows to discover the columns present.

## Related endpoints

- **Rollup** — standard LLM token/cost metrics, grouped by exact model and fixed wall-clock bucket:
  `hiloop api /v1/telemetry/rollup -X post -d '{ "spec": { "runId": "01K6Z…", "bucketNs": "60000000000" } }'`
- **Branch diff** — set-difference of two branches; see the parent SKILL.md §5.
