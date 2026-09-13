#!/usr/bin/env python3
"""Render the `mock` entries in a manifest — HTML mocks of app screens — to PNG through
headless Chrome, at the canvas size each template declares.

    python3 render_mocks.py decks/x/graphics.json            # every mock whose file is missing or older than its template
    python3 render_mocks.py decks/x/graphics.json --force    # all of them

A mock is a screenshot you control: the app's visual language, synthetic names, no PII,
and no dependency on anyone's screen looking a certain way on the day. Templates set
their own canvas in a CSS rule of the form `html,body{…width:1660px;height:640px…}`,
which is what Chrome is told to capture. Render at about twice the placed size so the
mock stays crisp on a 4K export.
"""
import argparse, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config, chrome_path, chrome_screenshot

TOOL = "render_mocks"

def canvas(html_path):
    css = Path(html_path).read_text()
    m = re.search(r"html,body\{[^}]*width:(\d+)px;height:(\d+)px", css)
    if not m: sys.exit(f"{TOOL}: {Path(html_path).name} has no html,body{{width..;height..}} rule")
    return int(m.group(1)), int(m.group(2))

def render(template, out, chrome=None):
    w, h = canvas(template)
    chrome = chrome or chrome_path(load_config(Path(template).parent))
    b = chrome_screenshot(chrome, Path(template).resolve(), out, w, h)
    if not b: sys.exit(f"{TOOL}: Chrome produced nothing for {Path(template).name}")
    side = {"kind": "mock", "template": str(template), "size": [w, h], "chrome": chrome}
    Path(out).with_suffix(".json").write_text(json.dumps(side, indent=2))
    return w, h

def render_manifest(manifest, force=False, only=None):
    manifest = Path(manifest); here = manifest.parent
    m = json.loads(manifest.read_text())
    chrome = chrome_path(load_config(here))
    for k, e in m.items():
        if k.startswith("_") or e.get("kind") != "mock" or (only and k != only): continue
        t, o = here / e["template"], here / e["file"]
        if not t.is_file(): print(f"  {k:18} SKIP  no template {e['template']}"); continue
        if o.is_file() and not force and o.stat().st_mtime >= t.stat().st_mtime:
            print(f"  {k:18} ok    {o.name} (up to date)"); continue
        w, h = render(t, o, chrome)
        print(f"  {k:18} wrote {o.name}  {w}x{h}")

if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("manifest", nargs="?", default="graphics.json")
    a.add_argument("--force", action="store_true")
    a.add_argument("--only", help="one entry id")
    args = a.parse_args()
    render_manifest(args.manifest, args.force, args.only)
