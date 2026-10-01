"""Aggregation and output formatting for tempo.

:func:`report` turns stored sessions into a :class:`Report`; a *formatter*
turns a :class:`Report` into a string.  Formatters live in a registry, so
adding an output format does not mean editing this module -- see
:func:`register_formatter`.

NOTE(mdc): every bucket boundary here (day, week, month) is computed from
local time via ``datetime.fromtimestamp``, using whatever timezone the machine
is in *when the report runs*, not the one it was in when the session was
logged.  Sessions are stored as UTC timestamps, so nothing is lost, but a
report run from a different timezone will move work across day boundaries and
the daily totals will not match what you saw at the time.  The same applies to
the hour either side of a DST change.  It has not bitten me but it will bite
somebody.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Sequence

from .storage import Session, Store, TempoError
from .timeparse import (
    format_duration,
    format_moment,
    humanize_range,
    month_bounds,
    round_seconds,
    week_bounds,
)

__all__ = [
    "Report",
    "ReportRow",
    "report",
    "render",
    "register_formatter",
    "unregister_formatter",
    "get_formatter",
    "available_formatters",
    "GROUP_BY_CHOICES",
    "Formatter",
]

#: What ``--group-by`` will accept.
GROUP_BY_CHOICES = ("tag", "day", "week", "month", "tag,day", "none")

#: A formatter takes a finished report and returns text.  Keyword arguments
#: are passed straight through from the caller, so a formatter should accept
#: ``**options`` and ignore what it does not recognise.
Formatter = Callable[..., str]

_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
}


# --------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ReportRow:
    """One line of a report: a group, its total, and how it got there."""

    key: str
    label: str
    seconds: float
    count: int
    tags: tuple[str, ...] = ()
    amount: float | None = None

    def share(self, total: float) -> float:
        """This row's fraction of ``total``, between 0 and 1."""
        return (self.seconds / total) if total else 0.0

    def to_dict(self, total: float = 0.0) -> dict[str, Any]:
        """A JSON-safe dict, as emitted by the ``json`` formatter."""
        data: dict[str, Any] = {
            "key": self.key,
            "label": self.label,
            "seconds": round(self.seconds, 3),
            "hours": round(self.seconds / 3600, 4),
            "duration": format_duration(self.seconds),
            "sessions": self.count,
            "tags": list(self.tags),
            "share": round(self.share(total), 4),
        }
        if self.amount is not None:
            data["amount"] = round(self.amount, 2)
        return data


