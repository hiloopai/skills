---
name: creating-sandboxes
description: >-
  Create, inspect, and delete hiloop sandboxes — isolated environments an agent runs in. Covers the
  create→poll-until-ready→delete lifecycle with the dedicated `hiloop sandbox` commands, projects,
  the required image-or-profile choice, resource requests (cpus/memory/disk/GPUs/architecture),
  managed networking and egress mode, telemetry capture, workspace revisions, lifetime limits
  (idle timeout / max runtime), secret-binding caveats, stop/resume semantics, and the
  desired-vs-observed state model. Use when asked to spin up / provision / launch a hiloop sandbox
  or environment, choose its image or profile, stop or resume one, or tear one down.
metadata:
  version: 0.7.0
---

# Creating sandboxes

A **sandbox** is an isolated environment your agent runs in. It boots from an explicit **profile or
image**, with a resource request, inside a **project**. The lifecycle is: create → poll until ready
→ use → delete. Drive it with the dedicated `hiloop sandbox` commands; for fields not exposed as a
flag, drop to `hiloop api`, the authenticated passthrough for any REST route.

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

**Exactly one of `--profile` or `--image` is required** — there is no default environment:

```sh
hiloop sandbox create \
  --project <project> \
  --profile gvisor-cpu \
  --name experiment-a \
  --cpus 2 --memory-mb 4096 --disk-mb 20480 \
  --wait
```

- `--profile <name>` selects a **named runtime profile** the deployment publishes (the hosted CPU
  profile is `gvisor-cpu`; your deployment may publish others — a GPU profile, a devbox plan). The
  platform resolves it to a preconfigured runtime image. This is the right default choice.
- `--image <ref>` boots an **OCI image** (e.g. `ubuntu:24.04`) instead. The selected sandbox cell
  must map it to an immutable environment plan — an image the deployment doesn't advertise is
  rejected, never silently substituted. Pin production environments by digest
  (`repository@sha256:…`); a tag is not an environment identity.

Create is **asynchronous**: by default it prints the new sandbox id and an operation id and
returns. Pass `--wait` to block until the sandbox is running. `--output json` prints the raw body —
capture the id.

To make a retry safe, pass `--idempotency-key <key>`: re-running with the same key returns the
original sandbox instead of creating a second one, and with a key set the CLI retries ambiguous
failures (a 5xx, a lost response) itself, up to 3 attempts. Reusing a key with a **different**
request fails with `idempotency_conflict` (409). Omitted, every invocation creates fresh.

### Resources

`--cpus`, `--memory-mb`, `--disk-mb` size the sandbox (omit any to take the server default);
`--arch` is `x86_64` (default) or `aarch64`. For accelerators, `--gpus <count>` requests GPU
devices or isolated slices, and `--gpu-model a100,h100` (requires `--gpus`) lists acceptable models
in preference order. A request no runtime can satisfy fails fast rather than placing the sandbox
somewhere it can't run.

### Network and egress

By default the sandbox keeps the runtime's non-managed network mode. `--network-mode sandbox`
requests the cell's managed network and applies `--egress-mode`: `allow` (default) permits outbound
traffic — package installs, git clones — and `deny` blocks it. Use the managed mode whenever the
workload needs the network deliberately configured.

### Capture

`--capture on` records the sandbox's activity as queryable telemetry **where the runtime lane
supports it natively** — the default is `off`, and requests for unavailable semantics fail closed
rather than pretending. For capturing an agent's model/tool/HTTP activity today, wrap the command
with `hiloop run` (see `querying-observability-trees`); platform lifecycle events
(`signal = 'runtime'`) flow for every sandbox regardless of this flag.

### Workspace (durable state)

The image root is read-only; the sandbox gets writable scratch at `/tmp` and a workspace at
`/workspace`. That scratch is **ephemeral** — to make the workspace durable (survive stop/resume,
seed other sandboxes), attach an exact versioned revision at create with `--workspace-revision` +
`--workspace-target`. That whole model — sealing on stop, restoring on resume, branching many
sandboxes from one revision — is the `persisting-and-branching-workspaces` skill.

### Lifetime: idle timeout and max runtime

