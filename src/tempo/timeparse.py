"""Time parsing and formatting for tempo.

Everything tempo accepts on the command line as a moment in time (``--at``,
``--since``, ``--until``, the start/end arguments of ``tempo edit``) is parsed
here, and everything it prints as a duration is formatted here.

Two rules the rest of the codebase relies on:

* moments are returned as naive ``datetime`` objects in the machine's local
  timezone; storage converts them to Unix timestamps on the way in;
* durations are plain floats, in seconds.

NOTE(mdc): all of the word tables below -- month names, weekday names, "am" /
"pm" -- are English. We do not consult ``locale`` anywhere. Someone running a
non-English system can still use ISO dates and 24-hour times; `--at '9:15am'`
will not work for them. Nobody has asked for this yet, so it stays.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

__all__ = [
    "TimeParseError",
    "BEGINNING_OF_TIME",
    "parse_duration",
    "parse_moment",
    "parse_since",
    "parse_until",
    "format_duration",
    "format_moment",
    "format_clock",
    "day_bounds",
    "week_bounds",
    "month_bounds",
    "round_seconds",
    "humanize_range",
]


class TimeParseError(ValueError):
    """Raised when a string cannot be understood as a moment or a duration."""


#: What ``--since`` falls back to when it cannot parse its argument.  This is
#: deliberately the Unix epoch and not ``datetime.min``: SQLite comparisons are
#: done on float timestamps, and negative timestamps are not portable.
BEGINNING_OF_TIME = datetime(1970, 1, 1, 0, 0, 0)


# --------------------------------------------------------------------------
# Word tables (English only -- see the module docstring)
# --------------------------------------------------------------------------

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_WEEKDAYS = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "weds": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}

_DURATION_UNITS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "week": 604800, "weeks": 604800,
}

_DURATION_TOKEN = re.compile(r"(\d+(?:\.\d+)?)\s*([a-z]+)")
_CLOCK = re.compile(
    r"^(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?$"
)
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_BARE_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")


# --------------------------------------------------------------------------
# Durations
# --------------------------------------------------------------------------

def parse_duration(text: str) -> float:
    """Parse a duration like ``3d``, ``90m``, ``1h30m`` or ``1.5h``.

    Returns a number of seconds.  Raises :class:`TimeParseError` on anything
    else, including a bare number: ``tempo report --since 3`` is ambiguous
    enough that guessing is worse than complaining.
    """
    if text is None:
        raise TimeParseError("empty duration")
    raw = " ".join(str(text).strip().lower().split())
    if not raw:
        raise TimeParseError("empty duration")
    if _BARE_NUMBER.match(raw):
        raise TimeParseError(
            f"{text!r}: durations need a unit (try {raw}m, {raw}h or {raw}d)"
        )

    total = 0.0
    consumed = 0
    seen_units: set[int] = set()
    for match in _DURATION_TOKEN.finditer(raw):
        if match.start() != consumed and raw[consumed:match.start()].strip():
            raise TimeParseError(f"{text!r}: not a duration")
        amount, unit = match.group(1), match.group(2)
        if unit not in _DURATION_UNITS:
            raise TimeParseError(f"{text!r}: unknown time unit {unit!r}")
        scale = _DURATION_UNITS[unit]
        if scale in seen_units:
            raise TimeParseError(f"{text!r}: unit {unit!r} given twice")
        seen_units.add(scale)
        total += float(amount) * scale
        consumed = match.end()

    if consumed == 0 or raw[consumed:].strip():
        raise TimeParseError(f"{text!r}: not a duration")
    return total


def looks_like_duration(text: str) -> bool:
    """True if :func:`parse_duration` would accept ``text``."""
    try:
        parse_duration(text)
    except TimeParseError:
        return False
    return True


# --------------------------------------------------------------------------
# Moments
# --------------------------------------------------------------------------

def parse_moment(text: str, now: datetime | None = None) -> datetime:
    """Parse a moment in time, strictly.

    Understands, in roughly this order:

    * ``now``, ``today``, ``yesterday``, ``tomorrow``, ``midnight``, ``noon``
    * ISO forms: ``2026-01-04``, ``2026-01-04T09:15``, ``2026-01-04 09:15:30``
    * clock times: ``9:15am``, ``9am``, ``17:00``, ``17:00:30`` -- resolved
      against *today*
    * a weekday name, optionally with a clock time: ``friday``, ``5pm friday``
      -- resolved backwards, to the most recent such weekday
    * a month name with a day, optionally a year: ``jan 4``, ``4 jan 2026``
    * ``yesterday 9am``, ``today 17:00``

    Raises :class:`TimeParseError` if it understands none of that.  Note that
    ``jan4``, with no separator, is *not* understood; the month tables are
    matched against whole words only.
    """
    now = now or datetime.now()
    if text is None:
        raise TimeParseError("empty time")
    raw = str(text).strip()
    if not raw:
        raise TimeParseError("empty time")

    iso = _try_iso(raw)
    if iso is not None:
        return iso

    tokens = _tokenize(raw.lower())
    if not tokens:
        raise TimeParseError(f"{text!r}: could not be read as a time")

    day: date | None = None
    clock: tuple[int, int, int] | None = None
    anchor_weekday: int | None = None

    index = 0
    while index < len(tokens):
        token = tokens[index]

        if token in ("now",):
            if len(tokens) != 1:
                raise TimeParseError(f"{text!r}: 'now' does not combine")
            return now.replace(microsecond=0)

        if token in ("today", "yesterday", "tomorrow"):
            if day is not None:
                raise TimeParseError(f"{text!r}: two dates given")
            offset = {"today": 0, "yesterday": -1, "tomorrow": 1}[token]
            day = (now + timedelta(days=offset)).date()
            index += 1
            continue

        if token == "midnight":
            clock = (0, 0, 0)
            index += 1
            continue

        if token == "noon":
            clock = (12, 0, 0)
            index += 1
            continue

        if token in _WEEKDAYS:
            if anchor_weekday is not None or day is not None:
                raise TimeParseError(f"{text!r}: two dates given")
            anchor_weekday = _WEEKDAYS[token]
            index += 1
            continue

        if token in _MONTHS:
            if day is not None:
                raise TimeParseError(f"{text!r}: two dates given")
            day, index = _read_month_form(tokens, index, now)
            continue

        # "4 jan" / "4 jan 2026": the day number arrives before the month.
        if (token.isdigit() and len(token) <= 2
                and index + 1 < len(tokens) and tokens[index + 1] in _MONTHS):
            if day is not None:
                raise TimeParseError(f"{text!r}: two dates given")
            day, index = _read_month_form(tokens, index + 1, now)
            continue

        iso_day = _ISO_DATE.match(token)
        if iso_day:
            if day is not None:
                raise TimeParseError(f"{text!r}: two dates given")
            day = date(int(iso_day.group(1)), int(iso_day.group(2)),
                       int(iso_day.group(3)))
            index += 1
            continue

        as_clock = _try_clock(token)
        if as_clock is not None:
            if clock is not None:
                raise TimeParseError(f"{text!r}: two times given")
            clock = as_clock
            index += 1
            continue

        # A bare number that follows a month name is handled above; anything
        # else that reaches here is simply not a time we know.
        raise TimeParseError(f"{text!r}: could not be read as a time")

    if anchor_weekday is not None:
        day = _most_recent_weekday(now.date(), anchor_weekday)

    if day is None and clock is None:
        raise TimeParseError(f"{text!r}: could not be read as a time")
    if day is None:
        day = now.date()
    if clock is None:
        clock = (0, 0, 0)

    return datetime(day.year, day.month, day.day, clock[0], clock[1], clock[2])


def parse_since(text: str, now: datetime | None = None) -> datetime:
    """Parse the argument of ``--since``: a duration *or* a moment.

    A duration is read as "this long ago", so ``--since 3d`` means the last
    three days.  Anything else is handed to :func:`parse_moment`.

    KNOWN BUG(mdc): if neither parse succeeds we return
    :data:`BEGINNING_OF_TIME` instead of raising, so `--since jan4` quietly
    reports everything you have ever logged rather than telling you it did not
    understand.  Users have lost an hour to this (see issue #19).  Fixing it is
    a behaviour change for anyone scripting against it, so it is waiting for
    0.5.  ``--until`` does *not* share this fallback -- it raises.
    """
    now = now or datetime.now()
    if text is None:
        return BEGINNING_OF_TIME
    raw = str(text).strip()
    if not raw:
        return BEGINNING_OF_TIME

    try:
        return now - timedelta(seconds=parse_duration(raw))
    except TimeParseError:
        pass
    try:
        return parse_moment(raw, now=now)
    except TimeParseError:
        return BEGINNING_OF_TIME


def parse_until(text: str, now: datetime | None = None) -> datetime:
    """Parse the argument of ``--until``: a duration ago, or a moment.

    Unlike :func:`parse_since` this raises :class:`TimeParseError` on input it
    does not understand.  The asymmetry is not deliberate design, it is the
    order the two flags were written in.
    """
    now = now or datetime.now()
    raw = "" if text is None else str(text).strip()
    if not raw:
        raise TimeParseError("empty time")
    try:
        return now - timedelta(seconds=parse_duration(raw))
    except TimeParseError:
        return parse_moment(raw, now=now)


# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Split on whitespace and commas, dropping filler words."""
    parts = re.split(r"[\s,]+", text.strip())
    return [p for p in parts if p and p not in ("at", "on", "last")]


def _try_iso(raw: str) -> datetime | None:
    """Try the stdlib ISO parser, including the ``YYYY-MM-DD HH:MM`` form."""
    candidate = raw.strip()
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        pass
    if " " in candidate:
        try:
            return datetime.fromisoformat(candidate.replace(" ", "T", 1))
        except ValueError:
            return None
    return None


def _try_clock(token: str) -> tuple[int, int, int] | None:
    """Parse ``9:15am`` / ``9am`` / ``17:00`` / ``17:00:30`` into h, m, s."""
    match = _CLOCK.match(token)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    second = int(match.group(3) or 0)
    meridiem = (match.group(4) or "").replace(".", "")

    # A bare 1- or 2-digit number with no colon and no am/pm is a day-of-month
    # far more often than it is an hour ("jan 4", "4 jan"), so refuse it here
    # and let the month-form reader have it.
    if not meridiem and match.group(2) is None:
        return None

    if meridiem:
        if not 1 <= hour <= 12:
            raise TimeParseError(f"{token!r}: {hour} is not a 12-hour clock hour")
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
    if not 0 <= hour <= 23 or not 0 <= minute <= 59 or not 0 <= second <= 59:
        raise TimeParseError(f"{token!r}: not a valid time of day")
    return hour, minute, second


def _read_month_form(tokens: list[str], index: int,
                     now: datetime) -> tuple[date, int]:
    """Read ``jan 4`` / ``jan 4 2026`` / ``4 jan`` starting at a month name."""
    month = _MONTHS[tokens[index]]
    rest = tokens[index + 1:]
    day_num: int | None = None
    year: int | None = None
    consumed = 1

    for token in rest[:2]:
        if not token.isdigit():
            break
        value = int(token)
        if day_num is None and 1 <= value <= 31 and len(token) <= 2:
            day_num = value
            consumed += 1
        elif year is None and len(token) == 4:
            year = value
            consumed += 1
        else:
            break

    if day_num is None and index > 0 and tokens[index - 1].isdigit():
        # "4 jan" -- the day was the token before the month name, and the main
        # loop already rejected it, so this branch is only reached when the
        # number came first and parse_moment retried.  Kept for symmetry.
        day_num = int(tokens[index - 1])

    if day_num is None:
        raise TimeParseError(f"{tokens[index]!r}: month given without a day")
    try:
        return date(year or now.year, month, day_num), index + consumed
    except ValueError as exc:
        raise TimeParseError(f"{tokens[index]} {day_num}: {exc}") from exc


def _most_recent_weekday(today: date, weekday: int) -> date:
    """The most recent ``weekday`` on or before ``today``."""
    delta = (today.weekday() - weekday) % 7
    return today - timedelta(days=delta)


# --------------------------------------------------------------------------
# Window helpers
# --------------------------------------------------------------------------

def day_bounds(moment: datetime) -> tuple[datetime, datetime]:
    """The local-midnight-to-local-midnight window containing ``moment``."""
    start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def week_bounds(moment: datetime, week_start: str = "monday"
                ) -> tuple[datetime, datetime]:
    """The week containing ``moment``.

    ``week_start`` is a weekday name; ``tempo config set week_start sunday``
    is the usual reason to pass anything but the default.
    """
    key = str(week_start).strip().lower()
    if key not in _WEEKDAYS:
        raise TimeParseError(f"{week_start!r}: not a weekday name")
    start_day = _WEEKDAYS[key]
    day_start, _ = day_bounds(moment)
    back = (day_start.weekday() - start_day) % 7
    start = day_start - timedelta(days=back)
    return start, start + timedelta(days=7)


def month_bounds(moment: datetime) -> tuple[datetime, datetime]:
    """The calendar month containing ``moment``."""
    start = moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------

def format_duration(seconds: float, style: str = "short") -> str:
    """Render a number of seconds.

    ``short`` gives ``1h 30m``, ``clock`` gives ``1:30``, ``decimal`` gives
    ``1.50`` (hours, which is what invoicing software wants), and ``long``
    gives ``1 hour 30 minutes``.
    """
    seconds = float(seconds or 0)
    negative = seconds < 0
    seconds = abs(seconds)

    if style == "decimal":
        text = f"{seconds / 3600:.2f}"
    elif style == "clock":
        text = format_clock(seconds)
    elif style == "long":
        text = _format_long(seconds)
    elif style == "short":
        text = _format_short(seconds)
    else:
        raise ValueError(f"unknown duration style: {style!r}")
    return f"-{text}" if negative else text


def _format_short(seconds: float) -> str:
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s" if secs else f"{minutes}m"
    return f"{secs}s"


def _format_long(seconds: float) -> str:
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if minutes:
        parts.append(f"{minutes} minute" + ("s" if minutes != 1 else ""))
    if secs and not hours:
        parts.append(f"{secs} second" + ("s" if secs != 1 else ""))
    return " ".join(parts) or "0 minutes"


def format_clock(seconds: float) -> str:
    """``5400`` -> ``1:30``.  Hours are not wrapped at 24."""
    total = int(round(abs(float(seconds or 0))))
    hours, rest = divmod(total, 3600)
    minutes = rest // 60
    return f"{hours}:{minutes:02d}"


def format_moment(moment: datetime, with_date: bool = True) -> str:
    """Render a moment the way tempo prints it: ``2026-01-04 09:15``."""
    if with_date:
        return moment.strftime("%Y-%m-%d %H:%M")
    return moment.strftime("%H:%M")


def humanize_range(start: datetime, end: datetime) -> str:
    """A short human label for a reporting window, used in report headers."""
    if start <= BEGINNING_OF_TIME:
        return f"everything up to {format_moment(end)}"
    same_day = start.date() == (end - timedelta(seconds=1)).date()
    if same_day:
        return start.strftime("%Y-%m-%d")
    return f"{start.strftime('%Y-%m-%d')} to {(end - timedelta(seconds=1)).strftime('%Y-%m-%d')}"


# --------------------------------------------------------------------------
# Rounding
# --------------------------------------------------------------------------

def round_seconds(seconds: float, minutes: int, mode: str = "up") -> float:
    """Round a duration to a multiple of ``minutes``.

    ``minutes`` of 0 (the default everywhere) means no rounding.

    NOTE(mdc): ``up`` is the default because that is what I bill.  Reporting
    applies this to *each session* before summing, not to the total, so a
    rounded report is reliably larger than an unrounded one -- fifteen
    five-minute sessions at ``--round 15`` come to three hours forty-five, not
    an hour and a quarter.  That is the intent, but it surprises people.
    """
    if not minutes:
        return float(seconds)
    if minutes < 0:
        raise ValueError("--round takes a positive number of minutes")
    step = minutes * 60
    if mode == "up":
        return float(-(-int(round(seconds)) // step) * step)
    if mode == "down":
        return float(int(seconds) // step * step)
    if mode == "nearest":
        return float(int(round(seconds / step)) * step)
    raise ValueError(f"unknown rounding mode: {mode!r}")
