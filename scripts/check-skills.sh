#!/usr/bin/env bash
# Lightweight skill-drift check for the hiloop skills repo.
#
# Two layers, both cheap and dependency-light:
#
#   1. STRUCTURE (always): every skills/<name>/SKILL.md has YAML frontmatter
#      with `name:` (matching its directory) and a non-empty `description:`,
#      the body stays under the ~500-line Agent Skills soft cap, every
#      `references/<file>` it links exists, and no known-stale token survives.
#
#   2. CLI COMMANDS (when a `hiloop` binary is on PATH): the set of valid
#      command paths is derived from `hiloop --help` (and one level of
#      sub-help) — NOT hardcoded — and every `hiloop <cmd> [<subcmd>]` used in
#      a fenced code block is checked against it. This is what catches CLI
#      drift: a renamed/removed subcommand makes a skill fail here. If no
#      `hiloop` is installed, this layer is skipped with a warning (so the
#      check never flakes on CLI-installer availability), and the workflow
#      installs the CLI best-effort.
#
# Exit non-zero if any check fails. Run from anywhere: it resolves the repo
# root from its own location.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
skills_dir="$repo_root/skills"
fail=0
err() { printf 'FAIL: %s\n' "$1" >&2; fail=1; }
note() { printf '%s\n' "$1"; }

MAX_LINES=500
# Tokens that must never reappear: the dropped QuerySpec query surface, and the
# retired fork-node/fork-path vocabulary (replaced by run-lineage / lineage_path).
BANNED_REGEX='QuerySpec|query-spec\.md|--spec\b|FILTER_OP_|CALCULATION_OP_|fork_node_id|fork_path|HILOOP_FORK_NODE_ID|HILOOP_FORK_PATH|--fork-path|--fork-node-id'

# --- Layer 1: structure -------------------------------------------------------

