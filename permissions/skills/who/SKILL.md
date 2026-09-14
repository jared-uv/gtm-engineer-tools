---
name: who
description: >-
  Say who may change a path and what happens if someone else tries, from
  PERMISSIONS.md and the governed rows of CANONICAL.md. Use when the user asks
  "can I edit this", "who owns this file", "why was that edit refused", or says
  "/permissions:who"; also when the permissions hook has just refused an edit
  and you need to explain it. Pass a path, or --rules for the whole list,
  --whoami for the identities in play, --check to validate the files.
---

# who

## Steps

1. Run it from inside the repo. `$ARGUMENTS` is a path or one of the flags `--rules`, `--whoami`, `--check`:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/permissions.py" test $ARGUMENTS
```

   The flags pass straight through: `test --rules` runs `rules`, `test --whoami` runs `whoami`, `test --check` runs `check`. Add `--as <identity>` after a path to ask what would happen for someone else.

2. Report the decision in one sentence: allowed, blocked and by whom, or proposal. Name the rule's source file and line so the user can find it. A path in another checkout is judged against that checkout's rules, and the output says so.

## When the hook has refused an edit

- **Blocked.** Do not work around it: no Bash heredoc into the file, no copy-and-rename. Tell the user who owns the path and stop. If the user is that person and git does not know it, the fix is `git config user.name` or `user.email` in this repo, or `GITHUB_USER` in the environment, and then the edit goes through on its own.
- **Proposal.** The first attempt was refused so the rule would be in the transcript. Tell the user the path is governed by the named owner, then retry the same edit; the second attempt goes through. When the work is shipped, the PR must carry the `hold` label and name the owner as reviewer. If another skill opens the PR, tell it that; otherwise `gh pr edit <number> --add-label hold`, creating the label first with `gh label create hold` if the repo does not have one.

## What `hold` does

Nothing by itself. It is a label that says "the owner has not decided yet". An auto-merge workflow that skips labelled PRs (the automerge plugin in the same marketplace does) turns it into a real wait. Without one, it is a signal to whoever merges, and the owner's review is only as strong as their habit of honouring it. Say which is true for this repo if you can see its workflows.

## What this is not

A security boundary. Identity is whatever git config says. This catches the honest mistake of editing a file someone else owns, and it gets the rule in front of the person at the moment it matters. The enforcement nobody can bypass is `CODEOWNERS` with branch protection, which `/permissions:codeowners` generates.
