#!/usr/bin/env python3
"""Keep a talk's leave-behind and mainstage in sync.

    python3 sync.py path/to/deck.json                 check, and say how many notes are stale
    python3 sync.py path/to/deck.json --write-notes   also regenerate the mainstage speaker notes
    python3 sync.py path/to/deck.json --json          machine-readable report

deck.json names the two HTML files, relative to itself:
    {"title": "…", "leave_behind": "talk.html", "mainstage": "talk-mainstage.html", "overrides": {}}

The HTML contract:
  - slides are <section> elements that are direct children of <slide-deck> or <deck-stage>
  - a slide's label is its data-label
  - speaker notes are <script type="application/json" id="speaker-notes">[ "…", … ]</script>
  - text inside data-deck-ignore, script, style and template is not slide text

Checks (settings from decks_config): slide count, label order, labels position by position,
words per mainstage slide, graphics per mainstage slide. Notes: each mainstage note becomes
"SAY THIS — the leave-behind slide, word for word:" plus that slide's text, and keeps
everything from a "— — —" line onward, which is the human-written part. Only the JSON
inside the speaker-notes tag is rewritten; the rest of the file is left byte for byte.
"""
import argparse, json, re, sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decks_config import load, describe, get, two_versions

DECK_TAGS = ("slide-deck", "deck-stage")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol", "section", "header", "footer",
         "figure", "figcaption", "td", "th", "tr", "table", "pre", "blockquote", "article", "aside", "nav", "main", "dl", "dt", "dd"}
SKIP_TAGS = {"script", "style", "template", "noscript"}
GRAPHIC_TAGS = {"img", "svg", "picture"}
NOTES_HEADER = "SAY THIS — the leave-behind slide, word for word:\n"
SEPARATOR = "— — —"
NOTES_PLACEHOLDER_TAIL = SEPARATOR + "\nTEN SECONDS: [write this]\n\n[delivery note]"
WORD = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)
NOTES_TAG = re.compile(r'(<script\b[^>]*\bid\s*=\s*["\']speaker-notes["\'][^>]*>)(.*?)(</script\s*>)', re.S | re.I)

# ── a small tree ────────────────────────────────────────────────────────────
class Node:
    __slots__ = ("tag", "attrs", "children", "parent")
    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.children, self.parent = tag, dict(attrs or {}), [], parent
    def elements(self):
        return [c for c in self.children if isinstance(c, Node)]

class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root"); self.stack = [self.root]
    def handle_starttag(self, tag, attrs):
        n = Node(tag, [(k, v if v is not None else "") for k, v in attrs], self.stack[-1])
        self.stack[-1].children.append(n)
        if tag not in VOID: self.stack.append(n)
    def handle_startendtag(self, tag, attrs):
        n = Node(tag, [(k, v if v is not None else "") for k, v in attrs], self.stack[-1])
        self.stack[-1].children.append(n)
    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]; return
    def handle_data(self, data):
        self.stack[-1].children.append(data)

def parse(html):
    b = TreeBuilder(); b.feed(html); b.close(); return b.root

def walk(node):
    for c in node.children:
        if isinstance(c, Node):
            yield c
            yield from walk(c)

def slides(root):
    """[(label, section node)] from the first <slide-deck> or <deck-stage>."""
    deck = next((n for n in walk(root) if n.tag in DECK_TAGS), None)
    if deck is None: return []
    return [(s.attrs.get("data-label", ""), s) for s in deck.elements() if s.tag == "section"]

# ── selectors ───────────────────────────────────────────────────────────────
_SEL_PART = re.compile(r"""\.([\w-]+)|\[\s*([\w:-]+)\s*(?:=\s*(?:"([^"]*)"|'([^']*)'|([^\]\s]*))\s*)?\]""")

def parse_selector(sel):
    """`tag`, `.class`, `[attr]`, `[attr=value]` (value optionally quoted), and compounds such as
    `div.ph[data-x=1]`. No combinators. Returns (tag or None, [classes], [(attr, value or None)])."""
    s = sel.strip()
    m = re.match(r"[a-zA-Z][\w-]*", s)
    tag = m.group(0).lower() if m else None
    pos = m.end() if m else 0
    classes, attrs = [], []
    while pos < len(s):
        pm = _SEL_PART.match(s, pos)
        if not pm: raise ValueError(f"unsupported selector: {sel!r}")
        if pm.group(1): classes.append(pm.group(1))
        else:
            val = next((g for g in (pm.group(3), pm.group(4), pm.group(5)) if g is not None), None)
            if val is None and "=" in pm.group(0): val = ""
            attrs.append((pm.group(2).lower(), val))
        pos = pm.end()
    if tag is None and not classes and not attrs: raise ValueError(f"empty selector: {sel!r}")
    return tag, classes, attrs