shopt -s nullglob
skill_files=("$skills_dir"/*/SKILL.md)
[ ${#skill_files[@]} -gt 0 ] || { err "no skills found under $skills_dir"; exit 1; }

for f in "${skill_files[@]}"; do
  dir="$(basename "$(dirname "$f")")"
  rel="skills/$dir/SKILL.md"

  # Frontmatter must be a leading `---` block.
  if [ "$(head -n1 "$f")" != "---" ]; then
    err "$rel: missing leading YAML frontmatter (\`---\`)"
    continue
  fi

  name="$(awk -F': *' '/^---/{c++; next} c==1 && /^name:/{print $2; exit}' "$f")"
  desc="$(awk '/^---/{c++; next} c==1 && /^description:/{print; exit}' "$f")"

  [ "$name" = "$dir" ] || err "$rel: frontmatter name '$name' != directory '$dir'"
  [ -n "$desc" ] || err "$rel: frontmatter is missing a description"

  lines="$(wc -l < "$f")"
  [ "$lines" -le "$MAX_LINES" ] || err "$rel: $lines lines exceeds the $MAX_LINES-line cap"

  if grep -Eqn "$BANNED_REGEX" "$f"; then
    err "$rel: contains a stale/banned token ($BANNED_REGEX):"
    grep -En "$BANNED_REGEX" "$f" >&2 || true
  fi

  # Linked references/<file> must exist.
  while IFS= read -r ref; do
    [ -f "$skills_dir/$dir/references/$ref" ] || err "$rel: links missing reference references/$ref"
  done < <(grep -oE 'references/[A-Za-z0-9._-]+' "$f" | sed 's#references/##' | sort -u)
done

# Banned tokens in the orientation/index files too.
for f in AGENTS.md README.md llms.txt; do
  [ -f "$repo_root/$f" ] || continue
  if grep -Eqn "$BANNED_REGEX" "$repo_root/$f"; then
    err "$f: contains a stale/banned token ($BANNED_REGEX)"
  fi
done

# --- Layer 2: CLI command existence (best-effort) -----------------------------

if ! command -v hiloop >/dev/null 2>&1; then
  note "NOTE: \`hiloop\` not on PATH — skipping CLI command-existence checks."
  [ "$fail" -eq 0 ] && note "OK: structure checks passed (${#skill_files[@]} skills)."
  exit "$fail"
fi

# Parse the first token of each line in a clap "Commands:" / "Subcommands:"
# section, stopping at the first blank line after it. Yields one command per line.
# stdin is taken from /dev/null so a `hiloop` invocation can never consume the
# input of a `while read` loop this is called inside.
subcommands_of() {
  "$@" --help </dev/null 2>/dev/null | awk '
    /^[A-Za-z]+ommands:/ { inblk=1; next }
    inblk && /^[[:space:]]*$/ { inblk=0 }
    inblk && /^[[:space:]]+[a-z]/ { print $1 }
  ' | grep -vE '^(help)$' || true
}

# Build the valid set in temp files: `top` (every top-level command) and `pairs`
# ("<cmd> <subcmd>" for each command group's subcommands), derived live from the
# CLI. Files (not in-memory strings) keep the read-loop independent of IFS and of
# the inner `hiloop` calls, and `grep -Fxq` over them is the membership test.
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
subcommands_of hiloop > "$work/top"
[ -s "$work/top" ] || { err "could not parse any commands from \`hiloop --help\`"; exit "$fail"; }
top_count="$(grep -c . "$work/top")"
: > "$work/groups"
: > "$work/pairs"
while IFS= read -r c; do
  [ -n "$c" ] || continue
  subcommands_of hiloop "$c" > "$work/subs"
  [ -s "$work/subs" ] || continue
  printf '%s\n' "$c" >> "$work/groups"
  while IFS= read -r s; do
    [ -n "$s" ] || continue
    printf '%s %s\n' "$c" "$s" >> "$work/pairs"
  done < "$work/subs"
done < "$work/top"
in_set() { grep -Fxq -- "$2" "$1"; }   # in_set <file> <value>

# Extract `hiloop <a> [<b>]` usages from fenced code blocks only (skip prose),
# normalize away backticks/parens, and validate against the derived set.
# `api` and `run` take freeform args (a REST path / a wrapped command), so we
# validate only their head, not the next token.
for f in "${skill_files[@]}"; do
  rel="skills/$(basename "$(dirname "$f")")/SKILL.md"
  while IFS=' ' read -r a b; do
    [ -n "$a" ] || continue
    case "$a" in --*|"") continue;; esac
    if ! in_set "$work/top" "$a"; then
      err "$rel: uses \`hiloop $a\` — not a current top-level command"
      continue
    fi
    # Only a known group's immediate next word is a subcommand worth checking;
    # skip flags, `--`, shell vars, ids, and the freeform-arg commands.
    in_set "$work/groups" "$a" || continue
    case "$a" in api|run) continue;; esac
    case "$b" in ""|-*|'$'*|'"'*) continue;; esac
    [[ "$b" =~ ^[a-z][a-z-]*$ ]] || continue
    if ! in_set "$work/pairs" "$a $b"; then
      err "$rel: uses \`hiloop $a $b\` — not a current \`$a\` subcommand"
    fi
  done < <(awk '
    /^```/ { fence = !fence; next }
    !fence { next }
    {
      line = $0
      gsub(/[`()]/, " ", line)        # drop backticks and $( ) wrappers
      sub(/^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=/, "", line)  # strip VAR= prefix
      sub(/^[[:space:]]+/, "", line)
      if (line ~ /^hiloop[[:space:]]/) {
        n = split(line, t, /[[:space:]]+/)
        print t[2], (n >= 3 ? t[3] : "")
      }
    }
  ' "$f")
done

if [ "$fail" -eq 0 ]; then
  note "OK: ${#skill_files[@]} skills — structure + CLI commands ($top_count top-level) all valid."
fi
exit "$fail"
