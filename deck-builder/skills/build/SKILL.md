---
name: build
description: >-
  Build a talk as HTML slides in the user's own brand, keep a leave-behind and a mainstage
  version in sync, and export a PDF plus a PowerPoint file that opens editable in Google Slides.
  Finds the slides an editable copy can't reproduce by comparing renders, and asks the user per
  group of slides: editable, editable with effects baked behind, or a picture. Use when the user
  says "/deck-builder:build", "build a deck", "make slides for my talk", "export this deck to
  Google Slides", "make an editable version", or hands you a deck.json. Pass the deck.json path,
  or a folder to start a new talk in.
---

# build

The scripts render, measure, compare and export. Your job is the parts they can't do: write slides that read well, show the user the settings they're building with, put each editability trade-off in front of them in plain words, and look at the renders before calling anything done.

Every script lives in `${CLAUDE_PLUGIN_ROOT}/scripts/`. The front door is `deckbuilder.py`.

## 0. Brand first

The plugin ships no brand. Look for `brand.json` above the deck folder.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckbuilder.py" brand <repo root>
```

If there isn't one, that writes a neutral template. Fill it with the user from **their** design system: ask where it lives (a Claude Design handoff folder, a Figma file, a brand guide, a tokens CSS file) and read it. Never invent brand values, and never copy another company's design system into theirs. The fonts section needs a `slides_equivalent` for each family: the Google Slides font the editable copy will use. If their font is a Google Font it's the same name.

## 1. Start, and say the settings out loud

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckbuilder.py" new <folder> --title "..."
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckbuilder.py" settings <folder>/deck.json
```

`new` writes both HTML versions from the starter templates, the slide runtime, a tokens stylesheet and `deck.json`. `settings` prints every setting with what it does.

**Tell the user the one-line "building with" summary before you write a slide**, and that each setting can be changed or switched off in `brand.json › decks` for all talks or `deck.json › overrides` for this one. The defaults are opinions: two versions, five words a mainstage slide, two graphics, notes from the leave-behind, editable PowerPoint. Don't enforce one the user has switched off, and don't argue for it more than once.

## 2. Write the leave-behind, then the mainstage from it

With two versions on:

- **Leave-behind first.** Everything on the slide; it has to read without a presenter.
- **Mainstage composed from it**, slide for slide, same order, same `data-label`. At most `mainstage.max_words` words and `mainstage.graphics_per_slide` graphics a slide. The presenter says the leave-behind's words.
- Diagram labels that shouldn't count toward the word limit go inside an element with `data-words="exempt"`. A graphic that isn't made yet is `<div data-placeholder>` with a brief of what goes there, not slide copy.
- Slides are `<section data-label="...">` children of `<slide-deck>`, laid out at 1920×1080 with the brand tokens.

For graphics — logos, props in the house style, app-screen mocks — hand off to the deck-graphics plugin if it's installed (`/deck-graphics:fill`), and swap placeholders for its files.

## 3. Sync

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckbuilder.py" sync <deck.json>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckbuilder.py" sync <deck.json> --write-notes
```

The first checks count, order, labels, words and graphics and names each problem by slide. Fix the slide, or, if the user means to bend a rule there, mark the exemption in the markup; don't quietly raise a limit. `--write-notes` regenerates each mainstage speaker note from its leave-behind slide and keeps the human-written ten-second version and delivery note after the `— — —` line. Fill any `[write this]` placeholders it leaves.

## 4. The fidelity check, and the user's choices

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckbuilder.py" check <deck.json>
```

It renders each slide as designed, renders it again from only what an editable PowerPoint can carry, and compares the two. It prints slides grouped by what they'd lose:

- **faithful**: editable looks the same. Nothing to decide.
- **effects-only**: the loss is glows, shadows or CSS decorations. Offer **editable** (the effect is gone), **glow-behind** (text stays editable, the effect is a picture underneath it; if they later change the words, the glow still shows the old ones), or **picture** (exact, not editable).
- **approximated**: the editable copy draws something close rather than exact — a font Google Slides doesn't have swapped for one it does, a gradient simplified (the report names how). Glows may be lost too. Offer **editable** or **picture**, and **glow-behind** when a glow is part of it.
- **other**: something else differs — an SVG, a filter, or a difference nothing explains. Offer **editable** or **picture**.

**Look before you ask.** Open the overlay PNGs it names (`NN-overlay.png`: yellow boxes are differences an effect explains, red ones aren't) and the matching `NN-preview.png` for any slide in "other". Then describe each group to the user in a sentence, in terms of what they'll see: "Slides 2 to 5: the headline glow is the only thing lost." Ask **once per group**, not once per slide, and let them split a group. A title slide going picture while the rest go editable is a normal answer.

A red region is not automatically a real loss. If the preview shows the check itself got a slide wrong, say so, and don't ask the user to choose on the strength of it.

## 5. Export

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckbuilder.py" export <deck.json> --treat 1=picture,2=glow-behind,17=glow-behind --save
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckbuilder.py" export <deck.json> --version leave-behind
```

`--save` records the choices in `deck.json › slides` so the next export doesn't ask. The PowerPoint gets speaker notes. The PDF prints from the HTML, so it keeps every effect.

Report what went where. If any slide exported editable only because nobody decided, say which.

**The PowerPoint is not verified until someone opens it in Google Slides.** Chrome's renders predict it; they don't prove it. Text metrics differ between Chrome and Slides, so a line that fits exactly in the browser can wrap in Slides. Say this plainly, and ask the user to flip through it once.

## 6. Before it goes out

- If `checks.writing` is on and the slop-check plugin is installed, run it on the leave-behind text and the speaker notes.
- If `checks.spelling` is set, read for that locale by eye.

## Rules

- The user's design system, never someone else's. Brand values come from their files or from them.
- Never use the image model or a screenshot to fake text that should be editable.
- Every choice about editability is the user's. Recommend; don't decide silently.
- Keys, if any are involved, stay in `.env`.
