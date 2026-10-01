# Slack thread, #tempo-dev, last Tuesday

**mdc** 10:02
i want to cut 0.5 this week. what's blocking

**jnwong** 10:04
nothing in code. the thing blocking us is that nobody can install it without
asking you a question first

**mdc** 10:04
it's pip install tempo-cli?

**jnwong** 10:05
it's `pip install tempo-cli` and then you have to know that the binary is
`tempo`, not `tempo-cli`, and that the first run creates ~/.tempo, and that if
you set TEMPO_HOME after you've already run it your old data is invisible

**jnwong** 10:06
i watched two people bounce off it this month. both of them thought it was
broken

**mdc** 10:07
fair. i've been meaning to write a proper readme since january

**jnwong** 10:08
also please say somewhere that report defaults to *today*. everyone assumes
it's all-time and thinks their data is gone

**jnwong** 10:09
and it's worse than that because `tempo tags` IS all-time. so the same person
runs both and gets two different answers about whether their data exists

**mdc** 10:11
yeah that's just history, tags came later. not changing it before 1.0

**mdc** 10:12
while you're listing things: `--round 15` rounds every session up, not the
total. that's what i want for invoicing but the first time someone sees a
3 minute session bill as 15 they'll file a bug

**jnwong** 10:14
write it down then

**jnwong** 10:15
last one. `tempo import` doesn't de-duplicate. i imported the same export
twice last week and doubled march. `--dry-run` would have told me, i just
didn't use it

**mdc** 10:16
noted. also we still ship click as a dependency and nothing has imported it
since 0.3. i'll pull it eventually, it's harmless

**jnwong** 10:16
"harmless" he says, in the thread about why installs confuse people
