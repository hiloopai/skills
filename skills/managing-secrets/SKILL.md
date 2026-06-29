---
name: managing-secrets
description: >-
  Give a hiloop sandbox a credential it can use but never see — a model-provider key, a third-party
  API token — via the secret broker. Covers `hiloop secret set` / `list` / `rotate` / `revoke`
  (write-only values bound to a destination host + header) and binding a secret into a run with
  `hiloop run --secret`. Use when an agent or sandbox needs to call an authenticated external API
  without the key landing in the agent's context, on disk, in the environment, or baked into a
  snapshot.
metadata:
  version: 0.1.0
---

# Managing sandbox secrets

A sandbox often needs a credential — an Anthropic/OpenAI key, a third-party API token — to do real
work. You do **not** want that key in the agent's context, in an env var the agent can echo, or baked
into a snapshot that every fork then inherits. hiloop solves this with a **secret broker**: you store
the value write-only and bind it to a destination; at request time the broker injects it into the
matching outbound request **at the edge**, so the agent uses the credential without ever seeing it.

> Tenant-scoped. Authenticate first (the `authenticating` skill). Secrets are tenant-scoped and
> resolved only by a project-bound key for their own tenant+project.

## Store a secret (write-only)

The value is **write-only** — supplied once, never returned. Prefer stdin so it stays out of your
shell history and the process list. Bind it to the host and header the proxy should inject it into:

```sh
echo "$ANTHROPIC_API_KEY" | hiloop secret set anthropic \
  --value-stdin \
  --kind bearer \
  --dest-host api.anthropic.com \
  --dest-header authorization \
  --scheme Bearer
```

- `--value-stdin` (preferred) reads one line from stdin; `--value <v>` passes it inline (lands in
  shell history — avoid).
- `--kind` shapes injection: `api-key`, `bearer`, `basic`, `custom`. `--dest-header` and `--scheme`
  default sensibly by kind (e.g. a `bearer` token → `authorization: Bearer …`), so you can often omit
  them.
- `--dest-host` is the outbound host the value is injected into. Only requests to that host get it.

## Use it in a run

Bind a stored secret into a captured run by name; the proxy resolves it from the broker on demand and
injects it into the matching request. The value is never written to disk, the environment, or a
snapshot:

```sh
hiloop run --secret anthropic -- claude -p "do the task"
```

`--secret` is repeatable — bind several. Inside the sandbox the agent just calls
`https://api.anthropic.com/…` with no key; the broker adds the `authorization` header in flight. This
is why a fork of the sandbox carries **no plaintext secret**: there was never one in the filesystem to
copy.

## Manage the lifecycle

```sh
hiloop secret list                       # metadata only — name, kind, destination; never the value
echo "$NEW_KEY" | hiloop secret rotate anthropic --value-stdin   # new value, stored as a new version
hiloop secret revoke anthropic           # a revoked secret resolves to nothing
```

## Never

- Print, log, echo, or commit a secret value, or pass it where it lands in shell history (prefer
  `--value-stdin` over `--value`).
- Bake a credential into a sandbox image or a snapshot — that's exactly what the broker exists to
  avoid. Store it as a secret and bind it with `hiloop run --secret`.
- Confuse this with your **hiloop** credential. `HILOOP_API_KEY` / `hiloop login` authenticate *you*
  to hiloop (the `authenticating` skill); a **secret** is a *third-party* credential a sandbox uses.