def matches(node, sel):
    tag, classes, attrs = parse_selector(sel) if isinstance(sel, str) else sel
    if tag and node.tag != tag: return False
    if classes:
        have = set((node.attrs.get("class") or "").split())
        if not all(c in have for c in classes): return False
    for a, v in attrs:
        if a not in node.attrs: return False
        if v is not None and node.attrs[a] != v: return False
    return True

def any_match(node, parsed):
    return any(matches(node, p) for p in parsed)

# ── text, words, graphics ───────────────────────────────────────────────────
def slide_lines(section, skip=None):
    """One line per block-level element, whitespace collapsed, empties dropped."""
    lines, buf = [], []
    def flush():
        t = " ".join("".join(buf).split())
        if t: lines.append(t)
        buf.clear()
    def go(n):
        for c in n.children:
            if not isinstance(c, Node):
                buf.append(c); continue
            if c.tag in SKIP_TAGS or "data-deck-ignore" in c.attrs: continue
            if skip and skip(c): continue
            if c.tag == "br": flush(); continue
            block = c.tag in BLOCK
            if block: flush()
            go(c)
            if block: flush()
    go(section); flush()
    return lines

def word_count(section, cfg):
    placeholders = [parse_selector(s) for s in (get(cfg, "mainstage.placeholder_selectors") or [])]
    exempt = [parse_selector(s) for s in (get(cfg, "mainstage.exempt_selectors") or [])] if get(cfg, "mainstage.label_exemption") else []
    skip = lambda n: any_match(n, placeholders) or any_match(n, exempt)
    lines = slide_lines(section, skip)
    return sum(len(WORD.findall(l)) for l in lines), lines

def graphic_count(section, cfg):
    placeholders = [parse_selector(s) for s in (get(cfg, "mainstage.placeholder_selectors") or [])]
    count = 0
    def go(n):
        nonlocal count
        for c in n.elements():
            if c.tag in SKIP_TAGS: continue
            if c.tag in GRAPHIC_TAGS or any_match(c, placeholders):
                count += 1; continue
            go(c)
    go(section)
    return count

# ── notes ───────────────────────────────────────────────────────────────────
def read_notes(raw):
    m = NOTES_TAG.search(raw)
    if not m: return None, None
    body = m.group(2).strip()
    try:
        notes = json.loads(body) if body else []
    except json.JSONDecodeError as e:
        raise SystemExit(f"deck-builder: speaker-notes JSON is invalid: {e}")
    if not isinstance(notes, list): raise SystemExit("deck-builder: speaker-notes must be a JSON array")
    return notes, m

def new_note(lb_lines, old):
    block = NOTES_HEADER + "\n".join(lb_lines)
    old_lines = (old or "").split("\n")
    idx = next((i for i, l in enumerate(old_lines) if l.strip() == SEPARATOR), None)
    if idx is None:
        return block + "\n\n" + NOTES_PLACEHOLDER_TAIL
    return block + "\n\n" + "\n".join(old_lines[idx:])

def format_notes(notes, original_body):
    enc = lambda s: json.dumps(s, ensure_ascii=False).replace("</", "<\\/")
    if re.match(r"\s*\[\s*\n", original_body) or not original_body.strip():
        inner = ",\n".join("  " + enc(s) for s in notes)
        return "[\n" + inner + "\n]"
    return "[" + ", ".join(enc(s) for s in notes) + "]"

def write_notes(raw, m, notes):
    body = m.group(2)
    lead = re.match(r"\s*", body).group(0)
    trail = body[len(body.rstrip()):]
    new_body = lead + format_notes(notes, body) + trail
    return raw[:m.start(2)] + new_body + raw[m.end(2):]

# ── the run ─────────────────────────────────────────────────────────────────
def read(path):
    with open(path, encoding="utf-8", newline="") as f: return f.read()

def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f: f.write(text)

