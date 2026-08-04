---
name: creating-sandboxes
description: >-
  Create, inspect, stop, start, and delete hiloop sandboxes — isolated environments an agent runs
  in. Covers the create→use→delete lifecycle with the `hiloop sandbox` commands, the required
  image-or-snapshot choice, storage class, published ports, volume mounts, telemetry capture, TTL,
  metadata, and idempotent retries. Use when asked to spin up / provision / launch a hiloop sandbox
  or environment, choose its image, stop or start one, or tear one down.
metadata:
  version: 0.9.0
---

# Creating sandboxes

> **Status: the sandbox runtime is mid-rebuild — these commands do not work against a deployment
> yet.** Two separate things are true, and both matter:
>
> 1. **The verbs below ship with the CLI's next release.** They are the settled contract. An
>    already-installed CLI still carries the *previous* sandbox surface (`sandbox run`, `fork`,
>    `access`, `expose`, `port-forward`, `ssh-config`, `shell`, `stream`) — those verbs were
>    removed, and nothing on this page depends on them.
> 2. **No deployment serves the `/v1/sandboxes` routes yet.** A call returns a bare `404` with an
>    empty body — not the usual `{"code": …, "message": …}` envelope, and not a helpful client-side
>    message. Recognise that shape for what it is: an unserved route, not a bad request of yours.
>
> So read this as the contract, not as runnable steps. Don't invent verbs or workarounds to get
> around the 404: capture agent work locally with `hiloop run` instead
> (`querying-observability-trees`), and expect this surface back with the rebuilt runtime.

A **sandbox** is an isolated environment your agent runs in. It boots from an **unmodified OCI
image** or from a **snapshot**. The lifecycle is: create (which blocks until running) → use →
delete. For fields without a dedicated flag, drop to `hiloop api`, the authenticated passthrough for
any REST route.

> Authenticate first (see the `authenticating` skill).

## The whole surface

This is the complete sandbox surface, deliberately small — each verb maps to one route:

```sh
hiloop sandbox create <name> --image <ref>   # POST   /v1/sandboxes
hiloop sandbox list                          # GET    /v1/sandboxes
hiloop sandbox get <sandbox>                 # GET    /v1/sandboxes/{id}
hiloop sandbox stop <sandbox>                # PATCH  /v1/sandboxes/{id}
hiloop sandbox start <sandbox>               # PATCH  /v1/sandboxes/{id}
hiloop sandbox delete <sandbox>              # DELETE /v1/sandboxes/{id}
hiloop sandbox exec <sandbox> -- <cmd>       # POST   /v1/sandboxes/{id}/exec
hiloop sandbox snapshot create <sandbox>     # POST   /v1/sandboxes/{id}/snapshots
hiloop sandbox snapshot list                 # GET    /v1/snapshots
hiloop sandbox snapshot delete <snapshot>    # DELETE /v1/snapshots/{id}
```

Plus `hiloop sandbox ssh` for interactive work and `hiloop sandbox cp` for file transfer
(`running-commands-in-a-sandbox`), which ride the session plane rather than REST. There is no
`run`, `fork`, `restore`, `resume`, `access`, `expose`, `port-forward`, `ssh-config`, or `logs`
verb — if you reach for one, it does not exist.

## Create

The name is **positional**, and **exactly one of `--image` or `--from` is required**:

```sh
hiloop sandbox create experiment-a --image ubuntu:24.04
hiloop sandbox create experiment-b --from <snapshot-name-or-id>
```

- `--image <ref>` boots an **unmodified customer OCI image** — no image build step, no baked-in
  agent. Pin production environments by digest (`repository@sha256:…`); a tag is not an environment
  identity.
- `--from <snapshot>` boots from a snapshot instead. This one flag is restore, fork, and branch —
  see `snapshotting-and-forking`.

**Create blocks until the sandbox is running** (or reaches a terminal state) and prints a progress
line; there is no `--wait` flag and no separate poll-until-ready step. `--output json` prints the
raw body.

Sizing is `--cpus` / `--memory-mb` / `--gpus`, each defaulting to the deployment's own default.
There is no `--profile`, `--disk-mb`, `--gpu-model`, or `--arch`; those went with the previous
runtime, so do not pass them.

