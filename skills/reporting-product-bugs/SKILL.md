---
name: reporting-product-bugs
description: >-
  Report a hiloop product bug — a hiloop surface (CLI, API, web console, sandbox, telemetry,
  annotations, docs) behaving wrong — or send non-bug product feedback to the hiloop team. Covers
  `hiloop feedback` (the structured expected/actual/repro fields, telemetry evidence ids, severity,
  fingerprint dedup) and the `POST /v1/feedback` API fallback for environments without the CLI. Use
  when a hiloop command errors or misbehaves, an API response contradicts its documentation, a
  surface renders wrong, or you have a product suggestion — never for reporting your own task's
  results.
metadata:
  version: 0.1.0
---

# Reporting product bugs

When **hiloop itself** misbehaves — a CLI panic, an API response that contradicts the docs, a
sandbox that does the wrong thing — report it to the hiloop team from right where you are.
`hiloop feedback` stores the report under your tenant and surfaces it for review.

Feedback is for **product bugs and product ideas only**: what *hiloop* did wrong, never what your
task produced. Research results, experiment outcomes, and eval scores are annotations on your run
(the `annotating-runs` skill) or your own deliverable — not feedback.

> Authenticate first (the `authenticating` skill). The tenant a report lands under always comes
> from your credential, never from the report body.

## File a bug

One `hiloop feedback` call per distinct finding — a positional title plus the structured fields:

```sh
hiloop feedback "runs tail panics on terminal resize" \
  --surface cli \
  --severity high \
  -m "resizing the terminal window kills a live tail" \
  --expected "the tail reflows to the new width (per the tailing section of the query guide)" \
  --actual "thread 'main' panicked at 'attempt to subtract with overflow'; exit code 101" \
  --repro "hiloop runs tail <run-id>   # then resize the terminal window" \
  --evidence run-01ABC --evidence evt-42 \
  --fingerprint cli/tail-resize-panic
```

- `--surface` — the part of the product the report is about: `cli` (the default), `api`, `web`,
  `sandbox`, `telemetry`, `annotations`, `docs`, or `other`.
- `--severity` — the bug's **impact**: `critical` (blocks work or loses data), `high`, `medium`,
  `low` (cosmetic). Omit it entirely for feedback that is not a bug.
- `-m` / `--message` — free-form details: context, what you were doing, anything the structured
  fields don't carry.
- `--expected` / `--actual` — the contract and its violation. Cite where the expectation comes from
  (the docs, `--help` text, behavior observed elsewhere), and paste the **exact** error output into
  `--actual` — never a paraphrase.
- `--repro` — steps runnable as-is: exact commands, in order, that reproduce the bug.
- `--evidence` (repeatable) — run / event / artifact ids. hiloop's telemetry already captured the
  failing run, so ids let the team jump straight to the trace; find them with the
  `querying-observability-trees` skill.
- `--fingerprint` — a stable dedup key, `<surface>/<short-slug>` (e.g. `cli/tail-resize-panic`).
  Derive it from the finding's content, never from a timestamp, so repeat reports of the same
  finding group together. Already reported this finding? Reuse the same fingerprint instead of
  filing a fresh report.
- `--output table|json` — `json` prints the stored `{id, relayed}` response verbatim.

Only the title is required — but a report the team can act on carries `--expected`, `--actual`,
`--repro`, and `--evidence`. Your CLI version is attached automatically.

## Non-bug feedback

An idea, a rough edge, a docs gap that isn't wrong-just-confusing — same verb, **no severity**:

```sh
hiloop feedback "sandbox exec help text is confusing" \
  -m "the --timeout unit is ambiguous; an example would fix it" --surface docs
```

## The confirmation: stored, then surfaced

On success the CLI prints the stored report's id and whether it has already been surfaced to the
team. A report that prints as *stored for review* (`"relayed": false` in JSON output) is **stored,
never lost** — the relay to the team's review channel just hasn't happened yet, and the command
still succeeded. Don't retry it; a retry files a duplicate.

## No CLI? `POST /v1/feedback`

The same shape over the API with your bearer credential — an agent that hits a bug inside a sandbox
can report it with its own credential:

```sh
curl -sS -X POST "${HILOOP_API_URL:-https://api.hiloop.ai}/v1/feedback" \
  -H "Authorization: Bearer ${HILOOP_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "runs tail panics on terminal resize",
    "surface": "cli",
    "severity": "high",
    "body": "resizing the terminal window kills a live tail",
    "expected": "the tail reflows to the new width",
    "actual": "panicked at attempt to subtract with overflow; exit code 101",
    "repro": "hiloop runs tail <run-id>, then resize the terminal window",
    "evidence": ["run-01ABC", "evt-42"],
    "fingerprint": "cli/tail-resize-panic"
  }'
```

The response is `{"id": "…", "relayed": true|false}` — `relayed: false` means stored but not yet
surfaced, as above. Required: `title` and `surface`. Caps: `title` ≤ 300 characters; `body`,
`expected`, `actual`, `repro` ≤ 10,000 each; `evidence` ≤ 50 ids of ≤ 256 characters each.

## Never

- File research results, experiment outcomes, or your task's output as feedback — feedback reports
  hiloop misbehaving, nothing else. Task judgments go through `annotating-runs`.
- Paraphrase an error — paste the exact text into `--actual`.
- File the same finding twice — reuse its fingerprint; two *distinct* findings are two reports.
- Treat `relayed: false` as a failure, or retry because of it — the report is stored.
- Put a secret, a `hil_…` value, or other sensitive material in a report — the body goes to the
  hiloop team as-is.
