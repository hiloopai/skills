---
name: persisting-and-branching-workspaces
description: >-
  Persist a hiloop sandbox's filesystem across stops and branch new sandboxes from a shared state
  using sealed, versioned workspace revisions. Covers attaching a workspace at create
  (`--workspace-revision` + `--workspace-target`), how `hiloop sandbox stop` seals the workspace and
  `resume` restores it exactly under a new runtime generation, reading the sealed revision out of the
  stop result, and booting N fresh sandboxes from one revision to explore divergent paths. Use when
  asked to save, checkpoint, suspend, restore, or branch a sandbox's state, or to start several
  attempts from an identical filesystem.
metadata:
  version: 0.6.0
---

# Persisting and branching workspaces

A sandbox's durable state lives in its **workspace** — a versioned filesystem attached at create.
Stopping the sandbox **seals** the workspace into an immutable **revision**; resuming restores that
exact filesystem under a fresh runtime generation; and any *new* sandbox can boot from a sealed
revision as its writable base. One sealed revision can seed many sandboxes, so "get to a good
state once, then explore N paths from it" is: seal it, then create N sandboxes from the revision.

Two rules the platform never bends:

- **Continuity is explicit.** Only a sandbox created with a workspace revision gets durable
  stop/resume. Ephemeral scratch is never secretly snapshotted — without an attached workspace,
  resume refuses (`workspace_continuity_unavailable`) unless you accept an empty workspace with
  `--fresh-workspace`.
- **Filesystem only.** A seal captures bytes, not processes: after any stop, every process and all
  memory state from the previous generation is gone. Checkpoint durable work as files in the
  workspace.

> Tenant-scoped (see `authenticating`). Sandbox basics — projects, images/profiles, poll-until-ready
> — are the `creating-sandboxes` skill.

## Attach a workspace at create

Pass an exact immutable revision plus the absolute in-sandbox path to mount it at (the two flags
require each other):

```sh
hiloop sandbox create \
  --project <project> \
  --profile <profile> \
  --workspace-revision "$REVISION" \
  --workspace-target /workspace \
  --wait
```

A revision reference is `branchfs:v1:<repository-hex>:<change-hex>`. You get one from:

- **Your deployment's published base revisions** — the starting points an operator publishes for
  each environment; ask your operator (or check your deployment's docs) for the base revision that
  matches your profile.
- **A sealed stop of an existing sandbox** (below) — every sealed stop yields a new revision you
  can build on.

The revision is the sandbox's writable base: the sandbox sees its contents at the target path and
writes its own changes on top. The source revision itself is immutable — booting from it never
mutates it, which is what makes it safe to share across many sandboxes.

## Stop seals; resume restores

```sh
hiloop sandbox stop <sandbox> --wait      # seals the workspace into a new revision
hiloop sandbox resume <sandbox> --wait    # restores it exactly, new runtime generation
```

Both are asynchronous (`--wait` to block) and idempotent by sandbox id. A stopped sandbox's record
stays inspectable (`hiloop sandbox get`); resume brings back the exact sealed bytes with brand-new
process and memory state. Resuming an already-running sandbox succeeds without effect.

If the sandbox had no attached workspace, the stop is destructive and the stop result says so;
`resume` then fails unless you pass `--fresh-workspace` to explicitly accept an empty workspace
(the previous contents are not recovered).

## Read the sealed revision out of the stop result

`stop --wait --output json` prints the completed operation; its result carries the seal — the
repository and the newly sealed change — which compose into the revision reference a future create
takes:

```sh
stop=$(hiloop sandbox stop <sandbox> --wait --output json)
repo=$(echo "$stop"   | jq -r '.operation.result.stop.repository_id')
change=$(echo "$stop" | jq -r '.operation.result.stop.sealed_change_id')
REVISION="branchfs:v1:${repo}:${change}"
```

The result also says whether the sandbox is `resumable` — read it rather than assuming.

## The pattern: branch N paths from one state

1. Create a sandbox with a workspace attached and get it to the state you want to branch from
   (install dependencies, clone the repo, reach the checkpoint).
2. `stop --wait --output json` and compose the sealed revision (above) — your shared baseline.
3. Create N sandboxes, each with `--workspace-revision "$REVISION"` — every one boots from the
   identical filesystem and diverges independently.
4. Run a different attempt in each (see `running-commands-in-a-sandbox`), and compare what each
   branch did through the telemetry surface (see `querying-observability-trees`).
5. Delete the sandboxes you're done with; the sealed revision outlives them, so the baseline stays
   reusable.

A sealed revision is also a "prebuilt environment" you can keep: seal once after the slow setup,
then boot fresh sandboxes from it in seconds instead of re-installing.

## Safe retries

`create` takes `--idempotency-key <key>`: re-running with the same key returns the original sandbox
instead of creating a second one, and with a key set the CLI retries ambiguous failures (a 5xx, a
lost response) itself, up to 3 attempts. Reusing a key with a **different** request is rejected.
`stop`, `resume`, and `delete` need no key — they are idempotent by sandbox id.

## Suspend-and-wake, automatically

You don't have to stop by hand: an idle sandbox is stopped automatically after its idle timeout
(server default 30 minutes; tune with `--idle-timeout`, or disable with `--no-idle-reclaim`), and
a workspace-attached sandbox seals on that stop like any other. This is the devbox pattern — a
long-lived sandbox that suspends when you stop using it and wakes with its filesystem intact — and
`assembling-a-personal-devbox` builds the full flow on top of it.
