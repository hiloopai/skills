---
name: launching-as-workloads
description: >-
  Launch hiloop runs and sandboxes as a workload — a named machine identity registered in your
  tenant — with `--as workload/<name>` on `hiloop run` and `hiloop sandbox create`. Covers
  `hiloop workloads create` (registration is always explicit — launching as an unregistered name
  is an error) / `list` / `show` (including the launch ACL) / `allow-launch` (open launching to
  every tenant member or restrict it to kinded principals — users by id and/or service-account
  keys such as a CI pipeline's; owner/admin only) / `delete` (owner/admin
  only; asks for confirmation unless `--yes`; live sandboxes conflict, past attribution keeps
  only the raw id). Use when work should be attributed to a service identity — a bot, a
  pipeline, a fleet role — rather than to whichever credential launched it, or when asked to
  control who may launch as one.
metadata:
  version: 0.5.0
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

Deleting is explicit too — an owner/admin action with a confirmation prompt. Pass `--yes` to skip
the prompt (required when stdin is not an interactive terminal, e.g. in a script):

```sh
hiloop workloads delete codex-runner --yes
```

Success prints `Deleted workload codex-runner.` (under `--output json`, the raw `{}` response).

A workload whose sandboxes are still running under its identity is a `conflict` (409) — stop them
first. Past runs keep only the workload's **raw id** in their attribution: once the name is gone
that id no longer resolves to a name, so still prefer long-lived role names (`codex-runner`) over
per-task throwaways, and delete only workloads whose history you no longer need to read by name.

## Launch as it

The launch verbs take the same flag (`hiloop run`, `hiloop sandbox create`, and the one-shot
`hiloop sandbox run`), and the value must be `workload/<name>` — a bare name is rejected
client-side:

```sh
hiloop run --as workload/codex-runner -- codex "fix the failing test"
hiloop sandbox create --profile gvisor-cpu --as workload/codex-runner --wait
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
    "created_at": "2026-07-11T01:39:15.922827+00:00",
    "created_by": "625121df-4564-40af-8934-112c8164516a",
    "description": "Codex fleet runner",
    "id": "47406778-b03b-463c-91e6-488bdc9fab9b",
    "launch_acl": {
      "launchers": [],
      "policy": "WORKLOAD_LAUNCH_POLICY_MEMBERS"
    },
    "name": "codex-runner",
    "updated_at": "2026-07-11T01:39:15.922827+00:00"
  }
}
```

`launch_acl.policy` is `WORKLOAD_LAUNCH_POLICY_MEMBERS` (any tenant member may launch — the default
for a new workload, `launchers` empty) or `WORKLOAD_LAUNCH_POLICY_RESTRICTED` (only the listed
`launchers`). Each launcher is a **kinded principal** — `{"kind": "user", "principal_id": "<user
id>"}` or `{"kind": "service_account", "principal_id": "<key id>"}`. The table view renders the
same as `LAUNCH members`, or `LAUNCH restricted (n)` plus a `LAUNCHERS` row of `kind:id` tokens
(e.g. `service_account:c3558c90-…`). Reading a name that isn't registered is `not_found` (404),
exit 1.

## Control who may launch as it

`allow-launch` **sets** the launch ACL — it is a PUT, so each call replaces the previous ACL, never
appends to it. It requires an owner or admin in the tenant. Either open it to all members, or
restrict it to named principals — tenant members by user id (`--user`) and/or service-account keys
by key id (`--service-account`, e.g. authorizing a CI pipeline's key to launch as the role):

```sh
# Restrict launching to a user and a CI service-account key (the list replaces the previous one).
hiloop workloads allow-launch codex-runner \
  --user 47a5bc34-c573-4c50-a8a9-392b76a59e5b \
  --service-account c3558c90-f175-4ac4-bc5c-8ba82028f2c6

# Reopen launching to every tenant member (the default for a new workload).
hiloop workloads allow-launch codex-runner --all-members
```

`--user` and `--service-account` are both repeatable and combine into one launcher list;
`--all-members` excludes both, and passing none of the three is an error (`pass --all-members to
open launching, or at least one --user or --service-account to restrict it`). A `--service-account`
id must be one of your tenant's service-account keys — anything else is rejected. The command
prints the updated workload — `--output json` returns the full record, e.g. `"launchers":
[{"kind": "service_account", "principal_id": "c3558c90-…"}]` — so the new ACL is confirmed in the
same call.

## The pattern

1. Register the role once: `hiloop workloads create <name> --description "…"`.
2. (Owner/admin) scope it: `allow-launch <name> --user … --service-account …` for a restricted
   role (members and/or CI keys), or leave a new workload open to all members.
3. Launch everything acting as that role with `--as workload/<name>` — `hiloop run`,
   `hiloop sandbox create`, and `hiloop sandbox run` all take it.
4. Read it back anytime: `hiloop workloads show <name>` for the ACL, `list` for the registry.
5. (Owner/admin) retire a role you no longer need: `hiloop workloads delete <name>` (confirms
   first; `--yes` to skip) — stop its sandboxes first (live ones are a `conflict`), and remember
   past runs keep only its raw id.
