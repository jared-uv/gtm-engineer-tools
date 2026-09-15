#!/usr/bin/env python3
"""Shared by the deck-graphics scripts: config discovery, .env loading, Chrome, slugs,
image-header checks and the white knockout. Standard library only; Pillow is optional
and the two places that want it say so when it is missing."""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

CONFIG_NAME = ".deckgraphics.json"
ENV_NAME = ".env"
NONE_STYLE = {"preamble": "", "refs": [], "aspect": "1:1"}

# ── discovery ───────────────────────────────────────────────────────────────
def walk_up(start):
    p = Path(start).resolve()
    if p.is_file(): p = p.parent
    yield p
    yield from p.parents

def find_config(start=None, explicit=None):
    """--config, then $DECKGRAPHICS_CONFIG, then the first .deckgraphics.json walking up from
    `start` (the manifest's folder, or the cwd). None when there is none."""
    if explicit: return Path(explicit)
    if os.environ.get("DECKGRAPHICS_CONFIG"): return Path(os.environ["DECKGRAPHICS_CONFIG"])
    for d in walk_up(start or Path.cwd()):
        if (d / CONFIG_NAME).is_file(): return d / CONFIG_NAME
    return None

def find_brand(start=None):
    for d in walk_up(start or Path.cwd()):
        if (d / "brand.json").is_file(): return d / "brand.json"
    return None

def load_config(start=None, explicit=None):
    """The config with style ref paths resolved against the config file's folder, and a
    `none` style always present. Without a config file you get `none` and nothing else.

    Where it comes from, first match wins: --config or $DECKGRAPHICS_CONFIG; the `graphics`
    section of the first brand.json walking up (the one brand file shared with deck-builder);
    the first .deckgraphics.json walking up (the older standalone file)."""
    path = None
    if not explicit and not os.environ.get("DECKGRAPHICS_CONFIG"):
        brand = find_brand(start)
        if brand:
            section = json.loads(brand.read_text()).get("graphics")
            if isinstance(section, dict):
                cfg = dict(section); path = brand
    if path is None:
        path = find_config(start, explicit)
        if not path or not path.is_file():
            return {"_path": None, "styles": {"none": dict(NONE_STYLE)}}
        cfg = json.loads(path.read_text())
    cfg.setdefault("styles", {})
    for name, st in cfg["styles"].items():
        st.setdefault("preamble", ""); st.setdefault("aspect", "1:1")
        st["refs"] = [str((path.parent / r).resolve()) for r in st.get("refs", [])]
    cfg["styles"].setdefault("none", dict(NONE_STYLE))
    cfg["_path"] = str(path)
    return cfg

def load_env(start=None):
    """Process env wins; the first .env found walking up from `start` fills the gaps.
    Walking up is what makes a git worktree under .claude/worktrees/ find the main
    checkout's .env, which is gitignored and only ever exists there. Never logs values."""
    for d in walk_up(start or Path.cwd()):
        p = d / ENV_NAME
        if not p.is_file(): continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        return p
    return None

def key(name, tool="deck-graphics"):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"{tool}: {name} is not set. Put it in a .env above the manifest (gitignored), or export it.")
    return v

# ── mock inputs ─────────────────────────────────────────────────────────────
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif")

def mock_inputs(template):
    """The local images a mock template draws on: url("…") in its CSS and src="…" in its HTML,
    resolved against the template's folder. Remote URLs and data: URIs are ignored. A mock that
    embeds another entry's output (an illustration under real labels, say) depends on it: the
    mock renders after that entry, and goes stale when the input is newer than the render."""
    import re
    t = Path(template)
    text = t.read_text(errors="replace")
    refs = [m[1] for m in re.findall(r'''url\((["']?)([^"')]+)\1\)''', text)]
    refs += re.findall(r'''src=["']([^"']+)["']''', text)
    out = []
    for ref in refs:
        ref = ref.strip()
        if not ref or "://" in ref or ref.startswith("data:") or not ref.lower().endswith(IMG_EXT): continue
        p = (t.parent / ref).resolve()
        if p not in out: out.append(p)
    return out

def mock_stale(template, out):
    """Why a rendered mock needs re-rendering, or None: missing, template newer, or an input newer."""
    template, out = Path(template), Path(out)
    if not out.is_file(): return "missing"
    t = out.stat().st_mtime
    if template.stat().st_mtime > t: return "template changed"
    for p in mock_inputs(template):
        if p.is_file() and p.stat().st_mtime > t: return f"input changed: {p.name}"
    return None

# ── chrome ──────────────────────────────────────────────────────────────────
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
]

