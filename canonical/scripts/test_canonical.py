#!/usr/bin/env python3
"""Exercise canonical.py against a throwaway registry.

    python3 scripts/test_canonical.py                  finds canonical.py beside itself
    python3 scripts/test_canonical.py path/to/canonical.py
"""
import json, os, shutil, subprocess, sys, tempfile, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(HERE, "canonical.py")
root = tempfile.mkdtemp(prefix="canon-test-")
os.makedirs(os.path.join(root, "docs"))
open(os.path.join(root, "docs", "positioning.md"), "w").write("# pos\n")
os.makedirs(os.path.join(root, "transcripts"))

today = dt.date.today()
fresh = (today - dt.timedelta(days=10)).isoformat()
old = (today - dt.timedelta(days=200)).isoformat()

REG = f"""# Where things live

Some prose above the table, with a | pipe in it.

| Type | Where | Class | Required | Owner | Cadence | Reviewed | Notes |
|---|---|---|---|---|---|---|---|
| Positioning | `docs/positioning.md` | governed | yes | Dana | 3m | {fresh} | One answer. |
| Author voice | docs/authors/dana.md then docs/style/ | governed | yes | Dana | 6m | {old} | profile wins |
| Call transcripts | transcripts/ | open | no | - | - | - | raw |
| Tasks and todos | tasks: the team tracker https://example.com/x | external | yes | Dana | 1m | - | |
| Contacts | crm: Accounts | external | yes | - | - | - | |
"""
path = os.path.join(root, "CANONICAL.md")
open(path, "w").write(REG)

def run(*args, env=None, cwd=None):
    e = dict(os.environ, CANONICAL_FILE=path)
    if env: e.update(env)
    p = subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd or root, capture_output=True, text=True, env=e)
    return p.returncode, p.stdout, p.stderr

results = []
def check(name, cond, detail=""):
    results.append(cond)
    print(("PASS" if cond else "FAIL"), name, "" if cond else detail)

rc, out, err = run("list", "--json")
rows = json.loads(out)
check("list parses 5 rows", len(rows) == 5, out[:200])
check("backticks stripped from Where", rows[0]["where"] == ["docs/positioning.md"], str(rows[0]["where"]))
check("waterfall split on then", rows[1]["where"] == ["docs/authors/dana.md", "docs/style/"], str(rows[1]["where"]))
check("fresh row ok", rows[0]["freshness"] == "ok", rows[0]["freshness_detail"])
check("old row stale", rows[1]["freshness"] == "stale", rows[1]["freshness_detail"])
check("no cadence -> none", rows[2]["freshness"] == "none")
check("cadence but never reviewed -> never", rows[3]["freshness"] == "never")

rc, out, err = run("where", "positioning")
check("where exact match", rc == 0 and out.startswith("Positioning"), out[:100])
rc, out, err = run("where", "voice")
check("where substring match", rc == 0 and "Author voice" in out and "1. docs/authors/dana.md" in out, out[:200])
check("where matches type before notes", "Positioning" not in out, out[:300])
rc, out, err = run("where", "profile")
check("where falls back to notes", rc == 0 and "Author voice" in out, out[:200])
rc, out, err = run("where", "todo")
check("where matches inside type words", rc == 0 and "Tasks and todos" in out, out[:200])
rc, out, err = run("where", "positoning")
check("where fuzzy match", rc == 0 and "Positioning" in out, out[:200])
rc, out, err = run("where", "unicorns")
check("where miss lists entries and exits 1", rc == 1 and "Positioning" in out, out[:200])
rc, out, err = run("where", "unicorns", "--json")
check("where miss with --json prints [] and exits 1", rc == 1 and json.loads(out) == [] and "Positioning" in err, out + err)

rc, out, err = run("stale", "--json")
stale = {r["type"] for r in json.loads(out)}
check("stale = old + never", stale == {"Author voice", "Tasks and todos"}, str(stale))
rc, out2, err = run("where", "--stale", "--json")
check("where --stale is the same as stale", rc == 0 and json.loads(out2) == json.loads(out), out2[:200])

rc, out, err = run("check")
check("check flags the two missing paths, nothing else", rc == 1 and "docs/authors/dana.md" in out and "docs/style/" in out and "Positioning" not in out and "Contacts" not in out, out)
problems = [l for l in out.splitlines() if l.startswith("  ")]
check("check reports exactly 2 problems", len(problems) == 2, out)
check("external rows may have no owner", "Contacts" not in out)
rc2, out2, err = run("where", "--check")
check("where --check is the same as check", rc2 == 1 and out2 == out, out2)

# a governed row with no owner is a problem
open(path, "w").write(REG.replace("| governed | yes | Dana | 3m |", "| governed | yes | - | 3m |", 1))
rc, out, err = run("check")
check("governed row without owner flagged", "Positioning" in out and "need an Owner" in out, out)

# fix the registry and re-check
os.makedirs(os.path.join(root, "docs", "authors")); open(os.path.join(root, "docs", "authors", "dana.md"), "w").write("x")
os.makedirs(os.path.join(root, "docs", "style"))
open(path, "w").write(REG)
rc, out, err = run("check")
check("check clean after fixes", rc == 0 and "no problems" in out, out)

# bad values
open(path, "w").write(REG + "| Dup | transcripts/ | secret | no | - | soon | yesterday | |\n| Dup | transcripts/ | open | no | - | - | - | |\n")
rc, out, err = run("check")
check("check flags bad class, cadence, date, duplicate", all(s in out for s in ["not one of", "Cadence `soon`", "Reviewed `yesterday`", "duplicate"]), out)

# no table
open(path, "w").write("# nothing here\n")
rc, out, err = run("list")
check("no table -> problem", rc == 1 and "no table" in (out + err), out + err)

# malformed input never produces a traceback
open(path, "wb").write(os.urandom(300) + b"\xff\xfe| Type | Where |\n")
rc, out, err = run("list")
check("non-UTF-8 registry: message, no traceback", rc == 1 and "UTF-8" in err and "Traceback" not in err, err)
rc, out, err = run("list", env={"CANONICAL_FILE": root})
check("registry path is a directory: message, no traceback", rc == 1 and "directory" in err and "Traceback" not in err, err)

# usage
rc, out, err = run("--help")
check("--help prints usage and exits 0", rc == 0 and "canonical.py where" in out, out + err)
rc, out, err = run("frobnicate")
check("unknown command exits 2 with usage", rc == 2 and "unknown command" in err and "Traceback" not in err, out + err)

# init
os.remove(path)
rc, out, err = run("where", "positioning")
check("no registry: points at setup, no traceback", rc == 1 and "/canonical:setup" in err and "Traceback" not in err, out + err)
rc, out, err = run("init")
check("init writes template", rc == 0 and os.path.exists(path) and "| Type | Where |" in open(path).read(), out + err)
rc, out, err = run("init")
check("init refuses to overwrite", "already exists" in out, out)
rc, out, err = run("init", env={"CANONICAL_FILE": os.path.join(root, "no", "such", "dir", "CANONICAL.md")})
check("init into a missing directory: message, no traceback", rc == 1 and "cannot write" in err and "Traceback" not in err, out + err)
rc, out, err = run("check")
check("fresh template reads as a registry with problems to fill in", rc == 1 and "need an Owner" in out and "Traceback" not in err, out + err)

shutil.rmtree(root)
print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
