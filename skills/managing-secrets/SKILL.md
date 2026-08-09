---
name: managing-secrets
description: >-
  Manage a third-party credential in hiloop's write-only secret store. Covers `hiloop secret set` /
  `list` / `rotate` / `revoke`, piped-stdin-only values, destination metadata, the absence of local
  run delivery, and why `hiloop sandbox create --secret NAME` fails closed until proof-bound
  request-time delivery ships. Use when an agent needs to register, inspect, rotate, revoke, or plan
  delivery of a model-provider key or external API token without exposing its value.
---

# Managing secrets

An agent often needs a credential — an OpenAI key, a third-party API token — to do real
work. You do **not** want that key in the agent's context, in an env var the agent can echo, or on
disk where every process can read it. hiloop currently provides write-only encrypted custody and
lifecycle management. It does **not** currently deliver a stored value to a local run or sandbox.

> Org-scoped. Authenticate first (the `authenticating` skill). Values are stored encrypted and
> never returned.

## Store a secret (write-only)

The value is **write-only** — supplied once, never echoed back. Piped stdin is the only value
channel, keeping it out of hiloop's argv and your shell history:

```sh
# Run in a trusted operator shell with tracing disabled.
printf '%s' "$OPENAI_API_KEY" | hiloop secret set openai \
  --value-stdin \
  --kind bearer \
  --dest-host api.openai.com
```

- `--value-stdin` requires non-terminal stdin containing exactly one non-empty line of at most 4096
  bytes. One final LF or CRLF is removed; other whitespace is preserved.
- If an agent performs the transfer, pipe directly from the existing secret store into hiloop.
  Never copy the value into agent context or print it between stores.
- `--kind`, `--dest-host`, `--dest-header`, and `--scheme` are stored metadata today. They do not
  authorize or inject a request yet.
- Use `bearer` plus the exact intended public HTTPS host for the planned first delivery slice. That
  slice will overwrite `Authorization: Bearer <value>` only after a live proof-bound request is
  authorized outside the sandbox.

## Delivery is fail-closed today

Local `hiloop run` has no secret-binding option. Storing destination metadata does not make a local
run credentialed.

`hiloop sandbox create --secret <name>` accepts a name-only binding request, but admission refuses
it with `unsupported_capability` until proof-bound request-time delivery is deployed. The sandbox is
never silently created without the requested credential, and there is no fallback that places a raw
provider key in guest environment, argv, exec input, files, images, snapshots, or workspaces.

## Manage the lifecycle

```sh
hiloop secret list                       # metadata only — name, kind, destination; never the value
printf '%s' "$NEW_KEY" | hiloop secret rotate openai --value-stdin
hiloop secret revoke openai              # a revoked secret resolves to nothing
```

`rotate` takes `--idempotency-key <key>` for safe retries: the same key and value returns the
original rotation instead of minting another version; reusing the key with a different value is
rejected.

## Never

- Print, log, echo, or commit a secret value. Pipe it only through `--value-stdin`.
- Put a provider credential in a sandbox environment, exec request, file, image, snapshot, or
  durable workspace. A refused binding is the final answer until proof-bound delivery ships.
- Confuse this with your **hiloop** credential. `HILOOP_API_KEY` / `hiloop login` authenticate
  *you* to hiloop (the `authenticating` skill); a **secret** is a *third-party* credential your
  workload uses.
