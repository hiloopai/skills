#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["rich>=14"]
# ///
r"""hiloop fleet dashboard — a live terminal view of a parallel-agent fleet.

Renders four panels over one project, refreshing in place (rich ``Live``, no flicker):

* **Fleet** — the project's runs: role label, status, start/duration, principal.
* **Lineage** — the run fork trees, reconstructed from ``parent_run_id``.
* **Leaderboard** — best experiment score per lane, read from the schema's ``ann_*`` view.
* **Events** — the most recent captured events and annotations, rolling.

Every byte comes from the ``hiloop`` CLI invoked as a subprocess with ``--output json`` —
the same public surface a user scripts against. No API client or private imports. Verify the
project and schema once with ``--once`` before relying on the live display.

Examples::

    # live, full-screen, refreshing every 2s
    uv run tools/fleet-dashboard/dashboard.py --project demos

    # one printed snapshot (tests, CI, quick checks)
    uv run tools/fleet-dashboard/dashboard.py --project demos --once

    # a lower-is-better metric under a different schema
    uv run tools/fleet-dashboard/dashboard.py --project demos \
        --schema acme.trial.v1 --score-field metric.value --direction lower
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

if TYPE_CHECKING:
    from rich.console import RenderableType

# One source of truth per enum-ish wire value: status/signal → (glyph, style).
STATUS_STYLE: dict[str, tuple[str, str]] = {
    "running": ("●", "bold yellow"),
    "pending": ("◌", "dim"),
    "succeeded": ("✔", "green"),
    "failed": ("✖", "red"),
    "canceled": ("⊘", "dim"),
}
SIGNAL_STYLE: dict[str, tuple[str, str]] = {
    "llm": ("✦", "magenta"),
    "exec": ("⚙", "cyan"),
    "log": ("·", "dim"),
    "net": ("⇄", "blue"),
    "annotation": ("✎", "yellow"),
}
_UNKNOWN_STATUS = ("?", "dim")
_UNKNOWN_SIGNAL = ("·", "white")

_DURATION_UNITS: tuple[tuple[str, int], ...] = (
    ("w", 7 * 86400),
    ("d", 86400),
    ("h", 3600),
    ("m", 60),
    ("s", 1),
)
_SINCE_RE = re.compile(r"^(\d+)([smhdw])$")
_DURATION_MAX_PARTS = 2
_NARROW_WIDTH = 100
_MAX_TREE_ROOTS = 8


class CliError(Exception):
    """A ``hiloop`` invocation failed; carries the CLI's error code and message."""

    def __init__(self, *, code: str, message: str) -> None:
        """Store the error envelope's ``code`` and ``message``."""
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# --- wire parsing (pure; unit-tested against recorded fixtures) --------------------------------


@dataclass(frozen=True)
class Run:
    """One run record as ``hiloop runs list --output json`` emits it."""

    id: str
    label: str
    status: str
    parent_run_id: str
    root_run_id: str
    created_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    executing_kind: str
    executing_principal: str

    @property
    def principal(self) -> str:
        """Compact principal identity (the JSON page carries the raw id, not a display name)."""
        short = self.executing_principal[:8] if self.executing_principal else "?"
        return f"{self.executing_kind or '?'}:{short}"

    def duration(self, now: datetime) -> timedelta | None:
        """Wall-clock from start to end, or to ``now`` while the run is still going."""
        if self.started_at is None:
            return None
        return (self.ended_at or now) - self.started_at


@dataclass(frozen=True)
class Experiment:
    """One experiment annotation row from the schema's ``ann_*`` view."""

    run_id: str
    lane: str
    score: float
    headline: str
    outcome: str
    ts: datetime | None


@dataclass(frozen=True)
class Event:
    """One captured event row from the ``events`` table."""

    ts: datetime | None
    signal: str
    name: str
    run_id: str
    detail: str


@dataclass(frozen=True)
class TickerEntry:
    """A ticker line: the newest event of a consecutive same-shaped burst, with its size."""

    event: Event
    count: int


