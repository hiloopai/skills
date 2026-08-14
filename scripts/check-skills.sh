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
#   3. CLI FLAGS (same condition): every `--flag` written against a resolvable
#      command path — in a fenced block *or* an inline `code span`, in the
#      skills and in the orientation files — must appear in that path's
#      `--help`. Prose is where stale flags hide, so inline spans count; a span
#      whose command path no longer exists is skipped here (a skill may name a
#      deleted verb to say it is deleted). What this still cannot see is a
#      *claim about absence* — prose asserting a flag does not exist when it
#      does — so re-read the status blocks when the surface moves.
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
# Tokens that must never reappear: the dropped QuerySpec query surface, the
# retired fork-node/fork-path vocabulary (replaced by run-lineage / lineage_path),
# and the retired built-in annotation value flags/columns (the annotation payload is
# now organization-defined — promote the fields you query; there are no built-in value columns).
# Also banned: the runtime-rebuild status vocabulary. Those routes are served; a
# capability a deployment refuses is described as a refusal, never as an absent route.
BANNED_REGEX='QuerySpec|query-spec\.md|--spec\b|FILTER_OP_|CALCULATION_OP_|fork_node_id|fork_path|HILOOP_FORK_NODE_ID|HILOOP_FORK_PATH|--fork-path|--fork-node-id|--score|--outcome|--annotator-kind|annotator_kind|mid-rebuild|runtime rebuild|runtime is being rebuilt|runtime is rebuilt|no deployment serves|routes are unserved|CLI'"'"'s next release|hiloop run --secret|--value([=[:space:]>]|$)|querying-observability-trees|tree-native|branch-diff|\btenant\b'

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

  for r in "$skills_dir/$dir"/references/*.md; do
    if grep -Eqn "$BANNED_REGEX" "$r"; then
      err "skills/$dir/references/$(basename "$r"): contains a stale/banned token ($BANNED_REGEX):"
      grep -En "$BANNED_REGEX" "$r" >&2 || true
    fi
  done
done

# Banned tokens in the orientation/index files too.
for f in AGENTS.md README.md llms.txt .claude-plugin/marketplace.json \
  .claude-plugin/plugin.json gemini-extension.json; do
  [ -f "$repo_root/$f" ] || continue
  if grep -Eqn "$BANNED_REGEX" "$repo_root/$f"; then
    err "$f: contains a stale/banned token ($BANNED_REGEX)"
  fi
done

# The released query wire is an envelope, not a bare row array. This prose contract is easy to
# invert while editing examples, and command/flag discovery cannot detect a response-shape drift.
query_reference="$skills_dir/querying-observability/references/events-sql.md"
grep -Fq '`{ "columns": ["col", …], "rows": [{ "col": value, … }, …] }`' \
  "$query_reference" || err "query reference: missing the CLI v0.18.0 {columns, rows} JSON envelope"
grep -Fq 'from `.rows`' "$query_reference" \
  || err "query reference: missing the required .rows access guidance"
if grep -Fq 'top-level array of row objects' "$query_reference"; then
  err "query reference: contains the stale top-level-array response claim"
fi

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

check_commands_in() {   # check_commands_in <file> <label>
  local f="$1" rel="$2"
  local grandchildren
  while IFS=' ' read -r a b c; do
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
      continue
    fi
    grandchildren="$(subcommands_of hiloop "$a" "$b")"
    [ -n "$grandchildren" ] || continue
    case "$c" in ""|-*|'$'*|'"'*) continue;; esac
    [[ "$c" =~ ^[a-z][a-z-]*$ ]] || continue
    if ! grep -Fxq -- "$c" <<<"$grandchildren"; then
      err "$rel: uses \`hiloop $a $b $c\` — not a current \`$a $b\` subcommand"
    fi
  done < <(awk '
    /^```/ { fence = !fence; next }
    !fence { next }
    {
      line = $0
      gsub(/[`()]/, " ", line)        # drop backticks and $( ) wrappers
      sub(/^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=/, "", line)  # strip VAR= prefix
      sub(/^[[:space:]]+/, "", line)
      if (line !~ /^hiloop[[:space:]]/ && match(line, /\|[[:space:]]*hiloop[[:space:]]/)) {
        line = substr(line, RSTART)
        sub(/^\|[[:space:]]*/, "", line)
      }
      if (line ~ /^hiloop[[:space:]]/) {
        n = split(line, t, /[[:space:]]+/)
        print t[2], (n >= 3 ? t[3] : ""), (n >= 4 ? t[4] : "")
      }
    }
  ' "$f")
}