@dataclass(frozen=True)
class Report:
    """The result of :func:`report`.

    ``rows`` are already sorted and, if ``--limit`` was used, already
    truncated; ``total_seconds`` is the total *before* truncation, so a
    limited report still tells you the real total.
    """

    rows: tuple[ReportRow, ...]
    total_seconds: float
    since: datetime
    until: datetime
    group_by: str = "tag"
    round_to: int = 0
    rate: float | None = None
    currency: str = "USD"
    session_count: int = 0
    truncated: int = 0
    running: Session | None = None
    sessions: tuple[Session, ...] = field(default=(), repr=False)

    @property
    def total_amount(self) -> float | None:
        """Billable total, or ``None`` when no rate was given."""
        if self.rate is None:
            return None
        return sum((r.amount or 0.0) for r in self.rows)

    @property
    def empty(self) -> bool:
        """True when nothing was logged in the window."""
        return not self.rows

    def title(self) -> str:
        """The one-line window description printed above a table."""
        return humanize_range(self.since, self.until)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe dict.  This is exactly what ``--json`` prints."""
        data: dict[str, Any] = {
            "since": format_moment(self.since),
            "until": format_moment(self.until),
            "group_by": self.group_by,
            "rows": [r.to_dict(self.total_seconds) for r in self.rows],
            "total_seconds": round(self.total_seconds, 3),
            "total_hours": round(self.total_seconds / 3600, 4),
            "total_duration": format_duration(self.total_seconds),
            "sessions": self.session_count,
        }
        if self.round_to:
            data["round_minutes"] = self.round_to
        if self.rate is not None:
            data["rate"] = self.rate
            data["currency"] = self.currency
            data["total_amount"] = round(self.total_amount or 0.0, 2)
        if self.truncated:
            data["rows_omitted"] = self.truncated
        if self.running is not None:
            data["running"] = self.running.to_dict()
        return data


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------

def report(store: Store,
           since: datetime | None = None,
           until: datetime | None = None,
           tags: Sequence[str] | None = None,
           group_by: str = "tag",
           round_to: int = 0,
           rate: float | None = None,
           currency: str = "USD",
           limit: int | None = None,
           week_start: str = "monday",
           include_running: bool = False,
           now: datetime | None = None) -> Report:
    """Aggregate stored sessions into a :class:`Report`.

    ``since`` and ``until`` default to the start of today and now, which is
    where ``tempo report`` with no flags gets its behaviour.  ``round_to`` is
    a number of minutes and is applied to each session individually before
    summing (see :func:`tempo.timeparse.round_seconds`).  ``include_running``
    folds the currently running session in, measured up to ``now``.
    """
    if group_by not in GROUP_BY_CHOICES:
        raise TempoError(
            f"unknown --group-by: {group_by!r} "
            f"(choose from {', '.join(GROUP_BY_CHOICES)})"
        )

    now = now or datetime.now()
    if since is None:
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if until is None:
        until = now
    if until < since:
        raise TempoError("--until is before --since")

    sessions = list(store.query(since=since, until=until, tags=tags))

    running = store.current()
    if running is not None and include_running:
        in_window = since.timestamp() <= running.start < until.timestamp()
        matches_tag = (not tags) or running.tag in set(tags)
        if in_window and matches_tag:
            sessions.append(
                Session(tag=running.tag, start=running.start,
                        end=now.timestamp(), note=running.note)
            )

    buckets: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    total = 0.0

    for session in sessions:
        seconds = round_seconds(session.duration(now.timestamp()), round_to)
        total += seconds
        for key, label in _bucket(session, group_by, week_start):
            if key not in buckets:
                buckets[key] = {"label": label, "seconds": 0.0,
                                "count": 0, "tags": set()}
                order.append(key)
            bucket = buckets[key]
            bucket["seconds"] += seconds
            bucket["count"] += 1
            bucket["tags"].add(session.tag)

    rows = [
        ReportRow(
            key=key,
            label=buckets[key]["label"],
            seconds=buckets[key]["seconds"],
            count=buckets[key]["count"],
            tags=tuple(sorted(buckets[key]["tags"])),
            amount=(None if rate is None
                    else buckets[key]["seconds"] / 3600 * rate),
        )
        for key in order
    ]
    rows = _sort_rows(rows, group_by)

    truncated = 0
    if limit and limit > 0 and len(rows) > limit:
        truncated = len(rows) - limit
        rows = rows[:limit]

    return Report(
        rows=tuple(rows),
        total_seconds=total,
        since=since,
        until=until,
        group_by=group_by,
        round_to=round_to,
        rate=rate,
        currency=currency,
        session_count=len(sessions),
        truncated=truncated,
        running=running,
        sessions=tuple(sessions),
    )


def _bucket(session: Session, group_by: str,
            week_start: str) -> list[tuple[str, str]]:
    """The (key, label) pairs a session contributes to."""
    started = session.started_at
    if group_by == "tag":
        return [(session.tag, session.tag)]
    if group_by == "day":
        key = started.strftime("%Y-%m-%d")
        return [(key, f"{key} {started.strftime('%a')}")]
    if group_by == "week":
        start, _ = week_bounds(started, week_start)
        key = start.strftime("%Y-%m-%d")
        return [(key, f"week of {key}")]
    if group_by == "month":
        start, _ = month_bounds(started)
        return [(start.strftime("%Y-%m"), start.strftime("%B %Y"))]
    if group_by == "tag,day":
        day = started.strftime("%Y-%m-%d")
        return [(f"{session.tag}\t{day}", f"{session.tag}  {day}")]
    # "none": every session is its own row, which is how `report --group-by
    # none` doubles as a log view.
    ended = session.ended_at
    finish = ended.strftime("%H:%M") if ended is not None else "...."
    label = f"{format_moment(started)}-{finish}  {session.tag}"
    return [(f"{session.start:015.0f}", label)]


def _sort_rows(rows: list[ReportRow], group_by: str) -> list[ReportRow]:
    """Biggest first for tags, chronological for anything time-shaped."""
    if group_by in ("day", "week", "month", "none"):
        return sorted(rows, key=lambda r: r.key)
    return sorted(rows, key=lambda r: (-r.seconds, r.label))


# --------------------------------------------------------------------------
# Formatter registry
# --------------------------------------------------------------------------

_FORMATTERS: dict[str, Formatter] = {}


def register_formatter(name: str, fn: Formatter,
                       replace: bool = False) -> Formatter:
    """Register an output format under ``name``.

    A formatter is any callable taking a :class:`Report` and returning a
    string; extra keyword arguments (``color``, ``duration_style`` and
    whatever the caller passes) arrive as keywords, so accept ``**options``
    and ignore the ones you do not care about::

        from tempo import register_formatter

        def one_line(rep, **options):
            return f"{rep.title()}: {rep.total_seconds / 3600:.2f}h"

        register_formatter("oneline", one_line)

    Registering over an existing name raises unless ``replace`` is true; that
    is deliberate, because two plugins quietly fighting over ``table`` is not
    a debugging session anyone enjoys.  Returns ``fn``, so it also works as a
    decorator factory.
    """
    key = str(name).strip().lower()
    if not key:
        raise ValueError("a formatter needs a name")
    if not callable(fn):
        raise TypeError(f"formatter {key!r} is not callable")
    if key in _FORMATTERS and not replace:
        raise ValueError(f"formatter {key!r} is already registered")
    _FORMATTERS[key] = fn
    return fn


def unregister_formatter(name: str) -> None:
    """Remove a formatter.  Unknown names are ignored."""
    _FORMATTERS.pop(str(name).strip().lower(), None)


def get_formatter(name: str) -> Formatter:
    """Look up a formatter by name.  Raises :class:`TempoError` if unknown."""
    key = str(name).strip().lower()
    try:
        return _FORMATTERS[key]
    except KeyError:
        raise TempoError(
            f"unknown format: {name} "
            f"(available: {', '.join(available_formatters())})"
        ) from None


def available_formatters() -> list[str]:
    """Every registered formatter name, sorted."""
    return sorted(_FORMATTERS)


def render(rep: Report, name: str = "table", **options: Any) -> str:
    """Format a report.  Shorthand for ``get_formatter(name)(rep, **options)``."""
    return get_formatter(name)(rep, **options)


# --------------------------------------------------------------------------
# Built-in formatters
# --------------------------------------------------------------------------

def format_table(rep: Report, color: bool | None = None,
                 duration_style: str = "short",
                 show_share: bool = True, **options: Any) -> str:
    """The default human-readable table."""
    paint = _painter(color)
    if rep.empty:
        return paint(_empty_message(rep), "dim")

    headers = ["", "time", "n"]
    if show_share:
        headers.append("share")
    if rep.rate is not None:
        headers.append(rep.currency)

    body: list[list[str]] = []
    for row in rep.rows:
        line = [
            row.label,
            format_duration(row.seconds, duration_style),
            str(row.count),
        ]
        if show_share:
            line.append(f"{row.share(rep.total_seconds) * 100:.0f}%")
        if rep.rate is not None:
            line.append(f"{row.amount or 0.0:,.2f}")
        body.append(line)

    footer = [
        "total",
        format_duration(rep.total_seconds, duration_style),
        str(rep.session_count),
    ]
    if show_share:
        footer.append("")
    if rep.rate is not None:
        footer.append(f"{rep.total_amount or 0.0:,.2f}")

    widths = [
        max(len(str(cell)) for cell in column)
        for column in zip(headers, footer, *body)
    ]

    out: list[str] = [paint(rep.title(), "bold")]
    out.append(paint(_row_text(headers, widths), "dim"))
    out.append(paint("-" * (sum(widths) + 2 * (len(widths) - 1)), "dim"))
    for line in body:
        out.append(_row_text(line, widths))
    out.append(paint("-" * (sum(widths) + 2 * (len(widths) - 1)), "dim"))
    out.append(paint(_row_text(footer, widths), "bold"))

    if rep.truncated:
        out.append(paint(f"({rep.truncated} more rows not shown)", "dim"))
    if rep.round_to:
        out.append(paint(
            f"(each session rounded up to {rep.round_to} minutes)", "dim"))
    if rep.running is not None:
        out.append(paint(
            f"* {rep.running.tag} is still running "
            f"({format_duration(rep.running.duration())} so far)", "yellow"))
    return "\n".join(out)


def format_csv(rep: Report, **options: Any) -> str:
    """Comma-separated rows, header included.  Suitable for a spreadsheet."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    header = ["label", "seconds", "hours", "sessions", "tags"]
    if rep.rate is not None:
        header.append("amount")
    writer.writerow(header)
    for row in rep.rows:
        line: list[Any] = [
            row.label,
            f"{row.seconds:.0f}",
            f"{row.seconds / 3600:.2f}",
            row.count,
            ";".join(row.tags),
        ]
        if rep.rate is not None:
            line.append(f"{row.amount or 0.0:.2f}")
        writer.writerow(line)
    return buffer.getvalue().rstrip("\n")


