#!/usr/bin/env python3
"""deck-graphics — fill a deck's graphics from its manifest, and say where each one came from.

    python3 deckgraphics.py init                          write .deckgraphics.json here if missing
    python3 deckgraphics.py check  decks/x/graphics.json  validate the manifest
    python3 deckgraphics.py status decks/x/graphics.json  one line per graphic: present? size? source?
    python3 deckgraphics.py fill   decks/x/graphics.json  fetch / generate / render everything missing
        --only <id>     one entry
        --force         redo entries that already have a file
        --dry-run       print the plan and the cost, do nothing
    python3 deckgraphics.py sheet  decks/x/graphics.json  one HTML page with every graphic, grouped, sidecar under each
        --out <file>    default: sheet.html beside the manifest
        --embed         inline the images (downscaled) so the page travels on its own

The manifest is a JSON object: keys starting with "_" are notes, every other key is one
graphic. `_assets_dir` (default assets/generated) is where logo rows put their files.

  kind        needs                       optional
  logo        domain, file                type icon|logo|symbol, theme dark|light, prefer <source>, url <pinned source>
  logo-row    domains[]                   pins {domain: url}, prefer {domain: source}   → assets/<dir>/logo-<slug>.png each
  generated   prompt, file                style, provider, model, seed, aspect
  mock        template (html), file
  screenshot  file                        nothing is fetched; someone captures it by hand

Any entry may carry `note`, a sentence for the reviewer; only `sheet` shows it.

Mocks render last. A mock template that embeds another entry's output (an illustration
under real labels) waits for that entry, and is re-rendered when the input is newer than
its PNG — the same rule as for its own template.

Every file written gets a sidecar .json beside it: the source tier or the provider,
model, prompt, refs, seed and cost. `status` reads the sidecars back, so the deck
records where each graphic came from and how good that is.

Assets and sidecars only. The deck builder is yours; it reads `file` per entry.
"""
import argparse, base64, html, json, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import load_config, load_env, slug, png_size_of, mock_inputs, mock_stale, CONFIG_NAME

KINDS = ("logo", "logo-row", "generated", "mock", "screenshot")
REQUIRED = {"logo": ("domain", "file"), "logo-row": ("domains",), "generated": ("prompt", "file"),
            "mock": ("template", "file"), "screenshot": ("file",)}
COST_GUESS = 0.07   # USD per generated image, Nano Banana 2 through OpenRouter, 2026-09
# What the default image model accepts (Gemini image, 2026-09). Others are rejected by the provider
# with an HTTP 400 after the request; `check` says so first.
ASPECTS = ("1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9")

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
        if side.get("seed") is not None: s += f" seed {side['seed']}"
        if side.get("cost"): s += f" ${side['cost']:.3f}"
        return s
    if side.get("kind") == "mock":
        s = "mock"
        if side.get("template"): s += f" · {Path(side['template']).name}"
        if side.get("inputs"): s += f" · over {', '.join(Path(i).name for i in side['inputs'])}"
        return s
    return "no sidecar"

