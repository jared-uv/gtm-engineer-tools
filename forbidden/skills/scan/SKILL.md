---
name: scan
description: >-
  Scan files or the staged index for information the repo must never hold,
  using FORBIDDEN.md, and say where each kind belongs instead. Use when the user
  says "/forbidden:scan", "is there anything sensitive in here", "check for
  secrets", "check for PII", before committing a raw export, or when the
  forbidden hook has just refused a write and you need to explain it. Pass
  paths, or --staged, or --check to validate the registry, or --patterns.
---

# scan

## Steps

1. Run it. `$ARGUMENTS` is one or more paths, or one of the flags `--staged`, `--check`, `--patterns`. With nothing, it scans the current directory.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forbidden.py" scan $ARGUMENTS
```

   Each file is judged by the `FORBIDDEN.md` of the git repository that holds it. If the output says there is no `FORBIDDEN.md`, nothing was checked; offer `/forbidden:init`.

2. Report each finding as the class, the file and line, and the Instead column. The sample is already redacted; do not print the matched text in full, and do not open the file to show it.

3. For a `block` finding, the fix is never to obfuscate the value so the pattern stops matching. Move the information where Instead says, and leave a reference here if one is needed. If the value is already committed, say that removing it from the file does not remove it from history, and that a real credential has to be rotated.

4. For a `warn` finding, judge it. The heuristic counts distinct addresses or numbers, so a list of speakers in event notes and a customer export look the same to it. If the file sits where the registry's Instead says such lists may live, say so and move on. If it is a list of contacts somewhere else, that is the finding the rule exists for.

## When the hook has refused a write

- A `block` refusal names the class and the Instead. Tell the user, and do not retry the write with the value disguised.
- A `warn` turned the write into a permission prompt. The user saw the reason and decided. If they allowed it, carry on. If they denied it, ask where the information should go.

## Fixtures and documentation

A line containing `forbidden-ok` is skipped. Use it for a test fixture or a doc that has to show what a pattern looks like, never to get a real value past the check.
