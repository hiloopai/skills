---
name: launching-as-workloads
description: >-
  Launch hiloop runs and sandboxes as a workload — a named machine identity registered in your
  tenant — with `--as workload/<name>` on `hiloop run` and `hiloop sandbox create`. Covers
  `hiloop workloads create` (registration is always explicit — launching as an unregistered name
  is an error) / `list` / `show` (including the launch ACL) / `allow-launch` (open launching to
  every tenant member or restrict it to listed users; owner/admin only). Use when work should be
  attributed to a service identity — a bot, a pipeline, a fleet role — rather than to whichever
  credential launched it, or when asked to control who may launch as one.
metadata:
  version: 0.1.0
---

# Launching as workloads

A **workload** is a named machine identity registered in your tenant that a run or sandbox can be
launched **as** — `codex-runner`, `nightly-sync`, `eval-fleet` — so the work is attributed to the
role that did it, not just to whichever credential happened to launch it. Each workload carries a
**launch ACL** saying who may launch as it. The executing identity is always **declared, never
inferred**: omit `--as` and you run as your own identity; pass `--as workload/<name>` and the
control plane checks the name against the registry before the launch proceeds.

> Tenant-scoped. Authenticate first (the `authenticating` skill); workloads live in your tenant and
> their names are unique within it.

## Register a workload (explicit, fail-closed)

Registration is always explicit — launching as an unregistered name is an error, never an implicit
registration:

```sh
hiloop workloads create codex-runner --description "Codex fleet runner"
```

Names must be lowercase letters, digits, `.`, `_` or `-`, starting and ending with a letter or
digit — anything else is rejected with `invalid_argument` (400), and re-registering an existing
name is `already_exists` (409). A new workload starts **open to launch by any tenant member**.

Registration is durable: the current surface has no delete/unregister verb, so name workloads as
long-lived roles (`codex-runner`), not per-task throwaways.

## Launch as it

Both launch verbs take the same flag, and the value must be `workload/<name>` — a bare name is
rejected client-side:

```sh
hiloop run --as workload/codex-runner -- codex "fix the failing test"
hiloop sandbox create --as workload/codex-runner --wait
```

The work is then attributed to that workload; you must hold launch rights on it. On a sandbox,
`--as` also applies any identity-bound egress policy for the workload.

An unregistered name **fails closed** at registration time — the run/sandbox is never created:

```
error: registering the run with the control plane: not_found (404): no workload named "nightly-sync" is registered
```

The command exits 1; under `--output json` (on `hiloop sandbox create`) the same failure is a
structured envelope on stderr: `{"error":{"code":"not_found","message":"…"}}`. Register the name
first — that is the fix, there is no flag that launches as an unregistered identity.

## Inspect

```sh
hiloop workloads list
hiloop workloads show codex-runner --output json
```

`list` renders one line per workload (`NAME`, `ID`, `LAUNCH`, `CREATED`); `show` includes who may
launch as it:

```json
{
  "workload": {
    "id": "47406778-b03b-463c-91e6-488bdc9fab9b",
    "name": "codex-runner",
    "description": "Codex fleet runner",
    "launchAcl": {
      "policy": "WORKLOAD_LAUNCH_POLICY_MEMBERS",
      "userIds": []
    },
    "createdBy": "625121df-4564-40af-8934-112c8164516a",
    "createdAt": "2026-07-11T01:39:15.922827+00:00",
    "updatedAt": "2026-07-11T01:39:15.922827+00:00"
  }
}
```

`launchAcl.policy` is `WORKLOAD_LAUNCH_POLICY_MEMBERS` (any tenant member may launch — the default
for a new workload, `userIds` empty) or `WORKLOAD_LAUNCH_POLICY_RESTRICTED` (only the listed
`userIds`). The table view renders the same as `LAUNCH members`, or `LAUNCH restricted (n)` plus a
`LAUNCHERS` row. Reading a name that isn't registered is `not_found` (404), exit 1.

## Control who may launch as it

`allow-launch` **sets** the launch ACL — it is a PUT, so each call replaces the previous ACL, never
appends to it. It requires an owner or admin in the tenant. Pass exactly one mode:

```sh
# Restrict launching to the listed users (repeat --user; the list replaces the previous one).
hiloop workloads allow-launch codex-runner --user 47a5bc34-c573-4c50-a8a9-392b76a59e5b

# Reopen launching to every tenant member (the default for a new workload).
hiloop workloads allow-launch codex-runner --all-members
```

`--all-members` and `--user` are mutually exclusive, and passing neither is an error (`pass
--all-members to open launching, or at least one --user to restrict it`). `--user` takes a user id
and is repeatable. The command prints the updated workload — `--output json` returns the full
record — so the new ACL is confirmed in the same call.

## The pattern

1. Register the role once: `hiloop workloads create <name> --description "…"`.
2. (Owner/admin) scope it: `allow-launch <name> --user …` for a restricted role, or leave a new
   workload open to all members.
3. Launch everything acting as that role with `--as workload/<name>` — `hiloop run` and
   `hiloop sandbox create` both take it.
4. Read it back anytime: `hiloop workloads show <name>` for the ACL, `list` for the registry.
