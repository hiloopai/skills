---
name: managing-volumes
description: >-
  Publish and mount large data — datasets, model caches, checkpoints — as hiloop volumes: named,
  versioned references that sandboxes mount instead of copying bytes in. Covers `hiloop volume
  create` / `push` (content-addressed, deduplicated, never half-published) / `list` / `get` /
  `delete`, and attaching one at sandbox create with `--volume <name>:/abs/path`, version pinned at
  admission. Use when many sandboxes share the same input data, when data is too large to move
  through a command's output, or when asked to publish, version, or mount a dataset.
metadata:
  version: 0.2.0
---

# Managing volumes

A **volume** is a named, versioned reference to large data — a dataset, a model cache, a checkpoint
tree — that sandboxes **mount instead of copying**. You push a local tree once to publish an
immutable version; content is stored once, deduplicated by digest, and shared across every attach.

> **Status.** The volume **routes are served** — publishing and versioning data works today. Two
> caveats: the `hiloop volume` verbs ship with the CLI's next release (an already-installed CLI
> reports `unrecognized subcommand 'volume'`; until you upgrade, reach the same routes through
> `hiloop api /v1/volumes …`), and **mounting** a volume into a sandbox waits on the sandbox runtime
> rebuild (see `creating-sandboxes`). You can publish and version data now; you cannot consume it
> from a sandbox yet.

The surface is exactly five verbs plus one create-time flag. **There is no `hiloop volume
prefetch`** — the node-cache pre-warm verb was removed; do not reach for it. There is also no
`hiloop sandbox cp`, so volumes are the supported way to get bulk data in.

> Authenticate first (the `authenticating` skill) and pick a project — a volume lives in a project
> and its name is unique within it.

## Create a volume

```sh
hiloop volume create imagenet-160 --size-gb 100 --description "ImageNet 160px"
```

`--size-gb` is a **quota** — a cap on the volume's total committed size, not an allocation. An empty
volume consumes no storage. The default per-volume ceiling is 2048 GiB (2 TiB). The volume starts
empty, with no versions, until the first push.

Project selection is `--project <slug-or-id>` > `HILOOP_PROJECT` > the active context's project.

## Push a version

Publish a local directory as the volume's next **immutable version**:

```sh
hiloop volume push imagenet-160 ./imagenet-160
```

The tree is chunked and digested locally, and only content the store does not already hold is
uploaded, over presigned upload URLs the API brokers per batch of blobs. Concretely:

- **Retrying is free and safe.** Re-pushing unchanged data uploads nothing; an interrupted push is
  always safe to re-run.
- **A version is never half-published.** It becomes visible only once every byte is stored, in a
  final publish step that returns the version digest.
- **Content is verified on the way out.** Blobs are digest-checked as they are read, and a file that
  changes size or mtime mid-push fails the push rather than publishing a torn version.
- **Expiring upload URLs are re-brokered automatically** and the affected uploads retried, so a slow
  push does not die partway.

Each push creates a new version; existing attachments are unaffected.

## Mount into a sandbox

Attach at **create time** with the `--volume` flag, repeatable, as `<volume>:<absolute-path>`:

```sh
hiloop sandbox create trainer-1 --image ubuntu:24.04 \
  --volume imagenet-160:/data/imagenet \
  --volume checkpoints:/data/ckpt
```

- **The volume name is resolved client-side before the create is sent**, so an unknown name fails
  immediately with a clear error rather than producing a sandbox missing its data.
- **The version is pinned at admission.** The attach resolves the volume's *current* version when
  the sandbox is created; a later push never changes a running sandbox's view. Sandboxes created
  afterwards pick up the new version.
- **Volumes must be pre-registered.** `--volume` references an existing volume only — there is no
  create-on-attach.
- The mount carries a volume id and a target path and nothing else; there is no read-write toggle to
  set, and live multi-attach / shared writable volumes are explicitly not in v1 (the model is
  fork-don't-share).

## Inspect and clean up

```sh
hiloop volume list                          # the active project; --project to override
hiloop volume get imagenet-160              # quota, current version, timestamps
hiloop volume delete imagenet-160 --yes     # removes the volume together with its versions
```

`delete` asks for confirmation on a terminal; `--yes` skips it (required in scripts).

## The pattern

1. `volume create` once per dataset.
2. `volume push` to publish it — repeat whenever the data changes; each push is a new immutable
   version.
3. Create N sandboxes, each with `--volume <name>:/data` — one push, N mounts, no per-sandbox copy.
4. Running sandboxes keep their pinned version; new ones see the latest.
