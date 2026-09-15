#!/usr/bin/env python3
"""Shared by the deck-builder scripts: Chrome discovery and the three ways we drive it
(screenshot, dump the DOM, print to PDF), each watched for its output file rather than
waited on, plus brand.json discovery. Standard library only."""
import json, os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
W, H = 1920, 1080

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
]

def walk_up(start):
    p = Path(start).resolve()
    if p.is_file(): p = p.parent
    yield p
    yield from p.parents

def find_brand(start):
    for d in walk_up(start):
        if (d / "brand.json").is_file(): return d / "brand.json"
    return None

def load_brand(start):
    p = find_brand(start)
    if not p: return {"_path": None}
    b = json.loads(p.read_text()); b["_path"] = str(p); b["_dir"] = str(p.parent)
    return b

def chrome_path(brand=None):
    graphics = (brand or {}).get("graphics") or {}
    for c in [os.environ.get("DECKBUILDER_CHROME"), os.environ.get("DECKGRAPHICS_CHROME"), graphics.get("chrome"), *CHROME_CANDIDATES]:
        if not c: continue
        if Path(c).is_file(): return c
        w = shutil.which(c)
        if w: return w
    sys.exit("deck-builder: no Chrome found. Set DECKBUILDER_CHROME, or graphics.chrome in brand.json.")

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]

def _watch(args, done, wait):
    """Start Chrome, poll `done()` until true or `wait` seconds, then stop Chrome.
    Chrome writes its output in a few seconds and a helper process can then hold stdout
    open indefinitely, so nothing is captured and exit is never awaited."""
    with tempfile.TemporaryDirectory() as prof:
        p = subprocess.Popen([args[0], "--headless", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={prof}",
                              "--no-first-run", "--no-default-browser-check", *args[1:]],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ok = False
        for _ in range(int(wait * 4)):
            if done(): ok = True; break
            if p.poll() is not None: ok = done(); break
            time.sleep(0.25)
        time.sleep(0.4)
        if p.poll() is None:
            p.terminate()
            try: p.wait(5)
            except subprocess.TimeoutExpired: p.kill()
        return ok or done()

def screenshot(chrome, url, out, w=W, h=H, transparent=False, budget=4000, wait=45, scale=1):
    """A PNG of the page at w×h CSS pixels; `scale` 2 writes it at twice that, as a 4K screen draws it."""
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True); out.unlink(missing_ok=True)
    args = [chrome, f"--force-device-scale-factor={scale}", f"--window-size={w},{h}", f"--virtual-time-budget={budget}",
            f"--screenshot={out}", url]
    if transparent: args.insert(1, "--default-background-color=00000000")
    ok = _watch(args, lambda: out.is_file() and out.stat().st_size > 0, wait)
    return out if ok else None

def dump_dom(chrome, url, marker, budget=6000, wait=45):
    """Chrome --dump-dom into a temp file; returns the DOM text once `marker` appears."""
    with tempfile.NamedTemporaryFile("w+", suffix=".html", delete=False) as tf: path = Path(tf.name)
    fh = open(path, "w")
    with tempfile.TemporaryDirectory() as prof:
        p = subprocess.Popen([chrome, "--headless", "--disable-gpu", f"--user-data-dir={prof}", "--no-first-run",
                              f"--window-size={W},{H}", f"--virtual-time-budget={budget}", "--dump-dom", url],
                             stdout=fh, stderr=subprocess.DEVNULL)
        text = ""
        for _ in range(int(wait * 4)):
            text = path.read_text(errors="replace")
            if marker in text or p.poll() is not None: break
            time.sleep(0.25)
        time.sleep(0.3)
        if p.poll() is None:
            p.terminate()
            try: p.wait(5)
            except subprocess.TimeoutExpired: p.kill()
    fh.close()
    text = path.read_text(errors="replace"); path.unlink(missing_ok=True)
    return text if marker in text else None

def print_pdf(chrome, url, out, budget=8000, wait=90):
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True); out.unlink(missing_ok=True)
    last = {"size": -1, "same": 0}
    def done():
        if not out.is_file(): return False
        s = out.stat().st_size
        if s > 0 and s == last["size"]: last["same"] += 1
        else: last["same"] = 0
        last["size"] = s
        return last["same"] >= 4   # size stable for a second
    ok = _watch([chrome, "--no-pdf-header-footer", f"--virtual-time-budget={budget}", f"--print-to-pdf={out}", url], done, wait)
    return out if ok else None
