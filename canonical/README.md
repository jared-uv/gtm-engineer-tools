# canonical

A registry of where each kind of company information lives, who owns it, how it is governed, and when someone last confirmed it is still right. One command answers "where does X live". Another lists what nobody has looked at lately.

## The problem

An agent asked for current positioning reads a six-year-old deck in Drive, because nothing told it where to look and when to stop. A teammate creates a second messaging file because they did not know the first one existed. Both are the same failure: the company has an answer for where things live, and it is in someone's head.

The fix is not a bigger search. It is a short, opinionated table that says: for this kind of information, look here first, then here, and stop. Think of it as a router for the agent. Without one, the agent either misses the answer or drowns in everything that looks like one, and an opinionated table with twenty rows beats a complete one with two hundred.

## Install

```
/plugin marketplace add le0li0n/gtm-engineer-tools
/plugin install canonical
```

Then, in the repo:

```
/canonical:setup
```

It writes a ten-row template to `CANONICAL.md` and walks through it with you one row at a time. It does not guess locations. A row you cannot answer keeps its placeholder and fails `check` until you decide, which is the point.

## The registry

`CANONICAL.md` at the repo root. It is the plugin's only configuration: every company-specific value lives in that file, and the plugin ships a template of it. A markdown table, so it reads without any tool.

| Type | Where | Class | Required | Owner | Cadence | Reviewed | Notes |
|---|---|---|---|---|---|---|---|
| Positioning | docs/positioning.md | governed | yes | Dana | 3m | 2026-09-01 | One answer. Do not reconstruct it from old decks. |
| Author voice | docs/authors/dana.md then docs/style-guide.md | governed | yes | Dana | 6m | - | The author profile wins. |
| Tasks | tasks: the team tracker | external | yes | Dana | - | - | Repos hold work products; the tracker holds actions. |

- **Type** is the kind of information, in the words people use when they ask for it.
- **Where** is a waterfall. First place first, and stop when found. Separate places with `then` (a `;` works too). A place is a repo path, a URL, or a named external system written as `name: detail`.
- **Class** is the governance. `open`: anyone writes. `governed`: the owner holds the pen and everyone else proposes. `external`: a system of record reached through a tool, so the row names the system rather than a path.
- **Required** is `yes` or `no`, for your own reading. Nothing enforces it.
- **Owner** is a person, not a team. Governed rows must have one.
- **Cadence** and **Reviewed**: how often the owner has to re-confirm the row (`30d`, `6w`, `3m`, `1y`, or `-`), and the date they last did (`YYYY-MM-DD`, or `-`). Git already records who changed what and when; this records whether anyone has looked.

Only `Type` and `Where` are required columns. The first table in the file with both is the registry; any other column is optional and matched by name. Prose around the table is fine.

## Commands

```
/canonical:where positioning      the entry, first place first
/canonical:where                  every entry
/canonical:where --stale          entries past their cadence, or with a cadence and no Reviewed date
/canonical:where --check          validate the registry
/canonical:setup                  write the template and fill it in with you
```

A lookup matches the Type exactly first, then as a substring, then every word of the query in the Type, then the same two in Notes, then a close spelling. A miss lists every Type the registry has.

`check` reports, and exits 1 on: an empty Type or Where, a duplicate Type, a Where path that does not exist in the repo, a Class that is not one of the three, a governed row with no Owner, a Cadence or Reviewed date in the wrong shape. Places that are URLs or `name: detail` systems are not checked.

The script behind the skills runs on its own, from a terminal, with the same verbs and `--json` on `list`, `where` and `stale`. In a terminal, `<plugin-dir>` is wherever the plugin is installed:

```
python3 <plugin-dir>/scripts/canonical.py where positioning --json
python3 <plugin-dir>/scripts/canonical.py stale
python3 <plugin-dir>/scripts/canonical.py check
python3 <plugin-dir>/scripts/canonical.py init
```

It finds the registry at the git repo root, or the current directory outside a repo. `CANONICAL_FILE=path` points it somewhere else. Exit codes: 0 fine, 1 no match or problems found or no registry, 2 an unknown command. In a repo with no `CANONICAL.md`, every command says so and points at `/canonical:setup`. Python 3.9 or later, standard library only.

## What the skill will not do

It will not search the repo when the registry is silent and present the result as canonical. That is the failure this exists to stop. It says the registry has no entry, and offers to add one.

## Making every session read it

`setup` offers one line for `CLAUDE.md`. That line is what turns a table into a router; without it the registry is documentation, and documentation is what the agent was ignoring before.

## Outside Claude Code

The skills run a Python script, so they need a Claude Code session that can run shell commands; the CLI is where this was built and tested. In Claude chat, or anywhere the plugin is not installed, nothing runs. The registry still works there as a document: paste or attach `CANONICAL.md` and the table answers "where does X live" by reading it. What you lose is `check` and `stale`, which you would have to do by eye.

## With the `permissions` plugin

On its own, the Owner column is a statement, not an enforcement. The `permissions` plugin from the same marketplace reads this registry if you install it, and turns every `governed` row into a rule: an edit to one of that row's paths by anyone other than its Owner has to go to the owner as a proposal. Without it, nothing reads the registry but this plugin. Keep the `Type`, `Where`, `Class` and `Owner` column names as they are if you use both, because that is what it looks for.

## Limits

- **A registry, not a guard.** No hook ships with this plugin. Nothing stops a file being created in the wrong place; the skill only tells the agent where the right place is when asked, and the `CLAUDE.md` line is what makes it ask.
- **A literal `|` inside a cell splits the cell**, and escaping it does not help. Write "or" instead.
- **A table inside a code fence counts.** If the file shows an example table with `Type` and `Where` columns above the real one, the example is read as the registry. Put examples below it.
- **Months are 30 days and years are 365** when working out whether a row is stale.
- **The path check is existence only.** It says `docs/positioning.md` is there, not that it holds positioning or that anyone has read it lately. That second question is what Cadence is for.

## Tests

From the plugin directory:

```
python3 scripts/test_canonical.py
```

It finds `canonical.py` beside itself, or takes a path to it as the first argument. 34 checks against a throwaway registry in a temp directory: parsing, the waterfall, lookup order, freshness, validation, the flag forms, `--json` on a miss, malformed and missing registries, and `init`. No network.
