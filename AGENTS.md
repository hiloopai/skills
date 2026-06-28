# Operating hiloop

hiloop runs AI agents in **isolated, forkable sandboxes** with **tree-native observability**. You
snapshot a sandbox's state, fork it so several attempts diverge from an identical starting point, and
query what each branch did — telemetry keyed by position in the fork tree.

This repository is a set of **Agent Skills** that teach you to operate hiloop. They follow the
open [Agent Skills standard](https://agentskills.io) and work across agent harnesses. Each skill is
self-contained; read the one that matches the task.

## The interface: the `hiloop` CLI

Drive hiloop through the `hiloop` CLI — it is the supported agent interface. The CLI wraps a typed
control-plane API; for any route without a dedicated subcommand, use the generic authenticated
passthrough:

```sh
hiloop api <path> [-X get|post|put|delete] [-H 'header: value'] [-d '<json>'] [--output json]
```

Install (single static binary): `curl -fsSL https://hiloop.ai/install.sh | sh`, then `hiloop --version`.

There is no MCP server by design — a CLI the agent already knows how to drive costs far less context
than loading tool definitions every turn. The TypeScript (`@hiloopai/sdk`) and Python (`hiloop`) SDKs
exist for writing application code that runs *inside* a sandbox, not for operating the platform.

## Always, in order

1. **Authenticate and verify.** Set `HILOOP_API_KEY` (headless) or `hiloop login` (interactive), then
   run `hiloop whoami` before anything else. → `authenticating`
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
| `authenticating` | Set up credentials, verify identity, manage scope and keys |
| `creating-sandboxes` | Create / inspect / delete sandboxes; projects, bring-your-own images, resources, capabilities |
| `running-commands-in-a-sandbox` | Run commands (quick or interactive); stream + steer long jobs; move files in/out via artifacts |
| `snapshotting-and-forking` | Snapshot state and fork into divergent branches |
| `querying-observability-trees` | Capture a run and query/diff its fork-tree telemetry |

## Canonical end-to-end loop

```
whoami → (tenant switch) → create project → create sandbox → poll ready →
execute command → snapshot → fork into branches → run divergent work →
query per fork_path / branch-diff → delete sandbox
```

## Secrets

Never print, log, or commit `HILOOP_API_KEY` or any `hil_…` value. Pass credentials through the
environment; never bake them into a script or sandbox image.

## More

Concepts and full references live at https://docs.hiloop.ai (`/llms.txt` for the machine index).
