---
name: creating-sandboxes
description: >-
  Create, inspect, and delete hiloop sandboxes — isolated, snapshottable environments an agent runs
  in. Covers the create→poll-until-ready→delete lifecycle over the `hiloop api` passthrough, projects,
  images, resources, idempotency keys, and the desired-vs-observed state model. Use when asked to spin
  up / provision / launch a hiloop sandbox or environment, or to tear one down.
metadata:
  version: 0.1.0
---

# Creating sandboxes

A **sandbox** is an isolated, snapshottable environment your agent runs in. It starts from an image
and a resource request, inside a **project**. The lifecycle is: create → poll until ready → use →
delete. The sandbox lifecycle is exposed over the API; from the CLI use `hiloop api`, the
authenticated passthrough for any REST route.

> Authenticate first (see the `authenticating` skill) and make sure you are **tenant-scoped** —
> sandbox work is tenant-scoped.

## 1. Pick or create a project

```sh
hiloop projects list
hiloop projects create --slug default --name "Default"   # if none exists
```

## 2. Create the sandbox

Creation is a mutation, so it takes an `idempotency-key` — reuse the same key to retry safely.

```sh
hiloop api /v1/sandboxes -X post \
  -H "idempotency-key: $(uuidgen)" \
  -d '{
    "projectId": "<project-id>",
    "name": "experiment-a",
    "image": { "oci": { "reference": "ghcr.io/acme/agent-base:latest" } },
    "resources": { "cpus": 2, "memoryMb": "4096", "diskMb": "20480" }
  }'
```

The response contains the **sandbox** (note its `id`) and an **operation**. Resources accept
`cpus`, `memoryMb`, `diskMb`, and optionally `architecture` (e.g. `ARCHITECTURE_X86_64`).

## 3. Poll until ready

hiloop reconciles sandboxes asynchronously: the **desired** state you asked for is tracked separately
from the **observed** state it has reached. Do not use a sandbox until it is ready.

```sh
hiloop api "/v1/sandboxes/${SANDBOX_ID}"            # inspect observed state
hiloop api "/v1/operations/${OPERATION_ID}"         # or poll the operation
```

Poll until the sandbox reports ready (or the operation completes), with a sane timeout — don't poll
forever. Only then run commands in it (see `running-commands-in-a-sandbox`).

## 4. Capabilities

If the workload needs a specific runtime feature (fast memory snapshots, GPUs), request it through
the sandbox's capability requirements; hiloop places it on a runtime that satisfies them. Discover
what's available:

```sh
hiloop api /v1/runtime/capabilities
```

## 5. Delete

Deleting is also an idempotent mutation:

```sh
hiloop api "/v1/sandboxes/${SANDBOX_ID}" -X delete -H "idempotency-key: $(uuidgen)"
```

Always clean up sandboxes you created for a task unless told to keep them.

## Tips

- `-X post`/`-X put`/`-X delete` selects the method; the default is GET.
- Pass `--output json` for raw response bodies you intend to parse; capture the `id` fields.
- Every mutation needs a fresh `idempotency-key` per logical operation (`$(uuidgen)`); reuse the
  *same* key only when retrying the *same* operation.
