"""The ``tempo`` command line.

tempo: track time against project tags from the terminal.
Started this as a way to stop guessing on invoices. -- mdc, Jan

NOTE(mdc): `tempo start` writes to ``$TEMPO_HOME/current``. If that file
already exists we bail out rather than clobber it. People hit this constantly
when a shell dies mid-session -- tell them about `tempo abort`.

The layout of this module: a parser builder, then one ``cmd_*`` function per
subcommand, then :func:`main`, which wires them together and turns our own
exceptions into an exit code and a one-line message on stderr.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence, TextIO

from . import __version__
from .reporting import (
    GROUP_BY_CHOICES,
    available_formatters,
    render,
    report,
)
from .storage import (
    DEFAULT_CONFIG,
    NoSessionRunning,
    SchemaTooOld,
    Session,
    SessionNotFound,
    SessionRunning,
    Store,
    TempoError,
)
from .timeparse import (
    TimeParseError,
    format_duration,
    format_moment,
    month_bounds,
    parse_moment,
    parse_since,
    parse_until,
    week_bounds,
)

__all__ = ["main", "build_parser"]

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

#: Values for the global flags when they are not given anywhere.  The flags
#: are defined with ``argparse.SUPPRESS`` so that ``tempo --json report`` and
#: ``tempo report --json`` can both work without the second parse wiping out
#: the first; the cost is that we have to fill the defaults in ourselves.
GLOBAL_DEFAULTS: dict[str, Any] = {
    "home": None,
    "db": None,
    "no_color": False,
    "verbose": 0,
    "quiet": False,
    "json": False,
}


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

class Console:
    """Everything tempo prints goes through one of these.

    Four levels: :meth:`out` is the answer to the question that was asked and
    is never suppressed; :meth:`info` is conversational confirmation and is
    silenced by ``--quiet``; :meth:`detail` only appears with ``--verbose``;
    :meth:`warn` and :meth:`error` go to stderr.
    """

    def __init__(self, quiet: bool = False, verbose: int = 0,
                 stdout: TextIO | None = None, stderr: TextIO | None = None):
        self.quiet = quiet
        self.verbose = verbose
        self.stdout = stdout or sys.stdout
        self.stderr = stderr or sys.stderr

    def out(self, text: str = "") -> None:
        """Print a result."""
        print(text, file=self.stdout)

    def info(self, text: str) -> None:
        """Print a confirmation, unless ``--quiet``."""
        if not self.quiet:
            print(text, file=self.stdout)

    def detail(self, text: str) -> None:
        """Print a diagnostic, only under ``--verbose``."""
        if self.verbose:
            print(f"tempo: {text}", file=self.stderr)

    def warn(self, text: str) -> None:
        """Print a warning to stderr.  ``--quiet`` does not hide warnings."""
        print(f"tempo: {text}", file=self.stderr)

    def error(self, text: str) -> None:
        """Print an error to stderr."""
        print(f"tempo: {text}", file=self.stderr)


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

def _global_parser() -> argparse.ArgumentParser:
    """The flags that are accepted before *and* after the subcommand."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--home", metavar="DIR", default=argparse.SUPPRESS,
        help="use this directory instead of $TEMPO_HOME or ~/.tempo")
    parser.add_argument(
        "--db", metavar="FILE", default=argparse.SUPPRESS,
        help="use this database file (overrides --home for the database only)")
    parser.add_argument(
        "--no-color", action="store_true", default=argparse.SUPPRESS,
        help="never emit ANSI colour")
    parser.add_argument(
        "-v", "--verbose", action="count", default=argparse.SUPPRESS,
        help="explain what is being read and written")
    parser.add_argument(
        "-q", "--quiet", action="store_true", default=argparse.SUPPRESS,
        help="print results only, no confirmations")
    parser.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS,
        help="machine-readable output")
    return parser


