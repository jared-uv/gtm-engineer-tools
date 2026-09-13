#!/usr/bin/env python3
"""deck-graphics — fill a deck's graphics from its manifest, and say where each one came from.

    python3 deckgraphics.py init                          write .deckgraphics.json here if missing
    python3 deckgraphics.py check  decks/x/graphics.json  validate the manifest
    python3 deckgraphics.py status decks/x/graphics.json  one line per graphic: present? size? source?
    python3 deckgraphics.py fill   decks/x/graphics.json  fetch / generate / render everything missing
        --only <id>     one entry
        --force         redo entries that already have a file
        --dry-run       print the plan and the cost, do nothing

The manifest is a JSON object: keys starting with "_" are notes, every other key is one
graphic. `_assets_dir` (default assets/generated) is where logo rows put their files.

  kind        needs                       optional
  logo        domain, file                type icon|logo|symbol, theme dark|light, prefer <source>, url <pinned source>
  logo-row    domains[]                   pins {domain: url}, prefer {domain: source}   → assets/<dir>/logo-<slug>.png each
  generated   prompt, file                style, provider, model, seed, aspect
  mock        template (html), file
  screenshot  file                        nothing is fetched; someone captures it by hand

Every file written gets a sidecar .json beside it: the source tier or the provider,
model, prompt, refs, seed and cost. `status` reads the sidecars back, so the deck
records where each graphic came from and how good that is.

Assets and sidecars only. The deck builder is yours; it reads `file` per entry.
"""
import argparse, json, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import load_config, load_env, slug, png_size_of, CONFIG_NAME

KINDS = ("logo", "logo-row", "generated", "mock", "screenshot")
REQUIRED = {"logo": ("domain", "file"), "logo-row": ("domains",), "generated": ("prompt", "file"),
            "mock": ("template", "file"), "screenshot": ("file",)}
COST_GUESS = 0.07   # USD per generated image, Nano Banana 2 through OpenRouter, 2026-09

# ── manifest ────────────────────────────────────────────────────────────────
def load_manifest(path):
    path = Path(path)
    if not path.is_file(): sys.exit(f"deck-graphics: no manifest at {path}")
    m = json.loads(path.read_text())
    if not isinstance(m, dict): sys.exit("deck-graphics: the manifest must be a JSON object")
    assets = path.parent / m.get("_assets_dir", "assets/generated")
    entries = {k: v for k, v in m.items() if not k.startswith("_")}
    return path, assets, entries

def pin_path(url, here):
    """A pinned source is a URL, or a file relative to the manifest (the vendor sent the logo)."""
    if not url or "://" in url: return url
    return str((here / url).resolve())

def targets(k, e, here, assets):
    """(label, file, spec) per file this entry owns — one, or one per domain for a logo row."""
    if e.get("kind") == "logo-row":
        pins, prefer = e.get("pins", {}), e.get("prefer", {})
        if not isinstance(prefer, dict): prefer = {}
        return [(f"{k} · {d}", assets / f"logo-{slug(d)}.png",
                 {"kind": "logo", "domain": d, "type": e.get("type", "icon"), "theme": e.get("theme", "dark"),
                  "url": pin_path(pins.get(d), here), "prefer": prefer.get(d)}) for d in e["domains"]]
    if e.get("kind") == "logo" and e.get("url"):
        e = {**e, "url": pin_path(e["url"], here)}
    return [(k, here / e["file"], e)]

def sidecar(file):
    p = Path(file).with_suffix(".json")
    try: return json.loads(p.read_text()) if p.is_file() else {}
    except json.JSONDecodeError: return {}

def describe(side):
    if "source" in side:
        s = side["source"]
        if s == "url": s = "pinned url"
        if str(side.get("url", "")).endswith("#white-knocked-out"): s += ", white ground removed"
        if side.get("tried"): s += f" (fell through {len(side['tried'])})"
        return s
    if "provider" in side:
        s = f"{side['provider']}/{side.get('model', '?')}"
        if side.get("cost"): s += f" ${side['cost']:.3f}"
        return s
    if side.get("kind") == "mock": return "mock"
    return "no sidecar"

# ── commands ────────────────────────────────────────────────────────────────
def cmd_init(args):
    dest = Path(args.dir) / CONFIG_NAME
    if dest.is_file():
        print(f"{dest} exists; nothing written."); return 0
    shutil.copy(HERE.parent / "templates" / "deckgraphics.template.json", dest)
    print(f"wrote {dest}\nNext: describe your house style in it (preamble + a few reference images), "
          f"put OPENROUTER_API_KEY and BRANDFETCH_CLIENT_ID in a .env beside it, then write a graphics.json "
          f"per deck (template: {HERE.parent / 'templates' / 'graphics.template.json'}).")
    return 0

