---
name: assembling-a-personal-devbox
description: >-
  Assemble a long-lived, owner-only development sandbox — a personal devbox — that suspends when
  idle and wakes on connect. Covers creating it (a managed-SSH profile, an attached workspace
  revision, `--no-idle-reclaim` or an idle timeout), connecting with `hiloop sandbox ssh`, using
  stock OpenSSH and rsync via `hiloop sandbox ssh-config print` / `install`, forwarding ports,
  keeping it owner-only with `hiloop sandbox access list` / `grant` / `revoke`, and the
  suspend-and-wake loop. Use when asked to set up a devbox, a persistent remote dev environment,
  SSH into a sandbox, or share one with a teammate.
metadata:
  version: 0.1.0
---

# Assembling a personal devbox

A personal devbox is an ordinary sandbox assembled deliberately: a durable workspace, an idle
timeout instead of a deadline, an access list that stays owner-only, and SSH as the front door.
There is no special sandbox kind — everything here composes the primitives from
`creating-sandboxes` and `persisting-and-branching-workspaces`.

What you get: the devbox suspends when you stop using it (its filesystem sealed exactly), and your
next `hiloop sandbox ssh` wakes it into the same workspace within seconds. Processes and memory do
not survive a suspend — durable state lives in the workspace.

## Prerequisites

- Signed in (`authenticating`), with a project selected.
- A **profile that carries managed SSH** — `hiloop sandbox ssh` needs it. Deployments with a devbox
  plan family let you pick durability by picking the plan (for example a *durable* plan on capacity
  that is never reclaimed, vs. a cheaper *spot* plan that relies on recovery after node
  reclamation). Ask your operator which profile names your deployment publishes.
- An exact `branchfs:v1` **workspace revision** to attach at create — a deployment-published base
  revision, or one you sealed earlier. Without one the devbox gets ephemeral scratch: its stop is
  destructive and it cannot wake (see `persisting-and-branching-workspaces`).

## Create the devbox

```sh
hiloop sandbox create \
  --name my-devbox \
  --profile <devbox-profile> \
  --cpus 16 --memory-mb 65536 \
  --network-mode sandbox \
  --egress-mode allow \
  --workspace-revision "$BASE_REVISION" \
  --workspace-target /workspace \
  --no-idle-reclaim \
  --wait
```

The choices that make it a devbox:

- `--workspace-revision` + `--workspace-target /workspace` attach the versioned workspace — what
  makes stop seal and resume restore.
- `--no-idle-reclaim` keeps it running until you stop it. Prefer `--idle-timeout 7200` instead when
  suspend-and-wake fits your workflow: the devbox suspends after two hours idle and the next
  connect wakes it in seconds. Either way, don't set `--max-runtime` — an actively used devbox may
  run indefinitely.
- `--network-mode sandbox` with `--egress-mode allow` gives the guest a managed network with
  outbound access for package installs and git clones.

## Connect

```sh
hiloop sandbox ssh my-devbox
```

The session runs through the signed session gateway with ephemeral credentials — no guest `sshd`,
no exposed port, no host key baked into the image. Remote commands go after `--`; pass a compound
command as one quoted argument:

```sh
hiloop sandbox ssh my-devbox -- 'cd /workspace/src && git status'
```

Forward a port to reach a dev server in the devbox from your browser (repeatable):

```sh
hiloop sandbox ssh my-devbox --local-forward 3000:3000
```

For a token-gated preview URL others can open without SSH, use `hiloop sandbox expose <sandbox>
<port>` (list active ones with `sandbox ports`, revoke with `sandbox unexpose`). A preview serves
the exposed port only — it does not wake a suspended devbox.

## Use stock OpenSSH and rsync

Print a one-sandbox OpenSSH config without touching your SSH configuration:

```sh
hiloop sandbox ssh-config print my-devbox > /tmp/hiloop-my-devbox.ssh
ssh -F /tmp/hiloop-my-devbox.ssh hiloop-my-devbox
```

The `Host` alias is the sandbox name prefixed `hiloop-`. Or install the stanza for normal OpenSSH,
rsync, and editor discovery (the first install asks before adding one managed `Include` to
`~/.ssh/config`; re-running refreshes it; `--remove` takes it back out):

```sh
hiloop sandbox ssh-config install my-devbox
ssh hiloop-my-devbox
rsync --archive ./src/ hiloop-my-devbox:/workspace/src/
rsync --archive hiloop-my-devbox:/workspace/src/ ./src/
```

Rsync must be installed locally and in the profile's image. Each connection is authorized
separately with short-lived keys held in memory by a local agent.

## Place state deliberately

The image root is read-only; everything outside the workspace is ephemeral.

- **Source trees and home state** live under `/workspace`. Keep dotfiles in a subtree such as
  `/workspace/home` so they share the workspace's versioning.
- **Caches and build outputs** are reconstructible — keeping them in the workspace is a size/speed
  trade-off you make explicitly.
- **Credentials never go in the workspace.** It is visible to every principal you grant access to
  and captured by every seal. Use the write-only secret store for service credentials
  (`managing-secrets`), and short-lived interactively-entered tokens for personal ones — never copy
  a long-lived private key in.

## Keep it yours

A sandbox starts owner-only. Every access write names the ACL revision it read, so a stale change
fails instead of overwriting a newer one — read the list first, then pass its revision:

```sh
hiloop sandbox access list my-devbox
hiloop sandbox access grant my-devbox --user ada --if-revision 0
hiloop sandbox access revoke my-devbox --user ada --if-revision 1
```

Principals are kinded — exactly one of `--user`, `--service-account`, or `--workload` per call.
Treat every grant as handing that principal your workspace contents.

## Suspend and wake

Let the idle timeout do the work. When the devbox suspends, the workspace is sealed; the first SSH
against a suspended devbox triggers the resume, waits for it, and runs — typically in seconds.
Concurrent connects join the same wake. Expect the exact filesystem back under a new runtime
generation, and expect every process from the previous generation to be gone: shells, servers,
multiplexer sessions.

```sh
hiloop sandbox ssh my-devbox -- 'cat /workspace/home/notes.md'
```

`hiloop sandbox stop` and `hiloop sandbox resume` remain available for explicit control, with the
same sealing semantics (`persisting-and-branching-workspaces`).
