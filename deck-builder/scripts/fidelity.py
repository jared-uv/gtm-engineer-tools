#!/usr/bin/env python3
"""Which slides won't survive as editable shapes, and why.

    python3 fidelity.py talk/deck.json                   # the mainstage (default)
    python3 fidelity.py talk/deck.json --version leave-behind
    python3 fidelity.py talk/deck.json --json

For each slide, three renders:

  raw       the slide as designed
  preview   the slide rebuilt only from the shape model the editable export will write —
            text boxes, filled and bordered boxes, images — so it shows what an editable
            copy can look like, before any PowerPoint file exists
  effects   only what the model can't carry (glows, shadows, CSS decorations), on transparent

raw and preview are compared pixel by pixel. Wherever they differ, the editable version
loses something. That is the generic check: it doesn't need to know in advance that glowing
text or a blend mode is a problem, it sees the difference. Each difference is then explained,
where it can be, by the measured effects on the elements it overlaps; what can't be explained
is reported as such, with its position, so a person can look.

Each slide gets a verdict and the treatments that make sense for it:

  faithful          editable looks the same; exported editable, nothing to decide
  effects-only      the only losses are glows, shadows or CSS decorations: offered
                    editable (loses them), glow-behind (editable text, effects baked in
                    a picture behind it), or picture
  approximated      the editable copy draws something close rather than exact: a font swapped
                    for one Google Slides has, a gradient simplified. Named even when the
                    comparison can't see it (a radial's spread only differs in the exported
                    file). Offered editable or picture, and glow-behind if a glow is lost too
  other             something else differs (an SVG, a filter, an unexplained region):
                    offered editable or picture

Renders land in <deck folder>/.deck-builder/fidelity/<version>/, including an overlay per
slide with the differing regions outlined, for a person or the skill to look at.
Needs Chrome and Pillow.
"""
import argparse, html as htmllib, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common
from stage import Stage

SLIDES_FONTS = {"inter", "barlow semi condensed", "barlow", "roboto", "open sans", "montserrat", "lato", "poppins",
                "archivo", "work sans", "dm sans", "ibm plex sans", "source sans 3", "nunito", "raleway", "oswald",
                "playfair display", "merriweather", "arial", "helvetica", "georgia", "times new roman", "verdana",
                "courier new", "roboto mono", "source code pro", "jetbrains mono", "ibm plex mono", "space mono"}
EFFECT_KINDS = ("glowing or shadowed text", "gradient-filled text", "shadow or glow on a shape", "CSS ::before", "CSS ::after")
# drawn differently on purpose rather than lost: close, editable, and named so nobody has to guess
APPROX_KINDS = ("font not in Google Slides", "gradient approximated", "letter spacing not in Google Slides", "weight ",
                "list marker position estimated")

# ── deck.json ───────────────────────────────────────────────────────────────
def load_deck(deck_json, version=None):
    deck_json = Path(deck_json).resolve()
    try:
        import decks_config
        cfg = decks_config.load(deck_json, version)
        deck = cfg.get("_deck") or json.loads(deck_json.read_text())
    except Exception:
        cfg, deck = {}, json.loads(deck_json.read_text())
    return deck_json.parent, deck, cfg

def deck_file(deck, version):
    """The HTML file for a version, or None. A two-version deck names each under leave_behind
    and mainstage. A one-version deck names its one file under "deck" (or under just one of
    those keys), and that file answers for either version, so check, export and build work on
    it without being told which version it is."""
    key = "mainstage" if version == "mainstage" else "leave_behind"
    if deck.get(key): return deck[key]
    named = {deck[k] for k in ("deck", "leave_behind", "mainstage") if deck.get(k)}
    return named.pop() if len(named) == 1 else None

def slide_count(html_text):
    m = re.search(r"<(slide-deck|deck-stage)\b[^>]*>(.*)</\1>", html_text, re.S | re.I)
    body = m.group(2) if m else html_text
    depth, count = 0, 0
    for tag in re.finditer(r"<(/?)section\b", body, re.I):
        if tag.group(1): depth -= 1
        else:
            if depth == 0: count += 1
            depth += 1
    return count

