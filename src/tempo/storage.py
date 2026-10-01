"""SQLite storage for tempo.

A tempo "home" is a directory -- ``~/.tempo`` unless told otherwise -- holding
two things:

``log.db``
    A SQLite database of finished sessions, plus a small key/value table for
    configuration.

``current``
    A JSON file describing the one session that is running right now, if any.
    It is a separate file and not a database row on purpose: a running session
    has no end, and every report query would otherwise have to remember to
    exclude it.

NOTE(mdc): home resolution is `--home`, then `--db` (which overrides just the
database file), then ``$TEMPO_HOME``, then ``~/.tempo``.  There is no search
and no migration between homes.  If you set ``TEMPO_HOME`` after you have
already logged time, tempo will happily create a brand new empty database at
the new location and your old sessions are still sitting in ``~/.tempo``,
invisible.  Two people have reported that as data loss.  It isn't, but it
looks exactly like it.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .timeparse import format_duration, format_moment

__all__ = [
    "Session",
    "TagSummary",
    "Store",
    "TempoError",
    "StorageError",
    "SessionRunning",
    "NoSessionRunning",
    "SchemaTooOld",
    "SessionNotFound",
    "SCHEMA_VERSION",
    "DEFAULT_CONFIG",
    "resolve_home",
    "resolve_db_path",
]

#: Bumped whenever the table definitions change.  See :meth:`Store._check_schema`
#: for what happens when an older database is opened.
SCHEMA_VERSION = 3

#: The configuration keys tempo knows about, with their defaults.  Anything
#: else is rejected by ``tempo config set`` so that typos are not silently
#: stored forever.
DEFAULT_CONFIG: dict[str, str] = {
    "week_start": "monday",
    "round": "0",
    "billable_rate": "",
    "currency": "USD",
    "group_by": "tag",
    "format": "table",
    "duration_style": "short",
    "color": "auto",
}


class TempoError(Exception):
    """Base class for every error tempo raises on purpose."""


class StorageError(TempoError):
    """The database or the home directory could not be used."""


class SchemaTooOld(StorageError):
    """The database was written by a tempo older than 0.3."""


class SessionRunning(TempoError):
    """``start`` was called while a session was already running."""

    def __init__(self, session: "Session"):
        super().__init__(f"session already running: {session.tag}")
        self.session = session


class NoSessionRunning(TempoError):
    """``stop``, ``abort`` or ``status`` found nothing running."""


class SessionNotFound(TempoError):
    """``edit`` or ``rm`` was given an id that is not in the database."""

    def __init__(self, session_id: int):
        super().__init__(f"no session with id {session_id}")
        self.session_id = session_id


# --------------------------------------------------------------------------
# The record type
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Session:
    """One tracked interval.

    ``start`` and ``end`` are Unix timestamps (seconds, float).  ``end`` is
    ``None`` while the session is running.  ``id`` is ``None`` for the running
    session, because it does not exist in the database until it is stopped.
    """

    tag: str
    start: float
    end: float | None = None
    note: str | None = None
    id: int | None = None

    @property
    def running(self) -> bool:
        """True while this session has no end."""
        return self.end is None

    @property
    def started_at(self) -> datetime:
        """The start, as a local-time ``datetime``."""
        return datetime.fromtimestamp(self.start)

    @property
    def ended_at(self) -> datetime | None:
        """The end, as a local-time ``datetime``, or ``None`` if running."""
        return None if self.end is None else datetime.fromtimestamp(self.end)

    def duration(self, now: float | None = None) -> float:
        """Length in seconds.  A running session is measured against ``now``."""
        if self.end is not None:
            return max(0.0, self.end - self.start)
        reference = datetime.now().timestamp() if now is None else now
        return max(0.0, reference - self.start)

    def overlaps(self, other: "Session") -> bool:
        """True if two closed sessions cover any of the same wall clock."""
        if self.end is None or other.end is None:
            return False
        return self.start < other.end and other.start < self.end

    def to_dict(self, now: float | None = None) -> dict[str, Any]:
        """A JSON-safe dict, as emitted by ``--json`` and ``tempo export``."""
        return {
            "id": self.id,
            "tag": self.tag,
            "start": self.start,
            "end": self.end,
            "started": format_moment(self.started_at),
            "ended": (format_moment(self.ended_at)
                      if self.ended_at is not None else None),
            "seconds": round(self.duration(now), 3),
            "duration": format_duration(self.duration(now)),
            "note": self.note,
            "running": self.running,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Session":
        """Build a session from a ``sessions`` row."""
        return cls(
            id=row["id"],
            tag=row["tag"],
            start=float(row["started"]),
            end=None if row["ended"] is None else float(row["ended"]),
            note=row["note"],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        """Build a session from a dict produced by :meth:`to_dict`.

        Used by ``tempo import``.  Only ``tag`` and ``start`` are required;
        ``id`` is ignored, because an imported session is always inserted
        fresh rather than overwriting whatever happens to share its id.
        """
        try:
            tag = str(data["tag"]).strip()
            start = float(data["start"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"not a session record: {data!r}") from exc
        if not tag:
            raise ValueError("session has an empty tag")
        end = data.get("end")
        note = data.get("note")
        return cls(
            tag=tag,
            start=start,
            end=None if end in (None, "") else float(end),
            note=None if note in (None, "") else str(note),
        )


# --------------------------------------------------------------------------
# Path resolution
# --------------------------------------------------------------------------

def resolve_home(home: str | os.PathLike[str] | None = None,
                 env: dict[str, str] | None = None) -> Path:
    """Work out which directory tempo should use.

    Precedence: the ``home`` argument (``--home``), then ``$TEMPO_HOME``, then
    ``~/.tempo``.  The directory is not created here; see :meth:`Store.open`.
    """
    environ = os.environ if env is None else env
    if home:
        return Path(home).expanduser()
    from_env = environ.get("TEMPO_HOME")
    if from_env:
        return Path(from_env).expanduser()
    return Path.home() / ".tempo"


def resolve_db_path(home: str | os.PathLike[str] | None = None,
                    db: str | os.PathLike[str] | None = None,
                    env: dict[str, str] | None = None) -> Path:
    """Work out which file the sessions live in.

    ``--db`` wins outright and may point anywhere; the home directory is still
    used for the ``current`` file, which is why the two flags are separate.
    """
    if db:
        return Path(db).expanduser()
    return resolve_home(home, env=env) / "log.db"


# --------------------------------------------------------------------------
# The store
# --------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id      INTEGER PRIMARY KEY,
    tag     TEXT NOT NULL,
    started REAL NOT NULL,
    ended   REAL,
    note    TEXT
);
CREATE INDEX IF NOT EXISTS sessions_started ON sessions (started);
CREATE INDEX IF NOT EXISTS sessions_tag ON sessions (tag);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Store:
    """A tempo home directory, opened.

    Usually reached through :class:`tempo.Tempo` rather than directly.  Use it
    as a context manager, or remember to :meth:`close` it::

        with Store(home="/tmp/demo") as store:
            store.start("thesis")
    """

    def __init__(self,
                 home: str | os.PathLike[str] | None = None,
                 db: str | os.PathLike[str] | None = None,
                 env: dict[str, str] | None = None,
                 create: bool = True):
        self.home = resolve_home(home, env=env)
        self.db_path = resolve_db_path(home, db, env=env)
        self.current_path = self.home / "current"
        self._create = create
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> "Store":
        self.open()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def connection(self) -> sqlite3.Connection:
        """The open SQLite connection, opening it on first use."""
        if self._conn is None:
            self.open()
        assert self._conn is not None
        return self._conn

    def open(self) -> "Store":
        """Create the home directory if needed and connect to the database."""
        if self._conn is not None:
            return self
        if self._create:
            try:
                self.home.mkdir(parents=True, exist_ok=True)
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise StorageError(f"cannot create {self.home}: {exc}") from exc
        elif not self.db_path.exists():
            raise StorageError(f"no tempo database at {self.db_path}")

        try:
            conn = sqlite3.connect(str(self.db_path))
        except sqlite3.Error as exc:
            raise StorageError(f"cannot open {self.db_path}: {exc}") from exc
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        self._conn = conn
        self._check_schema(conn)
        return self

    def close(self) -> None:
        """Close the connection.  Safe to call more than once."""
        if self._conn is not None:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def _check_schema(self, conn: sqlite3.Connection) -> None:
        """Create the schema, or refuse a database from before 0.3.

        There is no migration code in tempo and there never has been.  Up to
        0.2 the ``sessions`` table had no ``note`` column and stored times as
        ISO strings rather than floats; reading one of those with today's
        queries produces wrong numbers rather than an error, which is worse
        than refusing.  So we refuse.

        TODO(mdc): write the 0.2 -> 0.3 migration before anyone else hits this.
        It has been on the list since March.
        """
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
        ).fetchone()

        if existing and version < SCHEMA_VERSION:
            raise SchemaTooOld(
                f"{self.db_path} was written by tempo < 0.3 and cannot be "
                f"upgraded. Back it up and delete it, then start again."
            )

        conn.executescript(_SCHEMA)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()

    # -- the running session ----------------------------------------------

    def current(self) -> Session | None:
        """The running session, or ``None``.

        A ``current`` file that cannot be read as JSON is treated as a
        corrupt-but-real session rather than as no session, so that ``start``
        still refuses and the user is pointed at ``tempo abort``.
        """
        if not self.current_path.exists():
            return None
        try:
            raw = json.loads(self.current_path.read_text(encoding="utf-8"))
            return Session(
                tag=str(raw["tag"]),
                start=float(raw["start"]),
                note=raw.get("note"),
            )
        except (OSError, ValueError, KeyError, TypeError):
            return Session(tag="<unreadable>", start=0.0)

    def _write_current(self, session: Session) -> None:
        # Write-then-rename so a killed process cannot leave a half-written
        # `current` behind.  NOTE(mdc): nobody has run any of this on Windows.
        # Path.replace() is atomic there too, and nothing here shells out or
        # assumes a path separator, so I expect it works -- but "I expect" is
        # not "I tested".
        payload = {
            "tag": session.tag,
            "start": session.start,
            "note": session.note,
            "written_by": f"tempo schema {SCHEMA_VERSION}",
        }
        tmp = self.current_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.current_path)

    def start(self, tag: str, at: datetime | None = None,
              note: str | None = None) -> Session:
        """Begin a session.

        Raises :class:`SessionRunning` if one already is.  That is the whole
        of the stale-session problem: a shell that dies without running
        ``stop`` leaves the ``current`` file behind, and every ``start`` after
        that fails until someone runs ``abort``.
        """
        tag = str(tag).strip()
        if not tag:
            raise TempoError("a session needs a tag")
        if "\n" in tag:
            raise TempoError("tags cannot contain newlines")

        running = self.current()
        if running is not None:
            raise SessionRunning(running)

        start_ts = (at or datetime.now()).timestamp()
        session = Session(tag=tag, start=start_ts, note=note)
        self.home.mkdir(parents=True, exist_ok=True)
        self._write_current(session)
        return session

    def stop(self, at: datetime | None = None,
             note: str | None = None) -> Session:
        """End the running session and write it to the database.

        ``at`` backdates the end, which is how you recover a session you
        forgot to stop: ``tempo stop --at '5pm friday'``.  An end before the
        start is refused rather than stored as a negative duration.
        """
        running = self.current()
        if running is None:
            raise NoSessionRunning("no session running")
        if running.tag == "<unreadable>":
            raise StorageError(
                f"{self.current_path} is not readable as a session; "
                f"`tempo abort` will discard it"
            )

        end_ts = (at or datetime.now()).timestamp()
        if end_ts < running.start:
            raise TempoError(
                f"end ({format_moment(datetime.fromtimestamp(end_ts))}) is "
                f"before the start "
                f"({format_moment(running.started_at)})"
            )

        finished = replace(running, end=end_ts,
                           note=note if note is not None else running.note)
        stored = self.add(finished)
        self.current_path.unlink(missing_ok=True)
        return stored

    def abort(self) -> Session:
        """Throw the running session away without logging it."""
        running = self.current()
        if running is None:
            raise NoSessionRunning("no session running")
        self.current_path.unlink(missing_ok=True)
        return running

    # -- stored sessions ---------------------------------------------------

    def add(self, session: Session) -> Session:
        """Insert a finished session and return it with its new id."""
        if session.end is None:
            raise TempoError("cannot store a session with no end")
        cur = self.connection.execute(
            "INSERT INTO sessions (tag, started, ended, note) VALUES (?, ?, ?, ?)",
            (session.tag, session.start, session.end, session.note),
        )
        self.connection.commit()
        return replace(session, id=int(cur.lastrowid))

    def add_many(self, sessions: Iterable[Session]) -> int:
        """Insert many finished sessions in one transaction.

        NOTE(mdc): no de-duplication.  ``tempo import`` of the same file twice
        gives you two of everything; there is no natural key to match on when
        two people really can log the same tag at the same minute.
        """
        rows = []
        for session in sessions:
            if session.end is None:
                raise TempoError("cannot store a session with no end")
            rows.append((session.tag, session.start, session.end, session.note))
        if not rows:
            return 0
        self.connection.executemany(
            "INSERT INTO sessions (tag, started, ended, note) VALUES (?, ?, ?, ?)",
            rows,
        )
        self.connection.commit()
        return len(rows)

    def get(self, session_id: int) -> Session:
        """Fetch one session by id.  Raises :class:`SessionNotFound`."""
        row = self.connection.execute(
            "SELECT id, tag, started, ended, note FROM sessions WHERE id = ?",
            (int(session_id),),
        ).fetchone()
        if row is None:
            raise SessionNotFound(int(session_id))
        return Session.from_row(row)

    def update(self, session_id: int, *, tag: str | None = None,
               start: datetime | None = None, end: datetime | None = None,
               note: str | None = None) -> Session:
        """Change fields on a stored session and return the new version."""
        existing = self.get(session_id)
        new_tag = existing.tag if tag is None else str(tag).strip()
        new_start = existing.start if start is None else start.timestamp()
        new_end = existing.end if end is None else end.timestamp()
        new_note = existing.note if note is None else note

        if not new_tag:
            raise TempoError("a session needs a tag")
        if new_end is not None and new_end < new_start:
            raise TempoError("end is before the start")

        self.connection.execute(
            "UPDATE sessions SET tag = ?, started = ?, ended = ?, note = ? "
            "WHERE id = ?",
            (new_tag, new_start, new_end, new_note, int(session_id)),
        )
        self.connection.commit()
        return Session(id=int(session_id), tag=new_tag, start=new_start,
                       end=new_end, note=new_note)

    def delete(self, session_ids: Sequence[int]) -> int:
        """Delete sessions by id.  Returns how many rows went."""
        ids = [int(i) for i in session_ids]
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        cur = self.connection.execute(
            f"DELETE FROM sessions WHERE id IN ({placeholders})", ids
        )
        self.connection.commit()
        return int(cur.rowcount)

    def query(self, since: datetime | None = None,
              until: datetime | None = None,
              tags: Sequence[str] | None = None,
              limit: int | None = None,
              newest_first: bool = False) -> list[Session]:
        """Fetch stored sessions in a window.

        A session is in the window if it *starts* inside it.  A session that
        begins at 23:40 and ends at 00:20 therefore belongs entirely to the
        first day; tempo never splits a session across a day boundary.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if since is not None:
            clauses.append("started >= ?")
            params.append(since.timestamp())
        if until is not None:
            clauses.append("started < ?")
            params.append(until.timestamp())
        if tags:
            wanted = [str(t).strip() for t in tags if str(t).strip()]
            if wanted:
                clauses.append(
                    "tag IN (%s)" % ",".join("?" for _ in wanted))
                params.extend(wanted)

        sql = "SELECT id, tag, started, ended, note FROM sessions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY started " + ("DESC" if newest_first else "ASC")
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))

        return [Session.from_row(r)
                for r in self.connection.execute(sql, params)]

    def iter_all(self, batch: int = 500) -> Iterator[Session]:
        """Walk every stored session, oldest first.  Used by ``export``."""
        cur = self.connection.execute(
            "SELECT id, tag, started, ended, note FROM sessions "
            "ORDER BY started ASC"
        )
        while True:
            rows = cur.fetchmany(batch)
            if not rows:
                return
            for row in rows:
                yield Session.from_row(row)

    def tags(self, since: datetime | None = None,
             until: datetime | None = None) -> list["TagSummary"]:
        """Every tag used in a window, with its totals, busiest-first."""
        clauses = ["ended IS NOT NULL"]
        params: list[Any] = []
        if since is not None:
            clauses.append("started >= ?")
            params.append(since.timestamp())
        if until is not None:
            clauses.append("started < ?")
            params.append(until.timestamp())

        sql = (
            "SELECT tag, COUNT(*) AS n, SUM(ended - started) AS total, "
            "MIN(started) AS first_seen, MAX(started) AS last_seen "
            "FROM sessions WHERE " + " AND ".join(clauses) +
            " GROUP BY tag ORDER BY total DESC"
        )
        return [
            TagSummary(
                tag=row["tag"],
                count=int(row["n"]),
                seconds=float(row["total"] or 0.0),
                first_seen=float(row["first_seen"]),
                last_seen=float(row["last_seen"]),
            )
            for row in self.connection.execute(sql, params)
        ]

    def count(self) -> int:
        """How many finished sessions are stored."""
        return int(self.connection.execute(
            "SELECT COUNT(*) FROM sessions").fetchone()[0])

    def span(self) -> tuple[datetime, datetime] | None:
        """First and last start time in the database, or ``None`` if empty."""
        row = self.connection.execute(
            "SELECT MIN(started) AS lo, MAX(started) AS hi FROM sessions"
        ).fetchone()
        if row is None or row["lo"] is None:
            return None
        return (datetime.fromtimestamp(row["lo"]),
                datetime.fromtimestamp(row["hi"]))

    def find_overlaps(self, session: Session) -> list[Session]:
        """Stored sessions covering any of the same wall clock as ``session``.

        ``import`` and ``edit`` use this to warn.  Nothing in tempo refuses an
        overlap: tracking two things at once is unusual but it is not our
        business to forbid it.
        """
        if session.end is None:
            return []
        rows = self.connection.execute(
            "SELECT id, tag, started, ended, note FROM sessions "
            "WHERE ended IS NOT NULL AND started < ? AND ended > ?",
            (session.end, session.start),
        )
        return [Session.from_row(r) for r in rows
                if r["id"] != session.id]

    # -- configuration -----------------------------------------------------

    def config_all(self) -> dict[str, str]:
        """Every configuration key, defaults filled in."""
        values = dict(DEFAULT_CONFIG)
        for row in self.connection.execute("SELECT key, value FROM meta"):
            if row["key"] in DEFAULT_CONFIG:
                values[row["key"]] = row["value"]
        return values

    def config_get(self, key: str) -> str:
        """One configuration value, or its default."""
        if key not in DEFAULT_CONFIG:
            raise TempoError(
                f"unknown config key: {key} "
                f"(known keys: {', '.join(sorted(DEFAULT_CONFIG))})"
            )
        row = self.connection.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else DEFAULT_CONFIG[key]

    def config_set(self, key: str, value: str) -> str:
        """Set a configuration value.  Returns the stored string."""
        if key not in DEFAULT_CONFIG:
            raise TempoError(
                f"unknown config key: {key} "
                f"(known keys: {', '.join(sorted(DEFAULT_CONFIG))})"
            )
        text = "" if value is None else str(value)
        _validate_config(key, text)
        self.connection.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, text),
        )
        self.connection.commit()
        return text

    def config_unset(self, key: str) -> None:
        """Forget a configuration value, restoring its default."""
        if key not in DEFAULT_CONFIG:
            raise TempoError(f"unknown config key: {key}")
        self.connection.execute("DELETE FROM meta WHERE key = ?", (key,))
        self.connection.commit()