@dataclass(frozen=True)
class LaneBest:
    """A leaderboard line: the best experiment for one lane, plus the lane's volume."""

    lane: str
    best: Experiment
    count: int


def _parse_ts(value: str) -> datetime | None:
    """Parse an RFC 3339 timestamp; empty or malformed → ``None``."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_ns(value: object) -> datetime | None:
    """Parse a ``ts_wall_ns`` value (the JSON page carries int64 columns as strings)."""
    try:
        return datetime.fromtimestamp(int(str(value)) / 1e9, tz=UTC)
    except ValueError, OSError, OverflowError:
        return None


def error_of(payload: object) -> CliError | None:
    """Extract the CLI's ``{"error": {code, message}}`` envelope, if this payload is one."""
    if not isinstance(payload, dict):
        return None
    err = payload.get("error")
    if not isinstance(err, dict):
        return None
    return CliError(code=str(err.get("code", "error")), message=str(err.get("message", "")))


def parse_runs(payload: dict[str, Any]) -> tuple[list[Run], bool]:
    """Parse a ``runs list`` JSON page into runs plus a has-more-pages flag."""
    runs = [
        Run(
            id=str(r.get("id", "")),
            label=str(r.get("label", "")),
            status=str(r.get("status", "")),
            parent_run_id=str(r.get("parent_run_id", "")),
            root_run_id=str(r.get("root_run_id", "")),
            created_at=_parse_ts(str(r.get("created_at", ""))),
            started_at=_parse_ts(str(r.get("started_at", ""))),
            ended_at=_parse_ts(str(r.get("ended_at", ""))),
            executing_kind=str(r.get("executing_kind", "")),
            executing_principal=str(r.get("executing_principal", "")),
        )
        for r in payload.get("runs", [])
    ]
    return runs, bool(payload.get("next_page_token"))


def fleet_order(runs: list[Run]) -> list[Run]:
    """In-flight first (running, then pending), then newest-first — mirrors ``runs list``."""
    rank = {"running": 0, "pending": 1}
    epoch = datetime.min.replace(tzinfo=UTC)
    return sorted(runs, key=lambda r: (rank.get(r.status, 2), -(r.created_at or epoch).timestamp()))


def build_forest(runs: list[Run]) -> dict[str, list[Run]]:
    """Group runs into ``parent id → children``; key ``""`` holds the roots.

    A run whose parent is outside this page is promoted to a root rather than dropped,
    so a truncated listing still renders every run somewhere.
    """
    by_id = {r.id: r for r in runs}
    forest: dict[str, list[Run]] = {"": []}
    for run in runs:
        parent = run.parent_run_id if run.parent_run_id in by_id else ""
        forest.setdefault(parent, []).append(run)
    epoch = datetime.min.replace(tzinfo=UTC)
    for children in forest.values():
        children.sort(key=lambda r: (r.created_at or epoch, r.id))
    return forest


def _dig(payload: dict[Any, Any], dotted: str) -> object:
    """Walk a dotted path (``metric.value``) into a nested dict; missing → ``None``."""
    node: object = payload
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def parse_experiments(
    rows: list[dict[str, Any]], *, score_field: str
) -> tuple[list[Experiment], int]:
    """Parse ``ann_*`` view rows into experiments, reading fields from ``payload_json``.

    Returns the parsed experiments plus how many rows were skipped (malformed payload or a
    missing/non-numeric score) — skips are surfaced, never silently absorbed.
    """
    experiments: list[Experiment] = []
    skipped = 0
    for row in rows:
        raw = row.get("payload_json")
        payload: object = raw
        if isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                skipped += 1
                continue
        if not isinstance(payload, dict):
            skipped += 1
            continue
        score = _dig(payload, score_field)
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            skipped += 1
            continue
        experiments.append(
            Experiment(
                run_id=str(row.get("run_id", "")),
                lane=str(payload.get("lane", "") or ""),
                score=float(score),
                headline=str(payload.get("headline", "") or ""),
                outcome=str(payload.get("outcome", "") or ""),
                ts=_parse_ns(row.get("ts_wall_ns", "")),
            )
        )
    return experiments, skipped


