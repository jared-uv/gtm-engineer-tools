#!/usr/bin/env python3
"""Exercise forbidden.py against throwaway repos.

    python3 scripts/test_forbidden.py            # finds forbidden.py next to itself
    python3 scripts/test_forbidden.py <script>   # or test another copy

Secrets are assembled at runtime so this file never contains one."""
import json, os, random, shutil, string, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(HERE, "forbidden.py")
TPL = os.path.join(os.path.dirname(os.path.dirname(SCRIPT)), "templates", "FORBIDDEN.template.md")
base = os.path.realpath(tempfile.mkdtemp(prefix="forb-test-"))
root = os.path.join(base, "repo")          # has the template registry
other = os.path.join(base, "other")        # a second checkout, no registry
outside = os.path.join(base, "plain")      # not a git repo at all
for d in (root, other, outside):
    os.makedirs(d)

def g(*a, cwd=root):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout

def w(rel, text, at=root):
    p = os.path.join(at, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(text)

for d in (root, other):
    g("init", "-q", "-b", "main", cwd=d); g("config", "user.email", "t@example.com", cwd=d); g("config", "user.name", "t", cwd=d)
shutil.copy(TPL, os.path.join(root, "FORBIDDEN.md"))

# ---- assembled values, never literal ----
rng = random.Random(7)
def rand(n, alphabet=string.ascii_letters + string.digits):
    while True:
        s = "".join(rng.choice(alphabet) for _ in range(n))
        # every character class the alphabet offers appears at least once
        if all(any(f(c) for c in s) for f in (str.isdigit, str.isupper, str.islower) if any(f(c) for c in alphabet)):
            return s

def luhn_complete(prefix, length):
    digits = prefix + "".join(str(rng.randrange(10)) for _ in range(length - len(prefix) - 1))
    for check in "0123456789":
        cand = digits + check
        total = sum((int(c) * 2 - 9 if int(c) * 2 > 9 else int(c) * 2) if i % 2 else int(c)
                    for i, c in enumerate(reversed(cand)))
        if total % 10 == 0:
            return cand

def group4(d):
    return " ".join(d[i:i + 4] for i in range(0, len(d), 4))

ssn = "536" + "-22-" + "8471"
card_visa = group4(luhn_complete("4" + "539", 16))
card_mc2 = luhn_complete("22" + "31", 16)
card_bad = card_visa[:-1] + str((int(card_visa[-1]) + 1) % 10)
aws = "AKIA" + rand(16, string.ascii_uppercase + string.digits)
anth = "sk-" + "ant-api03-" + rand(90)
oai = "sk-" + "proj-" + rand(60)
gh_tok = "gh" + "p_" + rand(36)
gh_pat = "github" + "_pat_" + rand(22) + "_" + rand(59)
pem = "-----BEGIN " + "RSA PRIVATE KEY-----"
pem_body = rand(64, string.ascii_letters + string.digits + "+/")
jwt_head = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
jwt = jwt_head + "." + "eyJ" + rand(30) + "." + rand(43)
pw = "password" + " = Hunter2secret!"
emails = "\n".join(f"person{i}@example.com" for i in range(30))
few_emails = "\n".join(f"person{i}@example.com" for i in range(5))

def run(*args, cwd=root):
    p = subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr

def raw_hook(stdin_bytes, cwd=root):
    p = subprocess.run([sys.executable, SCRIPT], input=stdin_bytes, cwd=cwd, capture_output=True)
    return p.returncode, p.stdout.decode(), p.stderr.decode()

def hook(tool, ti, target="notes.md", at=root, cwd=None):
    ti = dict(ti); ti.setdefault("file_path", os.path.join(at, target))
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": cwd or at, "session_id": "s", "tool_input": ti}
    rc, out, err = raw_hook(json.dumps(payload).encode(), cwd=cwd or at)
    out = out.strip()
    if rc != 0 or err:
        return "error", f"rc={rc} {err}"
    if not out:
        return "allow", ""
    h = json.loads(out)["hookSpecificOutput"]
    return h["permissionDecision"], h["permissionDecisionReason"]

results = []
def check(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS" if cond else "FAIL"), name, "" if cond else detail)

# --- hook: block ---
d, r = hook("Write", {"content": f"applicant ssn {ssn}\n"});           check("ssn blocks", d == "deny" and "Social security" in r and "Never stored" in r, r)
d, r = hook("Write", {"content": f"card {card_visa}\n"});              check("Luhn-valid Visa blocks", d == "deny" and "Card number" in r, r)
d, r = hook("Write", {"content": f"card {card_mc2}\n"});               check("2-series Mastercard blocks", d == "deny" and "Card number" in r, r)
d, r = hook("Write", {"content": f"id {card_bad}\n"});                 check("Luhn-invalid number allowed", d == "allow", r)
d, r = hook("Write", {"content": f"key={aws}\n"});                     check("aws key blocks", d == "deny" and "AWS" in r, r)
d, r = hook("Write", {"content": f"ANTHROPIC_API_KEY={anth}\n"});      check("anthropic key blocks, named as anthropic", d == "deny" and "Anthropic" in r and "OpenAI" not in r, r)
d, r = hook("Write", {"content": f"key: {oai}\n"});                    check("openai project key blocks", d == "deny" and "OpenAI" in r, r)
d, r = hook("Write", {"content": f"token {gh_tok}\n"});                check("github classic token blocks", d == "deny" and "GitHub" in r, r)
d, r = hook("Write", {"content": f"token {gh_pat}\n"});                check("github fine-grained token blocks", d == "deny" and "GitHub" in r, r)
d, r = hook("Write", {"content": pem + "\n" + pem_body + "\n"});       check("pem key with body blocks", d == "deny" and "Private key" in r, r)
d, r = hook("Write", {"content": json.dumps({"private_key": pem + "\n" + pem_body + "\n"}) + "\n"}); check("pem key inside JSON blocks", d == "deny" and "Private key" in r, r)
d, r = hook("Write", {"content": f"Authorization: Bearer {jwt}\n"});   check("jwt with real header blocks", d == "deny" and "JSON web token" in r, r)
d, r = hook("Write", {"content": pw + "\n"});                          check("password assignment blocks", d == "deny" and "Password" in r, r)
d, r = hook("Write", {"content": "DB_PASS" + "WORD=" + "Tr0ub4dor" + "&3x\n"});  check("env-style DB_PASSWORD blocks", d == "deny" and "Password" in r, r)
d, r = hook("Write", {"content": "CRM_API_KEY=" + rand(32) + "\n"});   check("generic secret after a prefixed name blocks", d == "deny" and "Token next to" in r, r)
d, r = hook("Edit", {"new_string": f"x {ssn}", "old_string": "y"});    check("Edit new_string scanned", d == "deny", r)
d, r = hook("MultiEdit", {"edits": [{"old_string": "a", "new_string": "b"}, {"old_string": "c", "new_string": aws}]}); check("MultiEdit edits scanned", d == "deny", r)
d, r = hook("NotebookEdit", {"new_source": f"k='{anth}'", "notebook_path": os.path.join(root, "n.ipynb")}, target="n.ipynb"); check("NotebookEdit new_source scanned", d == "deny", r)
d, r = hook("Write", {"content": f"example: {ssn}  forbidden-ok\n"});   check("forbidden-ok marker skips line", d == "allow", r)
d, r = hook("Write", {"content": f"{ssn}\n"}, target="FORBIDDEN.md");  check("registry itself never scanned", d == "allow", r)
d, r = hook("Write", {"content": f"{ssn}\n"}, target="docs/FORBIDDEN.md"); check("a file named FORBIDDEN.md elsewhere is scanned", d == "deny", r)
d, r = hook("Write", {"content": "nothing to see\n"});                 check("clean write allowed", d == "allow", r)
d, r = hook("Write", {"content": f"phone 555-123-4567 and {card_visa}  forbidden-ok\n"}); check("marker covers whole line", d == "allow", r)

# --- false positives: ordinary content that must not block ---
benign = {
    "uuid": "id 3f2504e0-4f89-11d3-9a0c-0305e82c3301",
    "git sha": "fixed in 9fceb02d0ae598e95dc970b74767f19372d61af8",
    "order numbers": "orders 4532015112830367 and 5425233430109904 and 6011000990139425 shipped",
    "dates and times": "2026-09-13 14:32:07, 09/13/2026, 1757771527123",
    "part number shaped like ssn": "SKU ABC-123-45-6789 and 123-45-6789-B",
    "sample ssn": "Enter it as 123-45-6789.",
    "published test cards": "Use 4242 4242 4242 4242 or 4111 1111 1111 1111 or 5555555555554444 in test mode.",
    "long numeric ids": "urn:li:activity:7234567890123456789 and 1234567890123456789",
    "sk- in a slug": "see sk-hynix-q3-2026-memory-market-analysis-final.md",
    "sk- placeholder": "export OPENAI_API_KEY=sk-...your-key-here...",
    "anthropic placeholder": "ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "aws doc example": "aws_access_key_id = AKIAIOSFODNN7EXAMPLE",
    "env var names": "api_key = ANTHROPIC_API_KEY_FROM_ENVIRONMENT",
    "api key placeholder": "api_key: YOUR_API_KEY_HERE_PLEASE",
    "api key from settings": "access_token = settings.crm.access_token_value",
    "password required": "Password: Required.",
    "password from env": "password = os.environ['DB_PASSWORD']",
    "password template": "password: \"{{ vault_db_password }}\"",
    "password masked": "password: ********",
    "password manager": "Password: 1Password",
    "shell pwd": "PWD=/home/runner/work/app",
    "password hash": "password_hash = bcrypt(value)",
    "pem header in prose": "The key file starts with " + pem + " and ends with the matching END line.",
    "pem header alone": pem + "\n(paste the rest here)\n",
    "eyJ not a jwt": "eyJ" + "notreallyjson1234.abcdefghijkl.mnopqrstuvwx",
    "slack placeholder": "SLACK_BOT_TOKEN=xoxb-your-token-here",
    "retina image names": "\n".join(f"icon{i}@2x.png" for i in range(40)),
}
for name, text in benign.items():
    d, r = hook("Write", {"content": text + "\n"}); check(f"benign: {name}", d == "allow", r)

# --- hook: warn ---
d, r = hook("Write", {"content": emails + "\n"});                      check("30 emails -> ask", d == "ask" and "heuristic" in r and "CRM" in r, r)
d, r = hook("Write", {"content": few_emails + "\n"});                  check("5 emails -> allow", d == "allow", r)
d, r = hook("Write", {"content": emails + f"\n{ssn}\n"});              check("block wins over warn", d == "deny" and "Social security" in r, r)
intl = "\n".join(f"+44 20 7946 {i:04d}" for i in range(30))
d, r = hook("Write", {"content": intl + "\n"});                        check("30 international phone numbers -> ask", d == "ask" and "Phone" in r, r)
w("lists/growing.md", "\n".join(f"p{i}@example.com" for i in range(24)) + "\n")
d, r = hook("Edit", {"old_string": "p0@example.com", "new_string": "p0@example.com\nnew@example.com"}, target="lists/growing.md")
check("Edit that takes a file across the threshold -> ask", d == "ask", r)
w("lists/big.md", emails + "\n")
d, r = hook("Edit", {"old_string": "person0@example.com", "new_string": "person0@example.com\nnew@example.com"}, target="lists/big.md")
check("Edit of a file already over the threshold -> allow", d == "allow", r)

# --- malformed input never crashes ---
for label, stdin in [("json list", b"[1, 2]"), ("empty stdin", b""), ("not json", b"hello"),
                     ("non-utf8", b"\xff\xfe{\x00"),
                     ("tool_input not a dict", json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": "x"}).encode()),
                     ("missing tool_input", json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Write"}).encode()),
                     ("content not a string", json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": root, "tool_input": {"file_path": os.path.join(root, "a.md"), "content": 123}}).encode()),
                     ("edits not a list", json.dumps({"hook_event_name": "PreToolUse", "tool_name": "MultiEdit", "cwd": root, "tool_input": {"file_path": os.path.join(root, "a.md"), "edits": [1, None, "x"]}}).encode()),
                     ("cwd not a string", json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": 5, "tool_input": {"file_path": os.path.join(root, "a.md"), "content": "hi"}}).encode())]:
    rc, out, err = raw_hook(stdin)
    check(f"malformed input: {label}", rc == 0 and not out.strip() and "Traceback" not in err, f"rc={rc} out={out} err={err}")

# --- which repo's registry applies ---
d, r = hook("Write", {"content": f"{ssn}\n"}, at=other, cwd=root);     check("write into a checkout with no registry, from a session in one that has it -> allow", d == "allow", r)
d, r = hook("Write", {"content": f"{ssn}\n"}, at=root, cwd=other);     check("write into the checkout with a registry, from a session elsewhere -> deny", d == "deny", r)
d, r = hook("Write", {"content": f"{ssn}\n"}, at=outside, cwd=root);   check("write outside any git repo -> allow (not checked)", d == "allow", r)
d, r = hook("Write", {"content": f"{ssn}\n"}, target="new/dir/deep.md"); check("write into a directory that does not exist yet is judged by its repo", d == "deny", r)
d, r = hook("Write", {"content": f"{ssn}\n", "file_path": "rel/notes.md"}); check("relative file_path resolved against cwd", d == "deny", r)

# --- scan CLI ---
w("docs/a.md", f"hello {ssn}\n"); w("docs/b.md", "clean\n"); w("docs/c.csv", emails + "\n")
w("docs/bin.dat", "x\x00y" + ssn)
with open(os.path.join(root, "docs/big.txt"), "w") as f:
    f.write((ssn + "\n") * 200_000)
with open(os.path.join(root, "docs/latin1.txt"), "wb") as f:
    f.write(b"caf\xe9 " + ssn.encode() + b"\n")
rc, out, err = run("scan", "docs")
check("scan finds block and warn, exit 1", rc == 1 and "docs/a.md:1" in out and "docs/c.csv" in out and "2 blocking" in out, out + err)
check("scan redacts", ssn not in out, out)
check("scan skips binary", "bin.dat" not in out, out)
check("scan skips files over the size limit", "big.txt" not in out, out)
check("scan reads non-UTF-8 text", "latin1.txt:1" in out, out)
rc, out, err = run("scan", "docs/b.md");                                check("clean scan exit 0", rc == 0 and "0 finding" in out, out)
rc, out, err = run("scan", "docs/nope.md");                             check("missing path says so", rc == 0 and "no such path" in err, out + err)
w("x.md", f"{ssn}\n", at=other)
rc, out, err = run("scan", os.path.join(other, "x.md"))
check("scan judges a file by its own repo's registry", rc == 0 and "no FORBIDDEN.md" in err and "0 finding" in out, out + err)

# --- staged ---
g("add", "docs/b.md", "docs/c.csv")
rc, out, err = run("staged");                                          check("staged: warn only passes, prints", rc == 0 and "docs/c.csv" in out, out + err)
rc, out, err = run("scan", "--staged");                                check("scan --staged is staged", rc == 0 and "docs/c.csv" in out, out + err)
g("add", "docs/a.md")
rc, out, err = run("staged");                                          check("staged: block refuses", rc == 1 and "docs/a.md" in out and "refused" in err, out + err)
w("docs/with space.md", f"{ssn}\n"); g("add", "docs/with space.md"); g("rm", "-q", "--cached", "docs/a.md")
rc, out, err = run("staged");                                          check("staged: path with a space", rc == 1 and "with space.md" in out, out + err)

# --- check / patterns / init ---
rc, out, err = run("check");                                           check("template passes check", rc == 0 and "16 rules, no problems" in out, out)
rc, out, err = run("scan", "--check");                                 check("scan --check is check", rc == 0 and "no problems" in out, out)
reg = open(os.path.join(root, "FORBIDDEN.md")).read()
w("FORBIDDEN.md", reg + "| Bad | nosuch | block | x | |\n| Bad2 | email-list:5 | block |  | |\n| Bad3 | regex: ( | warn | x | |\n")
rc, out, err = run("check");                                           check("check flags unknown detector, heuristic-block, empty Instead, bad regex", rc == 1 and "not a known" in out and "cry wolf" in out and "Instead is empty" in out and "does not compile" in out, out)
w("FORBIDDEN.md", reg + "| Custom | regex: (?i)\\bIBAN\\b\\s*\\d{6,} | block | bank | |\n| Upper | SSN | block | x | |\n")
d, r = hook("Write", {"content": "IBAN " + "12345678\n"});             check("custom regex rule works", d == "deny" and "Custom" in r, r)
rc, out, err = run("check");                                           check("detector names are case-insensitive", rc == 0, out)
rc, out, err = run("patterns")
check("patterns lists fourteen built-ins and two heuristics", "built-in detectors, 14" in out and "anthropic-key" in out and "email-list" in out and "phone-list" in out, out)
rc, out, err = run("scan", "--patterns");                              check("scan --patterns is patterns", "built-in detectors" in out, out)
rows = [l for l in open(TPL) if l.startswith("| ") and not l.startswith("| Class")]
check("template has sixteen rows", len(rows) == 16, len(rows))
os.remove(os.path.join(root, "FORBIDDEN.md"))
d, r = hook("Write", {"content": f"{ssn}\n{aws}\n"});                   check("no registry -> hook does nothing", d == "allow", r)
rc, out, err = run("check");                                           check("check with no registry says to init", rc == 1 and "init" in out, out)
rc, out, err = run("init");                                            check("init writes template", rc == 0 and os.path.exists(os.path.join(root, "FORBIDDEN.md")), out)
rc, out, err = run("init");                                            check("init leaves an existing registry alone", rc == 0 and "already exists" in out, out)
rc, out, err = run("init", cwd=outside);                               check("init outside a git repo refuses", rc == 1 and not os.path.exists(os.path.join(outside, "FORBIDDEN.md")), out)
rc, out, err = run("staged", cwd=outside);                             check("staged outside a git repo exits quietly", rc == 0 and "not inside a git repository" in err, out + err)

shutil.rmtree(base)
print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
