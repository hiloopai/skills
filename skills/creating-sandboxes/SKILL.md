---
name: creating-sandboxes
description: >-
  Create, inspect, and delete hiloop sandboxes — isolated, snapshottable environments an agent runs
  in. Covers the create→poll-until-ready→delete lifecycle over the `hiloop api` passthrough, projects,
  bring-your-own images (any OCI reference or a build artifact), resource requests (cpus/memory/disk/
  architecture), capability requirements, idempotency keys, and the desired-vs-observed state model.
  Use when asked to spin up / provision / launch a hiloop sandbox or environment, choose its image, or
  tear one down.
metadata:
  version: 0.2.0
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

Creation is a create-style mutation, so it **optionally** takes an `idempotency-key`. Supply one (and
reuse it) to make a retry safe; omit it and the server generates one for you.

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

The response contains the **sandbox** (note its `id`) and an **operation**.

### Resources

The `resources` request accepts `cpus`, `memoryMb`, `diskMb`, and optionally `architecture`
(`ARCHITECTURE_X86_64` or `ARCHITECTURE_AARCH64`). Ask for what the workload needs; the platform
places the sandbox on a runtime that can satisfy the request.

### Bring your own image

The base image is **generic** on purpose — pick the image your workload needs and install the rest at
runtime. Two image sources, set under `image`:

```sh
# Any public OCI reference — a tag, or pin a digest for reproducibility.
"image": { "oci": { "reference": "python:3.12-slim" } }
"image": { "oci": { "reference": "node:22-bookworm", "digest": "sha256:…" } }

# A build artifact produced earlier in your pipeline.
"image": { "buildArtifact": { "artifactRef": "<artifact-ref>" } }
```

Set exactly one source. If you don't need a custom image, start from a small generic base
(`python:3.12-slim`, `node:22-bookworm`, `debian:stable-slim`) and install dependencies once the
sandbox is ready — `pip install …`, `npm i -g …`, `apt-get install …` — via
`running-commands-in-a-sandbox`. Bring your own image only when the install step is heavy enough to be
worth baking in.

Capture (queryable telemetry of the sandbox's LLM/tool/HTTP activity) is **on by default**. To run
without instrumentation, set `"capture": { "enabled": false }`.

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

If the workload needs a specific runtime feature (fast memory snapshots, GPUs), request it through the
sandbox's capability requirements; hiloop places it on a runtime that satisfies them. First discover
what's available, then pin the requirement on create:

```sh
hiloop api /v1/runtime/capabilities
```

Each requirement is a `key` plus optional floors — `minimumSupport` and `minimumMaturity` — so you can
demand not just that a capability exists but that it's supported and mature enough:

```sh
hiloop api /v1/sandboxes -X post -d '{
    "projectId": "<project-id>",
    "name": "gpu-job",
    "image": { "oci": { "reference": "nvidia/cuda:12.4.0-runtime-ubuntu22.04" } },
    "resources": { "cpus": 8, "memoryMb": "32768", "diskMb": "51200" },
    "requestedCapabilities": [
      { "key": "gpu", "minimumSupport": "supported", "minimumMaturity": "ga" }
    ]
  }'
```

Use the exact `key`/`support`/`maturity` strings the capabilities endpoint reports — don't guess. If
no runtime satisfies the requirement, creation fails fast rather than placing the sandbox somewhere it
can't run.

## 5. Delete

Deleting is idempotent by sandbox id, so it needs no idempotency key:

```sh
hiloop api "/v1/sandboxes/${SANDBOX_ID}" -X delete
```

Always clean up sandboxes you created for a task unless told to keep them.

## Tips

- `-X post`/`-X put`/`-X delete` selects the method; the default is GET.
- Pass `--output json` for raw response bodies you intend to parse; capture the `id` fields.
- Create-style mutations (create, execute, snapshot, restore, fork) **optionally** take an
  `idempotency-key`; supply your own (and reuse it) to make a retry safe, or omit it and the server
  generates one. Delete and lifecycle operations need no key — they are idempotent by sandbox id.