# ── measuring ───────────────────────────────────────────────────────────────
def measure(stage, chrome, file_rel, n):
    dom = common.dump_dom(chrome, stage.url(file_rel, n, "measure"), '"items"')
    if not dom: return None
    m = re.search(r'<pre id="__model"[^>]*>(.*?)</pre>', dom, re.S)
    return json.loads(htmllib.unescape(m.group(1))) if m else None

# ── the preview: the shape model, drawn back as HTML ────────────────────────
def css_color(c):
    return "transparent" if not c else f"rgba({c['r']:.0f},{c['g']:.0f},{c['b']:.0f},{c['a']})"

def css_gradient(g):
    stops = ", ".join(f"{css_color(s['c'])} {s['p']*100:.1f}%" for s in g["stops"])
    if g["kind"] == "linear": return f"linear-gradient({g['angle']}deg, {stops})"
    at = g.get("at") or {"x": 0.5, "y": 0.5}
    return f"radial-gradient({g.get('shape') or 'circle'} at {at['x']*100:.1f}% {at['y']*100:.1f}%, {stops})"

def font_for(family, brand):
    """The family the editable copy will actually use: the brand's declared Slides equivalent,
    the family itself if Slides has it, else a generic stand-in."""
    fam = (family or "").strip()
    for f in ((brand or {}).get("fonts") or {}).values():
        if isinstance(f, dict) and f.get("family", "").lower() == fam.lower() and f.get("slides_equivalent"):
            return f["slides_equivalent"]
    if fam.lower() in SLIDES_FONTS: return fam
    return "Roboto Mono" if re.search(r"mono|code|menlo|consolas|courier", fam, re.I) else "Arial"

def font_faces(deck_html):
    """@font-face rules and font stylesheet links from the deck, so the preview can use the
    same font files for families Google Slides also has."""
    faces = re.findall(r"@font-face\s*{[^}]*}", deck_html)
    links = re.findall(r"<link[^>]+(?:fonts\.googleapis|\.css)[^>]*>", deck_html, re.I)
    # url("...") may itself contain semicolons (Google Fonts: wght@1,700;1,800), so match the
    # parenthesised url whole; a cut-off @import leaves an open string that eats the rest of the style block
    imports = re.findall(r"@import\s+url\((?:\"[^\"]*\"|'[^']*'|[^)]*)\)[^;]*;", deck_html)
    return "\n".join(links), "\n".join(imports + faces)

def generic_for(family):
    return "monospace" if re.search(r"mono|code|menlo|consolas|courier", family or "", re.I) else "sans-serif"

def substitute_links(model, brand):
    """Google Fonts links for families the editable copy switches to (SF Mono -> Roboto Mono),
    so the preview draws the substitute Slides will use instead of a browser fallback."""
    subs = set()
    for it in model.get("items", []):
        for r in it.get("runs", []):
            if r.get("br"): continue
            f = font_for(r.get("family"), brand)
            if f.lower() != (r.get("family") or "").lower() and f.lower() not in ("arial", "helvetica", "georgia", "times new roman", "verdana", "courier new"):
                subs.add(f)
    return "".join('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=' + f.replace(" ", "+")
                   + ':ital,wght@0,400;0,700;1,400;1,700&display=swap">' for f in sorted(subs))

