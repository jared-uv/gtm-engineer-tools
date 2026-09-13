#!/usr/bin/env python3
"""Fetch a company logo for a slide, trying sources from best to worst until one works.

    python3 logos.py clay.com --out assets/generated/logo-clay.png
    python3 logos.py slack.com --type icon --theme dark --size 512 --out assets/generated/logo-slack.png
    python3 logos.py calendar.google.com --url https://…/Google_Calendar_icon.svg --out …

Sources, in order:

  url          only with --url: a source you chose, for when the chain gets a mark wrong.
  brandfetch   real logos — light/dark variants, icon vs wordmark. Needs the free client ID
               in BRANDFETCH_CLIENT_ID. https://cdn.brandfetch.io/domain/<d>/…?c=<id>
               Answers in WebP (converted to PNG through Chrome), and "theme/dark" still puts
               some marks on an opaque white square, which is knocked out. Resolves Google
               subdomains to the plain G, and some small vendors only to a wordmark.
  simpleicons  clean monochrome SVGs for household brands, recolored to --color. No key.
               The CDN first, then the pinned npm package on jsDelivr for marks the CDN
               has dropped (OpenAI, Slack). Has no niche tools.
  favicon      Google's favicon service at 256px. Always answers, quality varies. An opaque
               white ground is knocked out (needs Pillow; skipped without it).

Every hit is checked to be a real raster or SVG, SVGs and WebP are rasterized to PNG
through headless Chrome at --size, and the result is written with a sidecar .json naming
the source and what was tried — so the deck records where each logo came from. A miss
falls through instead of failing: the caller gets *something*, and the sidecar says how
good it is. Look at the PNG before trusting it.

Brand marks in a talk are nominative use. Don't recolor a brand's own logo; only the
SimpleIcons tier is recolored, and those are already monochrome by design.
"""
import argparse, base64, json, os, sys, tempfile, urllib.parse, urllib.request, urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (load_config, load_env, chrome_path, chrome_screenshot, knockout_white,
                    is_png, is_svg, is_jpeg, is_webp, png_size)

TOOL = "logos"
_CHROME = {"path": None}

def chrome():
    if not _CHROME["path"]: _CHROME["path"] = chrome_path(load_config())
    return _CHROME["path"]

def get(url, timeout=20):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "deck-graphics/1"}), timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, "", b""
    except Exception:
        return 0, "", b""

def rasterize_svg(svg_bytes, size):
    """SVG → PNG on a transparent ground, centered at `size`."""
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "logo.svg").write_bytes(svg_bytes)
        html = Path(td) / "wrap.html"
        html.write_text('<!doctype html><html><body style="margin:0;background:transparent">'
                        f'<img src="logo.svg" style="width:{size}px;height:{size}px;object-fit:contain;display:block"></body></html>')
        return chrome_screenshot(chrome(), html, Path(td) / "out.png", size, size, transparent=True)

def rasterize_bitmap(img_bytes, mime, size):
    """JPEG/WebP → PNG at `size`, same wrapper as SVGs use."""
    with tempfile.TemporaryDirectory() as td:
        html = Path(td) / "wrap.html"
        html.write_text('<!doctype html><html><body style="margin:0;background:transparent">'
                        f'<img src="data:{mime};base64,{base64.b64encode(img_bytes).decode()}" '
                        f'style="width:{size}px;height:{size}px;object-fit:contain;display:block"></body></html>')
        return chrome_screenshot(chrome(), html, Path(td) / "out.png", size, size, transparent=True)

def to_png(b, size):
    if is_svg(b): return rasterize_svg(b, size)
    if is_webp(b): return rasterize_bitmap(b, "image/webp", size)
    if is_jpeg(b): return rasterize_bitmap(b, "image/jpeg", size)
    return b

def dark_ground(b, url, theme):
    if theme != "dark": return b, url
    b, cut = knockout_white(b)
    return b, (url + "#white-knocked-out" if cut else url)

# ── sources ─────────────────────────────────────────────────────────────────
def pinned(url, kind, theme, size):
    """A URL, or a local file (no scheme): the vendor sent the logo, it lives in the repo."""
    if "://" not in url:
        p = Path(url)
        if not p.is_file(): return None, f"no file at {p}"
        b, ctype = p.read_bytes(), "file"
    else:
        code, ctype, b = get(url)
        if code != 200 or not b: return None, f"HTTP {code}"
    b = to_png(b, size)
    if not is_png(b): return None, f"not an image ({ctype})"
    return dark_ground(b, url, theme)