def leaderboard(
    experiments: list[Experiment],
    runs_by_id: dict[str, Run],
    *,
    higher_is_better: bool,
) -> list[LaneBest]:
    """Best experiment per lane, ranked best-first.

    A row's lane is its ``lane`` field when present, else its run's label, else the run id —
    so the board stays meaningful for schemas that don't declare lanes.
    """
    lanes: dict[str, list[Experiment]] = {}
    for exp in experiments:
        run = runs_by_id.get(exp.run_id)
        lane = exp.lane or (run.label if run else "") or exp.run_id or "?"
        lanes.setdefault(lane, []).append(exp)
    board = [
        LaneBest(
            lane=lane,
            best=(max if higher_is_better else min)(rows, key=lambda e: e.score),
            count=len(rows),
        )
        for lane, rows in lanes.items()
    ]
    board.sort(key=lambda b: b.best.score, reverse=higher_is_better)
    return board


def _event_detail(raw: object) -> str:
    """Pull a one-line human detail (the ``message`` attribute) out of ``attributes_json``."""
    attrs: object = raw
    if isinstance(raw, str):
        try:
            attrs = json.loads(raw)
        except json.JSONDecodeError:
            return ""
    if not isinstance(attrs, dict):
        return ""
    message = attrs.get("message")
    if not isinstance(message, str):
        return ""
    return " ".join(message.split())


def parse_events(rows: list[dict[str, Any]]) -> list[Event]:
    """Parse ticker rows (newest-first, as the SQL orders them)."""
    return [
        Event(
            ts=_parse_ns(row.get("ts_wall_ns", "")),
            signal=str(row.get("signal", "")),
            name=str(row.get("name", "")),
            run_id=str(row.get("run_id", "")),
            detail=_event_detail(row.get("attributes_json")),
        )
        for row in rows
    ]


def collapse_events(events: list[Event]) -> list[TickerEntry]:
    """Merge consecutive same-shaped events (same run, signal, name) into one xN line.

    Keeps the newest event of each burst, so a tick loop reads as one moving line
    instead of a wall of identical rows.
    """
    entries: list[TickerEntry] = []
    for event in events:
        if (
            entries
            and (last := entries[-1].event).run_id == event.run_id
            and last.signal == event.signal
            and last.name == event.name
        ):
            entries[-1] = TickerEntry(event=last, count=entries[-1].count + 1)
        else:
            entries.append(TickerEntry(event=event, count=1))
    return entries


def view_name(schema: str) -> str:
    """The registered query view for a schema: lowercase, non-alphanumerics → ``_``, ``ann_``."""
    return "ann_" + re.sub(r"[^a-z0-9]", "_", schema.lower())


def parse_since(value: str) -> timedelta:
    """Parse a relative duration (``90s``, ``30m``, ``2h``, ``3d``, ``1w``) — the CLI's grammar."""
    match = _SINCE_RE.match(value.strip())
    if match is None:
        msg = f"invalid duration {value!r} (expected e.g. 90s, 30m, 2h, 3d, 1w)"
        raise ValueError(msg)
    seconds = int(match.group(1)) * dict(_DURATION_UNITS)[match.group(2)]
    return timedelta(seconds=seconds)


def fmt_duration(delta: timedelta | None) -> str:
    """Humanize a duration: the two most significant units (``3m40s``), ``—`` for unknown."""
    if delta is None:
        return "—"
    seconds = max(0, int(delta.total_seconds()))
    parts = []
    for suffix, size in _DURATION_UNITS:
        if seconds >= size or (suffix == "s" and not parts):
            parts.append(f"{seconds // size}{suffix}")
            seconds %= size
        if len(parts) == _DURATION_MAX_PARTS:
            break
    return "".join(parts)


