---
name: running-commands-in-a-sandbox
description: >-
  Run commands inside a hiloop sandbox and get results out. Covers the buffered
  `hiloop sandbox exec` (timeout ceiling, output truncation, exit codes, safe retries with
  idempotency keys), interactive terminals over managed SSH (`hiloop sandbox ssh`, port forwarding
  via stock OpenSSH flags), and moving files across the boundary with `hiloop sandbox cp`, volumes,
  and scp/sftp over SSH.
  Use when asked to run a command, script, build, or test inside a hiloop sandbox, to work in one
  interactively, or to get files in or out.
metadata:
  version: 0.7.0
---

# Running commands in a sandbox

> **Status: the sandbox runtime is mid-rebuild — these commands do not work against a deployment
> yet.** The verbs below ship with the CLI's next release, and no deployment serves the
> `/v1/sandboxes` routes yet, so `exec` and `ssh` return a bare `404` (empty body, no error
> envelope). The surface below is the settled contract they return on. Meanwhile, capture agent work
> locally with `hiloop run` (`querying-observability-trees`). See `creating-sandboxes` for the full
> status.

Once a sandbox is **running** (see `creating-sandboxes`), there are exactly two ways to run work in
it:

- **Buffered one-shot → `hiloop sandbox exec`.** Sends one command, waits, prints its captured
  stdout/stderr, and exits with its exit code. For short, non-interactive commands.
- **Interactive or long-attended → `hiloop sandbox ssh`.** A real terminal over managed SSH. For
  exploration, REPLs, file transfer, and anything you steer by hand.

There is no `hiloop sandbox run` one-shot verb, and no `sandbox cp`. If you want a sandbox that
exists for a single command, create it, exec, and delete it.

## Buffered: `exec`

Everything after `--` is the command:

```sh
hiloop sandbox exec <sandbox> --timeout 300 -- sh -lc 'cd /workspace && python3 train.py --lr 3e-4'
```

It prints stdout/stderr and exits with the command's exit code, so you can branch on it directly. A
non-zero exit means the command failed inside the sandbox; read stderr to diagnose.

- **The flag is `--timeout`, in seconds, and its accepted range is 1–3600.** (It is not
  `--timeout-secs`.) Omitted, the server default applies.
- **Transport success is distinct from command exit.** A timeout or a truncated response never
  fabricates an exit code — treat a transport failure and a non-zero exit as different problems.
  Retrying a command that genuinely failed will not help; fix the command.
- **Output is buffered and can be truncated.** When it is, the CLI prints
  `warning: remote output was truncated` on stderr. Write large output to a file inside the sandbox
  and read it back deliberately rather than relying on the exec response.
- **Retry ambiguous failures with `--idempotency-key <key>`.** Re-running with the same key returns
  the original execution instead of running the command twice.
- **Env vars and working directory are not flags** — bake them into the command
  (`sh -lc 'cd /workspace && FOO=bar python3 …'`).
- **Exec is buffered only in v1.** Streaming (SSE) output is a fast-follow, not available now, so
  do not design around live output from `exec`.

## Interactive: `ssh`

`hiloop sandbox ssh` resolves the sandbox, **auto-starts it if it is stopped**, and then spawns
**stock OpenSSH** against a short-lived generated config, relaying its exit status:

```sh
hiloop sandbox ssh <sandbox>                                    # a shell
hiloop sandbox ssh <sandbox> -- 'cd /workspace && git status'   # one remote command
hiloop sandbox ssh <sandbox> -- -L 8080:localhost:8080          # forward a port (stock ssh flag)
```

What follows `--` is handed to `ssh`: leading `-flags` are placed before the host and the rest
becomes the remote command, so port forwarding, agent forwarding, and the rest of the OpenSSH flag
surface work as they normally do. There is **no** `--local-forward` flag, no `sandbox port-forward`,
and no `sandbox expose` — preview URLs / HTTP exposure are a later phase.

If the environment cannot issue an SSH connection, the CLI says so explicitly and points you at
buffered execution rather than hanging:

```
session plane not yet available in this environment
Use buffered execution: hiloop sandbox exec <sandbox> -- <command>
```

SSH processes end when their session ends, and a stop/start cycle gives you a **new runtime
generation** — the filesystem returns, processes do not. Checkpoint durable work to a file.

## Errors, retries, and polling

- **Distinguish the two failure layers.** An auth / not-found / sandbox-not-running failure is not
  the same as a command that ran and exited non-zero.
- **Back off when polling.** If you poll state by id, use capped exponential backoff (1s, 2s, 4s …)
  with an overall timeout — don't hot-loop and don't poll forever.
- **Bound long jobs and checkpoint.** Split unattended work into bounded steps that write state to
  disk between commands; a sandbox with a `--ttl` will be reclaimed when it expires.

## Move files across the boundary

Pick the path that fits the data:

- **Files and directories, either direction:** `hiloop sandbox cp [-r] <src> <dst>`, writing the
  sandbox side as `<sandbox>:/absolute/path`. It needs nothing installed in the sandbox, retries a
  transient transport failure, and works against any image:

  ```sh
  hiloop sandbox cp ./train.py box:/workspace/train.py
  hiloop sandbox cp -r box:/workspace/out ./out
  ```

- **Bulk data in, shared by many sandboxes:** publish it as a **volume** and mount it at create
  (`--volume <name>:/data`) — see `managing-volumes`. This is the right answer for datasets, model
  caches, and checkpoints.
- **Incremental sync of a large tree:** `rsync` over managed SSH, which transfers only what changed
  — but it runs itself on both ends, so it needs the `rsync` binary inside the image, and the
  default image does not carry one. Plain `scp` and `sftp` work with nothing installed, the same way
  `cp` does.
- **Small results out:** write them to a file, then read them back with
  `exec -- cat /path/to/summary.json` — but mind the output truncation above.
- **Inputs from the network:** with egress allowed, fetch them from inside
  (`exec -- sh -lc 'curl -fsSL <url> -o /data.zip'`).
- **State you must keep:** snapshot the sandbox (`snapshotting-and-forking`), or create it with
  `--storage-class durable`.

## See what the command did

A sandbox is *where* an agent runs; telemetry is *how you see what it did*. To capture an agent's
model calls, tool traffic, and stdio, wrap the agent with `hiloop run` and query it — see
`querying-observability-trees`.
