#!/usr/bin/env python3
"""canonical — where each kind of company information lives.

    canonical.py list            every entry
    canonical.py where <words>   the entry (or entries) matching the words
    canonical.py stale           entries past their review cadence, or never reviewed
    canonical.py check           validate the registry; exit 1 on problems
    canonical.py init            write the template to CANONICAL.md if none exists

Add --json to list / where / stale for machine output. --list, --stale and
--check work as flags too, so `where --stale` is the same as `stale`.

Exit codes: 0 ok; 1 no match, a problem found, or no registry; 2 bad usage.

The registry is CANONICAL.md at the repo root (override: CANONICAL_FILE=path).
It is a markdown table. The first table whose header has both a `Type` and a
`Where` column is the registry; other columns are optional and matched by name:

    | Type | Where | Class | Required | Owner | Cadence | Reviewed | Notes |

Where   an ordered waterfall: look in the first place, then the next, and stop
        when found. Separate places with ` then `. A place is a repo path, a URL,
        or a named external system such as `crm: Accounts, via the CRM connector`.
Class   open      anyone writes; the brand layer
        governed  named owner holds the pen; the canonical layer
        external  a system of record reached through a tool; the deterministic layer
Cadence how often the entry must be re-confirmed: 30d, 6w, 3m, 1y, or - for never.
Reviewed  YYYY-MM-DD of the last confirmation, or - if nobody has.
"""

import datetime as dt
import difflib
import json
import os
import re
import subprocess
import sys

CLASSES = {"open", "governed", "external"}
CADENCE = re.compile(r"^(\d+)\s*([dwmy])$")
UNIT_DAYS = {"d": 1, "w": 7, "m": 30, "y": 365}
SPLIT_WHERE = re.compile(r"\s+then\s+|\s*;\s*")


def repo_root():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return os.getcwd()


def registry_path(root):
    return os.environ.get("CANONICAL_FILE") or os.path.join(root, "CANONICAL.md")


def strip_md(s):
    s = s.strip()
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)  # [text](link) -> text
    return s.strip("`").strip()


