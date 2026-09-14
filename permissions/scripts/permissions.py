#!/usr/bin/env python3
"""permissions — paths only named people may change.

Rules come from two files at the root of the repo that holds the path, and
PERMISSIONS.md is checked first:

  PERMISSIONS.md   a table  | Path | Who | On miss | Notes |   first matching row wins
  CANONICAL.md     every `governed` row: its local Where paths, owned by its Owner,
                   on miss `propose` (override the location with CANONICAL_FILE=path,
                   as the canonical plugin does)

Path    a repo-relative file, a directory (trailing slash, or a directory on disk,
        covers everything under it), or a glob: `*` within one segment, `**` across.
Who     comma-separated names, emails or @github-handles. `*` means anyone.
        Matched case-insensitively against the identity below. `-` is nobody.
On miss block    the edit is refused, in Claude sessions and at commit.
        propose  the edit goes through after one refusal that states the rule; the
                 change has to reach the owner as a PR carrying the `hold` label.

Identity: `git config user.email`, `user.name`, `github.user`, and $GITHUB_USER.
Any of them matching a Who entry is a match. This is a guard against accident,
not a boundary: anyone can set user.email to anything.

CLI (run from inside a git checkout):
  permissions.py test <path> [--as IDENTITY]   what would happen to an edit
  permissions.py whoami                         the identities in play
  permissions.py rules                          every rule, in the order checked
  permissions.py check                          validate both files; exit 1 on problems
  permissions.py codeowners [--write]           .github/CODEOWNERS from the rules
  permissions.py staged                         pre-commit: exit 1 on a block miss
  permissions.py init                           write the template if no PERMISSIONS.md

--rules, --whoami and --check work as flags too, so `test --rules` is `rules`.

With no subcommand it reads a PreToolUse payload on stdin and acts as the hook.
The hook says nothing and allows the edit when the path is outside any git repo,
when that repo has no rules, when git knows no identity, or when the input is
not a payload it understands.
"""

import json
import os
import re
import subprocess
import sys

MISS = {"block", "propose"}
FILE_KEYS = ("file_path", "notebook_path", "path")
# Same split as canonical.py, applied to the raw cell the same way.
SPLIT_WHERE = re.compile(r"\s+then\s+|\s*;\s*")
TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "templates", "PERMISSIONS.template.md")


def sh(args, cwd=None):
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def git_root(directory):
    """Top of the git checkout containing `directory`, resolved, or None."""
    top = sh(["git", "rev-parse", "--show-toplevel"], directory)
    return os.path.realpath(top) if top else None


def root_for(abs_path):
    """The checkout holding abs_path, which need not exist yet."""
    d = abs_path
    while d and not os.path.isdir(d):
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent
    return git_root(d) if d else None


def common_dir(root):
    d = sh(["git", "rev-parse", "--git-common-dir"], root) or ".git"
    return d if os.path.isabs(d) else os.path.join(root, d)


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


# ---------- registry parsing ----------

def strip_md(s):
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s.strip())
    return s.strip("`").strip()


def parse_table(text, need):
    """First markdown table whose header contains every column in `need`.

    Each row maps lowercase header -> stripped cell, and `_raw` holds the unstripped
    cells so Where can be split before stripping, exactly as canonical.py does."""
    lines = text.splitlines()
    for i, line in enumerate(lines[:-1]):
        if not line.lstrip().startswith("|") or not re.match(r"^\s*\|?\s*:?-+", lines[i + 1]):
            continue
        header = [strip_md(h).lower() for h in line.strip().strip("|").split("|")]
        if not all(c in header for c in need):
            continue
        rows = []
        j = i + 2
        while j < len(lines) and lines[j].lstrip().startswith("|"):
            cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
            cells += [""] * (len(header) - len(cells))
            row = {h: strip_md(cells[k]) for k, h in enumerate(header)}
            row["_raw"] = {h: cells[k] for k, h in enumerate(header)}
            row["_line"] = j + 1
            rows.append(row)
            j += 1
        return rows
    return None


def split_list(s):
    return [p for p in (x.strip() for x in s.split(",")) if p and p != "-"]


def split_where(raw):
    return [strip_md(p) for p in SPLIT_WHERE.split(raw.strip()) if strip_md(p)]


def looks_like_path(place):
    if "://" in place or re.match(r"^[a-z][a-z0-9+-]*:\s", place):
        return False
    return ("/" in place or "." in place) and " " not in place


def canonical_path(root):
    return os.path.join(root, os.environ.get("CANONICAL_FILE") or "CANONICAL.md")


