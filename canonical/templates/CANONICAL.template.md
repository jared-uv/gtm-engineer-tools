# Where things live

The registry every agent and every teammate reads before looking for company information, and before creating a file that holds some. One row per kind of information. If it is not here, nobody agreed where it goes yet, so add the row first.

Ask it: `/canonical:where <type>`. See what nobody has confirmed lately: `/canonical:where --stale`. Validate after editing: `/canonical:where --check`.

**Where** is an ordered list. Look in the first place, then the next, and stop when found. Separate places with `then`. **Class** is `open` (anyone writes), `governed` (the owner holds the pen; others propose) or `external` (a system of record reached through a tool). **Cadence** is how often the owner has to re-confirm the entry is still right: `30d`, `6w`, `3m`, `1y`, or `-`. **Reviewed** is the date they last did.

The paths below are suggestions. Replace each with where the thing really lives, or delete the row.

| Type | Where | Class | Required | Owner | Cadence | Reviewed | Notes |
|---|---|---|---|---|---|---|---|
| What the company is | docs/company.md | governed | yes | | 3m | - | Industry, offerings, business model, size. The file every other document builds on. |
| Ideal customer | docs/icp.md | governed | yes | | 3m | - | |
| Positioning | docs/positioning.md | governed | yes | | 3m | - | One answer. Do not reconstruct it from old decks. |
| Messaging and offers | docs/messaging.md | governed | yes | | 3m | - | |
| Voice | docs/voice.md | governed | yes | | 6m | - | |
| Live campaigns | campaigns/ | governed | yes | | 2w | - | One file per campaign, written before its first send. |
| Published content | content/ | open | no | | - | - | Drafts, one file per piece. |
| Call transcripts | transcripts/ | open | no | | - | - | Raw. Never cite in outward content without curating first. |
| Tasks and todos | tasks: name the tool here | external | yes | | - | - | Repos hold work products; the tracker holds actions. |
| Contacts and accounts | crm: name it here | external | yes | | - | - | |
