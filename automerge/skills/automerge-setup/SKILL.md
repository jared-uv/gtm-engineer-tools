---
name: automerge-setup
description: >-
  Set up PR auto-merge on the GitHub repo you are in: installs a scheduled
  workflow that squash-merges any open PR older than 15 minutes with no
  conflict, no failing check, no `hold` label and not a draft, every half
  hour; turns on delete-branch-on-merge; creates the `hold` label. Use when
  the user says "/automerge-setup", "set up automerge", "auto-merge my PRs",
  or complains that PRs are piling up in a repo. Self-contained — copy this
  folder to any repo's `.claude/skills/`, or to `~/.claude/skills/` to have
  it everywhere.
---

# automerge-setup

Installs auto-merge on the GitHub repo of the current checkout. One script, three idempotent steps, one manual merge at the end.

## What's in this folder

| File | Role |
|---|---|
| `setup.sh` | Does the work. Run it; don't reimplement its steps by hand. |
| `automerge.yml` | The workflow it installs. **This copy is the source.** The repo's `.github/workflows/automerge.yml` is an install of it. |

## Steps

### 1. Run the script from anywhere inside the target repo

```
bash "${CLAUDE_PLUGIN_ROOT:-.claude}/skills/automerge-setup/setup.sh"
```

`CLAUDE_PLUGIN_ROOT` is set when this is installed as a plugin; the fallback covers a hand-copied `.claude/skills/` folder. If neither path exists, find `setup.sh` next to this file and run that — never reimplement its steps inline.

Add `--dry-run` first if the user wants to see what would change. The script:

- turns on `delete_branch_on_merge` (skips if already on)
- creates the `hold` label (skips if it exists)
- commits `automerge.yml` to a fresh `automerge-setup-<timestamp>` branch cut from the default branch, pushes it, and opens a PR. If the workflow is already on the default branch, or a setup PR is already open, it says so and stops.

The user's working tree is never touched. The commit happens in a throwaway git worktree that is removed on exit, so it's safe to run with other work uncommitted.

### 2. Report

Relay the script's output. The line that matters is the PR URL, with this said plainly: **the user merges that PR by hand, once.** GitHub only runs scheduled workflows from the default branch, so the workflow can't merge itself in. After that every later PR that meets the rules merges on its own.

Never merge the setup PR yourself.

### 3. If the push is rejected

Pushing a file under `.github/workflows/` needs the `workflow` scope on the gh token. The script prints the fix; pass it on:

```
gh auth refresh -h github.com -s workflow
```

then run the script again.

## What the installed workflow does

Every 30 minutes, and on demand from the Actions tab, it lists open PRs and squash-merges each one that is:

- at least 15 minutes old
- mergeable with no conflict
- not a draft, and not labeled `hold`
- free of pending or failing checks

Conflicted PRs are skipped and named in the run log for a person to resolve. Nothing is rebased or resolved automatically.

**To change the timing**, edit two numbers in `automerge.yml`: the `cron` line (how often it runs) and `MIN_AGE_MINUTES` (how old a PR must be). Change them in this folder's copy first, then re-run the script; it will report that the installed copy differs and leave the decision to you.

## Why a workflow, not GitHub's own auto-merge

GitHub's built-in auto-merge only activates on a base branch with branch protection, and private repos on the free plan can't have branch protection. A workflow with `contents: write` and `pull-requests: write` does the same job without it. Cost is a few hundred Actions minutes a month against the free plan's 2,000.

## Portability

Nothing here is specific to one repo. The workflow reads the repo name from GitHub at run time and the script reads it from the checkout. Copy the whole folder, not just `SKILL.md`, since the script needs the template next to it.
