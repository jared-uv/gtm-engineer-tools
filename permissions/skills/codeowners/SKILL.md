---
name: codeowners
description: >-
  Generate .github/CODEOWNERS from PERMISSIONS.md and the governed rows of
  CANONICAL.md, so the one enforcement GitHub actually applies stays in sync
  with the inspectable rules. Use when the user says "/permissions:codeowners",
  "update codeowners", "sync codeowners", or after editing either registry.
---

# codeowners

`CODEOWNERS` is the only one of the three enforcement layers nobody can bypass, and only when branch protection requires owner review. This keeps it generated rather than hand-edited, so the rules people read and the rules GitHub applies are the same rules.

## Steps

1. Preview:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/permissions.py" codeowners
```

   Rules whose Who names no `@handle` are skipped and listed on stderr. GitHub can only match handles, so a rule for "Dana" enforces locally and not here; add `@dana` (her GitHub handle) to the Who column if it should. A rule whose Who is `*` appears as a path with no owners, so a broader rule below it does not claim that path on GitHub.

2. If the preview is right, write it:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/permissions.py" codeowners --write
```

   The script checks the rules for `.github/CODEOWNERS` itself before writing. If that path is blocked for the current git identity it refuses and exits 1; hand the owner the preview instead. If it is a proposal, it writes and reminds you the PR needs the `hold` label.

3. Tell the user two things. Whether branch protection with "require review from Code Owners" is on for the default branch, if you can see it (`gh api repos/{owner}/{repo}/branches/<default>/protection`), and that without it CODEOWNERS only suggests reviewers. And that private repos on GitHub's free plan do not get branch protection at all, so for those the owner's review of proposal PRs rests on the `hold` label and on whoever merges honouring it.
