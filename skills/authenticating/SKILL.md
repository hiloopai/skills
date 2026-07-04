---
name: authenticating
description: >-
  Authenticate to hiloop from a terminal or headless agent so the hiloop CLI and API can be used.
  Covers `hiloop login` (the default — a browser or device flow), the HILOOP_API_KEY environment
  variable for CI and headless agents, verifying identity with `hiloop whoami`, and org-vs-tenant
  scope. Use this when a hiloop command returns 401 / unauthenticated, before the first hiloop call
  in a session, or when setting up credentials for an agent.
metadata:
  version: 0.1.0
---

# Authenticating to hiloop

hiloop authenticates every request with a bearer token at its edge. The token is **either** a session
from `hiloop login` **or** a `hil_…` API key — the API accepts both. `hiloop login` is the default;
reach for an API key when no human is present.

The CLI resolves credentials in this order, first match wins: `--api-key` flag → `HILOOP_API_KEY`
env → cached `hiloop login` session. So an explicitly-set env var always overrides a cached login —
which is what you want in CI.

## Default: `hiloop login`

```sh
hiloop login                 # opens a browser, approves locally (loopback) — the default
hiloop login --device        # prints a URL + short code to approve on any device — use on a
                             # remote box or any machine with no local browser
```

`hiloop login` caches a short-lived, auto-refreshed session in the OS keychain, so **no long-lived
secret sits on disk**. The browser (loopback) flow is the default when a local browser is available.

`--device` is the right choice for an **agent running on a remote host**: the agent prints the
verification URL and code, a human approves out-of-band, and the CLI caches the session. After login,
`hiloop whoami` confirms who you are.

> Already have a dashboard key and want it stored once? `hiloop login --with-key` reads a key from
> stdin (`echo "$KEY" | hiloop login`), verifies it, and stores it — the scriptable variant of login.

## Headless / CI: `HILOOP_API_KEY`

When **no human is present** (CI, a fully unattended agent), skip the browser and pass a key in the
environment:

```sh
export HILOOP_API_KEY="hil_…"           # provided to the agent out-of-band; never print or commit it
# Optional: point at a non-default environment (default is https://api.hiloop.ai)
export HILOOP_API_URL="https://api.hiloop.ai"
```

## Verify first: `hiloop whoami`

Whichever path you took, confirm it resolves to an identity before doing anything else:

```sh
hiloop whoami
```

This calls `GET /v1/whoami` and prints the identity the credential resolves to: the **principal** —
its `kind` (`user` or `service_account`), id, and the API key's id and name (`email` too for a user
key) — and the **tenant** (id + slug). `--output json` prints exactly
`{"principal": {…}, "tenant": {…}}`. **Always run `whoami` first** — it is the cheapest way to
confirm auth and scope are correct before a real operation. If it fails with 401/unauthenticated,
the credential is missing, malformed, expired, or revoked.

## Minting a scoped key

If you have an authenticated session and need a key for an unattended agent to run with, mint one
scoped least-privilege and hand it over once (the secret is shown only at creation). The key's
**name is its identity everywhere**: it is what `whoami` reports as `key_name` and what the
`PRINCIPAL` column of `hiloop runs list` / `tree` / `show` renders for everything the key writes —
so name keys for who acts with them (`laptop`, `ci-bot`):

```sh
hiloop keys create --name agent-ci               # acts as the tenant (--kind service_account, the default)
hiloop keys create --name laptop --kind user     # acts on behalf of you
hiloop keys list                                 # metadata only; never reveals the secret
hiloop keys revoke <key-id>                      # revoke when done
```

Prefer a **tenant-scoped** key for runtime/sandbox work. Treat a leaked key as compromised and revoke
it. (For credentials a *sandbox* uses but the agent must never see — e.g. a model provider key — use
the secret broker instead: the `managing-secrets` skill.)

## Scope: org vs tenant

A login lands at **org scope** (manage the org, tenants, members, org keys). Runtime work —
sandboxes, executions, snapshots, forks — is **tenant-scoped**. Enter a tenant before sandbox work:

```sh
hiloop whoami                # check the current scope
hiloop tenant switch <tenant-id>   # re-scope the session to a tenant
```

If a sandbox call returns `403 NotOrgScoped` or a scope error, you are at the wrong scope — switch
into the tenant and retry.

## Never

- Print, log, echo, or commit `HILOOP_API_KEY` or any `hil_…` value.
- Hardcode a key into a script or a sandbox image — pass it through the environment.
