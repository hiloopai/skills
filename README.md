# hiloop skills

Open-source [Agent Skills](https://agentskills.io) that teach AI coding agents to operate
**[hiloop](https://hiloop.ai)** — isolated agent sandboxes you can snapshot and branch, with
tree-native observability.

The skills follow the open Agent Skills standard, so they work across harnesses (Claude Code, Cursor,
Codex, and others). They drive hiloop through the `hiloop` **CLI** — the supported agent interface —
not an MCP server: a CLI the agent already knows how to drive costs far less context than loading tool
definitions every turn.

## What's here

| Skill | Use it to |
|---|---|
| [`autoresearch`](skills/autoresearch/SKILL.md) | Run an autonomous research loop with evolving idea cards, scored experiments, an ensemble, and a leaderboard |
| [`authenticating`](skills/authenticating/SKILL.md) | Sign in with `hiloop login` (or a key), verify identity, mint and revoke keys |
| [`operating-sandboxes`](skills/operating-sandboxes/SKILL.md) | Create, inspect, exec, stop, start, and delete sandboxes; follow conditional references for sessions, snapshots, and devboxes |
| [`managing-volumes`](skills/managing-volumes/SKILL.md) | Publish and version large data once, mount it into many sandboxes |
| [`managing-secrets`](skills/managing-secrets/SKILL.md) | Give a run a credential it uses but never sees (the secret broker) |
| [`launching-as-workloads`](skills/launching-as-workloads/SKILL.md) | Launch a run as a registered machine identity (a workload) and control who may launch as it |
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

**2. Point the CLI at your deployment, then authenticate** — the built-in default edge is not live,
so save a context (or set `HILOOP_API_URL`) first. `hiloop login` is the default (`--device` on a
remote box with no local browser):

```sh
hiloop config set-context my-deployment --api-url https://api.example.com
hiloop config use-context my-deployment
hiloop login
hiloop whoami
```

…or headless (an agent / CI), skip the browser with a key: `export HILOOP_API_KEY="hil_…"`.

**3. Upgrade the CLI, then install the skills.** Choose your harness, or install every supported
target:

```sh
hiloop skills install claude-code  # cursor | codex | gemini | copilot
hiloop skills install all
```

`copilot` installs into the current repository; the other targets install for your user. Full target
paths, native alternatives, and unsupported-harness fallback instructions are in
[`SETUP.md`](SETUP.md).

CLI v0.17.0 pins bundle v0.5.0. Until a CLI pins this v0.5.1 correction, pass
`--ref v0.5.1` when installing.

Then ask your agent to capture a run and query the trace tree — the skills guide the rest.

> **Sandbox status.** Core lifecycle and buffered exec are served. Optional capabilities are
> deployment-dependent and refuse explicitly when absent; see the capability table in
> [`operating-sandboxes`](skills/operating-sandboxes/SKILL.md). Every create returns an ambient run,
> but automatic runtime capture is not attached yet; normal entrypoint/exec/SSH activity produces
> zero ambient events.

For autonomous metric optimization, point the agent at your task, fixed dataset/scorer, and the
[`autoresearch`](skills/autoresearch/SKILL.md) skill. Watch it with the public
[`fleet-dashboard`](tools/fleet-dashboard/README.md).

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