def parse(text):
    """Return (rows, problems). Each row is a dict keyed by lowercase header."""
    lines = text.splitlines()
    rows, problems = [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-+", lines[i + 1]):
            header = [strip_md(h).lower() for h in line.strip().strip("|").split("|")]
            if "type" in header and "where" in header:
                i += 2
                while i < len(lines) and lines[i].lstrip().startswith("|"):
                    cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                    if len(cells) < len(header):
                        cells += [""] * (len(header) - len(cells))
                    row = {h: cells[k] for k, h in enumerate(header)}
                    row["_line"] = i + 1
                    row["type"] = strip_md(row.get("type", ""))
                    raw_where = row.get("where", "").strip()
                    row["where_list"] = [strip_md(w) for w in SPLIT_WHERE.split(raw_where) if strip_md(w)]
                    for k in ("class", "required", "owner", "cadence", "reviewed", "notes"):
                        row[k] = strip_md(row.get(k, ""))
                    row["class"] = row["class"].lower()
                    rows.append(row)
                    i += 1
                return rows, problems
        i += 1
    problems.append("no table with both a `Type` and a `Where` column")
    return rows, problems


def load(root):
    path = registry_path(root)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return None, path, ["no registry here. Create one with /canonical:setup, or `canonical.py init`"]
    except IsADirectoryError:
        return None, path, ["is a directory, not a registry file"]
    except UnicodeDecodeError:
        return None, path, ["is not UTF-8 text"]
    except OSError as e:
        return None, path, [f"cannot be read: {e.strerror or e}"]
    rows, problems = parse(text)
    return rows, path, problems


def cadence_days(s):
    m = CADENCE.match(s.strip().lower())
    if not m:
        return None
    return int(m.group(1)) * UNIT_DAYS[m.group(2)]


def parse_date(s):
    try:
        return dt.date.fromisoformat(s.strip())
    except ValueError:
        return None


def staleness(row, today=None):
    """Return (state, detail). state in {ok, stale, never, none}."""
    today = today or dt.date.today()
    days = cadence_days(row["cadence"]) if row["cadence"] not in ("", "-") else None
    if days is None:
        return "none", "no cadence"
    reviewed = parse_date(row["reviewed"]) if row["reviewed"] not in ("", "-") else None
    if reviewed is None:
        return "never", f"never reviewed, cadence {row['cadence']}"
    due = reviewed + dt.timedelta(days=days)
    if due < today:
        return "stale", f"reviewed {reviewed}, due {due}, {(today - due).days}d overdue"
    return "ok", f"reviewed {reviewed}, due {due}"


def looks_like_path(place):
    if "://" in place or re.match(r"^[a-z][a-z0-9+-]*:\s", place):
        return False
    return ("/" in place or "." in place) and " " not in place


def check(rows, root):
    problems = []
    seen = {}
    for r in rows:
        where = f"line {r['_line']} `{r['type'] or '?'}`"
        if not r["type"]:
            problems.append(f"{where}: empty Type")
        if r["type"].lower() in seen:
            problems.append(f"{where}: duplicate of line {seen[r['type'].lower()]}")
        seen[r["type"].lower()] = r["_line"]
        if not r["where_list"]:
            problems.append(f"{where}: empty Where")
        for place in r["where_list"]:
            if looks_like_path(place) and not os.path.exists(os.path.join(root, place)):
                problems.append(f"{where}: `{place}` does not exist")
        if r["class"] and r["class"] not in CLASSES:
            problems.append(f"{where}: Class `{r['class']}` is not one of {sorted(CLASSES)}")
        if r["class"] == "governed" and r["owner"] in ("", "-"):
            problems.append(f"{where}: governed entries need an Owner")
        if r["cadence"] not in ("", "-") and cadence_days(r["cadence"]) is None:
            problems.append(f"{where}: Cadence `{r['cadence']}` should look like 30d, 6w, 3m or 1y")
        if r["reviewed"] not in ("", "-") and parse_date(r["reviewed"]) is None:
            problems.append(f"{where}: Reviewed `{r['reviewed']}` should be YYYY-MM-DD")
    return problems


def fmt_entry(r):
    lines = [f"{r['type']}"]
    for n, place in enumerate(r["where_list"], 1):
        lines.append(f"  {n}. {place}")
    bits = []
    if r["class"]:
        bits.append(r["class"])
    if r["required"]:
        bits.append(f"required: {r['required']}")
    if r["owner"]:
        bits.append(f"owner: {r['owner']}")
    state, detail = staleness(r)
    if state != "none":
        bits.append(f"review every {r['cadence']} ({detail})")
    if bits:
        lines.append("  " + " · ".join(bits))
    if r["notes"]:
        lines.append(f"  {r['notes']}")
    return "\n".join(lines)


def public(r):
    state, detail = staleness(r)
    return {
        "type": r["type"],
        "where": r["where_list"],
        "class": r["class"],
        "required": r["required"],
        "owner": r["owner"],
        "cadence": r["cadence"],
        "reviewed": r["reviewed"],
        "freshness": state,
        "freshness_detail": detail,
        "notes": r["notes"],
        "line": r["_line"],
    }


def find(rows, words):
    q = " ".join(words).lower().strip()
    if not q:
        return rows
    exact = [r for r in rows if r["type"].lower() == q]
    if exact:
        return exact
    terms = q.split()
    # Type first, notes only as a fallback, so "voice" finds Author voice and not
    # every row whose note mentions voice.
    for field in ("type", "notes"):
        hits = [r for r in rows if q in r[field].lower()]
        if hits:
            return hits
        hits = [r for r in rows if all(t in r[field].lower() for t in terms)]
        if hits:
            return hits
    close = difflib.get_close_matches(q, [r["type"].lower() for r in rows], n=3, cutoff=0.75)
    return [r for r in rows if r["type"].lower() in close]


def cmd_init(root):
    path = registry_path(root)
    if os.path.exists(path):
        print(f"{path} already exists; not touching it.")
        return 0
    tpl = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "CANONICAL.template.md")
    try:
        with open(tpl, encoding="utf-8") as f:
            template = f.read()
    except OSError:
        print(f"the plugin's template is missing: {tpl}", file=sys.stderr)
        return 1
    try:
        with open(path, "w", encoding="utf-8") as out:
            out.write(template)
    except OSError as e:
        print(f"cannot write {path}: {e.strerror or e}", file=sys.stderr)
        return 1
    print(f"wrote {path} from the template. Edit it, then run `canonical.py check`.")
    return 0


VERBS = ("list", "where", "stale", "check", "init")
FLAG_VERBS = {"--list": "list", "--stale": "stale", "--check": "check"}


def main(argv):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    flagged = [FLAG_VERBS[a] for a in argv if a in FLAG_VERBS]
    if flagged:
        cmd, argv = flagged[0], [flagged[0]]
    else:
        cmd = argv[0] if argv else "list"
    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if cmd not in VERBS:
        print(f"unknown command `{cmd}`.\n" + __doc__, file=sys.stderr)
        return 2
    root = repo_root()
    if cmd == "init":
        return cmd_init(root)
    rows, path, problems = load(root)
    if rows is None or (problems and cmd != "check"):
        print(f"{path}: " + "; ".join(problems), file=sys.stderr)
        return 1
    if cmd == "check":
        problems += check(rows, root)
        if problems:
            print(f"{path}: {len(problems)} problem(s)")
            for p in problems:
                print("  " + p)
            return 1
        print(f"{path}: {len(rows)} entries, no problems")
        return 0
    if cmd == "list":
        out = rows
    elif cmd == "where":
        out = find(rows, argv[1:])
        if not out:
            msg = f"nothing in {path} matches '{' '.join(argv[1:])}'. Entries: " + ", ".join(r["type"] for r in rows if r["type"])
            if as_json:
                print("[]")
                print(msg, file=sys.stderr)
            else:
                print(msg)
            return 1
    elif cmd == "stale":
        out = [r for r in rows if staleness(r)[0] in ("stale", "never")]
        if not out and not as_json:
            print(f"{path}: nothing stale")
            return 0
    if not out and not as_json:
        print(f"{path}: no entries")
        return 0
    if as_json:
        print(json.dumps([public(r) for r in out], indent=2))
    else:
        print("\n\n".join(fmt_entry(r) for r in out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
