#!/usr/bin/env python3
"""deck-builder — build a talk in your brand, keep its two versions in sync, and export it.

    python3 deckbuilder.py brand     [repo]            write brand.json at the repo root if there isn't one
    python3 deckbuilder.py new       <folder> [--title "..."] [--name talk]
                                                       start a talk: both HTML versions, deck.js, tokens.css, deck.json
    python3 deckbuilder.py settings  <deck.json>       every setting in effect, where it came from, how to change it
    python3 deckbuilder.py sync      <deck.json> [--write-notes]
    python3 deckbuilder.py check     <deck.json> [--version mainstage|leave-behind]
                                                       which slides won't survive as editable shapes, and why
    python3 deckbuilder.py export    <deck.json> [--version ...] [--treat 1=picture,...] [--save] [--pdf-only|--pptx-only]
    python3 deckbuilder.py build     <deck.json>       sync, then check, then export everything `exports` lists

Settings are opinionated defaults — two versions, five words a mainstage slide, notes from the
leave-behind, editable PowerPoint — and every one can be changed or switched off in brand.json ›
decks (all talks) or deck.json › overrides (one talk). `settings` shows them all.
"""
import argparse, json, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
sys.path.insert(0, str(HERE))
import common

def cfg_for(deck_json, version=None):
    import decks_config
    return decks_config.load(Path(deck_json).resolve(), version)

def run_script(name, *args):
    return subprocess.call([sys.executable, str(HERE / name), *map(str, args)])

# ── brand ───────────────────────────────────────────────────────────────────
def cmd_brand(a):
    root = Path(a.repo).resolve()
    found = common.find_brand(root)
    if found:
        print(f"brand.json already at {found}; nothing written."); return 0
    shutil.copy(PLUGIN / "templates" / "brand.template.json", root / "brand.json")
    print(f"wrote {root / 'brand.json'}\n"
          "Fill it from your own design system: colors, display/body/mono fonts and their Google Slides "
          "equivalents, any text glow, logo and illustrations. Point design_system at your design system "
          "(a Claude Design handoff folder, a Figma link) so people and the skill can read it.")
    return 0

# ── new ─────────────────────────────────────────────────────────────────────
def cmd_new(a):
    import decks_config
    folder = Path(a.folder).resolve(); folder.mkdir(parents=True, exist_ok=True)
    name = a.name or folder.name
    lb, ms = f"{name}.html", f"{name}-mainstage.html"
    for src, dst in (("leave-behind.template.html", lb), ("mainstage.template.html", ms)):
        if (folder / dst).exists(): print(f"  keep   {dst} (exists)"); continue
        shutil.copy(PLUGIN / "templates" / src, folder / dst); print(f"  wrote  {dst}")
    if not (folder / "deck.js").exists():
        shutil.copy(PLUGIN / "runtime" / "deck.js", folder / "deck.js"); print("  wrote  deck.js")
    if not (folder / "tokens.css").exists():
        brand = common.load_brand(folder)
        tokens = brand.get("tokens_css") and Path(brand["_dir"]) / brand["tokens_css"]
        if tokens and tokens.is_file():
            rel = Path(shutil.os.path.relpath(tokens, folder))
            (folder / "tokens.css").write_text(f'/* your brand tokens live in brand.json › tokens_css */\n@import url("{rel.as_posix()}");\n')
            print(f"  wrote  tokens.css (imports {rel.as_posix()})")
        else:
            shutil.copy(PLUGIN / "templates" / "tokens.template.css", folder / "tokens.css"); print("  wrote  tokens.css (neutral placeholder)")
    if not (folder / "deck.json").exists():
        decks_config.init_deck_json(folder, a.title or name, lb, ms); print("  wrote  deck.json")
    cfg = decks_config.load(folder / "deck.json")
    print(decks_config.describe(cfg))
    if not common.find_brand(folder):
        print("no brand.json found above this folder — run `deckbuilder.py brand <repo root>` and fill it in")
    return 0

