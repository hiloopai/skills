---
name: running-commands-in-a-sandbox
description: >-
  Execute commands inside a hiloop sandbox and move files across its boundary. Covers the
  `:execute` endpoint (program, args, env, cwd, timeout), reading an execution's exit code and
  stdout/stderr, and archiving files to / restoring files from artifacts. Use when asked to run a
  command, script, build, or test inside a hiloop sandbox, or to get files in or out of one.
metadata:
  version: 0.1.0
---

# Running commands in a sandbox

Once a sandbox is **ready** (see `creating-sandboxes`), run commands in it and move files across its
boundary. From the CLI, use the `hiloop api` passthrough.

## Execute a command

A command spec is a program, its arguments, and optionally environment, working directory, and a
timeout. Execution is a mutation, so it takes an `idempotency-key`.

```sh
hiloop api "/v1/sandboxes/${SANDBOX_ID}:execute" -X post \
  -H "idempotency-key: $(uuidgen)" \
  -d '{
    "command": { "program": "python", "args": ["train.py", "--lr", "3e-4"] }
  }'
```

The response is an **execution** with its own `id`. Each execution records an **exit code** and
references to its captured **stdout** and **stderr**. Fetch it by id to read the result:

```sh
hiloop api "/v1/executions/${EXECUTION_ID}"
```

Check the exit code before treating a command as successful. A non-zero exit means the command
failed inside the sandbox — read stderr to diagnose, don't assume success.

## Move files across the boundary

Archive a file from the sandbox filesystem into an **artifact**:

```sh
hiloop api "/v1/sandboxes/${SANDBOX_ID}/files:to-artifact" -X post \
  -H "idempotency-key: $(uuidgen)" \
  -d '{ "path": "/workspace/results/report.json", "mediaType": "application/json" }'
```

Restore an artifact into a sandbox file:

```sh
hiloop api "/v1/sandboxes/${SANDBOX_ID}/files:from-artifact" -X put \
  -H "idempotency-key: $(uuidgen)" \
  -d '{ "artifactId": "<artifact-id>", "path": "/workspace/inputs/report.json" }'
```

Both calls return **operations** — poll the operation (`GET /v1/operations/{id}`) before assuming the
file move is complete. Fetch an artifact's bytes with `GET /v1/artifacts/{id}`.

## See what the command did

A sandbox is *where* the agent runs; tree-native telemetry is *how you see what it did*. To capture a
full agent run (model calls, tool traffic, stdio) rather than a single command's exit code, wrap the
agent with `hiloop run` and then query it — see `querying-observability-trees`.
