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
| [`authenticating`](skills/authenticating/SKILL.md) | Sign in with `hiloop login` (or a key), verify identity, manage scope and keys |
| [`creating-sandboxes`](skills/creating-sandboxes/SKILL.md) | Create / inspect / delete sandboxes; bring your own image, request resources |
| [`running-commands-in-a-sandbox`](skills/running-commands-in-a-sandbox/SKILL.md) | Run commands; stream + steer long-running processes; move files in/out |
| [`snapshotting-and-forking`](skills/snapshotting-and-forking/SKILL.md) | Snapshot state and fork into branches |
| [`managing-secrets`](skills/managing-secrets/SKILL.md) | Give a sandbox a credential it uses but never sees (the secret broker) |
| [`querying-observability-trees`](skills/querying-observability-trees/SKILL.md) | Capture a run and query (SQL) / tail / diff its fork-tree telemetry |
| [`annotating-runs`](skills/annotating-runs/SKILL.md) | Stamp structured judgments (outcome / score) you can filter and aggregate on |

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

**3. Install the skills.** Full per-harness instructions are in [`SETUP.md`](SETUP.md). The short version:

- **Claude Code:** `/plugin marketplace add hiloopai/skills` then `/plugin install hiloop@hiloop`.
- **Codex, Cursor, Gemini CLI, Amp, Pi** — the cross-harness skills directory:

  ```sh
  git clone https://github.com/hiloopai/skills.git ~/.hiloop-skills
  mkdir -p ~/.agents/skills
  for s in ~/.hiloop-skills/skills/*/; do ln -sfn "$s" "$HOME/.agents/skills/$(basename "$s")"; done
  ```

- **GitHub Copilot:** `gh skill install hiloopai/skills <skill>`.
- **Gemini CLI (one line):** `gemini extensions install https://github.com/hiloopai/skills`.
- **Anything else / fallback:** drop the root [`AGENTS.md`](AGENTS.md) into your project — it's the
  universal, always-on convention (Windsurf, Aider via `--read`, and every harness above honor it).

Then ask your agent to spin up a hiloop sandbox, fork it, and query the trace tree — the skills guide
the rest.

## Develop

These skills mirror the `hiloop` CLI surface and the published guides at https://docs.hiloop.ai. Keep
skill bodies under ~500 lines and push dense schemas into `references/`, per the Agent Skills best
practices. When the CLI changes, update the matching skill in the same change.

## License

Apache-2.0 (see `LICENSE`).