def build_parser() -> argparse.ArgumentParser:
    """Build the whole command-line parser."""
    common = _global_parser()
    parser = argparse.ArgumentParser(
        prog="tempo",
        parents=[common],
        description="Track time against project tags.",
    )
    parser.add_argument("--version", action="version",
                        version=f"tempo {__version__}")
    sub = parser.add_subparsers(dest="cmd", metavar="COMMAND")

    # -- start ------------------------------------------------------------
    start = sub.add_parser(
        "start", parents=[common], help="begin a session")
    start.add_argument("tag", help="project tag, e.g. thesis")
    start.add_argument("--at", metavar="TIME",
                       help="backdate the start, e.g. '9:15am'")
    start.add_argument("-m", "--note", metavar="TEXT",
                       help="a note to store with the session")
    start.set_defaults(func=cmd_start)

    # -- stop -------------------------------------------------------------
    stop = sub.add_parser(
        "stop", parents=[common], help="end the running session")
    stop.add_argument("--at", metavar="TIME",
                      help="backdate the end, e.g. '5pm friday'")
    stop.add_argument("-m", "--note", metavar="TEXT",
                      help="replace the session's note")
    stop.set_defaults(func=cmd_stop)

    # -- abort ------------------------------------------------------------
    abort = sub.add_parser(
        "abort", parents=[common],
        help="discard the running session without logging it")
    abort.set_defaults(func=cmd_abort)

    # -- status -----------------------------------------------------------
    status = sub.add_parser(
        "status", parents=[common], help="show the running session, if any")
    status.add_argument(
        "--exit-code", action="store_true",
        help="exit 1 when nothing is running (for shell prompts)")
    status.set_defaults(func=cmd_status)

    # -- report -----------------------------------------------------------
    rep = sub.add_parser(
        "report", parents=[common], help="summarize logged time")
    # -w is weekly, -m monthly.  Kept short because I type this 20x a day.
    window = rep.add_mutually_exclusive_group()
    window.add_argument("-w", "--week", action="store_true",
                        help="this week instead of today")
    window.add_argument("-m", "--month", action="store_true",
                        help="this calendar month instead of today")
    rep.add_argument("--since", metavar="TIME",
                     help="start of the window: an ISO date or a duration "
                          "like 3d")
    rep.add_argument("--until", metavar="TIME",
                     help="end of the window (exclusive)")
    rep.add_argument("--tag", metavar="TAG", action="append", dest="tags",
                     help="only this tag; repeat for several")
    rep.add_argument("--group-by", metavar="WHAT", default=None,
                     choices=GROUP_BY_CHOICES,
                     help="one of: " + ", ".join(GROUP_BY_CHOICES))
    rep.add_argument("--csv", action="store_true",
                     help="machine-readable output")
    rep.add_argument("--format", metavar="NAME", dest="fmt", default=None,
                     help="a registered formatter: "
                          + ", ".join(available_formatters())
                          + " (plugins may add more)")
    rep.add_argument("--round", metavar="MINUTES", type=int, default=None,
                     dest="round_to",
                     help="round each session up to a multiple of MINUTES")
    rep.add_argument("--billable-rate", metavar="RATE", type=float,
                     default=None, dest="rate",
                     help="also show money, at RATE per hour")
    rep.add_argument("--limit", metavar="N", type=int, default=None,
                     help="show at most N rows")
    rep.add_argument("--no-running", action="store_true",
                     help="leave the currently running session out")
    rep.set_defaults(func=cmd_report)

    # -- tags -------------------------------------------------------------
    tags = sub.add_parser(
        "tags", parents=[common], help="list the tags you have used")
    tags.add_argument("--since", metavar="TIME",
                      help="only tags used since then (default: all time)")
    tags.add_argument("--until", metavar="TIME", help="only tags used before then")
    tags.add_argument("--limit", metavar="N", type=int, default=None,
                      help="show at most N tags")
    tags.add_argument("--csv", action="store_true",
                      help="machine-readable output")
    tags.set_defaults(func=cmd_tags)

    # -- edit -------------------------------------------------------------
    edit = sub.add_parser(
        "edit", parents=[common], help="change a stored session")
    edit.add_argument("id", type=int, help="session id, as shown by report")
    edit.add_argument("--tag", metavar="TAG", help="move it to another tag")
    edit.add_argument("--start", metavar="TIME", help="new start time")
    edit.add_argument("--end", metavar="TIME", help="new end time")
    edit.add_argument("-m", "--note", metavar="TEXT", help="replace the note")
    edit.set_defaults(func=cmd_edit)

    # -- rm ---------------------------------------------------------------
    remove = sub.add_parser(
        "rm", parents=[common], help="delete stored sessions")
    remove.add_argument("ids", type=int, nargs="+", metavar="ID",
                        help="one or more session ids")
    remove.add_argument("-f", "--force", action="store_true",
                        help="do not ask for confirmation")
    remove.set_defaults(func=cmd_rm)

    # -- export -----------------------------------------------------------
    export = sub.add_parser(
        "export", parents=[common], help="write sessions out")
    export.add_argument("--since", metavar="TIME",
                        help="only sessions since then (default: all time)")
    export.add_argument("--until", metavar="TIME", help="only sessions before then")
    export.add_argument("--tag", metavar="TAG", action="append", dest="tags",
                        help="only this tag; repeat for several")
    export.add_argument("--format", metavar="NAME", dest="fmt",
                        choices=("jsonl", "json", "csv"), default="jsonl",
                        help="jsonl (default), json or csv")
    export.add_argument("-o", "--output", metavar="FILE",
                        help="write here instead of stdout")
    export.set_defaults(func=cmd_export)

    # -- import -----------------------------------------------------------
    load = sub.add_parser(
        "import", parents=[common], help="read sessions in")
    load.add_argument("file", help="a file written by tempo export, or - for stdin")
    load.add_argument("--format", metavar="NAME", dest="fmt",
                      choices=("auto", "jsonl", "json", "csv"), default="auto",
                      help="auto (default), jsonl, json or csv")
    load.add_argument("--dry-run", action="store_true",
                      help="say what would be imported, change nothing")
    load.set_defaults(func=cmd_import)

    # -- config -----------------------------------------------------------
    config = sub.add_parser(
        "config", parents=[common], help="read and write settings")
    config.add_argument(
        "action", nargs="?", default="list",
        choices=("list", "get", "set", "unset", "path"),
        help="list (default), get, set, unset or path")
    config.add_argument("key", nargs="?", help="a setting name")
    config.add_argument("value", nargs="?", help="the new value, for set")
    config.set_defaults(func=cmd_config)

    return parser