def _ago(ts: datetime, now: datetime) -> str:
    """Single most-significant-unit ago string (``16m``, ``2h``)."""
    seconds = max(0, int((now - ts).total_seconds()))
    for suffix, size in _DURATION_UNITS:
        if seconds >= size:
            return f"{seconds // size}{suffix}"
    return "0s"


# --- hiloop CLI seam (spoofed in tests via --hiloop-bin pointing at a fixture replayer) --------


@dataclass(frozen=True)
class HiloopCli:
    """Invokes the ``hiloop`` binary and returns parsed JSON payloads."""

    bin_path: str
    project: str
    timeout: float = 15.0

    def _invoke(self, *args: str) -> dict[str, Any]:
        """Run one CLI command; raise :class:`CliError` on any failure shape."""
        argv = [self.bin_path, *args, "--output", "json"]
        try:
            proc = subprocess.run(  # noqa: S603 - argv is a constructed list, never shell-interpolated
                argv, capture_output=True, text=True, check=False, timeout=self.timeout
            )
        except FileNotFoundError:
            message = f"hiloop binary not found: {self.bin_path!r}"
            raise CliError(code="not_found", message=message) from None
        except subprocess.TimeoutExpired:
            message = f"hiloop {args[0]} timed out after {self.timeout:g}s"
            raise CliError(code="timeout", message=message) from None
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            detail = proc.stderr.strip().splitlines()
            summary = detail[-1] if detail else f"exit {proc.returncode}, no JSON output"
            message = f"hiloop {args[0]}: {summary}"
            raise CliError(code="error", message=message) from None
        if err := error_of(payload):
            raise err
        if proc.returncode != 0:
            message = f"hiloop {args[0]} exited {proc.returncode}"
            raise CliError(code="error", message=message)
        return payload if isinstance(payload, dict) else {"rows": payload}

    def runs_page(self, *, page_size: int, since: str) -> dict[str, Any]:
        """One ``runs list`` page for the project (newest-first server order)."""
        args = ["runs", "list", "--project", self.project, "--page-size", str(page_size)]
        if since:
            args += ["--since", since]
        return self._invoke(*args)

    def project_record(self) -> dict[str, Any]:
        """The project record (id + display name) for the configured slug."""
        return self._invoke("projects", "get", self.project)

    def query_rows(self, sql: str) -> list[dict[str, Any]]:
        """Run a read-only SELECT via ``hiloop query --sql``, project-scoped."""
        payload = self._invoke("query", "--project", self.project, "--sql", sql)
        rows = payload.get("rows")
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]


def leaderboard_sql(view: str, *, limit: int = 400) -> str:
    """The leaderboard SELECT over a schema's registered view (structural columns only)."""
    return (
        f"SELECT run_id, ts_wall_ns, payload_json FROM {view} "  # noqa: S608 - view_name()-sanitized identifier + int literal, not user SQL
        f"ORDER BY ts_wall_ns DESC LIMIT {int(limit)}"
    )


def events_sql(project_id: str, *, cutoff_ns: int, limit: int = 60) -> str:
    """The ticker SELECT: recent events, scoped tight so the engine never cold-scans the tenant."""
    pid = uuid.UUID(project_id)  # refuses anything that is not a real project UUID
    return (
        "SELECT ts_wall_ns, signal, name, run_id, attributes_json FROM events "  # noqa: S608 - validated UUID + int literals, not user SQL
        f"WHERE project_id = '{pid}' AND ts_wall_ns >= {int(cutoff_ns)} "
        f"ORDER BY ts_wall_ns DESC LIMIT {int(limit)}"
    )


def is_missing_view(err: CliError, view: str) -> bool:
    """True when a query failed only because the schema's view has not been registered yet."""
    return err.code == "invalid_query" and "not found" in err.message and view in err.message


# --- snapshot collection ------------------------------------------------------------------------


@dataclass(frozen=True)
class Options:
    """Resolved dashboard settings (parsed flags, ready for collection/rendering)."""

    project: str
    schema: str
    score_field: str
    higher_is_better: bool
    label_prefix: str
    since: str
    ticker_since: timedelta
    page_size: int
    max_fleet_rows: int


