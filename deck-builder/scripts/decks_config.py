#!/usr/bin/env python3
"""deck-builder settings: the defaults, where they come from, and how to say them out loud.

The defaults are defined here and nowhere else. Three layers, later wins:

  1. DEFAULTS below                         (the plugin's opinions)
  2. brand.json › decks                     (a company's settings, found walking up from the deck)
  3. deck.json › overrides                  (one talk's exceptions)

`null` in a later layer means "switched off" and survives the merge: `"max_words": null`
stops the word check, it does not fall back to 5. Keys starting with "_" are notes for
humans and are ignored by the loader.

    from decks_config import load, describe
    cfg = load("marketing/decks/my-talk/deck.json")
    print(describe(cfg))
"""
import copy, json
from pathlib import Path

BRAND_NAME = "brand.json"
DECK_NAME = "deck.json"

DEFAULTS = {
    "versions": ["leave-behind", "mainstage"],
    "mainstage": {
        "max_words": 5,
        "graphics_per_slide": 2,
        "label_exemption": True,
        "exempt_selectors": ["[data-words=exempt]", "[data-placeholder]"],
        "placeholder_selectors": ["[data-placeholder]"],
    },
    "sync": {
        "check": ["count", "order", "labels"],
        "notes": "leave-behind-verbatim",
    },
    "placeholders": "brief",
    "exports": ["pdf", "pptx"],
    "pptx": {
        "mode": "editable",
        "unfaithful": "ask",
        "target": "google-slides",
    },
    "checks": {
        "writing": "slop-check",
        "spelling": "en-US",
    },
}

DESCRIPTIONS = {
    "versions": "Two builds of the talk: a leave-behind that reads alone and a mainstage the presenter talks over. [\"single\"] for one deck.",
    "mainstage": {
        "max_words": "Word limit per mainstage slide, checked by sync. A number, or null to stop checking.",
        "graphics_per_slide": "Most graphics (img, svg, picture, placeholders) per mainstage slide. A number, or null.",
        "label_exemption": "Diagram labels marked with an exempt selector don't count toward the word limit. false to count them.",
        "exempt_selectors": "Elements whose text doesn't count toward the word limit when label_exemption is on.",
        "placeholder_selectors": "Elements that are graphic placeholders: they count as graphics, and their brief never counts as words.",
    },
    "sync": {
        "check": "What must match between the two versions: any of count, order, labels. [] to check nothing.",
        "notes": "\"leave-behind-verbatim\": mainstage speaker notes are generated from the leave-behind slide's text. \"manual\" to write them by hand.",
    },
    "placeholders": "\"brief\": a missing graphic shows as a dashed box saying what goes there. \"hide\" to leave the space empty.",
    "exports": "What build writes: any of pdf, pptx.",
    "pptx": {
        "mode": "\"editable\": native shapes, with a per-slide picture fallback. \"pictures\" for a flat deck.",
        "unfaithful": "What to do with a slide the editable rebuild can't reproduce: \"ask\", or \"auto\" to apply the per-issue defaults.",
        "target": "Which font list and effect support the fidelity check uses: \"google-slides\" or \"powerpoint\".",
    },
    "checks": {
        "writing": "AI-tells check on slide copy and notes, run when the slop-check plugin is installed. null to skip.",
        "spelling": "Locale for a spelling pass, e.g. en-US. null to skip.",
    },
}

# ── merging ─────────────────────────────────────────────────────────────────
def deep_merge(base, over):
    """Merge `over` into `base` in place. Dicts merge key by key; everything else, None
    included, replaces. Keys starting with "_" in `over` are skipped."""
    for k, v in (over or {}).items():
        if k.startswith("_"): continue
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = copy.deepcopy(v)
    return base

def get(cfg, dotted, default=None):
    cur = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur: return default
        cur = cur[part]
    return cur

# ── discovery ───────────────────────────────────────────────────────────────
def find_brand(start):
    """The first brand.json walking up from `start` (a file or a folder); None if absent."""
    p = Path(start).resolve()
    if p.is_file(): p = p.parent
    for d in (p, *p.parents):
        if (d / BRAND_NAME).is_file(): return d / BRAND_NAME
    return None

def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"deck-builder: {path} is not valid JSON: {e}")

def effective(start):
    """DEFAULTS merged with the brand.json found from `start`, without any deck overrides."""
    cfg = copy.deepcopy(DEFAULTS)
    brand = find_brand(start)
    if brand:
        deep_merge(cfg, _read_json(brand).get("decks") or {})
    return cfg, brand

