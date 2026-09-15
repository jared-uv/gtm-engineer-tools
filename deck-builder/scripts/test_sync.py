#!/usr/bin/env python3
"""Exercise decks_config.py and sync.py against throwaway decks. No network, no browser.

    python3 test_sync.py
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import decks_config as dc  # noqa: E402
import sync  # noqa: E402

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond: passed += 1; print(f"  ok   {name}")
    else: failed += 1; print(f"  FAIL {name}  {detail}")

def tmp():
    return Path(tempfile.mkdtemp(prefix="deckbuilder-test-")).resolve()

def section(label, body):
    return f'  <section data-label="{label}">{body}</section>\n'

def deck_html(slides_html, notes=None, tag="deck-stage"):
    notes_part = ""
    if notes is not None:
        notes_part = ('<script type="application/json" id="speaker-notes">\n[\n'
                      + ",\n".join("  " + json.dumps(n, ensure_ascii=False) for n in notes) + "\n]\n</script>\n")
    return ("<!doctype html>\n<html><head><style>.glow{text-shadow:0 0 8px pink}</style></head>\n<body>\n"
            f"<{tag} width=\"1920\" height=\"1080\">\n{''.join(slides_html)}</{tag}>\n\n{notes_part}"
            "<script src=\"deck-stage.js\"></script>\n</body>\n</html>\n")

def make_deck(d, lb, ms, overrides=None, brand=None):
    (d / "lb.html").write_text(lb); (d / "ms.html").write_text(ms)
    (d / "deck.json").write_text(json.dumps({"title": "T", "leave_behind": "lb.html", "mainstage": "ms.html", "overrides": overrides or {}}))
    if brand is not None: (d / "brand.json").write_text(json.dumps(brand))
    return d / "deck.json"

def run_cli(*args):
    r = subprocess.run([sys.executable, str(HERE / "sync.py"), *map(str, args)], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr

def kinds(report):
    return [p["kind"] for p in report["problems"]]

DEFAULT_LINE = ("building with: two versions (leave-behind + mainstage), ≤5 words a mainstage slide, ≤2 graphics, "
                "sync checks count/order/labels, notes from the leave-behind, exports pdf + pptx (editable, ask on unfaithful slides) "
                "— change in brand.json › decks or deck.json › overrides")

LB = [section("Title", '<div class="eyebrow">A talk</div><h1>FOUR MONTHS CHANGED GTM</h1><p>A longer line of leave-behind copy.</p>'),
      section("Stack", "<h2>FIVE LAYERS</h2><ul><li>Surfaces</li><li>Loops</li></ul>"),
      section("Close", "<h1>MODEL RENTED. CONTEXT YOURS.</h1>")]
MS = [section("Title", "<h1>FOUR MONTHS.</h1>"),
      section("Stack", "<h2>FIVE LAYERS</h2>"),
      section("Close", "<h1>CONTEXT: YOURS.</h1>")]

# ── config ──────────────────────────────────────────────────────────────────
print("config")
d = tmp()
p = make_deck(d, deck_html(LB), deck_html(MS, ["x", "y", "z"]))
cfg = dc.load(p)
check("defaults load", cfg["mainstage"]["max_words"] == 5 and cfg["sync"]["check"] == ["count", "order", "labels"])
check("describe() states the defaults exactly", dc.describe(cfg) == DEFAULT_LINE, dc.describe(cfg))
check("_sources without a brand", cfg["_sources"] == ["defaults", str(p)], cfg["_sources"])

d = tmp(); (d / "talks" / "one").mkdir(parents=True)
(d / "brand.json").write_text(json.dumps({"colors": {"ink": "#000"}, "decks": {"mainstage": {"max_words": 7}}}))
p = make_deck(d / "talks" / "one", deck_html(LB), deck_html(MS), overrides={"mainstage": {"graphics_per_slide": None}, "sync": {"check": []}})
cfg = dc.load(p)
check("brand.json found walking up", dc.find_brand(d / "talks" / "one") == d / "brand.json")
check("brand layer merges", cfg["mainstage"]["max_words"] == 7)
check("deep merge keeps untouched siblings", cfg["mainstage"]["label_exemption"] is True)
check("null in overrides survives as switched off", "graphics_per_slide" in cfg["mainstage"] and cfg["mainstage"]["graphics_per_slide"] is None)
check("[] in overrides survives", cfg["sync"]["check"] == [])

# per-version settings and per-version slide choices
d2 = tmp(); pv = make_deck(d2, deck_html(LB), deck_html(MS))
data = json.loads(pv.read_text())
data["version_overrides"] = {"leave-behind": {"pptx": {"mode": "pictures"}}}
pv.write_text(json.dumps(data))
check("version_overrides apply to their version", dc.load(pv, "leave-behind")["pptx"]["mode"] == "pictures")
check("and not to the other version", dc.load(pv, "mainstage")["pptx"]["mode"] == "editable")
check("and not when no version is given", dc.load(pv)["pptx"]["mode"] == "editable")
check("a mainstage settings group in overrides is still settings, not a version", dc.load(p)["mainstage"]["graphics_per_slide"] is None)
flat = {"slides": {"_why": "x", "1": "picture", "7": "glow-behind"}}
check("flat slide choices apply to every version", dc.slides_for(flat, "mainstage") == dc.slides_for(flat, "leave-behind") == {"1": "picture", "7": "glow-behind"})
split = {"slides": {"_why": "x", "mainstage": {"7": "glow-behind", "_why": "y"}}}
check("per-version slide choices apply to their version", dc.slides_for(split, "mainstage") == {"7": "glow-behind"})
check("a version with no map of its own has none", dc.slides_for(split, "leave-behind") == {})
check("no slides at all is empty", dc.slides_for({}, "mainstage") == {})
check("_sources lists brand and deck", cfg["_sources"] == ["defaults", str(d / "brand.json"), str(p)], cfg["_sources"])
line = dc.describe(cfg)
check("describe() reflects brand value", "≤7 words" in line, line)
check("describe() says switched-off graphics", "no graphics limit" in line, line)
check("describe() says no sync checks", "no sync checks" in line, line)
cfg["mainstage"]["max_words"] = None
check("describe() says no word limit", "no word limit" in dc.describe(cfg))
cfg2 = dict(cfg, versions=["single"])
check("describe() says one version", dc.describe(cfg2).startswith("building with: one version,"), dc.describe(cfg2))
cfg3 = dict(dc.DEFAULTS, pptx={"mode": "pictures"})
check("describe() says pictures", "pptx (pictures)" in dc.describe(cfg3), dc.describe(cfg3))

d = tmp()
dest = dc.init_deck_json(d, "My talk", "talk.html", "talk-mainstage.html")
data = json.loads(dest.read_text())
check("init writes empty overrides", data["overrides"] == {})
check("init snapshots settings in effect", data["_settings_in_effect"]["mainstage"]["max_words"] == 5)
try:
    dc.init_deck_json(d, "x", "a", "b"); check("init never overwrites", False)
except FileExistsError:
    check("init never overwrites", True)
(d / "talk.html").write_text(deck_html(LB)); (d / "talk-mainstage.html").write_text(deck_html(MS))
cfg = dc.load(dest)
check("loader ignores _settings_in_effect", "_settings_in_effect" not in cfg and "_about" not in cfg)
check("DESCRIPTIONS cover every default", all(k in dc.DESCRIPTIONS for k in dc.DEFAULTS)
      and all(kk in dc.DESCRIPTIONS[k] for k, v in dc.DEFAULTS.items() if isinstance(v, dict) for kk in v))

# ── extraction ──────────────────────────────────────────────────────────────
print("extraction")
for tag in ("slide-deck", "deck-stage"):
    s = sync.slides(sync.parse(deck_html(LB, tag=tag)))
    check(f"slides from <{tag}>", [l for l, _ in s] == ["Title", "Stack", "Close"], [l for l, _ in s])
nested = "<slide-deck><div><section data-label='x'>hi</section></div></slide-deck>"
check("only direct children are slides", sync.slides(sync.parse(nested)) == [])
check("no deck element → no slides", sync.slides(sync.parse("<section>hi</section>")) == [])
sec = sync.slides(sync.parse(deck_html([section("A",
    '<div class="eyebrow">Eyebrow</div><h1>BIG <span class="accent">WORDS</span></h1>'
    '<p>one<br>two</p><script>var x = 1;</script><style>.a{}</style><template>tpl</template>'
    '<div data-deck-ignore>hidden</div><p>  spaced\n   out  &amp; done </p>')])))[0][1]
lines = sync.slide_lines(sec)
check("one line per block, br breaks, inline joins", lines == ["Eyebrow", "BIG WORDS", "one", "two", "spaced out & done"], lines)
check("missing data-label is empty", sync.slides(sync.parse("<deck-stage><section>x</section></deck-stage>"))[0][0] == "")

# ── selectors ───────────────────────────────────────────────────────────────
print("selectors")
n = sync.Node("div", {"class": "ph ico x", "data-placeholder": "", "data-words": "exempt"})
for sel, want in [("div", True), ("span", False), (".ph", True), (".ph.ico", True), (".nope", False),
                  ("[data-placeholder]", True), ("[data-missing]", False), ("[data-words=exempt]", True),
                  ('[data-words="exempt"]', True), ("[data-words='exempt']", True), ("[data-words=other]", False),
                  ("div.ph", True), ("span.ph", False), ("div.ph[data-words=exempt]", True)]:
    check(f"selector {sel} → {want}", sync.matches(n, sel) is want)
try:
    sync.parse_selector("div > .ph"); check("combinators are rejected", False)
except ValueError:
    check("combinators are rejected", True)

# ── checks ──────────────────────────────────────────────────────────────────
print("checks")
d = tmp(); p = make_deck(d, deck_html(LB), deck_html(MS, ["", "", ""]))
rep, _ = sync.run(p)
check("in-sync pair has no problems", rep["problems"] == [], rep["problems"])
code, out = run_cli(p)
check("CLI: first line is describe()", out.splitlines()[0] == DEFAULT_LINE, out.splitlines()[0])
check("CLI: ok summary, exit 0", code == 0 and "ok: 3 slides in sync" in out, out)

d = tmp(); p = make_deck(d, deck_html(LB), deck_html(MS[:2], ["", ""]))
rep, _ = sync.run(p)
check("count fires", "count" in kinds(rep), rep["problems"])
code, out = run_cli(p)
check("CLI: problems exit 1", code == 1 and "problems" in out.splitlines()[-1], out)

d = tmp(); p = make_deck(d, deck_html(LB), deck_html([MS[0], section("Layers", "<h2>FIVE</h2>"), MS[2]], ["", "", ""]))
rep, _ = sync.run(p)
check("labels fires on a renamed slide", [x for x in rep["problems"] if x["kind"] == "labels" and x["slide"] == 2], rep["problems"])
check("order does not fire on a rename", "order" not in kinds(rep), rep["problems"])

d = tmp(); p = make_deck(d, deck_html(LB), deck_html([MS[1], MS[0], MS[2]], ["", "", ""]))
rep, _ = sync.run(p)
check("order fires on swapped slides", "order" in kinds(rep), rep["problems"])
rep2, _ = sync.run(make_deck(tmp(), deck_html(LB), deck_html([MS[1], MS[0], MS[2]], ["", "", ""]), overrides={"sync": {"check": ["count"]}}))
check("checks limited to sync.check", kinds(rep2) == [], rep2["problems"])

wordy = [section("Title", "<h1>ONE TWO THREE FOUR FIVE SIX</h1>"), MS[1], MS[2]]
d = tmp(); p = make_deck(d, deck_html(LB), deck_html(wordy, ["", "", ""]))
rep, _ = sync.run(p)
check("words fires over the limit", [x for x in rep["problems"] if x["kind"] == "words" and x["slide"] == 1], rep["problems"])
labels = [section("Title", '<h1>FOUR MONTHS.</h1><div data-words="exempt">SURFACES LOOPS JUDGMENT REACH CONTEXT</div>'), MS[1], MS[2]]
rep, _ = sync.run(make_deck(tmp(), deck_html(LB), deck_html(labels, ["", "", ""])))
check("exempt labels don't count", "words" not in kinds(rep), rep["problems"])
rep, _ = sync.run(make_deck(tmp(), deck_html(LB), deck_html(labels, ["", "", ""]), overrides={"mainstage": {"label_exemption": False}}))
check("label_exemption false counts them", "words" in kinds(rep), rep["problems"])
brief = [section("Title", '<h1>FOUR MONTHS.</h1><div data-placeholder>Icon: a t-shirt cannon mid fire over a crowd</div>'), MS[1], MS[2]]
rep, _ = sync.run(make_deck(tmp(), deck_html(LB), deck_html(brief, ["", "", ""]), overrides={"mainstage": {"label_exemption": False}}))
check("placeholder briefs never count as words", "words" not in kinds(rep), rep["problems"])
rep, _ = sync.run(make_deck(tmp(), deck_html(LB), deck_html(wordy, ["", "", ""]), overrides={"mainstage": {"max_words": None}}))
check("max_words null stops the check", "words" not in kinds(rep), rep["problems"])
check("contractions and hyphens are one word", len(sync.WORD.findall("I'M NOT a two-version deck")) == 5)

busy = [section("Title", '<h1>HI</h1><img src="a.png"><picture><img src="b.png"></picture><div data-placeholder>brief</div>'), MS[1], MS[2]]
rep, _ = sync.run(make_deck(tmp(), deck_html(LB), deck_html(busy, ["", "", ""])))
g = [x for x in rep["problems"] if x["kind"] == "graphics"]
check("graphics fires, picture counted once", g and "3 graphics" in g[0]["detail"], rep["problems"])
rep, _ = sync.run(make_deck(tmp(), deck_html(LB), deck_html(busy, ["", "", ""]), overrides={"mainstage": {"graphics_per_slide": None}}))
check("graphics_per_slide null stops the check", "graphics" not in kinds(rep), rep["problems"])

d = tmp(); p = make_deck(d, deck_html(LB), deck_html(MS[:1], ["x"]), overrides={"versions": ["single"]})
rep, _ = sync.run(p)
check("single version short-circuits", rep["message"] == "one version configured; nothing to sync" and rep["problems"] == [])
code, out = run_cli(p)
check("CLI: single version exits 0", code == 0 and "nothing to sync" in out, out)

d = tmp(); p = make_deck(d, deck_html(LB), deck_html(MS))
rep, _ = sync.run(p)
check("missing speaker-notes is a notes problem", "notes" in kinds(rep), rep["problems"])

# ── notes ───────────────────────────────────────────────────────────────────
print("notes")
human = "— — —\nTEN SECONDS: Four months changed the job.\n\nDelivery (60s). Slow down on the second line."
old_notes = ["SAY THIS — the leave-behind slide, word for word:\nstale copy\n\n" + human, "no separator here", ""]
d = tmp(); ms_html = deck_html(MS, old_notes); p = make_deck(d, deck_html(LB), ms_html)
before = (d / "ms.html").read_bytes()
rep, _ = sync.run(p)
check("dry run counts changes", rep["notes_changed"] == 3, rep["notes_changed"])
check("dry run writes nothing", (d / "ms.html").read_bytes() == before)
code, out = run_cli(p)
check("CLI dry run says would change", "3 of 3 mainstage notes would change" in out, out)
rep, _ = sync.run(p, write_notes_flag=True)
after_raw = (d / "ms.html").read_text()
notes, m = sync.read_notes(after_raw)
check("notes written", rep["notes_written"] and len(notes) == 3)
check("slide text replaces the stale block", notes[0].startswith(sync.NOTES_HEADER + "A talk\nFOUR MONTHS CHANGED GTM\nA longer line"), notes[0][:120])
check("human part after — — — kept exactly", notes[0].endswith("\n\n" + human), notes[0][-120:])
check("no separator → placeholder tail", notes[1].endswith("\n\n" + sync.NOTES_PLACEHOLDER_TAIL) and notes[1].startswith(sync.NOTES_HEADER + "FIVE LAYERS\nSurfaces\nLoops"), notes[1])
check("empty note → placeholder tail", notes[2].endswith(sync.NOTES_PLACEHOLDER_TAIL))
b0, a0 = before.decode(), after_raw
mb, ma = sync.NOTES_TAG.search(b0), sync.NOTES_TAG.search(a0)
check("bytes before the notes body unchanged", b0[:mb.start(2)] == a0[:ma.start(2)])
check("bytes after the notes body unchanged", b0[mb.end(2):] == a0[ma.end(2):])
check("one-string-per-line format kept", ma.group(2).startswith("\n[\n  \"") and ma.group(2).endswith("\n]\n"), repr(ma.group(2)[:20]))
rep, _ = sync.run(p, write_notes_flag=True)
check("second write is a no-op", rep["notes_changed"] == 0 and not rep["notes_written"])
tricky = [section("Title", "<h1>A &lt;/script&gt; \"quoted\" ünïcode</h1>"), MS[1], MS[2]]
d = tmp(); p = make_deck(d, deck_html(tricky), deck_html(MS, ["", "", ""]))
sync.run(p, write_notes_flag=True)
raw = (d / "ms.html").read_text()
notes, _ = sync.read_notes(raw)
check("</script> in slide text can't close the tag", notes is not None and "</script>" in notes[0] and raw.count("</script>") == 2, raw[-300:])
check("unicode written unescaped", "ünïcode" in raw)
d = tmp(); p = make_deck(d, deck_html(LB), deck_html(MS, old_notes), overrides={"sync": {"notes": "manual"}})
before = (d / "ms.html").read_bytes()
rep, _ = sync.run(p, write_notes_flag=True)
check("sync.notes manual leaves notes alone", (d / "ms.html").read_bytes() == before and "left alone" in (rep["message"] or ""))
code, out = run_cli(p, "--json")
check("--json is valid JSON with the contract keys", code == 0 and set(json.loads(out)) >= {"slides", "problems", "notes_changed"}, out[:200])

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
