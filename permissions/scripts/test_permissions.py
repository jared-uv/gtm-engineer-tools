#!/usr/bin/env python3
"""Exercise permissions.py against throwaway repos with both registries.

    python3 scripts/test_permissions.py [path/to/permissions.py]

With no argument it tests the permissions.py next to this file.
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(HERE, "permissions.py")
base = os.path.realpath(tempfile.mkdtemp(prefix="perm-test-"))
root = os.path.join(base, "repo")
other = os.path.join(base, "other")
bare = os.path.join(base, "noident")
outside = os.path.join(base, "not-a-repo")
for d in (root, other, bare, outside):
    os.makedirs(d)
empty_cfg = os.path.join(base, "gitconfig-empty"); open(empty_cfg, "w").close()

# No global or system git config leaks in: identity comes only from each repo.
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=empty_cfg, GIT_CONFIG_NOSYSTEM="1", HOME=base)
ENV.pop("GITHUB_USER", None); ENV.pop("CANONICAL_FILE", None)

def g(*a, cwd=root):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True, env=ENV).stdout.strip()

def w(rel, text="x\n", at=root):
    p = os.path.join(at, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w").write(text)

g("init", "-q", "-b", "main")
w("CANONICAL.md", """# Where
| Type | Where | Class | Required | Owner | Cadence | Reviewed | Notes |
|---|---|---|---|---|---|---|---|
| Positioning | docs/positioning.md | governed | yes | Dana | 3m | - | |
| Voice | `docs/voice/dana.md` then `docs/style/` | governed | yes | Dana | 6m | - | |
| Drafts | docs/drafts/ | open | no | - | - | - | |
| Tasks | tracker: Tasks board | external | yes | Dana | - | - | |
| Orphan | docs/orphan.md | governed | no | - | - | - | |
""")
w("PERMISSIONS.md", """# Who
| Path | Who | On miss | Notes |
|---|---|---|---|
| CANONICAL.md | Dana, @dana | block | |
| contracts/ | dana@example.com | block | |
| .claude/**/*.json | Dana | propose | |
| docs/launch-plan.md | * | propose | anyone |
| docs/ | @dana | block | |
| lib/ | Dana | propose | |
| .github/ | Dana, @dana | block | |
| ./ops/x.md | Dana | block | |
| *.txt | @dana | block | root-level text files |
""")
w(".github/workflows/ci.yml"); w("ops/x.md"); w("notes.txt"); w("sub/deep.txt")
w("docs/positioning.md"); w("docs/voice/dana.md"); w("docs/style/x.md"); w("docs/orphan.md")
w("docs/drafts/post.md"); w("contracts/deal.docx"); w(".claude/hooks/a.json"); w(".claude/settings.json")
w("docs/launch-plan.md"); w("lib/h.py"); w("README.md")
g("add", "."); g("config", "user.email", "s@example.com"); g("config", "user.name", "Stranger"); g("commit", "-q", "-m", "init")

# A second checkout with its own rules, and a repo where git knows nobody.
g("init", "-q", "-b", "main", cwd=other)
w("PERMISSIONS.md", "| Path | Who | On miss | Notes |\n|---|---|---|---|\n| secret.md | Dana | block | |\n", at=other)
w("secret.md", at=other); w("free.md", at=other)
g("config", "user.email", "s@example.com", cwd=other)
g("init", "-q", "-b", "main", cwd=bare)
w("PERMISSIONS.md", "| Path | Who | On miss | Notes |\n|---|---|---|---|\n| locked.md | Dana | block | |\n", at=bare)

def run(*args, cwd=root, env=None):
    e = dict(ENV); e.update(env or {})
    p = subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd, capture_output=True, text=True, env=e)
    return p.returncode, p.stdout, p.stderr

def raw_hook(stdin, cwd=root, env=None):
    e = dict(ENV); e.update(env or {})
    p = subprocess.run([sys.executable, SCRIPT], input=stdin, cwd=cwd, capture_output=True, text=True, env=e)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def hook(target, session="s1", tool="Write", key="file_path", cwd=root, env=None):
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": cwd, "session_id": session,
               "tool_input": {key: target if os.path.isabs(target) else os.path.join(root, target)}}
    rc, out, err = raw_hook(json.dumps(payload), cwd=cwd, env=env)
    if not out:
        return "allow", err
    h = json.loads(out)["hookSpecificOutput"]
    return h["permissionDecision"], h["permissionDecisionReason"]

results = []
def check(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS" if cond else "FAIL"), name, "" if cond else detail)

# --- hook, as Stranger ---
d, r = hook("CANONICAL.md");                 check("stranger blocked on CANONICAL.md", d == "deny" and "Dana" in r and "Do not edit" in r, r)
d, r = hook("contracts/deal.docx");          check("stranger blocked under contracts/", d == "deny" and "dana@example.com" in r, r)
d, r = hook("contracts/new/sub.md");         check("directory rule covers new nested file", d == "deny", r)
d, r = hook("docs/launch-plan.md");          check("Who=* allows anyone, ahead of a broader block", d == "allow", r)
d, r = hook("docs/positioning.md");          check("PERMISSIONS.md row wins over a CANONICAL.md row", d == "deny" and "Do not edit" in r, r)
d, r = hook("lib/h.py", tool="Edit");        check("propose: first refusal states the rule", d == "deny" and "proposal" in r and "hold" in r, r)
d, r = hook("lib/h.py", tool="Edit");        check("propose: same path second time allowed", d == "allow", r)
d, r = hook("lib/h.py", session="s2");       check("propose: new session refuses once again", d == "deny", r)
d, r = hook("README.md");                    check("unruled path allowed", d == "allow", r)
d, r = hook(".claude/hooks/a.json");         check("** glob matches nested", d == "deny" and "proposal" in r, r)
d, r = hook(".claude/hooks/a.py");           check("glob does not match other extension", d == "allow", r)
d, r = hook(".github/workflows/ci.yml");     check("dot-directory rule matches", d == "deny", r)
d, r = hook("ops/x.md");                     check("./ prefix on a rule is ignored", d == "deny", r)
d, r = hook("notes.txt");                    check("*.txt matches at the root", d == "deny", r)
d, r = hook("sub/deep.txt");                 check("*.txt does not match deeper", d == "allow", r)
d, r = hook("nb.ipynb", tool="NotebookEdit", key="notebook_path"); check("notebook_path read, unruled", d == "allow", r)
d, r = hook("CANONICAL.md", env={"GITHUB_USER": "dana"}); check("GITHUB_USER matches @dana", d == "allow", r)

# --- CANONICAL.md contract, tested with PERMISSIONS.md out of the way ---
shutil.move(os.path.join(root, "PERMISSIONS.md"), os.path.join(base, "PERMISSIONS.md.bak"))
d, r = hook("docs/positioning.md", session="c1"); check("governed row -> propose", d == "deny" and "proposal" in r and "Positioning" in r, r)
d, r = hook("docs/style/new.md", session="c1");   check("waterfall second place (backticked) is governed too", d == "deny" and "Voice" in r, r)
d, r = hook("docs/drafts/post.md", session="c1"); check("open row -> no rule", d == "allow", r)
rc, out, err = run("rules");                      check("external row with no path makes no rule", "Tasks" not in out and "tracker" not in out, out)
d, r = hook("docs/orphan.md", session="c1");      check("Owner `-` is nobody named", d == "deny" and "nobody named" in r, r)
os.rename(os.path.join(root, "CANONICAL.md"), os.path.join(root, "REGISTRY.md"))
rc, out, err = run("rules", env={"CANONICAL_FILE": "REGISTRY.md"}); check("CANONICAL_FILE override honoured", "docs/positioning.md" in out and "REGISTRY.md" in out, out)
os.rename(os.path.join(root, "REGISTRY.md"), os.path.join(root, "CANONICAL.md"))
shutil.move(os.path.join(base, "PERMISSIONS.md.bak"), os.path.join(root, "PERMISSIONS.md"))

# --- paths are judged by the repo that holds them ---
d, r = hook(os.path.join(other, "secret.md"));              check("cwd in one checkout, target in another: other's rules apply", d == "deny" and "secret.md" in r, r)
d, r = hook(os.path.join(other, "free.md"));                check("other checkout, unruled file allowed", d == "allow", r)
d, r = hook(os.path.join(root, "README.md"), cwd=other);    check("root's README judged by root, not by cwd", d == "allow", r)
d, r = hook(os.path.join(root, "CANONICAL.md"), cwd=other); check("root's CANONICAL.md blocked from a session in other", d == "deny", r)
d, r = hook(os.path.join(outside, "x.md"));                 check("target outside any repo: silent", d == "allow" and r == "", r)
d, r = hook(os.path.join(root, "CANONICAL.md"), cwd=outside); check("session outside any repo, target inside: judged", d == "deny", r)
d, r = hook(os.path.join(root, "brand-new/dir/f.md"));      check("target in a directory that does not exist yet", d == "allow" and r == "", r)

# --- silent no-ops ---
d, r = hook(os.path.join(bare, "locked.md"), cwd=bare);     check("no git identity: silent", d == "allow" and r == "", r)
for label, stdin in [("not JSON", "nope"), ("JSON list", "[1,2]"), ("tool_input a string", json.dumps({"hook_event_name": "PreToolUse", "tool_input": "x"})),
                     ("file_path not a string", json.dumps({"hook_event_name": "PreToolUse", "cwd": root, "tool_input": {"file_path": 5}})),
                     ("empty stdin", ""), ("other event", json.dumps({"hook_event_name": "PostToolUse", "cwd": root, "tool_input": {"file_path": os.path.join(root, "CANONICAL.md")}}))]:
    rc, out, err = raw_hook(stdin);                          check(f"malformed input ({label}): exit 0, no output", rc == 0 and out == "" and err == "", out + err)

# --- CLI test / whoami / rules ---
rc, out, err = run("test", "contracts/deal.docx");          check("test: stranger blocked", "block" in out and "as: s@example.com" in out, out)
rc, out, err = run("test", "contracts/deal.docx", "--as", "dana@example.com"); check("test --as owner allows", out.startswith("contracts/deal.docx: allow"), out)
rc, out, err = run("test", "README.md", "--as");            check("test --as with no value: usage, no traceback", rc == 2 and "usage" in out and "Traceback" not in err, out + err)
rc, out, err = run("test", "README.md");                    check("test: no rule", "no rule" in out, out)
rc, out, err = run("test", os.path.join(other, "secret.md")); check("test: path in another checkout uses its rules", "judged against" in out and "secret.md: block" in out, out)
rc, out, err = run("test", os.path.join(outside, "x.md"));  check("test: path outside any repo", rc == 0 and "outside any git repository" in out, out)
rc, out, err = run("test", "../CANONICAL.md", cwd=os.path.join(root, "docs")); check("test from a subdirectory resolves against cwd", out.startswith("CANONICAL.md: block"), out)
rc, out, err = run("whoami");                               check("whoami lists email and name", "s@example.com" in out and "stranger" in out, out)
rc, out, err = run("whoami", cwd=bare);                     check("whoami with no identity says so", "no identity" in out, out)
rc, out, err = run("rules");                                check("rules lists PERMISSIONS rows before CANONICAL rows", out.index("lib/") < out.index("Positioning"), out)
rc, out, err = run("test", "--rules");                      check("test --rules runs rules, not a path lookup", "no rule" not in out and out.index("lib/") < out.index("Positioning"), out)
rc, out, err = run("test", "--whoami");                     check("test --whoami runs whoami", "no rule" not in out and "s@example.com" in out, out)
rc, out, err = run("--check");                              check("--check alone runs check", "no rule" not in out and out == run("check")[1], out)
rc, out, err = run("check", cwd=outside);                   check("CLI outside a repo: clear message, no traceback", rc == 2 and "not inside a git repository" in err and "Traceback" not in err, err)
rc, out, err = run("bogus");                                check("unknown command prints usage", rc == 2 and "CLI" in out, out)

# --- check ---
rc, out, err = run("check");                                check("check flags the Owner `-` row only", rc == 1 and "1 problem" in out and "docs/orphan.md" in out, out)
canon = open(os.path.join(root, "CANONICAL.md")).read()
w("CANONICAL.md", canon.replace("| docs/orphan.md | governed | no | - |", "| docs/orphan.md | governed | no | Dana |"))
rc, out, err = run("check");                                check("check clean", rc == 0 and "no problems" in out, out)
perm = open(os.path.join(root, "PERMISSIONS.md")).read()
w("PERMISSIONS.md", perm + "| ghost/ |  | maybe | |\n")
rc, out, err = run("check");                                check("check flags empty Who, bad On miss, missing path", rc == 1 and "Who is empty" in out and "must be block or propose" in out and "does not exist" in out, out)
w("PERMISSIONS.md", perm)

# --- codeowners ---
rc, out, err = run("codeowners")
check("codeowners emits @handle rules, anchored", "/CANONICAL.md @dana" in out and "/*.txt @dana" in out and "contracts" not in out, out)
check("codeowners: Who=* becomes an ownerless line after the broader rule", "\n/docs/launch-plan.md\n" in out and out.index("/docs/ @dana") < out.index("/docs/launch-plan.md"), out)
check("codeowners reports skipped", "skipped" in err and "contracts/" in err, err)
rc, out, err = run("codeowners", "--write");                check("codeowners --write refused when .github/ is blocked for you", rc == 1 and not os.path.exists(os.path.join(root, ".github", "CODEOWNERS")) and "Not written" in err, out + err)
rc, out, err = run("codeowners", "--write", env={"GITHUB_USER": "dana"}); check("codeowners --write as owner", rc == 0 and os.path.exists(os.path.join(root, ".github", "CODEOWNERS")), out + err)

# --- staged ---
w("contracts/deal.docx", "changed\n"); w("lib/h.py", "changed\n"); w("README.md", "changed\n")
g("add", "contracts/deal.docx", "lib/h.py", "README.md")
rc, out, err = run("staged");                               check("staged: refused on block, warns on propose", rc == 1 and "contracts/deal.docx" in err and "lib/h.py" in out and "hold" in out, out + err)
g("reset", "-q", "contracts/deal.docx")
rc, out, err = run("staged");                               check("staged: passes with only propose + unruled", rc == 0 and "lib/h.py" in out, out + err)
g("checkout", "-q", "--", "contracts/deal.docx"); g("reset", "-q"); g("checkout", "-q", "--", ".")
g("mv", "contracts/deal.docx", "deal.docx")
rc, out, err = run("staged");                               check("staged: moving a blocked file out is refused", rc == 1 and "contracts/deal.docx" in err, out + err)
g("reset", "-q", "--hard")

# --- no registries at all ---
os.remove(os.path.join(root, "PERMISSIONS.md")); os.remove(os.path.join(root, "CANONICAL.md"))
d, r = hook("contracts/deal.docx", session="s4");          check("no registries -> silent", d == "allow" and r == "", r)
rc, out, err = run("check");                                check("check with no rules says so", rc == 0 and "no rules" in out, out)
rc, out, err = run("init")
written = open(os.path.join(root, "PERMISSIONS.md")).read() if os.path.exists(os.path.join(root, "PERMISSIONS.md")) else ""
check("init writes the template, only rows for paths that exist", rc == 0 and "| contracts/ |" in written and "| PERMISSIONS.md |" in written
      and "| CANONICAL.md |" not in written and "CANONICAL.md" in out and "| Path | Who |" in written, out + written)
rc, out, err = run("init");                                 check("init never overwrites", "already exists" in out, out)

shutil.rmtree(base)
print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
