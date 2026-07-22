---
name: running-commands-in-a-sandbox
description: >-
  Run commands inside a hiloop sandbox and get results out. Covers the quick buffered
  `hiloop sandbox exec` (timeout ceiling, output caps, exit codes, safe retries with idempotency
  keys), one-shot purpose-built sandboxes with `hiloop sandbox run` (--rm, --wait), interactive
  terminals over managed SSH (`hiloop sandbox ssh`, port forwarding), and moving files across the
  boundary (workspace + rsync, execution output artifacts). Use when asked to run a command,
  script, build, test, or long-running process inside a hiloop sandbox, to work in one
  interactively, or to get files in or out.
metadata:
  version: 0.5.0
---

# Running commands in a sandbox

Once a sandbox is **running** (see `creating-sandboxes`), there are three ways to run work in it —
and the choice matters:

- **Quick, bounded one-shot → `hiloop sandbox exec`.** Runs the command through the durable
  execution queue, waits, prints its captured stdout/stderr, and exits with its exit code. For
  short, non-interactive commands.
- **One command as the sandbox's whole purpose → `hiloop sandbox run`.** Creates the sandbox, runs
  the command to completion, and stops (or deletes) the sandbox when it exits. For batch jobs and
  fire-and-forget work.
- **Interactive or long-attended → `hiloop sandbox ssh`.** A real terminal through the signed
  session gateway, on profiles that carry managed SSH. For exploration, REPLs, and anything you
  steer by hand.

## Quick one-shot: `exec`

Everything after `--` is the command:

```sh
hiloop sandbox exec <sandbox> --timeout-secs 300 -- sh -lc 'cd /workspace && python3 train.py --lr 3e-4'
```

It polls the execution to completion, prints stdout/stderr, and exits with the command's exit
code — so you can branch on it directly. A non-zero exit means the command failed inside the
sandbox; read stderr to diagnose. Behaviors to know:

- **Every command is a durable execution record** — state, exit code, and bounded output survive
  the CLI invocation.
- **Timeouts have a ceiling.** `--timeout-secs` is optional (server default 30s); a command that
  exceeds it fails with `command_timed_out`. The server rejects a timeout above what one queued
  execution may run (595s on a default deployment, named in the rejection) — run longer work as a
  `sandbox run` one-shot or under SSH.
- **Captured output is capped** by the runtime (as low as 128 KiB of combined stdout/stderr). An
  over-cap command may be stopped at the cap and prints the captured leading bytes plus a
  truncation warning on stderr — write large output to a file under `/workspace` instead.
- **Retry ambiguously-failed execs with an idempotency key.** Pass `--idempotency-key <key>`:
  re-running with the same key returns the original execution instead of running the command a
  second time (the same key with a different command is rejected).
- **Env vars and working directory** aren't `exec` flags — bake them into the command
  (`sh -lc 'cd /workspace && FOO=bar python3 …'`), or use the `:execute` passthrough with a full
  command spec (`env`, `working_dir`, `timeout_secs`).

Write only below `/workspace` or `/tmp` — the image root is read-only.

## One-shot sandbox: `sandbox run`

When the sandbox exists *for* one command, create-and-run in one verb. It takes the same
environment flags as `sandbox create` (`--profile`/`--image` required, resources, workspace,
`--secret`, `--as`), runs the command once the sandbox is running, and stops the sandbox when the
command exits — the run ends `succeeded` on exit 0 and `failed` otherwise:

```sh
hiloop sandbox run \
  --project <project> \
  --profile gvisor-cpu \
  --name train-once \
  --rm \
  --wait \
  -- python3 -c 'print("done")'
```

- Detached by default: it prints the sandbox, run, and execution ids and returns. `--wait` follows
  the command's output live and exits with its exit code once the sandbox has come to rest.
- `--rm` deletes the sandbox when the command exits instead of stopping it; the run and execution
  records persist either way.
- The command's lifetime is bounded: `--max-runtime` (server default 86400s/24h) kills it past the
  cap, and `--idempotency-key` makes a retried create-and-run safe (the original sandbox,
  operation, and execution come back instead of a second run).

## Interactive: `sandbox ssh`

On a profile that advertises managed SSH, attach a real terminal through the signed session
gateway — ephemeral credentials, no guest `sshd`, no exposed port:

```sh
hiloop sandbox ssh <sandbox>                          # a shell
hiloop sandbox ssh <sandbox> -- 'cd /workspace && git status'   # one remote command
hiloop sandbox ssh <sandbox> --local-forward 8080:8080          # forward a local port in
```

SSH processes end when their session ends; checkpoint durable work under `/workspace`. The full
devbox workflow — stock OpenSSH config, rsync, access grants, suspend-and-wake — is the
`assembling-a-personal-devbox` skill.

To reach a TCP service in the sandbox without SSH, `hiloop sandbox port-forward <sandbox>
<remote-port>` forwards a local loopback port, and `hiloop sandbox expose <sandbox> <port>` mints a
token-gated preview URL others can open (see `assembling-a-personal-devbox`).

## Errors, retries, and polling backoff

- **Distinguish the two failure layers.** A non-zero CLI/transport failure (auth, not-found,
  sandbox not running) is different from a command that ran but exited non-zero. Retrying a bad
  command won't help; fix the command.
- **Back off when polling.** If you poll an execution or operation by id, use capped exponential
  backoff (e.g. 1s, 2s, 4s … to a ceiling) with a sane overall timeout — don't hot-loop, and don't
  poll forever.
- **Bound long jobs and checkpoint.** Split unattended work into bounded steps that checkpoint
  state under `/workspace` between commands — an idle sandbox is reclaimed on its idle timeout
  (see `creating-sandboxes`), and a `sandbox run` one-shot carries its own `--max-runtime`.

## Move files across the boundary

There is no dedicated file-copy verb; pick the path that fits the data:

- **Results a command produces:** write them under `/workspace`, then read small ones back with
  `exec` (`-- cat /workspace/out/summary.json`). A workspace attached as a versioned revision also
  survives the sandbox — seal it and the data outlives the runtime
  (`persisting-and-branching-workspaces`).
- **Bulk copy in either direction:** on a managed-SSH profile, install the OpenSSH stanza and use
  rsync — `hiloop sandbox ssh-config install <sandbox>`, then
  `rsync --archive ./data/ hiloop-<sandbox>:/workspace/data/` (see
  `assembling-a-personal-devbox`).
- **Inputs from the network:** with egress allowed, fetch them from inside
  (`exec -- sh -lc 'curl -fsSL <url> -o /workspace/data.zip'`).
- **Execution outputs as artifacts:** each execution records its bounded stdout/stderr as
  content-addressed artifacts. Read an execution over the passthrough
  (`hiloop api /v1/executions/<execution-id>`) for its artifact ids, fetch small ones via
  `hiloop api /v1/artifacts/<artifact-id>`, and rediscover ids later with `hiloop artifact list`.

## See what the command did

A sandbox is *where* the agent runs; telemetry is *how you see what it did*. Platform lifecycle
events flow for every sandbox (`hiloop query --run-id <run-id> --signal runtime`), and a `sandbox
run` one-shot registers a run you can inspect with `hiloop runs show`. To capture a full agent
run's model calls, tool traffic, and stdio, wrap the agent with `hiloop run` and query it — see
`querying-observability-trees`.
