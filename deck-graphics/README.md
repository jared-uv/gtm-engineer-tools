# deck-graphics

Fill a deck's graphics from a manifest, and record where each one came from. Logos through a Brandfetch → SimpleIcons → favicon chain. On-style props through an image model, with your existing illustrations as references so the new ones match. App-screen mocks through headless Chrome. Every file gets a sidecar `.json` saying which source or which model, prompt and seed produced it.

Assets and sidecars only. The deck builder is yours. This plugin stops at the PNGs.

## The problem

A talk needs thirty small graphics: a dozen vendor logos, a handful of icons in the house style, three screenshots that show an app without showing a customer. Doing that by hand is an afternoon of right-click-save-as and a second afternoon in an image tool, and none of it is reproducible. Doing it with an image model alone gets you thirty things that don't match each other.

The fix is a manifest per deck, a style file per company, and a loop: fetch or generate, look at every result, re-roll or pin a source, and keep the recipe beside the file so the deck can be rebuilt.

## Install

```
/plugin marketplace add le0li0n/gtm-engineer-tools
/plugin install deck-graphics
```

Then, at your repo root:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckgraphics.py" init
```

That writes `.deckgraphics.json`. Describe your house style in it: a prompt preamble and two to four reference images the model should match. Put keys in a `.env` beside it (gitignored):

| Key | For | Where |
|---|---|---|
| `OPENROUTER_API_KEY` | generated props (Nano Banana 2 by default; one key, many models) | openrouter.ai |
| `FAL_KEY` | generated props through fal.ai instead, `"provider": "fal"` on the entry | fal.ai |
| `BRANDFETCH_CLIENT_ID` | real logos instead of favicons | brandfetch.com, free tier |

Without a Brandfetch ID the logo chain still answers, from SimpleIcons and Google's favicon service, at lower quality. Without either image key, `generated` entries fail and everything else works.

## The manifest

One `graphics.json` per deck, next to the deck. Keys starting with `_` are notes; every other key is one graphic. `_assets_dir` (default `assets/generated`) is where logo rows put their files.

| kind | needs | optional |
|---|---|---|
| `logo` | `domain`, `file` | `type` icon / logo / symbol, `theme` dark / light, `prefer` a source, `url` a pinned source |
| `logo-row` | `domains[]` | `pins` {domain: url}, `prefer` {domain: source}. Writes `logo-<slug>.png` per domain into the assets dir. |
| `generated` | `prompt`, `file` | `style`, `provider`, `model`, `seed`, `aspect` |
| `mock` | `template` (HTML), `file` | The template may embed other entries' outputs; see "Mocks over generated art". |
| `screenshot` | `file` | `brief`. Nothing is fetched; someone captures it by hand. |

Any entry may also carry `note`, one sentence for whoever reviews the sheet. Nothing else reads it.

Keys group by everything before their last hyphen: `growth-current`, `growth-rich` and `growth-hybrid` are three treatments of one figure, and `sheet` shows them side by side. Name variants that way and the review page organizes itself.

The slug for a domain drops the TLD and joins the labels innermost-last: `calendar.google.com` → `googlecalendar`, `notion.so` → `notion`. A deck builder that names its placeholders the same way can find the files without a lookup.

`templates/graphics.template.json` shows one of each.

## The commands

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckgraphics.py" check  decks/x/graphics.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckgraphics.py" status decks/x/graphics.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckgraphics.py" fill   decks/x/graphics.json [--only id] [--force] [--dry-run]
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deckgraphics.py" sheet  decks/x/graphics.json [--out file] [--embed]
```

`status` is one line per graphic with the pixel size and what the sidecar says. `fill --dry-run` prints the plan and the estimated cost and does nothing. One failed entry does not stop a run.

`sheet` writes one HTML page with every graphic in the manifest, grouped by key prefix, each with its `note` and what its sidecar says underneath. It is the same look the skill takes, handed to a person: open it, squint, decide. `--embed` inlines the images downscaled (JPEG for opaque, PNG where there is transparency) so the page can be sent or published on its own; without Pillow the images go in at full size.

## Mocks over generated art

A mock template can embed another entry's output — an illustration the image model made, with real labels laid over it in HTML. That is the way to get labeled figures without letting the model draw text: the picture is generated, the words are type.

