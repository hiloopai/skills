---
name: autoresearch
description: >-
  Run an autonomous, evidence-preserving research loop with hiloop: reuse a project, safely
  register idea and experiment schemas, propose diverse ideas, execute and score bounded arms,
  record evolving idea cards and immutable experiment rows, ensemble winners, and expose the
  run through the leaderboard, lineage tree, annotations, and fleet dashboard. Use when asked to
  autonomously optimize a metric over a supplied dataset and scorer, run an experiment loop, or
  produce a ranked research leaderboard.
metadata:
  version: 0.1.1
---

# Run an autonomous research loop

Own the loop from idea to evidence. Do not ask the user to choose ideas or copy results between
steps. The user watches; you propose, execute, annotate, compare, and summarize.

The proven path executes arms in the local directory inside one captured `hiloop run`. A sandboxed
arm path is documented at the end, but is a preview until the operator explicitly says its full
staging rehearsal is green. Never silently switch between them.

## Non-negotiable research rules

- Treat the supplied dataset and scorer as fixed. Do not inspect, edit, copy out, or bypass hidden
  labels. Use only their documented loading and scoring interfaces.
- Fit only on training data. The scorer alone evaluates holdout data.
- Copy the scorer's metric value from its `HILOOP_METRIC` line exactly. Never estimate, round,
  recompute, or improve a value in prose.
- A scorer result marked `valid=false` never wins. Record it as failed or inconclusive.
- Record negative results. A broken or regressed idea is evidence, not something to omit.
- Bound each experiment by time and total budget. Stop creating arms before the wrap-up budget.
- Never place a hiloop API key or model-provider credential in a script, sandbox command, file,
  annotation, log, or artifact.
- Spawn every local experiment under a clean, allowlisted environment. The trusted orchestrator
  needs hiloop authority to annotate; candidate scripts do not and must never inherit it.

## 1. Orient and reuse a project

Verify identity first:

```sh
hiloop whoami
```

Use the project already named by `HILOOP_PROJECT` or the user's requested slug. If neither exists,
use `autoresearch`:

```sh
export HILOOP_PROJECT="${HILOOP_PROJECT:-autoresearch}"
hiloop projects get "$HILOOP_PROJECT" >/dev/null 2>&1 || \
  hiloop projects create "$HILOOP_PROJECT" --description "Autonomous research runs"
```

When this skill runs inside `hiloop run`, require a non-empty `HILOOP_RUN_ID`. All idea and
experiment annotations attach to that run.

## 2. Check schemas before registering

Schema names are tenant-wide. Registration is not an idempotent upsert: registering an existing
name creates a new version. Never re-register either schema just to make a check pass.

Set `AUTORESEARCH_SKILL_DIR` to the directory containing this `SKILL.md`. First run:

```sh
hiloop annotation-schema get hiloop.idea --output json
hiloop annotation-schema get demo.experiment.v1 --output json
```

For an existing `hiloop.idea`, require exactly these promoted fields:

- `headline:str:identity`
- `status:str`
- `score:f64`
- `outcome:str`

`headline:str:identity` is load-bearing: it keeps one latest card per headline. A different
promotion list changes the view slot map and can make historical values appear under the wrong
columns. If the schema exists with a different list, stop and report the incompatibility. Do not
register another version, remove fields, or choose a different identity.

For an existing `demo.experiment.v1`, require exactly `score:f64`, `outcome:str`, `lane:str`, and
`experiment_id:str:identity`. Verify mechanically from each command's `.schema.promoted_fields`
JSON; do not judge by the prose description.

Only when `get` returns `not_found`, register the missing schema once:

```sh
hiloop annotation-schema register hiloop.idea \
  --json-schema "@$AUTORESEARCH_SKILL_DIR/references/hiloop.idea.schema.json" \
  --description "Research idea card, superseded in place as its status evolves" \
  --promote headline:str:identity \
  --promote status:str \
  --promote score:f64 \
  --promote outcome:str
```

```sh
hiloop annotation-schema register demo.experiment.v1 \
  --json-schema "@$AUTORESEARCH_SKILL_DIR/references/demo.experiment.v1.schema.json" \
  --description "One scored research experiment" \
  --promote score:f64 \
  --promote outcome:str \
  --promote lane:str \
  --promote experiment_id:str:identity
```

