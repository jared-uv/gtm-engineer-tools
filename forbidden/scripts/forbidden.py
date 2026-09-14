#!/usr/bin/env python3
"""forbidden — information that must never enter the repo, and where it goes instead.

The registry is FORBIDDEN.md at the root of the git repository, a table:

    | Class | Detect | Action | Instead | Notes |

Detect   a built-in detector name (see `forbidden.py patterns`), a heuristic with
         a threshold such as `email-list:25`, or `regex: <pattern>`.
Action   block   objective: the write or commit is refused.
         warn    heuristic: in a Claude session the tool call is turned into a
                 permission prompt that states the finding; at commit it prints.
Instead  where this kind of information belongs. The column that makes this more
         than a secret scanner.

A line containing `forbidden-ok` is skipped, for fixtures and documentation.
The registry file itself is never scanned.

Every file is judged by the FORBIDDEN.md of the git repository that holds it.
A repository with no FORBIDDEN.md, and a file outside any repository, is not
checked by the hook at all.

CLI:
  forbidden.py scan <path>...     scan files or directories; exit 1 on a block hit
  forbidden.py scan --staged      same as `staged`
  forbidden.py scan --check       same as `check`
  forbidden.py scan --patterns    same as `patterns`
  forbidden.py staged             pre-commit: scan the index; exit 1 on a block hit
  forbidden.py patterns           the built-in detectors
  forbidden.py check              validate the registry
  forbidden.py init               write the template if there is no FORBIDDEN.md

With no subcommand it reads a PreToolUse payload on stdin and acts as the hook.
Standard library only.
"""

import base64
import json
import os
import re
import subprocess
import sys

OK_MARKER = "forbidden-ok"
REGISTRY = "FORBIDDEN.md"
MAX_BYTES = 2_000_000
DEFAULT_THRESHOLD = 25

# ---------- validators: what turns a regex match into a finding ----------

PLACEHOLDER = re.compile(r"(?i)example|placeholder|redacted|changeme|dummy|sample|your[_-]|[_-]here(?![a-z])|x{5,}|\*{3}|\.\.\.")
WORDLIKE = re.compile(r"[a-z]+|[A-Z]+|\d+|[A-Z][a-z]+")


def body(m):
    """The secret part of a match: the first named group that matched, else all of it."""
    for v in m.groupdict().values():
        if v:
            return v
    return m.group(0)


def looks_random(s, min_len=16):
    """True when s reads like a generated token rather than a word, a slug, a
    variable name or a placeholder. Real keys mix case and digits inside one
    run; `sk-market-analysis-2026` and `YOUR_API_KEY` do not."""
    if len(s) < min_len or PLACEHOLDER.search(s) or len(set(s)) < 8:
        return False
    segs = [x for x in re.split(r"[-_./+=]", s) if x]
    # Short mixed runs such as q3, v2 or 2x are ordinary in slugs; a key has a long one.
    return any(len(x) >= 6 and not WORDLIKE.fullmatch(x) for x in segs)


def token_ok(m):
    return looks_random(body(m))


def aws_ok(m):
    return "EXAMPLE" not in m.group(0)


SSN_EXAMPLES = {"123-45-6789", "078-05-1120", "219-09-9999"}


def ssn_ok(m):
    return m.group(0) not in SSN_EXAMPLES


def luhn(digits):
    total = 0
    for i, c in enumerate(reversed(digits)):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def card_brand(d):
    """True when the length fits the issuer range the number starts with."""
    n, p2, p3, p4, p6 = len(d), int(d[:2]), int(d[:3]), int(d[:4]), int(d[:6])
    if d[0] == "4":
        return n in (16, 19)                                   # Visa
    if 51 <= p2 <= 55 or 2221 <= p4 <= 2720:
        return n == 16                                         # Mastercard
    if p2 in (34, 37):
        return n == 15                                         # Amex
    if p4 == 6011 or p2 == 65 or 644 <= p3 <= 649 or 622126 <= p6 <= 622925:
        return 16 <= n <= 19                                   # Discover
    if p2 == 62:
        return 16 <= n <= 19                                   # UnionPay
    if 3528 <= p4 <= 3589:
        return 16 <= n <= 19                                   # JCB
    if 300 <= p3 <= 305 or p2 in (36, 38):
        return 14 <= n <= 19                                   # Diners
    return False


