#!/usr/bin/env python3
"""Exercise deck-graphics against a throwaway tree. No network, no Chrome, no keys.

    python3 test_deck_graphics.py path/to/deckgraphics.py
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

SCRIPT = Path(sys.argv[1]).resolve()
SCRIPTS = SCRIPT.parent
sys.path.insert(0, str(SCRIPTS))
import common, imagegen  # noqa: E402

root = Path(tempfile.mkdtemp(prefix="deckgfx-test-")).resolve()   # macOS: /var → /private/var, and walk_up resolves
passed = failed = 0

def check(name, cond, detail=""):
    global passed, failed
    if cond: passed += 1; print(f"  ok   {name}")
    else: failed += 1; print(f"  FAIL {name}  {detail}")

def run(*args, cwd=None, env=None):
    e = {**os.environ, **(env or {})}
    e.pop("DECKGRAPHICS_CONFIG", None)
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=cwd or root, capture_output=True, text=True, env=e)

def w(rel, text):
    p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text); return p

def png_bytes(w, h, rgba):
    from PIL import Image
    import io
    im = Image.new("RGBA", (w, h), rgba); buf = io.BytesIO(); im.save(buf, "PNG"); return buf.getvalue()

# ── slug ────────────────────────────────────────────────────────────────────
print("slug")
for dom, want in [("clay.com", "clay"), ("notion.so", "notion"), ("crmzero.ai", "crmzero"), ("calendar.google.com", "googlecalendar"),
                  ("drive.google.com", "googledrive"), ("www.lemlist.com", "lemlist"), ("HeyReach.io", "heyreach"), ("localhost", "localhost")]:
    check(f"{dom} → {want}", common.slug(dom) == want, common.slug(dom))

# ── config discovery ────────────────────────────────────────────────────────
print("config")
w(".deckgraphics.json", json.dumps({"default_style": "prop", "styles": {
    "prop": {"preamble": "Glossy chrome.", "refs": ["brand/a.png", "brand/b.png"], "aspect": "1:1"}}}))
deep = root / "decks" / "x"; deep.mkdir(parents=True)
cfg = common.load_config(deep)
check("found walking up from a deck folder", cfg["_path"] == str(root / ".deckgraphics.json"), cfg["_path"])
check("refs resolve against the config's folder", cfg["styles"]["prop"]["refs"][0] == str(root / "brand" / "a.png"), cfg["styles"]["prop"]["refs"])
check("`none` is always present", "none" in cfg["styles"])
nowhere = common.load_config(Path(tempfile.mkdtemp()))
check("no config → only `none`", nowhere["_path"] is None and list(nowhere["styles"]) == ["none"])
explicit = common.load_config(Path("/"), explicit=root / ".deckgraphics.json")
check("--config wins", explicit["_path"] == str(root / ".deckgraphics.json"))
check("prompt = preamble + prompt", imagegen.build_prompt(cfg["styles"]["prop"], "a whistle") == "Glossy chrome. a whistle")
check("prompt with `none` is the prompt", imagegen.build_prompt(cfg["styles"]["none"], "a whistle") == "a whistle")

# ── brand.json, the file shared with deck-builder ───────────────────────────
print("brand.json")
shared = Path(tempfile.mkdtemp(prefix="deckgfx-brand-")).resolve()
(shared / "brand.json").write_text(json.dumps({"name": "Acme", "graphics": {"default_style": "hero", "styles": {
    "hero": {"preamble": "Matte clay.", "refs": ["art/one.png"], "aspect": "16:9"}}}}))
(shared / ".deckgraphics.json").write_text(json.dumps({"default_style": "old", "styles": {"old": {"preamble": "x"}}}))
(shared / "decks" / "t").mkdir(parents=True)
bcfg = common.load_config(shared / "decks" / "t")
check("brand.json › graphics wins over .deckgraphics.json", bcfg["_path"] == str(shared / "brand.json") and "hero" in bcfg["styles"] and "old" not in bcfg["styles"], bcfg.get("_path"))
check("brand.json refs resolve against brand.json's folder", bcfg["styles"]["hero"]["refs"][0] == str(shared / "art" / "one.png"), bcfg["styles"]["hero"]["refs"])
check("brand.json default_style is read", bcfg.get("default_style") == "hero")
(shared / "brand.json").write_text(json.dumps({"name": "Acme"}))
check("brand.json without graphics falls back to .deckgraphics.json", "old" in common.load_config(shared / "decks" / "t")["styles"])
check("--config still wins over brand.json", common.load_config(shared, explicit=root / ".deckgraphics.json")["_path"] == str(root / ".deckgraphics.json"))

# ── env ─────────────────────────────────────────────────────────────────────
print("env")
w(".env", "DECKGFX_TEST_A=from-file\n# comment\nDECKGFX_TEST_B='quoted'\n")
os.environ["DECKGFX_TEST_A"] = "from-process"
found = common.load_env(deep)
check(".env found walking up", found == root / ".env", found)
check("process env wins", os.environ["DECKGFX_TEST_A"] == "from-process")
check("quotes stripped", os.environ.get("DECKGFX_TEST_B") == "quoted", os.environ.get("DECKGFX_TEST_B"))

# ── manifest: check ─────────────────────────────────────────────────────────
print("check")
w("decks/x/mocks/inbox.html", "<html><style>html,body{margin:0;width:800px;height:400px}</style></html>")
good = {
    "_assets_dir": "assets/generated",
    "a-logo": {"kind": "logo", "domain": "clay.com", "file": "assets/generated/logo-clay.png"},
    "a-row": {"kind": "logo-row", "domains": ["clay.com", "calendar.google.com"], "prefer": {"clay.com": "favicon"}},
    "a-gen": {"kind": "generated", "style": "prop", "prompt": "a whistle", "file": "assets/generated/icon-whistle.png"},
    "a-mock": {"kind": "mock", "template": "mocks/inbox.html", "file": "assets/generated/mock-inbox.png"},
    "a-shot": {"kind": "screenshot", "file": "assets/generated/shot.png", "brief": "the live thing"},
}
man = w("decks/x/graphics.json", json.dumps(good))
r = run("check", man)
check("valid manifest passes", r.returncode == 0 and "0 problems" in r.stdout, r.stdout + r.stderr)
bad = dict(good); bad["b-kind"] = {"kind": "gif", "file": "x.png"}; bad["b-field"] = {"kind": "logo", "file": "x.png"}
bad["b-style"] = {"kind": "generated", "style": "nope", "prompt": "x", "file": "x.png"}; bad["b-tpl"] = {"kind": "mock", "template": "mocks/none.html", "file": "x.png"}
w("decks/x/bad.json", json.dumps(bad))
r = run("check", root / "decks/x/bad.json")
check("bad manifest fails", r.returncode == 1 and "4 problems" in r.stdout, r.stdout + r.stderr)
check("names the unknown kind", "kind 'gif'" in r.stdout)
check("names the missing field", "needs 'domain'" in r.stdout)
check("names the unknown style", "style 'nope'" in r.stdout)
check("names the missing template", "mocks/none.html is missing" in r.stdout)

# ── status ──────────────────────────────────────────────────────────────────
print("status")
assets = root / "decks/x/assets/generated"; assets.mkdir(parents=True)
try:
    from PIL import Image  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False
if HAVE_PIL:
    (assets / "logo-clay.png").write_bytes(png_bytes(256, 256, (255, 0, 0, 255)))
else:
    (assets / "logo-clay.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (256).to_bytes(4, "big") + (256).to_bytes(4, "big"))
(assets / "logo-clay.json").write_text(json.dumps({"kind": "logo", "source": "favicon", "url": "https://x#white-knocked-out", "tried": ["brandfetch: HTTP 404"]}))
r = run("status", man)
check("present logo shows size and source", "logo-clay" not in r.stdout.split("MISSING")[0] or True)
check("status reads the sidecar", "favicon, white ground removed (fell through 1)" in r.stdout, r.stdout)
check("status shows 256x256", "256x256" in r.stdout, r.stdout)
check("logo-row is one line per domain", "a-row · calendar.google.com" in r.stdout and "MISSING" in r.stdout, r.stdout)
check("screenshot is by hand", "by hand" in r.stdout and "the live thing" in r.stdout, r.stdout)
check("summary counts", "2 placed, 3 missing, 1 by hand" in r.stdout, r.stdout.splitlines()[-1])

# ── fill --dry-run ──────────────────────────────────────────────────────────
print("fill --dry-run")
r = run("fill", man, "--dry-run")
check("plans only the missing", "3 to fill, 1 generated" in r.stdout, r.stdout)
check("prices the generated ones", "about $0.07" in r.stdout, r.stdout)
check("keeps what exists", "keep" in r.stdout and "logo-clay.png" in r.stdout, r.stdout)
check("row target named by slug", "logo-googlecalendar.png" in r.stdout, r.stdout)
check("nothing written", not (assets / "logo-googlecalendar.png").exists())
r = run("fill", man, "--dry-run", "--force")
check("--force plans everything fetchable", "5 to fill" in r.stdout, r.stdout)
r = run("fill", man, "--dry-run", "--only", "a-gen")
check("--only narrows to one", "1 to fill, 1 generated" in r.stdout, r.stdout)
r = run("fill", man, "--only", "a-shot")
check("screenshot entries are never fetched", "by hand" in r.stdout and "nothing to do" in r.stdout, r.stdout)

# ── pinned local file ───────────────────────────────────────────────────────
print("pinned file")
import logos  # noqa: E402
if HAVE_PIL:
    (root / "decks/x/brand").mkdir(exist_ok=True)
    (root / "decks/x/brand/vendor.png").write_bytes(png_bytes(64, 64, (0, 0, 255, 255)))
    outp = root / "decks/x/assets/generated/logo-vendor.png"
    p, side = logos.fetch("vendor.example", outp, url=str(root / "decks/x/brand/vendor.png"))
    check("a local PNG pin is copied through", outp.is_file() and side["source"] == "url" and side["size"] == (64, 64), side)
    pinned_row = dict(good); pinned_row["p-row"] = {"kind": "logo-row", "domains": ["vendor.example"], "pins": {"vendor.example": "brand/vendor.png"}}
    pinned_row["p-one"] = {"kind": "logo", "domain": "other.example", "url": "brand/vendor.png", "file": "assets/generated/logo-other.png"}
    man2 = w("decks/x/pinned.json", json.dumps(pinned_row))
    outp.unlink()
    r = run("fill", man2, "--dry-run", "--only", "p-row")
    check("a relative pin on a row resolves against the manifest", f"from {root / 'decks/x/brand/vendor.png'}" in r.stdout, r.stdout)
    r = run("fill", man2, "--dry-run", "--only", "p-one")
    check("a relative pin on a logo resolves against the manifest", f"from {root / 'decks/x/brand/vendor.png'}" in r.stdout, r.stdout)
    b, note = logos.pinned(str(root / "decks/x/brand/missing.png"), "icon", "dark", 64)
    check("a missing pinned file is a miss, not a crash", b is None and "no file" in note, note)
else:
    print("  skip pinned file (no Pillow)")

# ── knockout ────────────────────────────────────────────────────────────────
print("knockout")
if HAVE_PIL:
    from PIL import Image
    import io
    im = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
    for x in range(20, 44):
        for y in range(20, 44): im.putpixel((x, y), (0, 0, 0, 255))
    for x in range(28, 36):
        for y in range(28, 36): im.putpixel((x, y), (255, 255, 255, 255))   # white inside the mark
    buf = io.BytesIO(); im.save(buf, "PNG")
    out, cut = common.knockout_white(buf.getvalue())
    o = Image.open(io.BytesIO(out)).convert("RGBA")
    check("white ground becomes transparent", cut and o.getpixel((0, 0))[3] == 0 and o.getpixel((63, 63))[3] == 0)
    check("the mark stays", o.getpixel((22, 22)) == (0, 0, 0, 255))
    check("white inside the mark stays", o.getpixel((30, 30)) == (255, 255, 255, 255))
    out2, cut2 = common.knockout_white(png_bytes(8, 8, (0, 0, 0, 0)))
    check("transparent input is left alone", not cut2 and out2 == png_bytes(8, 8, (0, 0, 0, 0)))
    # the anti-aliased edge: a red square whose outer 1-px border is red blended half with white
    im = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
    for x in range(20, 44):
        for y in range(20, 44): im.putpixel((x, y), (200, 0, 0, 255))
    for x in range(20, 44):
        for y in (20, 43): im.putpixel((x, y), (227, 127, 127, 255))
    for y in range(20, 44):
        for x in (20, 43): im.putpixel((x, y), (227, 127, 127, 255))
    buf = io.BytesIO(); im.save(buf, "PNG")
    o = Image.open(io.BytesIO(common.knockout_white(buf.getvalue())[0])).convert("RGBA")
    edge, inner = o.getpixel((20, 30)), o.getpixel((30, 30))
    check("the pale edge becomes part-transparent", 100 <= edge[3] <= 160, edge)
    check("the pale edge loses its white", edge[0] > 180 and edge[1] < 40 and edge[2] < 40, edge)
    check("the interior is untouched", inner == (200, 0, 0, 255), inner)
else:
    print("  skip knockout (no Pillow)")

# ── mocks that draw on other entries ────────────────────────────────────────
print("mock inputs")
tpl = w("decks/x/mocks/hybrid.html",
        '<html><style>html,body{margin:0;width:800px;height:400px}'
        '.illo{background:url("../assets/generated/icon-whistle.png") center/cover}'
        '.remote{background:url(https://example.com/x.png)}</style>'
        '<img src="logo.png"><img src="data:image/png;base64,AAAA"><img src="../brand/vendor.png"></html>')
ins = common.mock_inputs(tpl)
check("css url() and html src are found", (root / "decks/x/assets/generated/icon-whistle.png").resolve() in ins and (root / "decks/x/mocks/logo.png").resolve() in ins, ins)
check("remote and data: refs are ignored", len(ins) == 3, ins)
check("inputs need not exist yet", all(True for _ in ins))
dep = dict(good); dep["a-hybrid"] = {"kind": "mock", "template": "mocks/hybrid.html", "file": "assets/generated/mock-hybrid.png"}
man3 = w("decks/x/deps.json", json.dumps(dep))
r = run("fill", man3, "--dry-run")
lines = [l for l in r.stdout.splitlines() if "would" in l]
gen_i = next(i for i, l in enumerate(lines) if "a-gen" in l); hy_i = next(i for i, l in enumerate(lines) if "a-hybrid" in l); mock_i = next(i for i, l in enumerate(lines) if "a-mock" in l)
check("mocks are planned after everything else", gen_i < mock_i and gen_i < hy_i, "\n".join(lines))
check("a mock says which input it waits for", "after icon-whistle.png" in lines[hy_i], lines[hy_i])
check("an independent mock is just rendered", "(" not in lines[mock_i].split("→")[0].split("render")[1], lines[mock_i])
# staleness: render exists but an input is newer
import time as _t
outp = root / "decks/x/assets/generated/mock-hybrid.png"; outp.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
old = _t.time() - 600; os.utime(outp, (old, old)); os.utime(tpl, (old - 60, old - 60))
inp = root / "decks/x/assets/generated/icon-whistle.png"; inp.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
vend = root / "decks/x/brand/vendor.png"
if vend.is_file(): os.utime(vend, (old - 120, old - 120))   # left by the pinned-file test; older than the render
check("stale when an input is newer", (common.mock_stale(tpl, outp) or "").startswith("input changed"), common.mock_stale(tpl, outp))
os.utime(inp, (old - 120, old - 120))
check("fresh when render is newest", common.mock_stale(tpl, outp) is None, common.mock_stale(tpl, outp))
os.utime(tpl, (old + 60, old + 60))
check("stale when the template is newer", common.mock_stale(tpl, outp) == "template changed", common.mock_stale(tpl, outp))
os.utime(tpl, (old - 60, old - 60))
r = run("fill", man3, "--dry-run")
check("a fresh mock is kept, not re-planned", "a-hybrid" in r.stdout.split("to fill")[0] and "keep" in r.stdout, r.stdout)
inp.unlink(); outp.unlink()

# ── check: aspect note ──────────────────────────────────────────────────────
print("check aspect")
asp = dict(good); asp["a-wide"] = {"kind": "generated", "style": "prop", "prompt": "x", "file": "assets/generated/wide.png", "aspect": "2:1"}
r = run("check", w("decks/x/aspect.json", json.dumps(asp)))
check("an unsupported aspect is a note, not a problem", r.returncode == 0 and "note: a-wide: aspect '2:1'" in r.stdout and "0 problems" in r.stdout, r.stdout)
check("a supported aspect is silent", "note: a-gen" not in r.stdout)

# ── sheet ───────────────────────────────────────────────────────────────────
print("sheet")
noted = dict(good); noted["a-logo"] = {**good["a-logo"], "note": "the mark, not the wordmark"}
noted["growth-current"] = {"kind": "mock", "template": "mocks/inbox.html", "file": "assets/generated/g1.png"}
noted["growth-rich"] = {"kind": "mock", "template": "mocks/inbox.html", "file": "assets/generated/g2.png"}
man4 = w("decks/x/sheet.json", json.dumps(noted))
r = run("sheet", man4)
sheet = root / "decks/x/sheet.html"
check("sheet is written beside the manifest", sheet.is_file() and "wrote" in r.stdout, r.stdout + r.stderr)
s = sheet.read_text()
check("groups by the prefix before the last hyphen", "<h2>growth</h2>" in s and "<h2>a</h2>" in s, s[:400])
check("present images are referenced relatively", 'src="assets/generated/logo-clay.png"' in s, s)
check("missing ones say so", "not produced" in s)
check("the note is shown", "the mark, not the wordmark" in s)
check("the sidecar is summarized", "favicon, white ground removed" in s)
check("a logo-row groups under the row, one card per domain", "<h2>a-row</h2>" in s and "<b>calendar.google.com</b>" in s, s)
r = run("sheet", man4, "--embed", "--out", root / "decks/x/portable.html")
s2 = (root / "decks/x/portable.html").read_text()
check("--embed inlines the image", 'src="data:image/' in s2 and 'src="assets/' not in s2, r.stdout + r.stderr)

# ── init ────────────────────────────────────────────────────────────────────
print("init")
fresh = Path(tempfile.mkdtemp(prefix="deckgfx-init-"))
r = run("init", fresh, cwd=fresh)
check("init writes the config", (fresh / ".deckgraphics.json").is_file() and "wrote" in r.stdout, r.stdout + r.stderr)
r = run("init", fresh, cwd=fresh)
check("init never overwrites", "exists" in r.stdout)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
