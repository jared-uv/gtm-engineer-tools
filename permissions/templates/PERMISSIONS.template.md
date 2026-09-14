# Who may change what

Paths only named people may change. If this repo has a `CANONICAL.md` (the canonical plugin's registry), every `governed` row in it is already a rule: its paths, its owner, on miss `propose`. This table is for paths that are not a kind of company information: the registries themselves, the agent configuration, signed paper, CI.

First matching row wins. **Path** is a file, a directory (trailing slash), or a glob (`*` within a segment, `**` across). **Who** is names, emails or @github-handles, comma-separated; `*` is anyone. **On miss** is `block` (refused) or `propose` (goes through once the rule has been stated; the PR carries the `hold` label and the owner decides).

This is a guard against accident, not a boundary. Anyone can set `git config user.email`. The one enforcement nobody can bypass is `CODEOWNERS` plus branch protection on GitHub, and `/permissions:codeowners` generates that file from the rules that name a @handle.

| Path | Who | On miss | Notes |
|---|---|---|---|
| CANONICAL.md | | block | The registry of where things live. |
| PERMISSIONS.md | | block | This file. |
| CLAUDE.md | | propose | What every session reads first. |
| .claude/ | | propose | Skills, hooks, rules. |
| .github/ | | block | CI and CODEOWNERS. |
| contracts/ | | block | Signed paper and redlines. |