def load_rules(root):
    """Return (rules, problems). Each rule: path, who(list), miss, source, line, notes."""
    rules, problems = [], []
    p = os.path.join(root, "PERMISSIONS.md")
    if os.path.isfile(p):
        rows = parse_table(read_text(p), ("path", "who", "on miss"))
        if rows is None:
            problems.append("PERMISSIONS.md has no table with Path, Who and On miss columns")
        else:
            for r in rows:
                rules.append({
                    "path": r["path"], "who": split_list(r["who"]),
                    "miss": r["on miss"].lower() or "block", "source": "PERMISSIONS.md",
                    "line": r["_line"], "notes": r.get("notes", ""),
                })
    c = canonical_path(root)
    if os.path.isfile(c):
        name = os.path.basename(c)
        rows = parse_table(read_text(c), ("type", "where"))
        if rows is None:
            problems.append(f"{name} has no table with Type and Where columns")
        else:
            for r in rows:
                if r.get("class", "").lower() != "governed":
                    continue
                for place in split_where(r["_raw"].get("where", "")):
                    if looks_like_path(place):
                        rules.append({
                            "path": place, "who": split_list(r.get("owner", "")),
                            "miss": "propose", "source": name,
                            "line": r["_line"], "notes": r.get("type", ""),
                        })
    return rules, problems


# ---------- matching ----------

def glob_to_re(pattern):
    out, i = "", 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"; i += 3
        elif pattern.startswith("**", i):
            out += ".*"; i += 2
        elif ch == "*":
            out += "[^/]*"; i += 1
        elif ch == "?":
            out += "[^/]"; i += 1
        else:
            out += re.escape(ch); i += 1
    return re.compile("^" + out + "$")


def clean_pattern(pat):
    pat = pat.strip()
    if pat.startswith("./"):
        pat = pat[2:]
    return pat.lstrip("/")


def rule_matches(rule, rel, root):
    pat = clean_pattern(rule["path"])
    if not pat:
        return False
    if pat.endswith("/"):
        return rel.startswith(pat)
    if any(c in pat for c in "*?["):
        return bool(glob_to_re(pat).match(rel))
    if rel == pat:
        return True
    if os.path.isdir(os.path.join(root, pat)):
        return rel.startswith(pat.rstrip("/") + "/")
    return False


def identities(root, override=None):
    if override:
        return [override.lower()]
    ids = []
    for key in ("user.email", "user.name", "github.user"):
        v = sh(["git", "config", key], root)
        if v:
            ids.append(v.lower())
    if os.environ.get("GITHUB_USER"):
        ids.append(os.environ["GITHUB_USER"].lower())
    return ids


def allowed(rule, ids):
    for w in rule["who"]:
        w = w.lower()
        if w == "*":
            return True
        if w in ids or w.lstrip("@") in ids or ("@" + w) in ids:
            return True
    return False


def decide(rel, root, rules, ids):
    """Return (decision, rule). decision in {allow, block, propose, unruled}."""
    for rule in rules:
        if rule_matches(rule, rel, root):
            if allowed(rule, ids):
                return "allow", rule
            return rule["miss"], rule
    return "unruled", None


def owners_text(rule):
    return ", ".join(rule["who"]) if rule["who"] else "nobody named"


# ---------- hook ----------

def seen_path(root, session):
    d = os.path.join(common_dir(root), "permissions-seen")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, re.sub(r"[^A-Za-z0-9_-]", "_", session or "nosession"))


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))


def hook(payload):
    if not isinstance(payload, dict) or payload.get("hook_event_name") != "PreToolUse":
        return 0
    ti = payload.get("tool_input")
    if not isinstance(ti, dict):
        return 0
    target = next((ti[k] for k in FILE_KEYS if isinstance(ti.get(k), str) and ti.get(k)), None)
    if not target:
        return 0
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else os.getcwd()
    # realpath: git reports the resolved path, and on macOS /tmp and /var are symlinks.
    abs_target = os.path.realpath(os.path.join(cwd, os.path.expanduser(target)))
    # Judge the path against the checkout that holds it, not the session's cwd: a
    # session in one worktree can write into another checkout, or outside any repo.
    root = root_for(abs_target)
    if not root:
        return 0
    rel = os.path.relpath(abs_target, root)
    if rel.startswith(".."):
        return 0
    rules, _ = load_rules(root)
    if not rules:
        return 0
    ids = identities(root)
    if not ids:
        return 0
    decision, rule = decide(rel, root, rules, ids)
    if decision not in MISS:
        return 0
    who = owners_text(rule)
    src = f"{rule['source']} line {rule['line']}"
    if rule["source"] != "PERMISSIONS.md" and rule["notes"]:
        src += f", {rule['notes']}"
    if decision == "block":
        deny(f"permissions: `{rel}` may only be changed by {who} ({src}). "
             f"You are {', '.join(ids)}. Do not edit it; tell the user who owns it.")
        return 0
    # propose: refuse once per session and path, then let it through
    try:
        sp = seen_path(root, payload.get("session_id") if isinstance(payload.get("session_id"), str) else None)
        seen = set(read_text(sp).split("\n")) if os.path.exists(sp) else set()
        if rel in seen:
            return 0
        with open(sp, "a", encoding="utf-8") as f:
            f.write(rel + "\n")
    except OSError:
        return 0  # without a record the retry would be refused forever; let it through
    deny(f"permissions: `{rel}` is governed by {who} ({src}) and you are "
         f"{', '.join(ids)}. You may edit it as a proposal: retry the same edit and it will "
         f"go through. The change then has to reach {who} as a PR carrying the `hold` label, "
         f"with them as reviewer, so it waits for their decision. Tell the user this before retrying.")
    return 0


