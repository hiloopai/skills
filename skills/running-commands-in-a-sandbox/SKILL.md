---
name: running-commands-in-a-sandbox
description: >-
  Run commands inside a hiloop sandbox and move files across its boundary. Covers the quick
  synchronous `:execute`, starting an interactive `executions` process (env, cwd, timeout, stdin,
  pty), streaming its combined stdout/stderr over Server-Sent Events, steering it with stdin and
  control signals (interrupt/terminate/kill/eof), reading exit codes, and archiving files to /
  restoring files from artifacts. Use when asked to run a command, script, build, test, or
  long-running / interactive process inside a hiloop sandbox, to watch or steer one live, or to get
  files in or out.
metadata:
  version: 0.2.0
---

# Running commands in a sandbox

Once a sandbox is **ready** (see `creating-sandboxes`), run commands in it and move files across its
boundary. From the CLI, use the `hiloop api` passthrough. There are two ways to run a command, and the
choice matters:

- **Quick one-shot → `:execute`.** A blocking call that runs the command and hands back the finished
  execution. Use for short, non-interactive commands where you only need the exit code and captured
  output.
- **Long-running or interactive → `executions` + stream.** Starts the process and returns
  immediately, so you can **stream** its output live and **steer** it (feed stdin, interrupt it).
  Use for builds, agent runs, anything slow, or anything you may need to watch or stop.

Both forms take the same **command spec**: a `program`, its `args`, and optionally `env` (a string
map), a `workingDir`, and a `timeoutSecs` (`0` uses the server default). Starting an execution is a
create-style mutation, so the `idempotency-key` is optional — supply your own to make a retry safe, or
omit it and the server generates one.

## Quick one-shot: `:execute`

```sh
hiloop api "/v1/sandboxes/${SANDBOX_ID}:execute" -X post -d '{
    "command": {
      "program": "python",
      "args": ["train.py", "--lr", "3e-4"],
      "env": { "WANDB_MODE": "offline" },
      "workingDir": "/workspace",
      "timeoutSecs": 600
    }
  }'
```

The response is an **execution** with its own `id`, an **exit code**, and references to its captured
**stdout** and **stderr** artifacts (`stdoutArtifactId` / `stderrArtifactId`). Fetch it by id to read
the result:

```sh
hiloop api "/v1/executions/${EXECUTION_ID}"
```

Check the exit code before treating a command as successful. A non-zero exit means the command failed
inside the sandbox — read stderr (via its artifact, see below) to diagnose; don't assume success.

Pass `stdin` at the top level to feed bytes to the process at start:

```sh
hiloop api "/v1/sandboxes/${SANDBOX_ID}:execute" -X post -d '{
    "command": { "program": "cat" },
    "stdin": "hello\n"
  }'
```

## Long-running / interactive: start, stream, steer

### Start an execution

`executions` starts the process and returns immediately. The response holds the **execution** (note
its `id` — it is the handle for everything below) and an **operation**. Set `pty: true` to allocate a
pseudo-terminal for programs that need one (REPLs, TUIs, anything that checks for a tty):

```sh
hiloop api "/v1/sandboxes/${SANDBOX_ID}/executions" -X post -d '{
    "command": {
      "program": "claude",
      "args": ["-p", "implement the feature"],
      "workingDir": "/workspace",
      "timeoutSecs": 0
    },
    "pty": true
  }'
```

### Stream the output

Subscribe to the execution's combined stdout/stderr as **Server-Sent Events**. This is how you watch
a long-running process live; the stream stays open until the process exits.

```sh
hiloop api "/v1/executions/${EXECUTION_ID}:stream"
```

Each event is an `ExecOutputEvent` with exactly one of:

- `stdoutChunk` — a base64-encoded chunk of standard output.
- `stderrChunk` — a base64-encoded chunk of standard error.
- `exit` — the **terminal** event: `{ "exitCode": <int>, "signal": <int> }`. No further events
  follow it. `signal` is `0` for a normal exit; non-zero means the process was killed by that signal.