def format_json(rep: Report, indent: int = 2, **options: Any) -> str:
    """The whole report as JSON, shaped like :meth:`Report.to_dict`."""
    return json.dumps(rep.to_dict(), indent=indent, sort_keys=False)


def format_total(rep: Report, duration_style: str = "short",
                 **options: Any) -> str:
    """Just the total, for shell prompts and status bars."""
    return format_duration(rep.total_seconds, duration_style)


def format_markdown(rep: Report, duration_style: str = "short",
                    **options: Any) -> str:
    """A GitHub-flavoured Markdown table, for pasting into a ticket."""
    if rep.empty:
        return f"_{_empty_message(rep)}_"
    head = ["| | time | n |", "|---|---:|---:|"]
    lines = [
        f"| {row.label} | {format_duration(row.seconds, duration_style)} "
        f"| {row.count} |"
        for row in rep.rows
    ]
    total = (f"| **total** | **"
             f"{format_duration(rep.total_seconds, duration_style)}** "
             f"| **{rep.session_count}** |")
    return "\n".join([f"**{rep.title()}**", ""] + head + lines + [total])


register_formatter("table", format_table)
register_formatter("csv", format_csv)
register_formatter("json", format_json)
register_formatter("total", format_total)
register_formatter("markdown", format_markdown)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _row_text(cells: Sequence[str], widths: Sequence[int]) -> str:
    """Left-align the first column, right-align the numeric rest."""
    parts = [str(cells[0]).ljust(widths[0])]
    parts.extend(
        str(cell).rjust(width)
        for cell, width in zip(cells[1:], widths[1:])
    )
    return "  ".join(parts).rstrip()