def load(deck_json_path, version=None):
    """The settings for one deck: DEFAULTS, then brand.json › decks, then deck.json › overrides,
    then, when a version is given, deck.json › version_overrides › that version.

    version_overrides is its own key because `mainstage` inside overrides already means the
    mainstage settings group. A talk whose two versions export differently uses it:
    {"version_overrides": {"leave-behind": {"pptx": {"mode": "pictures"}}}}."""
    p = Path(deck_json_path).resolve()
    if not p.is_file(): raise SystemExit(f"deck-builder: no deck.json at {p}")
    deck = _read_json(p)
    cfg, brand = effective(p.parent)
    sources = ["defaults"] + ([str(brand)] if brand else [])
    deep_merge(cfg, deck.get("overrides") or {})
    sources.append(str(p))
    per_version = (deck.get("version_overrides") or {}).get(version) if version else None
    if per_version:
        deep_merge(cfg, per_version)
        sources.append(f"{p} › version_overrides › {version}")
    cfg["_sources"] = sources
    cfg["_deck"] = deck
    cfg["_dir"] = str(p.parent)
    cfg["_path"] = str(p)
    cfg["_version"] = version
    return cfg

def slides_for(deck, version):
    """The per-slide export choices for a version. deck.json › slides is either one map for every
    version ({"1": "picture"}) or one map per version ({"mainstage": {"1": "picture"}}). In the
    per-version form, a version with no map of its own has no saved choices."""
    s = deck.get("slides") or {}
    if isinstance(s.get(version), dict):
        return {k: v for k, v in s[version].items() if not k.startswith("_")}
    if any(isinstance(v, dict) for v in s.values()):
        return {}
    return {k: v for k, v in s.items() if not k.startswith("_")}

# ── saying it out loud ──────────────────────────────────────────────────────
def two_versions(cfg):
    v = cfg.get("versions") or []
    return "leave-behind" in v and "mainstage" in v

def describe(cfg):
    """One line naming every active setting, so a build never runs on a default nobody saw."""
    parts = []
    v = cfg.get("versions") or []
    if not v or v == ["single"] or len(v) == 1:
        parts.append("one version" + (f" ({v[0]})" if len(v) == 1 and v[0] != "single" else ""))
    elif two_versions(cfg) and len(v) == 2:
        parts.append("two versions (leave-behind + mainstage)")
    else:
        parts.append(f"{len(v)} versions ({' + '.join(v)})")

    if "mainstage" in v:
        mw = get(cfg, "mainstage.max_words")
        parts.append("no word limit" if mw is None else f"≤{mw} words a mainstage slide")
        g = get(cfg, "mainstage.graphics_per_slide")
        parts.append("no graphics limit" if g is None else f"≤{g} graphics")
    if two_versions(cfg):
        chk = get(cfg, "sync.check")
        parts.append("no sync checks" if not chk else "sync checks " + "/".join(chk))
        notes = get(cfg, "sync.notes")
        parts.append("notes from the leave-behind" if notes == "leave-behind-verbatim" else "notes by hand")

    ex = cfg.get("exports")
    if not ex:
        parts.append("no exports")
    else:
        s = "exports " + " + ".join(ex)
        if "pptx" in ex:
            mode = get(cfg, "pptx.mode")
            if mode == "pictures":
                s += " (pictures)"
            else:
                s += f" ({mode or 'editable'}, {get(cfg, 'pptx.unfaithful') or 'ask'} on unfaithful slides)"
        parts.append(s)
    return "building with: " + ", ".join(parts) + " — change in brand.json › decks or deck.json › overrides"

# ── writing a deck.json ─────────────────────────────────────────────────────
def init_deck_json(dir, title, leave_behind, mainstage, force=False):
    """Write deck.json in `dir` with empty overrides and a snapshot of every setting in effect.
    Never overwrites unless `force`."""
    d = Path(dir).resolve(); d.mkdir(parents=True, exist_ok=True)
    dest = d / DECK_NAME
    if dest.exists() and not force:
        raise FileExistsError(f"{dest} exists")
    cfg, brand = effective(d)
    data = {
        "title": title,
        "leave_behind": leave_behind,
        "mainstage": mainstage,
        "overrides": {},
        "_about": ("Put changes under overrides, using the same keys as _settings_in_effect. null switches a "
                   "setting off. _settings_in_effect is a snapshot for reading; the loader ignores it."),
        "_settings_in_effect": cfg,
        "_settings_from": ["defaults"] + ([str(brand)] if brand else []),
    }
    dest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return dest
