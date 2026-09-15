# deck-builder

Build a talk as HTML slides in your own brand, keep a leave-behind and a mainstage version of it in sync, and export a PDF plus a PowerPoint file that opens editable in Google Slides.

Where an editable copy can't look like the slide you designed, it tells you which slides, what they'd lose, and lets you choose: editable, editable with the effect baked in behind the text, or a picture.

It pairs with [deck-graphics](../deck-graphics/), which fills the logos, props and screenshots. Neither needs the other.

## The problem

A talk usually needs two decks. One is for the stage, where a slide full of text splits the room between listening and reading. The other is sent afterwards and has to make sense with nobody presenting it. Kept by hand, they drift within a week.

Then someone asks for the slides "in Google Slides so I can edit them". A PowerPoint made of pictures of your slides isn't editable. One rebuilt from shapes is editable but quietly loses whatever Google Slides can't draw: a glow on a headline, a font it doesn't have, a blend mode. You find out on the day, in front of the room.

## Install

```
/plugin marketplace add le0li0n/gtm-engineer-tools
/plugin install deck-builder
```

It needs Python 3.9+, Chrome or Chromium, and for the fidelity check and the PowerPoint export, `pip install pillow python-pptx`.

## Bring your own brand

The plugin ships no design system. Put one `brand.json` at your repo root, and both this plugin and deck-graphics read it:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckbuilder.py" brand .
```

That writes a neutral template. Fill it from your design system: colors, display, body and mono fonts, any text glow, logo, illustrations, and a pointer to where the design system lives. That can be a Claude Design handoff folder, a Figma file or a tokens stylesheet. Each font gets a `slides_equivalent`, the Google Slides font the editable copy uses in its place. If your font is a Google Font, it's the same name.

Don't commit anyone else's brand into your file, and don't commit yours into a plugin.

## Start a talk

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckbuilder.py" new talks/q3-keynote --title "What changed this quarter"
```

That writes both HTML versions from a four-slide starter, the slide runtime, a tokens stylesheet that imports your brand's, and `deck.json`. Or run `/deck-builder:build`, which walks the whole thing with you.

## Opinionated defaults, every one adjustable

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckbuilder.py" settings talks/q3-keynote/deck.json
```

That prints every setting in effect, what it does, where it came from, and how to change it. Each build starts with a one-line summary, so nothing is applied silently.

| Setting | Default | Change or remove |
|---|---|---|
| `versions` | leave-behind + mainstage | `["single"]` |
| `mainstage.max_words` | 5 | any number, or `null` |
| `mainstage.graphics_per_slide` | 2 | any number, or `null` |
| `mainstage.label_exemption` | diagram labels marked `data-words="exempt"` don't count | `false` |
| `sync.check` | count, order, labels | any subset, or `[]` |
| `sync.notes` | mainstage notes generated from the leave-behind | `"manual"` |
| `exports` | pdf, pptx | any subset |
| `pptx.mode` | editable, with per-slide picture fallback | `"pictures"` |
| `pptx.unfaithful` | ask | `"auto"` |
| `pptx.target` | google-slides | `"powerpoint"` |
| `checks.writing` | slop-check, if installed | `null` |
| `checks.spelling` | en-US | another locale, or `null` |

Set one for every talk in `brand.json › decks`, or for one talk in `deck.json › overrides`.

**A deck with one version** names its file under `deck` instead of `leave_behind` and `mainstage`, and sets `versions` to `["single"]`:

```
{"title": "Q3 keynote", "deck": "q3-keynote.html", "overrides": {"versions": ["single"]}}
```

`check`, `export` and `build` then work on that file whichever version they're asked for, and `sync` has nothing to compare, so it says so and passes.

**Two versions that export differently** set the difference under `version_overrides`, keyed by version name. It's a separate key because `mainstage` inside `overrides` already means the mainstage settings. Per-slide choices can be split the same way inside `slides`:

```
{
  "leave_behind": "talk.html", "mainstage": "talk-mainstage.html",
  "version_overrides": {"leave-behind": {"pptx": {"mode": "pictures"}}},
  "slides": {"mainstage": {"1": "glow-behind"}}
}
```

Here the mainstage exports editable with slide 1's glow kept behind its text, and the leave-behind exports as pictures. A flat `slides` map (`{"1": "picture"}`) still applies to every version.

## Keeping the two versions in sync

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckbuilder.py" sync talks/q3-keynote/deck.json [--write-notes]
```