# ── settings ────────────────────────────────────────────────────────────────
def cmd_settings(a):
    import decks_config
    cfg = decks_config.load(Path(a.deck).resolve())
    print(decks_config.describe(cfg))
    print(f"sources: {', '.join(map(str, cfg.get('_sources', []))) or 'plugin defaults only'}\n")
    def walk(d, desc, prefix=""):
        for k, v in d.items():
            if k.startswith("_"): continue
            path = f"{prefix}{k}"
            if isinstance(v, dict) and isinstance(desc.get(k), dict):
                walk(v, desc.get(k, {}), path + ".")
            else:
                default = decks_config.get(decks_config.DEFAULTS, path)
                mark = "" if v == default else f"   (default {json.dumps(default)})"
                note = desc.get(k) if isinstance(desc.get(k), str) else ""
                print(f"  {path:32} {json.dumps(v):34}{mark}")
                if note: print(f"  {'':32} {note}")
    walk({k: v for k, v in cfg.items() if k in decks_config.DEFAULTS}, decks_config.DESCRIPTIONS)
    print("\nChange one for every talk in brand.json › decks, or for this talk in deck.json › overrides. null switches a check off.")
    return 0

# ── sync / check / export ───────────────────────────────────────────────────
def cmd_sync(a):
    args = [a.deck] + (["--write-notes"] if a.write_notes else [])
    return run_script("sync.py", *args)

def cmd_check(a):
    return run_script("fidelity.py", a.deck, "--version", a.version)

def export_pdf(deck_json, version):
    import fidelity
    folder, deck, cfg = fidelity.load_deck(deck_json)
    rel = fidelity.deck_file(deck, version)
    if not rel: return None
    from stage import Stage
    chrome = common.chrome_path(common.load_brand(folder))
    out = folder / (Path(rel).stem + ".pdf")
    with Stage(folder) as st:
        # the runtime stays in for printing: its print CSS lays out one slide per page
        return common.print_pdf(chrome, st.abs_url(rel), out)

def cmd_export(a):
    cfg = cfg_for(a.deck, a.version)
    exports = cfg.get("exports") or []
    rc = 0
    if not a.pptx_only and ("pdf" in exports or a.pdf_only):
        out = export_pdf(a.deck, a.version)
        print(f"{out}" if out else "pdf: failed to print"); rc |= 0 if out else 1
    if not a.pdf_only and "pptx" in exports:
        mode = (cfg.get("pptx") or {}).get("mode")
        args = [a.deck, "--version", a.version]
        if a.treat: args += ["--treat", a.treat]
        if a.save: args += ["--save"]
        if mode == "pictures":
            import fidelity
            folder, deck, _ = fidelity.load_deck(a.deck)
            n = fidelity.slide_count((folder / fidelity.deck_file(deck, a.version)).read_text())
            args = [a.deck, "--version", a.version, "--treat", ",".join(f"{i}=picture" for i in range(1, n + 1))]
        rc |= run_script("export_pptx.py", *args)
    return rc

def cmd_build(a):
    import decks_config
    cfg = decks_config.load(Path(a.deck).resolve())
    print(decks_config.describe(cfg))
    versions = ["mainstage", "leave-behind"] if decks_config.two_versions(cfg) else ["mainstage"]
    if decks_config.two_versions(cfg):
        if run_script("sync.py", a.deck) != 0:
            print("sync found problems; fix them or change the settings, then build again"); return 1
    for v in versions:
        run_script("fidelity.py", a.deck, "--version", v)
        ns = argparse.Namespace(deck=a.deck, version=v, treat=None, save=False, pdf_only=False, pptx_only=False)
        cmd_export(ns)
    return 0

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("brand"); s.add_argument("repo", nargs="?", default="."); s.set_defaults(fn=cmd_brand)
    s = sub.add_parser("new"); s.add_argument("folder"); s.add_argument("--title"); s.add_argument("--name"); s.set_defaults(fn=cmd_new)
    s = sub.add_parser("settings"); s.add_argument("deck"); s.set_defaults(fn=cmd_settings)
    s = sub.add_parser("sync"); s.add_argument("deck"); s.add_argument("--write-notes", action="store_true"); s.set_defaults(fn=cmd_sync)
    s = sub.add_parser("check"); s.add_argument("deck"); s.add_argument("--version", choices=["mainstage", "leave-behind"], default="mainstage"); s.set_defaults(fn=cmd_check)
    s = sub.add_parser("export"); s.add_argument("deck"); s.add_argument("--version", choices=["mainstage", "leave-behind"], default="mainstage")
    s.add_argument("--treat"); s.add_argument("--save", action="store_true")
    g = s.add_mutually_exclusive_group(); g.add_argument("--pdf-only", action="store_true"); g.add_argument("--pptx-only", action="store_true")
    s.set_defaults(fn=cmd_export)
    s = sub.add_parser("build"); s.add_argument("deck"); s.set_defaults(fn=cmd_build)
    a = p.parse_args()
    sys.exit(a.fn(a))
