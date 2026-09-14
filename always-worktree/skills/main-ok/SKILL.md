---
name: main-ok
description: >-
  Allow edits on the default branch for a while, overriding the always-worktree guard. Use when the user says "/always-worktree:main-ok", "it's fine to edit on main", "override the worktree check", or "let me commit here" — and only on the user's say-so, never because the guard blocked you. Also takes the override back early, or reports what the guard would decide.
---

# main-ok

The always-worktree guard blocks Write, Edit and write-looking Bash while the session is on the default branch. This skill switches it off for this repo, and every worktree of it, for a limited time.

## Rules

- **Only on the user's explicit instruction.** A blocked edit is not a reason to run this. Tell the user the guard fired and ask; if they say to go ahead on the default branch, run it.
- The override is per repo and expires. Default 240 minutes, or `allow_minutes` in `.claude/always-worktree.json`; the user can name a different number.
- Say what you did in one line so it is in the transcript.

## Steps

1. Run, from anywhere inside the repo:

```
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/guard.py" --allow
```

Add a whole number of minutes after `--allow` if the user named one.

2. Report the line it prints. Then carry on with the edit that was blocked.

To take the override back early:

```
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/guard.py" --revoke
```

To see what the guard thinks of the current directory without changing anything:

```
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/guard.py" --status
```
