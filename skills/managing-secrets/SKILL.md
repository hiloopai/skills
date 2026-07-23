---
name: managing-secrets
description: >-
  Give a hiloop run a credential it can use but never see — a model-provider key, a third-party API
  token — via the secret broker. Covers `hiloop secret set` / `list` / `rotate` / `revoke`
  (write-only values bound to a destination host + header) and binding a secret into a captured run
  with `hiloop run --secret`, plus why sandbox-side bindings currently fail closed. Use when an
  agent needs to call an authenticated external API without the key landing in the agent's context,
  on disk, or in the environment.
metadata:
  version: 0.3.0
---

# Managing secrets

An agent often needs a credential — an Anthropic/OpenAI key, a third-party API token — to do real
work. You do **not** want that key in the agent's context, in an env var the agent can echo, or on
disk where every process can read it. hiloop solves this with a **secret broker**: you store the
value write-only and bind it to a destination; at request time the value is injected into the
matching outbound request in flight, so the agent uses the credential without ever seeing it.

> Tenant-scoped. Authenticate first (the `authenticating` skill). Values are stored encrypted and
> never returned.

## Store a secret (write-only)

The value is **write-only** — supplied once, never echoed back. Prefer stdin so it stays out of
your shell history and the process list. Bind it to the host and header it should be injected
into:

```sh
echo "$ANTHROPIC_API_KEY" | hiloop secret set anthropic \
  --value-stdin \
  --kind bearer \
  --dest-host api.anthropic.com
```

- `--value-stdin` (preferred) reads one line from stdin; `--value <v>` passes it inline (lands in
  shell history — avoid).
- `--kind` shapes injection: `api-key` (default), `bearer`, `basic`, `custom`. `--dest-header` and
  `--scheme` default sensibly by kind (a `bearer` token → `authorization: Bearer …`), so you can
  usually omit them.
- `--dest-host` is the outbound host the value is injected into. Only requests to that host get it.

## Use it in a captured run

Bind a stored secret into a `hiloop run` by name; the wrapper resolves it from the broker on demand
and injects it into the matching outbound request per the stored destination binding. The value is
never written to disk, the environment, or the workspace:

```sh
hiloop run --secret anthropic -- claude -p "do the task"
```

`--secret` is repeatable — bind several. The wrapped agent just calls
`https://api.anthropic.com/…` with no key; the credential is added in flight. Secret bindings
require the transparent (netns) network-capture mode — on a host where its preflight fails, the
run fails before the child starts rather than running unauthenticated or leaking the value
(see `querying-observability-trees` for `--net-capture`).

## Sandbox bindings fail closed (for now)

`hiloop sandbox create --secret <name>` requests the same binding for a sandbox — but **current
production cells do not advertise native secret injection, so the create fails closed**. A
credential is never silently dropped while the sandbox runs unauthenticated, and there is no flag
that overrides it.

Do not work around this by placing a key in a sandbox's environment, image, command line, or
workspace — those paths expose plaintext to the agent and to process-inspection and logging
surfaces, and a workspace copy is captured by every seal. Until native injection ships, run
credentialed agent work under `hiloop run`, where the broker path above works today.

## Manage the lifecycle

```sh
hiloop secret list                       # metadata only — name, kind, destination; never the value
echo "$NEW_KEY" | hiloop secret rotate anthropic --value-stdin   # new value, stored as a new version
hiloop secret revoke anthropic           # a revoked secret resolves to nothing
```

`rotate` takes `--idempotency-key <key>` for safe retries: the same key and value returns the
original rotation instead of minting another version.

## Never

- Print, log, echo, or commit a secret value, or pass it where it lands in shell history (prefer
  `--value-stdin` over `--value`).
- Bake a credential into a sandbox image, environment, or workspace — that's exactly what the
  broker exists to avoid.
- Confuse this with your **hiloop** credential. `HILOOP_API_KEY` / `hiloop login` authenticate
  *you* to hiloop (the `authenticating` skill); a **secret** is a *third-party* credential your
  workload uses.
