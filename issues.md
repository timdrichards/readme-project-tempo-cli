# Open issues (exported from the tracker)

---

**#12 -- "tempo start" says "session already running" but there isn't one**
opened by rkessler

I closed my laptop on Friday with a session going. Today every `tempo start`
gives me:

```
tempo: session already running: thesis
tempo:   it started 2026-01-16 09:02 (71h 14m ago)
tempo:   `tempo stop` to log it, `tempo abort` to discard it
```

`tempo stop` then logs 71 hours, which is not what happened.

> **mdc** commented:
> `tempo abort` throws away the stale session without logging it. Then start a
> fresh one. If you want to keep the real hours, `tempo stop --at '5pm friday'`
> backdates the end.
>
> This comes up a lot. It should be in the docs.

---

**#19 -- report --since is inconsistent**
opened by jnwong

`--since 3d` works. `--since 2026-01-04` works. `--since jan4` reports
*everything I have ever logged*, with no warning. Took me an hour to work out
it wasn't my data.

Also `--until jan4` errors properly. So the two halves of the same window
disagree about what a bad date is.

> **mdc** commented:
> Right. `--since` tries a duration first, then a date, and if both fail it
> falls back to the beginning of time instead of raising. `--until` raises.
> That's a bug and it's mine.
>
> `jan 4` with a space does parse, for what it's worth. The workaround is ISO
> dates. Leaving open -- fixing it changes behaviour for anyone scripting
> against it, so it waits for 0.5.

---

**#23 -- Does this work on Windows?**
opened by student-account-91

Title says it. I don't see anything about it anywhere.

> **mdc** commented:
> Honestly untested. The paths should be fine -- nothing shells out. The
> `--at '9:15am'` parsing assumes English: the month names, the weekday names
> and "am"/"pm" are all hardcoded. ISO dates and 24-hour times work regardless.
> Try it and report back.

---

**#24 -- can I get at the data without shelling out to the CLI?**
opened by p.arnesen

I want to pull my hours into a reporting script rather than parsing
`tempo report --csv`. Is there anything importable, or should I just read
log.db myself?

> **mdc** commented:
> Don't read log.db directly, the schema moves. There's a Python API:
> `from tempo import Tempo`, then `t.report(...)` gives you a Report object
> with `.rows` and `.total_seconds` on it.
>
> If what you want is a different *output* shape there's a formatter registry
> too -- `register_formatter("mine", fn)` and then `tempo report --format mine`
> picks it up.
>
> None of this is written down anywhere, which is my fault.