def _empty_message(rep: Report) -> str:
    """What to say when a window has nothing in it.

    Worth its own function: "no sessions" on its own sends people looking for
    lost data, when the real answer is almost always that the window is
    narrower than they think.
    """
    return f"nothing logged for {rep.title()}"


def _painter(color: bool | None) -> Callable[[str, str], str]:
    """Return a paint(text, style) function, honouring --no-color and NO_COLOR."""
    enabled = _color_enabled(color)

    def paint(text: str, style: str) -> str:
        if not enabled or style not in _ANSI:
            return text
        return f"{_ANSI[style]}{text}{_ANSI['reset']}"

    return paint


def _color_enabled(color: bool | None) -> bool:
    """Decide whether to emit ANSI codes.

    ``--no-color`` and ``--json``/``--csv`` force it off; otherwise we follow
    the NO_COLOR convention and then fall back to "is stdout a terminal".
    """
    if color is not None:
        return bool(color)
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def sessions_to_rows(sessions: Iterable[Session]) -> list[dict[str, Any]]:
    """Flatten sessions into dicts, as used by ``tempo export --format csv``."""
    return [s.to_dict() for s in sessions]


def window_for(flag: str, now: datetime,
               week_start: str = "monday") -> tuple[datetime, datetime]:
    """The window meant by ``-w``/``-m``, or by no flag at all.

    ``flag`` is ``"week"``, ``"month"`` or ``"today"``.  Anything else is a
    programming error rather than user input, so it raises ``ValueError``.
    """
    if flag == "week":
        return week_bounds(now, week_start)
    if flag == "month":
        return month_bounds(now)
    if flag == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    raise ValueError(f"unknown window: {flag!r}")
