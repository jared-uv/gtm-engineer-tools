---
name: where
description: >-
  Answer "where does X live" from the company's CANONICAL.md registry instead of
  from memory or grep. Use when the user asks where something is kept, which file
  is the source of truth for something, or before creating a file that holds
  company information; also when the user says "/canonical:where", "what's
  stale", "what needs review", or "check the registry". Pass --stale for entries
  past their review cadence and --check to validate the file.
---

# where

The registry is `CANONICAL.md` at the repo root. It says, for each kind of information, where to look first and where to look next, who owns it, whether the owner holds the pen, and when someone last confirmed it is right. Read it before searching, and stop at the first place that answers.

## Steps

1. Run the lookup. `$ARGUMENTS` is whatever followed the command.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/canonical.py" where "$ARGUMENTS"
```

   With no arguments, run `list` instead. `--list`, `--stale` and `--check` pass straight through: the script treats them as the `list`, `stale` and `check` commands.

   If it says there is no registry, say so and offer `/canonical:setup`. Do not go looking for the information another way.

2. Report what it printed. For a lookup, name the first place and the class in one sentence, and say whether the entry is stale. Do not open the file unless the user's question needs its contents.

3. If nothing matched, the script lists every type it knows. Pick the closest if there is one; otherwise say the registry has no entry for that, and offer to add a row. Adding a row is an edit to `CANONICAL.md`, and if that file is governed, it goes to its owner as a proposal.

4. If the user is about to create a file of some type, and the entry says where that type lives, put the file there. If the entry is `governed` and the user is not the owner, say so before writing.

## What the columns mean

- **Where** is a waterfall. First place first; stop when found. Separated by `then`.
- **Class**: `open` anyone writes; `governed` the owner holds the pen and everyone else proposes; `external` a system of record reached through a tool, so the entry names the system and the tool rather than a path.
- **Cadence** and **Reviewed**: how often the owner has to re-confirm the entry, and when they last did. `stale` is the list of entries where that has lapsed or never happened.

## Not this skill

This does not search the repo. If the registry has no entry, do not fall back to grep and call the result canonical; say the registry is silent and let the user decide where the thing lives.
