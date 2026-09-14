#!/usr/bin/env python3
"""always-worktree — keep edits off the default branch.

Runs as a Claude Code hook. Reads the hook payload on stdin, works out
whether the session is about to edit on the default branch, and if so
blocks the tool call (PreToolUse) or adds a warning line (UserPromptSubmit).

Write, Edit, MultiEdit and NotebookEdit are judged by the repo that holds the
file being written, so a session in the main checkout can still write to a
scratch directory or a linked worktree. Bash is judged by the session's
working directory, because the command string has no reliable target.

Also the CLI behind `/always-worktree:main-ok`:

    guard.py --allow [MINUTES]   write a time-limited override for this repo
    guard.py --revoke            remove it
    guard.py --status            print what the hook would decide right now

Config, all optional, in `.claude/always-worktree.json` at the repo root:

    {
      "mode": "branch",          "branch" = block on the default branch, wherever it
                                 is checked out (default). "strict" = also block in
                                 the main checkout on any branch, so every edit
                                 happens in a linked worktree.
      "gate_bash": true,         also block Bash commands that look like writes.
      "default_branch": "main",  skip detection and use this.
      "allow_minutes": 240       how long the main-ok override lasts.
    }

Environment: ALWAYS_WORKTREE_OFF=1 disables the hook for that shell.

Stdlib only. Any failure inside the hook exits 0 with no output, so a broken
config or an odd payload never gets in the way of the session.
"""

import json
import os
import re
import subprocess
import sys
import time

EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
DEFAULT_MINUTES = 240

# Bash that is probably a write. Deliberately loose: the point is to catch a
# heredoc into a tracked file or a `git commit` on main, not to be airtight.
BASH_WRITE = re.compile(
    r"(?<![<|])>{1,2}\s*[^&\s]"          # redirect to a file, not `2>&1` or `>&`
    r"|\btee\b"
    r"|\bsed\s+-i\b"
    r"|\b(?:cp|mv|rm|mkdir|touch|ln)\s"
    r"|\bgit\s+(?:add|commit|mv|rm|merge|rebase|cherry-pick|apply)\b"
    r"|<<-?\s*['\"]?\w+['\"]?"          # heredoc
    r"|\b(?:python3?|node|ruby|perl)\b.*\b(?:open\(|write|Path\()"
)

# Redirects that write nothing. Stripped before the check so `ls > /dev/null`
# and `cmd 2>/dev/null` pass.
DEV_NULL = re.compile(r"\d?>{1,2}\s*/dev/null")


def sh(args, cwd):
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def load_config(top):
    path = os.path.join(top, ".claude", "always-worktree.json")
    try:
        with open(path) as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    mode = cfg.get("mode")
    gate = cfg.get("gate_bash")
    branch = cfg.get("default_branch")
    try:
        minutes = int(cfg.get("allow_minutes", DEFAULT_MINUTES))
    except (TypeError, ValueError):
        minutes = DEFAULT_MINUTES
    return {
        "mode": mode if mode in ("branch", "strict") else "branch",
        "gate_bash": gate if isinstance(gate, bool) else True,
        "default_branch": branch if isinstance(branch, str) and branch else None,
        "allow_minutes": minutes if minutes > 0 else DEFAULT_MINUTES,
    }


def local_branch_exists(top, name):
    return sh(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"], top) is not None


def default_branch(top, cfg):
    """The configured branch, else what a remote says, else a local guess, else None."""
    if cfg["default_branch"]:
        return cfg["default_branch"]
    # origin/HEAD first, then any other remote's HEAD (a repo whose only remote
    # is called `upstream`, say).
    refs = sh(["git", "for-each-ref", "--format=%(refname:short) %(symref:short)",
               "refs/remotes/*/HEAD"], top) or ""
    heads = {}
    for line in refs.splitlines():
        parts = line.split()
        if len(parts) == 2 and "/" in parts[1]:
            heads[parts[0].split("/", 1)[0]] = parts[1].split("/", 1)[1]
    if "origin" in heads:
        return heads["origin"]
    if heads:
        return heads[sorted(heads)[0]]
    # No remote HEAD: the name this machine gives new repos, then main, master.
    init = sh(["git", "config", "--get", "init.defaultBranch"], top)
    for name in [init, "main", "master"]:
        if name and local_branch_exists(top, name):
            return name
    return None


def is_main_checkout(top):
    git_dir = sh(["git", "rev-parse", "--git-dir"], top)
    common = sh(["git", "rev-parse", "--git-common-dir"], top)
    if git_dir is None or common is None:
        return True
    return os.path.realpath(os.path.join(top, git_dir)) == os.path.realpath(os.path.join(top, common))


def allow_path(top):
    # The common git dir is shared by every worktree of a repo, and by nothing else.
    common = sh(["git", "rev-parse", "--git-common-dir"], top) or ".git"
    return os.path.join(top, common, "always-worktree-allow")


def allow_active(top):
    try:
        with open(allow_path(top)) as f:
            until = float(f.read().strip() or 0)
    except (OSError, ValueError):
        return None
    left = until - time.time()
    return left if left > 0 else None


def existing_dir(path):
    """The nearest directory at or above `path` that exists."""
    d = path if os.path.isdir(path) else os.path.dirname(path)
    while d and not os.path.isdir(d):
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return d or os.sep


def situation(cwd):
    """Return (blocked_reason or None, details dict, config)."""
    if os.environ.get("ALWAYS_WORKTREE_OFF"):
        return None, {"why": "ALWAYS_WORKTREE_OFF set"}, None
    top = sh(["git", "rev-parse", "--show-toplevel"], cwd)
    if not top:
        return None, {"why": "not a git repo"}, None
    cfg = load_config(top)
    branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], top) or "HEAD"
    default = default_branch(top, cfg)
    main_checkout = is_main_checkout(top)
    left = allow_active(top)
    d = {
        "top": top,
        "branch": branch,
        "default": default or "unknown (set default_branch in .claude/always-worktree.json)",
        "main_checkout": main_checkout,
        "mode": cfg["mode"],
        "gate_bash": cfg["gate_bash"],
        "allow_left_min": round(left / 60) if left else 0,
    }
    if left:
        return None, d, cfg
    if default and branch == default:
        return f"on `{default}`", d, cfg
    if cfg["mode"] == "strict" and main_checkout:
        return f"in the main checkout (branch `{branch}`)", d, cfg
    return None, d, cfg


