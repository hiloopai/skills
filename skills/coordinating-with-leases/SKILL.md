---
name: coordinating-with-leases
description: >-
  Coordinate concurrent agents and orchestrators with hiloop leases — named, TTL-bounded,
  project-scoped mutual-exclusion claims (at most one live holder per `<project>/<name>`). Covers
  `hiloop lease acquire` (an atomic compare-and-set that exits 1 while a live holder exists) /
  `renew` / `release`, the acquire→work→renew→release loop, and branching on contention in scripts.
  Use when asked to take a lock, claim a job or resource, serialize concurrent work, elect a
  leader, or keep two agents from doing the same thing at once.
metadata:
  version: 0.1.0
---

# Coordinating with leases

A **lease** is a named, TTL-bounded mutual-exclusion claim scoped to a project: at most one live
holder per `<project>/<name>` at a time. Use one to serialize concurrent orchestrators — agents
that would otherwise run the same job try to acquire the same lease name, and only one proceeds. An
unrenewed lease expires on its own, so a crashed holder never wedges the name, and every
acquire/renew/release transition is recorded as a queryable telemetry event (see
`querying-observability-trees`).

## Acquire

`acquire` takes the lease target **positionally as `<project>/<name>`** — the project (slug or id),
a `/`, then the lease name — unlike the sibling commands' `--project` flag. `--ttl` (seconds, 1 to
86400) is required:

```sh
hiloop lease acquire default/nightly-sync --ttl 300
```

Acquisition is an **atomic compare-and-set**: it succeeds when the name is free (or the previous
holder's TTL has lapsed) and prints the **lease id** — the handle `renew` and `release` take.
While a live holder exists it **exits 1** with error code `lease_held` (409), so a contention loop
branches on the exit code:

```sh
if hiloop lease acquire default/nightly-sync --ttl 300; then
  # you hold the lease: do the work, then release
else
  # exit 1 → another holder is live (lease_held): skip, back off, or wait for its TTL
fi
```

`--output json` prints the full lease record on success (`lease.id`, `holder`, `expiresAt`) and a
structured `{"error": {"code": "lease_held", …}}` envelope on contention.

## Hold it: renew before the TTL lapses

Work that outlives one TTL must renew — `renew` resets the expiry to now + `--ttl`. Renew at a
comfortable margin before expiry (e.g. every TTL/2):

```sh
hiloop lease renew <lease-id> --ttl 300
```

A lease whose TTL already lapsed **cannot be renewed** — renew fails with `lease_expired`, and the
name is up for grabs. Treat that as having lost the lease: stop the guarded work and `acquire`
again rather than carrying on unprotected.

## Release

Release when the work is done — it frees the name immediately instead of leaving the next acquirer
waiting out your TTL:

```sh
hiloop lease release <lease-id>
```

Releasing an already-lapsed lease reports `lease_expired` (it ended on its own), and an id that no
longer names a live lease is `not_found` — either way the claim is gone, so neither needs handling
in a cleanup path.

## The pattern: acquire → work → renew → release

1. `acquire <project>/<name> --ttl <secs>` — exit 1 means someone else holds it: skip or back off.
2. Do the guarded work, renewing on an interval comfortably shorter than the TTL.
3. `release` the lease id the moment the work completes.

Size the TTL to survive expected pauses in the holder (long tool calls, slow steps) but short
enough that a crashed holder frees the name quickly — then let expiry be the crash recovery and
`release` the happy path.