def _apply_global_defaults(args: argparse.Namespace) -> argparse.Namespace:
    """Fill in the global flags that neither parse happened to set."""
    for name, default in GLOBAL_DEFAULTS.items():
        if not hasattr(args, name):
            setattr(args, name, default)
    return args


# --------------------------------------------------------------------------
# Commands: the running session
# --------------------------------------------------------------------------

def cmd_start(args: argparse.Namespace, store: Store,
              console: Console) -> int:
    """``tempo start TAG [--at TIME] [-m NOTE]``."""
    at = _moment(args.at) if args.at else None
    try:
        session = store.start(args.tag, at=at, note=args.note)
    except SessionRunning as exc:
        running = exc.session
        console.error(str(exc))
        console.error(
            f"  it started {format_moment(running.started_at)} "
            f"({format_duration(running.duration())} ago)")
        console.error("  `tempo stop` to log it, `tempo abort` to discard it")
        return EXIT_ERROR

    if args.json:
        console.out(json.dumps(session.to_dict(), indent=2))
    else:
        console.info(
            f"started {session.tag} at {format_moment(session.started_at)}")
    if at is not None:
        console.detail(f"backdated by {format_duration(session.duration())}")
    return EXIT_OK


def cmd_stop(args: argparse.Namespace, store: Store, console: Console) -> int:
    """``tempo stop [--at TIME] [-m NOTE]``."""
    at = _moment(args.at) if args.at else None
    try:
        session = store.stop(at=at, note=args.note)
    except NoSessionRunning:
        console.error("no session running")
        console.error("  `tempo start TAG` to begin one")
        return EXIT_ERROR

    if args.json:
        console.out(json.dumps(session.to_dict(), indent=2))
    else:
        console.info(
            f"stopped {session.tag} after "
            f"{format_duration(session.duration())} (id {session.id})")

    overlaps = store.find_overlaps(session)
    if overlaps:
        console.warn(
            f"this session overlaps {len(overlaps)} already logged "
            f"({', '.join(sorted({o.tag for o in overlaps}))})")
    return EXIT_OK


def cmd_abort(args: argparse.Namespace, store: Store, console: Console) -> int:
    """``tempo abort`` -- throw the running session away."""
    try:
        session = store.abort()
    except NoSessionRunning:
        console.error("no session running")
        return EXIT_ERROR

    if args.json:
        console.out(json.dumps(session.to_dict(), indent=2))
    else:
        console.info(
            f"discarded {session.tag} "
            f"({format_duration(session.duration())}, not logged)")
    return EXIT_OK


