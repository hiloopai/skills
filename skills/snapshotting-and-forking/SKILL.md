---
name: snapshotting-and-forking
description: >-
  Snapshot a hiloop sandbox and branch from it to explore multiple paths from one shared state.
  Covers `hiloop sandbox snapshot create` / `list` / `delete`, and `hiloop sandbox create --from
  <snapshot>` — the single verb that is restore, fork, and branch — plus safe retries with
  idempotency keys and the recorded fork lineage that makes branches comparable. Use when asked to
  snapshot, save, checkpoint, branch, or fork a sandbox, or to explore alternative agent paths from
  a common starting point.
metadata:
  version: 0.7.0
---

# Snapshotting and branching

> **Status: the sandbox runtime is mid-rebuild — these commands do not work against a deployment
> yet.** `hiloop sandbox snapshot` ships with the CLI's next release (an already-installed CLI does
> not have it), and no deployment serves the `/v1/sandboxes` or `/v1/snapshots` routes yet, so a call
> returns a bare `404`. The surface below is the settled contract they return on. See
> `creating-sandboxes` for the full status.

hiloop's distinctive primitive: **snapshot** a sandbox's state, then create N sandboxes **from**
that snapshot so several attempts diverge from an identical starting point.

**Persistence is one concept.** A snapshot is the saved state of a sandbox, and
`hiloop sandbox create --from <snapshot>` is **restore, fork, and branch in one verb**. There are no
`fork`, `restore`, or `resume` verbs and no workspace-revision references — that is a settled design
decision, not a temporary gap. If you reach for `hiloop sandbox fork`, it does not exist and will
not come back.

In v1 a snapshot captures **disk, not memory**. Processes never survive; checkpoint durable work as
files. (Memory restore is a committed later phase.)

## Snapshot a sandbox

```sh
hiloop sandbox snapshot create <sandbox> --name baseline-after-setup
```

- `--name <name>` gives the snapshot a human-readable handle. Omitted, it is unnamed and you work
  from its id.
- `--wait-remote` waits up to 25 seconds for **replicated** durability. Without it the call returns
  as soon as the snapshot is locally durable. The response reports `durability` as `local` or
  `replicated` — read it rather than assuming; a snapshot that is only local is truthfully labeled
  so, never overstated.
- `--idempotency-key <key>` makes a retry safe: the same key returns the original snapshot instead
  of creating a second one.

A snapshot outlives its source sandbox — stop or delete the sandbox and the snapshot stays usable.

## List and delete snapshots

```sh
hiloop sandbox snapshot list                        # every snapshot, with lineage edges
hiloop sandbox snapshot list --sandbox <sandbox>    # only those from one source
hiloop sandbox snapshot list --name baseline        # exact name
hiloop sandbox snapshot delete <snapshot>           # permanent
```

`list` includes the **lineage edges** — which snapshot came from which sandbox — which is what makes
a fan-out tree readable after the fact. There is no `snapshot get`; use `list` with a filter.

## Branch: create from a snapshot

```sh
hiloop sandbox create arm-lr-004 --from baseline-after-setup
hiloop sandbox create arm-lr-008 --from baseline-after-setup
hiloop sandbox create arm-lr-016 --from baseline-after-setup
```

Each is an independent sandbox starting from identical bytes. **N concurrent `create --from` against
one snapshot is the fan-out primitive** — that is the intended way to explore several approaches at
once. Fork-tree lineage is recorded from snapshot parentage, so the relationship between branches
survives in the record.

`--from` is mutually exclusive with `--image`; everything else on `create` (`--ttl`,
`--storage-class`, `--port`, `--volume`, `--secret`, `--capture`, `--metadata`) applies normally —
see `creating-sandboxes`.

## Safe retries: idempotency keys

Both `sandbox create` and `sandbox snapshot create` take `--idempotency-key <key>`. Re-running with
the same key returns the original resource instead of making a second one, so an ambiguous failure
(a 5xx, a lost response) can be retried without risking a duplicate. Reusing a key with a
*different* request is a conflict. This is the **only** thing that makes create replay-idempotent —
the deterministic naming underneath is not sufficient on its own, so pass a key whenever you might
retry.

## The pattern: explore N paths from one state

1. Get a sandbox to the state you want to branch from (install dependencies, clone the repo, reach
   the checkpoint).
2. `hiloop sandbox snapshot create <sandbox> --name <baseline>` — your shared baseline, and a
   reusable "prebuilt environment" that skips the slow setup next time.
3. `hiloop sandbox create <arm-n> --from <baseline>`, once per approach.
4. Run a different attempt in each (see `running-commands-in-a-sandbox`).
5. Compare them through telemetry. Wrap each attempt's agent with `hiloop run` so the branches show
   up in the run-lineage tree, then use `hiloop runs list --root-run-id`, per-`lineage_path`
   queries, and annotations to pick the winner — see `querying-observability-trees` and
   `annotating-runs`.

Note that **run lineage and snapshot lineage are two different trees**. Snapshot parentage records
which sandbox came from which; `lineage_path` records which *run* descends from which. Branch
comparisons should key on the run id and `lineage_path`, which work regardless of how the sandbox
was created.