# The processors' published test numbers. Documentation is full of them.
TEST_CARDS = {
    "4111111111111111", "4242424242424242", "4012888888881881", "4222222222222",
    "4000056655665556", "5555555555554444", "5105105105105100", "5200828282828210",
    "2223003122003222", "378282246310005", "371449635398431", "378734493671000",
    "6011111111111117", "6011000990139424", "6011000400000000", "3530111333300000",
    "3566002020360505", "30569309025904", "38520000023237", "36227206271667",
    "6200000000000005", "6555900000604105",
}


def card_ok(m):
    d = re.sub(r"\D", "", m.group(0))
    if d in TEST_CARDS or re.search(r"(\d)\1{5}", d):
        return False
    return card_brand(d) and luhn(d)


def jwt_ok(m):
    head = m.group(0).split(".", 1)[0]
    try:
        obj = json.loads(base64.urlsafe_b64decode(head + "=" * (-len(head) % 4)))
    except (ValueError, TypeError):
        return False
    return isinstance(obj, dict) and "alg" in obj


NOT_PASSWORDS = {"required", "optional", "none", "null", "true", "false", "string", "hidden",
                 "password", "1password", "keychain", "prompt", "unset", "empty"}


def password_ok(m):
    v = m.group("s").rstrip(".,;:!?)")
    if len(v) < 6 or v.lower() in NOT_PASSWORDS or PLACEHOLDER.search(v):
        return False
    if v[0] in "$%{<[(*/~.@&#`\\" or any(c in v for c in "(){}[]<>$`"):
        return False                                           # a variable, a template, a path
    if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", v):
        return False                                           # settings.db_password
    has_letter = re.search(r"[A-Za-z]", v)
    has_digit_or_symbol = re.search(r"[^A-Za-z\-_'.]", v)
    return bool(has_letter and has_digit_or_symbol)


def email_ok(m):
    return m.group(0).rsplit(".", 1)[-1].lower() not in FILE_EXTENSIONS


FILE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "avif", "js", "ts", "css",
                   "json", "md", "py", "rb", "html", "txt", "pdf", "yml", "yaml", "lock"}

# name: (regex, description, validator, scan the whole text rather than line by line)
BUILTIN = {
    "ssn": (r"(?<![\w-])(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?![\w-])",
            "US social security number, hyphenated; the well-known sample numbers are ignored", ssn_ok, False),
    "card": (r"(?<![\w.-])[2-6](?:\d{13,18}|\d{3}(?:[ -]\d{4}){3}(?:[ -]?\d{1,3})?|\d{3}[ -]\d{6}[ -]\d{4,5})(?![\w-])",
             "card number: issuer prefix and length fit, passes Luhn, not a published test number", card_ok, False),
    "aws-key": (r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b", "AWS access key id (not the documentation example)", aws_ok, False),
    "github-token": (r"\b(?:gh[pousr]_(?P<a>[A-Za-z0-9]{36,})|github_pat_(?P<b>[A-Za-z0-9_]{60,}))",
                     "GitHub token, classic or fine-grained", token_ok, False),
    "slack-token": (r"\bxox[abeoprs]-(?P<s>\d+-[A-Za-z0-9-]{10,})", "Slack token", token_ok, False),
    "anthropic-key": (r"(?<![\w-])sk-ant-(?P<s>[A-Za-z0-9_-]{32,})", "Anthropic API key", token_ok, False),
    "openai-key": (r"(?<![\w-])sk-(?!ant-)(?:(?:proj|svcacct|admin)-)?(?P<s>[A-Za-z0-9_-]{32,})",
                   "OpenAI API key", token_ok, False),
    "google-api-key": (r"\bAIza(?P<s>[0-9A-Za-z_-]{35})(?![\w-])", "Google API key", token_ok, False),
    "stripe-key": (r"\b[rs]k_(?:live|test)_(?P<s>[A-Za-z0-9]{20,})", "Stripe secret or restricted key", token_ok, False),
    "notion-token": (r"\b(?:secret|ntn)_(?P<s>[A-Za-z0-9]{40,})\b", "Notion integration token", token_ok, False),
    "private-key": (r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP |ENCRYPTED )?PRIVATE KEY(?: BLOCK)?-----[ \t]*"
                    r"(?:\r?\n|\\n)(?:[A-Za-z-]+:[^\n]*(?:\r?\n|\\n))*[ \t]*(?:\r?\n|\\n)?[ \t]*[A-Za-z0-9+/=]{40,}",
                    "PEM private key: the header followed by key material, not a header quoted in prose", None, True),
    "jwt": (r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "JSON web token with a real header", jwt_ok, False),
    "password-assignment": (r"(?i)(?<![a-z])(?:password|passwd|passphrase)[\"']?\s*[:=]\s*[\"']?(?P<s>[^\s\"',;]{6,})",
                            "a literal password assigned to a password field; variables, templates and placeholders are ignored",
                            password_ok, False),
    "generic-secret": (r"(?i)(?<![a-z])(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|private[_-]?token)"
                       r"[\"']?\s*[:=]\s*[\"']?(?P<s>[A-Za-z0-9_\-./+=]{16,})",
                       "a generated-looking value assigned to a field that means token", token_ok, False),
}
HEURISTICS = {
    "email-list": (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "N or more distinct email addresses in one file", email_ok),
    "phone-list": (r"(?<![\w+-])(?:(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}"
                   r"|\+[1-9]\d{0,2}[ .-]?(?:\(\d{1,4}\)[ .-]?)?\d{1,4}(?:[ .-]?\d{2,4}){2,4})(?![\w-])",
                   "N or more distinct phone numbers in one file, North American or written with a +country code", None),
}