Decode the base64 chunks to reconstruct output. Treat the `exit` event as end-of-stream and read
`exitCode` the same way you would for a one-shot — non-zero is a failure.

### Steer: send input or a signal

Feed the running process either standard-input bytes **or** a control signal — one per call:

```sh
# write to the process's stdin
hiloop api "/v1/executions/${EXECUTION_ID}:input" -X post -d '{ "stdin": "y\n" }'

# interrupt it (e.g. stop a running agent) — like Ctrl-C
hiloop api "/v1/executions/${EXECUTION_ID}:input" -X post -d '{ "signal": "EXEC_SIGNAL_INTERRUPT" }'
```

Signals: `EXEC_SIGNAL_INTERRUPT` (SIGINT), `EXEC_SIGNAL_TERMINATE` (SIGTERM, polite stop),
`EXEC_SIGNAL_KILL` (SIGKILL, forced), `EXEC_SIGNAL_EOF` (close stdin — let a process reading stdin
finish).

### Kill

To stop an execution outright, signal it directly. `EXEC_SIGNAL_TERMINATE` is used when you omit the
signal:

```sh
hiloop api "/v1/executions/${EXECUTION_ID}:kill" -X post -d '{ "signal": "EXEC_SIGNAL_KILL" }'
```

## Errors, retries, and polling backoff

- **Distinguish the two failure layers.** A non-2xx from `hiloop api` is an *API/transport* failure
  (auth, not-found, sandbox not ready, transcoding). A 2xx with a non-zero execution `exitCode` is a
  *command* failure inside the sandbox. Handle them differently — retrying a bad command won't help.
- **Make retries idempotent.** When you retry a `:execute` or `executions` start, reuse the same
  `idempotency-key` so a network blip doesn't launch the command twice.
- **Back off when polling.** When you poll an execution or operation by id, use capped exponential
  backoff (e.g. 1s, 2s, 4s … to a ceiling) with a sane overall timeout — don't hot-loop, and don't
  poll forever. For live output, prefer the `:stream` SSE endpoint over polling: it pushes events as
  they happen instead of you re-fetching.
- **A dropped stream is recoverable.** If a `:stream` connection drops mid-run, re-open it against the
  same `executionId`; the execution keeps running independently of any one viewer.

## Monitoring a long job

For anything slow, **stream the execution** (`:stream`) and act on the events as they arrive rather
than blocking on a single call. The stream both shows you progress and keeps you attached: an idle
sandbox can be reclaimed, so don't start a long job and walk away with nothing watching it. If you
must detach, keep the work observable — stream periodically, or capture the whole run as telemetry
(below) and query it. When the job is interactive, `:input` lets you answer prompts or steer it
without restarting.

## Move files across the boundary

Archive a file from the sandbox filesystem into an **artifact**:

```sh
hiloop api "/v1/sandboxes/${SANDBOX_ID}/files:to-artifact" -X post -d '{ "path": "/workspace/results/report.json", "mediaType": "application/json" }'
```

Restore an artifact into a sandbox file:

```sh
hiloop api "/v1/sandboxes/${SANDBOX_ID}/files:from-artifact" -X put -d '{ "artifactId": "<artifact-id>", "path": "/workspace/inputs/report.json" }'
```

Both calls return **operations** — poll the operation (`GET /v1/operations/{id}`) before assuming the
file move is complete. Fetch an artifact's bytes with `GET /v1/artifacts/{id}` — this is also how you
read an execution's captured `stdoutArtifactId` / `stderrArtifactId`.

## See what the command did

A sandbox is *where* the agent runs; tree-native telemetry is *how you see what it did*. To capture a
full agent run (model calls, tool traffic, stdio) rather than a single command's exit code, wrap the
agent with `hiloop run` and then query it — see `querying-observability-trees`. Capture is on by
default for sandboxes, so a process you start is already observable by run/fork lineage.
