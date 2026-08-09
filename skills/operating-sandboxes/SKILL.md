---
name: operating-sandboxes
description: >-
  Operate hiloop sandboxes through their full lifecycle: create from an image, snapshot, or the
  platform default; inspect, exec, stop, start, and delete; use managed SSH and file transfer when
  available; snapshot and branch; or compose a persistent development environment or devbox. Use
  for any request to create, launch, inspect, enter, execute in, copy files to or from, snapshot, fork,
  stop, restart, or remove a hiloop sandbox. Routes deployment-dependent session, persistence,
  attachment, and capture workflows to focused references and treats capability refusals as
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
| `--volume`, `--secret` | Refused where no backing transport exists |
| ambient sandbox telemetry | Managed capture: explicit entrypoint/exec/SSH, cooperative HTTP, OTLP |
| nonzero `--gpus` | Unavailable in sandbox v1; do not request it |

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

`create --output json` returns the converged sandbox object plus `run_id`. Read the sandbox id from
`.id` and its ambient run from `.run_id`.

Common flags are `--ttl`, `--storage-class standard|durable`, repeatable `--port`, `--cpus`,
`--memory-mb`, repeatable `--metadata`, and `--idempotency-key`. The optional `--volume`, `--secret`,
flags are capability requests, not promises. There is no sandbox `--capture` flag. The CLI accepts
`--gpus` for forward compatibility, but sandbox v1 refuses every nonzero request.

## Inspect and execute

```sh
hiloop sandbox list --state running
hiloop sandbox get <sandbox>
hiloop sandbox exec <sandbox> --timeout 300 -- sh -lc 'cd /workspace && ./build.sh'
```

Everything after `--` is the command. `exec` is buffered, relays the remote exit code, and may
truncate large output with an explicit warning. Write large results to a file. Retry an ambiguous
transport failure with the same `--idempotency-key`; do not retry a command that ran and failed.

### Ambient capture

The sandbox starts one managed capture session before the workload. An explicit create command,
every buffered exec, and non-PTY SSH receive process/stdio capture with distinct execution ids. PTY
SSH records boundaries and terminal output, never keystrokes/input. The whole sandbox also shares a
cooperative HTTP proxy and an OTLP/HTTP receiver; clients that ignore proxy variables or use raw
sockets can bypass HTTP capture.

An image's implicit entrypoint still receives proxy/OTLP settings, but Kubernetes cannot prepend a
supervisor while preserving an unknown image command. Supply an explicit create command after `--`
when entrypoint process/stdio capture matters. Inside the sandbox, `hiloop run -- <command>` joins
the ambient run without a Hiloop credential or second proxy; run-selecting, per-command secret, and
egress flags are refused at that already-owned boundary.

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