def cmd_status(args: argparse.Namespace, store: Store,
               console: Console) -> int:
    """``tempo status`` -- what is running, if anything."""
    session = store.current()

    if session is None:
        if args.json:
            console.out(json.dumps({"running": False}, indent=2))
        else:
            console.info("no session running")
        return EXIT_ERROR if args.exit_code else EXIT_OK

    if args.json:
        payload = session.to_dict()
        payload["running"] = True
        console.out(json.dumps(payload, indent=2))
        return EXIT_OK

    console.out(
        f"{session.tag}  {format_duration(session.duration())}  "
        f"(since {format_moment(session.started_at)})")
    if session.note:
        console.out(f"  note: {session.note}")
    console.detail(f"current file: {store.current_path}")
    return EXIT_OK


# --------------------------------------------------------------------------
# Commands: reporting
# --------------------------------------------------------------------------

def cmd_report(args: argparse.Namespace, store: Store,
               console: Console) -> int:
    """``tempo report`` -- the one everybody runs.

    With no window flags this reports *today only*, from local midnight to
    now.  That is the single most surprising thing about tempo: people assume
    it is all-time, see an empty table, and conclude their data is gone.
    """
    settings = store.config_all()
    now = datetime.now()
    since, until = _report_window(args, settings, now)

    rep = report(
        store,
        since=since,
        until=until,
        tags=args.tags,
        group_by=args.group_by or settings["group_by"],
        round_to=_round_minutes(args, settings),
        rate=_rate(args, settings),
        currency=settings["currency"],
        limit=args.limit,
        week_start=settings["week_start"],
        include_running=not args.no_running,
        now=now,
    )

    fmt = _output_format(args, settings)
    console.detail(
        f"window {format_moment(since)} .. {format_moment(until)}, "
        f"{rep.session_count} sessions, format {fmt}")

    text = render(
        rep, fmt,
        color=_color_choice(args, settings),
        duration_style=settings["duration_style"],
    )
    if text:
        console.out(text)

    if rep.empty and fmt == "table" and not args.quiet:
        _explain_empty(store, console, since, until)
    return EXIT_OK


def _report_window(args: argparse.Namespace, settings: dict[str, str],
                   now: datetime) -> tuple[datetime, datetime]:
    """Turn the window flags into a concrete half-open interval."""
    if (args.week or args.month) and (args.since or args.until):
        raise TempoError("-w/-m and --since/--until cannot be combined")

    if args.week:
        return week_bounds(now, settings["week_start"])
    if args.month:
        return month_bounds(now)

    if args.since or args.until:
        since = (parse_since(args.since, now=now) if args.since
                 else datetime.fromtimestamp(0))
        until = parse_until(args.until, now=now) if args.until else now
        return since, until

    # The default: today, local midnight to now.
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _explain_empty(store: Store, console: Console,
                   since: datetime, until: datetime) -> None:
    """Say something factual when a report comes back empty.

    An empty table on its own is the most common way tempo looks broken, so
    we at least name the database we looked in and say whether there is
    anything in it at all.
    """
    span = store.span()
    if span is None:
        console.warn("nothing has ever been logged in this tempo home: "
                     f"{store.db_path}")
        return
    first, last = span
    if last < since or first >= until:
        console.warn(
            f"nothing in this window, but {store.count()} sessions are "
            f"stored between {format_moment(first)} and {format_moment(last)}"
        )


