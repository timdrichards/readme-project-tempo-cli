From: p.arnesen@example.edu
To: mdc@example.com
Subject: tempo -- can't get past the first step (sorry!)

Hi,

A colleague recommended tempo for tracking hours against my grant projects and
I've been trying to set it up for about forty minutes. I'm probably doing
something obvious wrong, but I can't tell what.

I ran `pip install tempo-cli` and it seemed to work. Then `tempo-cli start` did
nothing -- "command not found". I eventually found a forum post that said the
command is just `tempo`, which worked.

Then I ran `tempo report` and got:

    nothing logged for 2026-03-16
    tempo: nothing in this window, but 3 sessions are stored between
    2026-03-12 09:40 and 2026-03-14 17:05

So it could see my data and still showed me an empty table, which I found more
confusing rather than less. I tried again three times, then went looking for a
"show everything" flag and couldn't find one.

I've since worked out that `tempo report` only shows today, and my sessions
were from before midnight, so they were there the whole time. `tempo report -w`
does what I originally expected. I'm not sure whether the default is intended.

Two more things, if you have a minute:

One, I want my data on a shared drive, and I saw TEMPO_HOME mentioned in a
comment in the source. Is that supported? Should I set it before the first run?

Two, I have a session from last Tuesday that I forgot to stop and it recorded
about thirty hours. Is there a way to correct it, or do I delete it and start
over?

Thanks for making this. Once I understood it, it's exactly what I wanted.

Best,
Petra
