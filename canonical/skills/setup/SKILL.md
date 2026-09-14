---
name: setup
description: >-
  Create CANONICAL.md for a repo that has none: write the template, then fill it
  in with the user one entry at a time, validate it, and add the one line to
  CLAUDE.md that makes every session read it. Use when the user says
  "/canonical:setup", "set up the registry", "where should things live", or
  installs the canonical plugin in a repo with no CANONICAL.md.
---

# setup

Produces a `CANONICAL.md` the user agrees with, not one you guessed. The template has ten rows that most companies need; the interview confirms or replaces each one.

## Rules

- **One question per message.** Never batch. Each row is one exchange.
- **Do not invent locations.** If the user does not know where something lives yet, leave the row with `Where` empty and say it will fail `check` until they decide. That is the point.
- **Owner is a person.** A team name is not an owner.

## Steps

1. Write the template if there is no registry yet:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/canonical.py" init
```

   If it says the file already exists, stop and switch to `/canonical:where --check`; this skill is for first setup.

2. Read the file back. Then walk the rows in order. For each, ask one question: does this kind of information exist here, and where does it live? Take the answer, edit the row, move on. Where the answer names a path, check it exists before writing it in.

3. When the template rows are done, ask once: what other kinds of information do people ask "where is" about? Add a row per answer, same way.

4. For every `governed` row, ask who owns it. For every row with a cadence, leave `Reviewed` as `-`; the owner sets it when they first confirm.

5. Validate:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/canonical.py" check
```

   Fix what it reports. Missing paths and missing owners are the usual ones.

6. Offer to add this line to the repo's `CLAUDE.md`, under whatever section lists the repo's navigation files. It is what turns the registry into a router every session follows:

```
- `CANONICAL.md` — where each kind of information lives, who owns it, and when it was last confirmed. Read it before searching for company information or creating a file that holds some. `/canonical:where <type>`.
```

7. Report: the number of rows, how many are governed, how many have no owner yet, and the `check` result.