@dataclass(frozen=True)
class Snapshot:
    """Everything one refresh gathered; each panel carries its own error honestly."""

    fetched_at: datetime
    project_name: str
    runs: list[Run]
    runs_error: str | None
    more_runs: bool
    board: list[LaneBest]
    board_skipped: int
    board_error: str | None
    board_missing_view: bool
    events: list[Event]
    events_error: str | None


def collect(
    cli: HiloopCli,
    opts: Options,
    *,
    project_id: str | None,
    project_id_error: str | None = None,
) -> Snapshot:
    """Gather one snapshot. Panel failures degrade that panel only, never the whole screen."""
    now = datetime.now(UTC)

    runs: list[Run] = []
    more_runs = False
    runs_error: str | None = None
    try:
        runs, more_runs = parse_runs(cli.runs_page(page_size=opts.page_size, since=opts.since))
    except CliError as err:
        runs_error = str(err)
    if opts.label_prefix:
        runs = [r for r in runs if r.label.startswith(opts.label_prefix)]

    view = view_name(opts.schema)
    board: list[LaneBest] = []
    board_skipped = 0
    board_error: str | None = None
    board_missing_view = False
    try:
        experiments, board_skipped = parse_experiments(
            cli.query_rows(leaderboard_sql(view)), score_field=opts.score_field
        )
        board = leaderboard(
            experiments, {r.id: r for r in runs}, higher_is_better=opts.higher_is_better
        )
    except CliError as err:
        if is_missing_view(err, view):
            board_missing_view = True
        else:
            board_error = str(err)

    events: list[Event] = []
    events_error: str | None = None
    if project_id is None:
        events_error = project_id_error or "project id unresolved — events ticker unavailable"
    else:
        cutoff_ns = int((now - opts.ticker_since).timestamp() * 1e9)
        try:
            events = parse_events(cli.query_rows(events_sql(project_id, cutoff_ns=cutoff_ns)))
        except CliError as err:
            events_error = str(err)

    return Snapshot(
        fetched_at=now,
        project_name=opts.project,
        runs=runs,
        runs_error=runs_error,
        more_runs=more_runs,
        board=board,
        board_skipped=board_skipped,
        board_error=board_error,
        board_missing_view=board_missing_view,
        events=events,
        events_error=events_error,
    )


# --- rendering (pure: Snapshot + now → rich renderables) -----------------------------------------


def _status_text(status: str) -> Text:
    """Status as ``glyph word`` in its registry style."""
    glyph, style = STATUS_STYLE.get(status, _UNKNOWN_STATUS)
    return Text(f"{glyph} {status or 'unknown'}", style=style)


def _error_body(message: str) -> Text:
    """A panel body that shows a degraded state loudly instead of pretending."""
    return Text(f"⚠ {message}", style="red")


def render_fleet(snapshot: Snapshot, now: datetime, *, max_rows: int) -> Panel:
    """The fleet table: one row per run, in-flight first."""
    if snapshot.runs_error:
        return Panel(_error_body(snapshot.runs_error), title="Fleet", border_style="red")
    ordered = fleet_order(snapshot.runs)
    table = Table(box=None, expand=True, pad_edge=False)
    table.add_column("ROLE", style="bold", overflow="ellipsis", ratio=3, no_wrap=True)
    table.add_column("STATUS", min_width=11, no_wrap=True)
    table.add_column("STARTED", justify="right", no_wrap=True)
    table.add_column("DUR", justify="right", no_wrap=True)
    table.add_column("PRINCIPAL", style="dim", overflow="ellipsis", ratio=2, no_wrap=True)
    table.add_column("RUN", style="dim", no_wrap=True)
    for run in ordered[:max_rows]:
        started = _ago(run.started_at, now) if run.started_at else "—"
        table.add_row(
            run.label or "(unlabeled)",
            _status_text(run.status),
            started,
            fmt_duration(run.duration(now)),
            run.principal,
            run.id[-6:],
        )
    footer = []
    if len(ordered) > max_rows:
        footer.append(f"+{len(ordered) - max_rows} more rows")
    if snapshot.more_runs:
        footer.append("more pages on the server — narrow with --since/--label-prefix")
    body: RenderableType = table
    if not ordered:
        body = Text(
            "no runs in this window — start one with `hiloop run --label <role> …`", style="dim"
        )
    elif footer:
        body = Group(table, Text(" · ".join(footer), style="dim italic"))
    return Panel(body, title=f"Fleet — {len(ordered)} runs", border_style="cyan")


