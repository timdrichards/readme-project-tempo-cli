# README Specification

This is the specification your `README.md` must follow. It is adapted from the [Standard Readme specification](https://github.com/RichardLitt/standard-readme/blob/main/spec.md), with some sections removed and some made required for this assignment.

A specification turns "is this a good README?" partly into a question anyone can check: are the sections there, in the right order, doing their job? The rest of the quality is in the writing, and your project's `START.md` says what your particular reader needs.

Your reviewers will use the **Reviewers check** line under each section when they review your pull request (see [PEER.md](PEER.md)).

## General rules

- The file is named exactly `README.md` and sits at the top level of your repository, next to `START.md`.
- It is written in Markdown and displays correctly on GitHub.
- The sections appear in the order below. Optional sections may be left out; required sections may not.
- Section headings use the exact names given here, as level 2 headings (`## Install`). The only level 1 heading (`#`) is the title.
- Every link works, including the links in your Table of Contents.
- Every command, flag, option, function and output you show matches the code in `src/`. If you are not sure, go back to the code. Do not invent behaviour the material does not support.

## Sections, in order

| # | Section | Status |
|---|---|---|
| 1 | Title | Required |
| 2 | Banner | Optional |
| 3 | Description | Required |
| 4 | Table of Contents | Required |
| 5 | Install | Required |
| 6 | Usage | Required |
| 7 | Extra sections | Optional |
| 8 | API | Required |
| 9 | Maintainers | Required |
| 10 | Credits | Required |

Background, Badges, Security, Contributing and License from the Standard Readme specification are not part of this assignment. Do not include them.

---

### 1. Title

**Required.**

- A level 1 heading with the project's name, for example `# tempo`.
- The name matches the project's name in its manifest (`pyproject.toml` or `package.json`). If the name people install or type is different from the project's name, say so in the Description.

**Reviewers check:** Is there exactly one level 1 heading, and is it the project's real name?

### 2. Banner

**Optional.**

- An image directly after the title, with no heading of its own.
- The image file is stored in your repository and linked from there, not from another website.

**Reviewers check:** If there is a banner, does it come straight after the title and load from the repository?

### 3. Description

**Required.**

- Comes directly after the title (and banner, if there is one). It has **no heading of its own**.
- Opens with a single sentence on its own line that says what the project is and who it is for. Someone who reads only that sentence should know whether to keep reading.
- Follows with a longer description, one to three short paragraphs: what the project does, the main reasons someone would use it, and anything the reader must know before they start (for example, that the install name differs from the command name).

**Reviewers check:** After the first sentence, do I know what this is and whether it is for me? Does the Description avoid having its own heading?

### 4. Table of Contents

**Required.** Written by hand.

- A level 2 heading, `## Table of Contents`, followed by a list of links.
- Links to every level 2 heading that comes after it. It does not list the Title or the Table of Contents itself.
- It may also list level 3 headings, indented under their section.
- Every link takes the reader to the right heading.

**How to write the links.** GitHub gives every heading an address you can link to within the same page. The address is the heading text in lower case, with spaces turned into hyphens and most punctuation removed, after a `#`:

| Heading | Link |
|---|---|
| `## Install` | `[Install](#install)` |
| `## Usage` | `[Usage](#usage)` |
| `## Known limitations` | `[Known limitations](#known-limitations)` |
| `### CLI` | `[CLI](#cli)` |

So the start of a Table of Contents looks like this:

```markdown
## Table of Contents

- [Install](#install)
- [Usage](#usage)
  - [CLI](#cli)
- [API](#api)
- [Maintainers](#maintainers)
- [Credits](#credits)
```

To check a link, commit your change and view `README.md` on GitHub, then click the link. You can also hover over any heading on GitHub and click the link symbol that appears next to it: the address bar then shows that heading's exact address.

If you rename a heading, update its link.

**Reviewers check:** Does every level 2 heading after the Table of Contents have a link? Click every link: does each one land on its heading?

### 5. Install

**Required.**

- A code block showing exactly what to type to install the project.
- What the reader needs first (for example, a Python or Node version), and how to check they have it.
- How to confirm the install worked.
- A `### Dependencies` subsection if anything must be installed separately or by hand.

**Reviewers check:** Using only this section and the project's files, could I install it? Are the commands correct for this project's manifest?

### 6. Usage

**Required.** This section is about the **command line**: what a person types in a terminal.

- Written as a walkthrough: start with the first thing a new user should do, and build from there.
- A `### CLI` subsection with several real commands in code blocks, each followed by the output it produces.
- More than the happy path: show at least one command that goes wrong, the message the user sees, and what they do about it. Your `START.md` may ask for more (for example, a dry run).

**Reviewers check:** Do the commands match the code? Could I follow them in order? Is there at least one case that goes wrong, with the fix?

### 7. Extra sections

**Optional.** Zero or more sections between Usage and API, each with a heading that names its content, such as `## Configuration`, `## Troubleshooting` or `## Known limitations`.

- Use these for things a reader must know that do not fit in Install or Usage: where data is stored, what the tool does not do, questions the material leaves unanswered.
- Do not title a section "Extra sections".

**Reviewers check:** Does each extra section earn its place, and is its heading in the Table of Contents?

### 8. API

**Required.** This section is about using the project **from code**: importing it into another program.

The API section is written in a different style from Usage. Usage is a walkthrough that a person follows in order. API is a **reference** that a programmer looks things up in.

- One entry for each part of the public API (what the package exports): its name, what it takes, what it returns, and what errors it can raise or throw.
- Short code examples: at least one complete example a reader can copy and run from their own program, and one example of extending the project through its extension point (named in your `START.md`).
- Anything that is internal and should not be relied on is left out, or clearly marked as internal.

A reference entry can be as simple as this:

````markdown
### `greet(name, loud=False)`

Returns a greeting for `name`.

- `name` (str): who to greet. Must not be empty.
- `loud` (bool, optional): if true, the greeting is in capitals. Defaults to false.
- Returns: the greeting, as a string.
- Raises: `ValueError` if `name` is empty.

```python
greet("Sam")  # "Hello, Sam"
```
````

(`greet` is a made-up function, there only to show the shape of an entry. Use the real names from your project's code.)

**Reviewers check:** Does it read as a reference rather than a second walkthrough? Does every name match an export in the code? Is there a runnable example and an extension example?

### 9. Maintainers

**Required.**

- Titled `## Maintainers`.
- Lists who maintains this README and repository. For this assignment, that is you: your name and a link to your GitHub profile.

**Reviewers check:** Is the maintainer named, with a working link?

### 10. Credits

**Required.** The last section of the README.

- Titled `## Credits`.
- Lists every source, tool and person you drew on in writing this README: the original developers (their names are in the project files), any outside documentation or examples you used, classmates or reviewers whose suggestions you took, and **any AI tool you used, with what you used it for**.
- If you drew on nothing beyond the project's own files, say so.

**Reviewers check:** Is it the final section? Does it credit the original developers? Is AI use, if any, stated plainly?
