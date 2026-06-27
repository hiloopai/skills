---
name: authenticating
description: >-
  Authenticate to hiloop from a terminal or headless agent so the hiloop CLI and API can be used.
  Covers the HILOOP_API_KEY environment variable (CI and headless agents), interactive `hiloop login`,
  verifying identity with `hiloop whoami`, and org-vs-tenant scope. Use this when a hiloop command
  returns 401 / unauthenticated, before the first hiloop call in a session, or when setting up
  credentials for an agent.
metadata:
  version: 0.1.0
---

# Authenticating to hiloop

hiloop authenticates every request with a bearer token at its edge. The token is **either** a
`hil_…` API key **or** a session token from `hiloop login` — the API accepts both. Pick the path that
matches who is running.

## Decide which path you are on

- **Headless agent / CI / no human present → use an API key in `HILOOP_API_KEY`.** This is the
  default for an agent operating hiloop. It needs no browser.
- **A human is at the terminal → `hiloop login`.** Caches a short-lived, auto-refreshed session in the
  OS keychain so no long-lived secret sits on disk.

The CLI resolves credentials in this order, first match wins: `--api-key` flag → `HILOOP_API_KEY`
env → cached `hiloop login` session. So an explicitly-set env var always overrides a cached login —
which is what you want in CI.

## Headless: API key

```sh
export HILOOP_API_KEY="hil_…"           # provided to the agent out-of-band; never print or commit it
# Optional: point at a non-default environment (default is https://api.hiloop.ai)
export HILOOP_API_URL="https://api.hiloop.ai"
```

Verify it resolves to an identity before doing anything else:

```sh
hiloop whoami
```

This calls `GET /v1/whoami` and prints the org, tenant, user, scope, and auth method the credential
maps to. **Always run `whoami` first** — it is the cheapest way to confirm auth and scope are correct
before a real operation. If it fails with 401/unauthenticated, the key is missing, malformed, or
revoked.

### Minting a scoped key

If you have an authenticated session and need a key for an agent to run with, mint one scoped
least-privilege and hand it over once (the secret is shown only at creation):

```sh
hiloop keys create --name "agent-ci" --kind service
hiloop keys list                         # metadata only; never reveals the secret
hiloop keys revoke <key-id>              # revoke when done
```

Prefer a **tenant-scoped** key for runtime/sandbox work. Treat a leaked key as compromised and revoke
it.

## Interactive: `hiloop login`

When a human is present:

```sh
hiloop login                 # opens a browser, approves locally (loopback)
hiloop login --device        # prints a URL + short code to approve on any device — use on a
                             # remote box or any machine with no local browser
```

`--device` is the right choice for an **agent running on a remote host**: the agent prints the
verification URL and code, a human approves out-of-band, and the CLI caches the session. After login,
`hiloop whoami` confirms who you are.

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