def group_of(k):
    """Everything before the last hyphen: growth-current, growth-rich, growth-hybrid are one group."""
    return k.rsplit("-", 1)[0] if "-" in k else k

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
    problems, notes = [], []
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
            asp = e.get("aspect") or cfg["styles"].get(st, {}).get("aspect")
            if asp and asp not in ASPECTS:
                notes.append(f"{k}: aspect {asp!r} is not one the default image model accepts ({', '.join(ASPECTS)}); the provider will reject it")
        if kind == "logo-row" and not isinstance(e.get("domains"), list):
            problems.append(f"{k}: domains must be a list")
    for p in problems: print("  " + p)
    for n in notes: print("  note: " + n)
    print(f"{'ok' if not problems else 'problems'}: {len(entries)} entries, {len(problems)} problems"
          + (f", {len(notes)} notes" if notes else "")
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

def plan_fill(entries, here, assets, only=None, force=False):
    """The list of (label, file, spec, why) to do, mocks last so they can draw on what came before.
    A mock joins the plan when missing, forced, stale (template or an input newer than its PNG),
    or when one of its inputs is being written by an earlier entry in the same run."""
    first, mocks, produced = [], [], set()
    for k, e in entries.items():
        if only and k != only: continue
        kind = e.get("kind")
        if kind not in KINDS: print(f"  {k:34} skip    unknown kind {kind!r}"); continue
        if kind == "screenshot": print(f"  {k:34} by hand {e.get('brief', '')}"); continue
        if kind == "mock": mocks.append((k, e)); continue
        for label, f, spec in targets(k, e, here, assets):
            if f.is_file() and f.stat().st_size and not force:
                print(f"  {label:34} keep    {f.name}"); continue
            first.append((label, f, spec, "")); produced.add(f.resolve())
    later = []
    for k, e in mocks:
        for label, f, spec in targets(k, e, here, assets):
            t = here / spec["template"]
            deps = [p for p in mock_inputs(t)] if t.is_file() else []
            waits = [p.name for p in deps if p in produced]
            why = "forced" if force else (mock_stale(t, f) if t.is_file() else "missing")
            if waits: why = f"after {', '.join(waits)}"
            if not why:
                print(f"  {label:34} keep    {f.name}"); continue
            later.append((label, f, spec, why))
    return first + later

def cmd_fill(args):
    path, assets, entries = load_manifest(args.manifest)
    here = path.parent
    load_env(here)
    plan = plan_fill(entries, here, assets, args.only, args.force)
    n_gen = sum(1 for _, _, s, _ in plan if s.get("kind") == "generated")
    if not plan:
        print("nothing to do"); return 0
    print(f"{len(plan)} to fill, {n_gen} generated (about ${n_gen * COST_GUESS:.2f})")
    if args.dry_run:
        for label, f, spec, why in plan:
            what = {"logo": f"fetch {spec.get('domain')}" + (f" from {spec['url']}" if spec.get("url") else ""),
                    "generated": f"generate [{spec.get('style') or 'default'}] {spec.get('prompt', '')[:60]}",
                    "mock": f"render {spec.get('template')}" + (f" ({why})" if why and why != "missing" else "")}[spec["kind"]]
            print(f"  {label:34} would   {what} → {f.relative_to(here)}")
        return 0
    import imagegen, logos, render_mocks
    failed = []
    for label, f, spec, why in plan:
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
                print(f"  {label:34} wrote   {f.name}  {w}x{h}" + (f"  ({why})" if why and why != "missing" else ""))
        except SystemExit as ex:   # each tool exits with a one-line reason; keep going
            failed.append((label, str(ex))); print(f"  {label:34} FAILED  {ex}")
    print(f"{len(plan) - len(failed)} written, {len(failed)} failed")
    return 1 if failed else 0

# ── sheet ───────────────────────────────────────────────────────────────────
SHEET_CSS = """
body{margin:0;padding:32px 24px 72px;background:#f6f5f2;color:#111;font-family:system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif}
h1{font-size:26px;font-weight:600;margin:0 0 4px}.lede{color:#555;margin:0 0 28px;font-size:14px}
h2{font-size:17px;font-weight:600;margin:36px 0 10px;letter-spacing:.2px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
figure{margin:0;background:#fff;border:1px solid #d9d6cf;border-radius:8px;overflow:hidden}
figure img{display:block;width:100%;height:auto;background:repeating-conic-gradient(#eee 0 25%,#fff 0 50%) 0 0/16px 16px}
figcaption{padding:10px 12px 12px}figcaption b{display:block;font-size:14px;font-weight:600}
figcaption p{margin:4px 0 0;font-size:13px;color:#333;line-height:1.4}figcaption small{display:block;margin-top:6px;font-size:11px;color:#777}
.missing{display:flex;align-items:center;justify-content:center;aspect-ratio:16/9;color:#999;font-size:13px}
@media (max-width:520px){body{padding:16px 16px 48px}.grid{grid-template-columns:1fr}}
"""

def _embed_src(f):
    """A data URI for the sheet: downscaled JPEG for opaque images, PNG kept for transparent ones.
    Without Pillow the bytes go in as they are."""
    data = f.read_bytes(); mime = "image/png"
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(data))
        if im.width > 1000: im = im.resize((1000, round(im.height * 1000 / im.width)))
        buf = io.BytesIO()
        if im.mode in ("RGBA", "LA", "P") and im.convert("RGBA").getextrema()[3][0] < 255:
            im.save(buf, "PNG", optimize=True)
        else:
            im.convert("RGB").save(buf, "JPEG", quality=82, optimize=True, progressive=True); mime = "image/jpeg"
        data = buf.getvalue()
    except ImportError:
        pass
    return f"data:{mime};base64," + base64.b64encode(data).decode()

