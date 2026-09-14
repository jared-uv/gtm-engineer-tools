#!/usr/bin/env python3
"""Exercise always-worktree/hooks/guard.py against throwaway repos.

    python3 hooks/test_guard.py [path/to/guard.py]

The guard path defaults to guard.py beside this file. Git runs with the
user's global and system config ignored, so a machine's own
init.defaultBranch or hooks can't change the result.
"""
import json, os, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(HERE, "guard.py")

ENV = dict(os.environ)
ENV.pop("ALWAYS_WORKTREE_OFF", None)
for k in [k for k in ENV if k.startswith("GIT_")]:
    ENV.pop(k)
ENV.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})

root = os.path.realpath(tempfile.mkdtemp(prefix="aw-test-"))


def g(*a, cwd):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True, env=ENV).stdout.strip()


def make_repo(name, branch="main"):
    path = os.path.join(root, name)
    os.makedirs(path)
    g("init", "-q", "-b", branch, cwd=path)
    g("config", "user.email", "dana@example.com", cwd=path)
    g("config", "user.name", "Dana", cwd=path)
    open(os.path.join(path, "a.md"), "w").write("x\n")
    g("add", "a.md", cwd=path)
    g("commit", "-q", "-m", "init", cwd=path)
    return path


def run(event, cwd, tool=None, cmd=None, file_path="a.md", env=None, raw=None):
    payload = {"hook_event_name": event, "cwd": cwd, "session_id": "s1"}
    if tool:
        payload["tool_name"] = tool
        payload["tool_input"] = {"command": cmd} if cmd else {"file_path": file_path}
    e = dict(ENV)
    if env:
        e.update(env)
    stdin = raw if raw is not None else json.dumps(payload)
    p = subprocess.run([sys.executable, GUARD], input=stdin, capture_output=True, text=True, env=e, cwd=cwd)
    out = p.stdout.strip()
    try:
        j = json.loads(out) if out else {}
    except ValueError:
        j = {"raw": out}
    h = j.get("hookSpecificOutput", {})
    return p.returncode, h.get("permissionDecision") or ("context" if h.get("additionalContext") else None), p


def cli(*args, cwd):
    return subprocess.run([sys.executable, GUARD, *args], cwd=cwd, capture_output=True, text=True, env=ENV)


results = []


def check(name, got, want):
    ok = got == want
    results.append(ok)
    print(("PASS" if ok else "FAIL"), name, "->", got, ("" if ok else f"(wanted {want})"))