def render_tree(snapshot: Snapshot, now: datetime) -> Panel:
    """The lineage forest: one tree per root run, statuses inline."""
    if snapshot.runs_error:
        return Panel(_error_body(snapshot.runs_error), title="Lineage", border_style="red")
    forest = build_forest(snapshot.runs)
    roots = forest.get("", [])
    if not roots:
        body: RenderableType = Text("no runs, no tree — fork something", style="dim")
        return Panel(body, title="Lineage", border_style="cyan")

    def node_text(run: Run) -> Text:
        glyph, style = STATUS_STYLE.get(run.status, _UNKNOWN_STATUS)
        text = Text()
        text.append(f"{glyph} ", style=style)
        text.append(run.label or run.id, style="bold" if run.status == "running" else "")
        text.append(f"  {fmt_duration(run.duration(now))}", style="dim")
        return text

    def attach(branch: Tree, run: Run) -> None:
        child_branch = branch.add(node_text(run))
        for child in forest.get(run.id, []):
            attach(child_branch, child)

    newest_first = sorted(
        roots, key=lambda r: r.created_at or datetime.min.replace(tzinfo=UTC), reverse=True
    )
    trees: list[RenderableType] = []
    for root in newest_first[:_MAX_TREE_ROOTS]:
        tree = Tree(node_text(root), guide_style="dim")
        for child in forest.get(root.id, []):
            attach(tree, child)
        trees.append(tree)
    if len(newest_first) > _MAX_TREE_ROOTS:
        trees.append(Text(f"+{len(newest_first) - _MAX_TREE_ROOTS} more trees", style="dim italic"))
    return Panel(Group(*trees), title="Lineage", border_style="cyan")


def render_leaderboard(snapshot: Snapshot, now: datetime, opts: Options) -> Panel:
    """Best score per lane from the schema's ``ann_*`` view, honest when the view is absent."""
    title = f"Leaderboard — {opts.schema}"
    if snapshot.board_error:
        return Panel(_error_body(snapshot.board_error), title=title, border_style="red")
    if snapshot.board_missing_view:
        body = Text(
            f"no experiment annotations yet — schema {opts.schema!r} is not registered.\n"
            f"register it with `hiloop annotation-schema register {opts.schema} …`, then\n"
            "`hiloop annotations add --schema … --data …` from each lane.",
            style="dim",
        )
        return Panel(body, title=title, border_style="cyan")
    if not snapshot.board:
        return Panel(
            Text("view registered, no scored experiments yet", style="dim"),
            title=title,
            border_style="cyan",
        )
    arrow = "↑" if opts.higher_is_better else "↓"
    table = Table(box=None, expand=True, pad_edge=False)
    table.add_column("#", justify="right", style="dim", no_wrap=True)
    table.add_column("LANE", style="bold", overflow="ellipsis", ratio=2, no_wrap=True)
    table.add_column(f"BEST {arrow}", justify="right", no_wrap=True)
    table.add_column("N", justify="right", style="dim", no_wrap=True)
    table.add_column("EXPERIMENT", overflow="ellipsis", ratio=3, no_wrap=True)
    table.add_column("WHEN", justify="right", style="dim", no_wrap=True)
    for rank, entry in enumerate(snapshot.board, start=1):
        style = "bold gold1" if rank == 1 else ""
        table.add_row(
            Text(f"{rank}", style=style),
            Text(entry.lane, style=style),
            Text(f"{entry.best.score:g}", style=style or "cyan"),
            str(entry.count),
            entry.best.headline or "—",
            _ago(entry.best.ts, now) if entry.best.ts else "—",
        )
    body_rows: list[RenderableType] = [table]
    if snapshot.board_skipped:
        body_rows.append(
            Text(f"⚠ {snapshot.board_skipped} rows skipped (malformed or unscored)", style="yellow")
        )
    return Panel(Group(*body_rows), title=title, border_style="cyan")