def sh(args, cwd=None):
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else None


def repo_root(start=None):
    """The git top level holding `start` (a file or directory, need not exist yet), or None."""
    d = os.path.abspath(start or os.getcwd())
    while d and not os.path.isdir(d):
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent
    out = sh(["git", "rev-parse", "--show-toplevel"], d)
    return os.path.realpath(out.strip()) if out and out.strip() else None


def is_registry(path, root):
    return os.path.realpath(path) == os.path.join(root, REGISTRY)


# ---------- registry ----------

def strip_md(s):
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s.strip()).strip("`").strip()


def parse_table(text):
    lines = text.splitlines()
    for i, line in enumerate(lines[:-1]):
        if not line.lstrip().startswith("|") or not re.match(r"^\s*\|?\s*:?-+", lines[i + 1]):
            continue
        header = [strip_md(h).lower() for h in line.strip().strip("|").split("|")]
        if not all(c in header for c in ("class", "detect", "action")):
            continue
        rows, j = [], i + 2
        while j < len(lines) and lines[j].lstrip().startswith("|"):
            # `\|` inside a cell is a literal pipe, which regexes need.
            raw = lines[j].strip().strip("|").replace("\\|", "\x00")
            cells = [c.strip().replace("\x00", "|") for c in raw.split("|")]
            cells += [""] * (len(header) - len(cells))
            row = {h: cells[k] for k, h in enumerate(header)}
            row = {k: (strip_md(v) if k != "detect" else v.strip().strip("`").strip()) for k, v in row.items()}
            row["_line"] = j + 1
            rows.append(row)
            j += 1
        return rows
    return None


def compile_rule(row):
    """Return (rule fields, problem)."""
    det = row["detect"].strip()
    m = re.match(r"^regex:\s*(.+)$", det)
    if m:
        try:
            return {"kind": "pattern", "rx": re.compile(m.group(1)), "valid": None, "whole": False}, None
        except re.error as e:
            return None, f"regex does not compile: {e}"
    m = re.match(r"^([A-Za-z-]+)(?::(\d+))?$", det)
    if not m:
        return None, f"Detect `{det}` is not a built-in, a heuristic:N, or regex: ..."
    name, n = m.group(1).lower(), m.group(2)
    if name in BUILTIN:
        rx, _, valid, whole = BUILTIN[name]
        return {"kind": "pattern", "rx": re.compile(rx), "valid": valid, "whole": whole}, None
    if name in HEURISTICS:
        rx, _, valid = HEURISTICS[name]
        return {"kind": "count", "rx": re.compile(rx), "valid": valid, "n": int(n or DEFAULT_THRESHOLD)}, None
    return None, f"Detect `{det}` is not a known detector"