def preview_html(model, brand, deck_html, base_href, w=common.W, h=common.H, target="google-slides"):
    links, faces = font_faces(deck_html)
    links += substitute_links(model, brand)
    parts = []
    bg = model.get("background") or {}
    bg_css = css_gradient(bg["gradient"]) if bg.get("gradient") else css_color(bg.get("fill")) if bg.get("fill") else "#000"
    for it in model["items"]:
        x, y, iw, ih = it["x"], it["y"], it["w"], it["h"]
        pos = f"position:absolute;left:{x:.1f}px;top:{y:.1f}px;width:{iw:.1f}px;height:{ih:.1f}px;box-sizing:border-box;"
        if it["type"] == "box":
            s = pos + f"border-radius:{it['radius']}px;opacity:{it.get('opacity', 1)};"
            if it.get("gradient"): s += f"background:{css_gradient(it['gradient'])};"
            elif it.get("fill"): s += f"background:{css_color(it['fill'])};"
            if it.get("border"): s += f"border:{it['border']['w']}px {'dashed' if it['border']['dash'] else 'solid'} {css_color(it['border']['c'])};"
            parts.append(f'<div style="{s}"></div>')
        elif it["type"] == "image":
            parts.append(f'<img src="{htmllib.escape(it["src"])}" style="{pos}object-fit:{it.get("fit") or "fill"};opacity:{it.get("opacity", 1)}">')
        elif it["type"] == "text":
            v = {"middle": "center", "bottom": "flex-end"}.get(it["valign"], "flex-start")
            j = {"center": "center", "right": "flex-end"}.get(it["align"], "flex-start")
            s = pos + (f"display:flex;flex-direction:column;justify-content:{v};text-align:{it['align']};"
                       f"line-height:{it['lineHeight']:.1f}px;white-space:{'pre-wrap' if it['wrap'] else 'pre'};opacity:{it.get('opacity', 1)};")
            # The container's own font sets the line box's strut. Left at the browser's 16px, a
            # 104px run on a 98.8px line height pushes every line apart; PowerPoint has no strut.
            first = next((r for r in it["runs"] if not r.get("br")), None)
            if first:
                ff = font_for(first.get("family"), brand)
                s += f"font-size:{first['size']}px;font-family:'{ff}',{generic_for(ff)};"
            spans = []
            for r in it["runs"]:
                if r.get("br"): spans.append("<br>"); continue
                fam = font_for(r['family'], brand)
                # drawn as the editable copy will set it: bold or regular, and no letter spacing in Google Slides
                spacing = 0 if target == "google-slides" else r.get("spacing", 0)
                rs = (f"font-family:'{fam}',{generic_for(fam)};font-size:{r['size']}px;font-weight:{slides_weight(r.get('weight'))};"
                      f"font-style:{'italic' if r['italic'] else 'normal'};color:{css_color(r['color'])};letter-spacing:{spacing}px;"
                      + ("text-decoration:underline;" if r.get("underline") else ""))
                spans.append(f'<span style="{rs}">{htmllib.escape(r["t"])}</span>')
            parts.append(f'<div style="{s}"><div style="align-self:stretch;text-align:{it["align"]}">{"".join(spans)}</div></div>')
        # raster items (svg, canvas…) are left out on purpose: the editable copy can't draw them
    return (f'<!doctype html><html><head><meta charset="utf-8"><base href="{base_href}">{links}'
            f'<style>{faces}\nhtml,body{{margin:0;width:{w}px;height:{h}px;overflow:hidden}}'
            f'#s{{position:relative;width:{w}px;height:{h}px;overflow:hidden;background:{bg_css}}}</style></head>'
            f'<body><div id="s">{"".join(parts)}</div></body></html>')

