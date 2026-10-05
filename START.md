# Start here — tempo

## What this project is

**tempo** is a command-line tool that tracks how much time you spend on
different projects. You start a timer with a tag, stop it when you're done, and
ask for a report later. It stores everything locally in a small database. It
can also be imported and driven from Python.

It was written by one developer for her own invoicing, and other people started
using it. It works. It has never had a README.

**Your job:** write that README.

## Who you are writing for

Someone who has just been told "try tempo" and has a terminal open. They have
not read the source. They will give the page about fifteen seconds before
deciding whether this is worth their afternoon.

Some of them will stop at the command line. A few will want to import it. Both
readers land on the same page.

## What's in this folder

| File | What it is |
|---|---|
| `pyproject.toml` | The packaging manifest: the install name, the dependencies, the command it creates |
| `src/tempo/__init__.py` | The public Python API: the `Tempo` class, what's exported, the version |
| `src/tempo/cli.py` | The command line: every subcommand and flag, the output, the error messages, and the developer's own comments |
| `src/tempo/storage.py` | The SQLite layer: where data lives, how the home directory is chosen, the running-session file |
| `src/tempo/reporting.py` | Aggregation and output formats, including the registry that lets you add your own |
| `src/tempo/timeparse.py` | Parsing of `--at`, `--since`, `--until` and durations; duration formatting |
| `issues.md` | Four issue threads from the tracker, with the maintainer's replies |
| `dev-chat.md` | A Slack thread between the two developers about why nobody can install it |
| `user-email.md` | An email from Petra, a researcher who spent forty minutes trying to get started |
| `SPEC.md` | The README specification for this assignment: the sections your README needs, in order |
| `PEER.md` | How your README is written on a branch, peer reviewed, merged, and submitted |

## A reading order that works

1. **`pyproject.toml` first.** It is the shortest file and it tells you what
   the thing is called and what it installs. Two of those facts matter more
   than they look.
2. **`src/tempo/cli.py`.** This is the biggest file and the most important one.
   Read `build_parser()` for the full inventory of commands and flags, then the
   `cmd_*` functions for what each one actually prints. Read the comments as
   carefully as the code: the developer leaves notes to herself that are really
   notes to a user.
3. **`user-email.md`.** This is your reader, in their own words, telling you
   exactly where they got stuck. Everything Petra struggled with is a section
   of your README.
4. **`issues.md`.** Questions people ask more than once belong on the page.
   Look for the moment the maintainer says something should be in the docs.
5. **`src/tempo/__init__.py`**, for the API half. The module docstring and
   `__all__` tell you what is public and what is internal. Everything not in
   `__all__` is somebody else's business.
6. **`storage.py`, `reporting.py`, `timeparse.py`** as needed. You do not have
   to understand all of this, but when the CLI does something you can't explain
   from `cli.py` alone, the answer is in one of these three.
7. **`dev-chat.md` last.** The developers say out loud what they think is wrong
   with the onboarding. Treat it as a requirements list.

## Before you start writing

Answer these for yourself. If you cannot, go back to the material.

- What do you type to install it, and what do you type to run it?
- What is the very first thing a new user should do after installing?
- What are the two or three ways a new user is most likely to get stuck?
- Where does the data live, and how would someone move it?
- What can a Python caller do that a shell user can't, and vice versa?
- What does this tool *not* do, or not do reliably?

## What the README has to contain

**Follow [SPEC.md](SPEC.md).** It is this assignment's README specification,
adapted from the [Standard Readme spec](https://github.com/RichardLitt/standard-readme).
It lists the sections, in order: Title, an optional Banner, Description, Table
of Contents, Install, Usage, optional extra sections, API (required: this
project has one), Maintainers, and Credits. Read it before you start. It is
short, and it settles most of the arguments you would otherwise have with
yourself about what goes where.

**Include worked examples of both halves of the project.**

- *The CLI.* Several real invocations with the output they produce. Not only
  the happy path: show at least one thing going wrong and what the user does
  about it. An example a reader can paste is worth three paragraphs.
- *The library.* How to import it and use it from Python, and one example of
  extending it through the formatter registry.

Examples must be consistent with the source in this folder. If you are not
sure what a command prints, that is a sign to go back and read `cli.py` rather
than to make something up.

## How you write it, and how it is reviewed

**Work only in the GitHub website.** Write `README.md` in your browser, in
your repository on GitHub. Do not clone the repository or use another editor:
every step of this assignment is explained inside GitHub, and course staff can
only help with problems that happen there.

You write the README on a branch called `readme-draft` and open a pull
request, where two classmates review it line by line. You revise, they
approve, you merge, and you submit a PDF of the finished README on Canvas.
[PEER.md](PEER.md) explains every step, starting with how to create
`README.md`.

## Two rules

**Use only what is in this folder.** Do not invent features, flags, or
behaviour that the material doesn't support. If you find yourself guessing,
that guess is a question for the maintainer, not a sentence in the README.

**If something is genuinely unclear, say so.** "Not tested on Windows" is a
useful sentence. Silence is not.

## Where your README goes

This repository is your own copy of the project, made from the course template. Write your README as a file named `README.md` at the top level of this repository, next to this `START.md`, not inside `src/`.

Do not commit it straight to the `main` branch. Create it on a branch called `readme-draft` and open a pull request, as [PEER.md](PEER.md) explains, so your reviewers can comment on it. Once both reviewers approve and you merge, GitHub shows `README.md` on the repository's front page: open your repository in a browser and check that it reads the way you meant it to. Leave every other file as it is: your README describes this code, it does not change it.

Your instructor will tell you when drafts are due, who your reviewers are, and the GitHub usernames to add as collaborators.