try:
    repo = make_repo("repo")
    g("branch", "feature", cwd=repo)
    wt = os.path.join(root, "wt")
    g("worktree", "add", "-q", wt, "feature", cwd=repo)
    scratch = os.path.join(root, "scratch")
    os.makedirs(scratch)

    # Tools on the default branch and off it
    check("Write on main", run("PreToolUse", repo, "Write")[1], "deny")
    check("Edit in worktree", run("PreToolUse", wt, "Edit")[1], None)
    check("Prompt on main adds context", run("UserPromptSubmit", repo)[1], "context")
    check("Prompt in worktree silent", run("UserPromptSubmit", wt)[1], None)

    # Edit tools are judged by the file's repo, not the session's cwd
    check("Write from main checkout into the worktree", run("PreToolUse", repo, "Write", file_path=os.path.join(wt, "a.md"))[1], None)
    check("Write from worktree into the main checkout", run("PreToolUse", wt, "Edit", file_path=os.path.join(repo, "a.md"))[1], "deny")
    check("Write from main checkout to a dir outside any repo", run("PreToolUse", repo, "Write", file_path=os.path.join(scratch, "new", "notes.md"))[1], None)
    check("Write to a not-yet-created dir on main", run("PreToolUse", repo, "Write", file_path="docs/new/positioning.md")[1], "deny")

    # Bash: reads pass, write-looking commands don't
    check("Bash git status on main", run("PreToolUse", repo, "Bash", "git status --short")[1], None)
    check("Bash ls|head on main", run("PreToolUse", repo, "Bash", "ls -la | head")[1], None)
    check("Bash grep 2>&1 on main", run("PreToolUse", repo, "Bash", "grep -rn foo . 2>&1 | head")[1], None)
    check("Bash 2>/dev/null on main", run("PreToolUse", repo, "Bash", "git log -1 2>/dev/null")[1], None)
    check("Bash heredoc on main", run("PreToolUse", repo, "Bash", "cat > a.md <<'EOF'\nhi\nEOF")[1], "deny")
    check("Bash git commit on main", run("PreToolUse", repo, "Bash", "git commit -m x")[1], "deny")
    check("Bash sed -i on main", run("PreToolUse", repo, "Bash", "sed -i '' 's/a/b/' a.md")[1], "deny")
    check("Bash >> on main", run("PreToolUse", repo, "Bash", "echo hi >> a.md")[1], "deny")
    check("Bash python open() on main", run("PreToolUse", repo, "Bash", "python3 -c \"open('a.md','w').write('x')\"")[1], "deny")
    check("Bash git commit in worktree", run("PreToolUse", wt, "Bash", "git commit -m x")[1], None)

    # Override: allow, revoke, expiry, and where the file lives
    cli("--allow", "5", cwd=repo)
    check("Write on main with override", run("PreToolUse", repo, "Write")[1], None)
    cli("--revoke", cwd=repo)
    check("Write on main after revoke", run("PreToolUse", repo, "Write")[1], "deny")
    cli("--allow", "5", cwd=wt)
    check("Override set from a worktree covers the main checkout", run("PreToolUse", repo, "Write")[1], None)
    common = os.path.join(repo, ".git")
    check("Override file sits in the common git dir", os.path.isfile(os.path.join(common, "always-worktree-allow")), True)
    open(os.path.join(common, "always-worktree-allow"), "w").write(f"{time.time() - 60:.0f}\n")
    check("Expired override no longer allows", run("PreToolUse", repo, "Write")[1], "deny")
    check("--allow with a bad number exits non-zero", cli("--allow", "soon", cwd=repo).returncode, 2)

    # Env kill switch
    check("Env off", run("PreToolUse", repo, "Write", env={"ALWAYS_WORKTREE_OFF": "1"})[1], None)

    # strict mode
    g("checkout", "-q", "-b", "other", cwd=repo)
    check("Feature branch in main checkout, branch mode", run("PreToolUse", repo, "Write")[1], None)
    os.makedirs(os.path.join(repo, ".claude"), exist_ok=True)
    cfg_path = os.path.join(repo, ".claude", "always-worktree.json")
    open(cfg_path, "w").write('{"mode": "strict"}')
    check("Feature branch in main checkout, strict mode", run("PreToolUse", repo, "Write")[1], "deny")
    check("Worktree, strict mode", run("PreToolUse", wt, "Write")[1], None)

    # gate_bash off
    open(cfg_path, "w").write('{"mode": "branch", "gate_bash": false}')
    g("checkout", "-q", "main", cwd=repo)
    check("Bash on main with gate_bash off", run("PreToolUse", repo, "Bash", "git commit -m x")[1], None)
    check("Write on main with gate_bash off still denied", run("PreToolUse", repo, "Write")[1], "deny")

    # Broken config and payloads stay quiet
    open(cfg_path, "w").write('["not", "an", "object"]')
    rc, d, p = run("PreToolUse", repo, "Write")
    check("Config that is not an object: still denies, no stderr", (rc, d, p.stderr), (0, "deny", ""))
    open(cfg_path, "w").write('{"allow_minutes": "a while", "mode": 7}')
    rc, d, p = run("PreToolUse", repo, "Write")
    check("Config with bad values: still denies, no stderr", (rc, d, p.stderr), (0, "deny", ""))
    os.remove(cfg_path)
    rc, d, p = run("PreToolUse", repo, raw="not json")
    check("Payload that is not JSON: silent exit 0", (rc, p.stdout, p.stderr), (0, "", ""))
    rc, d, p = run("PreToolUse", repo, raw="[1, 2]")
    check("Payload that is not an object: silent exit 0", (rc, p.stdout, p.stderr), (0, "", ""))

    # Not a git repo
    rc, d, p = run("PreToolUse", scratch, "Write")
    check("Outside a repo: silent exit 0", (rc, p.stdout), (0, ""))

    # Default branch that is not main
    trunk = make_repo("trunk", branch="trunk")
    check("trunk, no remote, no hint: nothing counts as default", run("PreToolUse", trunk, "Write")[1], None)
    g("config", "init.defaultBranch", "trunk", cwd=trunk)
    check("trunk, no remote, init.defaultBranch=trunk: denied", run("PreToolUse", trunk, "Write")[1], "deny")
    g("config", "--unset", "init.defaultBranch", cwd=trunk)
    os.makedirs(os.path.join(trunk, ".claude"))
    open(os.path.join(trunk, ".claude", "always-worktree.json"), "w").write('{"default_branch": "trunk"}')
    check("trunk, default_branch in config: denied", run("PreToolUse", trunk, "Write")[1], "deny")

    master = make_repo("legacy", branch="master")
    check("master, no remote: denied", run("PreToolUse", master, "Write")[1], "deny")

    # Remote HEAD wins over a local main
    dev = make_repo("dev")
    g("branch", "develop", cwd=dev)
    g("remote", "add", "origin", os.path.join(root, "nowhere.git"), cwd=dev)
    g("update-ref", "refs/remotes/origin/develop", "HEAD", cwd=dev)
    g("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/develop", cwd=dev)
    check("origin/HEAD -> develop: main is allowed", run("PreToolUse", dev, "Write")[1], None)
    g("checkout", "-q", "develop", cwd=dev)
    check("origin/HEAD -> develop: develop is denied", run("PreToolUse", dev, "Write")[1], "deny")

    up = make_repo("up", branch="trunk")
    g("remote", "add", "upstream", os.path.join(root, "nowhere.git"), cwd=up)
    g("update-ref", "refs/remotes/upstream/trunk", "HEAD", cwd=up)
    g("symbolic-ref", "refs/remotes/upstream/HEAD", "refs/remotes/upstream/trunk", cwd=up)
    check("Only remote is upstream, HEAD -> trunk: denied", run("PreToolUse", up, "Write")[1], "deny")

    # An override in one repo does not reach another
    cli("--allow", "5", cwd=dev)
    check("Override in one repo leaves another blocked", run("PreToolUse", up, "Write")[1], "deny")

    print(cli("--status", cwd=repo).stdout)
finally:
    shutil.rmtree(root, ignore_errors=True)

print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if results and all(results) else 1)