Any auth, transport, or validation error is not `not_found`; stop instead of registering through
uncertainty.

## 3. Establish the scorer contract

Read the task description, not the protected dataset/scorer implementation. Identify:

- the optimization direction and exact metric name;
- the documented loader and scorer calls;
- the scorer's `HILOOP_METRIC` output shape;
- the allowed dependencies and per-arm timeout;
- the prediction artifact format needed for an ensemble.

Run one honest baseline first. Save each arm's predictions under a unique filename so the final
ensemble can blend winners without rerunning or reading hidden labels.

## 4. Propose every idea before testing

Create seven distinct idea cards within the first two minutes:

1. A simple baseline.
2. Five genuinely different model or feature families, not five parameter values of one family.
3. An ensemble of the best decorrelated winners.

An idea's `headline` is its identity. Keep it byte-for-byte identical in every update. Always send
the complete card, never a partial patch. Start every card as `proposed`:

```sh
hiloop annotations add --run "$HILOOP_RUN_ID" --schema hiloop.idea --data '{
  "id": "poly-ridge",
  "headline": "Degree-2 polynomial interactions plus ridge",
  "hypothesis": "Interactions expose nonlinear signal while regularization controls width.",
  "idea_family": "feature-eng",
  "status": "proposed",
  "annotator": "llm"
}'
```

Before execution, rewrite the full card with `status: "testing"`. After execution, rewrite it with
`status` and `outcome` set to `worked` only when a valid result beats the baseline; otherwise use
`failed`. Include the exact score and metric object for scored terminal cards.

## 5. Execute the proven local loop

Run every candidate, retry, refinement, and ensemble script with the task's pinned environment and
only the non-secret process settings it needs:

```sh
env -i \
  HOME="$HOME" \
  PATH="$PATH" \
  TMPDIR="${TMPDIR:-/tmp}" \
  uv run python experiment.py
```

Do not replace this with a plain `uv run`, `python`, or inherited shell environment. In particular,
the child must not receive `HILOOP_API_KEY`, `HILOOP_RUN_ID`, model-provider keys, cloud credentials,
or the agent's other environment variables. If a task truly needs configuration, add each reviewed,
non-secret variable to this allowlist by name.

For each idea, in order:

1. Mark the complete idea card `testing`.
2. Write the smallest candidate that uses the documented loader and scorer.
3. Execute it with the clean environment above and the arm timeout. Allow at most one bug-fix or
   refinement retry.
4. Copy the numeric token from the emitted `HILOOP_METRIC` line without changing it.
5. Immediately add one immutable experiment row with a unique `experiment_id`.
6. Save predictions for valid candidates.
7. Terminalize the complete idea card as `worked` or `failed`.

One experiment row per scored execution:

```sh
hiloop annotations add --run "$HILOOP_RUN_ID" --schema demo.experiment.v1 --data '{
  "experiment_id": "poly-ridge-1",
  "headline": "polynomial degree 2 plus ridge alpha 10",
  "lane": "poly-ridge",
  "metric_name": "rmse",
  "direction": "lower_better",
  "outcome": "worked",
  "score": 52.53
}'
```

Use `worked` when valid and better than baseline, `regressed` when valid but not better, and
`inconclusive` for `valid=false`. If a process fails before the scorer emits a metric, do not invent
a score to satisfy the experiment schema; terminalize the idea as failed and preserve the error in
its rationale.

A complete scored terminal card looks like:

```sh
hiloop annotations add --run "$HILOOP_RUN_ID" --schema hiloop.idea --data '{
  "id": "poly-ridge",
  "headline": "Degree-2 polynomial interactions plus ridge",
  "hypothesis": "Interactions expose nonlinear signal while regularization controls width.",
  "change": "StandardScaler to PolynomialFeatures(2) to Ridge(alpha=10).",
  "rationale": "The interaction basis improved the fixed holdout score.",
  "idea_family": "feature-eng",
  "status": "worked",
  "outcome": "worked",
  "annotator": "llm",
  "score": 52.53,
  "metric": {
    "name": "rmse",
    "value": 52.53,
    "direction": "lower_better",
    "valid": true
  }
}'
```