def load_rules(root):
    """Return (rules, registry path, problems). No registry means no rules and no problems."""
    path = os.path.join(root, REGISTRY)
    try:
        with open(path, "rb") as f:
            text = f.read(MAX_BYTES).decode("utf-8", "replace")
    except OSError:
        return [], path, []
    rows = parse_table(text)
    if rows is None:
        return [], path, [f"{REGISTRY} has no table with Class, Detect and Action columns"]
    rules, problems = [], []
    for r in rows:
        fields, problem = compile_rule(r)
        where = f"line {r['_line']} `{r['class'] or '?'}`"
        if problem:
            problems.append(f"{where}: {problem}")
            continue
        action = r["action"].lower()
        if action not in ("block", "warn"):
            problems.append(f"{where}: Action `{r['action']}` must be block or warn")
            continue
        if not r["class"]:
            problems.append(f"{where}: empty Class")
        fields.update({"class": r["class"], "detect": r["detect"], "action": action,
                       "instead": r.get("instead", ""), "notes": r.get("notes", ""), "line": r["_line"]})
        rules.append(fields)
    return rules, path, problems


# ---------- scanning ----------

def redact(s):
    s = s.strip()
    return s[:4] + "…" + s[-2:] if len(s) > 8 else "…"


def hit(rule, where, sample):
    return {"class": rule["class"], "action": rule["action"], "instead": rule["instead"],
            "where": where, "sample": sample}


def pattern_hits(text, rule, name):
    hits, lines = [], text.splitlines()
    if rule.get("whole"):
        seen = set()
        for m in rule["rx"].finditer(text):
            ln = text.count("\n", 0, m.start()) + 1
            if ln in seen or (ln <= len(lines) and OK_MARKER in lines[ln - 1]):
                continue
            if rule["valid"] and not rule["valid"](m):
                continue
            seen.add(ln)
            hits.append(hit(rule, f"{name}:{ln}", redact(m.group(0).split("\n")[0].split("\\n")[0])))
        return hits
    for ln, line in enumerate(lines, 1):
        if OK_MARKER in line:
            continue
        for m in rule["rx"].finditer(line):
            if rule["valid"] and not rule["valid"](m):
                continue
            hits.append(hit(rule, f"{name}:{ln}", redact(m.group(0))))
            break  # one hit per line per rule is enough
    return hits


def distinct(text, rule):
    found = set()
    for line in text.splitlines():
        if OK_MARKER in line:
            continue
        for m in rule["rx"].finditer(line):
            if rule["valid"] and not rule["valid"](m):
                continue
            v = m.group(0)
            found.add(v.lower() if "@" in v else re.sub(r"\D", "", v))
    return len(found)


def scan_text(text, rules, name="<text>"):
    """Return list of hits: dict(class, action, instead, where, sample)."""
    hits = []
    for rule in rules:
        if rule["kind"] == "pattern":
            hits += pattern_hits(text, rule, name)
        else:
            n = distinct(text, rule)
            if n >= rule["n"]:
                hits.append(hit(rule, name, f"{n} distinct, threshold {rule['n']}"))
    return hits


def is_binary(b):
    return b"\x00" in b[:8192]


def read_text(path):
    """File contents as text; '' if missing; None if unreadable, binary or over the size limit."""
    try:
        with open(path, "rb") as f:
            b = f.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return ""
    except OSError:
        return None
    if len(b) > MAX_BYTES or is_binary(b):
        return None
    return b.decode("utf-8", errors="replace")


def report(hits):
    for h in hits:
        line = f"[{h['action']}] {h['class']} at {h['where']}: {h['sample']}"
        if h["instead"]:
            line += f"\n         instead: {h['instead']}"
        print(line)


# ---------- hook ----------

def text_field(d, key):
    v = d.get(key) if isinstance(d, dict) else None
    return v if isinstance(v, str) else ""


def edits_of(tool, ti):
    if tool == "Edit":
        return [ti]
    if tool == "MultiEdit":
        edits = ti.get("edits")
        return [e for e in edits if isinstance(e, dict)] if isinstance(edits, list) else []
    return []


