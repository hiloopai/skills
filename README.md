# hiloop skills

Open-source [Agent Skills](https://agentskills.io) that teach AI coding agents to operate
**[hiloop](https://hiloop.ai)** — isolated, forkable agent sandboxes with tree-native observability.

The skills follow the open Agent Skills standard, so they work across harnesses (Claude Code, Cursor,
Codex, and others). They drive hiloop through the `hiloop` **CLI** — the supported agent interface —
not an MCP server: a CLI the agent already knows how to drive costs far less context than loading tool
definitions every turn.

## What's here

| Skill | Use it to |
|---|---|
| [`authenticating`](skills/authenticating/SKILL.md) | Set up credentials, verify identity, manage scope and keys |
| [`creating-sandboxes`](skills/creating-sandboxes/SKILL.md) | Create / inspect / delete sandboxes |
| [`running-commands-in-a-sandbox`](skills/running-commands-in-a-sandbox/SKILL.md) | Execute commands; move files in/out |
| [`snapshotting-and-forking`](skills/snapshotting-and-forking/SKILL.md) | Snapshot state and fork into branches |
| [`querying-observability-trees`](skills/querying-observability-trees/SKILL.md) | Capture a run and query/diff its fork-tree telemetry |

[`AGENTS.md`](AGENTS.md) is the whole-product orientation an agent reads first.

## Quickstart

**1. Install the CLI** (single static binary):

```sh
curl -fsSL https://hiloop.ai/install.sh | sh
hiloop --version
```

**2. Authenticate** — headless (an agent / CI):

```sh
export HILOOP_API_KEY="hil_…"
hiloop whoami
```

…or interactively, when a human is present: `hiloop login` (`--device` on a remote box).

**3. Install the skills.**

- **Claude Code (one line):**

  ```
  /plugin marketplace add hiloopai/skills
  /plugin install hiloop@hiloop
  ```

- **Any harness:** copy the `skills/` directory into the location your agent loads skills from (e.g.
  `.claude/skills/`), or point your agent at this repo. `AGENTS.md` works anywhere the AGENTS.md
  convention is supported.

Then ask your agent to spin up a hiloop sandbox, fork it, and query the trace tree — the skills guide
the rest.

## Develop

These skills are validated end-to-end against hiloop on every change (see `scripts/` and CI). Keep
skill bodies under ~500 lines and push dense schemas into `references/`, per the Agent Skills
best practices. Commands here mirror the published guides at https://docs.hiloop.ai.

## License

Apache-2.0 (see `LICENSE`).