def cmd_tags(args: argparse.Namespace, store: Store, console: Console) -> int:
    """``tempo tags`` -- every tag used, busiest first.

    Unlike ``report``, this defaults to all time.  The inconsistency is real
    and is on the list.
    """
    now = datetime.now()
    since = parse_since(args.since, now=now) if args.since else None
    until = parse_until(args.until, now=now) if args.until else None

    summaries = store.tags(since=since, until=until)
    if args.limit and args.limit > 0:
        summaries = summaries[:args.limit]

    if args.json:
        console.out(json.dumps([s.to_dict() for s in summaries], indent=2))
        return EXIT_OK

    if args.csv:
        writer = csv.writer(console.stdout, lineterminator="\n")
        writer.writerow(["tag", "sessions", "seconds", "hours", "last_seen"])
        for summary in summaries:
            writer.writerow([
                summary.tag, summary.count, f"{summary.seconds:.0f}",
                f"{summary.seconds / 3600:.2f}",
                format_moment(summary.last_seen_at),
            ])
        return EXIT_OK

    if not summaries:
        console.info("no tags yet")
        return EXIT_OK

    width = max(len(s.tag) for s in summaries)
    for summary in summaries:
        console.out(
            f"{summary.tag.ljust(width)}  "
            f"{format_duration(summary.seconds).rjust(9)}  "
            f"{str(summary.count).rjust(4)}  "
            f"last {format_moment(summary.last_seen_at)}")
    return EXIT_OK


# --------------------------------------------------------------------------
# Commands: editing
# --------------------------------------------------------------------------

def cmd_edit(args: argparse.Namespace, store: Store, console: Console) -> int:
    """``tempo edit ID`` -- fix a session after the fact."""
    if not any((args.tag, args.start, args.end, args.note)):
        raise TempoError("nothing to change: pass --tag, --start, --end or -m")

    try:
        before = store.get(args.id)
    except SessionNotFound as exc:
        console.error(str(exc))
        return EXIT_ERROR

    after = store.update(
        args.id,
        tag=args.tag,
        start=_moment(args.start) if args.start else None,
        end=_moment(args.end) if args.end else None,
        note=args.note,
    )

    if args.json:
        console.out(json.dumps(
            {"before": before.to_dict(), "after": after.to_dict()}, indent=2))
    else:
        console.info(f"- {_describe(before)}")
        console.info(f"+ {_describe(after)}")

    overlaps = store.find_overlaps(after)
    if overlaps:
        console.warn(
            f"now overlaps {len(overlaps)} other sessions "
            f"({', '.join(str(o.id) for o in overlaps)})")
    return EXIT_OK


def cmd_rm(args: argparse.Namespace, store: Store, console: Console) -> int:
    """``tempo rm ID...`` -- delete sessions.  There is no undo."""
    doomed: list[Session] = []
    for session_id in args.ids:
        try:
            doomed.append(store.get(session_id))
        except SessionNotFound as exc:
            console.error(str(exc))
            return EXIT_ERROR

    if not args.force:
        for session in doomed:
            console.info(f"  {_describe(session)}")
        if not _confirm(f"delete {len(doomed)} session(s)?", console):
            console.info("nothing deleted")
            return EXIT_OK

    removed = store.delete([s.id for s in doomed if s.id is not None])
    if args.json:
        console.out(json.dumps({"deleted": removed}, indent=2))
    else:
        console.info(f"deleted {removed} session(s)")
    return EXIT_OK


def _confirm(question: str, console: Console) -> bool:
    """Ask a yes/no question.  Refuses rather than guesses when not a tty."""
    if not sys.stdin.isatty():
        console.error(f"{question} refusing to guess; pass --force")
        return False
    try:
        answer = input(f"{question} [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


# --------------------------------------------------------------------------
# Commands: import and export
# --------------------------------------------------------------------------

def cmd_export(args: argparse.Namespace, store: Store,
               console: Console) -> int:
    """``tempo export`` -- write sessions out, all time by default."""
    now = datetime.now()
    since = parse_since(args.since, now=now) if args.since else None
    until = parse_until(args.until, now=now) if args.until else None
    sessions = store.query(since=since, until=until, tags=args.tags)

    text = _export_text(sessions, args.fmt)
    if args.output:
        path = Path(args.output).expanduser()
        path.write_text(text + "\n", encoding="utf-8")
        console.info(f"wrote {len(sessions)} sessions to {path}")
    else:
        console.out(text)
    return EXIT_OK


def _export_text(sessions: Sequence[Session], fmt: str) -> str:
    """Serialise sessions as jsonl, json or csv."""
    if fmt == "json":
        return json.dumps([s.to_dict() for s in sessions], indent=2)
    if fmt == "jsonl":
        return "\n".join(json.dumps(s.to_dict()) for s in sessions)
    if fmt == "csv":
        buffer = _StringWriter()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["id", "tag", "start", "end", "note"])
        for session in sessions:
            writer.writerow([session.id, session.tag, session.start,
                             session.end, session.note or ""])
        return buffer.value().rstrip("\n")
    raise TempoError(f"unknown export format: {fmt}")