def render_ticker(snapshot: Snapshot, now: datetime) -> Panel:
    """The rolling event feed, newest first; annotations pop, logs stay dim."""
    if snapshot.events_error:
        return Panel(_error_body(snapshot.events_error), title="Events", border_style="red")
    if not snapshot.events:
        return Panel(
            Text("no captured events in the window", style="dim"),
            title="Events",
            border_style="cyan",
        )
    labels = {r.id: r.label for r in snapshot.runs}
    table = Table(box=None, expand=True, pad_edge=False, show_header=False)
    table.add_column("when", justify="right", style="dim", no_wrap=True)
    table.add_column("sig", no_wrap=True)
    table.add_column("event", overflow="ellipsis", ratio=3, no_wrap=True)
    table.add_column("run", style="dim", overflow="ellipsis", ratio=1, no_wrap=True)
    for entry in collapse_events(snapshot.events):
        event = entry.event
        glyph, style = SIGNAL_STYLE.get(event.signal, _UNKNOWN_SIGNAL)
        line = Text(event.name, style="yellow" if event.signal == "annotation" else "")
        if event.detail:
            line.append(f"  {event.detail}", style="dim")
        if entry.count > 1:
            line.append(f"  x{entry.count}", style="dim italic")
        table.add_row(
            _ago(event.ts, now) if event.ts else "—",
            Text(f"{glyph} {event.signal}", style=style),
            line,
            labels.get(event.run_id) or event.run_id[-6:],
        )
    return Panel(table, title="Events", border_style="cyan")


def render_header(snapshot: Snapshot, opts: Options) -> Panel:
    """The one-line status header: project, status counts, freshness."""
    counts: dict[str, int] = {}
    for run in snapshot.runs:
        counts[run.status] = counts.get(run.status, 0) + 1
    text = Text()
    text.append("hiloop fleet", style="bold")
    text.append(f"  ·  project {snapshot.project_name}", style="cyan")
    if opts.label_prefix:
        text.append(f"  ·  label {opts.label_prefix}*", style="dim")
    for status in ("running", "pending", "succeeded", "failed", "canceled"):
        if status in counts:
            glyph, style = STATUS_STYLE[status]
            text.append(f"   {glyph} {counts[status]} {status}", style=style)
    text.append(f"   ·   {snapshot.fetched_at.strftime('%H:%M:%S')} UTC", style="dim")
    return Panel(text, border_style="bright_black")


def compose(
    snapshot: Snapshot, opts: Options, *, width: int, height: int, stack: bool = False
) -> RenderableType:
    """Assemble the panels: two columns full-screen, a single stack when narrow or printing.

    ``stack`` forces the vertical arrangement — ``--once`` uses it so a printed snapshot
    shows every panel in full instead of cropping to the terminal height.
    """
    now = snapshot.fetched_at
    header = render_header(snapshot, opts)
    fleet = render_fleet(snapshot, now, max_rows=opts.max_fleet_rows)
    tree = render_tree(snapshot, now)
    board = render_leaderboard(snapshot, now, opts)
    ticker = render_ticker(snapshot, now)
    if stack or width < _NARROW_WIDTH:
        return Group(header, fleet, tree, board, ticker)
    layout = Layout()
    ticker_size = max(6, min(12, height - 24))
    layout.split_column(
        Layout(header, name="header", size=3),
        Layout(name="body"),
        Layout(ticker, name="ticker", size=ticker_size),
    )
    layout["body"].split_row(Layout(fleet, name="fleet", ratio=5), Layout(name="right", ratio=4))
    layout["right"].split_column(
        Layout(tree, name="tree", ratio=1), Layout(board, name="board", ratio=1)
    )
    return layout


