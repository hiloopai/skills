---
name: assembling-a-personal-devbox
description: >-
  Assemble a long-lived development sandbox — a personal devbox — from the ordinary `hiloop sandbox`
  verbs: durable storage so `/workspace` survives a stop, managed SSH as the front door, `exec` for
  scripted work, and stop/start to park it. There is no `hiloop devbox` command; it was deleted.
  Covers getting code in and out over the session plane, and the limits that make this unlike a
  virtual machine. Use when asked to set up a devbox, a persistent remote dev environment, or to
  SSH into a sandbox.
metadata:
  version: 0.3.1
---

# Assembling a personal devbox

> **There is no `hiloop devbox` command.** The whole tree (`create`, `list`, `ssh`, `stop`,
> `delete`) was deleted — every verb was a client-side stub that refused before touching the
> network, and none of it is coming back. A devbox is not a product surface; it is a plain sandbox
> you keep around. If a `hiloop devbox …` invocation appears in an old script, replace it with the
> `hiloop sandbox` equivalent below rather than looking for a flag that revives it.

A personal devbox is an ordinary sandbox assembled deliberately: durable storage so your working
tree outlives a stop, no TTL so it lives until you delete it, and SSH as the front door. Everything
here composes primitives from `creating-sandboxes` and `running-commands-in-a-sandbox`.

> Authenticate first (`authenticating`), with a project selected.

## Create it once

```sh
hiloop sandbox create devbox --storage-class durable --cpus 4 --memory-mb 8192
```

Three choices make it a devbox:

- **`--storage-class durable`** mounts `/workspace` as storage with its own lifetime. Files written
  there survive a stop and survive losing the sandbox's node. Everything outside `/workspace` comes
  back from the image. This is the one flag you must not omit.
- **No `--ttl`.** An omitted TTL takes the deployment default, which on the hosted service is no
  expiry. Check the `expires` row of `hiloop sandbox get devbox` if your deployment sets one.
- **No `--image`.** The platform default image is a Debian base with Python, Node, `bash`, `tar`,
  and `curl`. Read the [image limits](#what-does-not-work-yet) before reaching for `--image`.

## Work in it

```sh
hiloop sandbox ssh devbox                                   # interactive shell
hiloop sandbox ssh devbox -- 'cd /workspace/api && cargo test'
hiloop sandbox ssh devbox -- -L 3000:127.0.0.1:3000 -N      # reach a dev server
hiloop sandbox exec devbox --timeout 600 -- bash -lc 'cd /workspace/api && cargo build'
```

`ssh` needs the sandbox SSH endpoint, which an operator enables per deployment and which is off by
default; where it is off, a connect is refused with `unsupported_capability`. `exec` needs no
session and is the right verb for scripted, non-interactive steps: it returns the command's real
exit code with stdout and stderr kept separate.

Both land in the same container and see the same filesystem, so a file written over SSH is visible
to the next `exec`.

## Get code and files in and out

There is **no `sandbox cp` today** — the verb was removed by the fabric cutover and has not been
rebuilt yet, so do not reach for it. Two paths exist meanwhile.

Prefer cloning into `/workspace` from inside the sandbox, over its own outbound network. For files
that only exist locally, pipe a tar archive through the shell. This needs nothing installed beyond
`tar`, which the default image has:

```sh
tar cf - myproject | hiloop sandbox ssh devbox -- 'tar xf - -C /workspace'
hiloop sandbox ssh devbox -- 'tar cf - -C /workspace myproject' | tar xf -
```

`scp` and `sftp` also work, and need nothing inside the sandbox: the sandbox serves the SFTP
subsystem itself, so they work against any image. `rsync` is different. It runs itself on both
ends, so it needs the `rsync` binary in the sandbox, and the default image does not carry one —
and anything a package manager installs lands outside `/workspace`, so an installed copy is gone
on the next stop.

None of them can call `hiloop sandbox ssh` directly, because the CLI requires a `--` separator
before the remote command. Use a shim on your `PATH`:

```sh
#!/bin/sh
# hiloop-ssh
box=$1
shift
exec hiloop sandbox ssh "$box" -- "$@"
```

```sh
rsync -av -e hiloop-ssh ./myproject/ devbox:/workspace/myproject/   # needs rsync in the sandbox too
```

For bulk, versioned data shared by many sandboxes the intended home is a volume
(`managing-volumes`). Volumes can be created, pushed, and read back today, but `--volume` at create
is still refused, so a volume is not yet a working ingress for a devbox.

## Place state deliberately

- **Source trees and dotfiles** go under `/workspace`. Nothing else survives a stop.
- **Package installs land outside `/workspace`** and are lost on the next start. Keep a setup script
  under `/workspace` and re-run it after a start.
- **Credentials never go on the disk.** Use the write-only secret store for service credentials
  (`managing-secrets`) and short-lived, interactively entered tokens for personal ones. Never copy
  a long-lived private key in.

## Park it and pick it up

```sh
hiloop sandbox stop devbox
hiloop sandbox start devbox
hiloop sandbox delete devbox      # permanent; releases the durable /workspace
```

## What does not work yet

State these plainly to the user rather than working around them.

- **A stop loses every process, not just the foreground shell.** Only `/workspace` survives. A
  running build, a dev server, a multiplexer session, and anything installed into the system
  directories are gone on the next start. You get files back, not a session. Do not promise resume.
- **A start can report `running` before the sandbox can serve.** `sandbox get` reads `running` while
  the first `exec` or `ssh` is still refused, sometimes for around two minutes, while the previous
  instance releases its storage. On a failure right after a start, wait and retry; do not conclude
  the sandbox is broken.
- **There is no development-shaped default image**, and bringing your own is not a reliable answer
  yet: a sandbox runs the image's own entrypoint, and an image whose entrypoint exits immediately —
  true of most base images — fails to materialize rather than idling. An image works here only if it
  keeps a process running.
- **`--volume` mounts are refused** with `unsupported_capability`.
- **`sandbox create --from <snapshot>` is refused**, so you cannot yet rebuild a configured devbox
  from a snapshot or branch one for an experiment. Taking the snapshot works; starting from it does
  not.

If one of these blocks real work, report it: `hiloop feedback "…" --surface sandbox`
(`reporting-product-bugs`). That is the signal that decides sequencing.
