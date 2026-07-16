# Setup per harness

These skills follow the [Agent Skills open standard](https://agentskills.io) — a directory of
`skills/<name>/SKILL.md` files plus a root [`AGENTS.md`](AGENTS.md). Install the verified bundle for
your harness with the hiloop CLI:

```sh
hiloop skills install claude-code  # cursor | codex | gemini | copilot
hiloop skills install all
```

Claude Code, Cursor, Codex, and Gemini installs are user-wide. Copilot installs into
`.github/skills/` in the current repository. Re-run the same command to refresh an installation.

Most agent harnesses load skills through one of two conventions:

- **`~/.agents/skills/`** — the cross-harness skills directory honored by **Codex, Cursor, Gemini CLI,
  Amp, and Pi**. One symlink covers all five.
- **`AGENTS.md`** at your project root — the universal, always-on fallback understood by nearly every
  harness (it's the [agents.md](https://agents.md) standard, stewarded by the Linux Foundation's
  Agentic AI Foundation). Use this anywhere SKILL.md discovery isn't supported.

> Note: the top-level `skills/` directory in *this repo* is the Claude Code plugin layout. No other
> harness scans a bare `skills/` dir, so for those you symlink/copy the skills into the harness's own
> directory (below). The Agent Skills standard itself is an independent project
> (`agentskills/agentskills`); only `AGENTS.md` is under the Linux Foundation.

## At a glance

| Harness | Native `SKILL.md` | `AGENTS.md` | One-line install | Where it loads skills |
|---|---|---|---|---|
| Claude Code | yes | yes (`CLAUDE.md`) | `hiloop skills install claude-code` | `~/.claude/skills/` |
| OpenAI Codex | yes | yes | `hiloop skills install codex` | `~/.agents/skills/` |
| Cursor | yes (2.4+) | yes | `hiloop skills install cursor` | `~/.cursor/skills/` |
| Gemini CLI | yes | opt-in | `hiloop skills install gemini` | `~/.gemini/skills/` |
| GitHub Copilot | yes | yes | `hiloop skills install copilot` | `.github/skills/` |
| Cline | yes (3.48+) | yes | — | `.claude/skills/`, `~/.cline/skills/` |
| Amp | yes | yes (primary) | — | `.agents/skills/`, `.claude/skills/` |
| Pi | yes | yes | `pi install git:github.com/hiloopai/skills` | `.agents/skills/`, `.pi/skills/` |
| Windsurf / Cascade | no (rules) | yes | — | `AGENTS.md` (or convert to `.windsurf/rules/`) |
| Aider | no | not auto-loaded | — | explicit `--read` |

---

## Claude Code

```sh
hiloop skills install claude-code
```

The Claude Code plugin marketplace is also supported:

```text
/plugin marketplace add hiloopai/skills
/plugin install hiloop@hiloop
```

## OpenAI Codex

```sh
hiloop skills install codex
```

Codex uses `~/.agents/skills/` (and `.agents/skills/` in a project). It also reads a global
`~/.codex/AGENTS.md` and per-project `AGENTS.md`.

## Cursor

```sh
hiloop skills install cursor
```

Reload the window after installing. Cursor 2.4+ also auto-loads `.agents/skills/` and `.claude/skills/`.

## Gemini CLI

```sh
hiloop skills install gemini
```

The native Gemini extension is also supported (this repo ships a `gemini-extension.json`):

```sh
gemini extensions install https://github.com/hiloopai/skills
```

To load a root `AGENTS.md` as context too, add it to the context filenames in
`~/.gemini/settings.json`:

```json
{ "context": { "fileName": ["AGENTS.md", "GEMINI.md"] } }
```

## GitHub Copilot

Install the full verified bundle into the current repository:

```sh
hiloop skills install copilot
```

GitHub's per-skill installer remains available, with preview:

```sh
gh skill preview hiloopai/skills <skill-name>
gh skill install hiloopai/skills <skill-name>
```

In VS Code, enable `chat.useAgentsMdFile` to honor the root `AGENTS.md`.

## Cline

Unsupported by `hiloop skills install`; use the manual fallback:

```sh
git clone https://github.com/hiloopai/skills /tmp/hiloop-skills
mkdir -p .claude/skills && cp -R /tmp/hiloop-skills/skills/* .claude/skills/    # project
mkdir -p ~/.cline/skills && cp -R /tmp/hiloop-skills/skills/* ~/.cline/skills/  # global (Cline 3.48+)
```

Cline also auto-detects a root `AGENTS.md`.

## Amp

Unsupported by `hiloop skills install`; use the manual fallback:

```sh
git clone https://github.com/hiloopai/skills /tmp/hiloop-skills
mkdir -p .agents/skills && cp -R /tmp/hiloop-skills/skills/* .agents/skills/      # project
mkdir -p ~/.agents/skills && cp -R /tmp/hiloop-skills/skills/* ~/.agents/skills/  # global
```

Amp treats `AGENTS.md` as its primary instructions file, so the root `AGENTS.md` is also picked up.

## Pi

Unsupported by `hiloop skills install`; use the native installer:

```sh
pi install git:github.com/hiloopai/skills
```

Or the universal `~/.agents/skills/` symlink (Pi shares that directory).

## Windsurf / Cascade

Unsupported by `hiloop skills install`. There is no native `SKILL.md`; use the manual fallback by
placing `AGENTS.md` at the workspace root (always-on):

```sh
git clone https://github.com/hiloopai/skills /tmp/hiloop-skills
cp /tmp/hiloop-skills/AGENTS.md ./AGENTS.md
```

Optionally convert each skill into a rule under `.windsurf/rules/` (add `trigger: model_decision`
frontmatter so Cascade loads it on relevance).

## Aider

Aider is unsupported by `hiloop skills install` and doesn't auto-load instruction files. Download
the repository's `AGENTS.md`, then point Aider at it explicitly (read-only context):

```yaml
# .aider.conf.yml
read: [AGENTS.md]
```

Or per-invocation: `aider --read AGENTS.md`. Keep it lean — read files ship in every request.

---

## Caveats (this space moves fast — verify against your harness's current docs)

- **Codex** discovery dirs shifted from `~/.codex/skills` (launch) to `~/.agents/skills/`; if on an
  older build, also symlink into `~/.codex/skills/`.
- **Gemini CLI** skills support is new; if `gemini extensions install` doesn't pick up skills, fall
  back to the `~/.agents/skills/` symlink.
- **Windsurf/Cascade** docs are migrating to `docs.devin.ai` and `.windsurf/rules/` → `.devin/rules/`.
- **Pi** advertises the Agent Skills standard; if a skill doesn't activate, confirm it reads the
  `name`/`description` frontmatter.

When in doubt, the root [`AGENTS.md`](AGENTS.md) works everywhere — it's the lowest-common-denominator
install.