`fill` knows about this. Mocks always render last, and a mock whose template references a file another entry is writing in the same run waits for it (`--dry-run` says `after icon-whistle.png`). A rendered mock is stale, and re-rendered, when its template *or any local image it references* is newer than its PNG — so a re-rolled illustration re-renders every mock built on it. References are `url(…)` in the template's CSS and `src="…"` in its HTML, relative to the template; remote URLs and `data:` URIs are ignored. The sidecar lists the inputs.

The three tools behind it can be run on their own: `logos.py <domain> --out …`, `imagegen.py --prompt … --out …`, `render_mocks.py <manifest>`.

## The loop, which is the point

`/deck-graphics:fill` runs the commands and then looks at every PNG with the Read tool and judges it: does it read at slide size, does it match the references, is there text baked in, is the logo on a transparent ground, is it the right mark. What fails goes back with a changed prompt, a pinned seed, a pinned URL, or a different preferred source. The skill file has the checklist.

That look is what makes the result trustworthy. The chain degrades instead of failing, so a miss produces *something*, and the sidecar says how good it is. Read the sidecar, look at the file.

## What the logo chain has learned

- Brandfetch answers in WebP, which python-pptx can't embed; it goes through Chrome to PNG. Its `theme/dark` variants still ship some marks on an opaque white square, so the white ground is flood-filled away from the corners (white inside the mark stays). It resolves Google subdomains to the plain G, and has some vendors only as a wordmark.
- Removing a white ground leaves the anti-aliased edge behind: pixels that were the mark blended with white, which read as a pale halo on a dark slide. The knockout now defringes a 2-px ring along the new edge, turning the whiteness into transparency and un-blending the color. It helps; an SVG is still better. When a household mark has a halo, pin its SVG with `url` (Wikimedia Commons has Slack, Gmail, Google Calendar and Drive) and nothing needs knocking out at all.
- SimpleIcons' CDN has dropped marks the npm package still ships (OpenAI, Slack). The package on jsDelivr is the fallback, with a fill painted on.
- Google's favicon service always answers, which means it will answer with some other site's icon for a domain behind a bot challenge. A 32-px result is a 32-px result; say so rather than upscale.
- `url` pins a source when the chain gets a mark wrong. Wikimedia Commons SVGs cover most household marks.
- `theme` is the color of the *mark*, not of the slide: `dark` returns a dark mark for a light page, `light` a white one for a dark page. Ask for `light` on a white deck and twelve logos come back invisible.

## What the image model rejects

The default model (Gemini image, through either provider) accepts a fixed set of aspect ratios: 1:1, 1:4, 1:8, 2:3, 3:2, 3:4, 4:1, 4:3, 4:5, 5:4, 8:1, 9:16, 16:9, 21:9. Anything else — 2:1, say — is rejected with an HTTP 400 after the request is made. `check` notes an aspect outside that list before you spend.

Brand marks in a talk are nominative use. Nothing here recolors a brand's own logo; only the monochrome SimpleIcons tier takes a color.

## Dependencies

- **Python 3.9+**, standard library for everything except the white knockout and nothing else.
- **Pillow**, optional. Without it, white grounds stay white and the tool says so in the sidecar's `url`.
- **Chrome or Chromium** for mocks and for SVG and WebP logos. Found at the usual macOS path or on `PATH`; override with `DECKGRAPHICS_CHROME` or `"chrome"` in the config. The renderer watches for the output file instead of waiting for Chrome to exit, because a helper process can hold stdout open long after the screenshot is written.

## Tests

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/test_deck_graphics.py" "${CLAUDE_PLUGIN_ROOT}/scripts/deckgraphics.py"
```

No network, no Chrome, no keys. Config discovery, `.env` loading, the slug rule, manifest validation, status and dry-run planning, and the white knockout when Pillow is present.

## What it doesn't do

Build the deck. A builder that reads the manifest and places `file` per entry is fifty lines of python-pptx or a `<img>` per placeholder in an HTML deck, and it is where the house style lives, so it stays with the house. The first user of this plugin fills a seventeen-slide talk with 44 graphics and 0 placeholders left, at about $1.20 in image calls, and its builder is a few hundred lines that are nobody else's business.
