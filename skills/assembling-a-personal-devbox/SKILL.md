---
name: assembling-a-personal-devbox
description: >-
  Assemble a long-lived development sandbox — a personal devbox — that persists across stops and is
  reached over managed SSH. NOTE: every `hiloop devbox` command currently refuses to run while the
  sandbox runtime is rebuilt; this skill documents the shape it returns to and what you can do
  meanwhile. Use when asked to set up a devbox, a persistent remote dev environment, or to
  SSH into a sandbox.
metadata:
  version: 0.2.0
---

# Assembling a personal devbox

> **Status: `hiloop devbox` is switched off.** Every subcommand (`create`, `list`, `ssh`, `stop`,
> `delete`) parses its arguments and then refuses, with exactly this message:
>
> ```
> sandbox fabric is being rebuilt — devbox commands return in the next release
> ```
>
> This is a hard client-side bail — there is no flag, environment variable, or API path that works
> around it. Do not try. The generic `hiloop sandbox` verbs are also not yet served by the API edge
> (see `creating-sandboxes`), so there is currently **no working path to a hosted devbox**. Read the
> rest of this skill as the shape the surface returns to; verify the flags against
> `hiloop devbox create --help` when it comes back, because the previous flag set did not survive
> the rebuild intact.

A personal devbox is a long-lived sandbox assembled deliberately: durable storage, an idle timeout
instead of a hard deadline, and SSH as the front door. Processes and memory do not survive a
suspend — durable state lives on disk.

## What you can do meanwhile

- **Local agent work is unaffected.** `hiloop run` captures an agent running on your own machine,
  with full telemetry, annotations, and secret binding. See `querying-observability-trees` and
  `managing-secrets`.
- **Report it if it blocks you.** `hiloop feedback "…" --surface sandbox` (see
  `reporting-product-bugs`) — that is the signal that decides sequencing.
- **Do not** hand-roll a substitute by putting credentials into some other remote host to imitate a
  devbox. The secret-handling rules below apply everywhere.

## The intended shape (returns after the rebuild)

`hiloop devbox create [name]` takes its own flag set, separate from `hiloop sandbox create`:
`--image` xor `--profile`, `--cpus`, `--memory-mb`, `--disk-mb`, `--gpus` / `--gpu-model`, `--arch`,
`--capture`, `--network-mode`, `--egress-mode`, `--max-runtime`, `--idle-timeout` xor
`--no-idle-reclaim`, `--as workload/<name>`, and `--secret`. Omitting both image and profile selects
a `devbox-cpu-durable` default.

**Treat that list as provisional.** It is what the CLI's argument parser still declares, but the
runtime underneath it was deleted and rebuilt, and several neighbouring flag sets (notably on
`hiloop sandbox create`) were cut down substantially in the same rebuild. Re-read `--help` before
relying on any of it.

The choices that make a sandbox a devbox:

- **Durable storage**, so a stop is not destructive.
- **`--no-idle-reclaim`** to keep it running until you stop it, or **`--idle-timeout 7200`** if
  suspend-and-wake fits your workflow. Don't set `--max-runtime` on a devbox — an actively used one
  should be able to run indefinitely.
- **Managed network with egress allowed**, for package installs and git clones.

### Verbs that are gone for good

The previous devbox workflow leaned on verbs that **were removed and are not coming back**:
`hiloop sandbox ssh-config print` / `install`, `hiloop sandbox access list` / `grant` / `revoke`,
`hiloop sandbox expose` / `unexpose` / `ports`, `hiloop sandbox port-forward`, and
`--workspace-revision` / `--workspace-target`. Preview URLs and HTTP exposure are a later phase.
Sharing a devbox with a teammate has no supported command today.

Port forwarding survives, but through stock OpenSSH rather than a hiloop flag: everything after `--`
on `hiloop sandbox ssh` is passed straight to `ssh`, so use `-L 3000:localhost:3000`. Likewise file
transfer is rsync/scp over that same managed-SSH path, not a `cp` verb.

## Place state deliberately

- **Source trees and home state** go on the durable disk. Keep dotfiles in a subtree so they share
  its lifecycle.
- **Caches and build outputs** are reconstructible — keeping them is an explicit size/speed
  trade-off.
- **Credentials never go on the devbox disk.** It is captured by every snapshot and visible to
  anyone you share the box with. Use the write-only secret store for service credentials
  (`managing-secrets`) and short-lived interactively-entered tokens for personal ones. Never copy a
  long-lived private key in.

## Suspend and wake

The intended loop: the devbox suspends when idle, and the next connect wakes it into the same
filesystem within seconds. Expect the exact disk back under a **new runtime generation**, and expect
every process from the previous generation to be gone — shells, servers, multiplexer sessions.
Anything you want to survive must be a file.
