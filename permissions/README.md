# permissions

Paths only named people may change. A short table of rules, plus every governed row of a `CANONICAL.md` if the repo has one, enforced three ways: as a hook inside Claude Code sessions, as a pre-commit check, and as a generated `CODEOWNERS`.

## The problem

Shared context only stays sharp if some of it has a single pen-holder. Positioning is one person's call. A signed contract is not edited by whoever is passing. The registry that says where things live is not rewritten by the agent that could not find something. Asking nicely does not hold those lines, and the person who crosses one is almost never malicious. They did not know.

So the rule has to be stated at the moment it matters, and the honest mistake has to be refused. Everything else about this plugin follows from those two sentences.

## Install

```
/plugin marketplace add le0li0n/gtm-engineer-tools
/plugin install permissions
```

Then, in a Claude Code session inside the repo, run `/permissions:init`. It writes `PERMISSIONS.md` at the repo root from the template, keeping only the example rows whose paths exist here (the registries, `CLAUDE.md`, `.claude/`, `.github/`, `contracts/`), then asks who owns each one and runs `check`. Nothing is enforced until that file, or a `CANONICAL.md` with governed rows, exists.

## Two outcomes on a miss

| On miss | What happens | For |
|---|---|---|
| `block` | The edit is refused. In a Claude session the hook denies the tool call and says who owns the path. At commit, the staged check refuses the commit. | Paths where an unapproved change is simply wrong: signed paper, CI, the registries. |
| `propose` | The edit goes through, after one refusal per session that states the rule so it is in the transcript. The change then has to reach the owner as a PR carrying the `hold` label. | Governed content: positioning, messaging, a launch plan. |

`propose` exists because canonical context is a working theory that gets revised. The people who talk to customers every day find out first when the positioning is wrong, and they have to be able to say so without being able to overwrite it. A proposal is how that feedback reaches the owner when the owner is one person and the contributors are many.

**What `hold` does.** By itself, nothing: the plugin never creates the label, adds it, or reads it. It only tells whoever opens the PR to add it. What makes it a gate is a merger that respects it. The `automerge` plugin in this marketplace skips any PR labelled `hold`, so with that installed a proposal waits for the owner. Without it, `hold` is a note to whoever merges, and it is as strong as their habit of reading labels.

## Where enforcement actually happens

| Layer | Real for | Silent for |
|---|---|---|
| `PreToolUse` hook on Write, Edit, MultiEdit and NotebookEdit | Every file tool call Claude makes in Claude Code | Bash commands that write the file, humans at a terminal, Claude surfaces that do not run plugin hooks |
| Pre-commit (`permissions.py staged`) | Humans and agents in repos that wired it in and enabled the hooks | Anyone who has not, which reads as a pass |
| `CODEOWNERS` plus branch protection | Everyone, on GitHub | Repos without branch protection, which includes private repos on the free plan |

**This is a guard against accident, not a boundary.** Identity is `git config user.email`, `user.name`, `github.user` and `$GITHUB_USER`; any one matching a Who entry counts. Anyone can set those to anything. The plugin's value is that the honest mistake gets caught and the rule gets stated. The one layer nobody can bypass is the third, and `/permissions:codeowners` keeps it generated from the same table.

The hook only runs where Claude Code runs plugin hooks. In Claude chat, or any client that loads the skills without the hooks, nothing is refused and the other two layers are all you have.

## The rules file

`PERMISSIONS.md` at the root of the repo it governs:

```
| Path | Who | On miss | Notes |
|---|---|---|---|
| CANONICAL.md | Dana, @dana | block | Rows are added by proposal. |
| contracts/ | dana@example.com, @dana | block | Signed paper. |
| docs/launch-plan.md | Dana, Sam | propose | |
| docs/*.txt | * | propose | Anyone. |
```

- **Path**: a file, a directory (trailing slash, or any directory that exists on disk), or a glob with `*` inside a segment and `**` across segments. Relative to the repo root; a leading `./` or `/` is ignored.
- **Who**: names, emails, or `@github-handles`, comma-separated, matched case-insensitively. `*` is anyone; `-` is nobody. Only `@handles` reach `CODEOWNERS`.
- **On miss**: `block` or `propose`. Empty means `block`.
- **Order**: first matching row wins, and `PERMISSIONS.md` rows are checked before `CANONICAL.md` rows. Put the narrow exception above the broad rule.