# ── comparing ───────────────────────────────────────────────────────────────
def diff_regions(raw_png, preview_png, cell=24, min_cell_frac=0.06, thresh=48):
    """Regions where the two renders differ: per-pixel difference over `thresh`, bucketed into
    cells, cells with enough changed pixels joined into rectangles. Returns (fraction of the
    slide that differs, [regions as x, y, w, h])."""
    from PIL import Image, ImageChops, ImageFilter
    a = Image.open(raw_png).convert("RGB"); b = Image.open(preview_png).convert("RGB").resize(a.size)
    # Shift-tolerant: a pixel only differs if its value falls outside the range of the other
    # render's pixels within `slack` px of it, in either direction. Chrome snaps text lines to
    # whole pixels, so a second line can sit a pixel lower in one render; that is not a loss.
    # A shape that is present in one render and absent in the other is still far outside range.
    slack = 2
    size = 2 * slack + 1
    def out_of_range(x, y):
        chans = []
        for cx, cy in zip(x.split(), y.split()):
            lo, hi = cy.filter(ImageFilter.MinFilter(size)), cy.filter(ImageFilter.MaxFilter(size))
            chans.append(ImageChops.lighter(ImageChops.subtract(cx, hi), ImageChops.subtract(lo, cx)))
        return ImageChops.lighter(ImageChops.lighter(chans[0], chans[1]), chans[2])
    d = ImageChops.lighter(out_of_range(a, b), out_of_range(b, a)).point(lambda v: 255 if v > thresh else 0)
    W, H = d.size; gw, gh = (W + cell - 1) // cell, (H + cell - 1) // cell
    px = d.load(); hot = [[False] * gw for _ in range(gh)]; changed = 0
    for gy in range(gh):
        for gx in range(gw):
            n = tot = 0
            for yy in range(gy * cell, min(H, (gy + 1) * cell), 2):
                for xx in range(gx * cell, min(W, (gx + 1) * cell), 2):
                    tot += 1
                    if px[xx, yy]: n += 1
            if tot and n / tot >= min_cell_frac: hot[gy][gx] = True; changed += n * 4
    seen, regions = set(), []
    for gy in range(gh):
        for gx in range(gw):
            if not hot[gy][gx] or (gx, gy) in seen: continue
            stack, cells = [(gx, gy)], []
            seen.add((gx, gy))
            while stack:
                cx, cy = stack.pop(); cells.append((cx, cy))
                for nx, ny in ((cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1), (cx+1, cy+1), (cx-1, cy-1), (cx+1, cy-1), (cx-1, cy+1)):
                    if 0 <= nx < gw and 0 <= ny < gh and hot[ny][nx] and (nx, ny) not in seen:
                        seen.add((nx, ny)); stack.append((nx, ny))
            xs = [c[0] for c in cells]; ys = [c[1] for c in cells]
            if len(cells) < 2: continue   # a single cell is anti-aliasing noise
            regions.append({"x": min(xs) * cell, "y": min(ys) * cell, "w": (max(xs) - min(xs) + 1) * cell, "h": (max(ys) - min(ys) + 1) * cell})
    return changed / float(W * H), regions