### The flags that exist

| Flag | Meaning |
|---|---|
| `--cpus <n>` | vCPUs, burstable. Omitted, the deployment default. |
| `--memory-mb <mb>` | Memory in MB. Omitted, the deployment default. |
| `--gpus <n>` | Accelerator count. Defaults to 0. |
| `--ttl <seconds>` | Sandbox lifetime. Omitted, no TTL is set. |
| `--storage-class standard\|durable` | `standard` (default) is node-bound; `durable` is a same-zone reattachable volume, for state you must not lose. |
| `--port <n>` | Guest TCP port to make privately reachable (1–65535). Repeatable. |
| `--volume <VOLUME:/abs/path>` | Mount a pre-registered volume. Repeatable. See `managing-volumes`. |
| `--secret <name>` | Request a pre-registered secret binding. Repeatable — but see the caveat below. |
| `--capture on\|off` | Override the deployment's telemetry capture default. |
| `--metadata <KEY=VALUE>` | Caller-owned metadata, also filterable on `list`. Repeatable. |
| `--idempotency-key <key>` | Replay key; one is generated per invocation when omitted. |

`--volume` and `--secret` reference **pre-registered resources only** — register them first, so
create validation is total and never half-succeeds.

### Idempotent retries

Pass `--idempotency-key <key>` to make a retry safe: re-running with the same key returns the
original sandbox instead of creating a second one. Reusing a key with a *different* request is a
conflict. This matters because create is CR-first: the client-supplied key is what makes a replay
idempotent.

### Secrets are not delivered into sandboxes yet

`--secret <name>` is accepted and sent, but **in-sandbox secret delivery is being respecified and
currently fails closed** — a sandbox never silently runs without the credential it asked for. Bind
secrets on `hiloop run` instead, where the broker path works today (`managing-secrets`), and never
work around it by putting a plaintext credential in a sandbox env, image, or command line.

### Capture

`--capture on|off` overrides the deployment default for recording the sandbox's activity as
queryable telemetry. To capture an agent's model/tool/HTTP activity today, wrap the command with
`hiloop run` (see `querying-observability-trees`).

## Inspect

```sh
hiloop sandbox get <sandbox>                       # by name or id
hiloop sandbox list                                # the active project
hiloop sandbox list --state running                # observed state; repeatable
hiloop sandbox list --name experiment-a            # exact name
hiloop sandbox list --metadata owner=ada           # exact metadata match; repeatable
hiloop sandbox list --all                          # include retained terminated rows
```

The **desired** state you asked for is tracked separately from the **observed** state reached. A
sandbox in a failed state reports a stable machine-readable code plus a human-readable message —
diagnose from that rather than guessing.

Project scope comes from `HILOOP_PROJECT` or the active context's project; `sandbox create` and
`sandbox list` have no user-facing `--project` flag.

## Stop, start, delete

```sh
hiloop sandbox stop <sandbox>      # seal and stop
hiloop sandbox start <sandbox>     # start a stopped one, or return a running one unchanged
hiloop sandbox delete <sandbox>    # permanent; waits for termination
```

`stop` seals the sandbox and keeps its record inspectable. `start` brings it back under a **new
runtime generation** — the filesystem returns, every process and all memory state from the previous
generation is gone. (Memory restore is a committed later phase, not v1.)

**`delete` does not prompt.** It is immediate and irreversible — there is no "are you sure" to catch
a mistake, and the `--yes` flag is accepted but does nothing (it is hidden from `--help` for that
reason). Snapshot anything you might want back *before* deleting.

Always clean up sandboxes you created for a task unless told to keep them.

## Tips

- `list` / `get` accept `--output json`; capture the `id`. Names are project-unique but the id is
  the canonical handle.
- Durability is a create-time choice: `--storage-class durable`, or snapshot before you stop.
- `hiloop usage` prints a point-in-time snapshot — active sandbox counts by state and your limits.
- `hiloop api <path> [-X post] [-d '<json>']` reaches any route without a dedicated flag.