# Extract `hiloop <a> [<b>]` usages from fenced code blocks only (skip prose),
# normalize away backticks/parens, and validate against the derived set.
# `api` and `run` take freeform args (a REST path / a wrapped command), so we
# validate only their head, not the next token.
for f in "${skill_files[@]}"; do
  dir="$(basename "$(dirname "$f")")"
  check_commands_in "$f" "skills/$dir/SKILL.md"
  for r in "$skills_dir/$dir"/references/*.md; do
    check_commands_in "$r" "skills/$dir/references/$(basename "$r")"
  done
done

# --- Layer 3: CLI flag existence ---------------------------------------------

# One file per command path, holding that path's `--flags`. `slug` flattens a
# path to a filename (`sandbox snapshot create` -> `sandbox.snapshot.create`).
mkdir -p "$work/flags"
slug() { printf '%s' "$*" | tr ' ' '.'; }
flags_of() {
  "$@" --help </dev/null 2>/dev/null |
    grep -oE -- '--[a-z0-9][a-z0-9-]*' | sort -u
}
record_flags() {   # record_flags <path words…>
  flags_of hiloop "$@" > "$work/flags/$(slug "$@")"
}
: > "$work/paths"
while IFS= read -r c; do
  [ -n "$c" ] || continue
  printf '%s\n' "$c" >> "$work/paths"
  record_flags "$c"
done < "$work/top"
while IFS=' ' read -r c s; do
  [ -n "$s" ] || continue
  printf '%s %s\n' "$c" "$s" >> "$work/paths"
  record_flags "$c" "$s"
  while IFS= read -r g; do
    [ -n "$g" ] || continue
    printf '%s %s %s\n' "$c" "$s" "$g" >> "$work/paths"
    record_flags "$c" "$s" "$g"
  done < <(subcommands_of hiloop "$c" "$s")
done < "$work/pairs"

# Longest valid prefix of a token list, printed as a path (empty if none).
resolve_path() {
  local best='' cur=''
  for t in "$@"; do
    case "$t" in -*|'$'*) break;; esac
    cur="${cur:+$cur }$t"
    in_set "$work/paths" "$cur" || break
    best="$cur"
  done
  printf '%s' "$best"
}

check_flags_in() {   # check_flags_in <file> <label>
  local file="$1" rel="$2" line path known tok
  while IFS= read -r line; do
    # Everything after `--`, a comment, or a pipe belongs to another program.
    line="${line%%--\ *}"; line="${line%%#*}"; line="${line%%|*}"
    # shellcheck disable=SC2086
    set -- $line
    shift   # drop the leading `hiloop`
    [ $# -gt 0 ] || continue
    path="$(resolve_path "$@")"
    [ -n "$path" ] || continue
    known="$work/flags/$(slug "$path")"
    [ -s "$known" ] || continue
    for tok in "$@"; do
      case "$tok" in --?*) ;; *) continue;; esac
      tok="${tok%%=*}"
      in_set "$known" "$tok" ||
        err "$rel: writes \`$tok\` on \`hiloop $path\` — not a current flag"
    done
  done < <(awk '
    /^```/ { fence = !fence; next }
    {
      line = $0
      if (!fence) {
        # Inline code spans only: prose around them is not a command.
        out = ""
        n = split(line, part, "`")
        for (i = 2; i <= n; i += 2) out = out part[i] "\n"
        line = out
      } else {
        sub(/^[[:space:]]+/, "", line)
        if (continued != "") line = continued " " line
        if (line ~ /\\[[:space:]]*$/) {
          sub(/[[:space:]]*\\[[:space:]]*$/, "", line)
          continued = line
          next
        }
        continued = ""
      }
      gsub(/"[^"]*"/, "", line)
      gsub(/\047[^\047]*\047/, "", line)
      gsub(/[`()]/, " ", line)
      sub(/^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=/, "", line)
      m = split(line, cand, "\n")
      for (j = 1; j <= m; j++) {
        c = cand[j]
        sub(/^[[:space:]]+/, "", c)
        if (c !~ /^hiloop[[:space:]]/ && match(c, /\|[[:space:]]*hiloop[[:space:]]/)) {
          c = substr(c, RSTART)
          sub(/^\|[[:space:]]*/, "", c)
        }
        if (c ~ /^hiloop[[:space:]]/) print c
      }
    }
  ' "$file")
}

for f in "${skill_files[@]}"; do
  dir="$(basename "$(dirname "$f")")"
  check_flags_in "$f" "skills/$dir/SKILL.md"
  for r in "$skills_dir/$dir"/references/*.md; do
    check_flags_in "$r" "skills/$dir/references/$(basename "$r")"
  done
done
for f in AGENTS.md README.md llms.txt; do
  [ -f "$repo_root/$f" ] && check_flags_in "$repo_root/$f" "$f"
done

if [ "$fail" -eq 0 ]; then
  note "OK: ${#skill_files[@]} skills — structure + CLI commands ($top_count top-level) and flags all valid."
fi
exit "$fail"