def brandfetch(domain, kind, theme, size):
    cid = os.environ.get("BRANDFETCH_CLIENT_ID")
    if not cid: return None, "no BRANDFETCH_CLIENT_ID"
    url = f"https://cdn.brandfetch.io/domain/{domain}/w/{size}/h/{size}/theme/{theme}/fallback/404/type/{kind}?c={urllib.parse.quote(cid)}"
    code, ctype, b = get(url)
    if code != 200 or not b: return None, f"HTTP {code}"
    b = to_png(b, size)
    if not is_png(b): return None, f"not an image ({ctype})"
    return dark_ground(b, url.split("?")[0], theme)

SIMPLEICONS_ALIASES = {"gmail.com": "gmail", "notion.so": "notion", "anthropic.com": "anthropic", "claude.ai": "anthropic",
                       "calendar.google.com": "googlecalendar", "drive.google.com": "googledrive", "stripe.com": "stripe",
                       "github.com": "github", "otter.ai": "otter", "linkedin.com": "linkedin", "openai.com": "openai",
                       "huggingface.co": "huggingface"}
SIMPLEICONS_PKG = "https://cdn.jsdelivr.net/npm/simple-icons@15/icons/{slug}.svg"

def simpleicons(domain, kind, theme, size, color):
    slug = SIMPLEICONS_ALIASES.get(domain) or domain.split(".")[0]
    url = f"https://cdn.simpleicons.org/{slug}/{color.lstrip('#')}"
    code, ctype, b = get(url)
    if code != 200 or not is_svg(b):
        # The CDN drops some marks the npm package still ships. The package SVGs carry
        # no fill, so paint one on the root element.
        url = SIMPLEICONS_PKG.format(slug=slug)
        code, ctype, b = get(url)
        if code != 200 or not is_svg(b): return None, f"HTTP {code} for slug {slug} (CDN and package)"
        b = b.replace(b"<svg", f'<svg fill="{color}"'.encode(), 1)
    png = rasterize_svg(b, size)
    return (png if is_png(png) else None), url

def favicon(domain, kind, theme, size):
    url = f"https://www.google.com/s2/favicons?domain={domain}&sz=256"
    code, ctype, b = get(url)
    if code != 200 or not b: return None, f"HTTP {code} ({ctype})"
    b = to_png(b, 256)   # keep native scale; the sidecar will say 256 came from a favicon
    if not is_png(b): return None, f"not a PNG/JPEG ({ctype})"
    return dark_ground(b, url, theme)

SOURCES = [("brandfetch", brandfetch), ("simpleicons", None), ("favicon", favicon)]

# ── entry ───────────────────────────────────────────────────────────────────
def fetch(domain, out, kind="icon", theme="dark", size=512, color="#FFFFFF", prefer=None, url=None):
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    load_env(out.parent)
    tried = []
    order = SOURCES if not prefer else [s for s in SOURCES if s[0] == prefer] + [s for s in SOURCES if s[0] != prefer]
    if url: order = [("url", lambda d, k, t, s: pinned(url, k, t, s))] + list(order)
    for name, fn in order:
        b, note = (simpleicons(domain, kind, theme, size, color) if name == "simpleicons" else fn(domain, kind, theme, size))
        if b:
            out.write_bytes(b)
            side = {"kind": "logo", "domain": domain, "source": name, "url": note, "type": kind, "theme": theme,
                    "size": png_size(b), "recolored": name == "simpleicons", "tried": tried}
            out.with_suffix(".json").write_text(json.dumps(side, indent=2))
            return out, side
        tried.append(f"{name}: {note}")
    sys.exit(f"{TOOL}: nothing found for {domain} — " + "; ".join(tried))

if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("domain"); a.add_argument("--out", required=True)
    a.add_argument("--type", dest="kind", default="icon", choices=["icon", "logo", "symbol"])
    a.add_argument("--theme", default="dark", choices=["dark", "light"])
    a.add_argument("--size", type=int, default=512)
    a.add_argument("--color", default="#FFFFFF", help="SimpleIcons tier only")
    a.add_argument("--prefer", choices=[s[0] for s in SOURCES])
    a.add_argument("--url", help="pin the source: fetch this URL first, fall back to the chain if it fails")
    args = a.parse_args()
    p, side = fetch(args.domain, args.out, args.kind, args.theme, args.size, args.color, args.prefer, args.url)
    w, h = side["size"] or (0, 0)
    print(f"{p}  {w}x{h}  via {side['source']}" + (f"   (fell through: {'; '.join(side['tried'])})" if side["tried"] else ""))
