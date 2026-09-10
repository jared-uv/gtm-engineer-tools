---
title: Campaign registry — every outbound campaign, where its replies land, and what to do with them
status: live
owner: YOUR NAME
last_updated: YYYY-MM-DD

# ── reply-queue config ────────────────────────────────────────────────
surface: slack               # slack | email
surface_id: D0123456789      # Slack DM/channel id, or an email address
draft_mailbox: you@company.com
voice:                       # optional path to a voice/author profile
window_hours: 3              # reply lookback; keep ≥ the routine interval
---

# Campaign registry

One row per campaign you have in flight: where it lives, who it went to, what a reply should get, when to nudge, and what bookkeeping a yes triggers. `/reply-queue` and its routine run off this file and nothing else.

**A campaign that is not in this file does not get worked.** Enforced from both sides: the checker also diffs your sources' running campaigns against this table on every run and flags any it doesn't recognise at the top of the queue.

## Adding a campaign

Before the first message goes out, add a row to the index and a playbook section below. The playbook needs five things, and a section missing any of them makes the checker guess:

1. **Where** — the source adapter and its ids. `mail:` with a search that isolates the thread set, `sequencer:` with campaign ids, or `manual:` (which the checker cannot see; replies get handed over by hand).
2. **The ask** — one line, so a reply can be judged against it.
3. **Reply buckets** — what a yes, a question, a no and an out-of-office each get, and where the copy comes from.
4. **Nudge** — the rule for silence. Most sequences carry their own follow-ups; the nudge rule is for after the sequence ends, or for anything sent by hand. One nudge, then stop, is the house default.
5. **Bookkeeping** — the CRM tag, the ledger row, the lead to end in a sibling campaign. This is the part that gets dropped when replies come in fast, and the part that matters months later.

Set `status` honestly. `live` is being worked. A campaign paused in the sequencer still receives replies, so it stays `live` here until its stop date. `done` means nothing more will come in that needs an answer.

## The index

| Slug | Campaign | Where | Status | Stop date | Playbook |
|---|---|---|---|---|---|
| `example-outbound` | Example — Q3 outbound to ops leaders | `sequencer:cam_abc123` (email) · `mail:from:them subject:"the ask"` | live | 2026-12-01 | below |
| `example-manual` | Example — hand-sent LinkedIn asks | `manual:linkedin` | live | rolling | below |

---

## Playbook — `example-outbound`

Copy this section per campaign. Delete the commentary once it's real.

**Where.** `sequencer:cam_abc123` for the email sequence. Replies also land in `draft_mailbox`, so the mail adapter catches anything the sequencer hasn't synced.

**The ask.** One sentence: what this campaign asked the recipient to do. A reply can only be judged against a stated ask.

**Reply buckets.**

| They said | It gets | Copy from |
|---|---|---|
| **Yes** | The booking link and the two-line what-to-expect | `outbound/example/yes.md` |
| **Question** | Answer from the repo. If the answer isn't written down, surface it — don't compose one | — |
| **No / not now** | One-line thanks, no argument, no re-pitch | `outbound/example/no.md` |
| **Out of office** | Nothing. Re-enters the nudge window on their return date | — |
| **Referral** | Thank them, then treat the named person as a new contact — not as a reply | `outbound/example/referral.md` |

**Nudge.** 9 days after the sequence's last step, once. Copy: `outbound/example/nudge.md`. Skip anyone with steps still pending.

**Bookkeeping.** A yes gets the CRM tag `example-yes` and a row in the pipeline. If they also sit in `example-manual`, end that lead — it's UI-only, so the card lists it rather than doing it.

**Escalate, don't draft.** Anything about price, discounts or contract terms that isn't already written down in the repo.

---

## Playbook — `example-manual`

**Where.** `manual:linkedin`. The checker cannot see these. Replies are handed over by hand, and this row exists so the campaign shows up in the report and in the nudge sweep.

**The ask.** …

*(remaining sections as above)*