def overlap(a, b):
    ix = max(0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
    iy = max(0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
    return ix * iy

def slides_weight(w):
    """The weight the editable copy can carry: a run is bold or it isn't."""
    return 700 if (w or 400) >= 600 else 400

def substitutions(model, brand, target="google-slides"):
    """Text the editable copy sets differently, as approximation entries: SF Mono isn't in Google
    Slides, so it becomes Roboto Mono, which is wider; Google Slides has no letter spacing, so
    tracked or tightened text comes out at its natural width; and any weight becomes bold or
    regular. Each can push a line past its box."""
    out = []
    for it in model.get("items", []):
        if it.get("type") != "text": continue
        runs = [r for r in it.get("runs", []) if not r.get("br")]
        effects = [f"font not in Google Slides: {a} → {b}" for a, b in sorted(
            {(r["family"], font_for(r["family"], brand)) for r in runs
             if r.get("family") and font_for(r["family"], brand).lower() != r["family"].lower()})]
        # any spacing at all: 0.42px across an 80-character caption moves its end by 30px
        if target == "google-slides" and any(abs(r.get("spacing") or 0) > 0.01 for r in runs):
            effects.append("letter spacing not in Google Slides")
        effects += [f"weight {w} drawn as {'bold' if slides_weight(w) == 700 else 'regular'}"
                    for w in sorted({r["weight"] for r in runs if r.get("weight") and r["weight"] not in (400, 700)})]
        if effects:
            label = "".join(r.get("t", "") for r in it["runs"]).replace("\n", " ")[:48]
            out.append({"label": label, "x": it["x"], "y": it["y"], "w": it["w"], "h": it["h"], "effects": effects})
    return out

def slide_notes(model, brand, target="google-slides"):
    """Every approximation a slide carries, whether or not the comparison shows it. Quiet ones (an
    estimated bullet position) are left out: they're named only when a difference lands on them."""
    return sorted({e for a in model.get("approximations", []) + substitutions(model, brand, target)
                   if not a.get("quiet") for e in a["effects"]})

def explain(regions, model, pad=40, cover=0.6, brand=None, target="google-slides"):
    """Attach reasons to each region from the measured effects that overlap it (their boxes
    grown by `pad`, since a glow spills past its element). A region only counts as explained
    when those boxes cover at least `cover` of it: a whole-slide difference with one glowing
    headline inside it is not explained by the headline."""
    out = []
    # an approximation explains a region only if the preview draws it too; one on the slide
    # background covers everything, so it only explains regions with nothing drawn over them
    approx = [a for a in model.get("approximations", []) if a.get("visible")]
    for r in regions:
        reasons, near, covered = [], None, 0
        bare = not any(overlap(r, it) for it in model.get("items", []))
        for u in model.get("unsupported", []) + substitutions(model, brand, target) + approx:
            if u.get("background") and not bare: continue
            grown = {"x": u["x"] - pad, "y": u["y"] - pad, "w": u["w"] + 2 * pad, "h": u["h"] + 2 * pad}
            o = overlap(r, grown)
            if o > 0:
                covered += o
                for e in u["effects"]:
                    reasons.append({"effect": e, "on": u["label"]})
        if reasons and covered < cover * r["w"] * r["h"]:
            reasons = []   # effects are nearby, but most of this region differs for some other reason
        if not reasons:
            best = 0
            for it in model["items"]:
                o = overlap(r, it)
                if o > best and it["type"] == "text":
                    best, near = o, "".join(x.get("t", "") for x in it["runs"])[:40]
        out.append({**r, "reasons": reasons, "near": near})
    return out

def verdict(score, regions, notes=()):
    """notes: approximations the slide carries whether or not the comparison shows them.
    A tiny score forgives explained differences, never unexplained ones: a missing bullet is a few pixels."""
    kinds = {reason["effect"] for r in regions for reason in r["reasons"]}
    unexplained = any(not r["reasons"] for r in regions)
    if unexplained: return "other"
    if not regions or score < 0.0015: return "approximated" if notes else "faithful"
    if not kinds or unexplained or not all(k.startswith(EFFECT_KINDS + APPROX_KINDS) for k in kinds):
        return "other"
    return "approximated" if notes or any(k.startswith(APPROX_KINDS) for k in kinds) else "effects-only"

TREATMENTS = {"faithful": ["editable"], "effects-only": ["editable", "glow-behind", "picture"],
              "approximated": ["editable", "picture"], "other": ["editable", "picture"]}

def treatments(v, regions=()):
    """An approximated slide that also loses a glow can have the glow baked behind it."""
    if v == "approximated" and any(x["effect"].startswith(EFFECT_KINDS) for r in regions for x in r["reasons"]):
        return ["editable", "glow-behind", "picture"]
    return TREATMENTS[v]

def overlay(raw_png, regions, out_png):
    from PIL import Image, ImageDraw
    im = Image.open(raw_png).convert("RGB"); d = ImageDraw.Draw(im)
    for r in regions:
        d.rectangle([r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]], outline=(255, 60, 60) if not r["reasons"] else (255, 200, 0), width=4)
    im.thumbnail((960, 540)); im.save(out_png)

# ── run ─────────────────────────────────────────────────────────────────────
def run(deck_json, version="mainstage", only=None, workdir=None):
    try:
        import PIL  # noqa: F401
    except ImportError:
        sys.exit("fidelity: needs Pillow (pip install pillow)")
    folder, deck, cfg = load_deck(deck_json, version)
    file_rel = deck_file(deck, version)
    if not file_rel: sys.exit(f'fidelity: deck.json names no file for the {version} (a one-version deck puts its file under "deck")')
    deck_html = (folder / file_rel).read_text()
    brand = common.load_brand(folder)
    target = (cfg.get("pptx") or {}).get("target") or "google-slides"
    chrome = common.chrome_path(brand)
    work = Path(workdir) if workdir else folder / ".deck-builder" / "fidelity" / version
    work.mkdir(parents=True, exist_ok=True)
    n_slides = slide_count(deck_html)
    base = "/" + (str(Path(file_rel).parent) + "/" if str(Path(file_rel).parent) not in (".", "") else "")
    results = []
    with Stage(folder) as st:
        for n in range(1, n_slides + 1):
            if only and n not in only: continue
            raw = common.screenshot(chrome, st.url(file_rel, n, "raw"), work / f"{n:02d}-raw.png")
            model = measure(st, chrome, file_rel, n)
            if not raw or not model or "error" in model:
                results.append({"slide": n, "verdict": "other", "error": "could not render or measure this slide", "treatments": ["picture"]})
                continue
            (work / f"{n:02d}-model.json").write_text(json.dumps(model))
            prev = common.screenshot(chrome, st.add_preview(f"p{n}", preview_html(model, brand, deck_html, base, target=target)), work / f"{n:02d}-preview.png")
            score, regions = diff_regions(raw, prev)
            regions = explain(regions, model, brand=brand, target=target)
            notes = slide_notes(model, brand, target)
            v = verdict(score, regions, notes)
            overlay(raw, regions, work / f"{n:02d}-overlay.png")
            results.append({"slide": n, "verdict": v, "treatments": treatments(v, regions), "score": round(score, 4), "regions": regions,
                            "approximations": notes,
                            "raw": str(work / f"{n:02d}-raw.png"), "preview": str(work / f"{n:02d}-preview.png"),
                            "overlay": str(work / f"{n:02d}-overlay.png")})
    labels = re.findall(r"<section\b[^>]*data-label=\"([^\"]*)\"", deck_html)
    import decks_config
    saved_choices = decks_config.slides_for(deck, version)
    for r in results:
        r["label"] = labels[r["slide"] - 1] if r["slide"] - 1 < len(labels) else ""
        r["saved"] = saved_choices.get(str(r["slide"]))
    report = {"deck": str(deck_json), "version": version, "slides": results, "workdir": str(work)}
    if not only:   # a partial run doesn't replace the full report the exporter reads
        (work / "report.json").write_text(json.dumps(report, indent=1))
    return report

def summary(report):
    lines = []
    groups = {}
    for r in report["slides"]:
        if r["verdict"] == "faithful": sig = "looks the same editable"
        elif r.get("error"): sig = r["error"]
        else:
            kinds = sorted({re.sub(r' ".*$', "", x["effect"]) for g in r["regions"] for x in g["reasons"]} | set(r.get("approximations") or []))
            unexplained = sum(1 for g in r["regions"] if not g["reasons"])
            sig = ", ".join(kinds) + (f"{', ' if kinds else ''}{unexplained} unexplained difference(s)" if unexplained else "")
        groups.setdefault((r["verdict"], sig), []).append(r)
    order = {"faithful": 0, "effects-only": 1, "approximated": 2, "other": 3}
    for (v, sig), rs in sorted(groups.items(), key=lambda kv: order[kv[0][0]]):
        nums = ", ".join(str(r["slide"]) for r in rs)
        lines.append(f"{v:13} slides {nums}: {sig}  → {' / '.join(rs[0]['treatments'])}")
        for r in rs:
            if r.get("saved"): lines.append(f"{'':13}   slide {r['slide']} saved as {r['saved']}")
    return "\n".join(lines)

if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("deck"); a.add_argument("--version", choices=["mainstage", "leave-behind"], default="mainstage")
    a.add_argument("--only", help="comma-separated slide numbers"); a.add_argument("--json", action="store_true")
    a.add_argument("--workdir")
    args = a.parse_args()
    only = {int(x) for x in args.only.split(",")} if args.only else None
    rep = run(args.deck, args.version, only, args.workdir)
    print(json.dumps(rep, indent=1) if args.json else summary(rep) + f"\nrenders and overlays: {rep['workdir']}")