def chrome_path(cfg=None):
    """$DECKGRAPHICS_CHROME, then "chrome" in the config, then the usual places."""
    for c in [os.environ.get("DECKGRAPHICS_CHROME"), (cfg or {}).get("chrome"), *CHROME_CANDIDATES]:
        if not c: continue
        if Path(c).is_file(): return c
        w = shutil.which(c)
        if w: return w
    sys.exit("deck-graphics: no Chrome found. Set DECKGRAPHICS_CHROME or \"chrome\" in .deckgraphics.json.")

def chrome_screenshot(chrome, target, out, w, h, transparent=False, wait=45):
    """Headless Chrome → PNG of `target` (a file or URL) at w×h. Watches for the file rather
    than waiting for Chrome to exit: Chrome writes the screenshot in a few seconds and a
    helper process can then hold stdout open until any timeout you set. Nothing is captured."""
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True); out.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as prof:
        args = [chrome, "--headless", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                f"--user-data-dir={prof}", "--no-first-run", "--no-default-browser-check",
                f"--window-size={w},{h}", f"--screenshot={out}", str(target)]
        if transparent: args.insert(4, "--default-background-color=00000000")
        p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(wait * 2):
            if (out.is_file() and out.stat().st_size > 0) or p.poll() is not None: break
            time.sleep(0.5)
        time.sleep(0.5)
        if p.poll() is None:
            p.terminate()
            try: p.wait(5)
            except subprocess.TimeoutExpired: p.kill()
    return out.read_bytes() if out.is_file() and out.stat().st_size else b""

# ── names ───────────────────────────────────────────────────────────────────
def slug(domain):
    """A filename stem for a domain: drop the TLD and a leading www, then join the labels
    innermost-last. calendar.google.com → googlecalendar, notion.so → notion, crmzero.ai → crmzero."""
    labels = domain.lower().strip().split(".")
    if len(labels) > 1: labels = labels[:-1]
    if labels and labels[0] == "www": labels = labels[1:]
    return "".join(reversed(labels))

# ── image bytes ─────────────────────────────────────────────────────────────
def is_png(b): return b[:8] == b"\x89PNG\r\n\x1a\n"
def is_jpeg(b): return b[:3] == b"\xff\xd8\xff"
def is_webp(b): return b[:4] == b"RIFF" and b[8:12] == b"WEBP"
def is_svg(b): return b.lstrip()[:5].lower() in (b"<svg ", b"<?xml") or b"<svg" in b[:300].lower()
def png_size(b): return (int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")) if is_png(b) else None
def png_size_of(path):
    try: return png_size(Path(path).read_bytes()[:24])
    except OSError: return None

def knockout_white(png_bytes, thresh=24):
    """Make an opaque white ground transparent: flood-fill from each near-white corner.
    Only the connected background goes — white inside the mark stays. Needs Pillow;
    returns the bytes unchanged (and False) when it isn't importable or nothing was white."""
    try:
        import io
        from PIL import Image, ImageDraw
    except ImportError:
        return png_bytes, False
    im = Image.open(io.BytesIO(png_bytes)).convert("RGBA"); w, h = im.size
    done = False
    for xy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        r, g, b_, a = im.getpixel(xy)
        if a > 0 and min(r, g, b_) >= 255 - thresh:
            ImageDraw.floodfill(im, xy, (0, 0, 0, 0), thresh=thresh); done = True
    if not done: return png_bytes, False
    defringe(im)
    buf = io.BytesIO(); im.save(buf, "PNG"); return buf.getvalue(), True

def defringe(im, ring=2):
    """After a white knockout the anti-aliased edge is still there: pixels that were the mark
    blended with white, now sitting against a dark slide as a pale halo. For the opaque
    pixels within `ring` px of the transparent ground, read the whiteness as missing
    coverage — a pixel that is mostly white is mostly background — turn it into alpha, and
    un-blend the color so what's left is the mark's color, not the mark's color plus white.
    Only the ring is touched; the interior of a pale mark is left alone."""
    from PIL import ImageFilter
    a = im.getchannel("A")
    near = a.filter(ImageFilter.MinFilter(2 * ring + 1))   # 0 where any pixel within `ring` is transparent
    px, ap, npx = im.load(), a.load(), near.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            if ap[x, y] == 0 or npx[x, y] != 0: continue
            r, g, b, _ = px[x, y]
            cov = 1.0 - min(r, g, b) / 255.0          # how much of this pixel is the mark
            if cov >= 0.98: continue
            if cov <= 0.05: px[x, y] = (0, 0, 0, 0); continue
            un = lambda c: max(0, min(255, int(round((c - 255 * (1 - cov)) / cov))))
            px[x, y] = (un(r), un(g), un(b), int(round(255 * cov)))