def written_text(tool, ti):
    """The text this tool call puts into the file."""
    if tool == "Write":
        return text_field(ti, "content")
    if tool == "NotebookEdit":
        return text_field(ti, "new_source")
    return "\n".join(text_field(e, "new_string") for e in edits_of(tool, ti))


def after_text(tool, ti, before):
    """The whole file as it will be after the call, as near as can be told."""
    if tool == "Write":
        return text_field(ti, "content")
    if tool in ("Edit", "MultiEdit"):
        text = before
        for e in edits_of(tool, ti):
            old, new = text_field(e, "old_string"), text_field(e, "new_string")
            if old and old in text:
                text = text.replace(old, new) if e.get("replace_all") is True else text.replace(old, new, 1)
            else:
                text += "\n" + new
        return text
    return before + "\n" + written_text(tool, ti)


def hook(payload):
    if not isinstance(payload, dict) or payload.get("hook_event_name") != "PreToolUse":
        return 0
    tool = payload.get("tool_name")
    ti = payload.get("tool_input")
    if tool not in ("Write", "Edit", "MultiEdit", "NotebookEdit") or not isinstance(ti, dict):
        return 0
    target = text_field(ti, "file_path") or text_field(ti, "notebook_path")
    if not target:
        return 0
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) and payload.get("cwd") else os.getcwd()
    target = os.path.abspath(os.path.join(cwd, os.path.expanduser(target)))
    root = repo_root(target)
    if not root or is_registry(target, root):
        return 0
    rules, _, _ = load_rules(root)
    if not rules:
        return 0
    new = written_text(tool, ti)
    if not new or len(new) > MAX_BYTES:
        return 0
    rel = os.path.relpath(os.path.realpath(target), root)

    hits = [h for r in rules if r["kind"] == "pattern" for h in pattern_hits(new, r, rel)]
    counts = [r for r in rules if r["kind"] == "count"]
    if counts:
        before = read_text(target)
        after = after_text(tool, ti, before) if before is not None else new
        before = before or ""
        for r in counts:
            n_after = distinct(after, r)
            # Ask when this write takes the file across the threshold, not on every
            # later edit of a file that was already over it. `scan` reports those.
            if n_after >= r["n"] and distinct(before, r) < r["n"]:
                hits.append(hit(r, rel, f"{n_after} distinct, threshold {r['n']}"))
    if not hits:
        return 0

    blocks = [h for h in hits if h["action"] == "block"]
    chosen = blocks or hits
    parts = []
    for h in chosen[:5]:
        p = f"{h['class']} ({h['sample']})"
        if h["instead"]:
            p += f" — belongs in: {h['instead']}"
        parts.append(p)
    reason = f"forbidden: this write to {rel} contains " + "; ".join(parts) + ". "
    reason += ("The repo must not hold this. Put it where the rule says and reference it from here."
               if blocks else
               "This is a heuristic, so it may be fine; the user decides.")
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny" if blocks else "ask",
        "permissionDecisionReason": reason}}))
    return 0


def run_hook():
    try:
        raw = sys.stdin.buffer.read(MAX_BYTES * 4)
        payload = json.loads(raw.decode("utf-8", "replace"))
    except (ValueError, OSError):
        return 0
    try:
        return hook(payload)
    except Exception as e:  # a broken guard must never break the session
        print(f"forbidden: hook error, write not checked: {e}", file=sys.stderr)
        return 0


# ---------- CLI ----------

def iter_files(paths):
    for p in paths:
        p = os.path.abspath(p)
        if os.path.isdir(p):
            for dp, dns, fns in os.walk(p):
                dns[:] = [d for d in dns if d != ".git"]
                for fn in sorted(fns):
                    yield os.path.join(dp, fn)
        elif os.path.exists(p):
            yield p
        else:
            print(f"forbidden: no such path: {p}", file=sys.stderr)


def display(path):
    rel = os.path.relpath(path)
    return path if rel.startswith("..") else rel