class _StringWriter:
    """A minimal write-collecting file object for :mod:`csv`."""

    def __init__(self) -> None:
        self._parts: list[str] = []

    def write(self, text: str) -> int:
        self._parts.append(text)
        return len(text)

    def value(self) -> str:
        """Everything written so far."""
        return "".join(self._parts)


def cmd_import(args: argparse.Namespace, store: Store,
               console: Console) -> int:
    """``tempo import FILE`` -- read sessions back in.

    NOTE(mdc): no de-duplication and no id preservation.  Importing the same
    file twice gives you two of everything, and `--dry-run` is the only thing
    standing between a user and that.
    """
    text = _read_input(args.file)
    fmt = args.fmt if args.fmt != "auto" else _sniff_format(args.file, text)
    console.detail(f"reading {args.file} as {fmt}")

    records = _parse_import(text, fmt)
    sessions: list[Session] = []
    skipped = 0
    for index, record in enumerate(records, start=1):
        try:
            session = Session.from_dict(record)
        except ValueError as exc:
            console.warn(f"record {index}: {exc}")
            skipped += 1
            continue
        if session.end is None:
            console.warn(f"record {index}: no end time, skipped")
            skipped += 1
            continue
        sessions.append(session)

    overlapping = sum(1 for s in sessions if store.find_overlaps(s))
    if overlapping:
        console.warn(
            f"{overlapping} of these overlap sessions you already have; "
            f"tempo import does not de-duplicate")

    if args.dry_run:
        console.info(
            f"would import {len(sessions)} sessions "
            f"({skipped} skipped)")
        for session in sessions[:10]:
            console.info(f"  {_describe(session)}")
        if len(sessions) > 10:
            console.info(f"  ... and {len(sessions) - 10} more")
        return EXIT_OK

    added = store.add_many(sessions)
    if args.json:
        console.out(json.dumps(
            {"imported": added, "skipped": skipped,
             "overlapping": overlapping}, indent=2))
    else:
        console.info(f"imported {added} sessions ({skipped} skipped)")
    return EXIT_OK


def _read_input(name: str) -> str:
    """Read a file, or stdin when the name is ``-``."""
    if name == "-":
        return sys.stdin.read()
    path = Path(name).expanduser()
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TempoError(f"cannot read {path}: {exc}") from exc


def _sniff_format(name: str, text: str) -> str:
    """Guess jsonl / json / csv from the extension, then the first character."""
    suffix = Path(name).suffix.lower()
    if suffix in (".jsonl", ".ndjson"):
        return "jsonl"
    if suffix == ".json":
        return "json"
    if suffix in (".csv", ".tsv"):
        return "csv"
    head = text.lstrip()[:1]
    if head == "[":
        return "json"
    if head == "{":
        return "jsonl"
    return "csv"


def _parse_import(text: str, fmt: str) -> list[dict[str, Any]]:
    """Turn imported text into raw dicts, one per session."""
    if fmt == "json":
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise TempoError(f"not valid JSON: {exc}") from exc
        if not isinstance(data, list):
            raise TempoError("expected a JSON array of sessions")
        return data
    if fmt == "jsonl":
        records = []
        for number, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError as exc:
                raise TempoError(f"line {number}: {exc}") from exc
        return records
    if fmt == "csv":
        return list(csv.DictReader(text.splitlines()))
    raise TempoError(f"unknown import format: {fmt}")


# --------------------------------------------------------------------------
# Commands: config
# --------------------------------------------------------------------------