The first table in the file with Path, Who and On miss columns is the one read; prose around it is ignored.

**From `CANONICAL.md`.** If the repo has a `CANONICAL.md` in the format the `canonical` plugin uses (a table with Type, Where, Class and Owner columns), every row whose Class is `governed` becomes a rule for each place in its Where column that looks like a path, owned by its Owner, on miss `propose`. Where places are separated by `then`; URLs and named systems such as `crm: accounts` are skipped. `CANONICAL_FILE=path` points at a different file, as it does for `canonical`. You do not need the canonical plugin installed for this; the file is enough.

**Which repo's rules.** A path is judged by the rules of the git checkout that holds it, not the one the session started in. A session in one worktree that writes into another checkout gets that checkout's rules. A write outside any git repo is not checked.

## When it stays quiet

The hook allows the edit and prints nothing when the file is outside any git repo, when that repo has neither `PERMISSIONS.md` nor a governed `CANONICAL.md` row, when git knows no identity at all, or when the hook input is not something it understands. A fresh install in a repo that has never heard of it changes nothing. The commands say plainly when they are run outside a repo, or when there are no rules or no identity.

No identity is the case to know about. Without one there is no way to tell the owner from anyone else, so the hook stands aside rather than refusing everybody. `/permissions:who --whoami` shows what git knows. The `staged` check does not stand aside: it refuses a blocked path and tells you to set `user.email`.

## Commands

In a session:

```
/permissions:init                write PERMISSIONS.md from the template
/permissions:who <path>          what would happen to an edit, and which rule says so
/permissions:who --rules         every rule in the order it is checked
/permissions:who --whoami        the identities git and the environment give you
/permissions:who --check         validate both files; exit 1 on problems
/permissions:codeowners          preview .github/CODEOWNERS, then write it
```

The same script runs from a terminal inside the repo, where `<plugin-dir>` is wherever the plugin sits on disk:

```
python3 <plugin-dir>/scripts/permissions.py test <path> [--as IDENTITY]
python3 <plugin-dir>/scripts/permissions.py whoami | rules | check | init
python3 <plugin-dir>/scripts/permissions.py codeowners [--write]
python3 <plugin-dir>/scripts/permissions.py staged
```

`codeowners --write` checks the rules for `.github/CODEOWNERS` first and refuses if that path is blocked for you. In the generated file, rules are anchored at the root and written in reverse order, because GitHub takes the last match and this plugin takes the first. A `*` rule becomes a path with no owners, so a broader rule below it does not claim that path on GitHub.

## Pre-commit

Nothing is checked at commit until you add it. In `.githooks/pre-commit`, `.git/hooks/pre-commit`, or whatever your hook manager runs:

```
python3 <plugin-dir>/scripts/permissions.py staged || exit 1
```

It exits 1 if any staged path, including the old path of a rename, is blocked for the committer, and prints a `hold` reminder for proposals. Git hooks run outside Claude Code, so `${CLAUDE_PLUGIN_ROOT}` is not set there, and the installed plugin's path can change when it updates. The steadier option is to copy `scripts/permissions.py` into the repo for this one caller and note which version it came from.

## Limits

- Identity is self-declared. See above.
- Bash is not gated. A `cat > file` in a shell command writes past the hook; the skill asks Claude not to, and nothing enforces that.
- `propose` refuses once per session and path, then allows. It records what it has refused under the repo's git directory (`permissions-seen/`).
- The PR, the `hold` label and the reviewer are left to whoever ships the change. The plugin reminds; it does not open PRs.
- `CODEOWNERS` can only name GitHub handles. A rule for a name or email is enforced locally and skipped there, with a note on stderr.

## Tests

From the plugin directory:

```
python3 scripts/test_permissions.py
```

67 checks. Builds throwaway repos with both registries, a second checkout, a repo with no git identity and a directory outside git, then runs the hook, the staged check, the CLI and the CODEOWNERS generator against them. Global git config is ignored for the run. Python 3 standard library only.
