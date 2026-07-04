---
name: snapshotting-and-forking
description: >-
  Snapshot a hiloop sandbox and fork it to explore multiple paths from a shared state. Covers
  `hiloop sandbox snapshot` / `restore` / `fork`, listing snapshots, and forking into divergent
  branches identified by lineage_path — the core primitive behind tree-native experimentation. Use when
  asked to snapshot, save, checkpoint, branch, or fork a sandbox, or to explore alternative agent
  paths from a common starting point.
metadata:
  version: 0.3.0
---

# Snapshotting and forking

hiloop's distinctive primitive: **snapshot** a sandbox's state, then **fork** from it so multiple
agent attempts diverge from an identical starting point. Each fork starts a **child run** (a new run
id with `parent_run_id` set), and that child gets a position in the **run-lineage tree**, identified
by a `lineage_path` (a dotted sequence of run ULIDs, e.g. `01K6Z….01K70…`) — the same paths you later
query and diff (see `querying-observability-trees`). This is what lets an agent try several solutions
from one state and compare them.

> Tenant-scoped, ready sandbox required (see `creating-sandboxes`).

## Snapshot a sandbox

Snapshotting is asynchronous; `--wait` blocks until it completes and prints the snapshot id:

```sh
hiloop sandbox snapshot <sandbox-id> --wait
```

List and restore snapshots (listing is over the passthrough; restore has a dedicated command):

```sh
hiloop api "/v1/snapshots?projectId=<project-id>"            # list
hiloop api "/v1/snapshots/<snapshot-id>"                     # inspect
hiloop sandbox restore <snapshot-id> --project <project-id> --wait   # restore into a new sandbox
```

## Fork a sandbox

Fork creates a child branch from a source sandbox. The child inherits the source's filesystem (from
its snapshot) and starts a **child run** (`parent_run_id` set to the source's run), taking a fresh
position in the run-lineage tree under its parent, which becomes its `lineage_path`:

```sh
hiloop sandbox fork <source-sandbox-id> --project <project-id> --name arm-feature-eng \
  --label lr-0.04 --wait
```

Forking is asynchronous (`--wait` to block). `--label` names the **child run** — it is what
`hiloop runs list` / `tree` show in place of the run id, so label each branch for what it tries.
The child's resources/image default to the server defaults / sandbox base unless you set `--cpus` /
`--memory-mb` / `--disk-mb` / `--image`; `--continuity filesystem` (the default) carries the
filesystem across.

> Runtime fork creation is capability-gated and provider-specific. Snapshot/restore and branch-diff
> queries are broadly available. So make branch *comparisons* depend on the run id and `lineage_path`
> (see `querying-observability-trees`), not on a particular fork mechanism.

## The pattern: explore N paths from one state

1. Get a sandbox to the state you want to branch from.
2. Snapshot it (your shared baseline) — also a reusable "prebuilt image" you can restore later.
3. Fork it into N children — each a child run with its own `lineage_path` — one per approach.
4. Run a different attempt in each branch (see `running-commands-in-a-sandbox`).
5. **Render the tree** (`hiloop runs tree <root-run-id>`), **query per `lineage_path`** to compare
   branches, or **branch-diff** two child runs to see exactly what one did that another didn't (see
   `querying-observability-trees`).

This snapshot→fork→compare loop is the foundation of tree-native experimentation in hiloop.
