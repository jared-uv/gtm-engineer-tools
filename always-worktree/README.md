# always-worktree

Stops a Claude Code session from editing on the default branch. Edits happen in a worktree on a branch, or not at all, unless you say otherwise for a while.

## The problem

A session starts in the main checkout on `main`, the first edit lands there, and by the time anyone notices there are six commits on `main` that should have been a PR. Or a second session opens in the same checkout and both are editing the same working tree. Worktrees fix both, and the only thing that goes wrong is forgetting to use one.

This makes forgetting impossible and overriding cheap.

## Install

```
/plugin marketplace add le0li0n/gtm-engineer-tools
/plugin install always-worktree
```

Nothing to configure. From the next prompt, any session on the default branch is told to move before it edits, and any edit it tries anyway is refused with the same message.

## What it does

| Event | On the default branch | Anywhere else |
|---|---|---|
| Each prompt | Adds a line of context: you are on `main`, edits will be blocked, move to a worktree or ask the user about the override. | Silent. |
| Write, Edit, MultiEdit, NotebookEdit | Denied, with the fix in the message. | Allowed. |
| Bash | Denied if the command looks like a write (list below). Reads pass. | Allowed. |

Write, Edit, MultiEdit and NotebookEdit are judged by the repo that holds the file being written, not by where the session started. A session in the main checkout can still write to a scratch directory outside the repo, or into one of its own linked worktrees. A session in a worktree that reaches back into the main checkout on `main` is refused.

Bash is judged by the session's working directory, because a command string has no reliable target. A command counts as a write if it contains any of these:

- a redirect to a file (`>` or `>>`; `2>&1` and redirects to `/dev/null` don't count)
- a heredoc (`<<EOF`)
- `tee` or `sed -i`
- `cp`, `mv`, `rm`, `mkdir`, `touch` or `ln`
- `git add`, `commit`, `mv`, `rm`, `merge`, `rebase`, `cherry-pick` or `apply`
- `python`, `python3`, `node`, `ruby` or `perl` followed later on the line by `open(`, `write` or `Path(`

The Bash check is a heuristic and is meant to be. It catches a heredoc into a tracked file and a `git commit` on `main`, which are the two ways edits on `main` actually happen once Write and Edit are blocked. A quoted `>` in an echo will trip it, and so will a read-only heredoc. That is the cost of not being bypassable by the obvious route, and the override is one command away. It is also not complete: `git reset --hard` or `git checkout -- .` pass, because they are not in the list.

## The override

```
/always-worktree:main-ok
```

Allows edits on any branch in this repo for 240 minutes, then expires on its own. Give it a number for a different duration. It is written to the repo's shared git directory (`.git/always-worktree-allow` in the main checkout), so it covers every worktree of that repo and reaches no other repo.

The skill behind it has one rule: it runs on the user's say-so, never because the guard blocked something. A blocked edit is a prompt to ask, not to override.

The skill can also take the override back early or report what the guard would decide right now. Ask for either, or run the script yourself from inside the repo, with the path to wherever the plugin is installed:

```
python3 <plugin-dir>/hooks/guard.py --revoke
python3 <plugin-dir>/hooks/guard.py --status
```

`ALWAYS_WORKTREE_OFF=1` in the environment disables the guard for that shell. For machines where you never want it.

## Config

Optional, in `.claude/always-worktree.json` at the repo root:

```json
{
  "mode": "branch",
  "gate_bash": true,
  "default_branch": "main",
  "allow_minutes": 240
}
```

- `mode`: `branch` (the default) blocks the default branch wherever it is checked out. `strict` also blocks the main checkout on any branch, so every edit happens in a linked worktree. Strict is the right setting when several sessions share one clone; `branch` is enough for one person who just wants nothing to land on `main` by accident.
- `gate_bash`: default `true`. Set `false` if the Bash heuristic gets in the way. Write and Edit stay blocked.
- `default_branch`: skip detection. Otherwise the guard uses, in order: what `origin/HEAD` points at; what any other remote's `HEAD` points at; the local branch named by git's `init.defaultBranch` setting; a local `main`; a local `master`. If none of those exists, no branch counts as the default and only `strict` mode blocks anything. `--status` says so.
- `allow_minutes`: default 240. How long the override lasts.

A missing or unreadable file, or a value of the wrong type, falls back to the defaults. The file is read from the top of whichever checkout the edit is in, so commit it if you want worktrees to see it too.

## Tests

From the plugin directory:

```
python3 hooks/test_guard.py
```

Builds throwaway repos, with your global git config ignored, and runs 43 cases: each tool on the default branch and off it; edits aimed across checkouts and outside any repo; the read-only and write-looking Bash commands; the override set, revoked, expired, set from a worktree, and kept out of other repos; both modes; `gate_bash` off; broken config and broken payloads; the environment switch; a directory that is not a repo; and default-branch detection for `trunk` with and without a hint, `master` with no remote, an `origin/HEAD` that points at `develop`, and a repo whose only remote is `upstream`.

## Limits

- Hooks run in the Claude Code CLI and in editors that host it. Where plugin hooks don't run, such as Claude desktop chat or claude.ai, this plugin does nothing. A person at a terminal is not affected either, and that is correct: this is a guard against the agent forgetting, not a branch-protection substitute.
- A brand-new repo with no commits is never blocked. There is nothing to branch from yet, and a worktree needs a commit.
- An `origin` added by hand, rather than by `git clone`, often has no `origin/HEAD`. `git remote set-head origin --auto` fixes that, or set `default_branch`.
- The guard reads local refs only and never touches the network, so it does not notice when the remote's default branch changes until `origin/HEAD` is updated.
- Python 3 has to be on the path as `python3`. No other dependencies.
