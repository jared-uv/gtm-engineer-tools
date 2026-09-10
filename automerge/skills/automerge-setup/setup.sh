#!/usr/bin/env bash
# Set up PR auto-merge on the GitHub repo of the current directory.
#
# Three things, all idempotent:
#   1. turn on delete_branch_on_merge, so merged branches clean up
#   2. create the `hold` label the workflow honors
#   3. put automerge.yml (bundled next to this script) on a branch and open a
#      PR for it — GitHub only runs scheduled workflows from the default
#      branch, so that PR has to be merged by hand once
#
# The working tree is never touched: the file is committed in a throwaway git
# worktree that is removed afterwards, so this is safe to run mid-session with
# other work uncommitted.
#
# Usage, from anywhere inside a clone of the target repo:
#     bash <path-to-this-folder>/setup.sh [--dry-run]
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
template="$here/automerge.yml"
path=".github/workflows/automerge.yml"
label="hold"
dry=0
[ "${1:-}" = "--dry-run" ] && dry=1

say() { printf '%s\n' "$*"; }
die() { printf 'automerge-setup: %s\n' "$*" >&2; exit 1; }
run() { if [ "$dry" = 1 ]; then say "  would: $*"; else "$@"; fi; }

# ── Preflight ─────────────────────────────────────────────────────────────
command -v gh >/dev/null 2>&1 || die "gh is not installed (https://cli.github.com)"
gh auth status >/dev/null 2>&1 || die "gh is not logged in; run: gh auth login"
[ -f "$template" ] || die "template missing: $template"
git rev-parse --show-toplevel >/dev/null 2>&1 || die "not inside a git repository"

repo="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)" \
  || die "no GitHub repo found for this checkout (is there an origin remote?)"
default="$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)"
say "repo: $repo   default branch: $default"
[ "$dry" = 1 ] && say "(dry run: nothing will change)"

# ── 1. Repo setting ────────────────────────────────────────────────────────
if [ "$(gh api "repos/$repo" -q .delete_branch_on_merge)" = "true" ]; then
  say "✓ delete_branch_on_merge already on"
else
  run gh api -X PATCH "repos/$repo" -F delete_branch_on_merge=true --silent
  say "✓ delete_branch_on_merge turned on"
fi

# ── 2. Label ───────────────────────────────────────────────────────────────
if gh label list --repo "$repo" --json name -q '.[].name' | grep -qx "$label"; then
  say "✓ '$label' label already exists"
else
  run gh label create "$label" --repo "$repo" --color D93F0B \
    --description "Keep this PR open; the auto-merge workflow skips it"
  say "✓ '$label' label created"
fi

# ── 3. Workflow file ───────────────────────────────────────────────────────
git fetch origin "$default" --quiet
if git cat-file -e "origin/$default:$path" 2>/dev/null; then
  if git show "origin/$default:$path" | diff -q - "$template" >/dev/null; then
    say "✓ workflow already on $default and matches the template; nothing to do"
  else
    say "! $path is already on $default but differs from this skill's template."
    say "  Leaving it alone. Diff them and decide which is right:"
    say "    git diff origin/$default -- $path   (after copying the template in)"
  fi
  exit 0
fi

existing="$(gh pr list --repo "$repo" --state open --json url,headRefName \
  -q '.[] | select(.headRefName | startswith("automerge-setup")) | .url' | head -1)"
if [ -n "$existing" ]; then
  say "✓ a setup PR is already open, merge it by hand once: $existing"
  exit 0
fi

branch="automerge-setup-$(date -u +%Y%m%d%H%M%S)"
if [ "$dry" = 1 ]; then
  say "  would: commit $path to branch $branch from origin/$default, push, open a PR"
  exit 0
fi

tmp="$(mktemp -d)"
cleanup() {
  git worktree remove --force "$tmp" 2>/dev/null || true
  git branch -D "$branch" >/dev/null 2>&1 || true   # local only; the remote branch stays
}
trap cleanup EXIT

git worktree add --quiet -b "$branch" "$tmp" "origin/$default"
mkdir -p "$tmp/$(dirname "$path")"
cp "$template" "$tmp/$path"
git -C "$tmp" add "$path"
git -C "$tmp" commit --quiet -m "Auto-merge clean PRs on a timer

Every 30 minutes, squash-merge any open PR that is at least 15 minutes old
and has no conflict, no pending or failing check, no hold label, and is
not a draft. Conflicted PRs are skipped and named in the run log.
GitHub's own auto-merge needs branch protection; this doesn't."

if ! git -C "$tmp" push --quiet -u origin "$branch"; then
  die "push rejected. If the error mentions the 'workflow' scope, run:
    gh auth refresh -h github.com -s workflow
  then run this script again."
fi

url="$(gh pr create --repo "$repo" --head "$branch" --base "$default" \
  --title "Auto-merge clean PRs on a timer" \
  --body "Adds \`$path\`: every 30 minutes, squash-merge any open PR that is at least 15 minutes old with no conflict, no pending or failing check, no \`$label\` label, and not a draft. Conflicted PRs are skipped and named in the run log.

GitHub's built-in auto-merge needs branch protection, which private repos on the free plan don't get. A scheduled workflow does the same job without it.

Repo settings changed alongside: \`delete_branch_on_merge\` is on, and a \`$label\` label exists for PRs that should stay open.

**Merge this one by hand.** Scheduled workflows only run from \`$default\`, so it can't bootstrap itself. After that it takes over.")"

say "✓ workflow pushed on $branch"
say ""
say "One manual step left: merge this PR, then the workflow takes over."
say "  $url"
