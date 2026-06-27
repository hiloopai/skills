# Setup per harness

These skills follow the [Agent Skills open standard](https://agentskills.io) — a directory of
`skills/<name>/SKILL.md` files plus a root [`AGENTS.md`](AGENTS.md). Most agent harnesses load them
through one of two conventions, so in practice you only need one of these:

- **`~/.agents/skills/`** — the cross-harness skills directory honored by **Codex, Cursor, Gemini CLI,
  Amp, and Pi**. One symlink covers all five.
- **`AGENTS.md`** at your project root — the universal, always-on fallback understood by nearly every
  harness (it's the [agents.md](https://agents.md) standard, stewarded by the Linux Foundation's
  Agentic AI Foundation). Use this anywhere SKILL.md discovery isn't supported.

> Note: the top-level `skills/` directory in *this repo* is the Claude Code plugin layout. No other
> harness scans a bare `skills/` dir, so for those you symlink/copy the skills into the harness's own
> directory (below). The Agent Skills standard itself is an independent project
> (`agentskills/agentskills`); only `AGENTS.md` is under the Linux Foundation.

## The universal install (covers Codex, Cursor, Gemini CLI, Amp, Pi)

```sh
git clone https://github.com/hiloopai/skills.git ~/.hiloop-skills
mkdir -p ~/.agents/skills
for s in ~/.hiloop-skills/skills/*/; do
  ln -sfn "$s" "$HOME/.agents/skills/$(basename "$s")"
done
```

Then restart your agent and ask it to operate hiloop. To update: `git -C ~/.hiloop-skills pull`.

## At a glance

| Harness | Native `SKILL.md` | `AGENTS.md` | One-line install | Where it loads skills |
|---|---|---|---|---|
| Claude Code | yes | yes (`CLAUDE.md`) | `/plugin marketplace add hiloopai/skills` | plugin, `.claude/skills/` |
| OpenAI Codex | yes | yes | — (`~/.agents/skills/`) | `.agents/skills/`, `~/.agents/skills/` |
| Cursor | yes (2.4+) | yes | — | `.cursor/skills/`, `~/.cursor/skills/`, `.agents/skills/` |
| Gemini CLI | yes | opt-in | `gemini extensions install <url>` | `~/.gemini/skills/`, `.agents/skills/` |
| GitHub Copilot | yes | yes | `gh skill install hiloopai/skills <skill>` | `.github/skills/`, `.claude/skills/`, `.agents/skills/` |
| Cline | yes (3.48+) | yes | — | `.claude/skills/`, `~/.cline/skills/` |
| Amp | yes | yes (primary) | — | `.agents/skills/`, `.claude/skills/` |
| Pi | yes | yes | `pi install git:github.com/hiloopai/skills` | `.agents/skills/`, `.pi/skills/` |
| Windsurf / Cascade | no (rules) | yes | — | `AGENTS.md` (or convert to `.windsurf/rules/`) |
| Aider | no | not auto-loaded | — | explicit `--read` |

---

## Claude Code

```text
/plugin marketplace add hiloopai/skills
/plugin install hiloop@hiloop
```

Or project-scoped without the marketplace: copy `skills/*` into `.claude/skills/`.

## OpenAI Codex

Uses `~/.agents/skills/` (and `.agents/skills/` in a project). The [universal install](#the-universal-install-covers-codex-cursor-gemini-cli-amp-pi)
above is the setup. Codex also reads a global `~/.codex/AGENTS.md` and per-project `AGENTS.md`.

## Cursor

```sh
# Global (all projects):
git clone https://github.com/hiloopai/skills /tmp/hiloop-skills
mkdir -p ~/.cursor/skills && cp -R /tmp/hiloop-skills/skills/* ~/.cursor/skills/
# …or project-scoped & tracked:
git submodule add https://github.com/hiloopai/skills .cursor/skills
```

Reload the window after installing. Cursor 2.4+ also auto-loads `.agents/skills/` and `.claude/skills/`.

## Gemini CLI

One line (this repo ships a `gemini-extension.json`):

```sh
gemini extensions install https://github.com/hiloopai/skills
```

Or use the universal `~/.agents/skills/` symlink, and add `AGENTS.md` to the context filenames in
`~/.gemini/settings.json`:

```json
{ "context": { "fileName": ["AGENTS.md", "GEMINI.md"] } }
```

## GitHub Copilot

Per-skill, with preview (skills aren't GitHub-verified — inspect first):

```sh
gh skill preview hiloopai/skills <skill-name>
gh skill install hiloopai/skills <skill-name>
```

Or vendor all of them into a repo for the coding agent:

```sh
git clone https://github.com/hiloopai/skills /tmp/hiloop-skills
mkdir -p .github/skills && cp -R /tmp/hiloop-skills/skills/* .github/skills/
```

In VS Code, enable `chat.useAgentsMdFile` to honor the root `AGENTS.md`.

## Cline

```sh
git clone https://github.com/hiloopai/skills /tmp/hiloop-skills
mkdir -p .claude/skills && cp -R /tmp/hiloop-skills/skills/* .claude/skills/    # project
mkdir -p ~/.cline/skills && cp -R /tmp/hiloop-skills/skills/* ~/.cline/skills/  # global (Cline 3.48+)
```

Cline also auto-detects a root `AGENTS.md`.

## Amp

```sh
git clone https://github.com/hiloopai/skills /tmp/hiloop-skills
mkdir -p .agents/skills && cp -R /tmp/hiloop-skills/skills/* .agents/skills/      # project
mkdir -p ~/.agents/skills && cp -R /tmp/hiloop-skills/skills/* ~/.agents/skills/  # global
```

Amp treats `AGENTS.md` as its primary instructions file, so the root `AGENTS.md` is also picked up.

## Pi

```sh
pi install git:github.com/hiloopai/skills
```

Or the universal `~/.agents/skills/` symlink (Pi shares that directory).

## Windsurf / Cascade

No native `SKILL.md`. Lead with `AGENTS.md` (auto-discovered at the workspace root, always-on):

```sh
git clone https://github.com/hiloopai/skills /tmp/hiloop-skills
cp /tmp/hiloop-skills/AGENTS.md ./AGENTS.md
```

Optionally convert each skill into a rule under `.windsurf/rules/` (add `trigger: model_decision`
frontmatter so Cascade loads it on relevance).

## Aider

Aider doesn't auto-load instruction files — point it explicitly (read-only context):

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