def cmd_check(args):
    path, assets, entries = load_manifest(args.manifest)
    cfg = load_config(path.parent, args.config)
    problems = []
    for k, e in entries.items():
        kind = e.get("kind")
        if kind not in KINDS:
            problems.append(f"{k}: kind {kind!r} is not one of {', '.join(KINDS)}"); continue
        for f in REQUIRED[kind]:
            if f not in e: problems.append(f"{k}: a {kind} entry needs {f!r}")
        if kind == "mock" and "template" in e and not (path.parent / e["template"]).is_file():
            problems.append(f"{k}: template {e['template']} is missing")
        if kind == "generated":
            st = e.get("style") or cfg.get("default_style") or "none"
            if st not in cfg["styles"]:
                problems.append(f"{k}: style {st!r} is not in {cfg['_path'] or 'the built-in set'} ({', '.join(cfg['styles'])})")
        if kind == "logo-row" and not isinstance(e.get("domains"), list):
            problems.append(f"{k}: domains must be a list")
    for p in problems: print("  " + p)
    print(f"{'ok' if not problems else 'problems'}: {len(entries)} entries, {len(problems)} problems"
          + (f", styles from {cfg['_path']}" if cfg["_path"] else ", no .deckgraphics.json (only style `none`)"))
    return 1 if problems else 0

def cmd_status(args):
    path, assets, entries = load_manifest(args.manifest)
    placed = missing = by_hand = 0
    for k, e in entries.items():
        if e.get("kind") not in KINDS:
            print(f"  {k:34} ??      kind {e.get('kind')!r}"); missing += 1; continue
        for label, f, spec in targets(k, e, path.parent, assets):
            if f.is_file() and f.stat().st_size:
                wh = png_size_of(f); size = f"{wh[0]}x{wh[1]}" if wh else "not a PNG"
                print(f"  {label:34} ok      {size:10} {describe(sidecar(f))}"); placed += 1
            elif e.get("kind") == "screenshot":
                print(f"  {label:34} by hand {'':10} {e.get('brief', '')}"); by_hand += 1
            else:
                print(f"  {label:34} MISSING {'':10} {f.relative_to(path.parent)}"); missing += 1
    print(f"{placed} placed, {missing} missing, {by_hand} by hand")
    return 0

def cmd_fill(args):
    path, assets, entries = load_manifest(args.manifest)
    here = path.parent
    load_env(here)
    plan = []
    for k, e in entries.items():
        if args.only and k != args.only: continue
        kind = e.get("kind")
        if kind not in KINDS: print(f"  {k:34} skip    unknown kind {kind!r}"); continue
        if kind == "screenshot": print(f"  {k:34} by hand {e.get('brief', '')}"); continue
        for label, f, spec in targets(k, e, here, assets):
            if f.is_file() and f.stat().st_size and not args.force:
                print(f"  {label:34} keep    {f.name}"); continue
            plan.append((label, f, spec))
    n_gen = sum(1 for _, _, s in plan if s.get("kind") == "generated")
    if not plan:
        print("nothing to do"); return 0
    print(f"{len(plan)} to fill, {n_gen} generated (about ${n_gen * COST_GUESS:.2f})")
    if args.dry_run:
        for label, f, spec in plan:
            what = {"logo": f"fetch {spec.get('domain')}" + (f" from {spec['url']}" if spec.get("url") else ""),
                    "generated": f"generate [{spec.get('style') or 'default'}] {spec.get('prompt', '')[:60]}",
                    "mock": f"render {spec.get('template')}"}[spec["kind"]]
            print(f"  {label:34} would   {what} → {f.relative_to(here)}")
        return 0
    import imagegen, logos, render_mocks
    failed = []
    for label, f, spec in plan:
        try:
            if spec["kind"] == "logo":
                _, side = logos.fetch(spec["domain"], f, spec.get("type", "icon"), spec.get("theme", "dark"),
                                      spec.get("size", 512), spec.get("color", "#FFFFFF"), spec.get("prefer"), spec.get("url"))
                w, h = side["size"] or (0, 0)
                print(f"  {label:34} wrote   {f.name}  {w}x{h}  via {side['source']}")
            elif spec["kind"] == "generated":
                _, side = imagegen.generate(spec["prompt"], f, spec.get("style"), spec.get("refs", ()), spec.get("provider"),
                                            spec.get("model"), spec.get("aspect"), spec.get("seed"), 1, spec.get("background"), args.config)
                print(f"  {label:34} wrote   {f.name}  via {side['provider']}/{side['model']}"
                      + (f"  ${side['cost']:.3f}" if side.get("cost") else ""))
            elif spec["kind"] == "mock":
                w, h = render_mocks.render(here / spec["template"], f)
                print(f"  {label:34} wrote   {f.name}  {w}x{h}")
        except SystemExit as ex:   # each tool exits with a one-line reason; keep going
            failed.append((label, str(ex))); print(f"  {label:34} FAILED  {ex}")
    print(f"{len(plan) - len(failed)} written, {len(failed)} failed")
    return 1 if failed else 0

if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = a.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("dir", nargs="?", default="."); p.set_defaults(fn=cmd_init)
    for name, fn in (("check", cmd_check), ("status", cmd_status), ("fill", cmd_fill)):
        p = sub.add_parser(name); p.add_argument("manifest"); p.add_argument("--config"); p.set_defaults(fn=fn)
        if name == "fill":
            p.add_argument("--only"); p.add_argument("--force", action="store_true"); p.add_argument("--dry-run", action="store_true")
    args = a.parse_args()
    sys.exit(args.fn(args))