def run(deck_json, write_notes_flag=False):
    cfg = load(deck_json)
    report = {"settings": describe(cfg), "slides": {}, "problems": [], "notes_changed": 0, "notes_written": False, "message": None}
    if not two_versions(cfg):
        report["message"] = "one version configured; nothing to sync"
        return report, cfg
    here = Path(cfg["_dir"]); deck = cfg["_deck"]
    paths = {}
    for key in ("leave_behind", "mainstage"):
        if not deck.get(key): raise SystemExit(f"deck-builder: deck.json has no {key!r}")
        p = here / deck[key]
        if not p.is_file(): raise SystemExit(f"deck-builder: {key} file not found: {p}")
        paths[key] = p
    lb_raw, ms_raw = read(paths["leave_behind"]), read(paths["mainstage"])
    lb, ms = slides(parse(lb_raw)), slides(parse(ms_raw))
    report["slides"] = {"leave_behind": len(lb), "mainstage": len(ms)}
    probs = report["problems"]
    add = lambda slide, kind, detail: probs.append({"slide": slide, "kind": kind, "detail": detail})
    checks = get(cfg, "sync.check") or []

    if not lb: add(None, "count", f"no slides found in {paths['leave_behind'].name} (need <section> children of <slide-deck> or <deck-stage>)")
    if not ms: add(None, "count", f"no slides found in {paths['mainstage'].name} (need <section> children of <slide-deck> or <deck-stage>)")

    if "count" in checks and len(lb) != len(ms):
        add(None, "count", f"leave-behind has {len(lb)} slides, mainstage has {len(ms)}")
    la, lm = [l for l, _ in lb], [l for l, _ in ms]
    if "order" in checks:
        common = set(la) & set(lm) - {""}
        seq_a = [l for l in la if l in common]; seq_b = [l for l in lm if l in common]
        if seq_a != seq_b:
            k = next(i for i, (a, b) in enumerate(zip(seq_a, seq_b)) if a != b)
            add(k + 1, "order", f"labels in both versions run in a different order, first at the {k + 1}th shared label: leave-behind {seq_a[k]!r}, mainstage {seq_b[k]!r}")
    if "labels" in checks:
        for i in range(min(len(la), len(lm))):
            if la[i] != lm[i]:
                add(i + 1, "labels", f"leave-behind {la[i]!r} vs mainstage {lm[i]!r}")

    mw = get(cfg, "mainstage.max_words")
    gl = get(cfg, "mainstage.graphics_per_slide")
    for i, (label, sec) in enumerate(ms):
        if mw is not None:
            n, lines = word_count(sec, cfg)
            if n > mw:
                add(i + 1, "words", f"{label!r}: {n} words (limit {mw}): \"{' / '.join(lines)[:70]}\"")
        if gl is not None:
            g = graphic_count(sec, cfg)
            if g > gl:
                add(i + 1, "graphics", f"{label!r}: {g} graphics (limit {gl})")

    if get(cfg, "sync.notes") == "leave-behind-verbatim":
        notes, m = read_notes(ms_raw)
        if m is None:
            add(None, "notes", f"{paths['mainstage'].name} has no <script type=\"application/json\" id=\"speaker-notes\">")
        else:
            updated = list(notes)
            for i in range(len(ms)):
                if i >= len(lb): break
                old = notes[i] if i < len(notes) else ""
                nn = new_note(slide_lines(lb[i][1]), old)
                if i < len(updated): updated[i] = nn
                else: updated.append(nn)
            report["notes_changed"] = sum(1 for i, s in enumerate(updated) if i >= len(notes) or notes[i] != s)
            if write_notes_flag and report["notes_changed"]:
                write(paths["mainstage"], write_notes(ms_raw, m, updated))
                report["notes_written"] = True
    elif write_notes_flag:
        report["message"] = f"sync.notes is {get(cfg, 'sync.notes')!r}; notes left alone"
    return report, cfg

def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("deck_json")
    a.add_argument("--write-notes", action="store_true")
    a.add_argument("--json", action="store_true")
    args = a.parse_args(argv)
    report, cfg = run(args.deck_json, args.write_notes)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1 if report["problems"] else 0
    print(report["settings"])
    if report["message"] and not report["slides"]:
        print(report["message"]); return 0
    for p in report["problems"]:
        where = f"slide {p['slide']} · " if p["slide"] else ""
        print(f"  {where}{p['kind']}: {p['detail']}")
    if report["message"]: print(report["message"])
    n = report["notes_changed"]
    if n:
        total = report["slides"].get("mainstage", 0)
        print(f"notes: wrote {n} of {total}" if report["notes_written"]
              else f"notes: {n} of {total} mainstage notes would change (run with --write-notes)")
    if report["problems"]:
        print(f"{len(report['problems'])} problems"); return 1
    print(f"ok: {report['slides'].get('mainstage', 0)} slides in sync"); return 0

if __name__ == "__main__":
    sys.exit(main())