def cmd_config(args: argparse.Namespace, store: Store,
               console: Console) -> int:
    """``tempo config [list|get|set|unset|path]``."""
    action = args.action

    if action == "path":
        if args.json:
            console.out(json.dumps({
                "home": str(store.home),
                "db": str(store.db_path),
                "current": str(store.current_path),
                "TEMPO_HOME": os.environ.get("TEMPO_HOME"),
            }, indent=2))
        else:
            console.out(f"home    {store.home}")
            console.out(f"db      {store.db_path}")
            console.out(f"current {store.current_path}")
        return EXIT_OK

    if action == "list":
        values = store.config_all()
        if args.json:
            console.out(json.dumps(values, indent=2))
            return EXIT_OK
        width = max(len(k) for k in values)
        for key in sorted(values):
            marker = "" if values[key] != DEFAULT_CONFIG[key] else "  (default)"
            console.out(f"{key.ljust(width)}  {values[key] or '-'}{marker}")
        return EXIT_OK

    if not args.key:
        raise TempoError(f"config {action} needs a key")

    if action == "get":
        console.out(store.config_get(args.key))
        return EXIT_OK

    if action == "unset":
        store.config_unset(args.key)
        console.info(f"{args.key} reset to {DEFAULT_CONFIG[args.key]!r}")
        return EXIT_OK

    if args.value is None:
        raise TempoError(f"config set {args.key} needs a value")
    stored = store.config_set(args.key, args.value)
    console.info(f"{args.key} = {stored}")
    return EXIT_OK


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------

def _moment(text: str) -> datetime:
    """Parse a ``--at`` / ``--start`` / ``--end`` argument, strictly.

    Unlike ``--since``, these raise on input they cannot read.  A silently
    wrong start time is a wrong invoice.
    """
    try:
        return parse_moment(text)
    except TimeParseError as exc:
        raise TempoError(str(exc)) from exc


def _describe(session: Session) -> str:
    """One line describing a session, used by edit, rm and import."""
    end = (format_moment(session.ended_at, with_date=False)
           if session.ended_at else "running")
    note = f"  {session.note}" if session.note else ""
    return (f"[{session.id if session.id is not None else '-'}] "
            f"{session.tag}  {format_moment(session.started_at)}-{end}  "
            f"{format_duration(session.duration())}{note}")


def _output_format(args: argparse.Namespace, settings: dict[str, str]) -> str:
    """Decide which formatter ``tempo report`` should use.

    ``--json`` beats ``--csv`` beats ``--format`` beats the stored default.
    """
    if args.json:
        return "json"
    if args.csv:
        return "csv"
    if args.fmt:
        return args.fmt
    return settings["format"]


def _color_choice(args: argparse.Namespace,
                  settings: dict[str, str]) -> bool | None:
    """Resolve ``--no-color`` and the ``color`` setting into a tri-state."""
    if args.no_color:
        return False
    choice = settings.get("color", "auto")
    if choice == "always":
        return True
    if choice == "never":
        return False
    return None


def _round_minutes(args: argparse.Namespace, settings: dict[str, str]) -> int:
    """``--round`` if given, otherwise the ``round`` setting."""
    if args.round_to is not None:
        if args.round_to < 0:
            raise TempoError("--round takes a positive number of minutes")
        return args.round_to
    return int(settings["round"] or 0)


def _rate(args: argparse.Namespace, settings: dict[str, str]) -> float | None:
    """``--billable-rate`` if given, otherwise the ``billable_rate`` setting."""
    if args.rate is not None:
        return args.rate
    stored = settings.get("billable_rate", "")
    return float(stored) if stored else None


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line.  Returns the process exit code.

    This is what the ``tempo`` console script calls.  The package on PyPI is
    ``tempo-cli``; the command it installs is ``tempo``.
    """
    parser = build_parser()
    args = _apply_global_defaults(parser.parse_args(argv))

    if not getattr(args, "cmd", None):
        parser.print_help()
        return EXIT_USAGE

    console = Console(quiet=args.quiet, verbose=args.verbose)

    store = Store(home=args.home, db=args.db)
    console.detail(f"home {store.home}")
    console.detail(f"db   {store.db_path}")

    try:
        store.open()
        return args.func(args, store, console)
    except SchemaTooOld as exc:
        console.error(str(exc))
        return EXIT_ERROR
    except TimeParseError as exc:
        console.error(str(exc))
        return EXIT_ERROR
    except TempoError as exc:
        console.error(str(exc))
        return EXIT_ERROR
    except BrokenPipeError:
        # `tempo export | head` is a normal thing to do.
        return EXIT_OK
    except KeyboardInterrupt:
        console.error("interrupted")
        return EXIT_ERROR
    finally:
        store.close()


def _run() -> None:
    """What the ``tempo`` console script and ``python -m tempo.cli`` call."""
    sys.exit(main())


if __name__ == "__main__":
    _run()
