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
  version: 0.4.0
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
hiloop projects create default   # if none exists; --name adds optional display metadata
```

Project selection is explicit everywhere: `--project <slug-or-id>` > the `HILOOP_PROJECT`
environment variable > the active context's default project (`hiloop config set-context <name>
--project <slug>`). With no match, the command errors rather than guessing.

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

Omit `--image` to get the **managed default base** — it carries the in-sandbox control agent that
`exec` / `start` / `stream` need, and it is generic on purpose: start from it and install
dependencies once the sandbox is ready — `pip install …`, `npm i -g …`, `apt-get install …` — via
`running-commands-in-a-sandbox`.

`--image` takes any public OCI reference (a tag like `python:3.12-slim` or `node:22-bookworm`), but
an arbitrary image boots **without** the control agent, so `exec`/`start`/`stream` won't reach it —
bring your own image only when you have an agent-carrying base and the install step is heavy enough
to be worth baking in.

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

## 5. Stop or delete

Both are asynchronous and idempotent by sandbox id. `stop` terminates the workload but keeps the
record inspectable; `delete` tears the sandbox down entirely:

```sh
hiloop sandbox stop <sandbox-id> --wait      # come to rest, stay inspectable
hiloop sandbox delete <sandbox-id> --wait    # tear down
```

Always clean up sandboxes you created for a task unless told to keep them.

## Tips

- `hiloop sandbox list` / `get` accept `--output json`; capture the `id` fields for the next call.
- Lifecycle commands (`create`, `stop`, `delete`, `fork`, `snapshot`, `restore`) are async — pass
  `--wait` to block, or poll `get`/`list` yourself.
- `hiloop usage` prints a point-in-time fleet snapshot — active sandbox counts by state and reserved
  resources against capacity — for the tenant, or one project with `--project`.
- For any route without a dedicated flag, `hiloop api <path> [-X post|delete] [-d '<json>']` reaches
  the whole REST surface.
