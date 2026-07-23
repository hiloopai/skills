# Operating hiloop

hiloop runs AI agents in **isolated sandboxes** with **tree-native observability**. You boot
sandboxes from explicit, versioned environments, seal a sandbox's workspace into an immutable
revision and branch new sandboxes from it, and query what each run did — telemetry keyed by
position in the run-lineage tree.

This repository is a set of **Agent Skills** that teach you to operate hiloop. They follow the
open [Agent Skills standard](https://agentskills.io) and work across agent harnesses. Each skill is
self-contained; read the one that matches the task.

## The interface: the `hiloop` CLI

Drive hiloop through the `hiloop` CLI — it is the supported agent interface. It has dedicated command
groups for the common work — `hiloop sandbox` (lifecycle, exec, one-shot runs, SSH, access lists),
`hiloop secret`, `hiloop lease` (serialize concurrent orchestrators), `hiloop workloads` (named
machine identities to launch runs and sandboxes as), `hiloop runs` (list / tree / show / tail /
complete), `hiloop query` (read-only SQL over captured events and views), `hiloop annotations` /
`annotation-schema`, `hiloop data-views`, `hiloop run`, `hiloop login`, `hiloop skills` (install
this bundle) — and a generic authenticated passthrough for any route without one:

```sh
hiloop api <path> [-X get|post|put|delete] [-H 'header: value'] [-d '<json>'] [--output json]
```

Install (single static binary): `curl -fsSL https://hiloop.ai/install.sh | sh`, then `hiloop --version`.

There is no MCP server by design — a CLI the agent already knows how to drive costs far less context
than loading tool definitions every turn. The TypeScript (`@hiloopai/sdk`) and Python (`hiloop`) SDKs
exist for writing application code that runs *inside* a sandbox, not for operating the platform.

## Always, in order

1. **Authenticate and verify.** `hiloop login` is the default; use `HILOOP_API_KEY` only when headless
   / in CI. Then run `hiloop whoami` before anything else. → `authenticating`
2. **Select a project and tenant explicitly.** Runtime work is tenant-scoped, and project selection
   is explicit everywhere (`--project` > `HILOOP_PROJECT` > the context's project — no guessing).
3. **Select the environment explicitly.** Every sandbox create names exactly one `--profile` or
   `--image`; there is no default environment, and an environment the deployment doesn't advertise
   is rejected rather than substituted.
4. **Treat mutations as async.** Create/execute/stop/resume/delete return an **operation**; pass
   `--wait` or poll until it completes — never assume immediate completion. Refusals are real:
   treat a capability or workspace-continuity error as an answer, not something to fall back from
   silently.
5. **Idempotency keys are optional.** Create-style mutations (`sandbox create`, `sandbox run`,
   `sandbox exec`, `secret rotate`) accept an `--idempotency-key` — supply your own (and reuse it)
   to make a retry safe: a replay returns the original resource, the CLI retries ambiguous failures
   itself (up to 3 attempts), and the same key with a different request fails with
   `idempotency_conflict` (409). Omit it and every invocation is fresh. Delete and lifecycle ops
   need no key; they are idempotent by id.
6. **Clean up** sandboxes you created unless told to keep them.

## The skills

| Skill | Use it to |
|---|---|
| `autoresearch` | Run a metric-driven research loop: ideas, bounded arms, honest annotations, ensemble, leaderboard |
| `authenticating` | Sign in with `hiloop login` (or a key), verify identity, manage tenant scope and keys |
| `creating-sandboxes` | Create / inspect / delete sandboxes; profiles and images, resources, networking, lifetimes |
| `running-commands-in-a-sandbox` | Run commands (buffered `exec`, one-shot `sandbox run`, SSH); move files in/out |
| `persisting-and-branching-workspaces` | Seal a workspace into a revision on stop, resume it exactly, branch N sandboxes from one revision |
| `assembling-a-personal-devbox` | A long-lived owner-only devbox: managed SSH, ssh-config/rsync, access grants, suspend-and-wake |
| `managing-secrets` | Give a run a credential it uses but never sees (the secret broker) |
| `coordinating-with-leases` | Serialize concurrent agents with named, TTL-bounded leases (at most one live holder per name) |
| `launching-as-workloads` | Launch runs/sandboxes as a registered machine identity (a workload) and control who may launch as it |
| `querying-observability-trees` | Capture a run and query (SQL) / tail / diff its run-lineage telemetry |
| `annotating-runs` | Stamp structured judgments (outcome / score) you can filter and aggregate on |
| `reporting-product-bugs` | Report a hiloop bug (or send product feedback) to the hiloop team — never your task's results |

## Canonical end-to-end loop

```
login (or HILOOP_API_KEY) → whoami → (tenant switch) → create project →
create sandbox (--profile or --image, workspace attached) → poll ready → exec commands →
stop (seals the workspace revision) → create N sandboxes from that revision →
run divergent work (credentials via hiloop run --secret) → annotate outcomes →
query per lineage_path / diff two runs → delete sandboxes
```

## Secrets

Two distinct things. (1) Your **hiloop credential** — never print, log, or commit `HILOOP_API_KEY` or
any `hil_…` value; pass it through the environment or `hiloop login`. (2) A **third-party credential
your workload needs** (a model-provider key, an API token) — never bake it into a script, image,
environment, or workspace; store it with the secret broker and bind it with `hiloop run --secret` so
the agent uses it without seeing it. Sandbox-side bindings (`sandbox create --secret`) currently
**fail closed** — the platform never runs a sandbox silently unauthenticated. → `managing-secrets`

## More

Concepts and full references live at https://docs.hiloop.ai (`/llms.txt` for the machine index).