# --- entrypoint ----------------------------------------------------------------------------------


def _resolve_project_id(cli: HiloopCli) -> tuple[str | None, str | None]:
    """Resolve the project slug to its UUID once (the events SQL filters on the raw id)."""
    try:
        record = cli.project_record().get("project", {})
    except CliError as err:
        return None, str(err)
    pid = str(record.get("id", "")) or None
    return pid, None if pid else "project record carried no id"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse dashboard flags."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("HILOOP_PROJECT", ""),
        help="project slug to watch (defaults to $HILOOP_PROJECT)",
    )
    parser.add_argument(
        "--schema",
        default="demo.experiment.v1",
        help="annotation schema whose ann_* view feeds the leaderboard",
    )
    parser.add_argument(
        "--score-field",
        default="score",
        help="dotted path to the numeric score inside the annotation payload (e.g. metric.value)",
    )
    parser.add_argument(
        "--direction",
        choices=("higher", "lower"),
        default="higher",
        help="whether a higher or lower score wins the leaderboard",
    )
    parser.add_argument(
        "--label-prefix", default="", help="only show runs whose label starts with this prefix"
    )
    parser.add_argument(
        "--since", default="", help="only runs created in this window (e.g. 2h, 3d; server-side)"
    )
    parser.add_argument(
        "--ticker-since", default="2h", help="events-ticker lookback window (e.g. 30m, 2h)"
    )
    parser.add_argument(
        "--refresh", type=float, default=2.0, help="seconds between refreshes (live mode)"
    )
    parser.add_argument(
        "--page-size", type=int, default=200, help="runs fetched per refresh (one wire page)"
    )
    parser.add_argument(
        "--max-fleet-rows", type=int, default=30, help="fleet-table row cap per refresh"
    )
    parser.add_argument(
        "--hiloop-bin",
        default=os.environ.get("HILOOP_BIN", "hiloop"),
        help="hiloop binary to invoke (defaults to $HILOOP_BIN, then `hiloop` on PATH)",
    )
    parser.add_argument(
        "--once", action="store_true", help="print a single snapshot and exit (tests/CI)"
    )
    args = parser.parse_args(argv)
    if not args.project:
        parser.error("--project is required (or set HILOOP_PROJECT)")
    try:
        args.ticker_window = parse_since(args.ticker_since)
    except ValueError as err:
        parser.error(str(err))
    return args


def main(argv: list[str] | None = None) -> int:
    """Run the dashboard: one printed snapshot with ``--once``, else the live loop."""
    args = parse_args(argv)
    opts = Options(
        project=args.project,
        schema=args.schema,
        score_field=args.score_field,
        higher_is_better=args.direction == "higher",
        label_prefix=args.label_prefix,
        since=args.since,
        ticker_since=args.ticker_window,
        page_size=args.page_size,
        max_fleet_rows=args.max_fleet_rows,
    )
    cli = HiloopCli(bin_path=args.hiloop_bin, project=args.project)
    console = Console()
    project_id, project_err = _resolve_project_id(cli)

    if args.once:
        snapshot = collect(cli, opts, project_id=project_id, project_id_error=project_err)
        console.print(compose(snapshot, opts, width=console.width, height=0, stack=True))
        if snapshot.runs_error:
            console.print(Text(f"runs listing failed: {snapshot.runs_error}", style="red"))
            return 1
        return 0

    try:
        with Live(console=console, screen=True, auto_refresh=False) as live:
            while True:
                started = time.monotonic()
                snapshot = collect(cli, opts, project_id=project_id, project_id_error=project_err)
                live.update(
                    compose(snapshot, opts, width=console.width, height=console.height),
                    refresh=True,
                )
                time.sleep(max(0.0, args.refresh - (time.monotonic() - started)))
    except KeyboardInterrupt:
        console.print("bye — the fleet keeps running; `hiloop runs list` to check on it")
        return 0


if __name__ == "__main__":
    sys.exit(main())
