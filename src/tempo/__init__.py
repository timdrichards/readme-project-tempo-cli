"""tempo -- track time against project tags.

The package is installed as ``tempo-cli`` and installs a command called
``tempo``.  This module is the importable half: everything below is meant to
be used from Python, and is what the command line itself is built on.

The short version::

    from tempo import Tempo

    with Tempo() as t:
        t.start("thesis")
        ...
        t.stop()
        rep = t.report(since="7d", group_by="tag")

Three layers, smallest first:

:class:`Tempo`
    The convenient one.  Opens a tempo home, honours the stored
    configuration, and defaults its reporting window the same way the command
    line does.
:class:`Store`
    The database itself, with no opinions about defaults.  Use it when you
    want to control the window and the settings yourself.
:func:`report` and the formatter registry
    Aggregation and output.  :func:`register_formatter` is the extension
    point: give it a name and a callable and ``tempo report --format NAME``
    will use it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Sequence

from .reporting import (
    GROUP_BY_CHOICES,
    Formatter,
    Report,
    ReportRow,
    available_formatters,
    get_formatter,
    register_formatter,
    render,
    report,
    unregister_formatter,
)
from .storage import (
    DEFAULT_CONFIG,
    NoSessionRunning,
    SchemaTooOld,
    Session,
    SessionNotFound,
    SessionRunning,
    StorageError,
    Store,
    TagSummary,
    TempoError,
    resolve_db_path,
    resolve_home,
)
from .timeparse import (
    TimeParseError,
    format_duration,
    parse_duration,
    parse_moment,
    parse_since,
)

__version__ = "0.4.1"

__all__ = [
    "__version__",
    # the facade
    "Tempo",
    # records
    "Session",
    "TagSummary",
    "Report",
    "ReportRow",
    # storage
    "Store",
    "resolve_home",
    "resolve_db_path",
    "DEFAULT_CONFIG",
    # reporting and its extension point
    "report",
    "render",
    "register_formatter",
    "unregister_formatter",
    "get_formatter",
    "available_formatters",
    "Formatter",
    "GROUP_BY_CHOICES",
    # time parsing, for callers building their own windows
    "parse_moment",
    "parse_since",
    "parse_duration",
    "format_duration",
    # errors
    "TempoError",
    "StorageError",
    "SchemaTooOld",
    "SessionRunning",
    "NoSessionRunning",
    "SessionNotFound",
    "TimeParseError",
]


class Tempo:
    """An open tempo home, with the stored configuration applied.

    ``home`` and ``db`` mirror the ``--home`` and ``--db`` flags; leaving both
    out means ``$TEMPO_HOME`` if it is set, and ``~/.tempo`` if it is not.
    The directory and database are created on first use unless ``create`` is
    false, in which case opening a home that does not exist raises
    :class:`StorageError`.

    Use it as a context manager, or call :meth:`close` when you are done::

        with Tempo(home="/tmp/demo") as t:
            t.start("thesis", at="9:15am")
    """

    def __init__(self, home: str | None = None, db: str | None = None,
                 create: bool = True):
        self.store = Store(home=home, db=db, create=create)
        self.store.open()

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> "Tempo":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<Tempo home={self.store.home} sessions={self.store.count()}>"

    def close(self) -> None:
        """Close the database.  Safe to call more than once."""
        self.store.close()

    @property
    def home(self):
        """The tempo home directory in use."""
        return self.store.home

    @property
    def db_path(self):
        """The database file in use."""
        return self.store.db_path

    # -- the running session ----------------------------------------------

    def start(self, tag: str, at: str | datetime | None = None,
              note: str | None = None) -> Session:
        """Begin a session.

        ``at`` may be a ``datetime`` or any string :func:`parse_moment`
        understands.  Raises :class:`SessionRunning` if one already is --
        there is no implicit stop, on purpose.
        """
        return self.store.start(tag, at=_as_moment(at), note=note)

    def stop(self, at: str | datetime | None = None,
             note: str | None = None) -> Session:
        """End the running session and store it.

        ``at`` backdates the end.  Raises :class:`NoSessionRunning` if nothing
        is running.
        """
        return self.store.stop(at=_as_moment(at), note=note)

    def abort(self) -> Session:
        """Discard the running session without storing it."""
        return self.store.abort()

    def current(self) -> Session | None:
        """The running session, or ``None``."""
        return self.store.current()

    # -- stored sessions ---------------------------------------------------

    def sessions(self, since: str | datetime | None = None,
                 until: str | datetime | None = None,
                 tags: Sequence[str] | None = None,
                 limit: int | None = None) -> list[Session]:
        """Stored sessions that *start* in a window, oldest first.

        Both ends are optional and default to unbounded -- note that this is
        not the same default as :meth:`report`, which is today only.
        """
        return self.store.query(
            since=_as_moment(since),
            until=_as_moment(until),
            tags=tags,
            limit=limit,
        )

    def get(self, session_id: int) -> Session:
        """One stored session by id."""
        return self.store.get(session_id)

    def add(self, tag: str, start: str | datetime, end: str | datetime,
            note: str | None = None) -> Session:
        """Store a finished session directly, without starting a timer."""
        began = _as_moment(start)
        ended = _as_moment(end)
        if began is None or ended is None:
            raise TempoError("add() needs both a start and an end")
        return self.store.add(
            Session(tag=tag, start=began.timestamp(),
                    end=ended.timestamp(), note=note))

    def delete(self, *session_ids: int) -> int:
        """Delete stored sessions by id.  Returns how many went."""
        return self.store.delete(session_ids)

    def tags(self, since: str | datetime | None = None,
             until: str | datetime | None = None) -> list[TagSummary]:
        """Every tag used in a window, busiest first."""
        return self.store.tags(since=_as_moment(since),
                               until=_as_moment(until))

    # -- reporting ---------------------------------------------------------

    def report(self, since: str | datetime | None = None,
               until: str | datetime | None = None,
               tags: Sequence[str] | None = None,
               group_by: str | None = None,
               round_to: int | None = None,
               rate: float | None = None,
               limit: int | None = None,
               include_running: bool = True) -> Report:
        """Aggregate sessions into a :class:`Report`.

        Anything left as ``None`` falls back to this home's configuration,
        and the window falls back to **today only** -- local midnight to now.
        That is the same default the command line has, and it is the one
        people are most often surprised by; pass ``since="7d"`` or an explicit
        date for anything wider.
        """
        settings = self.store.config_all()
        return report(
            self.store,
            since=_as_moment(since),
            until=_as_moment(until),
            tags=tags,
            group_by=group_by or settings["group_by"],
            round_to=int(settings["round"] or 0) if round_to is None
            else round_to,
            rate=_setting_rate(settings) if rate is None else rate,
            currency=settings["currency"],
            limit=limit,
            week_start=settings["week_start"],
            include_running=include_running,
        )

    def render(self, rep: Report, fmt: str | None = None,
               **options: Any) -> str:
        """Format a report with a registered formatter."""
        settings = self.store.config_all()
        options.setdefault("duration_style", settings["duration_style"])
        return render(rep, fmt or settings["format"], **options)

    # -- configuration -----------------------------------------------------

    def config(self, key: str | None = None) -> Any:
        """Read configuration: one key, or the whole dict when given none."""
        if key is None:
            return self.store.config_all()
        return self.store.config_get(key)

    def set_config(self, key: str, value: str) -> str:
        """Write one configuration value.  Unknown keys raise."""
        return self.store.config_set(key, value)


def _as_moment(value: str | datetime | None) -> datetime | None:
    """Accept a ``datetime``, a string, or ``None`` from library callers.

    A string may be a duration ago (``"7d"``) or a moment (``"2026-01-04"``,
    ``"9:15am"``).  Unlike the ``--since`` flag, an unreadable string raises
    :class:`TimeParseError` here rather than quietly meaning "everything":
    a library caller who mistypes a date should find out.
    """
    if value is None or isinstance(value, datetime):
        return value
    text = str(value)
    try:
        return datetime.now() - timedelta(seconds=parse_duration(text))
    except TimeParseError:
        return parse_moment(text)


def _setting_rate(settings: dict[str, str]) -> float | None:
    """The stored billable rate, or ``None`` when it is unset."""
    stored = settings.get("billable_rate", "")
    return float(stored) if stored else None
