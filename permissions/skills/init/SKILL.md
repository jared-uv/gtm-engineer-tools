---
name: init
description: >-
  Write a starter PERMISSIONS.md at the root of the current repo from the
  plugin's template, keeping only the example rows for paths this repo has.
  Use when the user says "/permissions:init", "set up permissions", "who may
  change what", or asks to protect files in a repo that has no PERMISSIONS.md.
---

# init

1. Run it from inside the repo:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/permissions.py" init
```

   It never overwrites an existing `PERMISSIONS.md`. It reports the template rows it left out because the path does not exist here.

2. Ask the user who owns each remaining row, one row at a time. Write names, emails or `@github-handles` in the Who column; a `@handle` is what lets the rule reach `CODEOWNERS`. Ask whether any other paths need a rule.

3. Validate:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/permissions.py" check
```

   Fix what it reports. Then tell the user that the hook is now live in their Claude sessions, that commits are only checked if they wire `staged` into a pre-commit hook (the README shows how), and that `/permissions:codeowners` generates the GitHub layer.