# ---------- CLI ----------

def cmd_test(root, args):
    ident = None
    if "--as" in args:
        k = args.index("--as")
        if k + 1 >= len(args):
            print("usage: permissions.py test <path> [--as IDENTITY]"); return 2
        ident = args[k + 1]; args = args[:k] + args[k + 2:]
    if not args:
        print("usage: permissions.py test <path> [--as IDENTITY]"); return 2
    abs_target = os.path.realpath(os.path.expanduser(args[0]))
    target_root = root_for(abs_target)
    if not target_root:
        print(f"{args[0]}: outside any git repository; no rules apply")
        return 0
    if target_root != root:
        print(f"(judged against the checkout that holds it: {target_root})")
        root = target_root
    rules, _ = load_rules(root)
    ids = identities(root, ident)
    rel = os.path.relpath(abs_target, root)
    decision, rule = decide(rel, root, rules, ids)
    if rule:
        print(f"{rel}: {decision} — rule `{rule['path']}` for {owners_text(rule)}, "
              f"on miss {rule['miss']} ({rule['source']} line {rule['line']})")
    else:
        print(f"{rel}: no rule; anyone may edit")
    print(f"as: {', '.join(ids) or '(no identity; the Claude hook stays silent until git has one)'}")
    return 0


def cmd_whoami(root):
    ids = identities(root)
    print("\n".join(ids) if ids else
          "no identity: set git config user.email or user.name, or GITHUB_USER. "
          "Until then the Claude hook allows every edit.")
    return 0


def cmd_rules(root):
    rules, problems = load_rules(root)
    for p in problems:
        print("problem:", p)
    if not rules and not problems:
        print("no rules: neither PERMISSIONS.md nor a governed row in CANONICAL.md")
    for r in rules:
        print(f"{r['path']:45} {owners_text(r):25} {r['miss']:8} {r['source']}:{r['line']}"
              + (f"  {r['notes']}" if r["notes"] else ""))
    return 0


def cmd_check(root):
    rules, problems = load_rules(root)
    for r in rules:
        where = f"{r['source']} line {r['line']} `{r['path']}`"
        if not r["who"]:
            problems.append(f"{where}: Who is empty")
        if r["miss"] not in MISS:
            problems.append(f"{where}: On miss `{r['miss']}` must be block or propose")
        pat = clean_pattern(r["path"]).rstrip("/")
        if pat and not any(c in pat for c in "*?[") and not os.path.exists(os.path.join(root, pat)):
            problems.append(f"{where}: does not exist")
    if not rules and not problems:
        print("no rules: neither PERMISSIONS.md nor a governed row in CANONICAL.md")
        return 0
    if problems:
        print(f"{len(problems)} problem(s)")
        for p in problems:
            print("  " + p)
        return 1
    print(f"{len(rules)} rules, no problems")
    return 0


def codeowners_pattern(path):
    # Anchor at the root: our rules are repo-relative, and an unanchored `*.md`
    # in CODEOWNERS would match at any depth.
    pat = "/" + clean_pattern(path)
    return pat.replace(" ", "\\ ")


def codeowners_text(rules):
    lines = ["# Generated by permissions.py from PERMISSIONS.md and CANONICAL.md. Edit those, not this.",
             "# Rules that name no @github-handle are enforced locally only and do not appear.", ""]
    skipped, emitted = [], 0
    # CODEOWNERS is last match wins and our rules are first match wins: emit in reverse.
    for r in reversed(rules):
        if "*" in r["who"]:
            # Anyone may edit. A pattern with no owners stops a broader rule below it
            # from claiming this path on GitHub, as first-match-wins does locally.
            lines.append(codeowners_pattern(r["path"])); emitted += 1; continue
        handles = [w for w in r["who"] if w.startswith("@")]
        if not handles:
            skipped.append(r); continue
        lines.append(f"{codeowners_pattern(r['path'])} {' '.join(handles)}"); emitted += 1
    return "\n".join(lines) + "\n", emitted, skipped