## 6. Ensemble and wrap up

Choose two or three strong, decorrelated valid prediction files. Average predictions, score the
blend through the same fixed scorer, and annotate the ensemble exactly like any other idea. A
regressed blend stays regressed; never call it a winner because it combines more models.

Before exiting:

- every tested idea is terminal; untested ideas honestly remain `proposed`;
- every scored execution has one experiment annotation;
- failed and invalid attempts remain visible;
- the summary names baseline, best score, winning idea, experiment count, and one learned lesson;
- every number in the summary matches an annotation.

## 7. Show the evidence

```sh
hiloop annotations list --run "$HILOOP_RUN_ID" --subtree
hiloop runs tree "$HILOOP_RUN_ID" --columns 'hiloop.idea:score,outcome'
hiloop query --project "$HILOOP_PROJECT" --sql \
  "SELECT headline, score, outcome FROM ann_hiloop_idea ORDER BY score"
```

The public dashboard in this repository declares its `rich` dependency inline, so a clone needs
only `uv` and the `hiloop` CLI:

```sh
uv run tools/fleet-dashboard/dashboard.py \
  --project "$HILOOP_PROJECT" \
  --schema demo.experiment.v1 \
  --direction lower
```

## Preview: sandboxed experiment arms

**Gate:** do not select this path for a live run until the operator explicitly confirms a full
staging rehearsal is green. The proven local path above remains the default. To flip after that
confirmation, set `HILOOP_AUTORESEARCH_FLEET` to a comma-separated prepared fleet and
`HILOOP_AUTORESEARCH_ROOT=/tmp/autoresearch`.

The local orchestrator still owns model calls and annotations. Model credentials and the hiloop API
key stay on the host. Sandboxes receive only the fixed task inputs, scorer, dependencies, candidate
script, and prediction bytes.

Mechanically stage the fixed files into every prepared member without inspecting their contents.
Use base64 over `sandbox exec` for these KB-scale files; there is no file-copy verb:

```sh
task_b64="$(base64 < TASK.md | tr -d '\n\r')"
data_b64="$(base64 < data.py | tr -d '\n\r')"
score_b64="$(base64 < score.py | tr -d '\n\r')"
hiloop sandbox exec "$sandbox" --timeout-secs 180 -- /bin/sh -c \
  "mkdir -p '$HILOOP_AUTORESEARCH_ROOT'; \
   printf '%s' '$task_b64' | base64 -d > '$HILOOP_AUTORESEARCH_ROOT/TASK.md'; \
   printf '%s' '$data_b64' | base64 -d > '$HILOOP_AUTORESEARCH_ROOT/data.py'; \
   printf '%s' '$score_b64' | base64 -d > '$HILOOP_AUTORESEARCH_ROOT/score.py'"
```

Run arms strict round-robin. Encode only the candidate script, execute with a stable idempotency
key, and read the scorer line from stdout:

```sh
script_b64="$(base64 < experiment.py | tr -d '\n\r')"
output="$(hiloop sandbox exec "$sandbox" --timeout-secs 90 \
  --idempotency-key "autoresearch-$HILOOP_RUN_ID-$experiment_id" -- /bin/sh -c \
  "printf '%s' '$script_b64' | base64 -d > '$HILOOP_AUTORESEARCH_ROOT/experiment.py'; \
   cd '$HILOOP_AUTORESEARCH_ROOT'; \
   '$HILOOP_AUTORESEARCH_ROOT/.venv/bin/python' experiment.py")"
printf '%s\n' "$output"
```

Each arm must emit one `HILOOP_METRIC` line and a base64-encoded NumPy prediction artifact. Decode
predictions on the host for winner selection. Send the selected prediction files to the next
sandbox by the same base64-over-exec mechanism; average and score the ensemble inside that sandbox.
Write all annotations from the authenticated local orchestrator against `HILOOP_RUN_ID`.

On any sandbox transport failure, retry once with the same idempotency key. Then record the honest
failure and continue. Never fall back to local execution while labeling the result sandboxed.
