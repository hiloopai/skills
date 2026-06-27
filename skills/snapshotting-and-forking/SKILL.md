---
name: snapshotting-and-forking
description: >-
  Snapshot a hiloop sandbox and fork it to explore multiple paths from a shared state. Covers
  creating/listing/restoring snapshots and forking a sandbox into divergent branches identified by
  fork_path, the core primitive behind tree-native experimentation. Use when asked to snapshot, save,
  checkpoint, branch, or fork a sandbox, or to explore alternative agent paths from a common starting
  point.
metadata:
  version: 0.1.0
---

# Snapshotting and forking

hiloop's distinctive primitive: **snapshot** a sandbox's state, then **fork** from it so multiple
agent attempts diverge from an identical starting point. Each branch gets a position in the
**fork tree**, identified by a `fork_path` (e.g. `/0/0`, `/0/1`) — the same paths you later query and
diff (see `querying-observability-trees`). This is what lets an agent try several solutions from one
state and compare them.

> Tenant-scoped, ready sandbox required (see `creating-sandboxes`).

## Snapshot a sandbox

Snapshotting is a mutation with an `idempotency-key`:

```sh
hiloop api "/v1/sandboxes/${SANDBOX_ID}/snapshots" -X post \
  -H "idempotency-key: $(uuidgen)" \
  -d '{ "contents": "SNAPSHOT_CONTENTS_FULL", "allowFallback": true }'
```

It returns an **operation** — poll it until the snapshot completes. Then manage snapshots:

```sh
hiloop api "/v1/snapshots?projectId=<project-id>"     # list
hiloop api "/v1/snapshots/${SNAPSHOT_ID}"             # inspect
hiloop api "/v1/snapshots/${SNAPSHOT_ID}:restore" -X post \
  -H "idempotency-key: $(uuidgen)" \
  -d '{ "projectId": "<project-id>" }'                # restore into a new sandbox
```

## Fork a sandbox

Fork creates a child branch from a source sandbox. The child takes a position in the fork tree under
its parent node, which becomes its `fork_path`:

```sh
hiloop api "/v1/sandboxes/${SOURCE_SANDBOX_ID}:fork" -X post \
  -H "idempotency-key: $(uuidgen)" \
  -d '{ "projectId": "<project-id>" }'
```

Returns the new (child) sandbox plus an **operation** — poll until ready, then run divergent work in
each branch.

> Runtime fork creation is capability-gated and provider-specific. Snapshot endpoints and
> branch-diff queries are public. So make branch *comparisons* depend on the run id and `fork_path`
> (see `querying-observability-trees`), not on a particular fork mechanism.

## The pattern: explore N paths from one state

1. Get a sandbox to the state you want to branch from.
2. Snapshot it (your shared baseline).
3. Fork it into N children — `/0/0`, `/0/1`, … — one per approach.
4. Run a different attempt in each branch.
5. **Query per `fork_path`** to compare them, or **branch-diff** two branches to see exactly what one
   did that another didn't (see `querying-observability-trees`).

This snapshot→fork→compare loop is the foundation of tree-native experimentation in hiloop.
