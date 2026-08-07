---
name: operating-sandboxes
description: >-
  Operate hiloop sandboxes through their full lifecycle: create from an image, snapshot, or the
  platform default; inspect, exec, stop, start, and delete; use managed SSH and file transfer when
  available; snapshot and branch; or compose a persistent development environment. Use for any
  request to create, launch, inspect, enter, execute in, copy files to or from, snapshot, fork,
  stop, restart, or remove a hiloop sandbox. Routes deployment-dependent session, persistence,
  attachment, capture, and GPU workflows to focused references and treats capability refusals as
  final answers.
---

# Operating sandboxes

Authenticate and select a project first. Core lifecycle and buffered exec are served on every
deployment; optional capabilities never silently degrade:

| Capability | Status |
|---|---|
| create/list/get/exec/stop/start/delete | Core |
| `--storage-class durable`, snapshots, `--from` | Deployment-dependent |
| `ssh`, `cp`, scp/sftp, port forwarding | Needs the deployment session plane |
| `--volume`, `--secret`, `--capture on`, nonzero `--gpus` | Refused where no backing transport or capacity exists |

An `unsupported_capability` response is the answer. Do not invent another verb, leak a credential,
or silently run without requested data or capture.

## Create

The name is positional. Use at most one source; omitting both selects the platform default image:

```sh
hiloop sandbox create scratch
hiloop sandbox create build --image ubuntu:24.04 --cpus 2 --memory-mb 4096 -- sleep infinity
```

An image whose entrypoint exits needs a long-running replacement command after `--`. Create blocks
until the sandbox is running or terminal; there is no `--wait` step.

Common flags are `--ttl`, `--storage-class standard|durable`, repeatable `--port`, `--cpus`,
`--memory-mb`, repeatable `--metadata`, and `--idempotency-key`. Optional `--volume`, `--secret`,
`--capture`, and `--gpus` are capability requests, not promises.

## Inspect and execute

```sh
hiloop sandbox list --state running
hiloop sandbox get <sandbox>
hiloop sandbox exec <sandbox> --timeout 300 -- sh -lc 'cd /workspace && ./build.sh'
```

Everything after `--` is the command. `exec` is buffered, relays the remote exit code, and may
truncate large output with an explicit warning. Write large results to a file. Retry an ambiguous
transport failure with the same `--idempotency-key`; do not retry a command that ran and failed.

For an interactive terminal, file transfer, or port forwarding, read
[`references/sessions.md`](references/sessions.md). For snapshots or branching, read
[`references/snapshots.md`](references/snapshots.md). For a persistent development environment,
read [`references/devbox.md`](references/devbox.md). Load only the reference the task needs.

## Stop, start, delete

```sh
hiloop sandbox stop <sandbox>
hiloop sandbox start <sandbox>
hiloop sandbox delete <sandbox>
```

Stop preserves the sandbox record and whatever its storage class guarantees. Start creates a new
runtime generation; unless the deployment explicitly proves memory restore, assume processes are
gone and only persisted files return. Delete is permanent. Snapshot anything needed later and
clean up task sandboxes unless told to keep them.

There is no `sandbox run`, `fork`, `restore`, `resume`, `access`, `expose`, `port-forward`,
`ssh-config`, or `logs` verb. Use create + exec + delete for one-shot work and `create --from` for a
branch.
