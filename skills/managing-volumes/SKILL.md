---
name: managing-volumes
description: >-
  Publish and mount large data — datasets, model caches, checkpoints — as hiloop volumes: named,
  versioned references that sandboxes mount instead of copying bytes into each sandbox. Covers
  `hiloop volume create` / `push` (content-addressed, deduplicated, never half-published) / `list` /
  `get` / `delete` / `prefetch` (node-cache pre-warm), and attaching a volume read-only at sandbox
  create with the version pinned at admission. Use when a sandbox needs data too large for
  `sandbox cp`, when many sandboxes share the same input data, or when asked to publish, version,
  mount, or pre-warm a dataset.
metadata:
  version: 0.1.0
---

# Managing volumes

A **volume** is a named, versioned reference to large data — a dataset, a model cache, a
checkpoint tree — that sandboxes **mount instead of copying**. You push a local tree once to
publish an immutable version; content is stored once, deduplicated by digest, and shared across
every attach. Volumes are **read-only** for sandboxes in v1.

Use a volume when:

- the data is over `sandbox cp`'s per-transfer size limit (`cp` rejects such files with a clear
  error and points here), or
- many sandboxes need the **same** input data — one push, N mounts, no per-sandbox copy.

> Tenant-scoped. Authenticate first (the `authenticating` skill) and pick a project
> (`creating-sandboxes`) — a volume lives in a project, and its name is unique within it.

## Create a volume

```sh
hiloop volume create imagenet-160 --size-gb 100 --project <project-id>
```

`--size-gb` is a **quota** — a cap on the volume's total committed size, not an allocation (an
empty volume consumes no storage; the cap is 2048 GiB). The volume starts empty, with no versions,
until the first push.

## Push a version

Publish a local directory (or a single file) as the volume's next **immutable version**:

```sh
hiloop volume push imagenet-160 ./imagenet-160
```

The tree is chunked and digested locally, and only content the store does not already hold is
uploaded — retrying a push, or re-pushing unchanged data, uploads nothing. The version becomes
visible only once every byte is stored, so a version is **never half-published** and an
interrupted push is always safe to re-run. Each push creates a new version; existing attachments
are unaffected (see pinning, below).

## Mount into a sandbox

Attach at **create time**, over the `hiloop api` passthrough (mounts are not a `sandbox create`
flag). Each mount names the volume and an absolute target path:

```sh
hiloop api /v1/sandboxes -X post -d '{
    "projectId": "<project-id>",
    "name": "trainer-1",
    "resources": { "cpus": 4, "memoryMb": "8192" },
    "volumeMounts": [ { "volume": "imagenet-160", "targetPath": "/data/imagenet" } ]
  }'
```

- **Read-only in v1.** A read-write attach is not yet available.
- **The version is pinned at admission.** The attach resolves the volume's *current* version when
  the sandbox is created; a later push never changes a running sandbox's view. New sandboxes pick
  up the new version.
- **Failures are loud.** An unknown volume name, a target-path collision, or a read-write request
  fails the create with a clear error — a create never silently drops a mount it cannot honor.

## Pre-warm before a wave of creates

`prefetch` pulls a volume version into the node-side cache ahead of a planned burst of sandbox
creates, so their attaches find the content already local instead of each paying the cold fill:

```sh
hiloop volume prefetch imagenet-160                         # current version
hiloop volume prefetch imagenet-160 --version-digest blake3:<hex>   # a specific version
```

Purely an optimization — an attach works without it.

## Inspect and clean up

```sh
hiloop volume list --project <project-id>   # newest first; omit --project to span your projects
hiloop volume get imagenet-160              # quota, current version digest, timestamps
hiloop volume delete imagenet-160           # removes the volume together with its versions
```

A volume attached to a sandbox cannot be deleted — detach it (delete or stop the sandboxes using
it) first.

## The pattern

1. `volume create` once per dataset; `volume push` to publish it.
2. `volume prefetch` right before a wave of sandbox creates.
3. Create N sandboxes, each mounting the volume (`volumeMounts` at create) — no per-sandbox copy.
4. New data? `volume push` again: a new immutable version. Running sandboxes keep their pinned
   version; sandboxes created afterwards see the new one.

For getting *individual files* in or out of a live sandbox, use `hiloop sandbox cp`
(`running-commands-in-a-sandbox`); volumes are for the big, shared, versioned inputs.
