# hiloop skills

Open-source [Agent Skills](https://agentskills.io) that teach AI coding agents to operate
**[hiloop](https://hiloop.ai)** — isolated agent sandboxes with branchable, versioned workspaces
and tree-native observability.

The skills follow the open Agent Skills standard, so they work across harnesses (Claude Code, Cursor,
Codex, and others). They drive hiloop through the `hiloop` **CLI** — the supported agent interface —
not an MCP server: a CLI the agent already knows how to drive costs far less context than loading tool
definitions every turn.

## What's here

| Skill | Use it to |
|---|---|
| [`authenticating`](skills/authenticating/SKILL.md) | Sign in with `hiloop login` (or a key), verify identity, manage tenant scope and keys |
| [`creating-sandboxes`](skills/creating-sandboxes/SKILL.md) | Create / inspect / delete sandboxes; pick a profile or image, request resources |
| [`running-commands-in-a-sandbox`](skills/running-commands-in-a-sandbox/SKILL.md) | Run commands (buffered, one-shot, or over SSH); move files in/out |
| [`persisting-and-branching-workspaces`](skills/persisting-and-branching-workspaces/SKILL.md) | Seal a workspace into a revision on stop, resume it exactly, branch N sandboxes from one revision |
| [`assembling-a-personal-devbox`](skills/assembling-a-personal-devbox/SKILL.md) | A long-lived, owner-only devbox: managed SSH, rsync, access grants, suspend-and-wake |
| [`managing-secrets`](skills/managing-secrets/SKILL.md) | Give a run a credential it uses but never sees (the secret broker) |
| [`coordinating-with-leases`](skills/coordinating-with-leases/SKILL.md) | Serialize concurrent agents with named, TTL-bounded leases (at most one live holder per name) |
| [`launching-as-workloads`](skills/launching-as-workloads/SKILL.md) | Launch runs/sandboxes as a registered machine identity (a workload) and control who may launch as it |
| [`querying-observability-trees`](skills/querying-observability-trees/SKILL.md) | Capture a run and query (SQL) / tail / diff its run-lineage telemetry |
| [`annotating-runs`](skills/annotating-runs/SKILL.md) | Stamp structured judgments (outcome / score) you can filter and aggregate on |
| [`reporting-product-bugs`](skills/reporting-product-bugs/SKILL.md) | Report a hiloop bug (or send product feedback) to the hiloop team with `hiloop feedback` |

[`AGENTS.md`](AGENTS.md) is the whole-product orientation an agent reads first.

## Quickstart

**1. Install the CLI** (single static binary):

```sh
curl -fsSL https://hiloop.ai/install.sh | sh
hiloop --version
```

**2. Authenticate** — `hiloop login` is the default (`--device` on a remote box with no local browser):

```sh
hiloop login
hiloop whoami
```

…or headless (an agent / CI), skip the browser with a key: `export HILOOP_API_KEY="hil_…"`.

**3. Install the skills.** Choose your harness, or install every supported target:

```sh
hiloop skills install claude-code  # cursor | codex | gemini | copilot
hiloop skills install all
```

`copilot` installs into the current repository; the other targets install for your user. Full target
paths, native alternatives, and unsupported-harness fallback instructions are in
[`SETUP.md`](SETUP.md).

Then ask your agent to spin up a hiloop sandbox, run work in it, and query the trace tree — the
skills guide the rest.

## Develop

These skills mirror the `hiloop` CLI surface and the published guides at https://docs.hiloop.ai. Keep
skill bodies under ~500 lines and push dense schemas into `references/`, per the Agent Skills best
practices. When the CLI changes, update the matching skill in the same change.

`scripts/check-skills.sh` is a lightweight drift guard (run in CI on every change and weekly): it
checks each skill's frontmatter/length/links and — when a `hiloop` binary is on `PATH` — that every
`hiloop …` command a skill mentions still exists, derived live from `hiloop --help` (no hardcoded
list). Run it locally with `./scripts/check-skills.sh`.

## License

Apache-2.0 (see `LICENSE`).
