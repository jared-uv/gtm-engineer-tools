---
name: fill
description: >-
  Fill a deck's graphics manifest — logos through a source chain, on-style props through
  an image model, app-screen mocks through Chrome — then look at every image and judge it
  before it goes in. Use when the user says "/deck-graphics:fill", "fill the placeholders",
  "get the logos for this deck", "generate the icons", or hands you a graphics.json.
  Pass the manifest path.
---

# fill

The scripts fetch and generate. The part that makes the result trustworthy is you looking at every PNG and deciding whether it goes in. Do not skip that.

## Steps

1. **Validate, then read the state.** `$ARGUMENTS` is the manifest path.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckgraphics.py" check $ARGUMENTS
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckgraphics.py" status $ARGUMENTS
```

   `check` says whether every entry has what its kind needs and whether the styles exist. `status` is one line per graphic: present or missing, pixel size, and what the sidecar says about where it came from.

2. **Plan and price it before spending.**

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckgraphics.py" fill $ARGUMENTS --dry-run
```

   Say the count and the estimated cost to the user. Generated images cost money (about $0.07 each through OpenRouter as of 2026-09); logos and mocks are free. Then run it without `--dry-run`. One failed entry does not stop the run; the summary lists what failed.

3. **Look at every new file with the Read tool.** Judge each one on these, and only these:
   - **Does it read at slide size?** A prop that needs a caption to be recognized is not a prop. Squint.
   - **Does it match the style references?** Same material, same lighting, same camera. A stray glossy object among flat ones goes back.
   - **Is there text baked in?** Image models spell. Anything with letters is a re-roll; words on a slide are text boxes.
   - **Is a logo on a transparent ground?** Corners should be transparent. A white tile on a dark slide is a re-fetch, not a crop.
   - **Is a logo the right mark?** A favicon-tier hit can be some other site's icon, a wordmark instead of the symbol, or 32 px. The sidecar's `source` and `tried` tell you which tier answered. Say so plainly; do not upscale and hope.
   - **Does a mock carry real names or data?** Mocks use synthetic names. If a template has a real customer in it, fix the template.

4. **Fix what failed the look.**
   - A prop: change the prompt (name the object more plainly, add "not a …" for what it drifted toward) and re-run that entry with `--only <id> --force`. Add `"seed"` to the entry to pin a roll you like.
   - A logo the chain got wrong: find the right source and pin it with `"url"` on the entry (Wikimedia Commons SVGs cover most household marks), or set `"prefer": "favicon"` when the favicon is the better mark. Re-run with `--only <id> --force`.
   - A mock: edit the HTML template and re-run; the renderer re-renders anything older than its template.

5. **Give the user the same look.** Build the review page and hand it over:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckgraphics.py" sheet $ARGUMENTS
```

   One page, every graphic grouped by key prefix, `note` and sidecar under each. Add `--embed` when it has to travel (a link, a shared file). When the manifest holds several treatments of one figure (`growth-current`, `growth-rich`, `growth-hybrid`), the sheet is where the user picks; do not pick for them.

6. **Report.** Run `status` again and give the user the counts, every entry that is still soft (favicon tier, small pixel size, by-hand screenshots) with the reason, and the money spent. Then hand off to whatever builds the deck; this plugin stops at the assets.

## Rules

- Never recolor a brand's own logo. Only the SimpleIcons tier is monochrome, and those are monochrome by design.
- Never invent a mark. If nothing on the chain is the real logo, say the slot is soft and leave the best available with its sidecar.
- Never draw text with the image model. When a figure needs labels over generated art, make a `mock` whose template embeds the generated PNG and sets the words in HTML; `fill` renders it after the illustration and re-renders it when the illustration changes.
- Keys stay in `.env`. Never print them, never commit them.