def cmd_scan(paths):
    here = repo_root() or os.path.realpath(os.getcwd())
    cache, hits, with_rules = {}, [], 0
    for f in iter_files(paths or ["."]):
        root = repo_root(f) or here
        if root not in cache:
            rules, path, problems = load_rules(root)
            for p in problems:
                print(f"problem in {path}: {p}", file=sys.stderr)
            if not rules and not problems:
                print(f"forbidden: no {REGISTRY} at {root}; nothing to check there. Run /forbidden:init.", file=sys.stderr)
            cache[root] = rules
        if is_registry(f, root) or not cache[root]:
            continue
        with_rules += 1
        text = read_text(f)
        if text:
            hits += scan_text(text, cache[root], display(f))
    report(hits)
    blocks = sum(1 for h in hits if h["action"] == "block")
    print(f"{len(hits)} finding(s), {blocks} blocking")
    return 1 if blocks else 0


def cmd_staged():
    root = repo_root()
    if not root:
        print("forbidden: not inside a git repository; nothing staged to check.", file=sys.stderr)
        return 0
    rules, _, _ = load_rules(root)
    if not rules:
        return 0
    out = sh(["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"], root) or ""
    hits = []
    for rel in [n for n in out.split("\0") if n]:
        if rel == REGISTRY:
            continue
        try:
            blob = subprocess.run(["git", "show", f":{rel}"], cwd=root, capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if blob.returncode != 0 or len(blob.stdout) > MAX_BYTES or is_binary(blob.stdout):
            continue
        hits += scan_text(blob.stdout.decode("utf-8", errors="replace"), rules, rel)
    report(hits)
    blocks = [h for h in hits if h["action"] == "block"]
    if blocks:
        print(f"forbidden: commit refused, {len(blocks)} blocking finding(s).", file=sys.stderr)
        return 1
    return 0


def cmd_patterns():
    print(f"built-in detectors, {len(BUILTIN)} (Action should be block):")
    for k, v in BUILTIN.items():
        print(f"  {k:22} {v[1]}")
    print(f"heuristics, with a threshold N as name:N, default {DEFAULT_THRESHOLD} (Action should be warn):")
    for k, v in HEURISTICS.items():
        print(f"  {k:22} {v[1]}")
    print("custom: regex: <python regular expression>, matched line by line")
    return 0


def cmd_check():
    root = repo_root() or os.path.realpath(os.getcwd())
    rules, path, problems = load_rules(root)
    if not os.path.exists(path):
        print(f"{path} not found. Run /forbidden:init, or `forbidden.py init`.")
        return 1
    for r in rules:
        if r["kind"] == "count" and r["action"] == "block":
            problems.append(f"line {r['line']} `{r['class']}`: a heuristic should warn, not block, or it will cry wolf")
        if not r["instead"]:
            problems.append(f"line {r['line']} `{r['class']}`: Instead is empty — say where it belongs")
    if problems:
        print(f"{path}: {len(problems)} problem(s)")
        for p in problems:
            print("  " + p)
        return 1
    print(f"{path}: {len(rules)} rules, no problems")
    return 0


def cmd_init():
    root = repo_root()
    if not root:
        print("forbidden: not inside a git repository. The hook only reads a FORBIDDEN.md at a repository's root; run init from inside one.")
        return 1
    p = os.path.join(root, REGISTRY)
    if os.path.exists(p):
        print(f"{p} already exists; not touching it.")
        return 0
    tpl = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "FORBIDDEN.template.md")
    with open(tpl, encoding="utf-8") as f, open(p, "w", encoding="utf-8") as out:
        out.write(f.read())
    print(f"wrote {p} from the template. Fill in the Instead column for your company, then run check.")
    return 0


def main(argv):
    if not argv:
        if sys.stdin is None or sys.stdin.isatty():
            print(__doc__)
            return 2
        return run_hook()
    cmd, args = argv[0], argv[1:]
    if cmd == "scan" and args and args[0] in ("--staged", "--check", "--patterns"):
        cmd, args = args[0][2:], args[1:]
    if cmd == "scan":
        return cmd_scan(args)
    if cmd == "staged":
        return cmd_staged()
    if cmd == "patterns":
        return cmd_patterns()
    if cmd == "check":
        return cmd_check()
    if cmd == "init":
        return cmd_init()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