def cmd_codeowners(root, write):
    rules, _ = load_rules(root)
    text, emitted, skipped = codeowners_text(rules)
    if write:
        ids = identities(root)
        decision, rule = decide(".github/CODEOWNERS", root, rules, ids)
        if decision == "block":
            print(f"permissions: `.github/CODEOWNERS` may only be changed by {owners_text(rule)} "
                  f"({rule['source']} line {rule['line']}). You are {', '.join(ids) or 'nobody git knows'}. "
                  "Not written; hand them the preview instead.", file=sys.stderr)
            return 1
        os.makedirs(os.path.join(root, ".github"), exist_ok=True)
        with open(os.path.join(root, ".github", "CODEOWNERS"), "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote .github/CODEOWNERS ({emitted} rules)")
        if decision == "propose":
            print(f"permissions: `.github/CODEOWNERS` is governed by {owners_text(rule)}; "
                  "open the PR with the `hold` label.")
    else:
        print(text, end="")
    if skipped:
        print(f"# skipped {len(skipped)} rule(s) with no @handle: "
              + ", ".join(f"`{r['path']}`" for r in skipped), file=sys.stderr)
    return 0


def cmd_staged(root):
    # --no-renames: a rename would otherwise list only the new path, and moving a
    # blocked file out of its directory would pass.
    files = (sh(["git", "diff", "--cached", "--name-only", "--no-renames"], root) or "").split("\n")
    files = [f for f in files if f]
    rules, _ = load_rules(root)
    if not files or not rules:
        return 0
    ids = identities(root)
    blocked, proposals = [], []
    for rel in files:
        decision, rule = decide(rel, root, rules, ids)
        if decision == "block":
            blocked.append((rel, rule))
        elif decision == "propose":
            proposals.append((rel, rule))
    for rel, rule in proposals:
        print(f"permissions: `{rel}` is governed by {owners_text(rule)}; open the PR with the `hold` label.")
    for rel, rule in blocked:
        print(f"permissions: `{rel}` may only be changed by {owners_text(rule)} "
              f"({rule['source']} line {rule['line']}). You are "
              f"{', '.join(ids) or 'nobody git knows (set git config user.email)'}.", file=sys.stderr)
    if blocked:
        print("permissions: commit refused.", file=sys.stderr)
        return 1
    return 0


def cmd_init(root):
    p = os.path.join(root, "PERMISSIONS.md")
    if os.path.exists(p):
        print("PERMISSIONS.md already exists; not touching it."); return 0
    try:
        lines = read_text(TEMPLATE).splitlines()
    except OSError:
        print(f"permissions: template not found at {TEMPLATE}; is the plugin intact?", file=sys.stderr)
        return 1
    # Keep only the example rows whose path exists here, so `check` starts clean
    # apart from the Who column you still have to fill in.
    kept, dropped, out = [], [], []
    for line in lines:
        m = re.match(r"^\|\s*([^|]+?)\s*\|", line)
        path = m.group(1).strip("`") if m else None
        if path and path.lower() != "path" and not path.startswith("-") and path != "PERMISSIONS.md":
            if os.path.exists(os.path.join(root, path.rstrip("/"))):
                kept.append(path)
            else:
                dropped.append(path); continue
        out.append(line)
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("wrote PERMISSIONS.md from the template.")
    if dropped:
        print("left out rows for paths this repo does not have: " + ", ".join(dropped))
    print("Fill in the Who column, add your own rows, then run `check`.")
    return 0


FLAG_VERBS = {"--rules": "rules", "--whoami": "whoami", "--check": "check"}


def main(argv):
    if not argv:
        try:
            return hook(json.loads(sys.stdin.read()))
        except Exception:
            return 0  # a hook must never break the session it guards
    # The who skill runs `test $ARGUMENTS`, so `/permissions:who --rules` arrives as
    # `test --rules`. Treat the flag as the command rather than as a path.
    flagged = [FLAG_VERBS[a] for a in argv if a in FLAG_VERBS]
    if flagged:
        argv = flagged[:1]
    cmd, args = argv[0], argv[1:]
    commands = {"test", "whoami", "rules", "check", "codeowners", "staged", "init"}
    if cmd not in commands:
        print(__doc__)
        return 2
    root = git_root(os.getcwd())
    if not root:
        print("permissions: not inside a git repository. Run this from a checkout; "
              "rules live at the root of the repo they govern.", file=sys.stderr)
        return 2
    if cmd == "test":
        return cmd_test(root, args)
    if cmd == "whoami":
        return cmd_whoami(root)
    if cmd == "rules":
        return cmd_rules(root)
    if cmd == "check":
        return cmd_check(root)
    if cmd == "codeowners":
        return cmd_codeowners(root, "--write" in args)
    if cmd == "staged":
        return cmd_staged(root)
    return cmd_init(root)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
