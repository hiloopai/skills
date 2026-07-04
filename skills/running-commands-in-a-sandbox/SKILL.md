---
name: running-commands-in-a-sandbox
description: >-
  Run commands inside a hiloop sandbox and move files across its boundary. Covers the quick buffered
  `hiloop sandbox exec`, starting an interactive execution with `hiloop sandbox start` (env, cwd,
  timeout, stdin, pty), streaming its combined output with `stream`, steering it with `send-input`
  (stdin and control signals: interrupt/terminate/kill/eof) and `kill`, reading exit codes, and
  archiving / restoring files via artifacts. Use when asked to run a command, script, build, test, or
  long-running / interactive process inside a hiloop sandbox, to watch or steer one live, or to get
  files in or out.
metadata:
  version: 0.3.0
---

# Running commands in a sandbox

Once a sandbox is **ready** (see `creating-sandboxes`), run commands in it with the `hiloop sandbox`
commands. There are two ways to run a command, and the choice matters:

- **Quick one-shot → `hiloop sandbox exec`.** Runs the command, waits for it to finish, prints its
  captured stdout/stderr, and exits with its exit code. Use for short, non-interactive commands.
- **Long-running or interactive → `hiloop sandbox start` + `stream`.** Starts the process and returns
  an execution id immediately, so you can **stream** its output live and **steer** it (feed stdin,
  signal it). Use for builds, agent runs, anything slow, or anything you may need to watch or stop.

## Quick one-shot: `exec`

Everything after `--` is the command:

```sh
hiloop sandbox exec <sandbox-id> --timeout-secs 600 -- python train.py --lr 3e-4
```

It polls the execution to completion, prints stdout/stderr, and exits with the command's exit code —
so you can branch on it directly. A non-zero exit means the command failed inside the sandbox; read
stderr to diagnose. (`--timeout-secs` is optional; omit it for the server default.)

> Need to set env vars or a working directory for a one-shot? Those aren't `exec` flags — use the
> `:execute` passthrough (below) with a full command spec, or bake them into the command
> (`sh -lc 'cd /workspace && FOO=bar python …'`).

The passthrough equivalent, when you need `env` / `workingDir` / `stdin` at start:

```sh
hiloop api "/v1/sandboxes/<sandbox-id>:execute" -X post -d '{
    "command": {
      "program": "python", "args": ["train.py", "--lr", "3e-4"],
      "env": { "WANDB_MODE": "offline" }, "workingDir": "/workspace", "timeoutSecs": 600
    }
  }'
```

## Long-running / interactive: start, stream, steer

### Start an execution

`start` launches the process and returns immediately, printing the **execution id** (the handle for
everything below). Set `--pty` to allocate a pseudo-terminal for programs that need one (REPLs, TUIs,
anything that checks for a tty); pass initial stdin with `--stdin`:

```sh
EXEC_ID=$(hiloop sandbox start <sandbox-id> --pty -- claude -p "implement the feature")
```

### Stream the output

Stream the execution's combined stdout/stderr live; the stream stays open until the process exits,
and the process's exit code becomes the command's exit code:

```sh
hiloop sandbox stream "$EXEC_ID"
```

### Steer: send input or a signal

Feed the running process either standard-input bytes **or** a control signal — one per call:

```sh
hiloop sandbox send-input "$EXEC_ID" --stdin "y
"                                                    # write to stdin
hiloop sandbox send-input "$EXEC_ID" --signal interrupt   # interrupt it (like Ctrl-C)
```

Signals: `interrupt` (SIGINT), `terminate` (SIGTERM, polite stop), `kill` (SIGKILL, forced), `eof`
(close stdin — let a process reading stdin finish).

### Kill

To stop an execution outright, signal it directly (`terminate` is the default):

```sh
hiloop sandbox kill "$EXEC_ID" --signal kill
```

### Interactive shell

For hands-on exploration, `hiloop sandbox shell <sandbox-id>` attaches an interactive shell: it
starts a durable execution, streams output, and forwards your stdin (with terminal controls when a
PTY is requested). Not SSH — both directions are recorded like any other execution. Prefer
`exec`/`start` for anything scripted.

## Errors, retries, and polling backoff

- **Distinguish the two failure layers.** A non-zero CLI/transport failure (auth, not-found, sandbox
  not ready) is different from a command that ran but exited non-zero. Retrying a bad command won't
  help; fix the command.
- **Back off when polling.** If you poll an execution or operation by id, use capped exponential
  backoff (e.g. 1s, 2s, 4s … to a ceiling) with a sane overall timeout — don't hot-loop, and don't
  poll forever. For live output, prefer `stream` over polling.
- **A dropped stream is recoverable.** If `stream` drops mid-run, re-open it against the same
  execution id; the execution keeps running independently of any one viewer.

## Monitoring a long job

For anything slow, **stream the execution** and act on events as they arrive rather than blocking. An
idle sandbox can be reclaimed, so don't start a long job and walk away with nothing watching it. If
you must detach, keep the work observable — re-`stream` periodically, or capture the whole run as
telemetry and query it (the `querying-observability-trees` skill); `send-input` lets you answer
prompts or steer an interactive job without restarting.

## Move files across the boundary

File transfer is over the passthrough. Archive a file from the sandbox into an **artifact**:

```sh
hiloop api "/v1/sandboxes/<sandbox-id>/files:to-artifact" -X post \
  -d '{ "path": "/workspace/results/report.json", "mediaType": "application/json" }'
```

Restore an artifact into a sandbox file:

```sh
hiloop api "/v1/sandboxes/<sandbox-id>/files:from-artifact" -X put \
  -d '{ "artifactId": "<artifact-id>", "path": "/workspace/inputs/report.json" }'
```

Both calls return **operations** — poll `hiloop api /v1/operations/<id>` before assuming the move is
complete. Fetch an artifact's bytes with `hiloop api /v1/artifacts/<id>`.

## See what the command did

A sandbox is *where* the agent runs; tree-native telemetry is *how you see what it did*. To capture a
full agent run (model calls, tool traffic, stdio) rather than a single command's exit code, wrap the
agent with `hiloop run` and query it — see `querying-observability-trees`. Capture is on by default for
sandboxes, so a process you start is already observable by run/fork lineage.