- `--idle-timeout <secs>` — how long the sandbox may sit without activity before it's
  automatically stopped (server default 1800s/30min; 60–86400). Activity means real sandbox
  operations — executing a command, sending input — not an open idle connection.
- `--no-idle-reclaim` — disable the inactivity clock entirely (mutually exclusive with
  `--idle-timeout`); explicit stop/delete and any max runtime still apply.
- `--max-runtime <secs>` — an absolute lifetime cap regardless of activity (60–86400). Omitted,
  there is no cap: an actively-used sandbox may run indefinitely and only going idle reclaims it.

### Secrets: fail-closed for now

`--secret <name>` (repeatable) requests a stored sandbox-secret binding. **Current production cells
do not advertise native secret injection, so a create with a secret binding fails closed** — the
sandbox is never silently created without its credential. Until native injection ships, bind
secrets on `hiloop run` instead (see `managing-secrets`), and never work around it by passing a
plaintext credential into a sandbox env, image, or command line.

### Identity

`--as workload/<name>` launches the sandbox as a registered machine identity instead of you — see
`launching-as-workloads`.

### Capabilities

Runtime features (managed SSH, GPUs, streaming exec, …) are **capabilities** each deployment
advertises with an explicit support level — discover the current set with
`hiloop api /v1/runtime/capabilities`, and treat what it reports as the source of truth. A create
that asks for something the deployment doesn't support fails fast at admission
(`unsupported_capability`), an impossible shape is `requirements_unsatisfiable`, and temporarily
committed capacity is `capacity_exhausted` (retryable) — a sandbox is never accepted and then
silently provisioned differently. To pin explicit capability floors, pass
`requested_capabilities` (a `key` with `minimum_support` / `minimum_maturity`) over the `hiloop
api` passthrough, and request only what the workload actually needs.

## 3. Poll until ready

hiloop reconciles sandboxes asynchronously: the **desired** state you asked for is tracked
separately from the **observed** state it has reached. Do not use a sandbox until it is running.
`--wait` blocks for you; without it, poll:

```sh
hiloop sandbox get <sandbox>            # inspect observed state (id or name)
hiloop sandbox list --state running     # or list by observed state
```

Poll with a sane timeout — don't poll forever — then run commands in it
(see `running-commands-in-a-sandbox`).

## 4. Stop, resume, or delete

All are asynchronous and idempotent by sandbox id. `stop` brings the sandbox to rest in a stopped
state and keeps its record inspectable; `delete` tears it down entirely:

```sh
hiloop sandbox stop <sandbox> --wait      # come to rest, stay inspectable
hiloop sandbox resume <sandbox> --wait    # wake it back up
hiloop sandbox delete <sandbox> --wait    # tear down
```

**Whether the filesystem survives a stop is explicit, never lucky.** With a versioned workspace
attached at create, stop **seals** it and resume restores the exact bytes under a new runtime
generation — process and memory state never survive. Without one, the stop is destructive: the
stop result says so, and `resume` fails with `workspace_continuity_unavailable` unless you pass
`--fresh-workspace` to accept an empty workspace. Details and the branching pattern:
`persisting-and-branching-workspaces`.

If a sandbox ends up **failed**, `hiloop sandbox get` shows a stable machine-readable failure code
plus a human-readable message — diagnose from that instead of guessing.

Always clean up sandboxes you created for a task unless told to keep them.

## Tips

- `hiloop sandbox list` / `get` accept `--output json`; capture the `id` fields for the next call.
  Names are not unique — the id stays the canonical handle.
- Lifecycle commands (`create`, `stop`, `resume`, `delete`) are async — pass `--wait` to block, or
  poll `get`/`list` yourself.
- `hiloop sandbox run` creates a sandbox that runs **one command as its purpose** and stops when it
  exits — the fire-and-forget shape (see `running-commands-in-a-sandbox`).
- `hiloop usage` prints a point-in-time snapshot — active sandbox counts by state, reserved
  resources, and workspace limits — for the tenant, or one project with `--project`.
- For any route without a dedicated flag, `hiloop api <path> [-X post|delete] [-d '<json>']`
  reaches the whole REST surface.
