---
name: creating-sandboxes
description: >-
  Create, inspect, and delete hiloop sandboxes — isolated, snapshottable environments an agent runs
  in. Covers the create→poll-until-ready→delete lifecycle with the dedicated `hiloop sandbox`
  commands, projects, bring-your-own images (any OCI reference or a build artifact), resource requests
  (cpus/memory/disk/architecture), capability requirements, capture, and the desired-vs-observed state
  model. Use when asked to spin up / provision / launch a hiloop sandbox or environment, choose its
  image, or tear one down.
metadata:
  version: 0.3.0
---

# Creating sandboxes

A **sandbox** is an isolated, snapshottable environment your agent runs in. It starts from an image
and a resource request, inside a **project**. The lifecycle is: create → poll until ready → use →
delete. Drive it with the dedicated `hiloop sandbox` commands; for fields not exposed as a flag, drop
to `hiloop api`, the authenticated passthrough for any REST route.

> Authenticate first (see the `authenticating` skill) and make sure you are **tenant-scoped** —
> sandbox work is tenant-scoped.

## 1. Pick or create a project

```sh
hiloop projects list
hiloop projects create --slug default --name "Default"   # if none exists
```

`hiloop sandbox create` defaults to your tenant's first project when you omit `--project`.

## 2. Create the sandbox

```sh
hiloop sandbox create \
  --project <project-id> \
  --image ghcr.io/acme/agent-base:latest \
  --name experiment-a \
  --cpus 2 --memory-mb 4096 --disk-mb 20480 \
  --wait
```

Create is **asynchronous**: by default it prints the new sandbox id and an operation id and returns.
Pass `--wait` to block until the sandbox is running. Omit any resource flag to take the server
default; `--arch` is `x86_64` (or `aarch64`). `--output json` prints the raw body — capture the id.

### Resources

`--cpus`, `--memory-mb`, `--disk-mb`, and `--arch` size the sandbox. Ask for what the workload needs;
the platform places it on a runtime that can satisfy the request.

### Capture

`--capture on` (the default) records the sandbox's LLM/tool/HTTP activity as queryable telemetry; pass
`--capture off` to run without instrumentation. (Querying that telemetry is the
`querying-observability-trees` skill.)

### Bring your own image

The base image is **generic** on purpose — pick the image your workload needs and install the rest at
runtime. `--image` takes any public OCI reference (a tag like `python:3.12-slim` or
`node:22-bookworm`). If you don't need a custom image, start from a small generic base and install
dependencies once the sandbox is ready — `pip install …`, `npm i -g …`, `apt-get install …` — via
`running-commands-in-a-sandbox`. Bring your own image only when the install step is heavy enough to be
worth baking in.

To **pin a digest** or use a **build artifact** (sources `--image` can't express), create over the
passthrough instead:

```sh
hiloop api /v1/sandboxes -X post -d '{
    "projectId": "<project-id>",
    "name": "experiment-a",
    "image": { "oci": { "reference": "node:22-bookworm", "digest": "sha256:…" } },
    "resources": { "cpus": 2, "memoryMb": "4096", "diskMb": "20480" }
  }'
# …or a build artifact produced earlier in your pipeline:
#   "image": { "buildArtifact": { "artifactRef": "<artifact-ref>" } }
```

## 3. Poll until ready

hiloop reconciles sandboxes asynchronously: the **desired** state you asked for is tracked separately
from the **observed** state it has reached. Do not use a sandbox until it is ready. `--wait` blocks for
you; without it, poll:

```sh
hiloop sandbox get <sandbox-id>            # inspect observed state
hiloop sandbox list --state running        # or list by observed state
```

Poll until the sandbox reports ready (with a sane timeout — don't poll forever), then run commands in
it (see `running-commands-in-a-sandbox`).

## 4. Capabilities

If the workload needs a specific runtime feature (fast memory snapshots, GPUs), request it through the
sandbox's capability requirements; hiloop places it on a runtime that satisfies them. Capability
requirements aren't a `create` flag, so discover and pin them over the passthrough:

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

Deleting is asynchronous and idempotent by sandbox id:

```sh
hiloop sandbox delete <sandbox-id> --wait
```

Always clean up sandboxes you created for a task unless told to keep them.

## Tips

- `hiloop sandbox list` / `get` accept `--output json`; capture the `id` fields for the next call.
- Lifecycle commands (`create`, `delete`, `fork`, `snapshot`, `restore`) are async — pass `--wait`
  to block, or poll `get`/`list` yourself.
- For any route without a dedicated flag, `hiloop api <path> [-X post|delete] [-d '<json>']` reaches
  the whole REST surface.