@dataclass(frozen=True)
class TagSummary:
    """One row of ``tempo tags``: a tag and what has been logged against it."""

    tag: str
    count: int
    seconds: float
    first_seen: float
    last_seen: float

    @property
    def first_seen_at(self) -> datetime:
        """First use, as a local-time ``datetime``."""
        return datetime.fromtimestamp(self.first_seen)

    @property
    def last_seen_at(self) -> datetime:
        """Most recent use, as a local-time ``datetime``."""
        return datetime.fromtimestamp(self.last_seen)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe dict, as emitted by ``tempo tags --json``."""
        return {
            "tag": self.tag,
            "sessions": self.count,
            "seconds": round(self.seconds, 3),
            "duration": format_duration(self.seconds),
            "first_seen": format_moment(self.first_seen_at),
            "last_seen": format_moment(self.last_seen_at),
        }


def _validate_config(key: str, value: str) -> None:
    """Reject config values that would only fail later, at report time."""
    if key == "week_start":
        from .timeparse import _WEEKDAYS  # local import: table, not API
        if value.strip().lower() not in _WEEKDAYS:
            raise TempoError(f"week_start must be a weekday name, not {value!r}")
    elif key == "round":
        if not value.isdigit():
            raise TempoError("round must be a whole number of minutes")
    elif key == "billable_rate":
        if value:
            try:
                float(value)
            except ValueError:
                raise TempoError(
                    f"billable_rate must be a number, not {value!r}") from None
    elif key == "group_by":
        if value not in ("tag", "day", "week", "month", "tag,day", "none"):
            raise TempoError(f"group_by cannot be {value!r}")
    elif key == "duration_style":
        if value not in ("short", "clock", "decimal", "long"):
            raise TempoError(f"duration_style cannot be {value!r}")
    elif key == "color":
        if value not in ("auto", "always", "never"):
            raise TempoError("color must be auto, always or never")