def block_message(reason, mins):
    return (
        f"always-worktree: this session is {reason}. Move to a worktree before editing "
        f"(EnterWorktree, or `git worktree add ../<name> -b <branch>`), or ask the user "
        f"whether to run /always-worktree:main-ok to allow edits here for {mins} minutes."
    )


def edit_target(payload, cwd):
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(path, str) or not path:
        return cwd
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return existing_dir(path)


def handle_pre_tool_use(payload):
    tool = payload.get("tool_name", "")
    cwd = payload.get("cwd") or os.getcwd()
    if tool in EDIT_TOOLS:
        reason, _, cfg = situation(edit_target(payload, cwd))
        if reason:
            deny(block_message(reason, cfg["allow_minutes"]))
        return 0
    if tool == "Bash":
        reason, _, cfg = situation(cwd)
        if not reason or not cfg["gate_bash"]:
            return 0
        cmd = (payload.get("tool_input") or {}).get("command", "")
        if isinstance(cmd, str) and BASH_WRITE.search(DEV_NULL.sub("", cmd)):
            deny(block_message(reason, cfg["allow_minutes"]) + " (Bash command looks like a write.)")
    return 0


def deny(text):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": text,
        }
    }))


def handle_user_prompt(payload):
    cwd = payload.get("cwd") or os.getcwd()
    reason, _, cfg = situation(cwd)
    if not reason:
        return 0
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                f"always-worktree: this session is {reason}. Edits to this checkout will be "
                f"blocked. Before changing files, move to a worktree (EnterWorktree), or ask "
                f"the user whether to run /always-worktree:main-ok "
                f"({cfg['allow_minutes']}-minute override)."
            ),
        }
    }))
    return 0


def cli_allow(minutes):
    top = sh(["git", "rev-parse", "--show-toplevel"], os.getcwd())
    if not top:
        print("always-worktree: not inside a git repo", file=sys.stderr)
        return 1
    minutes = minutes or load_config(top)["allow_minutes"]
    until = time.time() + minutes * 60
    with open(allow_path(top), "w") as f:
        f.write(f"{until:.0f}\n")
    print(f"always-worktree: edits allowed on any branch in {top} and its worktrees for {minutes} minutes.")
    return 0


def cli_revoke():
    top = sh(["git", "rev-parse", "--show-toplevel"], os.getcwd())
    if not top:
        print("always-worktree: not inside a git repo", file=sys.stderr)
        return 1
    try:
        os.remove(allow_path(top))
        print("always-worktree: override removed.")
    except FileNotFoundError:
        print("always-worktree: no override was set.")
    return 0


def cli_status():
    reason, d, _ = situation(os.getcwd())
    for k, v in d.items():
        print(f"{k}: {v}")
    print("decision:", f"BLOCK edits ({reason})" if reason else "allow")
    return 0


def main(argv):
    if argv and argv[0] == "--allow":
        minutes = None
        if len(argv) > 1:
            try:
                minutes = int(argv[1])
            except ValueError:
                print("always-worktree: --allow takes a whole number of minutes", file=sys.stderr)
                return 2
            if minutes <= 0:
                print("always-worktree: --allow takes a positive number of minutes", file=sys.stderr)
                return 2
        return cli_allow(minutes)
    if argv and argv[0] == "--revoke":
        return cli_revoke()
    if argv and argv[0] == "--status":
        return cli_status()
    # Hook path: never fail loudly.
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        event = payload.get("hook_event_name", "")
        if event == "PreToolUse":
            return handle_pre_tool_use(payload)
        if event == "UserPromptSubmit":
            return handle_user_prompt(payload)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
