# Operating hiloop

hiloop runs AI agents in **isolated, forkable sandboxes** with **tree-native observability**. You
snapshot a sandbox's state, fork it so several attempts diverge from an identical starting point, and
query what each branch did — telemetry keyed by position in the fork tree.

This repository is a set of **Agent Skills** that teach you to operate hiloop. They follow the
open [Agent Skills standard](https://agentskills.io) and work across agent harnesses. Each skill is
self-contained; read the one that matches the task.

## The interface: the `hiloop` CLI

Drive hiloop through the `hiloop` CLI — it is the supported agent interface. It has dedicated command
groups for the common work — `hiloop sandbox` (lifecycle, exec, fork, snapshot, interactive
executions), `hiloop secret`, `hiloop runs` (list / tree / show / tail), `hiloop query` (read-only
SQL over captured events and views), `hiloop annotate` / `annotation-schema`, `hiloop data-views`,
`hiloop run`, `hiloop login` — and a generic authenticated passthrough for any route without one:

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
2. **Be tenant-scoped for runtime work.** Sandboxes/snapshots/forks are tenant-scoped; switch into a
   tenant if `whoami` shows org scope.
3. **Treat mutations as async.** Create/execute/snapshot/fork return an **operation**; poll
   `GET /v1/operations/{id}` (or the resource) until ready — never assume immediate completion.
4. **Idempotency keys are optional.** Create-style mutations (create, execute, snapshot, restore,
   fork) accept an `idempotency-key` — supply your own (and reuse it) to make a retry safe, or omit it
   and the server generates one. Delete and lifecycle ops need no key; they are idempotent by id.
5. **Clean up** sandboxes you created unless told to keep them.

## The skills

| Skill | Use it to |
|---|---|
| `authenticating` | Sign in with `hiloop login` (or a key), verify identity, manage scope and keys |
| `creating-sandboxes` | Create / inspect / delete sandboxes; projects, bring-your-own images, resources, capabilities |
| `running-commands-in-a-sandbox` | Run commands (quick or interactive); stream + steer long jobs; move files in/out via artifacts |
| `snapshotting-and-forking` | Snapshot state and fork into divergent branches |
| `managing-secrets` | Give a sandbox a credential it uses but never sees (the secret broker) |
| `querying-observability-trees` | Capture a run and query (SQL) / tail / diff its fork-tree telemetry |
| `annotating-runs` | Stamp structured judgments (outcome / score) you can filter and aggregate on |
| `reporting-product-bugs` | Report a hiloop bug (or send product feedback) to the hiloop team — never your task's results |

## Canonical end-to-end loop

```
login (or HILOOP_API_KEY) → whoami → (tenant switch) → create project →
create sandbox → poll ready → run command → snapshot → fork into branches →
run divergent work (key via secret broker) → annotate outcomes →
query per lineage_path / branch-diff → delete sandbox
```

## Secrets

Two distinct things. (1) Your **hiloop credential** — never print, log, or commit `HILOOP_API_KEY` or
any `hil_…` value; pass it through the environment or `hiloop login`. (2) A **third-party credential a
sandbox needs** (a model-provider key, an API token) — never bake it into a script, image, or
snapshot; store it with the secret broker and bind it with `hiloop run --secret` so the agent uses it
without seeing it. → `managing-secrets`

## More

Concepts and full references live at https://docs.hiloop.ai (`/llms.txt` for the machine index).
