#!/usr/bin/env python3
"""Generate a slide graphic from a prompt, in a named style, through one of two providers.

    python3 imagegen.py --prompt "a t-shirt cannon firing into a stadium crowd" \
        --style prop --out decks/x/assets/generated/cannon.png

    python3 imagegen.py --provider fal --prompt "..." --ref path/to/ref.png --out ...

Providers, picked with --provider (default: whichever key is set, OpenRouter first):

  openrouter  POST https://openrouter.ai/api/v1/images   (one key, many models)
              default model google/gemini-3.1-flash-image — "Nano Banana 2"
  fal         queue.fal.run/<model>  submit → poll → result  (image-first, deeper knobs)
              default model fal-ai/nano-banana-2 (or /edit when references are given)

Keys come from the environment, then from the first .env found walking up from the
output folder: OPENROUTER_API_KEY, FAL_KEY.

Styles come from .deckgraphics.json (found the same way, or --config). A style is a
prompt preamble plus reference images passed alongside the prompt so the model matches
props you already have. `none` is always available and means the prompt as written.

Every image gets a sidecar .json beside it recording provider, model, prompt, refs,
seed and cost, so a deck can be rebuilt and a graphic re-rolled from the same recipe.

This never draws text. Words on a slide are text boxes; image models spell.
"""
import argparse, base64, json, mimetypes, os, sys, time, urllib.request, urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config, load_env, key, png_size

TOOL = "imagegen"

# ── helpers ─────────────────────────────────────────────────────────────────
def data_url(path):
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()

def http(method, url, headers, body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={**headers, **({"Content-Type": "application/json"} if data else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:600]
        sys.exit(f"{TOOL}: {method} {url} → HTTP {e.code}\n{detail}")

def fetch_bytes(url, timeout=120):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()

def build_prompt(style, prompt):
    return (style.get("preamble", "") + " " + prompt).strip()

# ── providers ───────────────────────────────────────────────────────────────
def gen_openrouter(prompt, refs, model, aspect, seed, n, background):
    body = {"model": model or "google/gemini-3.1-flash-image", "prompt": prompt,
            "n": n, "aspect_ratio": aspect, "output_format": "png"}
    if background: body["background"] = background
    if seed is not None: body["seed"] = seed
    if refs:
        body["input_references"] = [{"type": "image_url", "image_url": {"url": data_url(r)}} for r in refs]
    res = http("POST", "https://openrouter.ai/api/v1/images",
               {"Authorization": f"Bearer {key('OPENROUTER_API_KEY', TOOL)}"}, body)
    images = [base64.b64decode(d["b64_json"]) for d in res.get("data", []) if d.get("b64_json")]
    return images, {"model": body["model"], "cost": (res.get("usage") or {}).get("cost")}

def gen_fal(prompt, refs, model, aspect, seed, n, background):
    if not model:
        model = "fal-ai/nano-banana-2/edit" if refs else "fal-ai/nano-banana-2"
    body = {"prompt": prompt, "num_images": n, "output_format": "png",
            "aspect_ratio": aspect if aspect else "auto", "resolution": "1K"}
    if seed is not None: body["seed"] = seed
    if refs: body["image_urls"] = [data_url(r) for r in refs]
    H = {"Authorization": f"Key {key('FAL_KEY', TOOL)}"}
    sub = http("POST", f"https://queue.fal.run/{model}", H, body)
    status_url, result_url = sub["status_url"], sub["response_url"]
    for _ in range(120):
        st = http("GET", status_url, H)
        if st.get("status") == "COMPLETED": break
        time.sleep(2)
    else:
        sys.exit(f"{TOOL}: fal request did not complete in time")
    res = http("GET", result_url, H)
    images = [fetch_bytes(im["url"]) for im in res.get("images", [])]
    return images, {"model": model, "cost": None, "request_id": sub.get("request_id")}

PROVIDERS = {"openrouter": (gen_openrouter, "OPENROUTER_API_KEY"), "fal": (gen_fal, "FAL_KEY")}

# ── entry ───────────────────────────────────────────────────────────────────
def generate(prompt, out, style=None, refs=(), provider=None, model=None,
             aspect=None, seed=None, n=1, background=None, config=None):
    out = Path(out)
    load_env(out.parent)
    cfg = load_config(out.parent, config)
    style = style or cfg.get("default_style") or "none"
    if style not in cfg["styles"]:
        sys.exit(f"{TOOL}: no style '{style}' in {cfg['_path'] or 'the built-in set'}; have {', '.join(cfg['styles'])}")
    st = cfg["styles"][style]
    full_prompt = build_prompt(st, prompt)
    all_refs = [r for r in st["refs"] if Path(r).is_file()] + [str(r) for r in refs]
    aspect = aspect or st["aspect"]
    if provider is None:
        provider = next((p for p, (_, k) in PROVIDERS.items() if os.environ.get(k)), None)
        if provider is None:
            sys.exit(f"{TOOL}: no provider key set (OPENROUTER_API_KEY or FAL_KEY).")
    fn, _ = PROVIDERS[provider]
    images, meta = fn(full_prompt, all_refs, model, aspect, seed, n, background)
    if not images:
        sys.exit(f"{TOOL}: provider returned no image")
    out.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for i, b in enumerate(images):
        p = out if i == 0 else out.with_name(f"{out.stem}-{i+1}{out.suffix}")
        p.write_bytes(b); written.append(p)
    sidecar = {"kind": "generated", "provider": provider, "style": style, "prompt": prompt, "full_prompt": full_prompt,
               "refs": all_refs, "aspect": aspect, "seed": seed, "background": background,
               **meta, "files": [str(p) for p in written], "size": png_size(images[0])}
    out.with_suffix(".json").write_text(json.dumps(sidecar, indent=2))
    return written, sidecar

if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--prompt", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--style", help="a style from .deckgraphics.json; default_style there, else none")
    a.add_argument("--ref", action="append", default=[], help="extra reference image (repeatable)")
    a.add_argument("--provider", choices=list(PROVIDERS))
    a.add_argument("--model")
    a.add_argument("--aspect", help="1:1, 16:9, 4:3 …")
    a.add_argument("--seed", type=int)
    a.add_argument("--n", type=int, default=1)
    a.add_argument("--background", choices=["transparent", "opaque"], help="OpenRouter only, where the model supports it")
    a.add_argument("--config", help="path to .deckgraphics.json (default: found walking up from --out)")
    args = a.parse_args()
    files, meta = generate(args.prompt, args.out, args.style, args.ref, args.provider, args.model,
                           args.aspect, args.seed, args.n, args.background, args.config)
    print(f"{files[0]}  {meta['size'] and '%dx%d' % meta['size']}  via {meta['provider']}/{meta['model']}"
          + (f"  ${meta['cost']:.3f}" if meta.get('cost') else ""))
