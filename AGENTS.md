# Operating hiloop

hiloop runs AI agents in **isolated sandboxes** with **tree-native observability**. You boot
sandboxes from an unmodified OCI image or from a snapshot, branch N sandboxes from one snapshot to
explore several paths from identical state, and query what each run did — telemetry keyed by
position in the run-lineage tree.

This repository is a set of **Agent Skills** that teach you to operate hiloop. They follow the
open [Agent Skills standard](https://agentskills.io) and work across agent harnesses. Each skill is
self-contained; read the one that matches the task.

## The interface: the `hiloop` CLI

> **Core sandbox lifecycle and buffered exec are served.** Optional storage, snapshot, session,
> volume, secret, capture, and GPU capabilities are admitted only when the deployment provides
> them; refusals are explicit and never silently degraded. The `operating-sandboxes` skill carries
> the current capability table and the conditional workflows.

Drive hiloop through the `hiloop` CLI — it is the supported agent interface. It has dedicated command
groups for the common work — `hiloop sandbox` (create / list / get / exec / ssh / cp / snapshot /
stop / start / delete), `hiloop volume` (publish and version data sandboxes mount), `hiloop secret`,
`hiloop workloads` (named machine identities to launch work as), `hiloop projects`, `hiloop runs`
(list / show / tail / complete), `hiloop query` (read-only SQL over captured events and views),
`hiloop events payload` (raw captured bodies), `hiloop annotations` / `annotation-schema`,
`hiloop data-views`, `hiloop usage`, `hiloop run`, `hiloop login` / `keys`, `hiloop skills`
(install this bundle) — and a generic authenticated passthrough for any route without one:

```sh
hiloop api <path> [-X get|post|put|delete] [-H 'header: value'] [-d '<json>'] [--output json]
```

Install (single static binary): `curl -fsSL https://hiloop.ai/install.sh | sh`, then `hiloop --version`.
An older installed CLI still carries retired verbs (`sandbox run`, `fork`, `access`, `expose`,
`port-forward`, `ssh-config`, `devbox`, `lease`, `tenant`) that no longer exist and that no
deployment serves. Upgrade with `hiloop upgrade` rather than reaching for them, and re-install the
skills (`hiloop skills install`) so the guidance matches the binary.

There is no MCP server by design — a CLI the agent already knows how to drive costs far less context
than loading tool definitions every turn. The TypeScript (`@hiloopai/sdk`) and Python (`hiloop`) SDKs
exist for writing application code that runs *inside* a sandbox, not for operating the platform.

## Always, in order

1. **Point the CLI at a deployment, authenticate, and verify.** The built-in default edge is not
   live — save a context (`hiloop config set-context`) or set `HILOOP_API_URL`. `hiloop login` is the
   default; use `HILOOP_API_KEY` only when headless / in CI. Then run `hiloop whoami` before anything
   else. → `authenticating`
2. **Select a project explicitly.** Project selection never guesses: `--project` where the command
   takes it (`run`, `runs list`, `query`, `volume …`, `annotations …`), otherwise `HILOOP_PROJECT` >
   the active context's project. The `sandbox` verbs have no `--project` flag — set the environment
   variable or the context. Tenant scope is implied by your credential; there is no tenant-switching
   command.
3. **Name the environment explicitly.** A sandbox create takes at most one of `--image` (an
   unmodified OCI image, digest-pinned in production) or `--from <snapshot>`; omitting both boots the
   platform default image, which is a convenience, not an environment identity. Size it with
   `--cpus` / `--memory-mb`, each defaulting to the deployment's own default.
4. **Create blocks; refusals are answers.** `sandbox create` runs until the sandbox is running or
   reaches a terminal state — there is no operation to poll and no `--wait`. When a command refuses
   (a capability error, a fail-closed secret binding), treat it as the answer, not as something to
   silently fall back from.
5. **Idempotency keys are optional.** Create-style mutations (`sandbox create`, `sandbox exec`,
   `sandbox snapshot create`, `secret rotate`) accept an `--idempotency-key` — supply your own (and
   reuse it) to make a retry safe: a replay returns the original resource, the CLI retries ambiguous
   failures itself (up to 3 attempts), and the same key with a different request fails with
   `idempotency_conflict` (409). Omit it and every invocation is fresh. Delete and lifecycle ops
   need no key; they are idempotent by id.
6. **Clean up** sandboxes you created unless told to keep them.

## The skills

| Skill | Use it to |
|---|---|
| `autoresearch` | Run a metric-driven research loop: ideas, bounded arms, honest annotations, ensemble, leaderboard |
| `authenticating` | Point the CLI at a deployment, sign in with `hiloop login` (or a key), verify identity, mint keys |
| `operating-sandboxes` | Create, inspect, exec, stop, start, and delete sandboxes; load SSH, file-transfer, snapshot, branch, or devbox details only when needed |
| `managing-volumes` | Publish and version large data once, mount it into many sandboxes |
| `managing-secrets` | Give a run a credential it uses but never sees (the secret broker) |
| `launching-as-workloads` | Launch a run as a registered machine identity (a workload) and control who may launch as it |
| `querying-observability-trees` | Capture a run and query (SQL) / tail / diff its run-lineage telemetry |
| `annotating-runs` | Stamp structured judgments (outcome / score) you can filter and aggregate on |
| `reporting-product-bugs` | Report a hiloop bug (or send product feedback) to the hiloop team — never your task's results |

## Canonical end-to-end loop

```
configure the edge → login (or HILOOP_API_KEY) → whoami → create project →
create sandbox → exec commands → [snapshot + branch when the deployment supports it] →
run credentialed local work with hiloop run --secret → annotate outcomes →
query the runs → delete sandboxes
```

## Secrets

Two distinct things. (1) Your **hiloop credential** — never print, log, or commit `HILOOP_API_KEY` or
any `hil_…` value; pass it through the environment or `hiloop login`. (2) A **third-party credential
your workload needs** (a model-provider key, an API token) — never bake it into a script, image,
environment, or a sandbox's disk; store it with the secret broker and bind it with
`hiloop run --secret` so the agent uses it without seeing it. Sandbox-side bindings
(`sandbox create --secret`) **fail closed** — the platform never runs a sandbox silently
unauthenticated, and there is no flag that overrides that. → `managing-secrets`

## More

Concepts and full references live at https://docs.hiloop.ai (`/llms.txt` for the machine index).