It checks that both versions have the same slides in the same order with the same labels. It also checks each mainstage slide against the word and graphics limits, and names every problem by slide.

With `--write-notes`, it rewrites each mainstage speaker note from its leave-behind slide, word for word. The hand-written part after the `— — —` line stays: the ten-second version and the delivery note. The rest of the file is left byte for byte.

## Which slides survive as editable

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckbuilder.py" check talks/q3-keynote/deck.json
```

This is the check that doesn't need to know what can go wrong in advance. Each slide is rendered twice:

- **as designed**, in Chrome
- **from only the shapes the editable PowerPoint will contain**: text boxes, filled and bordered boxes, gradients, images

The two renders are compared, allowing for a pixel or two of drift. Any area that differs is something the editable copy loses. Each difference is then explained where possible by what's measured on the slide: glowing or shadowed text, a shadow on a shape, a CSS decoration. Some things the editable copy draws close rather than exact, and those are named as approximations whether or not they show in the comparison: a font Google Slides doesn't have and the one it's swapped for, a gradient with extra layers or a repeat, a radial gradient's spread. A difference nothing explains is reported with its position so a person can look.

The slides come back grouped:

```
approximated  slides 2, 3, 4, 5, 9, 10, 13, 15: glowing or shadowed text, letter spacing not in Google Slides, weight 800 drawn as bold, weight 900 drawn as bold  → editable / glow-behind / picture
approximated  slides 6, 11: font not in Google Slides: SF Mono → Roboto Mono, glowing or shadowed text, letter spacing not in Google Slides, weight 900 drawn as bold  → editable / glow-behind / picture
approximated  slides 17: glowing or shadowed text, gradient approximated: radial gradient: spread is close, not exact, in PowerPoint and Google Slides, letter spacing not in Google Slides, weight 900 drawn as bold  → editable / glow-behind / picture
```

Google Slides has no letter spacing and sets a run bold or regular, so a deck in a tracked, black-weight brand will read "approximated" nearly everywhere. That is the check being accurate, not noisy; set `pptx.target` to `"powerpoint"` if that's where the deck opens.

A line that doesn't wrap in the browser is exported in a box wide enough to survive that wider setting, because Google Slides wraps even a `wrap="none"` box at its width on import.

For each slide there's a render, a preview of the editable version, and an overlay with the differences boxed, under `.deck-builder/fidelity/`. Add that folder to `.gitignore`.

## Export

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckbuilder.py" export talks/q3-keynote/deck.json --treat 1=picture,2=glow-behind --save
```

- **editable**: native shapes. Anything the shapes can't draw, like an SVG or a canvas, is placed as a picture cut from the render, so nothing goes missing.
- **glow-behind**: editable text with the effect rendered on a transparent picture underneath. It looks right as delivered. If you change the words, the glow still shows the old ones.
- **picture**: the slide as rendered, exact, not editable. Rendered at twice the slide's size (3840×2160), so it stays sharp on a projector or a 4K screen; the effects behind glow-behind text and the cut-outs of anything shapes can't draw are rendered the same way.

`--save` records the choices in `deck.json` so the next export doesn't ask. Speaker notes come along. The PDF prints from the HTML, so it keeps every effect.

## What it can't promise

- **Chrome predicts Google Slides; it doesn't prove it.** Text metrics differ between the two, so a line that fits exactly in the browser can wrap in Slides. Open the PowerPoint in Google Slides and flip through it once before it matters.
- **Layout is read from the rendered slide, in paint order.** Stacking set with `z-index` isn't modelled.
- **Gradients keep their first and last stops.** A three-stop radial glow comes out as a two-stop radial.

## Runtime

`runtime/deck.js` is a small `<slide-deck>` web component. It scales to fit, navigates by keyboard and touch, shows speaker notes with `N`, follows `#N` in the URL, and prints one slide per page. The checks and exports don't depend on it: they pin one slide at a time with CSS. That means decks built on another runtime work too, as long as slides are `<section>` children of the deck element.

## Tests

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/test_sync.py"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/test_fidelity.py"
```

Neither needs Chrome or a network.