def cmd_sheet(args):
    path, assets, entries = load_manifest(args.manifest)
    here = path.parent
    out = Path(args.out) if args.out else here / "sheet.html"
    groups = {}
    for k, e in entries.items():
        if e.get("kind") not in KINDS: continue
        for label, f, spec in targets(k, e, here, assets):
            g = k if e.get("kind") == "logo-row" else group_of(k)
            short = label.split(" · ", 1)[1] if " · " in label else (k.rsplit("-", 1)[1] if "-" in k and g != k else k)
            groups.setdefault(g, []).append((short, f, e, spec))
    parts = [f"<title>{html.escape(here.name)} graphics</title><style>{SHEET_CSS}</style>",
             f"<h1>{html.escape(here.name)}</h1>",
             f'<p class="lede">{sum(len(v) for v in groups.values())} graphics in {len(groups)} groups · from {html.escape(path.name)}. '
             'Squint: does each one read at the size it will be placed?</p>']
    n_img = 0
    for g, items in groups.items():
        parts.append(f"<h2>{html.escape(g)}</h2><div class=\"grid\">")
        for short, f, e, spec in items:
            if f.is_file() and f.stat().st_size:
                src = _embed_src(f) if args.embed else html.escape(str(Path(f.resolve()).relative_to(out.resolve().parent)) if f.resolve().is_relative_to(out.resolve().parent) else str(f.resolve()))
                wh = png_size_of(f); size = f"{wh[0]}×{wh[1]}" if wh else ""
                img = f'<img src="{src}" alt="{html.escape(g)}: {html.escape(short)}" loading="lazy">'; n_img += 1
            else:
                img, size = '<div class="missing">not produced</div>', ""
            note = e.get("note") or ("captured by hand" if e.get("kind") == "screenshot" else "")
            meta = " · ".join(x for x in (spec.get("kind") or e.get("kind"), size, describe(sidecar(f)) if f.is_file() else "") if x)
            parts.append(f"<figure>{img}<figcaption><b>{html.escape(short)}</b>"
                         + (f"<p>{html.escape(note)}</p>" if note else "")
                         + f"<small>{html.escape(meta)}</small></figcaption></figure>")
        parts.append("</div>")
    out.write_text("\n".join(parts))
    print(f"wrote {out}  {n_img} images in {len(groups)} groups" + ("  (embedded)" if args.embed else ""))
    return 0

if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = a.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("dir", nargs="?", default="."); p.set_defaults(fn=cmd_init)
    for name, fn in (("check", cmd_check), ("status", cmd_status), ("fill", cmd_fill), ("sheet", cmd_sheet)):
        p = sub.add_parser(name); p.add_argument("manifest"); p.add_argument("--config"); p.set_defaults(fn=fn)
        if name == "fill":
            p.add_argument("--only"); p.add_argument("--force", action="store_true"); p.add_argument("--dry-run", action="store_true")
        if name == "sheet":
            p.add_argument("--out"); p.add_argument("--embed", action="store_true")
    args = a.parse_args()
    sys.exit(args.fn(args))
